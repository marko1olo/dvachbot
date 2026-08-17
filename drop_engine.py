"""
Drop Engine for DvachBot: Public Money Drop ("Чек / Дроп шекелей в тред на реакцию")
100% race-condition protected inside atomic db_lock.
"""

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------

@dataclass
class DropRecord:
    drop_id: str
    donor_id: int
    donor_name: str
    board_id: str
    amount: int
    created_at: float
    expires_at: float
    status: str = "active"  # "active", "claimed", "expired", "cancelled"
    claimed_by: Optional[int] = None
    claimed_name: Optional[str] = None
    claimed_at: Optional[float] = None


# In-memory registry of active and recent drops
active_drops: Dict[str, DropRecord] = {}
drop_lock = asyncio.Lock()


# -----------------------------------------------------------------------------
# Drop Creation & Claiming
# -----------------------------------------------------------------------------

async def create_money_drop(
    donor_id: int,
    donor_name: str,
    board_id: str,
    amount: int,
    db_lock: asyncio.Lock,
    db_conn,
    timeout_sec: float = 600.0,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically creates a public money drop by deducting funds from donor global balance.
    """
    if amount < 10:
        return False, "❌ Минимальная сумма для дропа — 10 ₪.", None

    from common.database import deduct_user_global_balance, get_user_global_balance

    async with db_lock:
        try:
            ok, new_bal = await deduct_user_global_balance(db_conn, donor_id, board_id, amount)
            if not ok:
                current_bal = await get_user_global_balance(db_conn, donor_id)
                return False, f"❌ Недостаточно средств! Твой баланс: {int(current_bal)} ₪, а попытка дропнуть: {amount} ₪.", None
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка базы данных при создании дропа: {e}", None

    drop_id = secrets.token_hex(6)
    now = time.time()
    record = DropRecord(
        drop_id=drop_id,
        donor_id=donor_id,
        donor_name=donor_name,
        board_id=board_id,
        amount=amount,
        created_at=now,
        expires_at=now + timeout_sec,
        status="active",
    )
    
    async with drop_lock:
        active_drops[drop_id] = record

    return True, "✅ Дроп успешно создан и отправлен в чат!", record


async def claim_money_drop(
    drop_id: str,
    claimer_id: int,
    claimer_name: str,
    claimer_board_id: str,
    db_lock: asyncio.Lock,
    db_conn,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically claims a money drop (First-Come, First-Served).
    Guarantees exactly 1 winner under high concurrency.
    """
    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден или уже был удален из памяти.", None

        if record.status == "claimed":
            winner = record.claimed_name or f"Анон #{record.claimed_by}"
            return False, f"❌ Этот дроп уже забрал {winner}!", record

        if record.status == "expired":
            return False, "❌ Время действия этого дропа истекло, шекели вернулись донору.", record

        if record.status == "cancelled":
            return False, "❌ Этот дроп был отменен создателем.", record

        if record.donor_id == claimer_id:
            return False, "❌ Ты не можешь забрать свой собственный дроп! (Используй отмену, если передумал).", record

        # Reserve drop status immediately inside drop_lock
        record.status = "claimed"
        record.claimed_by = claimer_id
        record.claimed_name = claimer_name
        record.claimed_at = time.time()

    # Atomically credit claimer in DB
    from common.database import add_user_global_balance
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, claimer_id, claimer_board_id, record.amount)
            await db_conn.commit()
        except Exception as e:
            # Revert status on severe db failure
            async with drop_lock:
                record.status = "active"
                record.claimed_by = None
                record.claimed_name = None
            return False, f"❌ Ошибка начисления выигрыша: {e}", None

    return True, f"🎉 Ты успешно перехватил дроп на {record.amount} ₪!", record


async def cancel_money_drop(
    drop_id: str,
    user_id: int,
    db_lock: asyncio.Lock,
    db_conn,
) -> Tuple[bool, str]:
    """
    Cancels an active drop and refunds donor.
    """
    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден."
        if record.donor_id != user_id:
            return False, "❌ Ты не являешься создателем этого дропа."
        if record.status != "active":
            return False, f"❌ Нельзя отменить дроп со статусом '{record.status}'."
        
        record.status = "cancelled"

    from common.database import add_user_global_balance
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, record.donor_id, record.board_id, record.amount)
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка возврата средств: {e}"

    return True, f"✅ Дроп на {record.amount} ₪ отменен, средства возвращены на баланс."


async def expire_unclaimed_drops_step(db_lock: asyncio.Lock, db_conn) -> List[DropRecord]:
    """
    Background step: refunds drops older than their expiration timestamp.
    """
    from common.database import add_user_global_balance
    now = time.time()
    expired_list: List[DropRecord] = []

    async with drop_lock:
        for drop_id, record in list(active_drops.items()):
            if record.status == "active" and now >= record.expires_at:
                record.status = "expired"
                expired_list.append(record)

    if not expired_list:
        return []

    async with db_lock:
        for rec in expired_list:
            try:
                await add_user_global_balance(db_conn, rec.donor_id, rec.board_id, rec.amount)
            except Exception:
                pass
        try:
            await db_conn.commit()
        except Exception:
            pass

    return expired_list


# -----------------------------------------------------------------------------
# Inline Keyboards for Drop System
# -----------------------------------------------------------------------------

def get_drop_claim_keyboard(drop_id: str, amount: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"💸 Забрать {amount} ₪", callback_data=f"drop:claim:{drop_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_drop_creator_keyboard(current_balance: int) -> InlineKeyboardMarkup:
    third = max(10, current_balance // 3)
    half = max(10, current_balance // 2)
    all_in = max(10, current_balance)

    buttons = [
        [
            InlineKeyboardButton(text=f"💰 Треть ({third} ₪)", callback_data=f"drop:create:{third}"),
            InlineKeyboardButton(text=f"💰 Половина ({half} ₪)", callback_data=f"drop:create:{half}"),
        ],
        [
            InlineKeyboardButton(text=f"🔥 Выбросить всё ({all_in} ₪)", callback_data=f"drop:create:{all_in}"),
        ],
        [
            InlineKeyboardButton(text="100 ₪", callback_data="drop:create:100"),
            InlineKeyboardButton(text="500 ₪", callback_data="drop:create:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data="drop:create:1000"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="drop:cancel_menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
