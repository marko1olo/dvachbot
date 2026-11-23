# -*- coding: utf-8 -*-
"""
auction_engine.py
Atomic Auction System & Whale Commands for DvachBot (Milestone 3)
Provides auction schema initialization, creation, atomic bidding with escrow refund,
anti-sniping, auction finalization with 100% burn to Abu Yacht Fund,
as well as auction_router handling /auction, /bid, /whale_safe, and /raid_oligarch.
"""

import asyncio
import html
import logging
import math
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from common.db_pool import get_pool
from common.database import get_user_global_balance
from common.anon_identity import get_anon_id, generate_anon_name
from whale_economy_engine import (
    ensure_auction_schema,
    create_auction,
    cancel_auction,
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
    "cancel_auction",
    "place_auction_bid",
    "finish_active_auctions",
    "get_active_auctions",
    "check_raid_proletarian",
    "auction_router",
    "format_shekels",
    "format_outbid_notification",
    "format_anti_sniping_notice",
    "format_auction_winner_dm",
    "format_auction_public_announcement",
    "dispatch_auction_completion_notifications",
    "auction_bid_in_flight_guard",
    "is_bid_in_flight",
    "check_bid_debounce",
]

def format_shekels(amount: int | float, show_sign: bool = False) -> str:
    """
    Красивое форматирование шекелей с разделителями тысяч (пробел) и защитой от float-артефактов:
    например, '1 500 ₪' вместо '1500.0000000001 ₪'.
    """
    if amount is None or (isinstance(amount, float) and (math.isnan(amount) or math.isinf(amount))):
        return "0 ₪"
    try:
        rounded = round(float(amount), 2)
        if abs(rounded - round(rounded)) < 1e-5:
            val_int = int(round(rounded))
            sign_prefix = "+" if (show_sign and val_int > 0) else ""
            formatted = f"{val_int:,}".replace(",", " ")
            return f"{sign_prefix}{formatted} ₪"
        else:
            sign_prefix = "+" if (show_sign and rounded > 0) else ""
            formatted = f"{rounded:,.2f}".replace(",", " ")
            return f"{sign_prefix}{formatted} ₪"
    except (ValueError, TypeError, OverflowError):
        return "0 ₪"


# In-flight lock & debouncing for auction bids
_user_bid_locks: Dict[int, asyncio.Lock] = {}
_bidding_inflight: Dict[int, float] = {}
_bid_meta_lock = asyncio.Lock()
user_bid_last_action: Dict[int, float] = {}


class AuctionBidInFlightError(Exception):
    """Выбрасывается при попытке сделать параллельную ставку до завершения предыдущей транзакции."""
    pass


async def get_user_bid_lock(user_id: int) -> asyncio.Lock:
    """Возвращает или создает per-user asyncio.Lock для сериализации ставок."""
    async with _bid_meta_lock:
        if user_id not in _user_bid_locks:
            _user_bid_locks[user_id] = asyncio.Lock()
        return _user_bid_locks[user_id]


def is_bid_in_flight(user_id: int) -> bool:
    """Проверяет, обрабатывается ли ставка прямо сейчас для данного пользователя."""
    lock = _user_bid_locks.get(user_id)
    if lock is not None and lock.locked():
        return True
    return user_id in _bidding_inflight


@asynccontextmanager
async def auction_bid_in_flight_guard(user_id: int, timeout: float = 0.0):
    """
    Контекстный менеджер защиты от спама кнопками ставки (/bid).
    Блокирует параллельные запросы до завершения списания депозита и обновления лота.
    """
    user_lock = await get_user_bid_lock(user_id)
    if user_lock.locked() and timeout <= 0.0:
        raise AuctionBidInFlightError("⏳ Ваша предыдущая ставка ещё обрабатывается! Подождите завершения транзакции.")

    acquired = False
    try:
        if timeout > 0.0:
            try:
                await asyncio.wait_for(user_lock.acquire(), timeout=timeout)
                acquired = True
            except asyncio.TimeoutError:
                raise AuctionBidInFlightError("⏳ Ваша предыдущая ставка ещё обрабатывается! Подождите завершения транзакции.")
        else:
            await user_lock.acquire()
            acquired = True

        _bidding_inflight[user_id] = time.time()
        yield
    finally:
        _bidding_inflight.pop(user_id, None)
        if acquired and user_lock.locked():
            user_lock.release()


def check_bid_debounce(user_id: int, min_interval: float = 1.0) -> Tuple[bool, str]:
    """
    Защита от быстрого спама ставками (debouncing).
    Возвращает (is_allowed, error_message).
    """
    now = time.time()
    last = user_bid_last_action.get(user_id, 0.0)
    if now - last < min_interval:
        rem = round(min_interval - (now - last), 1)
        return False, f"⏳ Не части! Подожди {rem} сек. перед следующей ставкой."
    user_bid_last_action[user_id] = now
    return True, ""


def format_outbid_notification(
    auction_id: int,
    lot_title: str,
    refunded_amount: int | float,
    new_bid: int | float,
    new_leader_name: str = "Другой участник"
) -> str:
    """
    Формирует подробное и понятное уведомление при перебитии ставки игрока:
    - Четко сообщает о перебитии ставки.
    - Подтверждает 100% возврат заблокированного депозита из эскроу на баланс.
    - Указывает актуальную лидирующую ставку лота.
    - Соблюдает полную анонимность лидера (не выводит сырой user_id).
    """
    if isinstance(new_leader_name, int) or (isinstance(new_leader_name, str) and new_leader_name.strip().isdigit()):
        clean_leader = generate_anon_name(int(new_leader_name))
    else:
        clean_leader = html.escape(str(new_leader_name or "Другой участник"))

    return (
        f"🔔 <b>ВНИМАНИЕ! ТВОЮ СТАВКУ ПЕРЕБИЛИ!</b>\n\n"
        f"🏛️ <b>Аукцион:</b> #{auction_id} ({lot_title})\n"
        f"👤 <b>Новый лидер:</b> {clean_leader}\n"
        f"⚡ <b>Новая ставка:</b> {format_shekels(new_bid)}\n\n"
        f"💰 <b>Возврат депозита:</b> Твоя заблокированная ставка {format_shekels(refunded_amount)} "
        f"автоматически и в полном объёме возвращена на твой баланс (100% эскроу-возврат)!\n\n"
        f"👉 Чтобы вернуть лидерство, сделай новую ставку: <code>/bid {auction_id} {int(new_bid) + 1000}</code>"
    )


def format_anti_sniping_notice(extension_sec: int = 300) -> str:
    """
    Формирует понятное уведомление о срабатывании анти-снайпинг таймера (продление торгов при ставке на последних секундах).
    """
    mins = extension_sec // 60
    return (
        f"🚨 <b>АНТИ-СНАЙПИНГ:</b> До завершения торгов оставалось менее {mins} минут!\n"
        f"Время аукциона автоматически продлено на +{mins} мин. (+{extension_sec} сек.), "
        f"чтобы исключить снайпинг в последнюю секунду и дать честный шанс всем участникам."
    )


def format_auction_winner_dm(auc: Dict[str, Any]) -> str:
    """
    Формирует красивое и подробное личное уведомление (DM) победителю аукциона.
    Включает информацию о выигранном лоте, финальной ставке, начисленной награде
    и 100% сжигании средств в Фонд Яхты Абу.
    """
    auc_id = auc.get("auction_id", 0)
    title = html.escape(str(auc.get("title", f"Лот #{auc_id}")))
    lot_type = str(auc.get("lot_type", "")).strip().lower()
    winning_bid = auc.get("winning_bid", 0.0)
    raw_desc = str(auc.get("description", "")).strip()

    reward_details = ""
    if lot_type == "custom_role":
        prefix = raw_desc if raw_desc.startswith("[") else f"[{raw_desc}]"
        safe_prefix = html.escape(prefix)
        reward_details = f"🏷️ <b>Награда:</b> Уникальный префикс <b>{safe_prefix}</b> активирован в твоем профиле на 30 дней!\n"
    elif lot_type == "board_pin":
        reward_details = "📌 <b>Награда:</b> VIP-ваучер на закрепление треда добавлен в твой профиль (активные предметы)!\n"
    elif lot_type == "custom_badge":
        reward_details = f"🎖️ <b>Награда:</b> Уникальный бейдж <b>{title}</b> добавлен в твой профиль!\n"
    else:
        reward_details = f"🎁 <b>Награда:</b> Лот «{title}» успешно начислен на твой аккаунт!\n"

    return (
        f"🎉 <b>ТЫ ВЫИГРАЛ АУКЦИОН #{auc_id}!</b>\n\n"
        f"📦 <b>Выигранный лот:</b> {title}\n"
        f"💰 <b>Финальная ставка:</b> <code>{format_shekels(winning_bid)}</code>\n"
        f"{reward_details}\n"
        f"🔥 100% шекелей твоей ставки сожжены в <b>Фонд Яхты Абу</b> на благо Двачеводства!\n\n"
        f"Посмотреть активные лоты и участвовать снова: <code>/auction</code>"
    )


def format_auction_public_announcement(auc: Dict[str, Any]) -> str:
    """
    Формирует публичное объявление о завершении аукциона для публикации на доске / в треде.
    СТРОГАЯ АНОНИМНОСТЬ: отображает ТОЛЬКО анонимный хэш/псевдоним победителя (anon_name),
    сырой user_id НИКОГДА не выводится в публичный текст.
    """
    auc_id = auc.get("auction_id", 0)
    title = html.escape(str(auc.get("title", f"Лот #{auc_id}")))
    lot_type = str(auc.get("lot_type", "")).strip().lower()
    winning_bid = auc.get("winning_bid", 0.0)
    raw_winner_name = auc.get("winner_name")
    winner_id = auc.get("winner_id")

    # Строгая защита анонимности: если winner_name это сырой ID (цифры) или отсутствует
    if not raw_winner_name or (isinstance(raw_winner_name, str) and raw_winner_name.strip().isdigit()):
        anon_name = generate_anon_name(winner_id or 0)
    else:
        anon_name = str(raw_winner_name).strip()

    safe_anon_name = html.escape(anon_name)

    lot_type_labels = {
        "custom_role": "Уникальный префикс",
        "board_pin": "VIP-закрепление треда",
        "custom_badge": "Коллекционный бейдж",
    }
    type_label = lot_type_labels.get(lot_type, "Особый лот")

    return (
        f"🏛️ <b>АУКЦИОН #{auc_id} ЗАВЕРШЕН!</b>\n\n"
        f"📦 <b>Лот:</b> {title} (<i>{type_label}</i>)\n"
        f"🏆 <b>Победитель:</b> <b>{safe_anon_name}</b>\n"
        f"💰 <b>Финальная ставка:</b> <code>{format_shekels(winning_bid)}</code>\n\n"
        f"🔥 100% суммы ({format_shekels(winning_bid)}) безвозвратно сожжены в Фонд Яхты Абу!\n"
        f"Новые торги и текущие лоты: <code>/auction</code>"
    )


async def dispatch_auction_completion_notifications(
    bots: Any,
    finished_auctions: List[Dict[str, Any]],
    board_data: Any = None,
    db: Any = None
) -> Dict[str, Any]:
    """
    Рассылает уведомления о завершении аукционов:
    1. Персональное ЛС победителю в Telegram через бота.
    2. Публичный анонс на доске Двачеводства (через create_post и enqueue_board_message).
    Гарантирует идемпотентность (через флаг _notified) и отсутствие сбоев рабочего цикла.
    """
    stats = {
        "dm_sent": 0,
        "dm_failed": 0,
        "board_posts": 0,
        "board_posts_failed": 0,
    }
    if not finished_auctions:
        return stats

    b_bot = None
    if isinstance(bots, dict):
        b_bot = bots.get('b') or bots.get('ru') or (next(iter(bots.values())) if bots else None)
    elif hasattr(bots, "send_message"):
        b_bot = bots
    if not b_bot:
        try:
            from common.bot_pool import global_bot_pool
            b_bot = global_bot_pool.get_default_bot()
        except Exception:
            pass

    if board_data is None:
        try:
            import shared_state
            board_data = getattr(shared_state, "board_data", None)
        except Exception:
            pass

    for auc in finished_auctions:
        if auc.get("_notified"):
            continue

        winner_id = auc.get("winner_id")
        winning_bid = auc.get("winning_bid", 0.0)

        # 1. Личное сообщение победителю в Telegram
        if winner_id and winning_bid > 0 and b_bot:
            dm_text = format_auction_winner_dm(auc)
            try:
                await b_bot.send_message(
                    chat_id=winner_id,
                    text=dm_text,
                    parse_mode="HTML"
                )
                stats["dm_sent"] += 1
                await asyncio.sleep(0.05)
            except Exception as e_dm:
                stats["dm_failed"] += 1
                logger.warning(f"Failed to dispatch auction winner DM to user {winner_id}: {e_dm}")

        # 2. Публичный анонс на доске Двачеводства
        target_board = str(auc.get("board_id") or "b")
        announcement_text = format_auction_public_announcement(auc)

        try:
            from common.database import create_post, update_post_content
            from post_helpers import format_header
            import shared_state

            content_obj = {
                'type': 'text',
                'text': announcement_text,
                'is_system_message': True,
                'archive_allowed': True
            }

            pnum = await create_post(
                board_id=target_board,
                author_id=0,
                content=content_obj,
                timestamp=time.time()
            )

            if pnum:
                header_base = await format_header(target_board, pnum)
                content_obj['header'] = f"### ABU YACHT AUCTION ###\n{header_base}"
                await update_post_content(pnum, content_obj)

                recipients = set()
                if board_data and target_board in board_data:
                    u_dict = board_data[target_board].get('users', {})
                    active_u = u_dict.get('active', set())
                    banned_u = u_dict.get('banned', set())
                    recipients = active_u - banned_u

                await shared_state.enqueue_board_message(target_board, {
                    "recipients": recipients,
                    "content": content_obj,
                    "post_num": pnum,
                    "board_id": target_board
                })
                stats["board_posts"] += 1
        except Exception as e_board:
            stats["board_posts_failed"] += 1
            logger.warning(f"Failed to publish auction announcement to board {target_board}: {e_board}")

        auc["_notified"] = True

    return stats

auction_router = Router(name="auction_router")

# Active raid lobbies in memory: raid_id -> dict
_ACTIVE_RAIDS: Dict[str, Dict[str, Any]] = {}
_raid_lock = asyncio.Lock()


async def check_raid_proletarian(db, user_id: int) -> Tuple[bool, str]:
    """
    Checks whether a user qualifies as a proletarian raider:
    1. Not isolated (is_isolated == 0)
    2. Total wealth (wallet + active bank deposits) < 5,000 ₪
    3. Posts >= 25 (Users.posts_count or Posts author count)
    """
    try:
        async with db.execute("SELECT COALESCE(is_isolated, 0) FROM Users WHERE user_id = ?", (user_id,)) as iso_c:
            iso_row = await iso_c.fetchone()
            if iso_row and iso_row[0]:
                return False, "🧘 Ты находишься в режиме самоизоляции и не можешь участвовать в рейдах ОБЭП."
    except Exception:
        pass

    bal = await get_user_global_balance(db, user_id)
    bank_tot = 0.0
    try:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='BankDeposits'") as tc:
            if await tc.fetchone():
                async with db.execute(
                    "SELECT COALESCE(SUM(principal + accrued_interest), 0.0) FROM BankDeposits WHERE user_id = ? AND status = 'active'",
                    (user_id,)
                ) as bc:
                    brow = await bc.fetchone()
                    if brow and brow[0]:
                        bank_tot = float(brow[0])
    except Exception:
        bank_tot = 0.0

    total_wealth = bal + bank_tot
    posts = 0
    try:
        async with db.execute("SELECT COALESCE(SUM(posts_count), 0) FROM Users WHERE user_id = ?", (user_id,)) as c:
            p_row = await c.fetchone()
            posts = p_row[0] if p_row else 0
    except Exception:
        posts = 0

    if posts < 25:
        try:
            async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (user_id,)) as pc:
                pc_row = await pc.fetchone()
                posts = max(posts, pc_row[0] if pc_row else 0)
        except Exception:
            pass

    if total_wealth >= 5000 or posts < 25:
        reasons = []
        if total_wealth >= 5000:
            reasons.append(f"баланс {total_wealth:,.0f} ₪ ≥ 5,000 ₪")
        if posts < 25:
            reasons.append(f"постов {posts} < 25")
        return False, f"Требуется: баланс < 5,000 ₪ и ≥ 25 постов ({', '.join(reasons)})."

    return True, ""


def build_auction_list_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру пагинации и хаб-навигации для активных аукционов."""
    rows: List[List[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav_row: List[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"auc_page:{page-1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="◀️", callback_data="auc_noop"))

        nav_row.append(InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data=f"auc_page:{page}"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"auc_page:{page+1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="▶️", callback_data="auc_noop"))
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="🛒 В Барахолку (/market)", callback_data="market_main_hub"),
        InlineKeyboardButton(text="🏦 Банк Абу (/bank)", callback_data="bank_main_hub"),
    ])
    rows.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main"),
        InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =============================================================================
# 1. /auction HANDLER
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(auction|auctions|аукцион)(?:@\w+)?(?:\s|$)", flags=re.IGNORECASE))
async def cmd_auction(message: types.Message, board_id: str | None = None, **kwargs):
    """
    Displays active auctions or allows creating lots via /auction create.
    """
    board_id = board_id or (message.board_id if isinstance(getattr(message, "board_id", None), str) else "b")
    text_val = (message.text or "").strip()
    parts = text_val.split(maxsplit=5)
    db = await get_pool()

    # /auction cancel <auction_id>
    if len(parts) >= 3 and parts[1].lower() in ("cancel", "отмена", "отменить"):
        from common.config import ADMIN_IDS
        user_id = message.from_user.id if message.from_user else 0
        if user_id not in ADMIN_IDS:
            await message.reply("❌ Отменять аукционы могут только администраторы.")
            return
        try:
            auc_id = int(parts[2])
        except ValueError:
            await message.reply("❌ Неверный ID аукциона.")
            return
        res = await cancel_auction(db, auc_id)
        if not res.get("ok"):
            await message.reply(f"❌ Ошибка отмены аукциона: {res.get('error')}")
            return
        ref_txt = f"\nЛидеру <b>{generate_anon_name(res.get('refunded_to'))}</b> возвращено {res.get('refunded_amount'):,.0f} ₪ из эскроу." if res.get("refunded_to") else ""
        await message.reply(f"🛑 <b>Аукцион #{auc_id} успешно отменен!</b>{ref_txt}")
        return

    # /auction create <lot_type> <start_price> <min_step> <duration_hours> <title>
    if len(parts) >= 6 and parts[1].lower() == "create":
        lot_type = parts[2].lower().strip()
        if lot_type not in ("custom_role", "board_pin", "custom_badge"):
            await message.reply(
                "❌ Недопустимый тип лота.\n"
                "Доступные типы: <code>custom_role</code>, <code>board_pin</code>, <code>custom_badge</code>."
            )
            return
        try:
            start_price = float(parts[3])
            min_step = float(parts[4])
            raw_hours = parts[5].split()[0]
            duration_hours = float(raw_hours)
            title = " ".join(parts[5].split()[1:]) if len(parts[5].split()) > 1 else f"Лот {lot_type}"
            duration_sec = duration_hours * 3600.0
            if start_price < 1.0 or min_step < 1.0 or duration_sec < 60.0 or duration_sec > 30 * 86400:
                raise ValueError("Параметры вне допустимого диапазона (мин. цена 1 ₪, мин. шаг 1 ₪, длительность от 0.02 до 720 ч).")
        except ValueError as err_val:
            await message.reply(
                f"❌ Неверные параметры: {err_val}\n"
                "Формат: <code>/auction create &lt;lot_type&gt; &lt;start_price&gt; &lt;min_step&gt; &lt;duration_hours&gt; &lt;title&gt;</code>"
            )
            return

        try:
            auc_id = await create_auction(
                db, lot_type, title, f"Аукционный лот: {title}", start_price, min_step, duration_sec, board_id
            )
        except ValueError as err_create:
            await message.reply(f"❌ Ошибка создания аукциона: {err_create}")
            return

        await message.reply(
            f"🏛️ <b>Аукцион #{auc_id} успешно создан!</b>\n\n"
            f"📦 <b>Лот:</b> {title} ({lot_type})\n"
            f"💰 <b>Стартовая цена:</b> {int(start_price):,} ₪\n"
            f"⚡ <b>Мин. шаг:</b> +{int(min_step):,} ₪\n"
            f"⏳ <b>Длительность:</b> {duration_hours} ч.\n\n"
            f"Делай ставку: <code>/bid {auc_id} {int(start_price)}</code>"
        )
        return

    # Normal listing of active auctions with safe pagination (max 4 per page, under 4096 chars)
    raw_page = 1
    if len(parts) >= 2 and parts[1].isdigit():
        raw_page = int(parts[1])
    elif len(parts) >= 3 and parts[1].lower() in ("page", "стр", "страница") and parts[2].isdigit():
        raw_page = int(parts[2])

    auctions = await get_active_auctions(db, board_id)
    if not auctions:
        kb = build_auction_list_kb(1, 1)
        await message.reply(
            "🏛️ <b>АУКЦИОННЫЙ ДОМ ДВАЧА</b>\n\n"
            "Сейчас нет активных торгов.\n"
            "Следите за объявлениями Абу или создайте лот:\n"
            "<code>/auction create &lt;lot_type&gt; &lt;start_price&gt; &lt;step&gt; &lt;hours&gt; &lt;title&gt;</code>\n\n"
            "Доступные типы: <code>custom_role</code>, <code>board_pin</code>, <code>custom_badge</code>.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    per_page = 4
    total_count = len(auctions)
    total_pages = max(1, math.ceil(total_count / per_page))
    page = max(1, min(raw_page, total_pages))
    start_idx = (page - 1) * per_page
    page_auctions = auctions[start_idx:start_idx + per_page]

    lines = [f"🏛️ <b>АКТИВНЫЕ АУКЦИОНЫ ДВАЧА</b> (Стр. {page}/{total_pages}, лотов: {total_count})\n"]
    for auc in page_auctions:
        mins_left = max(1, auc["time_left"] // 60)
        hours_left = mins_left // 60
        rem_str = f"{hours_left} ч. {mins_left % 60} мин." if hours_left > 0 else f"{mins_left} мин."
        next_min = (auc["current_bid"] + auc["min_bid_step"]) if auc["current_winner_id"] else auc["start_price"]
        raw_leader = auc.get("current_winner_name")
        if raw_leader and not (isinstance(raw_leader, str) and raw_leader.strip().isdigit()):
            leader_display = str(raw_leader).strip()
        elif auc.get("current_winner_id"):
            leader_display = generate_anon_name(auc["current_winner_id"])
        else:
            leader_display = "Нет ставок"
        leader = html.escape(leader_display)
        safe_title = html.escape(str(auc['title']))
        safe_desc = html.escape(str(auc['description']))

        lines.append(
            f"🔹 <b>Лот #{auc['id']}: {safe_title}</b>\n"
            f"📝 <i>{safe_desc}</i>\n"
            f"💰 Текущая ставка: <code>{int(auc['current_bid']):,} ₪</code> (Лидер: <b>{leader}</b>)\n"
            f"⚡ Мин. шаг: <code>+{int(auc['min_bid_step']):,} ₪</code> | ⏳ Осталось: <b>{rem_str}</b>\n"
            f"👉 Поставить: <code>/bid {auc['id']} {int(next_min)}</code>\n"
        )

    lines.append("<i>Все победные ставки на 100% сжигаются в Фонд Яхты Абу!</i>")
    out_text = "\n".join(lines)
    if len(out_text) > 3900:
        out_text = out_text[:3850] + "\n\n⚠️ <i>[Список сокращен]</i>"

    kb = build_auction_list_kb(page, total_pages)
    await message.reply(out_text, reply_markup=kb, parse_mode="HTML")


# =============================================================================
# 2. /bid HANDLER
# =============================================================================

@auction_router.callback_query(F.data.startswith("auc_page:"))
async def cb_auction_page(callback: types.CallbackQuery):
    """Пагинация активных аукционов через инлайн-кнопки."""
    from common.bot_helpers import safe_callback_answer, render_menu_transition
    try:
        raw_page = callback.data.split(":", 1)[1]
        page = int(raw_page) if raw_page.isdigit() else 1
        board_id = "b"
        if callback.message and isinstance(getattr(callback.message, "board_id", None), str):
            board_id = callback.message.board_id or "b"
        db = await get_pool()
        auctions = await get_active_auctions(db, board_id)
        if not auctions:
            await callback.answer("Аукционы завершены или отсутствуют.", show_alert=True)
            return

        per_page = 4
        total_count = len(auctions)
        total_pages = max(1, math.ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        page_auctions = auctions[start_idx:start_idx + per_page]

        lines = [f"🏛️ <b>АКТИВНЫЕ АУКЦИОНЫ ДВАЧА</b> (Стр. {page}/{total_pages}, лотов: {total_count})\n"]
        for auc in page_auctions:
            mins_left = max(1, auc["time_left"] // 60)
            hours_left = mins_left // 60
            rem_str = f"{hours_left} ч. {mins_left % 60} мин." if hours_left > 0 else f"{mins_left} мин."
            next_min = (auc["current_bid"] + auc["min_bid_step"]) if auc["current_winner_id"] else auc["start_price"]
            raw_leader = auc.get("current_winner_name")
            if raw_leader and not (isinstance(raw_leader, str) and raw_leader.strip().isdigit()):
                leader_display = str(raw_leader).strip()
            elif auc.get("current_winner_id"):
                leader_display = generate_anon_name(auc["current_winner_id"])
            else:
                leader_display = "Нет ставок"
            leader = html.escape(leader_display)
            safe_title = html.escape(str(auc['title']))
            safe_desc = html.escape(str(auc['description']))

            lines.append(
                f"🔹 <b>Лот #{auc['id']}: {safe_title}</b>\n"
                f"📝 <i>{safe_desc}</i>\n"
                f"💰 Текущая ставка: <code>{int(auc['current_bid']):,} ₪</code> (Лидер: <b>{leader}</b>)\n"
                f"⚡ Мин. шаг: <code>+{int(auc['min_bid_step']):,} ₪</code> | ⏳ Осталось: <b>{rem_str}</b>\n"
                f"👉 Поставить: <code>/bid {auc['id']} {int(next_min)}</code>\n"
            )

        lines.append("<i>Все победные ставки на 100% сжигаются в Фонд Яхты Абу!</i>")
        out_text = "\n".join(lines)
        if len(out_text) > 3900:
            out_text = out_text[:3850] + "\n\n⚠️ <i>[Список сокращен]</i>"

        kb = build_auction_list_kb(page, total_pages)
        await render_menu_transition(callback, out_text, kb, category="shop", prefer_banner=False)
    finally:
        await safe_callback_answer(callback)


@auction_router.callback_query(F.data == "auc_noop")
async def cb_auc_noop(callback: types.CallbackQuery):
    from common.bot_helpers import safe_callback_answer
    await safe_callback_answer(callback)


@auction_router.message(F.text.regexp(r"^/(bid|auction_bid|ставка)(?:@\w+)?(?:\s|$)", flags=re.IGNORECASE))
async def cmd_bid(message: types.Message):
    """
    Places an atomic bid on an active auction.
    """
    board_id = message.board_id if isinstance(getattr(message, "board_id", None), str) else "b"
    user_id = message.from_user.id
    from common.anon_identity import generate_anon_name
    user_name = generate_anon_name(user_id)
    parts = (message.text or "").split()

    db = await get_pool()

    # Мут-гард
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(user_id, board_id, db=db) or await check_user_is_muted(db, user_id, board_id):
        await message.reply("🔇 Замученным нельзя делать ставки на аукционе.")
        return

    # Самоизоляция
    try:
        async with db.execute("SELECT COALESCE(is_isolated, 0) FROM Users WHERE user_id = ?", (user_id,)) as iso_c:
            iso_row = await iso_c.fetchone()
            if iso_row and iso_row[0]:
                await message.reply("🧘 Вы находитесь в режиме самоизоляции. Ставки на аукционе заблокированы (капитал заморожен).", parse_mode="HTML")
                return
    except Exception:
        pass

    # Розыск 5★
    try:
        from common.bot_helpers import _get_user_active_items
        s_items = await _get_user_active_items(db, user_id, board_id)
        if int(s_items.get("wanted_stars", 0) or 0) >= 5:
            await message.reply(
                "🚨 <b>СЛУЖБА ФИНАНСОВОГО МОНИТОРИНГА АБУ:</b>\n"
                "Вы находитесь в федеральном розыске (5★)! Все аукционные операции заблокированы полицией.\n"
                "Сбросьте розыск через взятку (<code>/bribe_cop</code>) или отсидите срок!",
                parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.warning(f"Error checking wanted status in cmd_bid: {e}")

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
        if math.isnan(bid_amount) or math.isinf(bid_amount) or bid_amount <= 0:
            await message.reply("❌ Ставка должна быть положительным числом!")
            return
    except (ValueError, OverflowError):
        await message.reply("❌ ID аукциона и сумма ставки должны быть числами!")
        return

    db = await get_pool()
    try:
        async with auction_bid_in_flight_guard(user_id):
            res = await place_auction_bid(db, auction_id, user_id, user_name, bid_amount, board_id)
    except AuctionBidInFlightError as err_inflight:
        await message.reply(str(err_inflight))
        return

    if not res.get("ok"):
        err_msg = html.escape(str(res.get('error', 'Неизвестная ошибка')))
        await message.reply(f"❌ <b>Ставка отклонена:</b> {err_msg}", parse_mode="HTML")
        return

    snipe_txt = (
        f"\n\n{format_anti_sniping_notice(300)}"
        if res.get("extended") else ""
    )
    prev_txt = (
        f"\n\n🔄 <b>Авто-возврат депозита:</b> Предыдущему лидеру <b>{generate_anon_name(res.get('previous_winner'))}</b> "
        f"100% заблокированного депозита немедленно и автоматически возвращено на баланс!"
        if res.get("previous_winner") else ""
    )

    # Уведомление предыдущему лидеру о перебитии ставки и 100% эскроу-возврате
    if res.get("previous_winner"):
        prev_winner_id = res["previous_winner"]
        refunded_amt = res.get("previous_bid", 0.0)
        lot_title = res.get("title", f"Лот #{auction_id}")
        outbid_text = format_outbid_notification(
            auction_id=auction_id,
            lot_title=lot_title,
            refunded_amount=refunded_amt,
            new_bid=bid_amount,
            new_leader_name=user_name,
        )
        try:
            await message.bot.send_message(chat_id=prev_winner_id, text=outbid_text, parse_mode="HTML")
        except Exception as e_outbid:
            logger.debug(f"Failed to dispatch outbid notification to {prev_winner_id}: {e_outbid}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main")],
    ])
    await message.reply(
        f"🔨 <b>СТАВКА ПРИНЯТА!</b>\n\n"
        f"Аукцион: <b>#{auction_id}</b>\n"
        f"Твоя ставка: <code>{format_shekels(bid_amount)}</code>\n"
        f"Статус: <b>Лидер аукциона 👑</b>"
        f"{prev_txt}{snipe_txt}",
        reply_markup=kb,
        parse_mode="HTML"
    )


# =============================================================================
# 3. /whale_safe HANDLER
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(whale_safe|whale|сейф_олигарха)(?:@\w+)?(?:\s|$)", flags=re.IGNORECASE))
async def cmd_whale_safe(message: types.Message, board_id: str | None = None, **kwargs):
    """
    Purchases and opens a Whale Safe (Сейф Олигарха).
    """
    board_id = board_id or (message.board_id if isinstance(getattr(message, "board_id", None), str) else "b")
    user_id = message.from_user.id
    db = await get_pool()

    res = await buy_whale_safe(db, user_id, board_id)

    if not res.get("ok"):
        err_msg = html.escape(str(res.get('error', 'Ошибка покупки')))
        await message.reply(f"❌ <b>Покупка отклонена:</b> {err_msg}", parse_mode="HTML")
        return

    rec_str = f"\n\n{res['recycle_note']}" if res.get("recycle_note") else ""
    safe_title = html.escape(str(res.get('title', '')))
    safe_desc = html.escape(str(res.get('desc', '')))
    text = (
        f"🐋 <b>СЕЙФ ОЛИГАРХА ВЗЛОМАН!</b>\n\n"
        f"🌟 <b>Тир:</b> {res['tier']}\n"
        f"🎁 <b>Награда:</b> <b>{safe_title}</b>\n"
        f"📝 <i>{safe_desc}</i>{rec_str}\n\n"
        f"🔥 <i>70% стоимости ({format_shekels(res['burned_to_abu'])}) навсегда сожжено в Фонд Яхты Абу!</i>\n"
        f"Твой новый баланс: <code>{format_shekels(res['new_balance'])}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main")],
    ])
    await message.reply(text, reply_markup=kb, parse_mode="HTML")

    # Рассылка редких дропов на доску и в новостной канал «Тгач Новости»
    tier_upper = str(res.get('tier', '')).upper()
    if "ЛОХ" not in tier_upper and "ТРОЛЛИНГ" not in tier_upper:
        try:
            from event_push_engine import push_whale_drop
            asyncio.create_task(push_whale_drop(
                bot=message.bot,
                board_id=board_id,
                winner_anon_id=get_anon_id(user_id),
                tier_name=res['tier'],
                item_title=res.get('title', 'Сейф Китов'),
                burned_to_abu=res.get('burned_to_abu', 0),
                exclude_uid=user_id,
            ))
        except Exception as e_push:
            logger.debug(f"Whale drop push failed: {e_push}")

        try:
            from news_channel_publisher import publish_whale_safe_rare_drop
            asyncio.create_task(publish_whale_safe_rare_drop(
                bot=message.bot,
                user_id=user_id,
                tier_name=res['tier'],
                item_title=res.get('title', 'Сейф Китов'),
                burned_to_abu=res.get('burned_to_abu', 0),
                desc=res.get('desc', ''),
            ))
        except Exception as e_news:
            logger.debug(f"Whale drop news publish failed: {e_news}")


# =============================================================================
# 4. /raid_oligarch & LOBBY HANDLERS
# =============================================================================

@auction_router.message(F.text.regexp(r"^/(raid_oligarch|раскулачить|raid|рейд)(?:@\w+)?(?:\s|$)", flags=re.IGNORECASE))
async def cmd_raid_oligarch(message: types.Message, board_id: str | None = None, **kwargs):
    """
    Initiates or executes a collaborative proletarian raid against an oligarch.
    """
    board_id = board_id or (message.board_id if isinstance(getattr(message, "board_id", None), str) else "b")
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

        from common.anon_identity import generate_anon_name
        oligarch_name = generate_anon_name(res['target_id'])
        await message.reply(
            f"☭ <b>РАСКУЛАЧИВАНИЕ ОЛИГАРХА {oligarch_name} ЗАВЕРШЕНО!</b>\n\n"
            f"💰 Конфисковано: <b>{res['confiscated']:,.0f} ₪</b> (10% капитала)\n"
            f"🔥 Сожжено в Фонд Яхты Абу (70%): <b>{res['burned_to_abu']:,.0f} ₪</b>\n"
            f"🛠️ Распределено 5 работягам (30%): <b>{res['distributed_total']:,.0f} ₪</b>\n"
            f"💵 Доля каждого участника: <b>+{res['per_voter']:,.0f} ₪</b>\n\n"
            f"<i>«Экспроприация экспроприаторов прошла успешно!»</i>"
        )
        return

    # Check target not self
    if target_id is not None and target_id == user_id:
        await message.reply("❌ Олигарх не может организовать рейд против самого себя!")
        return

    # Proletarian qualification check for initiator
    is_ok, reason = await check_raid_proletarian(db, user_id)
    if not is_ok:
        await message.reply(f"❌ <b>Ты не можешь объявить рейд ОБЭП!</b>\n{reason}", parse_mode="HTML")
        return

    # Check active raid in this chat
    now_ts = time.time()
    async with _raid_lock:
        for r_id, r_info in list(_ACTIVE_RAIDS.items()):
            if r_info.get("chat_id") == message.chat.id and (now_ts - r_info.get("created_at", 0) < 600):
                cnt = len(r_info.get("voters", []))
                await message.reply(f"⚠️ В этом чате уже идет сбор рабочего рейда ОБЭП ({cnt}/5)! Присоединяйся к нему по кнопке выше.")
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

    from common.anon_identity import generate_anon_name
    tgt_str = f"Олигарх: <b>{generate_anon_name(target_id)}</b>" if target_id else "Самый богатый олигарх борды"
    await message.reply(
        f"☭ <b>ОБЪЯВЛЕН НАРОДНЫЙ РЕЙД ОБЭП (/raid_oligarch)!</b>\n\n"
        f"🎯 <b>Цель:</b> {tgt_str}\n"
        f"Требования к работягам: баланс &lt; 5,000 ₪ и &gt;= 25 постов.\n"
        f"Добыча: 10% капитала цели (макс 1,000,000 ₪).\n"
        f"70% сжигается в Фонд Яхты Абу, 30% делится поровну между 5 участниками!\n\n"
        f"Собрано пролетариев: <b>1/5</b>",
        reply_markup=kb
    )

    # Пуш-уведомление о начале рейда активным юзерам доски
    try:
        from event_push_engine import push_raid_oligarch
        from common.anon_identity import get_anon_id
        from common.database import get_user_global_balance as _get_bal
        db_push = await get_pool()
        oligarch_bal = 0
        if target_id:
            oligarch_bal = int(await _get_bal(db_push, target_id))
        oligarch_anon = get_anon_id(target_id) if target_id else "???"
        potential_loot = min(int(oligarch_bal * 0.10 * 0.30), 60000)
        asyncio.create_task(push_raid_oligarch(
            bot=message.bot,
            board_id=board_id,
            oligarch_anon_id=oligarch_anon,
            oligarch_balance=oligarch_bal,
            potential_loot=potential_loot,
            exclude_uid=user_id,
        ))
    except Exception:
        pass


@auction_router.callback_query(F.data.startswith("raid_join_"))
async def cb_raid_join(callback: types.CallbackQuery):
    """
    Handles joining an active raid lobby.
    Thread-safe, resilient against caption/photo cards and detailed feedback.
    Prunes stale lobbies and guards against oligarch self-sabotage and bank deposit evasion.
    """
    from common.bot_helpers import safe_callback_answer
    try:
        raid_id = callback.data.replace("raid_join_", "")
        now_ts = time.time()
        async with _raid_lock:
            # Prune stale raids older than 3600 seconds to prevent unbounded memory growth
            stale_keys = [k for k, v in _ACTIVE_RAIDS.items() if now_ts - v.get("created_at", now_ts) > 3600]
            for k in stale_keys:
                _ACTIVE_RAIDS.pop(k, None)

            raid = _ACTIVE_RAIDS.get(raid_id)
            if not raid:
                await callback.answer("⏳ Рейд уже завершен или истек!", show_alert=True)
                return

            user_id = callback.from_user.id
            if raid.get("target_id") and user_id == raid["target_id"]:
                await callback.answer("❌ Олигарх не может участвовать в рейде против самого себя!", show_alert=True)
                return

            if user_id in raid["voters"]:
                await callback.answer(f"⚠️ Ты уже в строю! Собрано: {len(raid['voters'])}/5", show_alert=True)
                return

        db = await get_pool()
        is_ok, reason = await check_raid_proletarian(db, user_id)
        if not is_ok:
            await callback.answer(f"❌ Ты не подходишь для рейда! {reason}", show_alert=True)
            return

        async with _raid_lock:
            if raid_id not in _ACTIVE_RAIDS:
                await callback.answer("⏳ Рейд уже завершен или истек!", show_alert=True)
                return
            raid = _ACTIVE_RAIDS[raid_id]
            if raid.get("target_id") and user_id == raid["target_id"]:
                await callback.answer("❌ Олигарх не может участвовать в рейде против самого себя!", show_alert=True)
                return
            if user_id in raid["voters"]:
                await callback.answer(f"⚠️ Ты уже в строю! Собрано: {len(raid['voters'])}/5", show_alert=True)
                return
            raid["voters"].append(user_id)
            cnt = len(raid["voters"])
            should_execute = False
            if cnt >= 5:
                _ACTIVE_RAIDS.pop(raid_id, None)
                should_execute = True

        if not should_execute:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🚩 Вступить в рейд ОБЭП ({cnt}/5)", callback_data=f"raid_join_{raid_id}")],
                [
                    InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
                    InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
                ],
            ])
            from common.anon_identity import generate_anon_name
            tgt_str = f"Олигарх: <b>{generate_anon_name(raid['target_id'])}</b>" if raid['target_id'] else "Самый богатый олигарх борды"
            new_text = (
                f"☭ <b>ОБЪЯВЛЕН НАРОДНЫЙ РЕЙД ОБЭП (/raid_oligarch)!</b>\n\n"
                f"🎯 <b>Цель:</b> {tgt_str}\n"
                f"Требования к работягам: баланс &lt; 5,000 ₪ и &gt;= 25 постов.\n"
                f"Добыча: 10% капитала цели (макс 1,000,000 ₪).\n"
                f"70% сжигается в Фонд Яхты Абу, 30% делится поровну между 5 участниками!\n\n"
                f"Собрано пролетариев: <b>{cnt}/5</b>"
            )
            try:
                if callback.message:
                    if callback.message.caption is not None or callback.message.photo:
                        await callback.message.edit_caption(caption=new_text, reply_markup=kb, parse_mode="HTML")
                    else:
                        await callback.message.edit_text(text=new_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                try:
                    if callback.message:
                        await callback.message.edit_reply_markup(reply_markup=kb)
                except Exception:
                    pass

            await callback.answer(f"🚩 Ты вступил в рейд ОБЭП! ({cnt}/5)")
            return

        # 5 voters gathered! Execute raid!
        res = await execute_oligarch_raid(db, raid["voters"], raid["target_id"], raid["board_id"])

        if not res.get("ok"):
            err_msg = html.escape(str(res.get('error', 'Ошибка')))
            fail_text = f"❌ <b>Рейд ОБЭП провален:</b> {err_msg}"
            fail_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
                    InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
                ],
            ])
            try:
                if callback.message:
                    if callback.message.caption is not None or callback.message.photo:
                        await callback.message.edit_caption(caption=fail_text, reply_markup=fail_kb, parse_mode="HTML")
                    else:
                        await callback.message.edit_text(text=fail_text, reply_markup=fail_kb, parse_mode="HTML")
            except Exception:
                pass
            await callback.answer("Рейд провален!", show_alert=True)
            return

        from common.anon_identity import generate_anon_name
        oligarch_name = generate_anon_name(res['target_id'])
        win_text = (
            f"☭ <b>РАСКУЛАЧИВАНИЕ ОЛИГАРХА {oligarch_name} ЗАВЕРШЕНО!</b>\n\n"
            f"💰 Конфисковано: <b>{res['confiscated']:,.0f} ₪</b> (10% капитала)\n"
            f"🔥 Сожжено в Фонд Яхты Абу (70%): <b>{res['burned_to_abu']:,.0f} ₪</b>\n"
            f"🛠️ Распределено 5 работягам (30%): <b>{res['distributed_total']:,.0f} ₪</b>\n"
            f"💵 Доля каждого участника: <b>+{res['per_voter']:,.0f} ₪</b>\n\n"
            f"<i>«Экспроприация экспроприаторов прошла успешно!»</i>"
        )
        win_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад в Банк", callback_data="bank_main_hub"),
                InlineKeyboardButton(text="⚡ Главное меню", callback_data="menu_main"),
            ],
        ])
        try:
            if callback.message:
                if callback.message.caption is not None or callback.message.photo:
                    await callback.message.edit_caption(caption=win_text, reply_markup=win_kb, parse_mode="HTML")
                else:
                    await callback.message.edit_text(text=win_text, reply_markup=win_kb, parse_mode="HTML")
        except Exception:
            pass

        # Уведомление олигарху в ЛС о раскулачивании
        try:
            await callback.bot.send_message(
                res["target_id"],
                f"☭ <b>ТЕБЯ РАСКУЛАЧИЛ РАБОЧИЙ РЕЙД ОБЭП В /{raid['board_id']}/!</b>\n\n"
                f"5 бдительных пролетариев объединились и экспроприировали твой капитал:\n"
                f"💸 Конфисковано: <b>{res['confiscated']:,.0f} ₪</b>\n"
                f"🔥 70% ушло в Фонд Яхты Абу, 30% роздано работягам.\n\n"
                f"<i>Защищайся дипломатическим паспортом или огнетушителем ОБЭП (/shop)!</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

        # Уведомление всем участникам рейда в ЛС
        voter_pm_text = (
            f"☭ <b>РАСКУЛАЧИВАНИЕ ОЛИГАРХА {oligarch_name} ЗАВЕРШЕНО!</b>\n\n"
            f"Ты принял участие в победоносном рейде ОБЭП в /{raid['board_id']}!\n"
            f"💰 Всего конфисковано: <b>{res['confiscated']:,.0f} ₪</b>\n"
            f"💵 Твоя доля перечислена на баланс: <b>+{res['per_voter']:,.0f} ₪</b>\n"
            f"🔥 70% сожжено в Фонд Яхты Абу.\n\n"
            f"<i>«Слава трудовому народу Тгача!»</i>"
        )
        for vid in raid["voters"]:
            if vid != user_id:
                try:
                    await callback.bot.send_message(vid, voter_pm_text, parse_mode="HTML")
                except Exception as e_pm:
                    logger.debug(f"Failed to send raid completion PM to voter {vid}: {e_pm}")

        # Рассылка пуша активным пользователям борды
        try:
            from event_push_engine import push_raid_success
            from common.anon_identity import get_anon_id
            target_anon = get_anon_id(res["target_id"])
            asyncio.create_task(push_raid_success(
                bot=callback.bot,
                board_id=raid["board_id"],
                target_anon_id=target_anon,
                confiscated=res["confiscated"],
                per_voter=res["per_voter"],
            ))
        except Exception as e_push:
            logger.debug(f"Raid success board push failed: {e_push}")

        # Публикация новости о раскулачивании в «Тгач Новости»
        try:
            from news_channel_publisher import publish_oligarch_raid_news
            asyncio.create_task(publish_oligarch_raid_news(
                bot=callback.bot,
                user_id=res["target_id"],
                tax_amount=int(res["confiscated"]),
                old_balance=int(res.get("old_balance", 0)),
                new_balance=int(res.get("new_balance", 0)),
                category="raid_oligarch",
                reason=f"Коллективный рейд 5 пролетариев ОБЭП в /{raid['board_id']}/"
            ))
        except Exception as e_news:
            logger.debug(f"Raid success news publish failed: {e_news}")
        await callback.answer("☭ Рейд успешно завершен!")
    finally:
        await safe_callback_answer(callback)
