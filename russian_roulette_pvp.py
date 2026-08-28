# -*- coding: utf-8 -*-
"""
russian_roulette_pvp.py — High-Stakes 2-Player PvP Russian Roulette for ТГАЧ / Двач
===================================================================================
Features & Mechanics:
1. Revolver Drum: 6 chambers, exactly 1 live round (шанс выстрела растет с каждым щелчком: 1/6 -> 1/5 -> 1/4 -> 1/3 -> 1/2 -> 1/1).
2. 2-Player Turn-Based PvP: Challenger vs Acceptor (open challenge or targeted via reply/ID).
3. Strict Turn Timer: 60.0 seconds per turn. Auto-forfeit on cowardice / timeout.
4. Financial Escrow: Atomic balance deduction on accept, 5% rake to Abu's Fund, winner takes pot.
5. Loser Penalty: Full bet loss + 30-MINUTE MUTE (1800s) in DB & RAM.
6. Winner Reward: Pot payout + transaction log + achievement check (ach_duel_win).
7. Chat Announcement: Public broadcast to the board stream with authentic 2ch flavor.
8. Background Watchdog: Proactively times out idle games and resolves bets/mutes automatically.
"""

import os
import io
import time
import json
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import shared_state
from common.db_pool import get_pool, db_lock
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    add_to_abu_fund,
    record_user_transaction,
    apply_regular_mute
)
from common.anon_identity import get_anon_id

logger = logging.getLogger("runtime")

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
MIN_RR_BET = 50
MAX_RR_BET = 10_000_000
RR_CHAMBERS_COUNT = 6
RR_TURN_TIMEOUT_SEC = 60.0
RR_CHALLENGE_TIMEOUT_SEC = 120.0
RR_MUTE_DURATION_SEC = 1800  # 30 minutes
RR_RAKE_PERCENT = 0.05  # 5% to Abu's Fund

# In-memory storage for active games & challenges
active_rr_games: Dict[str, Dict[str, Any]] = {}
user_active_rr_game: Dict[int, str] = {}
rr_lock = asyncio.Lock()

# Router instance
rr_router = Router(name="russian_roulette_pvp")
router = rr_router


def generate_game_id() -> str:
    """Generates unique alphanumeric game ID."""
    return f"rr_{int(time.time() * 1000)}_{random.randint(100, 999)}"


# -----------------------------------------------------------------------------
# Visual & Message Formatting Helpers
# -----------------------------------------------------------------------------

def format_drum_visual(current_chamber: int, is_finished: bool = False, outcome: Optional[str] = None) -> str:
    """
    Renders visual 6-chamber revolver drum representation.
    ⚪ - Unfired chamber
    💨 - Empty chamber (Click / Survived)
    🎯 - Current loaded chamber ready to fire
    💥 - Live round detonated (Death)
    """
    slots = []
    for idx in range(RR_CHAMBERS_COUNT):
        if idx < current_chamber:
            slots.append("💨")
        elif idx == current_chamber:
            if is_finished and outcome == "shot":
                slots.append("💥")
            elif is_finished:
                slots.append("⚪")
            else:
                slots.append("🎯")
        else:
            slots.append("⚪")
    return f"[{ ' '.join(slots) }]"


def get_shot_probability(current_chamber: int) -> float:
    """Calculates current chamber live round probability percentage."""
    remaining = max(1, RR_CHAMBERS_COUNT - current_chamber)
    return round((1.0 / remaining) * 100, 1)


def format_rr_challenge_message(game: Dict[str, Any]) -> str:
    """Formats HTML text for pending challenge lobby."""
    challenger_id = game["challenger_id"]
    target_id = game.get("target_id")
    bet = game["bet"]
    ch_anon = get_anon_id(challenger_id)

    target_str = f"Анона <b>[ID:{get_anon_id(target_id)}]</b>" if target_id else "любого смелого анона"

    text = (
        f"💀 <b>РУССКАЯ РУЛЕТКА: ВЫЗОВ НА СМЕРТЕЛЬНУЮ ДУЭЛЬ!</b>\n\n"
        f"👤 <b>Инициатор:</b> Анон <b>[ID:{ch_anon}]</b>\n"
        f"🎯 <b>Цель:</b> Вызов брошен для {target_str}!\n"
        f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code> | <b>Банк:</b> <code>{bet * 2:,} ₪</code>\n\n"
        f"📜 <b>Условия дуэли:</b>\n"
        f"• Револьвер: <b>6 камор, 1 боевой патрон</b>.\n"
        f"• Поочередный спуск курка с таймером <b>60 секунд на ход</b>.\n"
        f"• 💥 <b>Проигравший:</b> получает пулю в лоб, теряет ставку и <b>МУТ НА 30 МИНУТ</b>!\n"
        f"• 👑 <b>Победитель:</b> забирает весь банк!\n\n"
        f"⏳ <i>Вызов активен 2 минуты. Нажми кнопку ниже для принятия боя.</i>"
    )
    return text


def format_rr_game_message(game: Dict[str, Any], last_action_text: Optional[str] = None) -> str:
    """Formats active or finished game card."""
    p1 = game["challenger_id"]
    p2 = game["acceptor_id"]
    bet = game["bet"]
    pot = bet * 2
    cur_ch = game["current_chamber"]
    turn = game["turn"]
    outcome = game.get("outcome")
    finished = game.get("finished", False)

    p1_anon = get_anon_id(p1)
    p2_anon = get_anon_id(p2) if p2 else "Ожидание..."

    drum_vis = format_drum_visual(cur_ch, is_finished=finished, outcome=outcome)
    prob = get_shot_probability(cur_ch)

    if finished:
        winner_id = game.get("winner_id")
        loser_id = game.get("loser_id")
        win_anon = get_anon_id(winner_id) if winner_id else "???"
        lose_anon = get_anon_id(loser_id) if loser_id else "???"
        payout = game.get("payout", pot)

        if outcome == "shot":
            header = "💥 <b>ДУЭЛЬ ЗАВЕРШЕНА: ВЫСТРЕЛ В ЛОБ!</b>"
            status_desc = (
                f"💀 <b>Анон [ID:{lose_anon}]</b> спустил курок на <b>{cur_ch + 1}-й каморе</b>...\n"
                f"💥 <b>БАХ!</b> Мозги забрызгали стены треда!\n\n"
                f"👑 <b>Победитель:</b> Анон <b>[ID:{win_anon}]</b> забирает банк <code>+{payout:,} ₪</code>!\n"
                f"🔇 <b>Проигравший:</b> Анон <b>[ID:{lose_anon}]</b> отправлен в <b>МУТ НА 30 МИНУТ</b>!"
            )
        elif outcome == "timeout":
            header = "⏱️ <b>ДУЭЛЬ ЗАВЕРШЕНА: ТАЙМАУТ / ТРУСОСТЬ!</b>"
            status_desc = (
                f"🐔 <b>Анон [ID:{lose_anon}]</b> зассал и не нажал на спуск за <b>60 секунд</b>!\n\n"
                f"👑 <b>Победитель:</b> Анон <b>[ID:{win_anon}]</b> забирает банк <code>+{payout:,} ₪</code> за трусость оппонента!\n"
                f"🔇 <b>Трус:</b> Анон <b>[ID:{lose_anon}]</b> отправлен в <b>МУТ НА 30 МИНУТ</b>!"
            )
        else:  # surrender
            header = "🏳️ <b>ДУЭЛЬ ЗАВЕРШЕНА: ДОБРОВОЛЬНАЯ СДАЧА!</b>"
            status_desc = (
                f"😭 <b>Анон [ID:{lose_anon}]</b> выронил револьвер и сдался в слезах!\n\n"
                f"👑 <b>Победитель:</b> Анон <b>[ID:{win_anon}]</b> забирает банк <code>+{payout:,} ₪</code>!\n"
                f"🔇 <b>Сдавшийся:</b> Анон <b>[ID:{lose_anon}]</b> отправлен в <b>МУТ НА 30 МИНУТ</b>!"
            )

        text = (
            f"{header}\n\n"
            f"💰 <b>Банк дуэли:</b> <code>{pot:,} ₪</code>\n"
            f"🔫 <b>Барабан:</b> {drum_vis}\n\n"
            f"{status_desc}"
        )
        return text

    # Active playing state
    turn_anon = get_anon_id(turn)
    rem_sec = max(0, int(game["turn_deadline_ts"] - time.time()))

    action_block = f"\n<i>{last_action_text}</i>\n" if last_action_text else ""

    text = (
        f"💀 <b>РУССКАЯ РУЛЕТКА: СМЕРТЕЛЬНЫЙ ПОЕДИНОК!</b>\n\n"
        f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code> | <b>Банк:</b> <code>{pot:,} ₪</code>\n"
        f"👤 <b>Дуэлянт 1:</b> Анон <code>[ID:{p1_anon}]</code>\n"
        f"👤 <b>Дуэлянт 2:</b> Анон <code>[ID:{p2_anon}]</code>\n\n"
        f"🔫 <b>Барабан:</b> {drum_vis} (Камора {cur_ch + 1}/{RR_CHAMBERS_COUNT})\n"
        f"⚠️ <b>Шанс выстрела в упор:</b> <b>{prob}%</b>\n"
        f"{action_block}\n"
        f"👉 <b>Сейчас у виска револьвер держит:</b> Анон <b>[ID:{turn_anon}]</b>\n"
        f"⏳ <b>Таймер на спуск:</b> <b>{rem_sec} сек</b> (при таймауте — авто-луз и мут)!\n\n"
        f"<i>Жми «💥 Нажать на спуск!», если хватит духу!</i>"
    )
    return text


# -----------------------------------------------------------------------------
# Keyboards
# -----------------------------------------------------------------------------

def get_rr_challenge_keyboard(game_id: str, bet: int) -> InlineKeyboardMarkup:
    """Keyboard for pending challenge."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"⚔️ Принять вызов ({bet:,} ₪)", callback_data=f"rr_accept:{game_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rr_decline:{game_id}")
        ]
    ])


def get_rr_game_keyboard(game_id: str, is_finished: bool = False) -> InlineKeyboardMarkup:
    """Keyboard during active game."""
    if is_finished:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💥 Нажать на спуск! (60с)", callback_data=f"rr_shoot:{game_id}")
        ],
        [
            InlineKeyboardButton(text="🏳️ Сдаться / Зассать", callback_data=f"rr_surrender:{game_id}")
        ]
    ])


# -----------------------------------------------------------------------------
# Public Announcement Helper
# -----------------------------------------------------------------------------

async def broadcast_game_announcement(bot, board_id: str, text: str):
    """
    Broadcasts public duel announcement to the board stream via process_new_post.
    """
    try:
        from post_processor import process_new_post
        import shared_state
        params = shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content={'type': 'text', 'text': text},
            reply_to_post=None,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        logger.error(f"Failed to broadcast Russian Roulette announcement: {e}")


# -----------------------------------------------------------------------------
# Core Game Lifecycle & Business Logic
# -----------------------------------------------------------------------------

async def create_rr_challenge(
    board_id: str,
    challenger_id: int,
    bet: int,
    target_id: Optional[int] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Creates a new pending PvP Russian Roulette challenge.
    """
    if bet < MIN_RR_BET:
        return False, f"❌ Минимальная ставка в Русскую Рулетку: <b>{MIN_RR_BET} ₪</b>.", None
    if bet > MAX_RR_BET:
        return False, f"❌ Максимальная ставка: <b>{MAX_RR_BET:,} ₪</b>.", None

    db = await get_pool()
    async with db_lock:
        bal = await get_user_global_balance(db, challenger_id)
    if bal < bet:
        return False, f"❌ Недостаточно шекелей! Ставка: <b>{bet:,} ₪</b>, на балансе: <b>{int(bal):,} ₪</b>.", None

    async with rr_lock:
        if challenger_id in user_active_rr_game:
            old_gid = user_active_rr_game[challenger_id]
            if old_gid in active_rr_games and not active_rr_games[old_gid].get("finished"):
                return False, "⚠️ У тебя уже есть активная дуэль в Русскую Рулетку!", None

        game_id = generate_game_id()
        active_rr_games[game_id] = {
            "game_id": game_id,
            "board_id": board_id,
            "challenger_id": challenger_id,
            "acceptor_id": target_id,
            "target_id": target_id,
            "bet": bet,
            "state": "pending",
            "bullet_chamber": random.randint(0, RR_CHAMBERS_COUNT - 1),
            "current_chamber": 0,
            "turn": challenger_id,
            "turn_deadline_ts": time.time() + RR_CHALLENGE_TIMEOUT_SEC,
            "created_ts": time.time(),
            "last_action_ts": time.time(),
            "finished": False,
            "outcome": None,
            "winner_id": None,
            "loser_id": None,
            "payout": 0,
            "chat_id": None,
            "msg_id": None,
            "history": []
        }
        user_active_rr_game[challenger_id] = game_id

    return True, "✅ Вызов создан!", game_id


async def accept_rr_challenge(game_id: str, acceptor_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Accepts pending challenge, locks escrow from both players, and starts the game.
    """
    async with rr_lock:
        game = active_rr_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена или была отменена.", None
        if game["state"] != "pending":
            return False, "❌ Вызов уже был принят или завершен!", None
        if game["challenger_id"] == acceptor_id:
            return False, "❌ Нельзя играть в Русскую Рулетку с самим собой, шизик.", None
        if game.get("target_id") and game["target_id"] != acceptor_id:
            return False, "❌ Этот вызов адресован другому анону!", None

        if acceptor_id in user_active_rr_game:
            old_gid = user_active_rr_game[acceptor_id]
            if old_gid in active_rr_games and not active_rr_games[old_gid].get("finished") and old_gid != game_id:
                return False, "⚠️ У тебя уже есть другая незавершенная дуэль!", None

        bet = game["bet"]
        board_id = game["board_id"]
        challenger_id = game["challenger_id"]

    # Escrow deduction
    db = await get_pool()
    async with db_lock:
        bal_c = await get_user_global_balance(db, challenger_id)
        bal_a = await get_user_global_balance(db, acceptor_id)
        if bal_c < bet:
            return False, "❌ У создателя вызова не хватает шекелей на балансе!", None
        if bal_a < bet:
            return False, f"❌ У тебя не хватает шекелей! Ставка: <b>{bet:,} ₪</b>, баланс: <b>{int(bal_a):,} ₪</b>.", None

        ok_c, _ = await deduct_user_global_balance(db, challenger_id, board_id, bet)
        ok_a, _ = await deduct_user_global_balance(db, acceptor_id, board_id, bet)
        if not ok_c or not ok_a:
            # Refund if partial failure
            if ok_c:
                await add_user_global_balance(db, challenger_id, board_id, bet)
            if ok_a:
                await add_user_global_balance(db, acceptor_id, board_id, bet)
            return False, "❌ Ошибка списания ставки. Баланс изменился.", None

        await record_user_transaction(db, challenger_id, -bet, 'rr_pvp', f'Ставка в Русской Рулетке #{game_id}')
        await record_user_transaction(db, acceptor_id, -bet, 'rr_pvp', f'Ставка в Русской Рулетке #{game_id}')

    async with rr_lock:
        game["acceptor_id"] = acceptor_id
        game["state"] = "playing"
        # 50/50 starting player
        first_player = random.choice([challenger_id, acceptor_id])
        game["turn"] = first_player
        game["turn_deadline_ts"] = time.time() + RR_TURN_TIMEOUT_SEC
        game["last_action_ts"] = time.time()
        user_active_rr_game[acceptor_id] = game_id

    return True, "✅ Дуэль началась!", game


async def decline_or_cancel_rr_challenge(game_id: str, user_id: int) -> Tuple[bool, str]:
    """
    Cancels pending challenge by creator or declines by target.
    """
    async with rr_lock:
        game = active_rr_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден."
        if game["state"] != "pending":
            return False, "❌ Нельзя отменить уже начавшуюся дуэль."

        ch_id = game["challenger_id"]
        tgt_id = game.get("target_id")

        if user_id != ch_id and (tgt_id and user_id != tgt_id):
            return False, "❌ Ты не участник этого вызова."

        game["finished"] = True
        game["state"] = "cancelled"
        active_rr_games.pop(game_id, None)
        user_active_rr_game.pop(ch_id, None)
        if tgt_id:
            user_active_rr_game.pop(tgt_id, None)

    if user_id == ch_id:
        return True, "❌ Вызов на дуэль отменен создателем."
    return True, f"❌ Вызов на дуэль отклонен Аноном [ID:{get_anon_id(user_id)}]."


async def pull_rr_trigger(game_id: str, user_id: int, bot=None) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Pulls the revolver trigger for current player on turn.
    Returns: (is_success, action_message, game_dict)
    """
    async with rr_lock:
        game = active_rr_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game["state"] != "playing" or game.get("finished"):
            return False, "❌ Дуэль уже завершена.", game
        if user_id not in (game["challenger_id"], game["acceptor_id"]):
            return False, "❌ Ты не участник этой дуэли!", game
        if user_id != game["turn"]:
            return False, "⏳ Сейчас не твой ход! Очередь соперника держать револьвер у виска.", game

        now = time.time()
        # Check turn timeout
        if now > game["turn_deadline_ts"]:
            opponent = game["acceptor_id"] if user_id == game["challenger_id"] else game["challenger_id"]
            return await _finish_rr_game(game_id, winner_id=opponent, loser_id=user_id, reason="timeout", bot=bot)

        cur_chamber = game["current_chamber"]
        bullet_chamber = game["bullet_chamber"]
        user_anon = get_anon_id(user_id)
        opponent_id = game["acceptor_id"] if user_id == game["challenger_id"] else game["challenger_id"]

        # LIVE BULLET DETONATION
        if cur_chamber == bullet_chamber:
            return await _finish_rr_game(game_id, winner_id=opponent_id, loser_id=user_id, reason="shot", bot=bot)

        # EMPTY CHAMBER - SURVIVED
        game["history"].append({"user_id": user_id, "chamber": cur_chamber, "outcome": "click"})
        game["current_chamber"] += 1
        game["turn"] = opponent_id
        game["turn_deadline_ts"] = now + RR_TURN_TIMEOUT_SEC
        game["last_action_ts"] = now

        click_msg = f"💨 <b>ЩЁЛК!</b> Пустая камора ({cur_chamber + 1}/6)! Анон [ID:{user_anon}] вытирает холодный пот со лба."
        return True, click_msg, game


async def surrender_rr_game(game_id: str, user_id: int, bot=None) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Voluntarily surrenders the game. Surrendering player loses and gets muted for 30m.
    """
    async with rr_lock:
        game = active_rr_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game["state"] != "playing" or game.get("finished"):
            return False, "❌ Дуэль уже завершена.", game
        if user_id not in (game["challenger_id"], game["acceptor_id"]):
            return False, "❌ Ты не участник этой дуэли!", game

        opponent_id = game["acceptor_id"] if user_id == game["challenger_id"] else game["challenger_id"]
        return await _finish_rr_game(game_id, winner_id=opponent_id, loser_id=user_id, reason="surrender", bot=bot)


async def _finish_rr_game(
    game_id: str,
    winner_id: int,
    loser_id: int,
    reason: str,
    bot=None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Finalizes the game:
    - Sets payout & rake to Abu's Fund.
    - Credits winner balance.
    - Applies 30-MINUTE MUTE (1800s) to loser in DB & RAM.
    - Checks achievements.
    - Broadcasts public verdict to chat.
    """
    game = active_rr_games[game_id]
    game["finished"] = True
    game["state"] = "finished"
    game["outcome"] = reason
    game["winner_id"] = winner_id
    game["loser_id"] = loser_id

    bet = game["bet"]
    pot = bet * 2
    board_id = game["board_id"]
    p1 = game["challenger_id"]
    p2 = game["acceptor_id"]

    # Clear active user mappings
    user_active_rr_game.pop(p1, None)
    if p2:
        user_active_rr_game.pop(p2, None)

    rake = max(5, int(pot * RR_RAKE_PERCENT))
    win_payout = pot - rake
    game["payout"] = win_payout

    win_anon = get_anon_id(winner_id)
    lose_anon = get_anon_id(loser_id)

    db = await get_pool()
    async with db_lock:
        # Payout to winner
        await add_user_global_balance(db, winner_id, board_id, win_payout)
        await add_to_abu_fund(db, rake)
        await record_user_transaction(db, winner_id, win_payout, 'rr_pvp', f'Победа в Русской Рулетке #{game_id} против [{lose_anon}]')

        # Check PvP achievement for winner
        try:
            from common.bot_helpers import _get_user_active_items
            from achievements_engine import check_and_unlock_achievement
            w_items = await _get_user_active_items(db, winner_id, board_id)
            unlocked, ach_info = check_and_unlock_achievement(w_items, "ach_duel_win")
            if unlocked and ach_info:
                await add_user_global_balance(db, winner_id, board_id, ach_info["reward_cash"])
                await record_user_transaction(db, winner_id, ach_info["reward_cash"], 'drop', f'Достижение: {ach_info["name"]}')
                await db.execute(
                    "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(w_items), winner_id, board_id)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error checking achievement in Russian Roulette: {e}")

    # Apply 30-MINUTE MUTE (1800s) to loser
    try:
        await apply_regular_mute(loser_id, board_id, duration_seconds=RR_MUTE_DURATION_SEC)
    except Exception as e:
        logger.error(f"Error applying regular mute in DB for user {loser_id}: {e}")

    try:
        import shared_state
        async with shared_state.storage_lock:
            if board_id in shared_state.board_data and 'mutes' in shared_state.board_data[board_id]:
                shared_state.board_data[board_id]['mutes'][loser_id] = datetime.now(timezone.utc) + timedelta(seconds=RR_MUTE_DURATION_SEC)
    except Exception as e:
        logger.error(f"Error updating in-memory mute for user {loser_id}: {e}")

    # Build chat broadcast text
    cur_ch = game["current_chamber"]
    if reason == "shot":
        announcement = (
            f"💥 <b>РУССКАЯ РУЛЕТКА: СМЕРТЕЛЬНЫЙ ВЫСТРЕЛ В ЛОБ!</b>\n\n"
            f"💀 Анон <code>[ID:{lose_anon}]</code> спустил курок на <b>{cur_ch + 1}-й каморе</b>... <b>БАХ!</b> Мозги забрызгали тред!\n"
            f"👑 <b>Победитель:</b> Анон <code>[ID:{win_anon}]</code> забирает банк <code>+{win_payout:,} ₪</code>!\n"
            f"🔇 Неудачник отправлен чистить парашу (<b>МУТ НА 30 МИНУТ</b>)!"
        )
    elif reason == "timeout":
        announcement = (
            f"⏱️ <b>РУССКАЯ РУЛЕТКА: ЗАССАЛ И ПОТЕРЯЛ ВСЁ!</b>\n\n"
            f"🐔 Анон <code>[ID:{lose_anon}]</code> дрожал от страха и не нажал на спуск за <b>60 секунд</b>!\n"
            f"👑 <b>Победитель:</b> Анон <code>[ID:{win_anon}]</code> забирает банк <code>+{win_payout:,} ₪</code>!\n"
            f"🔇 Трус отправлен в <b>МУТ НА 30 МИНУТ</b> за срыв дуэли!"
        )
    else:  # surrender
        announcement = (
            f"🏳️ <b>РУССКАЯ РУЛЕТКА: КАПИТУЛЯЦИЯ В СЛЕЗАХ!</b>\n\n"
            f"😭 Анон <code>[ID:{lose_anon}]</code> выронил револьвер и сдался без боя!\n"
            f"👑 <b>Победитель:</b> Анон <code>[ID:{win_anon}]</code> забирает банк <code>+{win_payout:,} ₪</code>!\n"
            f"🔇 Сдавшийся отправлен в <b>МУТ НА 30 МИНУТ</b>!"
        )

    if bot:
        asyncio.create_task(broadcast_game_announcement(bot, board_id, announcement))

    return True, "Дуэль завершена.", game


# -----------------------------------------------------------------------------
# Background Watchdog for Auto-Timeouts
# -----------------------------------------------------------------------------

async def rr_watchdog_step(bot=None):
    """
    Single iteration step of background watchdog checking expired turns,
    updating countdowns dynamically, and cleaning expired challenges.
    """
    now = time.time()
    expired_games = []
    expired_pending = []
    live_tick_games = []

    async with rr_lock:
        for gid, game in list(active_rr_games.items()):
            if game.get("finished"):
                continue
            if game["state"] == "playing":
                if now > game["turn_deadline_ts"]:
                    expired_games.append(gid)
                else:
                    # Live countdown auto-update every 10 seconds
                    last_tick = game.get("last_tick_ts", game["turn_deadline_ts"] - RR_TURN_TIMEOUT_SEC)
                    if now - last_tick >= 10.0:
                        game["last_tick_ts"] = now
                        live_tick_games.append(gid)
            elif game["state"] == "pending" and now > (game["created_ts"] + RR_CHALLENGE_TIMEOUT_SEC):
                # Expire unaccepted challenge
                game["finished"] = True
                game["state"] = "expired"
                ch_id = game["challenger_id"]
                user_active_rr_game.pop(ch_id, None)
                expired_pending.append(gid)

    # 1. Update live countdown timer in playing games
    for gid in live_tick_games:
        game = active_rr_games.get(gid)
        if not game or game.get("finished"):
            continue
        if bot and game.get("chat_id") and game.get("msg_id"):
            try:
                updated_text = format_rr_game_message(game)
                await bot.edit_message_text(
                    chat_id=game["chat_id"],
                    message_id=game["msg_id"],
                    text=updated_text,
                    reply_markup=get_rr_game_keyboard(gid),
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # 2. Finish expired turn games (timeout forfeit)
    for gid in expired_games:
        game = active_rr_games.get(gid)
        if not game or game.get("finished"):
            continue
        loser_id = game["turn"]
        winner_id = game["acceptor_id"] if loser_id == game["challenger_id"] else game["challenger_id"]
        _, _, fin_game = await _finish_rr_game(gid, winner_id, loser_id, reason="timeout", bot=bot)

        if bot and game.get("chat_id") and game.get("msg_id"):
            try:
                updated_text = format_rr_game_message(fin_game)
                await bot.edit_message_text(
                    chat_id=game["chat_id"],
                    message_id=game["msg_id"],
                    text=updated_text,
                    reply_markup=get_rr_game_keyboard(gid, is_finished=True),
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # 3. Clean and edit expired pending challenges
    for gid in expired_pending:
        game = active_rr_games.get(gid)
        if not game:
            continue
        if bot and game.get("chat_id") and game.get("msg_id"):
            try:
                await bot.edit_message_text(
                    chat_id=game["chat_id"],
                    message_id=game["msg_id"],
                    text=(
                        "⏳ <b>ВЫЗОВ В РУССКУЮ РУЛЕТКУ ИСТЕК!</b>\n\n"
                        "Ни один анон не принял вызов на дуэль за 2 минуты.\n"
                        "Вызов аннулирован, ставка не списана."
                    ),
                    reply_markup=None,
                    parse_mode="HTML"
                )
            except Exception:
                pass


async def start_rr_watchdog_loop(bot):
    """
    Continuous background watchdog loop for Russian Roulette timeouts.
    """
    logger.info("Russian Roulette PvP watchdog loop started.")
    while True:
        try:
            await rr_watchdog_step(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in rr_watchdog_loop: {e}")
        await asyncio.sleep(2.5)


# -----------------------------------------------------------------------------
# AIOGRAM ROUTER & HANDLERS
# -----------------------------------------------------------------------------

async def _resolve_reply_author(message: types.Message) -> Optional[int]:
    """Helper to extract author user_id from replied message."""
    if not message.reply_to_message:
        return None
    chat_id = message.reply_to_message.chat.id
    msg_id = message.reply_to_message.message_id

    try:
        import shared_state
        async with shared_state.storage_lock:
            p_num = shared_state.message_to_post.get((chat_id, msg_id))
            if p_num and p_num in shared_state.messages_storage:
                return shared_state.messages_storage[p_num].get("author_id")
    except Exception:
        pass

    try:
        from common.database import get_post_info_by_copy
        info = await get_post_info_by_copy(chat_id, msg_id)
        if info:
            return info[1]
    except Exception:
        pass

    if message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot:
        return message.reply_to_message.from_user.id

    return None


@rr_router.message(Command("duel_rr", "rr", "roulette_pvp", "pvp_roulette", "рулетка_пвп", "дуэль_рулетка", ignore_case=True, ignore_mention=True))
async def cmd_russian_roulette(message: types.Message, board_id: str | None = None, stream: str = 'ru'):
    """
    Handles /rr command:
    - /rr <amount> : Creates open or targeted challenge
    - /rr accept : Accepts active challenge
    - /rr decline : Declines/cancels active challenge
    - /rr help : Shows help rules
    """
    if not board_id:
        board_id = "b"

    user_id = message.from_user.id
    args = (message.text or message.caption or "").split()[1:]

    if not args:
        help_text = (
            "💀 <b>PvP РУССКАЯ РУЛЕТКА (6 КАМОР, 1 ПАТРОН)</b>\n\n"
            "Смертельная дуэль на двоих с поочередным спуском курка и жестким таймером 60 секунд.\n\n"
            "📌 <b>Команды:</b>\n"
            "• <code>/rr 500</code> — создать открытый вызов на 500 ₪\n"
            "• <code>/rr 1000</code> (в ответ на пост) — вызвать конкретного анона на дуэль\n"
            "• <code>/rr accept</code> — принять активный вызов на борде\n"
            "• <code>/rr decline</code> — отклонить или отменить вызов\n\n"
            "⚖️ <b>Правила:</b>\n"
            "• Револьвер: <b>6 камор, ровно 1 боевой патрон</b>.\n"
            "• Поочередный спуск курка с таймером <b>60 секунд на ход</b>.\n"
            "• 💥 <b>Проигравший:</b> теряет ставку и получает <b>МУТ НА 30 МИНУТ</b>!\n"
            "• 👑 <b>Победитель:</b> забирает весь банк!\n"
            "• ⏱️ Если анон зассал и не нажал на спуск за 60с — авто-луз и мут!"
        )
        await message.answer(help_text, parse_mode="HTML")
        return

    subcmd = args[0].lower()

    # ACCEPT SHORTCUT
    if subcmd in ("accept", "принять", "+", "ок", "ok"):
        found_gid = None
        async with rr_lock:
            for gid, g in list(active_rr_games.items()):
                if g["board_id"] == board_id and g["state"] == "pending":
                    if g.get("target_id") is None or g["target_id"] == user_id:
                        found_gid = gid
                        break

        if not found_gid:
            await message.answer("⚔️ Нет активных вызовов в Русскую Рулетку для тебя на этой борде.")
            return

        ok, err_text, game = await accept_rr_challenge(found_gid, user_id)
        if not ok:
            await message.answer(err_text, parse_mode="HTML")
            return

        game_text = format_rr_game_message(game)
        kb = get_rr_game_keyboard(found_gid)
        sent = await message.answer(game_text, reply_markup=kb, parse_mode="HTML")
        async with rr_lock:
            game["chat_id"] = sent.chat.id
            game["msg_id"] = sent.message_id
        return

    # DECLINE / CANCEL SHORTCUT
    if subcmd in ("decline", "отклонить", "cancel", "отмена", "отменить", "-"):
        found_gid = None
        async with rr_lock:
            for gid, g in list(active_rr_games.items()):
                if g["board_id"] == board_id and g["state"] == "pending":
                    if g["challenger_id"] == user_id or g.get("target_id") == user_id:
                        found_gid = gid
                        break

        if not found_gid:
            await message.answer("⚔️ У тебя нет активных вызовов для отмены/отклонения.")
            return

        ok, res_text = await decline_or_cancel_rr_challenge(found_gid, user_id)
        await message.answer(res_text, parse_mode="HTML")
        return

    # CREATE CHALLENGE
    try:
        bet = int(args[0])
    except ValueError:
        await message.answer("❌ Неверная сумма ставки. Пример: <code>/rr 500</code>", parse_mode="HTML")
        return

    target_id = await _resolve_reply_author(message)
    if target_id == user_id:
        target_id = None

    ok, err_text, game_id = await create_rr_challenge(board_id, user_id, bet, target_id=target_id)
    if not ok:
        await message.answer(err_text, parse_mode="HTML")
        return

    game = active_rr_games[game_id]
    card_text = format_rr_challenge_message(game)
    kb = get_rr_challenge_keyboard(game_id, bet)

    sent = await message.answer(card_text, reply_markup=kb, parse_mode="HTML")
    async with rr_lock:
        game["chat_id"] = sent.chat.id
        game["msg_id"] = sent.message_id


# -----------------------------------------------------------------------------
# CALLBACK QUERY HANDLERS
# -----------------------------------------------------------------------------

@rr_router.callback_query(F.data.startswith("rr_accept:"))
async def cb_rr_accept(callback: types.CallbackQuery, board_id: str | None = None):
    """Callback when a player accepts the Russian Roulette challenge."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    game_id = parts[1]
    user_id = callback.from_user.id

    ok, msg, game = await accept_rr_challenge(game_id, user_id)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    await callback.answer("⚔️ Дуэль принята! Барабан заряжен.")
    game_text = format_rr_game_message(game)
    kb = get_rr_game_keyboard(game_id)

    try:
        await callback.message.edit_text(game_text, reply_markup=kb, parse_mode="HTML")
        async with rr_lock:
            game["chat_id"] = callback.message.chat.id
            game["msg_id"] = callback.message.message_id
    except TelegramBadRequest:
        pass


@rr_router.callback_query(F.data.startswith("rr_decline:"))
async def cb_rr_decline(callback: types.CallbackQuery):
    """Callback when challenge is declined or cancelled."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    game_id = parts[1]
    user_id = callback.from_user.id

    ok, res_text = await decline_or_cancel_rr_challenge(game_id, user_id)
    if not ok:
        await callback.answer(res_text, show_alert=True)
        return

    await callback.answer("Вызов отменен")
    try:
        await callback.message.edit_text(f"⚔️ <b>{res_text}</b>", parse_mode="HTML", reply_markup=None)
    except TelegramBadRequest:
        pass


@rr_router.callback_query(F.data.startswith("rr_shoot:"))
async def cb_rr_shoot(callback: types.CallbackQuery):
    """Callback when player pulls the trigger."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    game_id = parts[1]
    user_id = callback.from_user.id

    ok, action_text, game = await pull_rr_trigger(game_id, user_id, bot=callback.bot)
    if not ok:
        await callback.answer(action_text, show_alert=True)
        return

    is_finished = game.get("finished", False)
    if is_finished:
        await callback.answer("💥 ВЫСТРЕЛ!", show_alert=True)
    else:
        await callback.answer("💨 ЩЁЛК! Пустая камора!")

    updated_text = format_rr_game_message(game, last_action_text=action_text)
    kb = get_rr_game_keyboard(game_id, is_finished=is_finished)

    try:
        await callback.message.edit_text(updated_text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass


@rr_router.callback_query(F.data.startswith("rr_surrender:"))
async def cb_rr_surrender(callback: types.CallbackQuery):
    """Callback when player voluntarily surrenders."""
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    game_id = parts[1]
    user_id = callback.from_user.id

    ok, res_text, game = await surrender_rr_game(game_id, user_id, bot=callback.bot)
    if not ok:
        await callback.answer(res_text, show_alert=True)
        return

    await callback.answer("🏳️ Ты сдался и получаешь мут на 30 минут!", show_alert=True)
    updated_text = format_rr_game_message(game)
    kb = get_rr_game_keyboard(game_id, is_finished=True)

    try:
        await callback.message.edit_text(updated_text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass

cmd_duel_rr = cmd_russian_roulette

