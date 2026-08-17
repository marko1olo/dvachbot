from common.config import BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE, BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE, BOT_PRIORITY_PASSIVE_SLICE_SIZE, BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE, BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC

import shared_state
from shared_state import *
from common.database import (
    upsert_delivery_queue_item, delete_delivery_queue_item, get_post_copies, 
    create_post, update_post_content, get_stream_active_users,
    get_and_clear_broadcast_queue, mark_broadcast_posts_sent
)
from common.board_config import BOARD_CONFIG
from post_helpers import format_header
from common.thread_manager import get_threads_data
from thread_texts import thread_messages
from common.bot_helpers import process_new_post
from datetime import timezone, datetime, timedelta
import __main__ as main
UTC = timezone.utc

PRIORITY_PASSIVE_MEDIA_SLICE_SIZE = max(10, BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE)

PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE = max(10, int(BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE))

PRIORITY_PASSIVE_SLICE_SIZE = max(10, BOT_PRIORITY_PASSIVE_SLICE_SIZE)

PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE = max(10, int(BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE))

PRIORITY_PRESSURE_SLICE_AGE_SEC = max(0.0, float(BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC))

def _durable_recipients_from_item(item: dict) -> list[int]:

    recipients = item.get("recipients", [])
    try:
        return sorted({int(uid) for uid in recipients if int(uid) > 0})
    except Exception:
        return []


def _queue_item_can_be_durable(item: dict) -> bool:

    if not main.DURABLE_DELIVERY_QUEUE_ENABLED:
        return False
    if not isinstance(item, dict):
        return False
    if item.get("keyboard") is not None:
        return False
    if item.get("thread_id"):
        return False
    if item.get("delivery_phase") != "passive":
        return False
    content = item.get("content")
    if not isinstance(content, dict):
        return False
    if main._contains_volatile_delivery_payload(content):
        return False
    return bool(item.get("post_num")) and bool(_durable_recipients_from_item(item))







def _board_queue_oldest_age_sec(board_id: str | None) -> float:

    if not board_id:
        return 0.0
    queue = message_queues.get(board_id)
    if not queue:
        return 0.0
    now = time.time()
    oldest = 0.0
    try:
        for item in getattr(queue, "_queue", []):
            if not isinstance(item, dict):
                continue
            enqueued_at = item.get("enqueued_at")
            if enqueued_at is None:
                continue
            try:
                oldest = max(oldest, now - float(enqueued_at))
            except (TypeError, ValueError):
                continue
    except Exception:
        return 0.0
    return max(0.0, oldest)


async def get_board_activity_last_hours(board_id: str, hours: int = 2) -> float:
    if hours <= 0: return 0.0
    time_threshold = datetime.now(UTC) - timedelta(hours=hours)
    post_count = 0
    async with storage_lock:
        for post_data in reversed(messages_storage.values()):
            if post_data.get("timestamp") < time_threshold: break
            if post_data.get("board_id") == board_id:
                post_count += 1
    return post_count / hours

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from collections import defaultdict
import traceback

from shared_state import (
    board_data, messages_storage, state,
    message_queues, current_deliveries, pending_edit_tasks,
    pending_edit_lock, posts_pending_deletion, runtime_logger
)
from common.html_utils import escape_html
from common.task_manager import spawn_task
from common.db_pool import get_pool
from post_helpers import check_post_numerals, apply_shadow_autoreplace
from broadcaster import (
    _format_message_body, _order_recipients_for_delivery, send_message_to_users,
    _build_lie_media_content, DeliveryResults, MessageBroadcaster, add_you_to_my_posts_fast
)
from moderation_config import _LIE_IMAGE_EXTS, _LIE_VIDEO_EXTS

# Constants needed by delivery manager
CHUNK_SIZE = 30
DELAY_BETWEEN_CHUNKS = 1.0
PRIORITY_SPLIT_FANOUT_ENABLED = True
PRIORITY_SPLIT_MIN_PASSIVE = 200
WORKER_RESTART_DELAY_SEC = 5.0
WORKER_RESTART_MAX_DELAY_SEC = 60.0
PASSIVE_MAX_PREEMPTIONS = 5
# Cumulative delivery metrics across phases for consolidated post summary printing
cumulative_post_metrics = defaultdict(lambda: {
    'success': 0, 'priority': 0, 'passive': 0, 'errors': 0, 'blocks': 0, 'start_time': 0, 'total': 0
})
# ENABLE_MULTILANG is canonical in shared_state.py (imported via *)
RE_YOU_PATTERN = re.compile(r'>>(\d+)')

def _get_random_header_prefix(lang='ru'):
    if lang == 'jp': return "名無し - "
    if lang == 'en': return "Anon - "
    return "Анон - "

@dataclass
class PassiveQueueItemParams:
    source_item: dict
    recipients: set[int]
    post_num: int
    original_recipients: int
    enqueued_at: float | None
    started_at: float


def _build_passive_queue_item(params: PassiveQueueItemParams) -> dict:

    passive_item = params.source_item.copy()
    passive_item["recipients"] = set(params.recipients)
    passive_item["delivery_phase"] = "passive"
    passive_item["original_recipients"] = params.original_recipients
    passive_item["priority_split_from"] = params.post_num
    passive_item["phase_enqueued_at"] = time.time()
    passive_item["board_id"] = params.source_item.get("board_id")
    if "enqueued_at" not in passive_item:
        passive_item["enqueued_at"] = params.enqueued_at or params.started_at
    return passive_item


async def _persist_durable_delivery_item(board_id: str, item: dict, reason: str) -> int | None:

    if not _queue_item_can_be_durable(item):
        return None
    durable_id = await upsert_delivery_queue_item(
        board_id=board_id,
        post_num=int(item["post_num"]),
        recipients=_durable_recipients_from_item(item),
        content=item["content"],
        delivery_phase=item.get("delivery_phase", "passive"),
        original_recipients=int(item.get("original_recipients") or 0),
        thread_id=item.get("thread_id"),
        enqueued_at=float(item.get("enqueued_at") or time.time()),
    )
    if durable_id:
        item["durable_delivery_id"] = durable_id
        durable_delivery_stats["persisted"] = durable_delivery_stats.get("persisted", 0) + 1
        runtime_logger.debug(
            "delivery_durable_saved %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "id": durable_id,
                    "board_id": board_id,
                    "post_num": item.get("post_num"),
                    "phase": item.get("delivery_phase"),
                    "recipients": len(_durable_recipients_from_item(item)),
                    "reason": reason,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        return durable_id
    durable_delivery_stats["persist_failed"] = durable_delivery_stats.get("persist_failed", 0) + 1
    return None


async def _delete_durable_delivery_item(item_or_id, reason: str) -> None:

    durable_id = item_or_id
    if isinstance(item_or_id, dict):
        durable_id = item_or_id.get("durable_delivery_id")
    if not durable_id:
        return
    if await delete_delivery_queue_item(int(durable_id)):
        durable_delivery_stats["deleted"] = durable_delivery_stats.get("deleted", 0) + 1
        runtime_logger.debug(
            "delivery_durable_deleted %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "id": int(durable_id),
                    "reason": reason,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )


async def _remove_already_delivered_recipients(post_num: int, recipients) -> set[int]:

    try:
        candidate_recipients = {int(uid) for uid in recipients if int(uid) > 0}
    except Exception:
        return set()
    if not candidate_recipients:
        return set()
    copies = await get_post_copies(post_num)
    delivered = {int(recipient_id) for recipient_id, _message_id in copies}
    return candidate_recipients - delivered


def _passive_slice_size_for_content(content: dict, board_id: str | None = None) -> int:

    content_type = str((content or {}).get("type", "")).split(".")[-1].lower()
    if content_type in {
        "photo",
        "video",
        "animation",
        "document",
        "audio",
        "voice",
        "sticker",
        "video_note",
        "media_group",
    }:
        base_size = PRIORITY_PASSIVE_MEDIA_SLICE_SIZE
        pressure_size = PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE
    else:
        base_size = PRIORITY_PASSIVE_SLICE_SIZE
        pressure_size = PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE
    if (
        board_id
        and PRIORITY_PRESSURE_SLICE_AGE_SEC > 0
        and _board_queue_oldest_age_sec(board_id) >= PRIORITY_PRESSURE_SLICE_AGE_SEC
    ):
        return min(base_size, pressure_size)
    return base_size


def _queue_has_full_message(queue: asyncio.Queue) -> bool:

    try:
        for item in getattr(queue, "_queue", []):
            if isinstance(item, dict) and item.get("delivery_phase", "full") == "full":
                return True
    except Exception:
        return False
    return False


def _split_recipients_for_delivery(board_id: str, recipients) -> tuple[list[int], list[int]]:
    recipient_list = list(recipients)
    if not PRIORITY_DELIVERY_ENABLED or not recipient_list:
        return [], recipient_list
    priority_set = weekly_active_users.get(board_id, set())
    if not priority_set:
        return [], recipient_list
    priority = []
    passive = []
    for uid in recipient_list:
        if uid in priority_set:
            priority.append(uid)
        else:
            passive.append(uid)
    return priority, passive


def _lie_media_kind(raw_type: str | None, item: dict | None = None) -> str | None:
    item = item or {}
    ftype = str(raw_type or item.get('type') or '').split('.')[-1].lower()
    mime = str(item.get('mime_type') or item.get('mime') or '').lower()
    filename = str(item.get('filename') or item.get('file_name') or item.get('name') or '').lower()
    if ftype in {'photo', 'image'}:
        return 'image'
    if ftype in {'video', 'animation', 'gif'}:
        return 'video'
    if ftype == 'document':
        if mime.startswith('video/') or filename.endswith(_LIE_VIDEO_EXTS):
            return 'video'
        if mime.startswith('image/') or filename.endswith(_LIE_IMAGE_EXTS):
            return 'image'
    return None


def _lie_archive_send_type(entry: dict, desired_kind: str) -> str | None:
    source_type = str(entry.get('source_type') or entry.get('type') or '').split('.')[-1].lower()
    mime = str(entry.get('mime_type') or entry.get('mime') or '').lower()
    filename = str(entry.get('filename') or entry.get('file_name') or entry.get('name') or '').lower()
    if desired_kind == 'image':
        if source_type in {'photo', 'image'}:
            return 'photo'
        if source_type == 'document' and (mime.startswith('image/') or filename.endswith(_LIE_IMAGE_EXTS)):
            return 'document'
    elif desired_kind == 'video':
        if source_type == 'video':
            return 'video'
        if source_type in {'animation', 'gif'}:
            return 'animation'
        if source_type == 'document' and (mime.startswith('video/') or filename.endswith(_LIE_VIDEO_EXTS)):
            return 'document'
    return None


def _lie_file_from_random_post(
    post: dict | None,
    desired_kind: str,
    allowed_send_types: set[str],
    avoid_post_num: int | None = None,
    exclude_file_ids: set[str] | None = None,
) -> dict | None:
    if not post or not isinstance(post.get('content'), dict):
        return None
    if avoid_post_num is not None:
        try:
            candidate_post_num = int(post.get('post_num') or post.get('id') or 0)
            if candidate_post_num == int(avoid_post_num):
                return None
        except (TypeError, ValueError):
            import traceback; traceback.print_exc()
    files = post['content'].get('files') or []
    if not files:
        return None
    selected_idx = post.get('_selected_file_index', 0)
    if not isinstance(selected_idx, int) or selected_idx < 0 or selected_idx >= len(files):
        selected_idx = 0
    entry = files[selected_idx]
    if not isinstance(entry, dict):
        return None
    file_id = entry.get('original_file_id') or entry.get('file_id') or entry.get('media')
    if not file_id or not isinstance(file_id, str) or file_id.startswith('<'):
        return None
    if exclude_file_ids and file_id in exclude_file_ids:
        return None
    send_type = _lie_archive_send_type(entry, desired_kind)
    if not send_type or send_type not in allowed_send_types:
        return None
    return {
        'type': send_type,
        'file_id': file_id,
        'filename': entry.get('filename') or entry.get('file_name') or entry.get('name'),
        'mime_type': entry.get('mime_type') or entry.get('mime'),
    }


async def _get_lie_archive_media(
    board_id: str,
    desired_kind: str,
    allowed_send_types: set[str],
    avoid_post_num: int | None = None,
    exclude_file_ids: set[str] | None = None,
) -> dict | None:
    getter = main.get_random_video_post if desired_kind == 'video' else main.get_random_image_post
    for _ in range(12):
        post = await getter([board_id])
        media = _lie_file_from_random_post(post, desired_kind, allowed_send_types, avoid_post_num, exclude_file_ids)
        if media:
            return media
    return None


def _lie_allowed_send_types(raw_type: str, media_group: bool = False) -> set[str]:
    ctype = str(raw_type or '').split('.')[-1].lower()
    if media_group:
        if ctype == 'photo':
            return {'photo'}
        if ctype == 'video':
            return {'video'}
        if ctype == 'document':
            return {'document'}
        return set()
    if ctype == 'photo':
        return {'photo'}
    if ctype == 'video':
        return {'video'}
    if ctype == 'animation':
        return {'animation'}
    if ctype == 'document':
        return {'document'}
    return set()


async def edit_post_for_all_recipients(post_num: int, bot_instance: Bot):
    """
    Находит все отправленные копии поста и редактирует их.
    Основной источник данных - база данных.
    Версия 2.2: Добавлена группировка сообщений по юзерам (защита от мульти-эдита альбомов).
    """
    copies_info = await get_post_copies(post_num)
    user_messages_map = defaultdict(list)
    if copies_info:
        for uid, mid in copies_info:
            user_messages_map[uid].append(mid)
    async with storage_lock:
        ram_copies = post_to_messages.get(post_num, {})
        for uid, mid_or_list in ram_copies.items():
            if isinstance(mid_or_list, list):
                for m in mid_or_list:
                    if m not in user_messages_map[uid]:
                        user_messages_map[uid].append(m)
            else:
                if mid_or_list not in user_messages_map[uid]:
                    user_messages_map[uid].append(mid_or_list)

    if not user_messages_map:
        return

    post_data_copy = {}
    content_copy = {}
    reply_author_id = None
    board_id = None
    async with storage_lock:
        post_data = messages_storage.get(post_num)
    if not post_data:
        db_post = await main.get_post_by_num(post_num)
        if db_post:
            content_dict = db_post['content'] if isinstance(db_post['content'], dict) else {}
            reactions_dict = content_dict.get('reactions', {'users': {}})
            async with storage_lock:
                messages_storage[post_num] = {
                    'author_id': db_post['author_id'],
                    'timestamp': datetime.fromtimestamp(db_post['timestamp'], UTC) if isinstance(db_post['timestamp'], (int, float)) else db_post['timestamp'],
                    'content': content_dict,
                    'reactions': reactions_dict,
                    'board_id': db_post['board_id'],
                    'thread_id': db_post.get('thread_id')
                }
                post_data = messages_storage.get(post_num)

    if not post_data:
        return

    async with storage_lock:
        content_type = post_data.get('content', {}).get('type')
        can_be_edited = content_type in ['text', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'media_group']
        if not can_be_edited: return
        post_data_copy = post_data.copy()
        content_copy = post_data.get('content', {}).copy()
        if 'reactions' not in post_data_copy and 'reactions' in content_copy:
            post_data_copy['reactions'] = content_copy['reactions']
        board_id = post_data.get('board_id')
        reply_to_post_num = content_copy.get('reply_to_post')
        if reply_to_post_num:
            reply_author_id = messages_storage.get(reply_to_post_num, {}).get('author_id')
    if not board_id: return
    
    final_keyboard = None
    if content_copy.get('poll_data'):
        poll_options = content_copy.get('poll_data', {}).get('options', [])
        if poll_options:
            buttons = []
            for i, option_text in enumerate(poll_options):
                button_text = option_text[:60]
                buttons.append(
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"poll_vote_{post_num}_{i}"
                    )
                )
            final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
            
    user_specific_texts = {}
    text_or_caption_base = content_copy.get('text') or content_copy.get('caption')
    text_with_you_links = text_or_caption_base
    if text_or_caption_base and ">>" in text_or_caption_base:
        mentioned_authors = {}
        mentions = RE_YOU_PATTERN.findall(text_or_caption_base)
        if mentions:
            async with storage_lock:
                for m_num_str in mentions:
                    try:
                        m_num = int(m_num_str)
                        if m_num in messages_storage:
                            mentioned_authors[m_num] = messages_storage[m_num].get("author_id")
                    except ValueError:
                        continue
        text_with_you_links = add_you_to_my_posts_fast(
            text_or_caption_base, 
            post_data_copy.get('author_id'), 
            mentioned_authors
        )            
    b_data = board_data[board_id]
    users_settings = b_data.get('user_settings', {})
    for user_id in user_messages_map.keys():
        header_text = content_copy.get('header', '')
        u_set = users_settings.get(user_id, {'hide': set()})
        should_hide = False
        if u_set['hide']:
            raw_content_text = content_copy.get('text') or content_copy.get('caption') or ""
            check_text = (header_text + " " + raw_content_text).lower()
            if any(word in check_text for word in u_set['hide']):
                should_hide = True
        head = f"<i>{escape_html(header_text)}</i>"
        if user_id == reply_author_id:
            head = head.replace("Пост", "🔴 Пост").replace("Post", "🔴 Post")
        if should_hide:
            lang_local = 'en' if board_id == 'int' else 'ru'
            placeholder = "🛡 Message hidden" if lang_local == 'en' else "🛡 Сообщение скрыто"
            full_text = f"{head}\n{placeholder}"
        else:
            current_text_or_caption = text_or_caption_base
            if user_id == post_data_copy.get('author_id'):
                current_text_or_caption = text_with_you_links
            content_for_user = content_copy.copy()
            if 'text' in content_for_user: content_for_user['text'] = current_text_or_caption
            elif 'caption' in content_for_user: content_for_user['caption'] = current_text_or_caption
            formatted_body = await _format_message_body(
                content=content_for_user, user_id_for_context=user_id,
                post_data=post_data_copy, reply_to_post_author_id=reply_author_id,
                quote_info=content_for_user.get('quote_info')
            )
            full_text = f"{head}\n\n{formatted_body}" if formatted_body else head
        user_specific_texts[user_id] = full_text

    async def _edit_one(user_id: int, message_id: int):
        max_attempts = 6
        delay = 1.5
        for attempt in range(max_attempts):
            try:
                full_text = user_specific_texts.get(user_id, "")
                content_type = content_copy.get('type')
                if content_type == 'text':
                    if len(full_text) > 4096: full_text = full_text[:4093] + "..."
                    await bot_instance.edit_message_text(text=full_text, chat_id=user_id, message_id=message_id, parse_mode="HTML", reply_markup=final_keyboard)
                else:
                    if len(full_text) > 1024: full_text = full_text[:1021] + "..."
                    await bot_instance.edit_message_caption(caption=full_text, chat_id=user_id, message_id=message_id, parse_mode="HTML", reply_markup=final_keyboard)
                return 
            except TelegramRetryAfter as e:
                wait_sec = e.retry_after + 1
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_sec)
                    continue
                else:
                    return 
            except TelegramBadRequest as e:
                error_message_lower = e.message.lower()
                ignored_errors = ("message is not modified", "message to edit not found", "chat not found")
                if any(err in error_message_lower for err in ignored_errors):
                    return
                if "flood control" in error_message_lower or "retry after" in error_message_lower:
                    wait_sec = 3
                    match = re.search(r'retry after (\d+)', error_message_lower)
                    if match:
                        wait_sec = int(match.group(1)) + 1
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(wait_sec)
                        continue
                    else:
                        return
                return 
            except (main.TelegramNetworkError, asyncio.TimeoutError, main.aiohttp.ClientError) as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 10) 
                    continue
                return 
            except main.TelegramForbiddenError:
                return
            except Exception as e:
                print(f"⚠️ Непредвиденная ошибка в _edit_one: {e}")
                return
    tasks_to_run = []
    for uid, msgs in user_messages_map.items():
        if msgs:
            target_mid = sorted(msgs)[0]
            task = spawn_task(_edit_one(uid, target_mid))
            tasks_to_run.append(task)

    CHUNK_SIZE = 30 
    DELAY_BETWEEN_CHUNKS = 0.3
    for i in range(0, len(tasks_to_run), CHUNK_SIZE):
        chunk_tasks = tasks_to_run[i:i + CHUNK_SIZE]
        await asyncio.gather(*chunk_tasks, return_exceptions=True)
        if i + CHUNK_SIZE < len(tasks_to_run):
            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)


async def execute_delayed_edit(
    post_num: int,
    bot_instance: Bot,
    author_id: int | None,
    notify_text: str | None,
    reply_to_message_id: int | None = None,
    delay: float = 3.0
):
    """
    Ждет задержку, отправляет уведомление (если оно есть) в виде ответа, а затем редактирует пост.
    """
    try:
        await asyncio.sleep(delay)
        if author_id and notify_text:
            try:
                await bot_instance.send_message(
                    author_id,
                    notify_text,
                    reply_to_message_id=reply_to_message_id
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass  # юзер заблокировал бота или сообщение удалено — норм
        await edit_post_for_all_recipients(post_num, bot_instance)
    except asyncio.CancelledError:
        raise  # нормальная отмена таски — не логируем, propagate вверх
    except Exception as e:
        print(f"❌ Ошибка в execute_delayed_edit для поста #{post_num}: {e}")
    finally:
        async with pending_edit_lock:
            current_task = asyncio.current_task()
            if pending_edit_tasks.get(post_num) is current_task:
                pending_edit_tasks.pop(post_num, None)


async def _supervise_message_worker(worker_name: str, board_id: str, bot_instance: Bot) -> None:
    """
    Держит воркер доски живым.

    Раньше воркер, вышедший из цикла (например по 'closed database'), исчезал
    молча: message_broadcaster висел в gather до смерти ВСЕХ воркеров, поэтому
    рестарта не происходило и доска переставала доставлять сообщения до
    перезапуска процесса. Теперь каждый воркер поднимается отдельно.
    """
    delay = WORKER_RESTART_DELAY_SEC
    while not (is_shutting_down or drain_shutdown_requested):
        start_time = time.time()
        try:
            await message_worker(worker_name, board_id, bot_instance)
            if is_shutting_down or drain_shutdown_requested:
                return
            print(f"⚠️ {worker_name} завершился без запроса остановки. Перезапуск через {delay:.0f} с.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if is_shutting_down or drain_shutdown_requested:
                return
            print(f"⛔ {worker_name} упал: {type(e).__name__}: {str(e)[:200]}. Перезапуск через {delay:.0f} с.")
            runtime_logger.exception("message_worker_crashed board=%s", board_id)

        if time.time() - start_time >= 120:
            delay = WORKER_RESTART_DELAY_SEC
        else:
            delay = min(delay * 2, WORKER_RESTART_MAX_DELAY_SEC)
        await asyncio.sleep(delay)


async def message_broadcaster(bots: dict[str, Bot]):

    tasks = [
        spawn_task(_supervise_message_worker(f"Worker-{board_id}", board_id, bot_instance))
        for board_id, bot_instance in bots.items()
    ]
    # return_exceptions: падение одного супервизора не должно ронять
    # message_broadcaster целиком (иначе _run_background_task поднимет ВТОРОЙ
    # комплект воркеров поверх ещё живых первых).
    await asyncio.gather(*tasks, return_exceptions=True)


class MessageDeliveryTask:
    """
    Класс для обработки доставки одного сообщения.
    Инкапсулирует логику, ранее находившуюся в монолитной функции message_worker.
    """
    def __init__(self, worker_name, board_id, bot_instance, queue, msg_data):
        self.worker_name = worker_name
        self.board_id = board_id
        self.bot_instance = bot_instance
        self.queue = queue
        self.msg_data = msg_data

        self.b_data = board_data[self.board_id]

    async def process(self):
        """Основной метод оркестрации обработки сообщения."""
        if not await validate_message_format(self.msg_data):
            return

        # Delayed initialization to ensure msg_data is valid
        self.post_num = self.msg_data['post_num']
        self.content = self.msg_data['content']
        self.content['post_num'] = self.post_num
        self.keyboard = self.msg_data.get('keyboard')
        self.thread_id = self.msg_data.get('thread_id')
        self.delivery_phase = self.msg_data.get("delivery_phase", "full")
        self.initial_recipients = self.msg_data['recipients']

        self.enqueued_at = self.msg_data.get("enqueued_at")
        self.started_at = time.time()
        self.queue_wait_sec = None
        if self.enqueued_at is not None:
            try:
                self.queue_wait_sec = max(0.0, self.started_at - float(self.enqueued_at))
            except (TypeError, ValueError):
                import traceback; traceback.print_exc()

        self.passive_slice_size = _passive_slice_size_for_content(self.content, self.board_id)

        if self.post_num in posts_pending_deletion:
            print(f"[{self.board_id}] Worker пропустил пост #{self.post_num}, т.к. он помечен на удаление.")
            return

        if self.msg_data.get("durable_delivery_id"):
            self.initial_recipients = await _remove_already_delivered_recipients(self.post_num, self.initial_recipients)
            self.msg_data["recipients"] = self.initial_recipients
            if not self.initial_recipients:
                await _delete_durable_delivery_item(self.msg_data, "already_delivered")
                return

        if await self._handle_preemption():
            return

        active_recipients = self._resolve_active_recipients()
        if not active_recipients:
            if self.msg_data.get("durable_delivery_id"):
                await _delete_durable_delivery_item(self.msg_data, "no_active_recipients")
            return

        try:
            original_recipients_for_post = int(self.msg_data.get("original_recipients") or len(active_recipients))
        except (TypeError, ValueError):
            original_recipients_for_post = len(active_recipients)

        recipients_to_send, passive_recipients_for_later, delivery_phase_for_send, deferred_reason = self._determine_delivery_phases(active_recipients)

        reply_info_copy = {}
        async with storage_lock:
            if self.post_num in post_to_messages:
                reply_info_copy = post_to_messages[self.post_num].copy()

        current_deliveries[self.board_id] = {
            "post_num": self.post_num,
            "started_at": self.started_at,
            "enqueued_at": self.enqueued_at,
            "queue_wait_sec": round(self.queue_wait_sec, 3) if self.queue_wait_sec is not None else None,
            "recipients": len(recipients_to_send),
            "original_recipients": original_recipients_for_post,
            "passive_deferred": len(passive_recipients_for_later),
            "passive_slice_size": self.passive_slice_size,
            "phase": delivery_phase_for_send,
            "thread_id": self.thread_id,
        }

        planned_passive_durable_id = None
        planned_passive_item = None
        if passive_recipients_for_later and not self.msg_data.get("durable_delivery_id"):
            planned_passive_item = _build_passive_queue_item(
                PassiveQueueItemParams(
                    source_item=self.msg_data,
                    recipients=passive_recipients_for_later,
                    post_num=self.post_num,
                    original_recipients=original_recipients_for_post,
                    enqueued_at=self.enqueued_at,
                    started_at=self.started_at,
                )
            )
            planned_passive_durable_id = await _persist_durable_delivery_item(
                self.board_id,
                planned_passive_item,
                "planned_before_send",
            )

        budget_deferred_count = 0
        delivered_now_count = 0
        try:
            delivery_results = await send_message_to_users(BroadcastConfig(
                bot_instance=self.bot_instance,
                board_id=self.board_id,
                recipients=recipients_to_send,
                content=self.content,
                reply_info=reply_info_copy,
                keyboard=self.keyboard,
                verbose=True,
                queue_enqueued_at=self.enqueued_at,
                queue_wait_sec=self.queue_wait_sec,
                delivery_phase=delivery_phase_for_send,
                delivery_original_recipients=original_recipients_for_post,
                delivery_deferred_recipients=len(passive_recipients_for_later),
            ))
            delivered_now_count = len(delivery_results)
            budget_deferred = getattr(delivery_results, "remaining_recipients", set())
            if budget_deferred:
                budget_deferred_count = len(budget_deferred)
                passive_recipients_for_later.update(budget_deferred)
                budget_reason = getattr(delivery_results, "interrupted_reason", None) or "phase_budget"
                deferred_reason = f"{deferred_reason}+{budget_reason}" if deferred_reason else budget_reason

            # Track cumulative delivery metrics for single consolidated summary
            d_stats = getattr(delivery_results, "stats", {})
            post_key = (self.board_id, self.post_num)
            cum = cumulative_post_metrics[post_key]
            if not cum['start_time']:
                cum['start_time'] = self.started_at or time.time()
                cum['total'] = original_recipients_for_post or len(recipients_to_send)
            cum['success'] += d_stats.get('success', len(delivery_results))
            cum['priority'] += d_stats.get('priority_recipients', 0)
            cum['passive'] += d_stats.get('passive_recipients', 0)
            cum['errors'] += d_stats.get('errors', 0)
            cum['blocks'] += d_stats.get('blocks', 0)

            # Stage 2 milestone: Log when priority / active recipients phase completes
            if delivery_phase_for_send == "priority" and not cum.get('priority_logged'):
                cum['priority_logged'] = True
                p_num = self.post_num if self.post_num is not None else "sys"
                prio_elapsed = max(0.05, time.time() - cum['start_time'])
                prio_success = d_stats.get('priority_recipients', len(delivery_results))
                prio_total = len(recipients_to_send)
                try:
                    print(f"⚡ Пост #{p_num} [/{self.board_id}/] разослан активным: {prio_success}/{prio_total} | Время: {prio_elapsed:.1f}с")
                except Exception:
                    try:
                        print(f"[Active] Post #{p_num} [/{self.board_id}/] sent to active: {prio_success}/{prio_total} | Time: {prio_elapsed:.1f}s")
                    except Exception:
                        pass
        except Exception:
            if planned_passive_durable_id and passive_recipients_for_later:
                planned_passive_item["durable_delivery_id"] = planned_passive_durable_id
                await self.queue.put(planned_passive_item)
                runtime_logger.warning(
                    "delivery_durable_requeued_after_send_error %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "id": planned_passive_durable_id,
                            "board_id": self.board_id,
                            "post_num": self.post_num,
                            "deferred": len(passive_recipients_for_later),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            raise
        finally:
            current_delivery = current_deliveries.get(self.board_id)
            if current_delivery and current_delivery.get("post_num") == self.post_num:
                current_deliveries.pop(self.board_id, None)

        if passive_recipients_for_later:
            passive_item = _build_passive_queue_item(
                PassiveQueueItemParams(
                    source_item=self.msg_data,
                    recipients=passive_recipients_for_later,
                    post_num=self.post_num,
                    original_recipients=original_recipients_for_post,
                    enqueued_at=self.enqueued_at,
                    started_at=self.started_at,
                )
            )
            if planned_passive_durable_id:
                passive_item["durable_delivery_id"] = planned_passive_durable_id
            await _persist_durable_delivery_item(self.board_id, passive_item, "deferred_after_send")
            await self.queue.put(passive_item)
            runtime_logger.debug(
                "delivery_passive_deferred %s",
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "board_id": self.board_id,
                        "post_num": self.post_num,
                        "phase": delivery_phase_for_send,
                        "reason": deferred_reason,
                        "requested_now": len(recipients_to_send),
                        "sent_now": delivered_now_count,
                        "deferred": len(passive_recipients_for_later),
                        "budget_deferred": budget_deferred_count,
                        "queue_size": self.queue.qsize(),
                        "passive_slice_size": self.passive_slice_size,
                        "content_type": str(self.content.get("type")),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        else:
            if self.msg_data.get("durable_delivery_id"):
                await _delete_durable_delivery_item(self.msg_data, "completed")
            # Stage 3 milestone: Post delivery is completely finished for all recipients!
            post_key = (self.board_id, self.post_num)
            cum = cumulative_post_metrics.pop(post_key, None)
            if cum:
                elapsed = max(0.1, time.time() - cum['start_time'])
                p_num = self.post_num if self.post_num is not None else "sys"
                p_total = cum['total'] or (cum['success'] + cum['errors'] + cum['blocks'])
                log_msg = f"📊 Пост #{p_num} [/{self.board_id}/] разослан всем: {cum['success']}/{p_total} (прио: {cum['priority']}, пасс: {cum['passive']}) | Ошибок: {cum['errors']} | Блоков: {cum['blocks']} | Время: {elapsed:.1f}с"
                try:
                    print(log_msg)
                except Exception:
                    try:
                        print(f"[Completed] Post #{p_num} [/{self.board_id}/] sent to all: {cum['success']}/{p_total} (prio: {cum['priority']}, pass: {cum['passive']}) | Errors: {cum['errors']} | Blocks: {cum['blocks']} | Time: {elapsed:.1f}s")
                    except Exception:
                        pass

    async def _handle_preemption(self):
        """Обрабатывает логику прерывания для пассивной фазы."""
        if (
            PRIORITY_SPLIT_FANOUT_ENABLED
            and self.delivery_phase == "passive"
            and not self.thread_id
            and PASSIVE_MAX_PREEMPTIONS > 0
            and len(self.initial_recipients) > self.passive_slice_size
            and _queue_has_full_message(self.queue)
        ):
            preemptions = int(self.msg_data.get("passive_preemptions", 0) or 0)
            if preemptions < PASSIVE_MAX_PREEMPTIONS:
                self.msg_data["passive_preemptions"] = preemptions + 1
                await self.queue.put(self.msg_data)
                runtime_logger.debug(
                    "delivery_passive_preempted %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": self.board_id,
                            "post_num": self.post_num,
                            "preemptions": self.msg_data["passive_preemptions"],
                            "max_preemptions": PASSIVE_MAX_PREEMPTIONS,
                            "queue_size": self.queue.qsize(),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return True
        return False

    def _resolve_active_recipients(self):
        """Определяет список активных получателей."""
        active_recipients = set()
        if self.thread_id:
            active_recipients = {
                uid for uid in self.initial_recipients
                if uid > 0 and uid not in self.b_data['users']['banned']
            }
        else:
            user_states = self.b_data.get('user_state', {})
            recipients_on_main = {
                uid for uid in self.initial_recipients
                if uid > 0 and user_states.get(uid, {}).get('location', 'main') == 'main'
            }
            active_recipients = {uid for uid in recipients_on_main if uid not in self.b_data['users']['banned']}
        return active_recipients

    def _determine_delivery_phases(self, active_recipients):
        """Определяет фазы доставки (recipients_to_send, passive_recipients_for_later, phase, reason)."""
        recipients_to_send = active_recipients
        passive_recipients_for_later = set()
        delivery_phase_for_send = self.delivery_phase
        deferred_reason = None

        if (
            self.delivery_phase == "full"
            and PRIORITY_SPLIT_FANOUT_ENABLED
            and not self.thread_id
        ):
            priority_recipients, passive_recipients = _split_recipients_for_delivery(self.board_id, active_recipients)
            if priority_recipients and len(passive_recipients) >= PRIORITY_SPLIT_MIN_PASSIVE:
                recipients_to_send = set(priority_recipients)
                passive_recipients_for_later = set(passive_recipients)
                delivery_phase_for_send = "priority"
                deferred_reason = "split_priority_first"
        elif (
            self.delivery_phase == "passive"
            and PRIORITY_SPLIT_FANOUT_ENABLED
            and not self.thread_id
            and len(active_recipients) > self.passive_slice_size
        ):
            ordered_passive = list(active_recipients)
            recipients_to_send = set(ordered_passive[:self.passive_slice_size])
            passive_recipients_for_later = set(ordered_passive[self.passive_slice_size:])
            delivery_phase_for_send = "passive_slice"
            deferred_reason = "passive_slice"

        return recipients_to_send, passive_recipients_for_later, delivery_phase_for_send, deferred_reason


async def message_worker(worker_name: str, board_id: str, bot_instance: Bot):
    """
    Воркер обработки очереди сообщений.
    Исправлено: queue.get() вынесен из try-блока, чтобы избежать ошибки task_done() при отмене задачи.
    Рефакторинг: Использован паттерн Method Object (MessageDeliveryTask) для инкапсуляции логики обработки сообщения.
    Улучшено: Добавлена обработка ошибок с экспоненциальным повтором и сохранением в надежное хранилище.
    """
    queue = message_queues[board_id]
    while True:
        msg_data = await queue.get()
        try:
            if not msg_data:
                await asyncio.sleep(0.05)
                continue

            task = MessageDeliveryTask(worker_name, board_id, bot_instance, queue, msg_data)
            await task.process()

        except asyncio.CancelledError:
            break
        except Exception as e:
            if is_shutting_down or drain_shutdown_requested:
                break
            # 'closed database' раньше означал break, то есть тихую смерть воркера
            # доски навсегда. Ошибка восстановимая: get_pool() переподключается
            # сам, поэтому ждём чуть дольше и продолжаем разгребать очередь.
            if "closed database" in str(e).lower():
                print(f"{worker_name} | ⚠️ Соединение с БД было закрыто, жду переподключения пула...")
                runtime_logger.warning("message_worker_db_closed board=%s", board_id)
                await asyncio.sleep(5)
                try:
                    await queue.put(msg_data)
                except Exception:
                    pass
                continue
            print(f"{worker_name} | ⛔ Ошибка обработки элемента: {str(e)[:200]}")
            import traceback
            traceback.print_exc()

            retries = msg_data.get("_retry_count", 0)
            max_retries = 3
            if retries < max_retries:
                msg_data["_retry_count"] = retries + 1
                backoff = 2 ** retries
                print(f"{worker_name} | 🔄 Повторная попытка ({retries + 1}/{max_retries}) для поста #{msg_data.get('post_num')} через {backoff}с...")
                await asyncio.sleep(backoff)
                try:
                    await queue.put(msg_data)
                except Exception as put_err:
                    print(f"{worker_name} | ⚠️ Не удалось повторно добавить элемент в очередь: {put_err}")
                    await _persist_durable_delivery_item(board_id, msg_data, "worker_retry_put_failed")
            else:
                print(f"{worker_name} | ❌ Превышен лимит попыток для поста #{msg_data.get('post_num')}. Сохраняю в надежное хранилище.")
                await _persist_durable_delivery_item(board_id, msg_data, "worker_max_retries_exceeded")

            await asyncio.sleep(1)
        finally:
            queue.task_done()


async def send_missed_messages(bot: Bot, board_id: str, user_id: int, target_location: str, stream: str = 'ru') -> tuple[bool, bool]:
    """
    Отправляет пользователю пропущенные сообщения. Гарантирует, что ОП-пост
    треда будет показан первым. ОПТИМИЗИРОВАННАЯ ВЕРСИЯ.
    Возвращает кортеж (были ли отправлены сообщения, нужно ли показать кнопку "Вся летопись" - всегда False).
    """
    b_data = board_data[board_id]
    user_s = b_data['user_state'].setdefault(user_id, {})
    missed_post_nums_full = []
    op_post_num = None
    posts_to_send_data = [] # Здесь будем хранить полные данные постов
    async with storage_lock:
        if target_location == 'main':
            last_seen_post = user_s.get('last_seen_main', 0)
            all_main_posts = sorted([
                p_num for p_num, p_data in messages_storage.items() 
                if p_data.get('board_id') == board_id and not p_data.get('thread_id')
            ])
            missed_post_nums_full = [p_num for p_num in all_main_posts if p_num > last_seen_post]
            if len(missed_post_nums_full) > 20:
                missed_post_nums_full = missed_post_nums_full[-20:]
        else: # Загрузка для треда
            thread_id = target_location
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info: return False, False
            all_thread_posts = sorted(thread_info.get('posts', []))
            if all_thread_posts:
                op_post_num = all_thread_posts[0]
            missed_post_nums_full = all_thread_posts
        if not missed_post_nums_full:
            return False, False
        for post_num in missed_post_nums_full:
            post_data = messages_storage.get(post_num)
            if post_data:
                posts_to_send_data.append({
                    'content': post_data.get('content', {}).copy(),
                    'reply_info': post_to_messages.get(post_num, {}).copy()
                })
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if target_location != 'main':
        try:
            if lang == 'en':
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>THREAD LOADED</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            elif lang == 'jp':
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>スレッド読み込み完了</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            else:
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>ТРЕД ЗАГРУЖЕН</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            await bot.send_message(user_id, loading_text, parse_mode="HTML")
            await asyncio.sleep(0.5)
        except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
            import traceback; traceback.print_exc()
    if op_post_num:
        op_post_data = next((p for p in posts_to_send_data if p['content'].get('post_num') == op_post_num), None)
        if op_post_data:
            try:
                await send_message_to_users(BroadcastConfig(bot_instance=bot, board_id=board_id, recipients={user_id}, content=op_post_data['content'], reply_info=op_post_data['reply_info']))
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки ОП-поста #{op_post_num} юзеру {user_id}: {e}")
    for post_bundle in posts_to_send_data:
        if post_bundle['content'].get('post_num') != op_post_num:
            try:
                await send_message_to_users(BroadcastConfig(bot_instance=bot, board_id=board_id, recipients={user_id}, content=post_bundle['content'], reply_info=post_bundle['reply_info']))
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки пропущенного сообщения #{post_bundle['content'].get('post_num')} юзеру {user_id}: {e}")
    if lang == 'en':
        final_text = "All new messages loaded."
    elif lang == 'jp':
        final_text = "新着メッセージを読み込みました。"
    else:
        final_text = "Все новые сообщения загружены."
    entry_keyboard = _get_thread_entry_keyboard(board_id, stream=stream)
    try:
        await bot.send_message(user_id, final_text, reply_markup=entry_keyboard, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        import traceback; traceback.print_exc()
    if missed_post_nums_full:
        new_last_seen = missed_post_nums_full[-1]
        if target_location == 'main':
            user_s['last_seen_main'] = new_last_seen
        else:
            user_s.setdefault('last_seen_threads', {})[target_location] = new_last_seen
    return True, False


async def board_help_worker(board_id: str):
    """
    Индивидуальный воркер рассылки помощи. 
    Исправлено: message.queues -> message_queues
    """
    await asyncio.sleep(random.randint(10, 300))
    while True:
        try:
            delay = random.randint(28800, 43200) # от 8 до 12 часов (не чаще 8ч)
            await asyncio.sleep(delay)
            activity = await main.get_board_activity_last_hours(board_id, hours=24)
            if activity < 15: # Если меньше 15 постов за сутки - доска мертва
                print(f"💀 [{board_id}] Доска полудохлая (акт: {activity}), пропускаем рассылку помощи.")
                continue
            b_data = board_data[board_id]
            streams_to_process = ['ru']
            if board_id == 'int':
                streams_to_process = ['en']
            elif ENABLE_MULTILANG:
                streams_to_process = ['ru', 'en', 'jp']
            for stream in streams_to_process:
                if board_id == 'int':
                    recipients = b_data['users']['active'] - b_data['users']['banned']
                else:
                    if ENABLE_MULTILANG:
                        stream_users = await get_stream_active_users(board_id, stream)
                        recipients = stream_users.intersection(b_data['users']['active']) - b_data['users']['banned']
                    else:
                        if stream != 'ru': continue 
                        recipients = b_data['users']['active'] - b_data['users']['banned']
                if not recipients:
                    continue
                message_text = ""
                choice = random.randint(1, 6)
                if stream == 'en':
                    if choice == 1: message_text = random.choice(HELP_TEXT_EN_COMMANDS)
                    elif choice == 2: message_text = main.generate_boards_list(BOARD_CONFIG, 'en')
                    elif choice == 3: message_text = random.choice(THREAD_PROMO_TEXT_EN)
                    elif choice == 4: message_text = random.choice(main.MODE_INFO_TEXT_EN)
                    elif choice == 5: message_text = random.choice(main.CHANNEL_PROMO_TEXT_EN)
                    else: message_text = random.choice(main.MECHANICS_INFO_TEXT_EN)
                elif stream == 'jp':
                    if choice == 1: message_text = random.choice(main.HELP_TEXT_JP_COMMANDS)
                    elif choice == 2: message_text = main.generate_boards_list(BOARD_CONFIG, 'jp')
                    elif choice == 3: message_text = random.choice(main.THREAD_PROMO_TEXT_JP)
                    elif choice == 4: message_text = random.choice(main.MODE_INFO_TEXT_JP)
                    elif choice == 5: message_text = random.choice(main.CHANNEL_PROMO_TEXT_JP)
                    else: message_text = random.choice(main.MECHANICS_INFO_TEXT_JP)
                else: # ru
                    if choice == 1: message_text = random.choice(main.HELP_TEXT_COMMANDS)
                    elif choice == 2: message_text = main.generate_boards_list(BOARD_CONFIG, 'ru')
                    elif choice == 3: message_text = random.choice(main.THREAD_PROMO_TEXT_RU)
                    elif choice == 4: message_text = random.choice(main.MODE_INFO_TEXT_RU)
                    elif choice == 5: message_text = random.choice(main.CHANNEL_PROMO_TEXT_RU)
                    else: message_text = random.choice(main.MECHANICS_INFO_TEXT_RU)
                now_dt = datetime.now(UTC)
                from banner_manager import get_banner_file, _BANNER_CACHE
                banner_cat = "start" if choice == 1 else "calm"
                fname, photo_payload = get_banner_file(category=banner_cat)
                fid = photo_payload if isinstance(photo_payload, str) else _BANNER_CACHE.get(fname)
                if not fid and _BANNER_CACHE:
                    fid = next(iter(_BANNER_CACHE.values()), None)
                content = {
                    'type': 'photo' if fid else 'text',
                    'file_id': fid,
                    'caption': message_text,
                    'text': message_text,
                    'is_system_message': True,
                    'archive_allowed': True
                }
                post_num = await create_post(
                    board_id=board_id, author_id=0, content=content,
                    timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
                )
                if not post_num: continue
                header = await format_header(board_id, post_num, stream=stream)
                content['header'] = header
                await update_post_content(post_num, content)
                async with storage_lock:
                    messages_storage[post_num] = {
                        'author_id': 0, 'timestamp': now_dt,
                        'content': content, 'board_id': board_id
                    }
                await enqueue_board_message(board_id, {
                    'recipients': recipients, 'content': content,
                    'post_num': post_num, 'board_id': board_id
                })
                print(f"✅ [{board_id}] Помощь ({stream}) #{post_num} отправлена в очередь.")
        except asyncio.CancelledError:
            print(f"ℹ️ Воркер помощи для [{board_id}] остановлен.")
            break
        except Exception as e:
            print(f"❌ [{board_id}] Ошибка в board_help_worker: {e}")
            await asyncio.sleep(120)


async def validate_message_format(msg_data: dict) -> bool:

    if not isinstance(msg_data, dict):
        return False
    required = ['recipients', 'content', 'post_num']
    if any(key not in msg_data for key in required):
        return False
    if not isinstance(msg_data['recipients'], (set, list)):
        return False
    if not isinstance(msg_data['content'], dict):
        return False
    if (msg_data['content'].get('type') == 'media_group' and 
        not isinstance(msg_data['content'].get('media'), list)):
        return False
    return True


def _get_thread_entry_keyboard(board_id: str, show_history_button: bool = False, stream: str = 'ru') -> InlineKeyboardMarkup:
    """
    Создает и возвращает инлайн-клавиатуру для сообщения о входе в тред.
    """
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        button_good_thread_text = "👍 Good Thread"
        button_leave_text = "Leave Thread"
    elif lang == 'jp':
        button_good_thread_text = "👍 良スレ"
        button_leave_text = "スレッドを出る"
    else:
        button_good_thread_text = "👍 Годный тред"
        button_leave_text = "Выйти из треда"
    keyboard_layout = [
        [
            InlineKeyboardButton(text=button_good_thread_text, callback_data="thread_like_placeholder"),
            InlineKeyboardButton(text=button_leave_text, callback_data="leave_thread")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)


# --- Media Group and Broadcaster Logic ---
# current_media_groups and media_group_timers come from shared_state (imported via *)
# DO NOT redefine them here — that would create local shadows disconnected from message_router.py


def _release_media_group_timer(media_group_key: str) -> None:
    """
    Снимает запись таймера альбома, ТОЛЬКО если она принадлежит текущей задаче.

    Каждое новое сообщение альбома отменяет предыдущий таймер и кладёт на его
    место новый. Отменённая задача не должна снести чужую запись, иначе
    недособранный альбом останется без таймера и не будет опубликован.
    Тот же приём, что и для pending_edit_tasks.
    """
    try:
        current = asyncio.current_task()
    except RuntimeError:
        current = None
    if media_group_timers.get(media_group_key) is current:
        media_group_timers.pop(media_group_key, None)

async def complete_media_group_after_delay(media_group_key: str, bot_instance: Bot, delay: float = 1.5):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ)
    Обеспечивает сбор альбома и защиту от краша при очистке очереди.
    """
    try:
        await asyncio.sleep(delay)
        group = current_media_groups.pop(media_group_key, None)
        if not group:
            print(f"⚠️ [MEDIAGRP] {media_group_key}: group уже удалена (race/duplicate timer), пропускаем.")
            return
        if media_group_key in sent_media_groups:
            print(f"ℹ️ [MEDIAGRP] {media_group_key}: уже обработана (dedup), пропускаем.")
            return
        raw_messages = group.get('raw_messages', [])
        if not raw_messages:
            print(f"⚠️ [MEDIAGRP] {media_group_key}: raw_messages пустой! board={group.get('board_id')} author={group.get('author_id')} — альбом потерян.")
            return
        raw_messages.sort(key=lambda m: m.message_id)
        found_caption = ""
        for msg in raw_messages:
            if msg.caption:
                raw_caption_html = getattr(msg, 'caption_html_text', msg.caption)
                found_caption = main.sanitize_html(raw_caption_html)
                break
        group['caption'] = found_caption
        final_media_list = []
        # Личность альбома для определения баяна. file_unique_id Telegram отдаёт
        # прямо в апдейте, поэтому ничего не качаем и не хешируем — как и для
        # одиночных медиа. Одиночный путь (@dp.message(~F.media_group_id))
        # альбомы исключает, поэтому они оставались без проверки.
        album_unique_ids = []
        for msg in raw_messages:
            c_type = str(msg.content_type).split('.')[-1].lower() if msg.content_type else 'photo'
            media_data = {'type': c_type, 'file_id': None}
            media_obj = None
            if msg.photo:
                media_obj = msg.photo[-1]
                media_data['file_id'] = media_obj.file_id
            elif msg.video:
                media_obj = msg.video
                media_data['file_id'] = media_obj.file_id
            elif msg.document:
                media_obj = msg.document
                media_data['file_id'] = media_obj.file_id
            elif msg.audio:
                media_obj = msg.audio
                media_data['file_id'] = media_obj.file_id
            if media_obj:
                file_name = getattr(media_obj, 'file_name', None)
                mime_type = getattr(media_obj, 'mime_type', None)
                if file_name:
                    media_data['filename'] = file_name
                if mime_type:
                    media_data['mime_type'] = mime_type
            if media_data['file_id']:
                final_media_list.append(media_data)
                uid = getattr(media_obj, 'file_unique_id', None)
                if uid:
                    album_unique_ids.append(uid)
        group['media'] = final_media_list
        # Считаем баян по альбому ЦЕЛИКОМ: ключ — отсортированный набор
        # file_unique_id. Так «БАЯН» означает «этот же набор картинок уже
        # постили», без ложных срабатываний на свежий альбом, куда попала одна
        # старая картинка. И это одна строка в БД на альбом, а не N.
        if album_unique_ids:
            import hashlib
            group['album_unique_key'] = hashlib.sha256(
                "|".join(sorted(album_unique_ids)).encode('utf-8')
            ).hexdigest()
        await process_complete_media_group(media_group_key, group, bot_instance)
        current_media_groups.pop(media_group_key, None)
        # --- ИЗМЕНЕНИЕ: Удалена опасная строка sent_media_groups.remove ---
        # Объекты в sent_media_groups (deque с maxlen) удаляются сами при переполнении.
        # Попытка удалить их вручную вызывала ValueError, если ID уже вытеснен.
    except asyncio.CancelledError:
        # Таймер заменён более свежим сообщением альбома: current_media_groups
        # НЕ трогаем — группу продолжает собирать новая задача.
        pass
    except Exception as e:
        import traceback
        print(f"❌ [MEDIAGRP] Ошибка в complete_media_group_after_delay для {media_group_key}: {e}")
        traceback.print_exc()
        current_media_groups.pop(media_group_key, None)
    finally:
        _release_media_group_timer(media_group_key)

async def process_complete_media_group(media_group_key: str, group: dict, bot_instance: Bot):
    if not group or not group.get('media'):
        return
    main.sent_media_groups.append(media_group_key)
    sent_media_groups.append(media_group_key)  # shared_state deque — read by message_router for dedup
    user_id = group['author_id']
    board_id = group['board_id']
    stream = group.get('stream', 'ru')
    b_data = board_data[board_id]
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if user_settings.get('shadow_media'):
        is_shadow_muted = True
    all_media = group.get('media',[])
    CHUNK_SIZE = 10
    CAPTION_LENGTH_LIMIT = 900
    media_chunks = [all_media[i:i + CHUNK_SIZE] for i in range(0, len(all_media), CHUNK_SIZE)]
    is_large_group = len(media_chunks) > 1
    original_caption = group.get('caption')
    is_long_caption = original_caption and len(original_caption) > CAPTION_LENGTH_LIMIT
    send_caption_separately = is_large_group or is_long_caption
    first_post_num = None

    # Баян по альбому. Шэдоу-мут не считаем: пост никто не увидит, счётчик врал бы.
    album_repost_count = 0
    album_key = group.get('album_unique_key')
    if album_key and not is_shadow_muted:
        from common.database import register_media_repost
        album_repost_count = await register_media_repost(board_id, album_key)

    for i, chunk in enumerate(media_chunks):
        if not chunk: continue
        reply_to_post = group.get('reply_to_post') if i == 0 else None
        caption_for_chunk = original_caption if not send_caption_separately else None
        content = {
            'type': 'media_group',
            'media': chunk,
            'caption': caption_for_chunk
        }
        # Метка только на первый чанк: большой альбом режется на посты по 10,
        # дублировать «БАЯН» на каждом смысла нет.
        if i == 0 and album_repost_count > 1:
            content['repost_count'] = album_repost_count
        
        # --- НАЧАЛО ИЗМЕНЕНИЙ (Добавлена Быстрая цитата для альбомов) ---
        from handlers.message_router import process_shadow_reject, build_quick_quote_info
        quote_info = await build_quick_quote_info(reply_to_post)
        if quote_info:
            content['quote_info'] = quote_info
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---
        
        if is_shadow_muted:
            await process_shadow_reject(shared_state.ShadowRejectContext(
                bot=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=content,
                reply_to_post=reply_to_post,
                stream=stream
            ))
            if is_large_group: await asyncio.sleep(1)
            continue
        post_num = await process_new_post(shared_state.NewPostParams(
            bot_instance=bot_instance,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        ))
        if i == 0:
            first_post_num = post_num
        if is_large_group:
            await asyncio.sleep(1)
            
    if send_caption_separately and original_caption:
        text_content = {'type': 'text', 'text': original_caption}
        if is_shadow_muted:
            await process_shadow_reject(shared_state.ShadowRejectContext(
                bot=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=text_content,
                reply_to_post=None,
                stream=stream
            ))
        elif first_post_num:
            await process_new_post(shared_state.NewPostParams(
                bot_instance=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=text_content,
                reply_to_post=first_post_num,
                is_shadow_muted=False, stream=stream
            ))

    if first_post_num:
        first_photo_id = None
        for m in all_media:
            if m.get('type') == 'photo' and m.get('file_id'):
                first_photo_id = m['file_id']
                break
        is_reply_to_bot = group.get('reply_to_post') is not None
        should_reply = False
        if is_reply_to_bot:
            now_t = time.time()
            last_user_t = main._last_persona_dialogue_user_ts.get(user_id, 0)
            if (now_t - last_user_t >= 45.0) and (random.random() < 0.35):
                should_reply = True
                main._last_persona_dialogue_user_ts[user_id] = now_t
        elif user_id in b_data.get('persona_favorites', {}):
            now_t_fav = time.time()
            if (now_t_fav - main._last_persona_board_ts.get(board_id, 0) >= 90.0) and random.random() < 0.08:
                should_reply = True
        else:
            # Глобальный пассивный тригер: 4% на любой пост на борде
            now_t_glob = time.time()
            if (now_t_glob - main._last_persona_board_ts.get(board_id, 0) >= 120.0) and random.random() < 0.04:
                should_reply = True

        if should_reply:
            main._last_persona_board_ts[board_id] = time.time()  # заблокировать до spawn чтобы не было race condition
            text_chunk = original_caption or "[альбом изображений]"
            spawn_task(main.schedule_persona_reply(bot_instance, board_id, first_post_num, text_chunk, stream, is_admin_trigger=False, photo_file_id=first_photo_id, is_dialogue=is_reply_to_bot))
            # --- THE ANCHOR (Мудрый Чед) ---
        from anchor_bot import anchor_tick, trigger_anchor_post
        if anchor_tick(board_id):
            spawn_task(trigger_anchor_post(bot_instance, board_id, stream))

async def thread_notifier():
    """
    Фоновая задача для уведомления пользователей в общем чате об активности в тредах.
    """
    global last_checked_post_counter_for_notify
    await asyncio.sleep(45)
    state = shared_state.state
    last_checked_post_counter_for_notify = state.get('post_counter', 0)
    while True:
        await asyncio.sleep(300) # Проверка каждые 5 минут
        now_dt = datetime.now(UTC) # Определяем время один раз
        current_post_counter = state.get('post_counter', 0)
        if current_post_counter > last_checked_post_counter_for_notify:
            new_thread_posts_count = defaultdict(lambda: defaultdict(int))
            async with storage_lock: # Безопасно читаем данные
                posts_slice = {k: v for k, v in messages_storage.items() if k > last_checked_post_counter_for_notify}
            for p_num, post_data in posts_slice.items():
                b_id = post_data.get('board_id')
                if b_id in THREAD_BOARDS:
                    t_id = post_data.get('thread_id')
                    if t_id: new_thread_posts_count[b_id][t_id] += 1
            last_checked_post_counter_for_notify = current_post_counter
            for board_id, threads in new_thread_posts_count.items():
                b_data = board_data[board_id]
                threads_data = get_threads_data(board_id)
                users_on_main = {
                    uid for uid, u_state in b_data.get('user_state', {}).items() 
                    if u_state.get('location', 'main') == 'main'
                }
                for thread_id, count in threads.items():
                    if count >= main.THREAD_NOTIFY_THRESHOLD:
                        thread_info = threads_data.get(thread_id)
                        if not thread_info or thread_info.get('is_archived'): continue
                        thread_stream = thread_info.get('stream', 'ru')
                        if ENABLE_MULTILANG and board_id != 'int':
                            stream_users = await get_stream_active_users(board_id, thread_stream)
                            recipients = users_on_main.intersection(stream_users)
                        else:
                            recipients = users_on_main
                        if not recipients: continue
                        lang = thread_stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                        title = thread_info.get('title', '...')
                        phrases = thread_messages.get(lang, {}).get('thread_activity_notification', ["High activity."])
                        notification_text = random.choice(phrases).format(title=title, count=count)
                        bot_username = BOARD_CONFIG[board_id]['username'].lstrip('@')
                        deeplink_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"
                        button_text = "Зайти в тред" if lang == 'ru' else "Enter Thread"
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=button_text, url=deeplink_url)]
                        ])
                        content = {'type': 'text', 'text': notification_text, 'is_system_message': True}
                        pnum = await create_post(
                            board_id=board_id, author_id=0, content=content,
                            timestamp=now_dt.timestamp(), is_from_site=False, stream='ru'
                        )
                        if not pnum:
                            print(f"⛔ [{board_id}] Не удалось создать пост в БД для уведомления об активности треда {thread_id}.")
                            continue
                        header = await format_header(board_id, pnum)
                        content['header'] = header
                        await update_post_content(pnum, content)
                        async with storage_lock:
                            messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
                        await enqueue_board_message(board_id, {
                            'recipients': recipients, 'content': content, 'post_num': pnum, 'board_id': board_id, 'keyboard': keyboard
                        })
        for board_id in THREAD_BOARDS:
            b_data = board_data[board_id]
            lang = 'en' if board_id == 'int' else 'ru'
            threads_data = get_threads_data(board_id)
            recipients_in_main = {
                uid for uid, u_state in b_data.get('user_state', {}).items() 
                if u_state.get('location', 'main') == 'main'
            }
            if not recipients_in_main: continue
            for thread_id, thread_info in threads_data.items():
                if thread_info.get('is_archived') or thread_info.get('bump_limit_notified'):
                    continue
                current_posts = len(thread_info.get('posts', []))
                remaining = main.MAX_POSTS_PER_THREAD - current_posts
                if 0 < remaining <= main.THREAD_BUMP_LIMIT_WARNING_THRESHOLD:
                    thread_info['bump_limit_notified'] = True
                    title = thread_info.get('title', '...')
                    notification_text = random.choice(thread_messages[lang]['thread_reaching_bump_limit']).format(title=title, remaining=remaining)
                    bot_username = BOARD_CONFIG[board_id]['username'].lstrip('@')
                    deeplink_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"
                    button_text = "Зайти в тред" if lang == 'ru' else "Enter Thread"
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=button_text, url=deeplink_url)]
                    ])
                    content = {'type': 'text', 'text': notification_text, 'is_system_message': True}
                    pnum = await create_post(
                        board_id=board_id, author_id=0, content=content,
                        timestamp=now_dt.timestamp(), is_from_site=False
                    )
                    if not pnum:
                        print(f"⛔ [{board_id}] Не удалось создать пост в БД для уведомления о бамп-лимите треда {thread_id}.")
                        continue
                    header = await format_header(board_id, pnum)
                    content['header'] = header
                    await update_post_content(pnum, content)
                    async with storage_lock:
                        messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
                    await enqueue_board_message(board_id, {
                        'recipients': recipients_in_main, 'content': content, 'post_num': pnum, 'board_id': board_id, 'keyboard': keyboard
                    })

async def site_posts_broadcaster():
    """
    Фоновая задача, которая извлекает посты, созданные на сайте, из очереди в БД
    и транслирует их в Telegram. Реализована логика уведомлений о новых тредах.
    """
    await asyncio.sleep(15)  # Начальная задержка при запуске бота
    while True:
        try:
            if drain_shutdown_requested:
                await asyncio.sleep(2)
                continue
            import common.database
            new_posts = await common.database.get_and_clear_broadcast_queue()
            if new_posts:
                new_posts.sort(key=lambda p: p.get('timestamp', 0))
                for post in new_posts:
                    try:
                        post_num = post.get('post_num')
                        if not post_num:
                            continue
                        if post.get('_broadcast_decode_failed'):
                            await common.database.mark_broadcast_posts_sent([post_num])
                            continue
                        if post_num in messages_storage or post_num in locally_created_posts:
                            await common.database.mark_broadcast_posts_sent([post_num])
                            continue
                        board_id = post.get('board_id')
                        author_id = post.get('author_id')
                        post_stream = post.get('stream', 'ru')
                        post_mode = post.get('post_mode') 
                        thread_id = post.get('thread_id')
                        is_new_thread = (
                            post_mode == 'new_thread'
                            or bool(post.get('is_op_post'))
                            or (thread_id is not None and str(thread_id) == str(post_num))
                        )
                        if not board_id or board_id not in BOARD_CONFIG:
                            await mark_broadcast_posts_sent([post_num])
                            continue
                        b_data = board_data[board_id]
                        content = post.get('content', {})
                        skip_broadcast = False
                        # Под локом только решение и обновление счётчика постов.
                        # format_header ниже — обращение к БД, и раньше оно
                        # выполнялось УДЕРЖИВАЯ storage_lock: фоновый цикл трансляции
                        # постов с сайта подвешивал доставку и реакции на всех
                        # досках на время запроса к базе, на каждый пост из очереди.
                        async with storage_lock:
                            is_banned = author_id in b_data.get('users', {}).get('banned', set())
                            m_until = b_data.get('mutes', {}).get(author_id)
                            is_muted = m_until and m_until > datetime.now(UTC)
                            sm_until = b_data.get('shadow_mutes', {}).get(author_id)
                            is_shadow_muted = sm_until and sm_until > datetime.now(UTC)
                            if is_banned or is_muted or is_shadow_muted:
                                skip_broadcast = True
                            else:
                                state['post_counter'] = max(state.get('post_counter', 0), post_num)
                        if not skip_broadcast:
                                header = await format_header(board_id, post_num, stream=post_stream)
                                source_content = content
                                if is_new_thread:
                                    raw_text = source_content.get('text', '')
                                    clean_text_no_tags = re.sub(r'<[^>]+>', '', raw_text)
                                    decoded_text = main.html.unescape(clean_text_no_tags)
                                    title_preview = (decoded_text[:120] + '...') if len(decoded_text) > 120 else decoded_text
                                    if not title_preview.strip():
                                        title_preview = "Новый тред (медиа-контент)"
                                    site_url = f"https://tgach.top/{board_id}/res/{post_num}.html"
                                    if post_stream == 'en':
                                        notify_text = (
                                            f"🌱 <b>New thread on website!</b>\n\n"
                                            f"📝 {main.html.escape(title_preview)}\n\n"
                                            f"🔗 <a href='{site_url}'>Open on Website</a>"
                                        )
                                    elif post_stream == 'jp':
                                        notify_text = (
                                            f"🌱 <b>サイトで新しいスレが作成されました！</b>\n\n"
                                            f"📝 {main.html.escape(title_preview)}\n\n"
                                            f"🔗 <a href='{site_url}'>サイトで開く</a>"
                                        )
                                    else:
                                        notify_text = (
                                            f"🌱 <b>На сайте создан новый тред!</b>\n\n"
                                            f"📝 {main.html.escape(title_preview)}\n\n"
                                            f"🔗 <a href='{site_url}'>Читать на сайте</a>"
                                        )
                                    content = {
                                        'type': 'text',
                                        'text': notify_text,
                                        'is_system_message': True,
                                        'header': f"### WEBSITE ###\n{header}",
                                        'post_num': post_num,
                                    }
                                    content = _attach_site_media_for_delivery(content, source_content)
                                else:
                                    content = _attach_site_media_for_delivery(content)
                                    content['header'] = header
                                    content['post_num'] = post_num
                                if post.get('reply_to_post_num'):
                                    content['reply_to_post'] = post['reply_to_post_num']
                                # Запись в messages_storage — единственное, что здесь
                                # действительно требует storage_lock. Короткий блок,
                                # без обращений к БД и сети.
                                async with storage_lock:
                                    messages_storage[post_num] = {
                                        'author_id': author_id,
                                        'timestamp': datetime.fromtimestamp(post['timestamp'], UTC),
                                        'content': content,
                                        'board_id': board_id,
                                        'thread_id': post.get('thread_id'),
                                    }
                        if skip_broadcast:
                            await mark_broadcast_posts_sent([post_num])
                            continue
                        base_recipients = b_data['users']['active'] - b_data['users']['banned']
                        if ENABLE_MULTILANG and board_id != 'int':
                            stream_users = await get_stream_active_users(board_id, post_stream)
                            base_recipients = base_recipients.intersection(stream_users)
                        recipients = set()
                        if is_new_thread or not thread_id:
                            recipients = base_recipients
                        else:
                            thread_info = main.get_thread_info(board_id, str(thread_id))
                            if thread_info:
                                subs = thread_info.get('subscribers', set())
                                recipients = subs.intersection(base_recipients)
                        if recipients:
                            enqueued = await enqueue_board_message(board_id, {
                                'recipients': recipients,
                                'content': content,
                                'post_num': post_num,
                                'board_id': board_id,
                                'thread_id': thread_id if not is_new_thread else None
                            })
                            if enqueued:
                                await mark_broadcast_posts_sent([post_num])
                            else:
                                runtime_logger.error(f"[site_posts_broadcaster] enqueue FAILED for #{post_num} board={board_id} — NOT marking as sent")
                            
                            if not content.get('is_system_message') or content.get('archive_allowed'):
                                bot_to_use = main.GLOBAL_BOTS.get(board_id) or main.GLOBAL_BOTS.get('b')
                                if bot_to_use:
                                    spawn_task(main._forward_post_to_realtime_archive(
                                        bot_instance=bot_to_use,
                                        board_id=board_id,
                                        post_num=post_num,
                                        content=content,
                                        is_shadow_muted=is_shadow_muted
                                    ))
                        else:
                            await mark_broadcast_posts_sent([post_num])
                    except Exception as item_err:
                        runtime_logger.error(f"[site_posts_broadcaster] Error processing broadcast item {post}: {item_err}", exc_info=True)
            await asyncio.sleep(5) 
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⛔ ОШИБКА в site_posts_broadcaster: {e}")
            await asyncio.sleep(10)
def _site_public_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    url = str(raw_url).strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"{main.SITE_PUBLIC_BASE_URL}{url}"
    return f"{main.SITE_PUBLIC_BASE_URL}/{url.lstrip('/')}"


def _site_media_item(file_info: dict) -> dict | None:
    send_type = main._site_file_send_type(file_info)
    source = main._site_file_source(file_info)
    if not send_type or not source:
        return None
    return {
        "type": send_type,
        "media": source,
        "file_id": source,
        "mime_type": file_info.get("mime_type"),
        "filename": file_info.get("filename"),
    }

def _attach_site_media_for_delivery(content: dict, source_content: dict | None = None) -> dict:
    files = (source_content or content).get("files")
    if not isinstance(files, list) or not files:
        return content

    media_items = [
        item for item in (_site_media_item(file_info) for file_info in files if isinstance(file_info, dict))
        if item
    ]
    if not media_items:
        return content

    delivery_content = content.copy()
    delivery_content["caption"] = delivery_content.get("caption") or delivery_content.get("text") or ""
    delivery_content["files"] = files

    album_supported = {"photo", "video", "document", "audio"}
    album_items = [item for item in media_items if item["type"] in album_supported]
    if len(album_items) > 1:
        delivery_content["type"] = "media_group"
        delivery_content["media"] = album_items[:10]
        delivery_content.pop("file_id", None)
        delivery_content.pop("image_url", None)
        return delivery_content

    first_item = media_items[0]
    delivery_content["type"] = first_item["type"]
    delivery_content["file_id"] = first_item["file_id"]
    first_file = files[0] if isinstance(files[0], dict) else {}
    public_url = _site_public_url(first_file.get("original_url") or first_file.get("thumbnail_url"))
    if public_url:
        delivery_content["image_url"] = public_url
    return delivery_content

