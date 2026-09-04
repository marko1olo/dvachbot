# -*- coding: utf-8 -*-
"""
combat_moderation_engine.py — Natural Balancing & Community Appeal Engine for /partyvan and /shoot
================================================================================================
Prevents oligarchic and hysterical mute abuse by:
1. Progressive mute duration based on attacker's 24-hour weapon attack frequency.
2. Target Activity Multiplier (active posters resist longer mutes).
3. Hard Newbie Immunity (posts_count < 25 are immune from lethal PvP mutes).
4. False Report & Misfire Escalation (backfire chance scales up to 80% for spam attackers).
5. Community Appeal System: 3 uninvolved anons can vote to cancel an unfair mute and fine the attacker.
6. Instant Bail / Bribe Button on the announcement card.
"""

import time
import asyncio
import random
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from common.db_pool import get_pool, db_lock, db_transaction
from common.anon_identity import get_anon_id

logger = logging.getLogger("runtime")

# --- Constants ---
NEWBIE_POSTS_THRESHOLD = 50
APPEAL_WINDOW_SEC = 600.0   # 10 minutes for community appeal
APPEAL_VOTES_REQUIRED = 3   # 3 uninvolved anons needed to overturn
ATTACKER_FALSE_REPORT_FINE = 500.0  # ₪ fine for overturned abuse

# 24-hour weapon usage records: attacker_id -> list of (timestamp, target_id, weapon_type)
_ATTACKER_COMBAT_HISTORY: Dict[int, List[Tuple[float, int, str]]] = defaultdict(list)
_COMBAT_ENGINE_LOCK = asyncio.Lock()

# Target attack records: (attacker_id, target_id) -> last_attack_ts
_TARGET_PAIR_LAST_ATTACK: Dict[Tuple[int, int], float] = {}

@dataclass
class CombatAppealSession:
    session_id: str
    board_id: str
    attacker_id: int
    target_id: int
    weapon_type: str  # 'partyvan' or 'shoot'
    duration_sec: int
    created_ts: float
    voters: Set[int] = field(default_factory=set)
    is_appealed: bool = False
    is_bailed: bool = False
    bailed_by: Optional[int] = None
    announcement_msg_id: Optional[int] = None
    chat_id: Optional[int] = None

active_combat_appeals: Dict[str, CombatAppealSession] = {}

combat_moderation_router = Router(name="combat_moderation_router")


def clean_combat_history():
    """Prunes attack records older than 24 hours."""
    now = time.time()
    cutoff_24h = now - 86400.0
    cutoff_pair = now - 1800.0  # 30 minutes pair cooldown

    for uid, history in list(_ATTACKER_COMBAT_HISTORY.items()):
        fresh = [entry for entry in history if entry[0] > cutoff_24h]
        if fresh:
            _ATTACKER_COMBAT_HISTORY[uid] = fresh
        else:
            _ATTACKER_COMBAT_HISTORY.pop(uid, None)

    for pair, ts in list(_TARGET_PAIR_LAST_ATTACK.items()):
        if ts <= cutoff_pair:
            _TARGET_PAIR_LAST_ATTACK.pop(pair, None)

    # Clean expired appeals
    cutoff_appeal = now - APPEAL_WINDOW_SEC
    for sid, sess in list(active_combat_appeals.items()):
        if sess.created_ts <= cutoff_appeal and not sess.is_appealed and not sess.is_bailed:
            active_combat_appeals.pop(sid, None)


def get_attacker_24h_usage_count(attacker_id: int, weapon_type: Optional[str] = None) -> int:
    """Returns how many times attacker used weapons in the last 24h."""
    now = time.time()
    cutoff = now - 86400.0
    history = _ATTACKER_COMBAT_HISTORY.get(attacker_id, [])
    if weapon_type:
        return sum(1 for ts, _, wtype in history if ts > cutoff and wtype == weapon_type)
    return sum(1 for ts, _, _ in history if ts > cutoff)


def record_combat_attack(attacker_id: int, target_id: int, weapon_type: str):
    """Records an attack event in 24h history and pair cooldown."""
    now = time.time()
    _ATTACKER_COMBAT_HISTORY[attacker_id].append((now, target_id, weapon_type))
    _TARGET_PAIR_LAST_ATTACK[(attacker_id, target_id)] = now


def check_pair_attack_cooldown(attacker_id: int, target_id: int) -> Tuple[bool, int]:
    """
    Prevents an attacker from griefing the EXACT SAME target repeatedly within 15 minutes.
    Returns (is_blocked, remaining_seconds).
    """
    now = time.time()
    last_ts = _TARGET_PAIR_LAST_ATTACK.get((attacker_id, target_id), 0.0)
    cooldown = 900.0  # 15 minutes
    if now - last_ts < cooldown:
        return True, int(cooldown - (now - last_ts))
    return False, 0


def calculate_combat_duration_and_backfire(
    attacker_id: int,
    target_id: int,
    weapon_type: str,
    target_posts: int
) -> Tuple[int, bool, float]:
    """
    Calculates:
      1. Progressive mute duration (seconds) based on attacker's 24h frequency.
      2. Target activity resistance multiplier (posts_count reduction).
      3. Backfire chance & trigger (false report / gun explosion).

    Returns:
      (final_duration_sec: int, is_backfire: bool, backfire_chance: float)
    """
    clean_combat_history()
    attacks_24h = get_attacker_24h_usage_count(attacker_id, weapon_type)

    # 1. Base duration & backfire scaling by attack count
    if weapon_type == "partyvan":
        # Partyvan base durations: 6h -> 3h -> 1.5h -> 1h
        if attacks_24h == 0:
            base_duration = 21600  # 6 hours
            backfire_chance = 0.0
        elif attacks_24h == 1:
            base_duration = 10800  # 3 hours
            backfire_chance = 0.15
        elif attacks_24h == 2:
            base_duration = 5400   # 1.5 hours
            backfire_chance = 0.40
        else:
            base_duration = 3600   # 1 hour
            backfire_chance = 0.75
    else:  # shoot (мут-ган)
        # Mute-gun base durations: 15m -> 10m -> 5m -> 1m
        if attacks_24h == 0:
            base_duration = 900    # 15 minutes
            backfire_chance = 0.0
        elif attacks_24h == 1:
            base_duration = 600    # 10 minutes
            backfire_chance = 0.15
        elif attacks_24h == 2:
            base_duration = 300    # 5 minutes
            backfire_chance = 0.40
        else:
            base_duration = 60     # 1 minute
            backfire_chance = 0.70

    # 2. Backfire roll
    is_backfire = (random.random() < backfire_chance)
    if is_backfire:
        return 0, True, backfire_chance

    # 3. Target Activity Resistance Multiplier (по требованию заказчика):
    # - posts_count < 50: полный отлёт атаки (рикошет / иммунитет новичка) -> 0 сек
    # - 50 <= posts_count < 250: сокращение длительности на -30% (множитель 0.70)
    # - posts_count >= 250: стандартное время без поблажек (множитель 1.00)
    if target_posts < 50:
        multiplier = 0.0
    elif target_posts < 250:
        multiplier = 0.70
    else:
        multiplier = 1.00

    if multiplier == 0.0:
        return 0, False, backfire_chance

    final_duration = max(60, int(round(base_duration * multiplier)))
    return final_duration, False, backfire_chance


def get_partyvan_flavor_text(attacks_24h: int) -> str:
    """Returns 2ch-styled black humor flavor text based on daily partyvan frequency."""
    if attacks_24h <= 0:
        return "🚔 <b>ОМОН сработал по первому разряду!</b> Наряд прибыл в масках, шмон с пристрастием, камера-одиночка."
    elif attacks_24h == 1:
        return "🚨 <b>В местном ОВД переполнение!</b> Менты устали строчить протоколы на твоих оппонентов. Срок урезан до 3 часов!"
    elif attacks_24h == 2:
        return "🚨 <b>Товарищ майор не спеша пьёт чай с пряниками</b> и зевает от твоих кляуз. Дежурный выписал задержанному УДО через 1.5 часа!"
    else:
        return "🚨 <b>В честь дня рождения Абу объявлена амнистия!</b> В обезьяннике кончились свободные шконки, задержанный выйдет уже через 1 час!"


def format_duration_str(seconds: int) -> str:
    """Formats seconds into human readable Russian time."""
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}ч {mins}мин" if mins > 0 else f"{hours}ч"
    elif seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}мин {secs}с" if secs > 0 else f"{mins}мин"
    return f"{seconds}с"


def create_combat_appeal_session(
    board_id: str,
    attacker_id: int,
    target_id: int,
    weapon_type: str,
    duration_sec: int,
    chat_id: Optional[int] = None,
    announcement_msg_id: Optional[int] = None
) -> str:
    """Registers an appeal session for an executed mute."""
    clean_combat_history()
    now = time.time()
    session_id = f"ca_{int(now)}_{attacker_id}_{target_id}"
    active_combat_appeals[session_id] = CombatAppealSession(
        session_id=session_id,
        board_id=board_id,
        attacker_id=attacker_id,
        target_id=target_id,
        weapon_type=weapon_type,
        duration_sec=duration_sec,
        created_ts=now,
        chat_id=chat_id,
        announcement_msg_id=announcement_msg_id
    )
    return session_id


def get_combat_appeal_keyboard(
    session_id: str,
    current_votes: int = 0,
    required_votes: int = APPEAL_VOTES_REQUIRED,
    is_appealed: bool = False,
    is_bailed: bool = False
) -> InlineKeyboardMarkup:
    """Builds interactive community appeal & bail buttons."""
    if is_appealed:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Мут аннулирован решением общества", callback_data=f"cainfo:{session_id}:appealed")
        ]])
    if is_bailed:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💸 Мут снят внесением залога", callback_data=f"cainfo:{session_id}:bailed")
        ]])

    appeal_text = f"⚖️ Опротестовать [{current_votes}/{required_votes}]"
    bail_text = "💸 Внести залог (Взятка)"

    keyboard = [
        [
            InlineKeyboardButton(text=appeal_text, callback_data=f"cappeal:{session_id}"),
            InlineKeyboardButton(text=bail_text, callback_data=f"cbail:{session_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def reset_combat_moderation_state():
    """Resets memory state for tests."""
    _ATTACKER_COMBAT_HISTORY.clear()
    _TARGET_PAIR_LAST_ATTACK.clear()
    active_combat_appeals.clear()


# --- AIOGRAM CALLBACK HANDLERS ---

@combat_moderation_router.callback_query(F.data.startswith("cappeal:"))
async def callback_combat_appeal(callback: types.CallbackQuery):
    """
    Handles community appeal button click '⚖️ Опротестовать [x/3]'.
    3 uninvolved anons with posts_count >= 10 can cancel the mute.
    """
    session_id = callback.data.split(":", 1)[1]
    sess = active_combat_appeals.get(session_id)
    if not sess:
        await callback.answer("⏳ Время на опротестование этого мута истекло.", show_alert=True)
        return

    voter_id = callback.from_user.id

    # 1. Attacker cannot appeal own attack
    if voter_id == sess.attacker_id:
        await callback.answer("🚫 Доносчик не может голосовать за отмену собственного доноса!", show_alert=True)
        return

    # 2. Target cannot self-vote
    if voter_id == sess.target_id:
        await callback.answer("🚫 Жертва не может голосовать сама за себя! Нужна поддержка других анонов треда.", show_alert=True)
        return

    # 3. Double-voting check
    if voter_id in sess.voters:
        await callback.answer("⚠️ Ты уже отдал свой голос за отмену этого мута!", show_alert=False)
        return

    # 4. Voter eligibility: minimum 10 posts to avoid burner bot brigades
    db = await get_pool()
    async with db.execute("SELECT posts_count FROM Users WHERE user_id = ? AND board_id = ?", (voter_id, sess.board_id)) as cur:
        row = await cur.fetchone()
        voter_posts = row[0] if row and row[0] is not None else 0

    if voter_posts < 10:
        await callback.answer("⛔ Голосовать за апелляцию могут только участники с 10+ постами на борде.", show_alert=True)
        return

    # Add vote
    sess.voters.add(voter_id)
    current_votes = len(sess.voters)

    if current_votes < APPEAL_VOTES_REQUIRED:
        await callback.answer(f"⚖️ Твой протест учтен ({current_votes}/{APPEAL_VOTES_REQUIRED})!", show_alert=False)
        # Update button text
        kb = get_combat_appeal_keyboard(session_id, current_votes, APPEAL_VOTES_REQUIRED)
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return

    # 5. Overturn threshold reached!
    sess.is_appealed = True
    active_combat_appeals.pop(session_id, None)

    # Immediately remove mute
    from common.bot_helpers import remove_regular_mute
    await remove_regular_mute(sess.target_id, sess.board_id)
    from shared_state import set_partyvan_victim_immunity
    set_partyvan_victim_immunity(sess.target_id, int(time.time()) + 3600)

    # Fine the false accuser / abusive attacker
    try:
        from main import deduct_user_global_balance
        await deduct_user_global_balance(db, sess.attacker_id, sess.board_id, ATTACKER_FALSE_REPORT_FINE)
    except Exception as e:
        logger.error(f"Error fining attacker {sess.attacker_id}: {e}")

    await callback.answer("⚖️ Единогласный протест принят! Мут немедленно аннулирован!", show_alert=True)

    overturn_text = (
        f"⚖️ <b>МУТ АННУЛИРОВАН ОБЩЕСТВОМ!</b> ⚖️\n\n"
        f"Аноны треда признали применение оружия <b>необоснованной истерикой</b> ({APPEAL_VOTES_REQUIRED}/{APPEAL_VOTES_REQUIRED} голосов).\n"
        f"• С жертвы <b>[ID:{sess.target_id}]</b> немедленно сняты все наручники и ограничения!\n"
        f"• Выдан полный иммунитет от повторных атак на 1 час.\n"
        f"• С доносчика <b>[ID:{sess.attacker_id}]</b> удержан штраф <code>-{int(ATTACKER_FALSE_REPORT_FINE)} ₪</code> за клевету и телефонный терроризм!"
    )
    kb = get_combat_appeal_keyboard(session_id, current_votes, APPEAL_VOTES_REQUIRED, is_appealed=True)
    try:
        await callback.message.edit_text(overturn_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass


@combat_moderation_router.callback_query(F.data.startswith("cbail:"))
async def callback_combat_bail(callback: types.CallbackQuery):
    """
    Handles instant bail payment button '💸 Внести залог (Взятка)'.
    Allows the victim or any generous comrade to bail out the victim for shekels.
    """
    session_id = callback.data.split(":", 1)[1]
    sess = active_combat_appeals.get(session_id)
    if not sess:
        await callback.answer("⏳ Время действия этого мута или залога истекло.", show_alert=True)
        return

    payer_id = callback.from_user.id
    db = await get_pool()

    # Determine bail price (using shop price of bribe or standard 500₪)
    try:
        from main import get_current_item_price
        bail_cost = get_current_item_price("bribe")
    except Exception:
        bail_cost = 600.0

    async with db.execute("SELECT balance FROM Users WHERE user_id = ? AND board_id = ?", (payer_id, sess.board_id)) as cur:
        row = await cur.fetchone()
        payer_bal = row[0] if row and row[0] is not None else 0.0

    if payer_bal < bail_cost:
        await callback.answer(f"💸 Недостаточно шекелей! Для выкупа требуется {int(bail_cost)} ₪ (у тебя {int(payer_bal)} ₪).", show_alert=True)
        return

    # Deduct balance
    from main import deduct_user_global_balance, remove_regular_mute
    await deduct_user_global_balance(db, payer_id, sess.board_id, bail_cost)
    await remove_regular_mute(sess.target_id, sess.board_id)
    from shared_state import set_partyvan_victim_immunity
    set_partyvan_victim_immunity(sess.target_id, int(time.time()) + 3600)

    sess.is_bailed = True
    sess.bailed_by = payer_id
    active_combat_appeals.pop(session_id, None)

    payer_tag = "Жертва лично внесла" if payer_id == sess.target_id else f"Благородный анон [ID:{payer_id}] внес"
    await callback.answer("💸 Залог успешно принят! Анон освобожден из-под ареста!", show_alert=True)

    bail_text = (
        f"💸 <b>ВЫКУП ИЗ-ПОД АРЕСТА!</b> 💸\n\n"
        f"{payer_tag} залог майору в размере <code>{int(bail_cost)} ₪</code>.\n"
        f"С анона <b>[ID:{sess.target_id}]</b> сняты все ограничения, выдан иммунитет на 1 час!"
    )
    kb = get_combat_appeal_keyboard(session_id, is_bailed=True)
    try:
        await callback.message.edit_text(bail_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass


@combat_moderation_router.callback_query(F.data.startswith("cainfo:"))
async def callback_combat_info(callback: types.CallbackQuery):
    """Informational click on finished sessions."""
    action = callback.data.split(":")[-1]
    if action == "appealed":
        await callback.answer("⚖️ Этот мут уже был отменен общественным голосованием анонов.", show_alert=True)
    elif action == "bailed":
        await callback.answer("💸 Этот мут уже был снят внесением залога (взятки).", show_alert=True)
    else:
        await callback.answer("ℹ️ Сессия завершена.", show_alert=False)
