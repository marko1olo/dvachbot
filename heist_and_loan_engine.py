# -*- coding: utf-8 -*-
"""
heist_and_loan_engine.py — Heist Event, Dirty Money Laundering & Loan Shark Engine for DvachBot.
=============================================================================================
Features:
1. Money Laundering (Теневая Прачечная Абу):
   - Commands: /launder, /отмыть, /стирка
   - Converts 'dirty_balance' from active_items to clean global balance (70%).
   - Flat 30% laundering fee burned directly to Abu Yacht Fund via add_to_abu_fund.
   - 2ch authentic responses.

2. Bank Armored Truck Heist (Налёт на инкассаторский броневик Абу):
   - Commands: /heist, /налет, /налёт, /ограбление
   - 45-second collaborative lobby with inline buttons [🦹 Вступить в банду (X/4)].
   - Requires 2 to 4 participants (free from isolation and active mutes).
   - Combat resolution math:
     * Base win chance: 45%.
     * Gear bonus: +5% per weapon/armor up to max 75%.
     * Win outcome: Safe blown open! 400,000 to 1,000,000 ₪ split in dirty_balance + 2 wanted stars + 10,000 ₪ bounty.
     * Lose outcome: Heavy machine gun "Корд" ambush! 60-minute mute for all crew + 15% wallet balance confiscated to Abu fund.

3. Loan Shark / Microloans («Быстрошекель Пахома»):
   - Commands: /loan (/заем, /займ, /долг) and /paydebt (/вернуть).
   - Eligibility: clean balance <= 500 ₪ and no active overdue loan.
   - Borrow limit: 500 ₪ to 5,000 ₪ with 20% flat interest (24-hour loan_due_at timer).
   - Repayment: clears debt, increases credit rating.
   - Overdue Default Enforcement: check_and_apply_loan_penalty marks is_defaulter = True,
     garnishes 75% of /work earnings, and triggers public collector threats from Пахом.
"""

import asyncio
import inspect
import json
import logging
import math
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from common.criminal_phrases import (
    HEIST_WIN_PHRASES,
    HEIST_LOSE_PHRASES,
    LOAN_PAKHOM_COLLECTOR_PHRASES,
    LAUNDER_WASHER_PHRASES,
)

logger = logging.getLogger("heist_and_loan_engine")

heist_loan_router = Router(name="heist_loan_router")
router = heist_loan_router  # Alias for standard router inclusion


# -----------------------------------------------------------------------------
# Active Items & Database Persistence Helpers
# -----------------------------------------------------------------------------

async def get_user_active_items(db, user_id: int, board_id: str = "b") -> Dict[str, Any]:
    """
    Safely retrieves and parses user active_items dictionary from database.
    """
    if db is None:
        return {}
    try:
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
            (user_id, board_id)
        ) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                if isinstance(row[0], dict):
                    return row[0]
                return json.loads(row[0])
            # Fallback across any board
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? LIMIT 1",
                (user_id,)
            ) as cur2:
                row2 = await cur2.fetchone()
                if row2 and row2[0]:
                    if isinstance(row2[0], dict):
                        return row2[0]
                    return json.loads(row2[0])
    except Exception as e:
        logger.warning(f"Error loading active_items for user {user_id}: {e}")
    return {}


async def save_user_active_items(db, user_id: int, items_or_board_id: Any, board_id_or_items: Any = None) -> bool:
    """
    Persists user active_items dictionary to Users table.
    Supports both (db, user_id, active_items, board_id="b") and (db, user_id, board_id, active_items).
    """
    if db is None:
        return False
    if isinstance(items_or_board_id, dict) and (board_id_or_items is None or isinstance(board_id_or_items, str)):
        active_items = items_or_board_id
        board_id = board_id_or_items or "b"
    elif isinstance(items_or_board_id, str) and isinstance(board_id_or_items, dict):
        board_id = items_or_board_id
        active_items = board_id_or_items
    else:
        active_items = items_or_board_id if isinstance(items_or_board_id, dict) else (board_id_or_items if isinstance(board_id_or_items, dict) else {})
        board_id = str(items_or_board_id) if isinstance(items_or_board_id, str) else (str(board_id_or_items) if board_id_or_items else "b")

    try:
        raw_json = json.dumps(active_items, ensure_ascii=False)
        await db.execute("""
            INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)
            ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items
        """, (user_id, board_id, raw_json))
        if hasattr(db, "commit"):
            await db.commit()
        return True
    except Exception as e:
        logger.warning(f"Error saving active_items for user {user_id}: {e}")
        return False


async def check_participant_muted(db, user_id: int, board_id: str = "b") -> bool:
    """
    Verifies if a user is currently muted in memory or database.
    """
    try:
        from common.bot_helpers import check_user_is_muted
        return await check_user_is_muted(db, user_id, board_id)
    except Exception:
        pass
    if db:
        try:
            now_ts = time.time()
            async with db.execute(
                "SELECT 1 FROM Mutes WHERE user_id = ? AND (board_id = ? OR board_id = 'ALL') AND expires_at > ? LIMIT 1",
                (user_id, board_id, now_ts)
            ) as cur:
                return await cur.fetchone() is not None
        except Exception:
            pass
    return False


async def check_participant_isolated(db, user_id: int, board_id: str = "b") -> bool:
    """
    Verifies if a user is currently in self-isolation mode.
    """
    try:
        from shared_state import board_data
        if board_data.get(board_id, {}).get("user_settings", {}).get(user_id, {}).get("is_isolated", False):
            return True
    except Exception:
        pass
    if db:
        try:
            async with db.execute(
                "SELECT is_isolated FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, board_id)
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return bool(row[0])
        except Exception:
            pass
    return False


async def apply_heist_loss_mute(db, user_id: int, board_id: str = "b", duration_seconds: int = 3600):
    """
    Mutes user for duration_seconds upon losing heist against Abu's guards.
    """
    try:
        from common.database import apply_regular_mute
        await apply_regular_mute(user_id, board_id, duration_seconds, reason="Неудачный налёт на инкассаторов Абу")
        return
    except Exception:
        pass
    if db:
        try:
            expires_at = time.time() + duration_seconds
            await db.execute(
                "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at, reason) VALUES (?, ?, 'mute', ?, ?)",
                (user_id, board_id, expires_at, "Неудачный налёт на инкассаторов Абу")
            )
        except Exception as e:
            logger.warning(f"Failed direct Mutes insert for user {user_id}: {e}")


def _is_media_message(message: Any) -> bool:
    if not message:
        return False
    photo = getattr(message, "photo", None)
    if photo is not None and (not (type(photo).__name__ == "MagicMock") or isinstance(photo, (list, tuple))):
        return bool(photo)
    video = getattr(message, "video", None)
    if video is not None and (not (type(video).__name__ == "MagicMock")):
        return bool(video)
    caption = getattr(message, "caption", None)
    if caption is not None and (not (type(caption).__name__ == "MagicMock") or isinstance(caption, str)):
        return bool(caption)
    return False


async def _safe_edit_or_replace_message(
    message: Optional[Message],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    """
    Safely edits or replaces a message whether it is a photo/media banner or plain text message.
    Handles media (photo/banner) by editing caption or deleting and sending fresh text,
    and plain text messages by calling edit_text with fallback to delete and answer.
    """
    if not message:
        return False
    is_media = _is_media_message(message)
    if is_media:
        if len(text) <= 1024:
            try:
                if hasattr(message, "edit_caption"):
                    res = message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
                    if inspect.isawaitable(res):
                        await res
                    return True
            except TelegramBadRequest as ex:
                if "message is not modified" in str(ex).lower():
                    return False
            except Exception:
                pass
        try:
            if hasattr(message, "delete"):
                res = message.delete()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass
        if hasattr(message, "answer"):
            res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
            if inspect.isawaitable(res):
                await res
        return True
    else:
        try:
            if hasattr(message, "edit_text"):
                res = message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
                return True
        except TelegramBadRequest as ex:
            if "message is not modified" in str(ex).lower():
                return False
            try:
                if hasattr(message, "delete"):
                    res = message.delete()
                    if inspect.isawaitable(res):
                        await res
            except Exception:
                pass
            if hasattr(message, "answer"):
                res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
            return True
        except Exception:
            try:
                if hasattr(message, "delete"):
                    res = message.delete()
                    if inspect.isawaitable(res):
                        await res
            except Exception:
                pass
            if hasattr(message, "answer"):
                res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
            return True


# -----------------------------------------------------------------------------
# SYSTEM 1: MONEY LAUNDERING (Теневая Прачечная Абу)
# -----------------------------------------------------------------------------


_USER_FINANCIAL_LOCKS: Dict[int, asyncio.Lock] = {}
_FINANCIAL_LOCKS_GUARD = asyncio.Lock()

async def get_user_financial_lock(user_id: int) -> asyncio.Lock:
    """Returns or creates a per-user asyncio.Lock for financial operations (loans/laundering)."""
    async with _FINANCIAL_LOCKS_GUARD:
        if user_id not in _USER_FINANCIAL_LOCKS:
            _USER_FINANCIAL_LOCKS[user_id] = asyncio.Lock()
        return _USER_FINANCIAL_LOCKS[user_id]


async def process_money_laundering(
    db,
    user_id: int,
    amount_spec: Union[str, int, float],
    board_id: str = "b",
    active_items: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes money laundering logic:
    - 30% laundering fee burned to Abu Yacht Fund
    - 70% converted to clean shekels into global balance
    - Deducts from dirty_balance in active_items
    """
    lock = await get_user_financial_lock(user_id)
    async with lock:
        if active_items is None:
            active_items = await get_user_active_items(db, user_id, board_id)

        dirty_balance = float(active_items.get("dirty_balance", 0.0))
        if dirty_balance <= 0:
            return (
                False,
                "🧺 <b>ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ:</b>\n"
                "У тебя нет меченых шекелей, нищеброд! Сначала иди грабь инкассаторов через <code>/heist</code>, "
                "потом приходи стирать бабло!",
                {"dirty_balance": 0.0, "clean": 0, "fee": 0}
            )

        # Parse requested amount
        str_spec = str(amount_spec).strip().lower()
        if str_spec in ("all", "все", "всё", ""):
            amount_to_launder = int(dirty_balance)
        else:
            try:
                parsed = int(float(str_spec))
                if parsed <= 0:
                    raise ValueError("Positive amount required")
                amount_to_launder = parsed
            except ValueError:
                return (
                    False,
                    "⚠️ Укажи корректную сумму для отмыва! Например: <code>/launder 50000</code> или <code>/launder all</code>.",
                    {"dirty_balance": dirty_balance, "clean": 0, "fee": 0}
                )

        if amount_to_launder > dirty_balance:
            return (
                False,
                f"❌ У тебя нет столько меченых шекелей! Твой грязный баланс: <b>{int(dirty_balance):,} ₪</b>.",
                {"dirty_balance": dirty_balance, "clean": 0, "fee": 0}
            )

        # 30% flat fee, 70% clean
        fee = int(round(amount_to_launder * 0.30))
        clean = int(amount_to_launder - fee)

        # Update dirty balance
        remaining_dirty = max(0.0, dirty_balance - amount_to_launder)
        active_items["dirty_balance"] = remaining_dirty

        # Persist to DB
        if db is not None:
            await save_user_active_items(db, user_id, active_items, board_id)
            try:
                from common.database import add_user_global_balance, add_to_abu_fund, record_user_transaction
                await add_user_global_balance(db, user_id, board_id, float(clean))
                await add_to_abu_fund(
                    db,
                    float(fee),
                    donor_id=user_id,
                    reason="Комиссия теневой прачечной Абу за отмыв бабла"
                )
                await record_user_transaction(
                    db,
                    user_id,
                    float(clean),
                    "laundering",
                    f"Отмыто {clean:,} ₪ через прачечную Абу (комиссия: {fee:,} ₪)"
                )
            except Exception as e:
                logger.error(f"Error in DB financial operations during laundering: {e}")

        washer_flavor = random.choice(LAUNDER_WASHER_PHRASES) if LAUNDER_WASHER_PHRASES else (
            "🧺 Стиралка 'Малютка' прокрутила твои меченые шекели с белизной! 30% Абу отжал на яхту, остальное чистое!"
        )

        confirm_text = (
            "🧺 <b>ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ:</b>\n"
            f"{washer_flavor}\n\n"
            f"30% ({fee:,} ₪) отжато на яхту, {clean:,} ₪ легли в карман чистыми белыми купюрами!\n"
            f"💰 Остаток меченых шекелей: <b>{int(remaining_dirty):,} ₪</b>"
        )

        result_data = {
            "amount_laundered": amount_to_launder,
            "clean": clean,
            "fee": fee,
            "remaining_dirty": remaining_dirty,
            "washer_flavor": washer_flavor,
        }
        return (True, confirm_text, result_data)


def build_launder_keyboard() -> InlineKeyboardMarkup:
    """
    Builds interactive inline keyboard for money laundering:
    [🧺 Отмыть всё (30% налог)] (launder_do_all)
    [🧺 Отмыть 50%] (launder_do_half)
    [⬅️ Назад в Банк (/bank)] (bank_main_hub)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧺 Отмыть всё (30% налог)", callback_data="launder_do_all")],
        [InlineKeyboardButton(text="🧺 Отмыть 50%", callback_data="launder_do_half")],
        [
            InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
            InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
        ],
    ])


def format_launder_menu_text(dirty_balance: float) -> str:
    """
    Renders card with dirty balance, 30% tax explanation, and estimated clean yield.
    """
    int_dirty = int(dirty_balance)
    clean_all = int(round(int_dirty * 0.70))
    tax_all = int(round(int_dirty * 0.30))
    half_dirty = int_dirty // 2
    clean_half = int(round(half_dirty * 0.70))
    tax_half = int(round(half_dirty * 0.30))

    return (
        "🧺 <b>ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ</b>\n\n"
        f"💰 Твой меченый баланс: <b>{int_dirty:,} ₪</b>\n\n"
        "🚿 <b>Условия отмыва:</b>\n"
        "• <b>30% налог</b> взимается Абу на обслуживание яхты в Дубае.\n"
        "• <b>70% шекелей</b> зачисляются на чистый глобальный баланс.\n\n"
        "📊 <b>Расчёт при отмыве:</b>\n"
        f"• Всё ({int_dirty:,} ₪): чистыми <b>+{clean_all:,} ₪</b> (налог: {tax_all:,} ₪)\n"
        f"• Половина ({half_dirty:,} ₪): чистыми <b>+{clean_half:,} ₪</b> (налог: {tax_half:,} ₪)\n\n"
        "<i>Нажми кнопку ниже для мгновенной стирки купюр:</i>"
    )


@heist_loan_router.message(Command("launder", "отмыть", "стирка"))
async def cmd_money_laundering(message: Message):
    """
    Handler for /launder, /отмыть, /стирка commands.
    If invoked without arguments: shows interactive laundering card with inline buttons.
    If invoked with arguments (e.g. /launder 50000 or /launder all): processes immediately.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    text_parts = message.text.strip().split() if message.text else []

    try:
        from common.db_pool import get_pool
        db = await get_pool()
    except Exception:
        db = None

    board_id = "b"

    # If no arguments provided -> Interactive laundering menu
    if len(text_parts) < 2:
        active_items = await get_user_active_items(db, user_id, board_id)
        dirty_balance = float(active_items.get("dirty_balance", 0.0))
        if dirty_balance <= 0:
            await message.reply(
                "🧺 <b>ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ:</b>\n"
                "У тебя нет меченых шекелей, нищеброд! Сначала иди грабь инкассаторов через <code>/heist</code>, "
                "потом приходи стирать бабло!",
                parse_mode="HTML"
            )
            return

        card_text = format_launder_menu_text(dirty_balance)
        kb = build_launder_keyboard()
        await message.reply(card_text, reply_markup=kb, parse_mode="HTML")
        return

    amount_spec = text_parts[1]
    success, reply_text, _ = await process_money_laundering(db, user_id, amount_spec, board_id=board_id)
    await message.reply(reply_text, parse_mode="HTML")


@heist_loan_router.callback_query(F.data == "launder_hub")
async def cb_launder_hub(callback: CallbackQuery):
    """
    Callback for opening/refreshing the laundering menu card.
    If user has 0 dirty balance, shows an informative guide on how to get dirty money.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        active_items = await get_user_active_items(db, user_id, "b")
        dirty_balance = float(active_items.get("dirty_balance", 0.0))
        from common.bot_helpers import render_menu_transition

        if dirty_balance <= 0:
            empty_text = (
                "🧺 <b>ТЕНЕВАЯ ПРАЧЕЧНАЯ АБУ</b>\n\n"
                "💰 Твой меченый баланс: <b>0 ₪</b>\n\n"
                "<i>У тебя сейчас нет меченых купюр со спецкраской. Чтобы получить куш:\n"
                "• Устраивай налёты на инкассаторов через <code>/heist</code>.\n"
                "• После успешного дела возвращайся сюда стирать бабло (30% налог Абу, 70% на чистый счёт).</i>"
            )
            empty_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚨 Налёт на инкассаторов (/heist)", callback_data="heist_hub")],
                [InlineKeyboardButton(text="💼 На биржу труда (/work)", callback_data="work_hub")],
                [
                    InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
                    InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
                ],
            ])
            await render_menu_transition(callback, empty_text, empty_kb, prefer_banner=False)
            return

        card_text = format_launder_menu_text(dirty_balance)
        kb = build_launder_keyboard()
        await render_menu_transition(callback, card_text, kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data == "heist_hub")
async def cb_heist_hub(callback: CallbackQuery):
    """Handles [🚨 Налёт на инкассаторов (/heist)] navigation button from launder menu."""
    from common.bot_helpers import safe_callback_answer
    try:
        if callback.message:
            fake_msg = callback.message
            if callback.from_user:
                from common.bot_helpers import SafeMessageProxy
                fake_msg = SafeMessageProxy(callback.message, callback.from_user, bot=callback.bot)
            await cmd_start_heist(fake_msg)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data == "launder_do_all")
async def cb_launder_do_all(callback: CallbackQuery):
    """
    Handles [🧺 Отмыть всё (30% налог)] callback.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        success, reply_text, data = await process_money_laundering(db, user_id, "all", board_id="b")
        if success:
            await safe_callback_answer(callback, f"🧺 Отмыто {data['amount_laundered']:,} ₪!")
        else:
            await safe_callback_answer(callback, "Ошибка отмыва!")

        result_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Погасить долг (/paydebt)", callback_data="loan_paydebt_full"),
                InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
            ],
            [
                InlineKeyboardButton(text="💼 На биржу труда", callback_data="work_hub"),
                InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
            ]
        ])
        from common.bot_helpers import render_menu_transition
        await render_menu_transition(callback, reply_text, result_kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data == "launder_do_half")
async def cb_launder_do_half(callback: CallbackQuery):
    """
    Handles [🧺 Отмыть 50%] callback.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        active_items = await get_user_active_items(db, user_id, "b")
        dirty_balance = float(active_items.get("dirty_balance", 0.0))
        half_amount = int(dirty_balance // 2)
        if half_amount <= 0 and dirty_balance > 0:
            half_amount = int(dirty_balance)

        success, reply_text, data = await process_money_laundering(db, user_id, half_amount, board_id="b", active_items=active_items)
        if success:
            await safe_callback_answer(callback, f"🧺 Отмыто {data['amount_laundered']:,} ₪ (50%)!")
        else:
            await safe_callback_answer(callback, "Ошибка отмыва!")

        result_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🪙 Взять новый займ", callback_data="loan_hub"),
                InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
            ],
            [
                InlineKeyboardButton(text="💼 На биржу труда", callback_data="work_hub"),
                InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
            ]
        ])
        from common.bot_helpers import render_menu_transition
        await render_menu_transition(callback, reply_text, result_kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


# -----------------------------------------------------------------------------
# SYSTEM 2: BANK ARMORED TRUCK HEIST (Налёт на инкассаторов)
# -----------------------------------------------------------------------------

def count_user_combat_gear(active_items: Dict[str, Any]) -> int:
    """
    Counts combat weapons and armor in participant's active_items.
    Each item gives +5% win chance to the heist crew.
    """
    if not isinstance(active_items, dict):
        return 0

    count = 0
    # 1. Explicit combat_gear_count
    if isinstance(active_items.get("combat_gear_count"), int):
        count += active_items["combat_gear_count"]

    # 2. Explicit combat_gear list
    if isinstance(active_items.get("combat_gear"), list):
        count += len(active_items["combat_gear"])

    # 3. Equipped slots
    combat_slots = [
        "equipped_weapon", "equipped_armor", "equipped_torso",
        "equipped_head", "equipped_shield", "equipped_body"
    ]
    for slot in combat_slots:
        val = active_items.get(slot)
        if val and isinstance(val, str):
            slot_lower = val.lower()
            if any(term in slot_lower for term in ("weapon", "armor", "gun", "knife", "helmet", "vest", "shield", "sword", "shotgun")):
                count += 1
            elif slot in ("equipped_weapon", "equipped_armor", "equipped_shield"):
                count += 1

    # 4. Inventory item flags
    combat_keywords = (
        "shit_gun", "weapon_knife", "body_armor", "vest",
        "hat_helmet", "armor_vest", "bulletproof", "ak47", "glock"
    )
    for kw in combat_keywords:
        if active_items.get(kw) or active_items.get(f"owned_{kw}"):
            count += 1

    return count


def calculate_heist_win_chance(crew_items_list: List[Dict[str, Any]]) -> float:
    """
    Calculates crew win chance:
    Base crew win chance: 45%.
    Increased by combat gear in participants' active_items (+5% per weapon/armor, up to max 75%).
    """
    base_chance = 0.45
    total_gear = sum(count_user_combat_gear(items) for items in crew_items_list)
    bonus = total_gear * 0.05
    win_chance = min(0.75, base_chance + bonus)
    return round(win_chance, 4)


class HeistLobby:
    """
    Represents an active interactive heist lobby.
    """
    def __init__(
        self,
        lobby_id: str,
        chat_id: int,
        initiator_id: int,
        initiator_name: str,
        board_id: str = "b",
        message_id: Optional[int] = None
    ):
        self.lobby_id = lobby_id
        self.chat_id = chat_id
        self.initiator_id = initiator_id
        self.initiator_name = initiator_name
        self.board_id = board_id
        self.message_id = message_id
        self.participants: List[int] = [initiator_id]
        self.participant_names: Dict[int, str] = {initiator_id: initiator_name}
        self.created_at: float = time.time()
        self.expires_at: float = self.created_at + 45.0
        self.status: str = "open"  # "open", "in_progress", "won", "lost", "cancelled"
        self.timer_task: Optional[asyncio.Task] = None


active_heist_lobbies: Dict[str, HeistLobby] = {}
chat_active_heist: Dict[int, str] = {}
heist_engine_lock = asyncio.Lock()


def build_heist_keyboard(lobby: HeistLobby) -> InlineKeyboardMarkup:
    """
    Builds the interactive lobby keyboard with participant count.
    """
    count = len(lobby.participants)
    btn_text = f"🦹 Вступить в банду ({count}/4)"
    buttons = [
        [InlineKeyboardButton(text=btn_text, callback_data=f"heist_join:{lobby.lobby_id}")]
    ]
    if count >= 2:
        buttons.append([
            InlineKeyboardButton(text="🚀 Начать налёт сейчас", callback_data=f"heist_start:{lobby.lobby_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_heist_lobby_text(lobby: HeistLobby) -> str:
    """
    Renders lobby status announcement in authentic 2ch slang.
    """
    time_left = max(0, int(lobby.expires_at - time.time()))
    crew_list = ", ".join(f"<b>{name}</b>" for name in lobby.participant_names.values())
    return (
        "🚨 <b>НАЛЁТ НА ИНКАССАТОРСКИЙ БРОНЕВИК АБУ!</b>\n\n"
        f"Аноним <b>{lobby.initiator_name}</b> заряжает волыну и собирает банду, чтобы взломать "
        "бронированный КАМАЗ с шекелями Абу!\n\n"
        "💰 <b>Куш:</b> от 400,000 до 1,000,000 меченых шекелей!\n"
        "👥 <b>Состав банды:</b> от 2 до 4 человек\n"
        "🔫 <b>Охрана:</b> инкассаторы Абу с пулемётом «Корд»!\n"
        f"⏳ <b>До выезда броневика:</b> {time_left} сек.\n\n"
        f"🦹 <b>Бойцы в банде ({len(lobby.participants)}/4):</b> {crew_list}\n\n"
        "<i>Нажимай кнопку ниже, пока инкассаторы не уехали в закат!</i>"
    )


async def resolve_heist(
    lobby_id: str,
    bot: Any = None,
    db: Any = None,
    force_win: Optional[bool] = None,
    custom_loot_pool: Optional[int] = None
) -> Dict[str, Any]:
    """
    Resolves combat math and rewards/punishments for the heist crew:
    - If < 2 participants: cancels heist.
    - If win: 400k-1M loot split in dirty_balance + 2 wanted stars + 10k bounty each.
    - If lose: 60m mute for all + 15% fine confiscated to Abu fund.
    """
    async with heist_engine_lock:
        lobby = active_heist_lobbies.get(lobby_id)
        if not lobby or lobby.status != "open":
            return {"status": "ignored", "reason": "lobby_not_open"}
        lobby.status = "in_progress"

    if db is None:
        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

    crew_ids = list(lobby.participants)
    num_crew = len(crew_ids)

    # Crew size requirement: 2 to 4
    if num_crew < 2:
        lobby.status = "cancelled"
        cancel_text = (
            "❌ <b>НАЛЁТ СОРВАН!</b>\n"
            "Не набралось смельчаков! Сычи струсили перед пулемётом «Корд» (нужно минимум 2 бойца). "
            "Банда распалась, инкассаторы спокойно увезли кассу."
        )
        if bot and lobby.chat_id:
            try:
                if lobby.message_id:
                    await bot.edit_message_text(
                        text=cancel_text,
                        chat_id=lobby.chat_id,
                        message_id=lobby.message_id,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(lobby.chat_id, cancel_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Failed to post heist cancellation: {e}")

        async with heist_engine_lock:
            active_heist_lobbies.pop(lobby_id, None)
            chat_active_heist.pop(lobby.chat_id, None)
        return {"status": "cancelled", "reason": "not_enough_participants", "participants": crew_ids}

    # Fetch active_items for all crew members
    crew_items: Dict[int, Dict[str, Any]] = {}
    for uid in crew_ids:
        crew_items[uid] = await get_user_active_items(db, uid, lobby.board_id)

    win_chance = calculate_heist_win_chance(list(crew_items.values()))
    if force_win is not None:
        is_win = force_win
    else:
        is_win = (random.random() <= win_chance)

    result_summary: Dict[str, Any] = {
        "status": "won" if is_win else "lost",
        "win_chance": win_chance,
        "participants": crew_ids,
        "crew_size": num_crew,
    }

    if is_win:
        lobby.status = "won"
        loot_pool = custom_loot_pool if custom_loot_pool is not None else random.randint(400_000, 1_000_000)
        per_member = loot_pool // num_crew
        result_summary["loot_pool"] = loot_pool
        result_summary["per_member"] = per_member

        for uid in crew_ids:
            u_items = crew_items[uid]
            u_items["dirty_balance"] = u_items.get("dirty_balance", 0.0) + per_member
            u_items["wanted_stars"] = u_items.get("wanted_stars", 0) + 2
            curr_bounty = float(u_items.get("bounty_pool") or u_items.get("bounty") or 0.0)
            u_items["bounty_pool"] = curr_bounty + 10_000.0
            u_items["bounty"] = curr_bounty + 10_000.0
            if db is not None:
                await save_user_active_items(db, uid, u_items, lobby.board_id)
                try:
                    from common.database import record_user_transaction
                    await record_user_transaction(
                        db,
                        uid,
                        float(per_member),
                        "heist_win",
                        f"Налёт на броневик Абу: добыча {per_member:,} меченых шекелей"
                    )
                except Exception as e:
                    logger.warning(f"Transaction log failed for {uid}: {e}")

        win_flavor = random.choice(HEIST_WIN_PHRASES) if HEIST_WIN_PHRASES else (
            "Банда взорвала задние двери броневика к херам! Охрана Абу в ужасе разбежалась, "
            "а пулемёт «Корд» заклинило на третьем выстреле!"
        )
        result_summary["win_phrase"] = win_flavor
        crew_mentions = ", ".join(f"<b>{lobby.participant_names.get(uid, f'Анон #{uid}')}</b>" for uid in crew_ids)
        win_text = (
            "💥 <b>НАЛЁТ УСПЕШЕН! БРОНЕВИК РАЗГРОМЛЕН!</b>\n\n"
            f"{win_flavor}\n\n"
            f"💰 <b>Общий куш:</b> {loot_pool:,} меченых шекелей\n"
            f"💵 <b>Доля каждого бойца:</b> +{per_member:,} ₪ (грязный баланс, отмыв: /launder)\n"
            "⭐ <b>Розыск:</b> +2 звезды розыска каждому!\n"
            "🎯 <b>Награда за головы:</b> +10,000 ₪ баунти!\n\n"
            f"👥 <b>Герои налёта:</b> {crew_mentions}"
        )
        if bot and lobby.chat_id:
            try:
                if lobby.message_id:
                    await bot.edit_message_text(
                        text=win_text,
                        chat_id=lobby.chat_id,
                        message_id=lobby.message_id,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(lobby.chat_id, win_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Failed to post heist victory: {e}")
    else:
        lobby.status = "lost"
        fines_confiscated: Dict[int, int] = {}

        for uid in crew_ids:
            # 60 minutes mute
            await apply_heist_loss_mute(db, uid, lobby.board_id, duration_seconds=3600)

            # 15% wallet balance fine confiscated to Abu Yacht Fund
            confiscated = 0
            if db is not None:
                try:
                    from common.database import (
                        get_user_global_balance,
                        deduct_user_global_balance,
                        add_to_abu_fund,
                        record_user_transaction
                    )
                    bal = await get_user_global_balance(db, uid)
                    fine_amt = int(round(bal * 0.15))
                    if fine_amt > 0:
                        await deduct_user_global_balance(db, uid, lobby.board_id, float(fine_amt))
                        await add_to_abu_fund(
                            db,
                            float(fine_amt),
                            donor_id=uid,
                            reason="Штраф за вооруженное нападение на инкассаторов Абу"
                        )
                        await record_user_transaction(
                            db,
                            uid,
                            -float(fine_amt),
                            "heist_fine",
                            f"Штраф 15% за нападение на броневик Абу: -{fine_amt:,} ₪"
                        )
                        confiscated = fine_amt
                except Exception as e:
                    logger.warning(f"Error executing loss confiscation for {uid}: {e}")
            fines_confiscated[uid] = confiscated

        lose_flavor = random.choice(HEIST_LOSE_PHRASES) if HEIST_LOSE_PHRASES else (
            "Инкассаторы Абу выкатили тяжелый пулемёт «Корд» и открыли ураганный огонь на поражение! "
            "Вся банда изрешечена и упакована лицом в асфальт!"
        )
        result_summary["lose_phrase"] = lose_flavor
        result_summary["fines"] = fines_confiscated
        crew_mentions = ", ".join(f"<b>{lobby.participant_names.get(uid, f'Анон #{uid}')}</b>" for uid in crew_ids)
        lose_text = (
            "💀 <b>ФИАСКО! ОБЛАВА ИНКАССАТОРОВ АБУ!</b>\n\n"
            f"{lose_flavor}\n\n"
            "🚨 <b>Итоги облавы:</b>\n"
            "🔇 Все налётчики отправлены в мут на <b>60 минут</b> за бандитизм!\n"
            "💸 Конфисковано <b>15% чистых шекелей</b> с кошелька каждого участника в казну Абу!\n\n"
            f"👥 <b>Пойманные неудачники:</b> {crew_mentions}"
        )
        if bot and lobby.chat_id:
            try:
                if lobby.message_id:
                    await bot.edit_message_text(
                        text=lose_text,
                        chat_id=lobby.chat_id,
                        message_id=lobby.message_id,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(lobby.chat_id, lose_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Failed to post heist defeat: {e}")

    async with heist_engine_lock:
        active_heist_lobbies.pop(lobby_id, None)
        chat_active_heist.pop(lobby.chat_id, None)

    return result_summary


async def start_lobby_timeout(lobby_id: str, bot: Any):
    """
    Background worker that sleeps 45 seconds and executes heist resolution.
    """
    try:
        await asyncio.sleep(45.0)
        await resolve_heist(lobby_id=lobby_id, bot=bot)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in heist lobby timer: {e}")


@heist_loan_router.message(Command("heist", "налет", "налёт", "ограбление"))
async def cmd_start_heist(message: Message):
    """
    Handler for /heist command. Initiates a 45-second collaborative lobby.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    chat_id = message.chat.id
    board_id = "b"

    try:
        from common.db_pool import get_pool
        db = await get_pool()
    except Exception:
        db = None

    # Check initiator mute status
    if await check_participant_muted(db, user_id, board_id):
        await message.reply("🔇 Ты в муте, чепуха! Рот заклеен, командовать налётом не выйдет.")
        return

    # Check initiator isolation
    if await check_participant_isolated(db, user_id, board_id):
        await message.reply("🧘 Ты сидишь в самоизоляции! Выйди из сычевальни перед тем как грабить броневики.")
        return

    async with heist_engine_lock:
        existing_lid = chat_active_heist.get(chat_id)
        if existing_lid and existing_lid in active_heist_lobbies:
            await message.reply("⚠️ В этом треде уже готовится налёт на броневик! Вступай в банду через кнопку выше.")
            return

        lobby_id = f"heist_{chat_id}_{int(time.time())}_{random.randint(100, 999)}"
        name = message.from_user.full_name or message.from_user.first_name or f"Анон #{user_id}"
        lobby = HeistLobby(
            lobby_id=lobby_id,
            chat_id=chat_id,
            initiator_id=user_id,
            initiator_name=name,
            board_id=board_id
        )
        active_heist_lobbies[lobby_id] = lobby
        chat_active_heist[chat_id] = lobby_id

    lobby_text = format_heist_lobby_text(lobby)
    kb = build_heist_keyboard(lobby)
    sent_msg = await message.reply(lobby_text, reply_markup=kb, parse_mode="HTML")
    lobby.message_id = sent_msg.message_id

    # Spawn 45s timer
    lobby.timer_task = asyncio.create_task(start_lobby_timeout(lobby_id, message.bot))


@heist_loan_router.callback_query(F.data.startswith("heist_join:"))
async def cb_heist_join(callback: CallbackQuery):
    """
    Handles player clicking [🦹 Вступить в банду (X/4)].
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        lobby_id = callback.data.split(":", 1)[1]
        async with heist_engine_lock:
            lobby = active_heist_lobbies.get(lobby_id)
            if not lobby or lobby.status != "open":
                await callback.answer("Налёт уже завершён или отменён!", show_alert=True)
                return

            if user_id in lobby.participants:
                await callback.answer("Ты уже в банде! Заряжай патроны!", show_alert=True)
                return

            if len(lobby.participants) >= 4:
                await callback.answer("Банда уже укомплектована (4/4)! Мест нет!", show_alert=True)
                return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        if await check_participant_muted(db, user_id, lobby.board_id):
            await callback.answer("Ты в муте! Тебя не возьмут на дело.", show_alert=True)
            return

        if await check_participant_isolated(db, user_id, lobby.board_id):
            await callback.answer("Ты в самоизоляции! Сиди дома.", show_alert=True)
            return

        name = callback.from_user.full_name or callback.from_user.first_name or f"Анон #{user_id}"
        auto_trigger = False

        async with heist_engine_lock:
            if lobby.status != "open":
                await callback.answer("Налёт уже стартовал!", show_alert=True)
                return
            if user_id not in lobby.participants and len(lobby.participants) < 4:
                lobby.participants.append(user_id)
                lobby.participant_names[user_id] = name
                if len(lobby.participants) >= 4:
                    auto_trigger = True
                    if lobby.timer_task:
                        lobby.timer_task.cancel()

        await callback.answer("🦹 Ты вступил в банду налётчиков!", show_alert=False)

        if auto_trigger:
            await resolve_heist(lobby_id=lobby_id, bot=callback.bot)
        else:
            # Update lobby message
            if callback.message:
                await _safe_edit_or_replace_message(
                    callback.message,
                    format_heist_lobby_text(lobby),
                    reply_markup=build_heist_keyboard(lobby),
                )
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data.startswith("heist_start:"))
async def cb_heist_start(callback: CallbackQuery):
    """
    Allows lobby captain (initiator) to launch heist early if >= 2 participants.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return
        lobby_id = callback.data.split(":", 1)[1]

        async with heist_engine_lock:
            lobby = active_heist_lobbies.get(lobby_id)
            if not lobby or lobby.status != "open":
                await callback.answer("Налёт уже стартовал или отменён!", show_alert=True)
                return

            if user_id != lobby.initiator_id:
                await callback.answer("Только главарь банды может дать команду на штурм!", show_alert=True)
                return

            if len(lobby.participants) < 2:
                await callback.answer("Нужно минимум 2 бойца для налёта! Жди подельников!", show_alert=True)
                return

            if lobby.timer_task:
                lobby.timer_task.cancel()

        await callback.answer("🚀 По коням! Начинаем штурм броневика!", show_alert=False)
        await resolve_heist(lobby_id=lobby_id, bot=callback.bot)
    finally:
        await safe_callback_answer(callback)


# -----------------------------------------------------------------------------
# SYSTEM 3: LOAN SHARK / MICROLOANS («Быстрошекель Пахома»)
# -----------------------------------------------------------------------------

def check_and_apply_loan_penalty(
    active_items: Dict[str, Any],
    current_time: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Checks if active loan is overdue. If current_time > loan_due_at:
    - Marks is_defaulter = True
    - Returns (True, collector_harassment_text)
    """
    if not isinstance(active_items, dict):
        return (False, "")

    loan_owed = float(active_items.get("loan_owed", 0.0))
    loan_due_at = float(active_items.get("loan_due_at", 0.0))

    if loan_owed <= 0 or loan_due_at <= 0:
        return (False, "")

    now = time.time() if current_time is None else current_time
    if now > loan_due_at:
        active_items["is_defaulter"] = True
        collector_phrase = random.choice(LOAN_PAKHOM_COLLECTOR_PHRASES) if LOAN_PAKHOM_COLLECTOR_PHRASES else (
            "👵 Счётчик тикает, чепуха дырявая! Пахом лично приехал с паяльником за процентами!"
        )
        threat_text = (
            "🚨 <b>Счётчик тикает, чепуха! Пахом прислал коллекторов за своими шекелями!</b>\n"
            f"<i>«{collector_phrase}»</i>\n\n"
            f"Срок возврата займа истёк! Твой долг: <b>{int(loan_owed):,} ₪</b>.\n"
            "Включён режим принудительного взыскания: <b>75% зарплаты на /work</b> уходит Пахому в счёт долга!"
        )
        return (True, threat_text)

    return (False, "")


def garnish_wages_for_loan(
    active_items: Dict[str, Any],
    wage: float,
    current_time: Optional[float] = None
) -> Tuple[float, float, str]:
    """
    Garnishes 75% of /work wage if user is a loan defaulter.
    Returns: (net_wage_to_user, garnished_amount, notice_text)
    """
    if not isinstance(active_items, dict) or wage <= 0:
        return (wage, 0.0, "")

    # Trigger penalty check
    check_and_apply_loan_penalty(active_items, current_time)

    if not active_items.get("is_defaulter"):
        return (wage, 0.0, "")

    loan_owed = float(active_items.get("loan_owed", 0.0))
    if loan_owed <= 0:
        active_items["is_defaulter"] = False
        active_items["loan_amount"] = 0
        return (wage, 0.0, "")

    # 75% wage garnishment
    withheld = round(min(wage * 0.75, loan_owed), 2)
    net_wage = round(wage - withheld, 2)
    remaining_owed = round(max(0.0, loan_owed - withheld), 2)

    active_items["loan_owed"] = remaining_owed
    if remaining_owed <= 0:
        active_items["is_defaulter"] = False
        active_items["has_active_loan"] = False
        active_items["loan_amount"] = 0
        active_items["loan_due_at"] = 0
        notice = (
            f"💸 <b>КОЛЛЕКТОРЫ ПАХОМА ВЗЫСКАЛИ {int(withheld):,} ₪!</b>\n"
            "🎉 Долг полностью погашен из твоей зарплаты! Пахом убирает биты и снимает счётчик."
        )
    else:
        notice = (
            f"💸 <b>КОЛЛЕКТОРЫ ПАХОМА ОТОБРАЛИ {int(withheld):,} ₪!</b> (75% зарплаты удержано в счёт долга).\n"
            f"Остаток долга: <b>{int(remaining_owed):,} ₪</b>. Счётчик продолжает тикать!"
        )

    return (net_wage, withheld, notice)


async def process_borrow_loan(
    db: Any,
    user_id: int,
    amount: int,
    board_id: str = "b",
    active_items: Optional[Dict[str, Any]] = None,
    current_balance: Optional[float] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validates and executes loan issuance from Loan Shark Пахом:
    - User clean balance must be <= 500 ₪
    - Loan amount must be between 500 ₪ and 5,000 ₪
    - User must not have active unpaid/overdue loan
    - 20% flat interest (owed = 1.20 * amount)
    - 24-hour timer (loan_due_at)
    """
    lock = await get_user_financial_lock(user_id)
    async with lock:
        if active_items is None:
            active_items = await get_user_active_items(db, user_id, board_id)

        # Check active loan
        if float(active_items.get("loan_owed", 0.0)) > 0:
            owed = int(active_items["loan_owed"])
            return (
                False,
                f"❌ Пахом скалится и машет сладким хлебом: <i>«Ты ещё прошлый долг не закрыл, чепушила! "
                f"Торчишь мне <b>{owed:,} ₪</b>! Сначала верни через <code>/paydebt</code>!»</i>",
                {"error": "active_loan_exists", "owed": owed}
            )

        # Check loan range
        if amount < 500 or amount > 5000:
            return (
                False,
                "⚠️ «Быстрошекель Пахома» выдаёт микрозаймы строго от <b>500 ₪</b> до <b>5,000 ₪</b>! "
                "Укажи правильную сумму: <code>/loan 1000</code>.",
                {"error": "invalid_amount"}
            )

        # Check clean balance
        if current_balance is None:
            try:
                from common.database import get_user_global_balance
                current_balance = await get_user_global_balance(db, user_id)
            except Exception:
                current_balance = 0.0

        if current_balance > 500.0:
            return (
                False,
                f"❌ Пахом ощупывает твои карманы: <i>«У тебя на руках аж <b>{int(current_balance):,} ₪</b>, олигарх мамкин! "
                "Быстрошекель выдаётся только нищим сычам с балансом до 500 ₪! Пшёл вон!»</i>",
                {"error": "balance_too_high", "balance": current_balance}
            )

        now = time.time()
        due_at = now + 86400.0  # 24 hours
        owed = int(round(amount * 1.20))

        active_items["loan_amount"] = amount
        active_items["loan_owed"] = owed
        active_items["loan_taken_at"] = now
        active_items["loan_due_at"] = due_at
        active_items["has_active_loan"] = True
        active_items["is_defaulter"] = False

        if db is not None:
            await save_user_active_items(db, user_id, active_items, board_id)
            try:
                from common.database import add_user_global_balance, record_user_transaction
                await add_user_global_balance(db, user_id, board_id, float(amount))
                await record_user_transaction(
                    db,
                    user_id,
                    float(amount),
                    "loan_borrow",
                    f"Микрозайм в «Быстрошекеле Пахома» +{amount:,} ₪ (к возврату: {owed:,} ₪)"
                )
            except Exception as e:
                logger.error(f"Error updating balance on loan issuance: {e}")

        contract_text = (
            "🪙 <b>БЫСТРОШЕКЕЛЬ ПАХОМА:</b>\n"
            f"Пахом отсчитал тебе <b>{amount:,} ₪</b> со словами:\n"
            f"<i>«Братишка, покушать принёс! Через 24 часа вернёшь <b>{owed:,} ₪</b> (+20%). "
            "Не вернёшь — включу счётчик, пошлю коллекторов и заберу 75% твоей зарплаты!»</i>\n\n"
            "⏳ <b>Срок возврата:</b> 24 часа\n"
            "💳 <b>Команда для возврата:</b> <code>/paydebt</code>"
        )

        return (
            True,
            contract_text,
            {"amount": amount, "owed": owed, "due_at": due_at}
        )


async def process_repay_debt(
    db: Any,
    user_id: int,
    board_id: str = "b",
    active_items: Optional[Dict[str, Any]] = None,
    current_balance: Optional[float] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Repays active loan in full:
    - Deducts owed amount from clean global balance
    - Clears loan debt in active_items
    - Increases credit rating
    """
    lock = await get_user_financial_lock(user_id)
    async with lock:
        if active_items is None:
            active_items = await get_user_active_items(db, user_id, board_id)

        owed = float(active_items.get("loan_owed", 0.0))
        if owed <= 0:
            return (
                False,
                "🤝 Пахом машет рукой: <i>«Ты мне ничего не должен, братишка! Отдыхай пока!»</i>",
                {"error": "no_active_debt"}
            )

        int_owed = int(round(owed))
        if current_balance is None:
            try:
                from common.database import get_user_global_balance
                current_balance = await get_user_global_balance(db, user_id)
            except Exception:
                current_balance = 0.0

        if current_balance < int_owed:
            return (
                False,
                f"❌ У тебя недостаточно шекелей для возврата долга! Нужно <b>{int_owed:,} ₪</b>, "
                f"а у тебя на руках всего <b>{int(current_balance):,} ₪</b>. Иди работай на <code>/work</code> или грабь броневик!",
                {"error": "insufficient_balance", "owed": int_owed, "balance": current_balance}
            )

        # Clear debt & increase credit rating
        active_items["loan_amount"] = 0
        active_items["loan_owed"] = 0
        active_items["loan_due_at"] = 0
        active_items["has_active_loan"] = False
        active_items["is_defaulter"] = False
        active_items["credit_rating"] = active_items.get("credit_rating", 100) + 10

        if db is not None:
            await save_user_active_items(db, user_id, active_items, board_id)
            try:
                from common.database import deduct_user_global_balance, record_user_transaction
                await deduct_user_global_balance(db, user_id, board_id, float(int_owed))
                await record_user_transaction(
                    db,
                    user_id,
                    -float(int_owed),
                    "loan_repay",
                    f"Возврат займа Пахому: -{int_owed:,} ₪"
                )
            except Exception as e:
                logger.error(f"Error deducting loan repayment balance: {e}")

        repay_text = (
            "🤝 <b>ПАХОМ ДОВОЛЕН:</b>\n"
            f"Ты вернул долг <b>{int_owed:,} ₪</b>! Пахом убирает сладкий хлеб:\n"
            "<i>«Красава, братишка, уважил старика. Кредитный рейтинг вырос (+10)! Всегда рады в 'Быстрошекеле'!»</i>"
        )

        return (
            True,
            repay_text,
            {"repaid": int_owed, "credit_rating": active_items["credit_rating"]}
        )


def build_loan_keyboard() -> InlineKeyboardMarkup:
    """
    Builds the preset borrowing inline buttons, repay button, and back button:
    [💸 500 ₪], [💸 1,000 ₪]
    [💸 2,500 ₪], [💸 5,000 ₪]
    [💳 Погасить долг (/paydebt)]
    [⬅️ Назад на биржу (/work)]
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💸 500 ₪", callback_data="loan_take_500"),
            InlineKeyboardButton(text="💸 1,000 ₪", callback_data="loan_take_1000"),
        ],
        [
            InlineKeyboardButton(text="💸 2,500 ₪", callback_data="loan_take_2500"),
            InlineKeyboardButton(text="💸 5,000 ₪", callback_data="loan_take_5000"),
        ],
        [
            InlineKeyboardButton(text="💳 Погасить долг (/paydebt)", callback_data="loan_paydebt_full"),
        ],
        [
            InlineKeyboardButton(text="◀️ Назад на биржу", callback_data="work_hub"),
            InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
        ]
    ])


def format_loan_menu_text(active_items: Dict[str, Any], clean_balance: float = 0.0) -> str:
    """
    Renders rich loan card with credit rating, active loan status, and debt terms.
    """
    credit_rating = int(active_items.get("credit_rating", 100))
    loan_owed = float(active_items.get("loan_owed", 0.0))
    loan_due_at = float(active_items.get("loan_due_at", 0.0))
    is_defaulter = bool(active_items.get("is_defaulter", False))
    now = time.time()

    if loan_owed > 0:
        if is_defaulter or now > loan_due_at:
            status_line = "🚨 <b>ПРОСРОЧЕНО (ДЕФОЛТ)!</b> Коллекторы удерживают 75% зарплаты на /work!"
            time_line = "⏰ <b>Срок:</b> Истёк! Включён счётчик!"
        else:
            time_left_sec = max(0, int(loan_due_at - now))
            hours = time_left_sec // 3600
            minutes = (time_left_sec % 3600) // 60
            status_line = "⏳ <b>Активен (ожидает возврата)</b>"
            time_line = f"⏰ <b>Осталось времени:</b> {hours}ч {minutes}мин"
        debt_info = (
            f"💳 <b>Текущий долг:</b> <b>{int(loan_owed):,} ₪</b>\n"
            f"{status_line}\n"
            f"{time_line}\n"
        )
    else:
        debt_info = "💳 <b>Текущий долг:</b> 0 ₪ (задолженностей нет)\n"

    eligibility = (
        "✅ <b>Доступен займ</b> (баланс <= 500 ₪)"
        if clean_balance <= 500.0 and loan_owed <= 0
        else "⚠️ <i>Выдача доступна только при балансе <= 500 ₪ и отсутствии долгов</i>"
    )

    return (
        "🪙 <b>БЫСТРОШЕКЕЛЬ ПАХОМА — МИКРОЗАЙМЫ</b>\n\n"
        f"⭐️ <b>Кредитный рейтинг:</b> {credit_rating}\n"
        f"💵 <b>Твой баланс:</b> {int(clean_balance):,} ₪\n"
        f"{debt_info}\n"
        "📜 <b>Условия кредитования:</b>\n"
        "• Сумма: от <b>500 ₪</b> до <b>5,000 ₪</b>\n"
        "• Ставка: <b>+20%</b> на 24 часа\n"
        "• При просрочке: <b>75% зарплаты на /work</b> уходит Пахому\n"
        "• Возврат вовремя: <b>+10</b> к кредитному рейтингу!\n\n"
        f"{eligibility}\n\n"
        "<i>Выбери сумму займа или погаси активный долг:</i>"
    )


@heist_loan_router.message(Command("loan", "заем", "займ", "долг"))
async def cmd_loan(message: Message):
    """
    Handler for /loan, /заем, /займ, /долг commands.
    If invoked without arguments: shows interactive loan menu with preset borrowing buttons.
    If invoked with amount (e.g. /loan 1000): borrows requested amount directly.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    try:
        from common.db_pool import get_pool
        db = await get_pool()
    except Exception:
        db = None

    board_id = "b"
    text_parts = message.text.strip().split() if message.text else []

    # If no amount argument specified -> Show interactive rich card menu
    if len(text_parts) < 2:
        active_items = await get_user_active_items(db, user_id, board_id)
        current_bal = 0.0
        if db is not None:
            try:
                from common.database import get_user_global_balance
                current_bal = await get_user_global_balance(db, user_id)
            except Exception:
                current_bal = 0.0
        card_text = format_loan_menu_text(active_items, current_bal)
        kb = build_loan_keyboard()
        await message.reply(card_text, reply_markup=kb, parse_mode="HTML")
        return

    try:
        amount = int(text_parts[1])
    except ValueError:
        await message.reply("⚠️ Укажи целое число шекелей! Например: <code>/loan 1000</code>.", parse_mode="HTML")
        return

    success, reply_text, _ = await process_borrow_loan(db, user_id, amount, board_id=board_id)
    nav_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Погасить долг (/paydebt)", callback_data="loan_paydebt_full"),
            InlineKeyboardButton(text="💼 На биржу (/work)", callback_data="work_hub")
        ]
    ])
    await message.reply(reply_text, reply_markup=nav_kb, parse_mode="HTML")


@heist_loan_router.callback_query(F.data == "loan_hub")
async def cb_loan_hub(callback: CallbackQuery):
    """
    Callback for opening/refreshing the loan hub menu.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        active_items = await get_user_active_items(db, user_id, "b")
        current_bal = 0.0
        if db is not None:
            try:
                from common.database import get_user_global_balance
                current_bal = await get_user_global_balance(db, user_id)
            except Exception:
                current_bal = 0.0

        card_text = format_loan_menu_text(active_items, current_bal)
        kb = build_loan_keyboard()
        from common.bot_helpers import render_menu_transition
        await render_menu_transition(callback, card_text, kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data.in_({"loan_take_500", "loan_take_1000", "loan_take_2500", "loan_take_5000"}))
async def cb_loan_take_preset(callback: CallbackQuery):
    """
    Handles callbacks: loan_take_500, loan_take_1000, loan_take_2500, loan_take_5000.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        preset_map = {
            "loan_take_500": 500,
            "loan_take_1000": 1000,
            "loan_take_2500": 2500,
            "loan_take_5000": 5000,
        }
        amount = preset_map.get(callback.data, 500)

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        success, reply_text, _ = await process_borrow_loan(db, user_id, amount, board_id="b")
        if success:
            await safe_callback_answer(callback, f"🪙 Займ {amount:,} ₪ оформлен!", show_alert=False)
        else:
            await safe_callback_answer(callback, "Ошибка оформления займа!", show_alert=True)

        result_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад в Быстрошекель", callback_data="loan_hub"),
                InlineKeyboardButton(text="💼 На биржу (/work)", callback_data="work_hub")
            ],
            [
                InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
            ]
        ])
        from common.bot_helpers import render_menu_transition
        await render_menu_transition(callback, reply_text, result_kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.callback_query(F.data == "loan_paydebt_full")
async def cb_loan_paydebt_full(callback: CallbackQuery):
    """
    Handles callback: loan_paydebt_full.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        if not user_id:
            return

        try:
            from common.db_pool import get_pool
            db = await get_pool()
        except Exception:
            db = None

        success, reply_text, _ = await process_repay_debt(db, user_id, board_id="b")
        if success:
            await safe_callback_answer(callback, "🤝 Долг полностью погашен!", show_alert=False)
        else:
            await safe_callback_answer(callback, "Не удалось погасить долг!", show_alert=True)

        result_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад в Быстрошекель", callback_data="loan_hub"),
                InlineKeyboardButton(text="💼 На биржу (/work)", callback_data="work_hub")
            ],
            [
                InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
            ]
        ])
        from common.bot_helpers import render_menu_transition
        await render_menu_transition(callback, reply_text, result_kb, prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@heist_loan_router.message(Command("paydebt", "вернуть"))
async def cmd_paydebt(message: Message):
    """
    Handler for /paydebt and /вернуть.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    try:
        from common.db_pool import get_pool
        db = await get_pool()
    except Exception:
        db = None

    success, reply_text, _ = await process_repay_debt(db, user_id, board_id="b")
    nav_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Назад в Быстрошекель", callback_data="loan_hub"),
            InlineKeyboardButton(text="💼 На биржу (/work)", callback_data="work_hub")
        ],
        [
            InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
        ]
    ])
    await message.reply(reply_text, reply_markup=nav_kb, parse_mode="HTML")
