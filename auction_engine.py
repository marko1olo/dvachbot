# -*- coding: utf-8 -*-
"""
auction_engine.py
Atomic Auction System & Whale Commands for DvachBot (Milestone 3)
Provides auction schema initialization, creation, atomic bidding with escrow refund,
anti-sniping, auction finalization with 100% burn to Abu Yacht Fund,
as well as auction_router handling /auction, /bid, /whale_safe, and /raid_oligarch.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from common.db_pool import get_pool
from common.database import get_user_global_balance
from whale_economy_engine import (
    ensure_auction_schema,
    create_auction,
    place_auction_bid,
    finish_active_auctions,
    get_active_auctions,
    buy_whale_safe,
    execute_oligarch_raid,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ensure_auction_schema",
    "create_auction",
    "place_auction_bid",
    "finish_active_auctions",
    "get_active_auctions",
    "auction_router",
]

auction_router = Router(name="auction_router")

# Active raid lobbies in memory: raid_id -> dict
_ACTIVE_RAIDS: Dict[str, Dict[str, Any]] = {}


# =============================================================================
# 1. /auction HANDLER
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(auction|auctions|аукцион)\b", flags=re.IGNORECASE))
async def cmd_auction(message: types.Message):
    """
    Displays active auctions or allows creating lots via /auction create.
    """
    board_id = message.board_id if isinstance(getattr(message, "board_id", None), str) else "b"
    text_val = (message.text or "").strip()
    parts = text_val.split(maxsplit=5)
    db = await get_pool()

    # /auction create <lot_type> <start_price> <min_step> <duration_hours> <title>
    if len(parts) >= 6 and parts[1].lower() == "create":
        lot_type = parts[2]
        try:
            start_price = float(parts[3])
            min_step = float(parts[4])
            raw_hours = parts[5].split()[0]
            duration_hours = float(raw_hours)
            title = " ".join(parts[5].split()[1:]) if len(parts[5].split()) > 1 else f"Лот {lot_type}"
            duration_sec = duration_hours * 3600.0
        except ValueError:
            await message.reply(
                "❌ Неверные параметры.\n"
                "Формат: <code>/auction create &lt;lot_type&gt; &lt;start_price&gt; &lt;min_step&gt; &lt;duration_hours&gt; &lt;title&gt;</code>"
            )
            return

        auc_id = await create_auction(
            db, lot_type, title, f"Аукционный лот: {title}", start_price, min_step, duration_sec, board_id
        )
        await message.reply(
            f"🏛️ <b>Аукцион #{auc_id} успешно создан!</b>\n\n"
            f"📦 <b>Лот:</b> {title} ({lot_type})\n"
            f"💰 <b>Стартовая цена:</b> {int(start_price):,} ₪\n"
            f"⚡ <b>Мин. шаг:</b> +{int(min_step):,} ₪\n"
            f"⏳ <b>Длительность:</b> {duration_hours} ч.\n\n"
            f"Делай ставку: <code>/bid {auc_id} {int(start_price)}</code>"
        )
        return

    # Normal listing of active auctions
    auctions = await get_active_auctions(db, board_id)
    if not auctions:
        await message.reply(
            "🏛️ <b>АУКЦИОННЫЙ ДОМ ДВАЧА (F3.2)</b>\n\n"
            "Сейчас нет активных торгов.\n"
            "Следите за объявлениями Абу или создайте лот:\n"
            "<code>/auction create &lt;lot_type&gt; &lt;start_price&gt; &lt;step&gt; &lt;hours&gt; &lt;title&gt;</code>\n\n"
            "Доступные типы: <code>custom_role</code>, <code>board_pin</code>, <code>custom_badge</code>."
        )
        return

    lines = ["🏛️ <b>АКТИВНЫЕ АУКЦИОНЫ ДВАЧА (F3.2)</b>\n"]
    for auc in auctions:
        mins_left = max(1, auc["time_left"] // 60)
        hours_left = mins_left // 60
        rem_str = f"{hours_left} ч. {mins_left % 60} мин." if hours_left > 0 else f"{mins_left} мин."
        next_min = (auc["current_bid"] + auc["min_bid_step"]) if auc["current_winner_id"] else auc["start_price"]
        leader = auc["current_winner_name"] or "Нет ставок"

        lines.append(
            f"🔹 <b>Лот #{auc['id']}: {auc['title']}</b>\n"
            f"📝 <i>{auc['description']}</i>\n"
            f"💰 Текущая ставка: <code>{int(auc['current_bid']):,} ₪</code> (Лидер: <b>{leader}</b>)\n"
            f"⚡ Мин. шаг: <code>+{int(auc['min_bid_step']):,} ₪</code> | ⏳ Осталось: <b>{rem_str}</b>\n"
            f"👉 Поставить: <code>/bid {auc['id']} {int(next_min)}</code>\n"
        )

    lines.append("<i>Все победные ставки на 100% сжигаются в Фонд Яхты Абу!</i>")
    await message.reply("\n".join(lines))


# =============================================================================
# 2. /bid HANDLER
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(bid|auction_bid|ставка)\b", flags=re.IGNORECASE))
async def cmd_bid(message: types.Message):
    """
    Places an atomic bid on an active auction.
    """
    board_id = message.board_id if isinstance(getattr(message, "board_id", None), str) else "b"
    user_id = message.from_user.id
    user_name = message.from_user.full_name or f"Анон #{user_id}"
    parts = (message.text or "").split()

    if len(parts) < 3:
        await message.reply(
            "⚠️ <b>Как делать ставку:</b>\n"
            "<code>/bid &lt;ID аукциона&gt; &lt;сумма шекелей&gt;</code>\n\n"
            "Пример: <code>/bid 1 60000</code>\n"
            "Список активных лотов: <code>/auction</code>"
        )
        return

    try:
        auction_id = int(parts[1])
        bid_amount = float(parts[2])
    except ValueError:
        await message.reply("❌ ID аукциона и сумма ставки должны быть числами!")
        return

    db = await get_pool()
    res = await place_auction_bid(db, auction_id, user_id, user_name, bid_amount, board_id)

    if not res.get("ok"):
        await message.reply(f"❌ <b>Ставка отклонена:</b> {res.get('error', 'Неизвестная ошибка')}")
        return

    snipe_txt = (
        "\n\n🚨 <b>АНТИ-СНАЙПИНГ:</b> До конца оставалось менее 5 минут! Время аукциона продлено на +300 секунд."
        if res.get("extended") else ""
    )
    prev_txt = "\nПредыдущему лидеру возвращено 100% ставки из эскроу." if res.get("previous_winner") else ""

    await message.reply(
        f"🔨 <b>СТАВКА ПРИНЯТА!</b>\n\n"
        f"Аукцион: <b>#{auction_id}</b>\n"
        f"Твоя ставка: <code>{int(bid_amount):,} ₪</code>\n"
        f"Статус: <b>Лидер аукциона 👑</b>"
        f"{prev_txt}{snipe_txt}"
    )


# =============================================================================
# 3. /whale_safe HANDLER
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(whale_safe|whale|сейф_олигарха)\b", flags=re.IGNORECASE))
async def cmd_whale_safe(message: types.Message):
    """
    Purchases and opens a Whale Safe (Сейф Олигарха).
    """
    board_id = message.board_id if isinstance(getattr(message, "board_id", None), str) else "b"
    user_id = message.from_user.id
    db = await get_pool()

    res = await buy_whale_safe(db, user_id, board_id)

    if not res.get("ok"):
        await message.reply(f"❌ <b>Покупка отклонена:</b> {res.get('error')}")
        return

    rec_str = f"\n\n{res['recycle_note']}" if res.get("recycle_note") else ""
    text = (
        f"🐋 <b>СЕЙФ ОЛИГАРХА ВЗЛОМАН!</b>\n\n"
        f"🌟 <b>Тир:</b> {res['tier']}\n"
        f"🎁 <b>Награда:</b> <b>{res['title']}</b>\n"
        f"📝 <i>{res['desc']}</i>{rec_str}\n\n"
        f"🔥 <i>70% стоимости ({res['burned_to_abu']:,.0f} ₪) навсегда сожжено в Фонд Яхты Абу!</i>\n"
        f"Твой новый баланс: <code>{int(res['new_balance']):,} ₪</code>"
    )
    await message.reply(text)


# =============================================================================
# 4. /raid_oligarch & LOBBY HANDLERS
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(raid_oligarch|раскулачить)\b", flags=re.IGNORECASE))
async def cmd_raid_oligarch(message: types.Message):
    """
    Initiates or executes a collaborative proletarian raid against an oligarch.
    """
    board_id = message.board_id if isinstance(getattr(message, "board_id", None), str) else "b"
    user_id = message.from_user.id
    text_val = (message.text or "").strip()
    parts = text_val.split()
    db = await get_pool()

    # Check target from reply
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        if not message.reply_to_message.from_user.is_bot:
            target_id = message.reply_to_message.from_user.id

    # Check if voter IDs supplied directly in arguments
    provided_voters: List[int] = []
    if len(parts) > 1:
        # Check comma-separated: /raid_oligarch 1,2,3,4,5 [target_id]
        raw_voters = parts[1].split(",")
        if len(raw_voters) >= 5:
            try:
                provided_voters = [int(v.strip()) for v in raw_voters if v.strip()]
                if len(parts) > 2 and parts[2].isdigit():
                    target_id = int(parts[2])
            except ValueError:
                provided_voters = []
        elif len(parts) >= 6:
            # /raid_oligarch 101 102 103 104 105 [target_id]
            try:
                provided_voters = [int(x) for x in parts[1:6]]
                if len(parts) >= 7 and parts[6].isdigit():
                    target_id = int(parts[6])
            except ValueError:
                provided_voters = []

    if len(provided_voters) >= 5:
        res = await execute_oligarch_raid(db, provided_voters, target_id, board_id)
        if not res.get("ok"):
            await message.reply(f"❌ <b>Рейд не удался:</b> {res.get('error')}")
            return

        await message.reply(
            f"☭ <b>РАСКУЛАЧИВАНИЕ ОЛИГАРХА #{res['target_id']} ЗАВЕРШЕНО!</b>\n\n"
            f"💰 Конфисковано: <b>{res['confiscated']:,.0f} ₪</b> (10% капитала)\n"
            f"🔥 Сожжено в Фонд Яхты Абу (70%): <b>{res['burned_to_abu']:,.0f} ₪</b>\n"
            f"🛠️ Распределено 5 работягам (30%): <b>{res['distributed_total']:,.0f} ₪</b>\n"
            f"💵 Доля каждого участника: <b>+{res['per_voter']:,.0f} ₪</b>\n\n"
            f"<i>«Экспроприация экспроприаторов прошла успешно!»</i>"
        )
        return

    # Interactive Raid Lobby
    raid_id = uuid.uuid4().hex[:8]
    _ACTIVE_RAIDS[raid_id] = {
        "voters": [user_id],
        "target_id": target_id,
        "board_id": board_id,
        "created_at": time.time(),
        "chat_id": message.chat.id,
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚩 Вступить в рейд ОБЭП (1/5)", callback_data=f"raid_join_{raid_id}")]
    ])

    tgt_str = f"Олигарх: <code>{target_id}</code>" if target_id else "Самый богатый олигарх борды"
    await message.reply(
        f"☭ <b>ОБЪЯВЛЕН НАРОДНЫЙ РЕЙД ОБЭП (/raid_oligarch)!</b>\n\n"
        f"🎯 <b>Цель:</b> {tgt_str}\n"
        f"Требования к работягам: баланс &lt; 5,000 ₪ и &gt;= 25 постов.\n"
        f"Добыча: 10% капитала цели (макс 200,000 ₪).\n"
        f"70% сжигается в Фонд Яхты Абу, 30% делится поровну между 5 участниками!\n\n"
        f"Собрано пролетариев: <b>1/5</b>",
        reply_markup=kb
    )


@auction_router.callback_query(F.data.startswith("raid_join_"))
async def cb_raid_join(callback: types.CallbackQuery):
    """
    Handles joining an active raid lobby.
    """
    raid_id = callback.data.replace("raid_join_", "")
    raid = _ACTIVE_RAIDS.get(raid_id)
    if not raid:
        await callback.answer("Рейд уже завершен или истек!", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id in raid["voters"]:
        await callback.answer("Ты уже участвуешь в этом рейде!", show_alert=True)
        return

    db = await get_pool()
    bal = await get_user_global_balance(db, user_id)
    async with db.execute("SELECT COALESCE(MAX(posts_count), 0) FROM Users WHERE user_id = ?", (user_id,)) as c:
        p_row = await c.fetchone()
        posts = p_row[0] if p_row else 0

    if posts < 25:
        try:
            async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (user_id,)) as pc:
                pc_row = await pc.fetchone()
                posts = max(posts, pc_row[0] if pc_row else 0)
        except Exception:
            pass

    if bal >= 5000 or posts < 25:
        await callback.answer("❌ Ты не подходишь для рейда! Нужно: баланс < 5,000 ₪ и >= 25 постов.", show_alert=True)
        return

    raid["voters"].append(user_id)
    cnt = len(raid["voters"])

    if cnt < 5:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🚩 Вступить в рейд ОБЭП ({cnt}/5)", callback_data=f"raid_join_{raid_id}")]
        ])
        tgt_str = f"Олигарх: <code>{raid['target_id']}</code>" if raid['target_id'] else "Самый богатый олигарх борды"
        await callback.message.edit_text(
            f"☭ <b>ОБЪЯВЛЕН НАРОДНЫЙ РЕЙД ОБЭП (/raid_oligarch)!</b>\n\n"
            f"🎯 <b>Цель:</b> {tgt_str}\n"
            f"Требования к работягам: баланс &lt; 5,000 ₪ и &gt;= 25 постов.\n"
            f"Добыча: 10% капитала цели (макс 200,000 ₪).\n"
            f"70% сжигается в Фонд Яхты Абу, 30% делится поровну между 5 участниками!\n\n"
            f"Собрано пролетариев: <b>{cnt}/5</b>",
            reply_markup=kb
        )
        await callback.answer(f"Ты вступил в рейд! ({cnt}/5)")
        return

    # 5 voters gathered! Execute!
    _ACTIVE_RAIDS.pop(raid_id, None)
    res = await execute_oligarch_raid(db, raid["voters"], raid["target_id"], raid["board_id"])

    if not res.get("ok"):
        await callback.message.edit_text(f"❌ <b>Рейд ОБЭП провален:</b> {res.get('error')}")
        await callback.answer("Рейд провален!", show_alert=True)
        return

    await callback.message.edit_text(
        f"☭ <b>РАСКУЛАЧИВАНИЕ ОЛИГАРХА #{res['target_id']} ЗАВЕРШЕНО!</b>\n\n"
        f"💰 Конфисковано: <b>{res['confiscated']:,.0f} ₪</b> (10% капитала)\n"
        f"🔥 Сожжено в Фонд Яхты Абу (70%): <b>{res['burned_to_abu']:,.0f} ₪</b>\n"
        f"🛠️ Распределено 5 работягам (30%): <b>{res['distributed_total']:,.0f} ₪</b>\n"
        f"💵 Доля каждого участника: <b>+{res['per_voter']:,.0f} ₪</b>\n\n"
        f"<i>«Экспроприация экспроприаторов прошла успешно!»</i>"
    )
    await callback.answer("Рейд успешно завершен!")
