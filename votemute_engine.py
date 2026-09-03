# -*- coding: utf-8 -*-
"""
votemute_engine.py — Democratic Vote-Mute Engine (Народный Вотум / Шизо-Мут) for ТГАЧ
===================================================================================
Allows community to vote-mute toxic spammers/waifu-wipers via 5 unique votes within 10 minutes.
Once passed, applies an UNBRIBABLE 30-minute iron mute that CANNOT be removed via shop bribes or regular un-mutes.

Key Features:
1. Command /votemute (or /вотум, /шизомут) as a reply to a post or by post number.
2. Interactive voting card with inline button '⚖️ Замутить шиза [1/5]' (5 unique anons within 10 minutes).
3. Upon reaching 5 votes — applies 30-minute IRON FOLK MUTE (ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ).
4. UNBRIBABLE FLAG (unbribable_votemute_until) — blocks bribes in /shop and admin unmutes.
5. Juicy public verdict broadcast to the whole board via process_new_post.
6. Full aiogram 3.x Router and menu integration helpers.
"""

import time
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any, Set, Union

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from common.db_pool import get_pool, db_lock, db_transaction
from common.anon_identity import get_anon_id

logger = logging.getLogger("runtime")

VOTES_REQUIRED = 5
VOTE_WINDOW_SEC = 600.0  # 10 minutes voting window
MUTE_DURATION_SEC = 1800  # 30 minutes iron mute
UNBRIBABLE_FLAG_KEY = "unbribable_votemute_until"

UNBRIBABLE_MUTE_ERROR_TEXT = (
    "❌ <b>Этот мут наложен народом борды и не продается за взятки!</b>\n"
    "🔒 Воля анонов несокрушима. До окончания срока осталось <b>{minutes} мин.</b>"
)

active_votemutes: Dict[str, Dict[str, Any]] = {}
votemute_lock = asyncio.Lock()

votemute_router = Router(name="votemute_router")


def generate_votemute_key(target_id: int, post_num: int) -> str:
    """Internal memory key for dedup — uses IDs, never exposed to Telegram."""
    return f"vm_{target_id}_{post_num}"


def get_votemute_callback_token(target_id: int, post_num: int) -> str:
    """
    Safe opaque token for InlineKeyboardButton callback_data.
    Uses existing anon_id hash (e.g. 'Шолтер5') — deterministic, no raw ID exposed,
    survives bot restarts since get_anon_id is keyed on a fixed secret salt.
    Format: '<anon_tag>_<post_num>'
    """
    return f"{get_anon_id(target_id)}_{post_num}"


def resolve_votemute_token(token: str) -> Optional[Tuple[int, int]]:
    """
    Resolves callback token '<anon_tag>_<post_num>' back to (target_id, post_num)
    by scanning active_votemutes for a matching entry.
    Returns None if not found or session expired.
    """
    # Token format: '<anon_tag>_<post_num>'  e.g. 'Шолтер5_12345'
    try:
        # Split from right once to get post_num
        last_sep = token.rfind("_")
        if last_sep == -1:
            return None
        anon_tag = token[:last_sep]
        post_num = int(token[last_sep + 1:])
    except (ValueError, IndexError):
        return None

    for vm in active_votemutes.values():
        t_id = vm.get("target_id")
        p_num = vm.get("post_num")
        if p_num == post_num and t_id and get_anon_id(t_id) == anon_tag:
            return t_id, post_num
    return None



def clean_expired_votemutes():
    """Removes unexecuted votemute sessions older than VOTE_WINDOW_SEC from memory."""
    now = time.time()
    expired_keys = [
        k for k, vm in active_votemutes.items()
        if (now - vm.get("created_ts", 0)) > VOTE_WINDOW_SEC and not vm.get("executed", False)
    ]
    for k in expired_keys:
        active_votemutes.pop(k, None)


def get_votemute_status(target_id: int, post_num: int) -> Optional[Dict[str, Any]]:
    """Returns current active votemute state dictionary if present."""
    vm_key = generate_votemute_key(target_id, post_num)
    return active_votemutes.get(vm_key)


def get_votemute_keyboard(target_id: int, post_num: int, votes_count: int, is_executed: bool = False) -> InlineKeyboardMarkup:
    """Builds inline keyboard for active or completed votemute. callback_data uses opaque token only."""
    token = get_votemute_callback_token(target_id, post_num)
    if is_executed or votes_count >= VOTES_REQUIRED:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔒 ЗАМУЧЕН НАРОДОМ (30 мин)",
                    callback_data=f"vm_info:{token}"
                )
            ]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⚖️ Замутить шиза [{votes_count}/{VOTES_REQUIRED}]",
                callback_data=f"vm_vote:{token}"
            )
        ]
    ])


def get_votemute_card_text(post_num: int, target_id: int, votes_count: int, created_ts: float, is_executed: bool = False) -> str:
    """Formats HTML text for the votemute message card."""
    now = time.time()
    time_left_sec = max(0, int(VOTE_WINDOW_SEC - (now - created_ts)))
    time_left_min = (time_left_sec + 59) // 60

    anon_tag = get_anon_id(target_id) if target_id else "???"
    if is_executed or votes_count >= VOTES_REQUIRED:
        return (
            f"⚖️ <b>НАРОДНЫЙ ВОТУМ ЗАВЕРШЕН!</b>\n\n"
            f"🎯 <b>Пост:</b> #{post_num}\n"
            f"🤐 <b>Нарушитель:</b> <code>[ID:{anon_tag}]</code>\n"
            f"📊 <b>Итог:</b> Собрано {VOTES_REQUIRED}/{VOTES_REQUIRED} голосов анонов!\n\n"
            f"🔒 <b>Приговор:</b> <b>ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ на 30 минут</b>.\n"
            f"<i>Этот мут не снимается взятками в /shop и защищен от помилований.</i>"
        )

    return (
        f"🗳️ <b>НАРОДНЫЙ ВОТУМ НЕДОВЕРИЯ / ШИЗО-МУТ</b>\n\n"
        f"🎯 <b>Выдвинут пост:</b> #{post_num}\n"
        f"👤 <b>Автор поста:</b> <code>[ID:{anon_tag}]</code>\n"
        f"📊 <b>Проголосовало:</b> <b>{votes_count}/{VOTES_REQUIRED}</b> анонов\n"
        f"⏳ <b>Осталось времени:</b> ~{time_left_min} мин.\n\n"
        f"<i>Нажми кнопку ниже, если считаешь, что автор — злостный шиз/вайпер. "
        f"При наборе 5 голосов на него наложится ЖЕЛЕЗНЫЙ МУТ на 30 минут, который нельзя снять за взятки!</i>"
    )


async def broadcast_votemute_announcement(bot, board_id: str, text: str, reply_to_post: Optional[int] = None):
    """
    Broadcasts public announcement to the whole board via process_new_post.
    """
    try:
        from post_processor import process_new_post
        import shared_state
        params = shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content={'type': 'text', 'text': text, 'is_system_message': True},
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        logger.error(f"Error broadcasting votemute announcement: {e}", exc_info=True)


def is_user_under_unbribable_mute(active_items: Optional[Union[dict, str]]) -> bool:
    """
    Checks if target user active_items contains an unexpired unbribable_votemute_until timestamp.
    """
    if not active_items:
        return False
    if isinstance(active_items, str):
        try:
            active_items = json.loads(active_items)
        except Exception:
            return False
    if not isinstance(active_items, dict):
        return False
    now = int(time.time())
    unbribable_until = active_items.get(UNBRIBABLE_FLAG_KEY, 0)
    return int(unbribable_until) > now


async def check_user_unbribable_mute(user_id: int, board_id: str) -> Tuple[bool, int]:
    """
    Asynchronously checks if user is currently restricted by unbribable folk mute in DB.
    Returns: (is_muted: bool, remaining_seconds: int)
    """
    now = int(time.time())
    try:
        db = await get_pool()
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
            (user_id, board_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    items = json.loads(row[0])
                    until = int(items.get(UNBRIBABLE_FLAG_KEY, 0))
                    if until > now:
                        return True, until - now
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error checking unbribable mute in DB for user {user_id}: {e}")
    return False, 0


async def start_or_add_vote(
    board_id: str,
    target_id: int,
    post_num: int,
    voter_id: int,
    bot=None
) -> Tuple[bool, str, int, bool]:
    """
    Starts a new votemute session or casts a vote in an existing one.
    Returns: (ok: bool, message: str, current_votes: int, is_executed: bool)
    """
    if not post_num or post_num <= 0:
        return False, "❌ Некорректный номер поста.", 0, False

    if not target_id or target_id <= 0:
        return False, "❌ Нельзя объявить вотум системному аккаунту.", 0, False

    if voter_id == target_id:
        return False, "❌ Нельзя голосовать за мут самого себя, шизик.", 0, False

    vm_key = generate_votemute_key(target_id, post_num)
    now = time.time()

    async with votemute_lock:
        # Check if already under active unbribable iron mute
        is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
        if is_unbribable:
            rem_min = max(1, (remaining_sec + 59) // 60)
            return False, f"⚠️ Этот анон уже отбывает Народный Мут! Осталось: {rem_min} мин.", VOTES_REQUIRED, True

        vm = active_votemutes.get(vm_key)
        if not vm:
            vm = {
                "key": vm_key,
                "board_id": board_id,
                "target_id": target_id,
                "post_num": post_num,
                "created_ts": now,
                "voters": {voter_id},
                "executed": False
            }
            active_votemutes[vm_key] = vm
            current_votes = 1
        else:
            if vm["executed"]:
                return False, "⚖️ Приговор по этому посту уже вынесен и приведен в исполнение!", len(vm["voters"]), True

            if now - vm["created_ts"] > VOTE_WINDOW_SEC:
                # Expired -> reset
                active_votemutes.pop(vm_key, None)
                vm = {
                    "key": vm_key,
                    "board_id": board_id,
                    "target_id": target_id,
                    "post_num": post_num,
                    "created_ts": now,
                    "voters": {voter_id},
                    "executed": False
                }
                active_votemutes[vm_key] = vm
                current_votes = 1
            else:
                if voter_id in vm["voters"]:
                    return False, f"⚠️ Ты уже отдал свой голос! Текущий сбор: [{len(vm['voters'])}/{VOTES_REQUIRED}]", len(vm["voters"]), False

                vm["voters"].add(voter_id)
                current_votes = len(vm["voters"])

        if current_votes >= VOTES_REQUIRED and not vm["executed"]:
            vm["executed"] = True
            asyncio.create_task(_apply_unbribable_iron_mute(board_id, target_id, post_num, bot))
            return True, "⚖️ ГОЛОС ПРИНЯТ! ПОРОГ ДОСТИГНУТ: ШИЗ ОТПРАВЛЯЕТСЯ В ЖЕЛЕЗНЫЙ МУТ НА 30 МИНУТ!", current_votes, True

    return True, f"⚖️ Твой голос учтен! Собрано: [{current_votes}/{VOTES_REQUIRED}]", current_votes, False


async def _apply_unbribable_iron_mute(board_id: str, target_id: int, post_num: int, bot=None):
    """
    Applies the unbribable 30-minute iron folk mute in DB, in-memory state, and broadcasts verdict.
    """
    now = int(time.time())
    mute_until = now + MUTE_DURATION_SEC

    # 1. Update SQLite database
    db = await get_pool()
    try:
        async with db_transaction(db):
            # Update user's active_items with unbribable_votemute_until and cursed_until
            await db.execute(
                """
                UPDATE Users 
                SET cursed_until = ?, 
                    active_items = json_set(COALESCE(NULLIF(active_items, ''), '{}'), '$.unbribable_votemute_until', ?) 
                WHERE user_id = ? AND board_id = ?
                """,
                (mute_until, mute_until, target_id, board_id)
            )
            # Insert / update Mutes table
            await db.execute(
                "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                (target_id, board_id)
            )
            await db.execute(
                "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, 'mute', ?)",
                (target_id, board_id, float(mute_until))
            )
    except Exception as e:
        logger.error(f"Error persisting unbribable mute for user {target_id}: {e}", exc_info=True)

    # 2. Update in-memory state
    try:
        import shared_state
        b_data = shared_state.board_data.get(board_id)
        if b_data is not None:
            b_data.setdefault('mutes', {})[target_id] = datetime.now(timezone.utc) + timedelta(seconds=MUTE_DURATION_SEC)
    except Exception as e:
        logger.error(f"Error updating in-memory mutes for user {target_id}: {e}")

    # 3. Publish public verdict across the board
    target_anon = get_anon_id(target_id) if target_id else "???"
    announcement = (
        f"⚖️ <b>НАРОДНЫЙ ПРИГОВОР ВЫНЕСЕН И ПРИВЕДЕН В ИСПОЛНЕНИЕ!</b>\n\n"
        f"👨‍⚖️ По итогам Народного Вотума недоверия (5 голосов анонов) за пост <b>#{post_num}</b>:\n"
        f"🤐 <b>Анон <code>[ID:{target_anon}]</code></b> признан злостным шизо-вайпером и отправлен в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>!\n\n"
        f"🔒 <i>Этот мут наложен волей народа борды: его НЕ СНЯТЬ взятками в /shop и админскими указами!</i>"
    )

    if bot:
        asyncio.create_task(broadcast_votemute_announcement(bot, board_id, announcement, reply_to_post=post_num))


# ============================================================================
# AIOGRAM ROUTER & HANDLERS
# ============================================================================

async def _resolve_target_from_message(message: types.Message) -> Tuple[Optional[int], Optional[int]]:
    """
    Resolves (target_post_num, target_author_id) from reply or arguments.
    """
    post_num = None
    target_id = None

    if message.reply_to_message:
        target_chat_id = message.reply_to_message.chat.id
        reply_mid = message.reply_to_message.message_id
        
        # 1. Try memory
        try:
            import shared_state
            async with shared_state.storage_lock:
                lookup_key = (target_chat_id, reply_mid)
                post_num = shared_state.message_to_post.get(lookup_key)
                if post_num and post_num in shared_state.messages_storage:
                    target_id = shared_state.messages_storage[post_num].get("author_id")
        except Exception:
            pass

        # 2. Try DB copy lookup
        if not post_num or not target_id:
            try:
                from common.database import get_post_info_by_copy
                info = await get_post_info_by_copy(target_chat_id, reply_mid)
                if info:
                    post_num, target_id = info
            except Exception:
                pass

        # 3. Try get post by num from DB if author missing
        if post_num and not target_id:
            try:
                from common.database import get_post_by_num
                db_p = await get_post_by_num(post_num)
                if db_p:
                    target_id = db_p.get("author_id")
            except Exception:
                pass

    # 4. Check explicit post_num argument: /votemute 12345
    if not post_num:
        parts = (message.text or message.caption or "").split()
        if len(parts) >= 2 and parts[1].isdigit():
            post_num = int(parts[1])
            try:
                from common.database import get_post_by_num
                db_p = await get_post_by_num(post_num)
                if db_p:
                    target_id = db_p.get("author_id")
            except Exception:
                pass

    return post_num, target_id


@votemute_router.message(Command("votemute", "вотум", "шизомут", "vm"))
async def cmd_votemute(message: types.Message, board_id: Optional[str] = None):
    """
    Handles /votemute command.
    """
    if not board_id:
        board_id = "b"

    voter_id = message.from_user.id
    post_num, target_id = await _resolve_target_from_message(message)

    if not post_num or not target_id:
        await message.answer(
            "⚠️ <b>Как использовать Народный Вотум (/votemute):</b>\n\n"
            "1. Ответь командой <code>/votemute</code> на пост нарушителя (реплаем).\n"
            "2. Или напиши <code>/votemute &lt;номер_поста&gt;</code>.\n\n"
            "⚖️ При сборе <b>5 голосов анонов за 10 минут</b> нарушитель отправляется в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b> "
            "(не продается за взятки в /shop!).",
            parse_mode="HTML"
        )
        return

    if voter_id == target_id:
        await message.answer("❌ Ты не можешь запустить вотум недоверия против самого себя, шизик.", parse_mode="HTML")
        return

    if target_id <= 0:
        await message.answer("❌ Нельзя объявить вотум системному сообщению.", parse_mode="HTML")
        return

    # Check if already in unbribable mute
    is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
    if is_unbribable:
        rem_min = max(1, (remaining_sec + 59) // 60)
        await message.answer(
            f"🔒 <b>Анон <code>[ID:{get_anon_id(target_id)}]</code> уже отбывает Железный Народный Мут!</b>\n"
            f"Осталось сидеть: ~<b>{rem_min} мин.</b> Повторный вотум не требуется.",
            parse_mode="HTML"
        )
        return

    # Cast initial vote
    ok, msg, current_votes, is_executed = await start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=voter_id,
        bot=message.bot
    )

    card_text = get_votemute_card_text(
        post_num=post_num,
        target_id=target_id,
        votes_count=current_votes,
        created_ts=time.time(),
        is_executed=is_executed
    )
    keyboard = get_votemute_keyboard(target_id, post_num, current_votes, is_executed)

    await message.answer(card_text, reply_markup=keyboard, parse_mode="HTML")


@votemute_router.callback_query(F.data.startswith("vm_vote:"))
async def callback_votemute_vote(callback: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Handles button click '⚖️ Замутить шиза [x/5]'.
    """
    if not board_id:
        board_id = "b"

    voter_id = callback.from_user.id
    token = callback.data.split(":", 1)[1]

    # Resolve opaque token -> (target_id, post_num)
    ids = resolve_votemute_token(token)
    if not ids:
        await callback.answer("⏳ Срок действия этого голосования истек.", show_alert=True)
        return
    target_id, post_num = ids

    # Get board_id from in-memory state if available
    vm_key = generate_votemute_key(target_id, post_num)
    async with votemute_lock:
        vm = active_votemutes.get(vm_key)
        if vm:
            board_id = vm.get("board_id", board_id)

    ok, msg, current_votes, is_executed = await start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=voter_id,
        bot=callback.bot
    )

    await callback.answer(msg, show_alert=not ok or is_executed)

    # Refresh message card UI
    async with votemute_lock:
        vm_data = active_votemutes.get(vm_key, {})
        created_ts = vm_data.get("created_ts", time.time())
        executed = vm_data.get("executed", is_executed)

    new_text = get_votemute_card_text(post_num, target_id, current_votes, created_ts, executed)
    new_kb = get_votemute_keyboard(target_id, post_num, current_votes, executed)

    try:
        await callback.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    except Exception as e:
        logger.error(f"Error updating votemute message card: {e}")


@votemute_router.callback_query(F.data.startswith("vm_info:"))
async def callback_votemute_info(callback: types.CallbackQuery):
    """
    Handles click on completed mute info button.
    """
    await callback.answer(
        "🔒 Этот шиз уже отправлен в ЖЕЛЕЗНЫЙ МУТ на 30 минут решением народного вотума!",
        show_alert=True
    )


@votemute_router.callback_query(F.data == "menu_votemute")
async def callback_menu_votemute(callback: types.CallbackQuery):
    """
    Displays quick info about votemute in menu.
    """
    info_text = (
        "🗳️ <b>НАРОДНЫЙ ВОТУМ / ШИЗО-МУТ (/votemute)</b>\n\n"
        "Демократический инструмент саморегуляции борды:\n"
        "• Ответь <code>/votemute</code> на пост любого вайпера или токсичного шиза.\n"
        "• Если <b>5 уникальных анонов</b> нажмут кнопку голосования в течение 10 минут — нарушитель получит "
        "<b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>.\n"
        "• 🚫 <b>Особенность:</b> Этот мут НЕЛЬЗЯ снять за шекели через /shop (взятки заблокированы) и админские команды!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_help")]
    ])
    try:
        await callback.message.edit_text(info_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.answer()
