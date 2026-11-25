# -*- coding: utf-8 -*-
"""
common/referral_engine.py — Centralized, Secure Referral & Virality UX Engine for ТГАЧ (dvachbot).

Responsibilities:
1. Phonetic alias generation and resolution (via common.anon_identity).
2. Anti-abuse verification:
   - Self-referral prevention (cannot refer oneself).
   - Duplicate prevention (each referred_id can only be claimed once globally in Referrals).
   - Non-new user detection (cannot refer existing active users).
   - Service bot filtering (TELEGRAM_SERVICE_BOT_IDS, user_id <= 0).
3. Financial ledger execution (atomic balance update + UserTransactions + Referrals persistence).
4. One-tap mobile UX formatting (isolated monospace <code> blocks for Telegram tap-to-copy).
5. Realtime DM notifications to referrers with masked anon names (ZERO raw user_id leakage).
6. Telegram native 1-tap sharing links (t.me/share/url).
"""

import logging
import time
import urllib.parse
from typing import Optional, Dict, Any, Tuple

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from common.anon_identity import get_referral_code, generate_anon_name, get_anon_id
from common.html_utils import escape_html
from common.db_pool import get_pool, db_lock, db_transaction
from common.config import SITE_PUBLIC_BASE_URL

logger = logging.getLogger("referral_engine")

# Canonical Financial Constants (15x boosted by user demand)
REFERRAL_REWARD_REFERRER: float = 22320.0  # 1488 * 15
REFERRAL_REWARD_REFEREE: float = 7500.0   # 500 * 15

# Telegram Service Bot IDs that cannot participate
TELEGRAM_SERVICE_BOT_IDS = {777000, 1087968824, 136817688}

# Localized promo snippets for share/copy
VIRAL_SNIPPETS = {
    "ru": "Залетай в анонимный ТГАЧ без цензуры, регистрации и мамкиных вахтёров! Забирай 7,500 ₪ подгон на старт по ссылке:",
    "en": "Crawl into anonymous TGACH — zero censorship, zero jannies, pure chaos. Claim your 7,500 ₪ starter stash here:",
    "jp": "検閲なし・登録なしの匿名掲示板ТГАЧへ来い！リンク踏んで初期資金ボーナスを回収しろ:"
}


async def get_or_create_referral_code(db, user_id: int) -> str:
    """
    Returns the deterministic, phonetic ASCII referral code for user_id.
    Ensures it is registered in ReferralAliases table.
    """
    if not user_id or user_id <= 0:
        return "Anon0"

    ref_code = get_referral_code(user_id)
    try:
        if getattr(db_lock, "is_owned_by_current_task", lambda: False)():
            await db.execute(
                "INSERT OR IGNORE INTO ReferralAliases (code, user_id) VALUES (?, ?)",
                (ref_code, user_id)
            )
        else:
            async with db_lock:
                await db.execute(
                    "INSERT OR IGNORE INTO ReferralAliases (code, user_id) VALUES (?, ?)",
                    (ref_code, user_id)
                )
    except Exception as e:
        logger.warning(f"Failed to ensure ReferralAlias for {user_id}: {e}")
    return ref_code


def build_referral_link(bot_username: str, ref_code: str) -> str:
    """
    Constructs the canonical deep link: https://t.me/<username>?start=ref_<ref_code>
    """
    clean_username = bot_username.lstrip("@").strip()
    return f"https://t.me/{clean_username}?start=ref_{ref_code}"


def build_share_url(ref_link: str, share_text: str) -> str:
    """
    Constructs Telegram native 1-tap share URL (opens chat picker on iOS/Android/Desktop).
    """
    return f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"


async def resolve_referral_code(db, code_or_payload: str) -> Optional[int]:
    """
    Resolves a start payload or referral code to the referrer's user_id.
    Handles 'ref_Sholter5', 'ref-Sholter5', 'Sholter5', and legacy numeric strings.
    """
    if not code_or_payload:
        return None

    raw = str(code_or_payload).strip()
    # Strip common prefixes
    for prefix in ("ref_", "ref-", "r_"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):].strip()
            break

    if not raw:
        return None

    # Check ReferralAliases table
    try:
        if getattr(db_lock, "is_owned_by_current_task", lambda: False)():
            async with db.execute("SELECT user_id FROM ReferralAliases WHERE code = ? COLLATE NOCASE LIMIT 1", (raw,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
        else:
            async with db_lock:
                async with db.execute("SELECT user_id FROM ReferralAliases WHERE code = ? COLLATE NOCASE LIMIT 1", (raw,)) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0] is not None:
                        return int(row[0])
    except Exception as e:
        logger.warning(f"Error querying ReferralAliases: {e}")

    # Legacy numeric fallback (if >= 7 digits)
    if raw.isdigit() and len(raw) >= 7:
        return int(raw)

    return None


async def get_referral_stats(db, user_id: int) -> Dict[str, Any]:
    """
    Fetches referral statistics for user_id.
    """
    stats = {
        "referrals_count": 0,
        "total_earned": 0.0,
        "recent_referrals": []
    }
    if not user_id or user_id <= 0:
        return stats

    try:
        # Check Users table count
        async with db.execute("SELECT COALESCE(SUM(referrals_count), 0) FROM Users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                stats["referrals_count"] = int(row[0])

        # Check Referrals table count if table exists
        async with db.execute(
            "SELECT COUNT(*), COALESCE(SUM(reward_amount), 0) FROM Referrals WHERE referrer_id = ? AND status = 'active'",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                ref_table_count = int(row[0] or 0)
                ref_table_earned = float(row[1] or 0.0)
                # Take maximum of counter or table rows to handle legacy and new records
                stats["referrals_count"] = max(stats["referrals_count"], ref_table_count)
                stats["total_earned"] = max(ref_table_earned, stats["referrals_count"] * REFERRAL_REWARD_REFERRER)
            else:
                stats["total_earned"] = stats["referrals_count"] * REFERRAL_REWARD_REFERRER
    except Exception as e:
        logger.debug(f"get_referral_stats fallback: {e}")
        stats["total_earned"] = stats["referrals_count"] * REFERRAL_REWARD_REFERRER

    return stats


def format_referral_dashboard_message(
    user_id: int,
    bot_username: str,
    ref_code: str,
    stats: Dict[str, Any],
    board_id: str = "b",
    stream: str = "ru"
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Generates high-virality, mobile-optimized referral message and keyboard.
    CRITICAL: The referral link and code are wrapped in isolated <code>...</code> blocks
    so users on Telegram mobile can copy them in exactly one tap.
    """
    ref_link = build_referral_link(bot_username, ref_code)
    referrals_count = stats.get("referrals_count", 0)
    earned = stats.get("total_earned", referrals_count * REFERRAL_REWARD_REFERRER)
    site_url = f"{SITE_PUBLIC_BASE_URL.rstrip('/')}/{board_id}/"

    snippet = VIRAL_SNIPPETS.get(stream, VIRAL_SNIPPETS["ru"])
    share_text = f"{snippet}\n{ref_link}"
    share_url = build_share_url(ref_link, snippet)

    if stream in ("en", "int"):
        text = (
            "🤝 <b>TGACH REFERRAL SYSTEM</b>\n\n"
            f"Drag fellow degenerates in here and pocket <b>+{int(REFERRAL_REWARD_REFERRER):,} ₪</b> per fresh meat!\n"
            f"Your recruit also gets a <b>+{int(REFERRAL_REWARD_REFEREE):,} ₪</b> starter stash so they don't starve.\n\n"
            "🔗 <b>Your Invite Link (tap to copy):</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "🏷 <b>Your Referral Code (tap to copy):</b>\n"
            f"<code>ref_{ref_code}</code>\n\n"
            "📊 <b>Your Catch:</b>\n"
            f"• Anons recruited: <b>{referrals_count}</b>\n"
            f"• Shekels farmed: <b>{int(earned):,} ₪</b>\n\n"
            "💬 <b>Ready-to-paste bait for chats (tap to copy):</b>\n"
            f"<code>{escape_html(snippet)}\n{ref_link}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share with Friend", url=share_url)],
            [
                InlineKeyboardButton(text="🖼 Card with QR", callback_data=f"gen_invite_pic:{board_id}"),
                InlineKeyboardButton(text="🌐 Web Version", url=site_url)
            ]
        ])
    elif stream == "jp":
        text = (
            "🤝 <b>ТГАЧ 紹介（リファラル）システム</b>\n\n"
            f"知り合いの陰キャを引きずり込んで1人あたり <b>+{int(REFERRAL_REWARD_REFERRER):,} ₪</b> を回収しろ！\n"
            f"釣られた新参にも初期資金 <b>+{int(REFERRAL_REWARD_REFEREE):,} ₪</b> が支給される。\n\n"
            "🔗 <b>あなたの招待リンク（タップでコピー）:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "🏷 <b>招待コード（タップでコピー）:</b>\n"
            f"<code>ref_{ref_code}</code>\n\n"
            "📊 <b>あなたの統計:</b>\n"
            f"• 招待した人数: <b>{referrals_count} 人</b>\n"
            f"• 獲得シェケル: <b>{int(earned):,} ₪</b>\n\n"
            "💬 <b>送信テキスト（タップでコピー）:</b>\n"
            f"<code>{escape_html(snippet)}\n{ref_link}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 友達に共有", url=share_url)],
            [
                InlineKeyboardButton(text="🖼 QRカード作成", callback_data=f"gen_invite_pic:{board_id}"),
                InlineKeyboardButton(text="🌐 ウェブ版", url=site_url)
            ]
        ])
    else:
        text = (
            "🤝 <b>РЕФЕРАЛЬНАЯ СИСТЕМА ТГАЧА</b>\n\n"
            f"Тащи сюда знакомых сычей и лутай <b>+{int(REFERRAL_REWARD_REFERRER):,} ₪</b> за каждого свежего ньюфага!\n"
            f"Приведённый битард тоже не с голой жопой останется — получит <b>+{int(REFERRAL_REWARD_REFEREE):,} ₪</b> на доширак и ставки.\n\n"
            "🔗 <b>Твоя ссылка-приманка (тапни, чтобы скопировать):</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "🏷 <b>Твой реф-код (тапни, чтобы скопировать):</b>\n"
            f"<code>ref_{ref_code}</code>\n\n"
            "📊 <b>Улов по рефералке:</b>\n"
            f"• Завербовано анонов: <b>{referrals_count}</b>\n"
            f"• Срублено шекелей: <b>{int(earned):,} ₪</b>\n\n"
            "💬 <b>Готовый зазыв для конф (тапни, чтобы скопировать):</b>\n"
            f"<code>{escape_html(snippet)}\n{ref_link}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить другу", url=share_url)],
            [
                InlineKeyboardButton(text="🖼 Картинка с QR", callback_data=f"gen_invite_pic:{board_id}"),
                InlineKeyboardButton(text="🌐 Веб-версия", url=site_url)
            ]
        ])

    return text, kb


async def process_referral_activation(
    db,
    bot,
    referred_id: int,
    referrer_id: int,
    board_id: str = "b",
    stream: str = "ru"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes atomic anti-abuse validation and reward distribution.
    Returns: (success: bool, reason: str, details: dict)
    """
    # 1. Basic validation
    if not referred_id or referred_id <= 0 or referred_id in TELEGRAM_SERVICE_BOT_IDS:
        return False, "invalid_referee", {}
    if not referrer_id or referrer_id <= 0 or referrer_id in TELEGRAM_SERVICE_BOT_IDS:
        return False, "invalid_referrer", {}

    # 2. Self-referral prevention
    if referred_id == referrer_id:
        return False, "self_referral", {}

    async with db_lock:
        # 3. Check duplicate in Referrals table
        try:
            async with db.execute("SELECT 1 FROM Referrals WHERE referred_id = ? LIMIT 1", (referred_id,)) as c:
                if await c.fetchone():
                    return False, "already_referred", {}
        except Exception:
            pass

        # 4. Check if user already exists globally with prior posts/balance
        async with db.execute(
            "SELECT posts_count, balance FROM Users WHERE user_id = ? LIMIT 1",
            (referred_id,)
        ) as c:
            existing = await c.fetchone()
            if existing:
                posts_count, bal = existing[0] or 0, existing[1] or 0.0
                if posts_count > 0 or bal > 0:
                    return False, "not_new_user", {}

        now_ts = time.time()
        now_int = int(now_ts)
        referee_anon = get_anon_id(referred_id, stream="ru")
        referrer_anon = get_anon_id(referrer_id, stream="ru")

        # 5. Atomic state update
        async with db_transaction(db):
            # A. Record in Referrals table
            await db.execute("""
                INSERT OR IGNORE INTO Referrals (referrer_id, referred_id, board_id, reward_amount, created_at, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            """, (referrer_id, referred_id, board_id, REFERRAL_REWARD_REFERRER, now_ts))

            # B. Credit Referrer (1488 ₪)
            await db.execute("""
                INSERT INTO Users (user_id, board_id, balance, referrals_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, board_id) DO UPDATE SET
                balance = balance + ?,
                referrals_count = referrals_count + 1
            """, (referrer_id, board_id, REFERRAL_REWARD_REFERRER, REFERRAL_REWARD_REFERRER))

            # C. Credit Referee welcome bonus (500 ₪)
            await db.execute("""
                INSERT INTO Users (user_id, board_id, balance)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, board_id) DO UPDATE SET
                balance = balance + ?
            """, (referred_id, board_id, REFERRAL_REWARD_REFEREE, REFERRAL_REWARD_REFEREE))

            # D. Record UserTransactions for audit trail
            await db.execute("""
                INSERT INTO UserTransactions (user_id, amount, category, description, timestamp)
                VALUES (?, ?, 'referral', ?, ?)
            """, (referrer_id, REFERRAL_REWARD_REFERRER, f"Реферальный бонус за Анон [{referee_anon}]", now_int))

            await db.execute("""
                INSERT INTO UserTransactions (user_id, amount, category, description, timestamp)
                VALUES (?, ?, 'referral_welcome', ?, ?)
            """, (referred_id, REFERRAL_REWARD_REFEREE, f"Приветственный бонус от Анон [{referrer_anon}]", now_int))

            # Get new referrer total balance
            async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (referrer_id,)) as c_sum:
                sum_row = await c_sum.fetchone()
                new_ref_balance = float(sum_row[0] or REFERRAL_REWARD_REFERRER)

    # 6. Realtime Notification in PM to the Referrer (with masked anon names — ZERO raw user_id)
    if bot:
        try:
            masked_referee_name = generate_anon_name(referred_id, stream=stream)
            if stream in ("en", "int"):
                notif_msg = (
                    "🤝 <b>NEW REFERRAL IN TGACH!</b>\n\n"
                    f"Fresh meat <b>{escape_html(masked_referee_name)}</b> just crawled in using your link!\n"
                    f"💰 Recruitment cut: <b>+{REFERRAL_REWARD_REFERRER:,.2f} ₪</b>\n"
                    f"💳 Your balance: <code>{new_ref_balance:,.2f} ₪</code>\n\n"
                    "<i>Drag more lurkers in via /ref — Abu pays for fresh bodies!</i>"
                )
            elif stream == "jp":
                notif_msg = (
                    "🤝 <b>新しい紹介（リファラル）！</b>\n\n"
                    f"お前のリンクから新参 <b>{escape_html(masked_referee_name)}</b> が釣れたぞ！\n"
                    f"💰 獲得ボーナス: <b>+{REFERRAL_REWARD_REFERRER:,.2f} ₪</b>\n"
                    f"💳 現在の残高: <code>{new_ref_balance:,.2f} ₪</code>"
                )
            else:
                notif_msg = (
                    "🤝 <b>НОВЫЙ РЕФЕРАЛ В ТГАЧ!</b>\n\n"
                    f"По твоей наводке на доску вкатился <b>{escape_html(masked_referee_name)}</b>!\n"
                    f"💰 Капнуло за вербовку: <b>+{REFERRAL_REWARD_REFERRER:,.2f} ₪</b>\n"
                    f"💳 Твой баланс: <code>{new_ref_balance:,.2f} ₪</code>\n\n"
                    "<i>Тащи ещё сычей через /ref — Абу щедро платит за свежее мясо!</i>"
                )
            await bot.send_message(referrer_id, notif_msg, parse_mode="HTML")
            logger.info(f"Referral notification sent to {referrer_id} for new referee {referred_id}")
        except Exception as e:
            logger.warning(f"Could not send PM notification to referrer {referrer_id}: {e}")

    return True, "success", {
        "referrer_reward": REFERRAL_REWARD_REFERRER,
        "referee_reward": REFERRAL_REWARD_REFEREE,
        "new_balance": new_ref_balance
    }


async def process_start_referral(
    db,
    bot,
    user_id: int,
    text_payload: str,
    board_id: str = "b",
    stream: str = "ru"
) -> bool:
    """
    Parses /start parameter and processes referral if applicable.
    Called on /start command in main.py.
    """
    if not text_payload:
        return False

    parts = text_payload.strip().split()
    if len(parts) <= 1:
        return False

    raw_token = parts[1].strip()
    # Support ref_Token, ref-Token, or direct token
    if not (raw_token.startswith("ref_") or raw_token.startswith("ref-") or len(raw_token) >= 4):
        return False

    referrer_id = await resolve_referral_code(db, raw_token)
    if not referrer_id:
        logger.debug(f"Could not resolve referral code from token: {raw_token}")
        return False

    success, reason, _ = await process_referral_activation(
        db=db,
        bot=bot,
        referred_id=user_id,
        referrer_id=referrer_id,
        board_id=board_id,
        stream=stream
    )
    if success:
        logger.info(f"Successfully processed referral: referrer={referrer_id}, referee={user_id}")
        return True
    else:
        logger.debug(f"Referral activation rejected: {reason}")
        return False


async def handle_referral_command(
    message: types.Message,
    board_id: Optional[str] = "b",
    stream: str = "ru"
) -> None:
    """
    Unified command handler for /ref, /invite, /referral.
    Renders high-virality dashboard with 1-tap copy links and statistics.
    """
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    target_board = board_id or "b"
    bot_username = "dvach_chatbot"
    try:
        me = await message.bot.get_me()
        if me and me.username:
            bot_username = me.username
    except Exception as e:
        logger.debug(f"Could not get bot username: {e}")

    db = await get_pool()
    ref_code = await get_or_create_referral_code(db, user_id)
    stats = await get_referral_stats(db, user_id)

    text, kb = format_referral_dashboard_message(
        user_id=user_id,
        bot_username=bot_username,
        ref_code=ref_code,
        stats=stats,
        board_id=target_board,
        stream=stream
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    try:
        await message.delete()
    except Exception:
        pass
