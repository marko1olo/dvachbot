import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
from shared_state import *
from utils import split_text

def _trim_post_copy_maps_unlocked(max_posts: int) -> tuple[int, int]:
    if max_posts < 0 or len(post_to_messages) <= max_posts:
        return 0, 0
    if max_posts == 0:
        stale_posts = list(post_to_messages)
    else:
        keep_posts = set(sorted(post_to_messages.keys(), reverse=True)[:max_posts])
        stale_posts = [post_num for post_num in post_to_messages if post_num not in keep_posts]
    removed_reverse = 0
    for post_num in stale_posts:
        removed_reverse += _drop_post_copy_maps_unlocked(post_num)
    return len(stale_posts), removed_reverse

def add_you_to_my_posts_fast(text: str, user_id: int, post_authors: dict[int, int]) -> str:
    """Улучшенная версия: не использует замок, работает с переданным словарем авторов."""
    if not text or ">>" not in text:
        return text
    
    matches = RE_YOU_PATTERN.findall(text)
    for post_str in matches:
        try:
            p_num = int(post_str)
            author_id = post_authors.get(p_num)
            if author_id and author_id > 0 and user_id > 0 and author_id == user_id:
                target = f">>{p_num}"
                replacement = f">>{p_num} (You)"
                if target in text and replacement not in text:
                    text = text.replace(target, replacement)
        except ValueError:
            continue
    return text

async def _format_message_body(
    content: dict, 
    user_id_for_context: int, 
    post_data: dict,
    reply_to_post_author_id: int | None,
    quote_info: dict | None = None
) -> str:
    """
    Формирует и форматирует тело сообщения (реакции, reply, опрос, greentext, (You)).
    Версия 2.1: Добавлена поддержка "Быстрой цитаты" (Quick Quote) с защитой от None.
    """
    parts = []

    parts.append(_format_quote_block(quote_info))
    parts.append(_format_reply_line(content, user_id_for_context, reply_to_post_author_id, quote_info))
    parts.append(_format_reactions_block(post_data))

    poll_data = content.get('poll_data')
    if poll_data:
        parts.append(generate_poll_text_display(poll_data))

    parts.append(_format_main_text(content))

    return '\n\n'.join(filter(None, parts))

def _order_recipients_for_delivery(board_id: str, recipients) -> tuple[list[int], int, int]:
    priority, passive = _split_recipients_for_delivery(board_id, recipients)
    if not priority:
        return passive, 0, len(passive)
    return priority + passive, len(priority), len(passive)

class DeliveryResults(list):
    def __init__(self, values=(), remaining_recipients=None, interrupted_reason: str | None = None):
        super().__init__(values)
        self.remaining_recipients = set(remaining_recipients or ())
        self.interrupted_reason = interrupted_reason

async def _build_lie_media_content(content: dict, board_id: str) -> dict:
    ctype = str(content.get('type') or '').split('.')[-1].lower()
    avoid_post_num = content.get('post_num')
    if ctype == 'media_group':
        source_media = content.get('media') or []
        if not source_media:
            return content
        replaced_any = False
        lie_media = []
        used_file_ids = set()
        for item in source_media:
            if not isinstance(item, dict):
                lie_media.append(item)
                continue
            item_type = str(item.get('type') or '').split('.')[-1].lower()
            desired_kind = _lie_media_kind(item_type, item)
            allowed_types = _lie_allowed_send_types(item_type, media_group=True)
            if desired_kind and allowed_types:
                replacement = await _get_lie_archive_media(
                    board_id,
                    desired_kind,
                    allowed_types,
                    avoid_post_num,
                    used_file_ids,
                )
                if replacement:
                    new_item = {
                        'type': replacement['type'],
                        'file_id': replacement['file_id'],
                        'media': replacement['file_id'],
                    }
                    if replacement.get('filename'):
                        new_item['filename'] = replacement['filename']
                    if replacement.get('mime_type'):
                        new_item['mime_type'] = replacement['mime_type']
                    lie_media.append(new_item)
                    used_file_ids.add(replacement['file_id'])
                    replaced_any = True
                    continue
            lie_media.append(item.copy())
        if not replaced_any:
            return content
        lie_content = content.copy()
        lie_content['media'] = lie_media
        return lie_content

    desired_kind = _lie_media_kind(ctype, content)
    allowed_types = _lie_allowed_send_types(ctype)
    if not desired_kind or not allowed_types:
        return content
    replacement = await _get_lie_archive_media(board_id, desired_kind, allowed_types, avoid_post_num)
    if not replacement:
        return content
    lie_content = content.copy()
    lie_content['type'] = replacement['type']
    lie_content['file_id'] = replacement['file_id']
    lie_content.pop('image_url', None)
    lie_content.pop('image_bytes', None)
    lie_content.pop('media', None)
    if replacement.get('filename'):
        lie_content['filename'] = replacement['filename']
    if replacement.get('mime_type'):
        lie_content['mime_type'] = replacement['mime_type']
    return lie_content

class MessageBroadcaster:
    def __init__(self, config: BroadcastConfig):
        self.bot_instance = config.bot_instance
        self.board_id = config.board_id
        self.recipients = config.recipients
        self.content = config.content
        self.reply_info = config.reply_info
        self.keyboard = config.keyboard
        self.verbose = config.verbose
        self.queue_enqueued_at = config.queue_enqueued_at
        self.queue_wait_sec = config.queue_wait_sec
        self.delivery_phase = config.delivery_phase
        self.delivery_original_recipients = config.delivery_original_recipients
        self.delivery_deferred_recipients = config.delivery_deferred_recipients

        # Instance state
        self.b_data = board_data.get(self.board_id) if self.board_id else None
        self.stats = {
            'success': 0,
            'ghosts': 0,
            'errors': 0,
            'blocks': 0,
            'retries': 0,
            'timeouts': 0,
            'priority_recipients': 0,
            'passive_recipients': 0,
        }
        self.media_url_text_fallback = False
        self.media_url_fallback_logged = False
        self.html_plain_fallback_logged = False
        self.all_results = []
        self.blocked_users = set()
        self.mentioned_authors = {}
        self.post_data_copy = {}
        self.reply_to_post_author_id = None
        self.post_num_for_replies = None
        self.db_replies_map = {}
        self.common_formatted_body = None
        self.base_head_html = ""
        self.highlight_head_html = ""
        self.base_header_text = ""
        self.final_keyboard = self.keyboard
        self.post_num = self.content.get('post_num')
        self.raw_text = self.content.get('text') or self.content.get('caption') or ''
        # Переопределяется в _prepare_content_and_mentions, когда известен header.
        self.hide_check_text = self.raw_text.lower()
        self.content_for_common = self.content.copy()

    async def broadcast(self) -> list:
        if not self.recipients or not self.content or 'type' not in self.content:
            return DeliveryResults([], remaining_recipients=set(), interrupted_reason=None)

        if not self.b_data:
            return DeliveryResults([], remaining_recipients=set(), interrupted_reason=None)

        active_recipients = {
            uid for uid in self.recipients
            if uid > 0 and uid not in self.b_data['users']['banned']
        }
        if not active_recipients:
            return DeliveryResults([], remaining_recipients=set(), interrupted_reason=None)

        original_recipients_count = self.delivery_original_recipients or len(active_recipients)
        ordered_recipients, priority_recipients_count, passive_recipients_count = _order_recipients_for_delivery(
            self.board_id, active_recipients
        )
        self.stats['priority_recipients'] = priority_recipients_count
        self.stats['passive_recipients'] = passive_recipients_count

        start_time = time.time()

        await self._prepare_content_and_mentions()

        remaining_recipients_for_later, interrupted_reason, phase_budget_sec = await self._process_delivery_queue(
            ordered_recipients, start_time
        )

        self._log_delivery_metrics(
            active_recipients,
            original_recipients_count,
            start_time,
            remaining_recipients_for_later,
            interrupted_reason,
            phase_budget_sec
        )

        await self._save_copies_to_db()
        await self._remove_blocked_users()

        return DeliveryResults(
            self.all_results,
            remaining_recipients=remaining_recipients_for_later,
            interrupted_reason=interrupted_reason,
        )

    async def _prepare_content_and_mentions(self):
        if self.content.get('poll_data') and not self.final_keyboard:
            poll_options = self.content.get('poll_data', {}).get('options', [])
            if poll_options and self.post_num:
                buttons = []
                for i, option_text in enumerate(poll_options):
                    button_text = option_text[:60]
                    buttons.append(
                        InlineKeyboardButton(
                            text=button_text,
                            callback_data=f"poll_vote_{self.post_num}_{i}"
                        )
                    )
                self.final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])

        async with storage_lock:
            if self.post_num:
                post_data = messages_storage.get(self.post_num, {})
                if post_data:
                    self.post_data_copy = post_data.copy()
            reply_to_post_num = self.content.get('reply_to_post')
            if reply_to_post_num:
                reply_p_data = messages_storage.get(reply_to_post_num, {})
                self.reply_to_post_author_id = reply_p_data.get('author_id')
                self.post_num_for_replies = reply_to_post_num

        if self.post_num_for_replies:
            if not self.reply_to_post_author_id:
                db_post = await get_post_by_num(self.post_num_for_replies)
                if db_post:
                    self.reply_to_post_author_id = db_post.get('author_id')

            in_ram = False
            async with storage_lock:
                if self.post_num_for_replies in post_to_messages:
                    in_ram = True

            if not in_ram:
                db_copies = await get_post_copies(self.post_num_for_replies)
                for rec_id, msg_id in db_copies:
                    self.db_replies_map[rec_id] = msg_id

        self.common_formatted_body = await _format_message_body(
            content=self.content_for_common,
            user_id_for_context=0,
            post_data=self.post_data_copy,
            reply_to_post_author_id=self.reply_to_post_author_id,
            quote_info=self.content_for_common.get('quote_info')
        )

        self.base_header_text = self.content.get('header', '')
        highlight_header_text = self.base_header_text
        if "Пост" in highlight_header_text:
            highlight_header_text = highlight_header_text.replace("Пост", "🔴 Пост", 1)
        elif "Post" in highlight_header_text:
            highlight_header_text = highlight_header_text.replace("Post", "🔴 Post", 1)

        self.base_head_html = f"<i>{escape_html(self.base_header_text)}</i>"
        self.highlight_head_html = f"<i>{escape_html(highlight_header_text)}</i>"

        has_reply_markers = ">>" in self.raw_text
        self.users_settings = self.b_data.get('user_settings', {})
        # Текст для проверки /hide одинаков для всех получателей, а считался
        # заново в _send_one на каждого — конкатенация плюс .lower() по всему
        # телу поста. Готовим один раз на рассылку.
        self.hide_check_text = (self.base_header_text + " " + self.raw_text).lower()

        if has_reply_markers:
            mentions = RE_YOU_PATTERN.findall(self.raw_text)
            if mentions:
                missing_mentions = []
                async with storage_lock:
                    for m_num_str in mentions:
                        try:
                            m_num = int(m_num_str)
                            if m_num in messages_storage:
                                self.mentioned_authors[m_num] = messages_storage[m_num].get("author_id")
                            else:
                                missing_mentions.append(m_num)
                        except ValueError:
                            continue

                if missing_mentions:
                    for m_num in missing_mentions:
                        db_post = await get_post_by_num(m_num)
                        if db_post:
                            self.mentioned_authors[m_num] = db_post.get("author_id")


    async def _process_delivery_queue(self, ordered_recipients, start_time):
        queue = deque(ordered_recipients)
        recipient_retry_counts = defaultdict(int)
        CHUNK_SIZE = DELIVERY_INITIAL_CHUNK_SIZE
        current_delay = 0.1
        phase_budget_sec = _phase_time_budget_sec(self.delivery_phase)
        phase_deadline = start_time + phase_budget_sec if phase_budget_sec else None
        remaining_recipients_for_later = set()
        interrupted_reason = None

        while queue:
            send_timeout_sec = DELIVERY_PER_RECIPIENT_TIMEOUT_SEC
            if phase_deadline is not None:
                remaining_phase_sec = phase_deadline - time.time()
                if remaining_phase_sec <= 0:
                    remaining_recipients_for_later.update(queue)
                    queue.clear()
                    interrupted_reason = "phase_budget"
                    break
                if remaining_phase_sec <= DELIVERY_PHASE_GUARD_SEC:
                    remaining_recipients_for_later.update(queue)
                    queue.clear()
                    interrupted_reason = "phase_budget_guard"
                    break
                send_timeout_sec = min(
                    DELIVERY_PER_RECIPIENT_TIMEOUT_SEC,
                    max(1.0, remaining_phase_sec - DELIVERY_PHASE_GUARD_SEC),
                )
            chunk = []
            for _ in range(min(len(queue), CHUNK_SIZE)):
                chunk.append(queue.popleft())

            tasks = [self._send_one_guarded(uid, send_timeout_sec) for uid in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            flood_wait_seconds = 0

            for uid, res in zip(chunk, results):
                if res == "FATAL_ERROR_STOP":
                    queue.clear()
                    self.stats['errors'] += len(chunk) + len(queue)
                    break
                if isinstance(res, Exception):
                    if isinstance(res, TelegramRetryAfter):
                        wait = res.retry_after
                        recipient_retry_counts[uid] += 1
                        if recipient_retry_counts[uid] <= DELIVERY_MAX_RECIPIENT_RETRIES:
                            flood_wait_seconds = max(flood_wait_seconds, wait)
                            queue.appendleft(uid)
                            self.stats['retries'] += 1
                        else:
                            self.stats['errors'] += 1
                            runtime_logger.warning(
                                "delivery_recipient_retry_exhausted %s",
                                json.dumps(
                                    {
                                        "board_id": self.board_id,
                                        "post_num": self.post_num,
                                        "phase": self.delivery_phase,
                                        "uid": uid,
                                        "retries": recipient_retry_counts[uid],
                                        "reason": "flood_wait",
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            )
                    elif isinstance(res, TelegramForbiddenError):
                        self.blocked_users.add(uid)
                        self.stats['blocks'] += 1
                    elif isinstance(res, (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError)):
                        if isinstance(res, asyncio.TimeoutError):
                            self.stats['timeouts'] += 1
                        recipient_retry_counts[uid] += 1
                        if recipient_retry_counts[uid] <= DELIVERY_MAX_RECIPIENT_RETRIES:
                            queue.append(uid)
                            self.stats['retries'] += 1
                        else:
                            self.stats['errors'] += 1
                            runtime_logger.warning(
                                "delivery_recipient_retry_exhausted %s",
                                json.dumps(
                                    {
                                        "board_id": self.board_id,
                                        "post_num": self.post_num,
                                        "phase": self.delivery_phase,
                                        "uid": uid,
                                        "retries": recipient_retry_counts[uid],
                                        "reason": type(res).__name__,
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            )
                    else:
                        print(f"❌ Ошибка отправки {uid}: {res}")
                        self.stats['errors'] += 1
                elif res:
                    self.all_results.append((uid, res))

            if flood_wait_seconds > 0:
                wait_real = flood_wait_seconds + 1
                if phase_deadline is not None and time.time() + wait_real + DELIVERY_PHASE_GUARD_SEC >= phase_deadline:
                    remaining_recipients_for_later.update(queue)
                    queue.clear()
                    interrupted_reason = "phase_budget_before_floodwait"
                    if self.verbose:
                        print(f"⏳ FloodWait: пауза {wait_real} сек. (перенос бюджета) ...")
                    await asyncio.sleep(wait_real)
                    break
                if self.verbose:
                    print(f"⏳ FloodWait: пауза {wait_real} сек. В очереди: {len(queue)}...")
                await asyncio.sleep(wait_real)
                CHUNK_SIZE = max(DELIVERY_MIN_CHUNK_SIZE, CHUNK_SIZE - 5)
            else:
                await asyncio.sleep(current_delay)
                if CHUNK_SIZE < DELIVERY_INITIAL_CHUNK_SIZE:
                    CHUNK_SIZE += 1

        return remaining_recipients_for_later, interrupted_reason, phase_budget_sec

    def _log_delivery_metrics(
        self,
        active_recipients,
        original_recipients_count,
        start_time,
        remaining_recipients_for_later,
        interrupted_reason,
        phase_budget_sec
    ):
        time_taken = time.time() - start_time
        post_created_at = self.post_data_copy.get("timestamp") if self.post_data_copy else None
        post_age_sec = None
        if isinstance(post_created_at, datetime):
            post_age_sec = max(0.0, time.time() - post_created_at.timestamp())
        elif isinstance(post_created_at, (int, float)):
            post_age_sec = max(0.0, time.time() - float(post_created_at))
        queue_total_sec = None
        if self.queue_enqueued_at is not None:
            try:
                queue_total_sec = max(0.0, time.time() - float(self.queue_enqueued_at))
            except (TypeError, ValueError):
                queue_total_sec = None
        if self.verbose:
            log_line = (
                f"📊 #{self.post_num} [{self.delivery_phase}] | "
                f"✅ {self.stats['success']}/{len(active_recipients)} phase "
                f"({len(active_recipients)}/{original_recipients_count}, def {self.delivery_deferred_recipients}) | "
                f"🚫 {self.stats['blocks']} | "
                f"❌ {self.stats['errors']} | "
                f"👻 {self.stats['ghosts']} | "
                f"🔄 {self.stats['retries']} | "
                f"⏲ {self.stats['timeouts']} | "
                f"⏭ {len(remaining_recipients_for_later)} | "
                f"prio {self.stats['priority_recipients']}/{len(active_recipients)} | "
                f"⏱ {time_taken:.1f}s"
            )
            print(log_line)
            delivery_record = {
                "ts": round(time.time(), 3),
                "board_id": self.board_id,
                "post_num": self.post_num,
                "phase": self.delivery_phase,
                "type": str(self.content.get("type")),
                "recipients": len(active_recipients),
                "phase_recipients": len(active_recipients),
                "original_recipients": original_recipients_count,
                "deferred_recipients": self.delivery_deferred_recipients,
                "priority_recipients": self.stats["priority_recipients"],
                "passive_recipients": self.stats["passive_recipients"],
                "success": self.stats["success"],
                "blocks": self.stats["blocks"],
                "errors": self.stats["errors"],
                "ghosts": self.stats["ghosts"],
                "retries": self.stats["retries"],
                "timeouts": self.stats["timeouts"],
                "budget_deferred": len(remaining_recipients_for_later),
                "interrupted_reason": interrupted_reason,
                "phase_budget_sec": phase_budget_sec,
                "seconds": round(time_taken, 3),
                "post_age_sec": round(post_age_sec, 3) if post_age_sec is not None else None,
                "queue_wait_sec": round(self.queue_wait_sec, 3) if self.queue_wait_sec is not None else None,
                "queue_total_sec": round(queue_total_sec, 3) if queue_total_sec is not None else None,
            }
            delivery_metrics[self.board_id].append(delivery_record)
            runtime_logger.info(
                "delivery_result %s",
                json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
            )
            if time_taken >= DELIVERY_SLOW_PHASE_SEC or (queue_total_sec is not None and queue_total_sec >= DELIVERY_SLOW_PHASE_SEC):
                runtime_logger.warning(
                    "delivery_slow %s",
                    json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
                )
            if remaining_recipients_for_later:
                runtime_logger.warning(
                    "delivery_phase_budget_deferred %s",
                    json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
                )


    async def _save_copies_to_db(self):
        if self.post_num and self.post_num not in posts_pending_deletion and not self.content.get('is_shadow_reject'):
            copies_for_db = []
            trimmed_copy_posts = 0
            trimmed_copy_refs = 0
            async with storage_lock:
                keep_copy_maps_in_ram = self.post_num in messages_storage and MAX_COPY_MAP_POSTS_IN_MEMORY > 0
                for uid, msg_obj_or_list in self.all_results:
                    msgs = msg_obj_or_list if isinstance(msg_obj_or_list, list) else [msg_obj_or_list]
                    if msgs:
                        msg_ids = [m.message_id for m in msgs]
                        for m in msgs:
                            copies_for_db.append((uid, m.message_id))
                        if keep_copy_maps_in_ram:
                            post_to_messages.setdefault(self.post_num, {})[uid] = msg_ids[0] if len(msg_ids) == 1 else msg_ids
                            for m in msgs:
                                message_to_post[(uid, m.message_id)] = self.post_num
                if keep_copy_maps_in_ram:
                    trimmed_copy_posts, trimmed_copy_refs = _trim_post_copy_maps_unlocked(MAX_COPY_MAP_POSTS_IN_MEMORY)
            if trimmed_copy_posts:
                runtime_logger.info(
                    "copy_map_ram_trim %s",
                    json.dumps(
                        {
                            "removed_posts": trimmed_copy_posts,
                            "removed_reverse": trimmed_copy_refs,
                            "limit": MAX_COPY_MAP_POSTS_IN_MEMORY,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            if copies_for_db:
                try:
                    await add_post_copies(self.post_num, copies_for_db)
                except Exception as e:
                    if "FOREIGN KEY constraint failed" in str(e):
                        pass
                    else:
                        print(f"⚠️ Ошибка сохранения копий для #{self.post_num}: {e}")
                        

    async def _remove_blocked_users(self):
        if self.blocked_users:
            users_to_remove_db = []
            for uid in self.blocked_users:
                if uid in self.b_data['users']['active']:
                    self.b_data['users']['active'].discard(uid)
                    users_to_remove_db.append(uid)

            # Раньше здесь чистились только user_settings, last_activity и
            # spam_violations — три хранилища из двенадцати. Это массовый путь,
            # именно он находит большинство заблокировавших бота, поэтому
            # остальное (включая deque с текстами сообщений) утекало.
            freed = await purge_users_from_board_ram(self.board_id, users_to_remove_db)

            if users_to_remove_db:
                from common.database import remove_users_from_board_batch
                await remove_users_from_board_batch(users_to_remove_db, self.board_id)

            print(f"🚫 [{self.board_id}] Удалено {len(self.blocked_users)} пользователей "
                  f"(блокировка бота). Освобождено записей в RAM: {freed}.")

    async def _send_one_guarded(self, uid: int, timeout_sec: float):
        request_timeout_sec = min(
            DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC,
            max(3.0, timeout_sec - 1.0),
        )
        try:
            return await asyncio.wait_for(
                self._send_one(uid, int(request_timeout_sec)),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError as exc:
            runtime_logger.warning(
                "delivery_recipient_timeout %s",
                json.dumps(
                    {
                        "board_id": self.board_id,
                        "post_num": self.post_num,
                        "phase": self.delivery_phase,
                        "uid": uid,
                        "timeout_sec": timeout_sec,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            return exc

    async def _send_one(self, uid: int, telegram_request_timeout_sec: int):
        request_timeout = max(3, int(telegram_request_timeout_sec))
        u_set = self.users_settings.get(uid, {'nsfw': False, 'hide': set()})
        if u_set['hide']:
            check_text = self.hide_check_text
            if any(word in check_text for word in u_set['hide']):
                lang_local = 'en' if self.board_id == 'int' else 'ru'
                placeholder = "🛡 Message hidden" if lang_local == 'en' else "🛡 Сообщение скрыто"
                try:
                    res = await self.bot_instance.send_message(
                        uid,
                        f"{self.base_head_html}\n{placeholder}",
                        parse_mode="HTML",
                        request_timeout=request_timeout,
                    )
                    self.stats['success'] += 1
                    return res
                except Exception:
                    self.stats['errors'] += 1
                    return None
                    
        is_direct_reply = bool(
            self.reply_to_post_author_id is not None 
            and self.reply_to_post_author_id > 0 
            and uid > 0 
            and uid == self.reply_to_post_author_id
        )
        head = self.highlight_head_html if is_direct_reply else self.base_head_html
        body = self.common_formatted_body
        send_content = self.content_for_common
        if u_set.get('lie_media'):
            try:
                send_content = await _build_lie_media_content(self.content_for_common, self.board_id)
                if send_content is not self.content_for_common:
                    body = await _format_message_body(
                        content=send_content,
                        user_id_for_context=uid,
                        post_data=self.post_data_copy,
                        reply_to_post_author_id=self.reply_to_post_author_id,
                        quote_info=send_content.get('quote_info')
                    )
            except Exception as exc:
                runtime_logger.warning(
                    "lie_media_replacement_failed %s",
                    json.dumps(
                        {
                            "board_id": self.board_id,
                            "post_num": self.post_num,
                            "uid": uid,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                send_content = self.content_for_common
        current_content = send_content
        
        if self.mentioned_authors:
            text_with_you = add_you_to_my_posts_fast(self.raw_text, uid, self.mentioned_authors)
            if text_with_you != self.raw_text:
                current_content = send_content.copy()
                target_field = 'text' if 'text' in current_content else 'caption'
                current_content[target_field] = text_with_you
                body = await _format_message_body(
                    content=current_content,
                    user_id_for_context=uid, 
                    post_data=self.post_data_copy,
                    reply_to_post_author_id=self.reply_to_post_author_id,
                    quote_info=current_content.get('quote_info')
                )
        elif is_direct_reply:
             body = await _format_message_body(
                content=current_content,
                user_id_for_context=uid, 
                post_data=self.post_data_copy,
                reply_to_post_author_id=self.reply_to_post_author_id,
                quote_info=current_content.get('quote_info')
            )
        
        full_text = f"{head}\n\n{body}" if body else head
        reply_to_mid = None
        if self.reply_info:
            raw = self.reply_info.get(uid)
            if raw: reply_to_mid = raw[0] if isinstance(raw, list) else raw
            
        if reply_to_mid is None and self.post_num_for_replies:
            async with storage_lock:
                replies_map = post_to_messages.get(self.post_num_for_replies)
                if replies_map:
                    raw = replies_map.get(uid)
                    if raw: reply_to_mid = raw[0] if isinstance(raw, list) else raw

        if reply_to_mid is None and self.post_num_for_replies:
            reply_to_mid = self.db_replies_map.get(uid)

        is_sage = send_content.get('is_sage', False)
        has_spoiler = u_set['nsfw']
        max_attempts = 5

        async def _send_text_fallback(reason: str):
            fallback_text = full_text
            media_url = current_content.get("image_url")
            if media_url and str(media_url) not in fallback_text:
                fallback_text = f"{fallback_text}\n\n{escape_html(str(media_url))}"
            if not self.media_url_fallback_logged:
                runtime_logger.warning(
                    "delivery_media_url_text_fallback %s",
                    json.dumps(
                        {
                            "board_id": self.board_id,
                            "post_num": self.post_num,
                            "phase": self.delivery_phase,
                            "type": str(current_content.get("type")),
                            "reason": reason,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                self.media_url_fallback_logged = True
            sent_msgs = []
            parts = split_text(fallback_text, 4096)
            for i, part in enumerate(parts):
                m = await self.bot_instance.send_message(
                    chat_id=uid,
                    text=part,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_mid if i == 0 else None,
                    reply_markup=self.final_keyboard if i == len(parts) - 1 else None,
                    disable_notification=is_sage,
                    disable_web_page_preview=False,
                    request_timeout=request_timeout,
                )
                sent_msgs.append(m)
            self.stats['success'] += 1
            return sent_msgs

        def _telegram_parse_error(err_low: str) -> bool:
            return (
                "can't parse entities" in err_low
                or "can't find end tag" in err_low
                or "unsupported start tag" in err_low
                or "unmatched end tag" in err_low
                or "can't parse message text" in err_low
            )

        def _plain_delivery_text() -> str:
            plain_head = html.unescape(clean_html_tags(head or ""))
            plain_body = html.unescape(clean_html_tags(body or ""))
            if plain_body:
                text = f"{plain_head}\n\n{plain_body}"
            else:
                text = plain_head
            return text.strip() or "."

        def _log_plain_fallback(reason: str) -> None:
            if self.html_plain_fallback_logged:
                return
            runtime_logger.warning(
                "delivery_html_plain_fallback %s",
                json.dumps(
                    {
                        "board_id": self.board_id,
                        "post_num": self.post_num,
                        "phase": self.delivery_phase,
                        "type": str(current_content.get("type")),
                        "reason": reason,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            self.html_plain_fallback_logged = True

        async def _send_plain_text_parts(
            reason: str,
            text: str | None = None,
            reply_to_id: int | None = None,
            include_keyboard: bool = True,
        ):
            _log_plain_fallback(reason)
            sent_msgs = []
            fallback_text = text if text is not None else _plain_delivery_text()
            parts = split_text(fallback_text, 4096)
            target_reply_id = reply_to_id if reply_to_id is not None else reply_to_mid
            for i, part in enumerate(parts):
                m = await self.bot_instance.send_message(
                    chat_id=uid,
                    text=part,
                    reply_to_message_id=target_reply_id if i == 0 else None,
                    reply_markup=self.final_keyboard if include_keyboard and i == len(parts) - 1 else None,
                    disable_notification=is_sage,
                    disable_web_page_preview=False,
                    request_timeout=request_timeout,
                )
                sent_msgs.append(m)
            self.stats['success'] += 1
            return sent_msgs

        def _plain_media_source(media_type: str):
            if current_content.get("image_bytes"):
                extensions = {'photo': 'jpg', 'animation': 'gif', 'audio': 'mp3', 'voice': 'ogg'}
                ext = extensions.get(media_type, 'mp4')
                return BufferedInputFile(current_content["image_bytes"], filename=f"file.{ext}")
            return current_content.get("file_id") or current_content.get("image_url")

        async def _send_plain_media_fallback(reason: str):
            plain_text = _plain_delivery_text()
            ct = str(current_content.get("type") or "").split('.')[-1].lower()
            if ct == "text":
                return await _send_plain_text_parts(reason, plain_text)
            if ct in {'photo', 'video', 'animation', 'document', 'audio', 'voice'}:
                file_source = _plain_media_source(ct)
                if not file_source:
                    return await _send_plain_text_parts(reason, plain_text)
                common_plain_kwargs = {
                    'chat_id': uid,
                    'reply_to_message_id': reply_to_mid,
                    'reply_markup': self.final_keyboard,
                    'disable_notification': is_sage,
                    'request_timeout': request_timeout,
                }
                if has_spoiler and ct in {'photo', 'video', 'animation'}:
                    common_plain_kwargs['has_spoiler'] = True
                send_method = getattr(self.bot_instance, f"send_{ct}")
                if len(plain_text) > 1024:
                    common_plain_kwargs[ct] = file_source
                    media_msg = await send_method(**common_plain_kwargs)
                    await _send_plain_text_parts(
                        reason,
                        plain_text,
                        reply_to_id=media_msg.message_id,
                        include_keyboard=False,
                    )
                    return media_msg
                common_plain_kwargs['caption'] = plain_text
                common_plain_kwargs[ct] = file_source
                res = await send_method(**common_plain_kwargs)
                _log_plain_fallback(reason)
                self.stats['success'] += 1
                return res
            if ct == "media_group":
                media_group_build = []
                can_fit_caption = len(plain_text) <= 1024
                caption_for_group = plain_text if can_fit_caption else None
                for idx, item in enumerate(current_content.get('media') or []):
                    media_src = item.get('media') or item.get('file_id')
                    if not media_src:
                        continue
                    m_type = str(item.get('type') or '').split('.')[-1].lower()
                    cap = caption_for_group if idx == 0 else None
                    if m_type == 'photo':
                        media_group_build.append(InputMediaPhoto(media=media_src, caption=cap, has_spoiler=has_spoiler))
                    elif m_type == 'video':
                        media_group_build.append(InputMediaVideo(media=media_src, caption=cap, has_spoiler=has_spoiler))
                    elif m_type == 'document':
                        media_group_build.append(InputMediaDocument(media=media_src, caption=cap))
                    elif m_type == 'audio':
                        media_group_build.append(InputMediaAudio(media=media_src, caption=cap))
                if not media_group_build:
                    return await _send_plain_text_parts(reason, plain_text)
                res = await self.bot_instance.send_media_group(
                    chat_id=uid,
                    media=media_group_build,
                    reply_to_message_id=reply_to_mid,
                    disable_notification=is_sage,
                    request_timeout=request_timeout,
                )
                _log_plain_fallback(reason)
                if not can_fit_caption:
                    anchor_msg = res[0] if isinstance(res, list) else res
                    anchor_id = getattr(anchor_msg, "message_id", None)
                    await _send_plain_text_parts(reason, plain_text, reply_to_id=anchor_id, include_keyboard=True)
                    return res
                self.stats['success'] += 1
                return res
            if ct in ['sticker', 'video_note', 'dice']:
                text_result = await _send_plain_text_parts(reason, plain_text)
                if ct == 'dice':
                    await self.bot_instance.send_dice(
                        chat_id=uid,
                        emoji=current_content.get('dice_emoji', '🎲'),
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                elif current_content.get("file_id"):
                    send_method = getattr(self.bot_instance, f"send_{ct}")
                    await send_method(
                        chat_id=uid,
                        **{ct: current_content.get("file_id")},
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                return text_result
            return await _send_plain_text_parts(reason, plain_text)
        
        for attempt in range(max_attempts):
            try:
                ct_raw = current_content["type"]
                ct = str(ct_raw).split('.')[-1].lower()
                common_kwargs = {
                    'chat_id': uid, 
                    'reply_to_message_id': reply_to_mid,
                    'reply_markup': self.final_keyboard,
                    'disable_notification': is_sage,
                    'request_timeout': request_timeout,
                }
                if ct == 'text':
                    parts = split_text(full_text, 4096)
                    sent_msgs = []
                    for i, part in enumerate(parts):
                        m = await self.bot_instance.send_message(
                            chat_id=uid, text=part, parse_mode="HTML",
                            reply_to_message_id=reply_to_mid if i == 0 else None,
                            reply_markup=self.final_keyboard if i == len(parts)-1 else None,
                            disable_notification=is_sage,
                            disable_web_page_preview=False,
                            request_timeout=request_timeout,
                        )
                        sent_msgs.append(m)
                    self.stats['success'] += 1
                    return sent_msgs
                elif ct in ['photo', 'video', 'animation', 'document', 'audio', 'voice']:
                    file_source = None
                    if current_content.get("image_bytes"):
                        if ct == 'photo': 
                            filename = "file.jpg"
                        elif ct == 'animation':
                            filename = "file.gif" 
                        else:
                            filename = "video.mp4"
                        file_source = BufferedInputFile(current_content["image_bytes"], filename=filename)
                    elif current_content.get("file_id"):
                        file_source = current_content["file_id"]
                    elif current_content.get("image_url"):
                        file_source = current_content["image_url"]
                    if not file_source:
                        self.stats['errors'] += 1
                        return None
                    if self.media_url_text_fallback and current_content.get("image_url"):
                        return await _send_text_fallback("cached_bad_media_url")
                    if has_spoiler and ct in ['photo', 'video', 'animation']:
                        common_kwargs['has_spoiler'] = True
                    if len(full_text) > 1024:
                        common_kwargs[ct] = file_source
                        send_method = getattr(self.bot_instance, f"send_{ct}")
                        media_msg = await send_method(**common_kwargs)
                        text_parts = split_text(full_text, 4096)
                        try:
                            for part in text_parts:
                                await self.bot_instance.send_message(
                                    chat_id=uid, text=part, parse_mode="HTML",
                                    reply_to_message_id=media_msg.message_id,
                                    disable_notification=is_sage,
                                    disable_web_page_preview=False,
                                    request_timeout=request_timeout,
                                )
                        except TelegramBadRequest as e:
                            if _telegram_parse_error(e.message.lower()):
                                await _send_plain_text_parts(
                                    "telegram_rejected_html_after_media",
                                    _plain_delivery_text(),
                                    reply_to_id=media_msg.message_id,
                                    include_keyboard=False,
                                )
                                return media_msg
                            raise
                        self.stats['success'] += 1
                        return media_msg
                    else:
                        common_kwargs['caption'] = full_text
                        common_kwargs['parse_mode'] = "HTML"
                        common_kwargs[ct] = file_source
                        send_method = getattr(self.bot_instance, f"send_{ct}")
                        res = await send_method(**common_kwargs)
                        self.stats['success'] += 1
                        return res
                elif ct == "media_group":
                    if not current_content.get('media'):
                        self.stats['errors'] += 1
                        return None
                    
                    can_fit_caption = len(full_text) <= 1024
                    caption_for_group = full_text if can_fit_caption else None
                    
                    media_group_build = []
                    for idx, item in enumerate(current_content['media']):
                        media_src = item.get('media') or item.get('file_id')
                        if not media_src: continue
                        m_type = item['type']
                        cap = caption_for_group if idx == 0 else None
                        
                        if m_type == 'photo':
                            media_group_build.append(InputMediaPhoto(media=media_src, caption=cap, parse_mode="HTML" if cap else None, has_spoiler=has_spoiler))
                        elif m_type == 'video':
                            media_group_build.append(InputMediaVideo(media=media_src, caption=cap, parse_mode="HTML" if cap else None, has_spoiler=has_spoiler))
                        elif m_type == 'document':
                            media_group_build.append(InputMediaDocument(media=media_src, caption=cap, parse_mode="HTML" if cap else None))
                        elif m_type == 'audio':
                            media_group_build.append(InputMediaAudio(media=media_src, caption=cap, parse_mode="HTML" if cap else None))
                    
                    if not media_group_build: 
                        self.stats['errors'] += 1
                        return None

                    res = await self.bot_instance.send_media_group(
                        chat_id=uid, media=media_group_build, 
                        reply_to_message_id=reply_to_mid,
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                    
                    if not can_fit_caption:
                        anchor_msg = res[0] if isinstance(res, list) else res
                        text_parts = split_text(full_text, 4096)
                        try:
                            for part in text_parts:
                                await self.bot_instance.send_message(
                                    chat_id=uid, text=part, parse_mode="HTML",
                                    reply_to_message_id=anchor_msg.message_id,
                                    disable_notification=is_sage,
                                    disable_web_page_preview=True,
                                    request_timeout=request_timeout,
                                )
                        except TelegramBadRequest as e:
                            if _telegram_parse_error(e.message.lower()):
                                await _send_plain_text_parts(
                                    "telegram_rejected_html_after_media_group",
                                    _plain_delivery_text(),
                                    reply_to_id=anchor_msg.message_id,
                                    include_keyboard=True,
                                )
                                return res
                            raise
                    
                    self.stats['success'] += 1
                    return res
                elif ct in ['sticker', 'video_note', 'dice']:
                    if ct == 'dice':
                        await self.bot_instance.send_message(
                            uid,
                            full_text,
                            parse_mode="HTML",
                            reply_to_message_id=reply_to_mid,
                            disable_notification=is_sage,
                            request_timeout=request_timeout,
                        )
                        res = await self.bot_instance.send_dice(
                            chat_id=uid,
                            emoji=current_content.get('dice_emoji', '🎲'),
                            disable_notification=is_sage,
                            request_timeout=request_timeout,
                        )
                    else:
                        common_kwargs[ct] = current_content.get("file_id")
                        send_method = getattr(self.bot_instance, f"send_{ct}")
                        res = await send_method(**common_kwargs)
                    self.stats['success'] += 1
                    return res
            except TelegramBadRequest as e:
                err_low = e.message.lower()
                if _telegram_parse_error(err_low):
                    return await _send_plain_media_fallback("telegram_rejected_html")
                if (
                    current_content.get("image_url")
                    and (
                        "wrong type of the web page content" in err_low
                        or "failed to get http url content" in err_low
                        or "wrong file identifier/http url specified" in err_low
                    )
                ):
                    self.media_url_text_fallback = True
                    return await _send_text_fallback("telegram_rejected_media_url")
                if "too big" in err_low or "file of size" in err_low:
                    if current_content.get('type') == 'media_group' and current_content.get('media'):
                        print(f"⚠️[Anti-Fat] Пост #{self.post_num}: Обнаружен жирный файл. Запуск фильтрации...")
                        clean_media_list = []
                        async with aiohttp.ClientSession() as head_session:
                            for item in current_content['media']:
                                media_obj = item.get('media') or item.get('file_id')
                                should_skip = False
                                if hasattr(media_obj, 'data'):
                                    if len(media_obj.data) > 9_900_000:
                                        print(f"   🗑 Исключен BufferedInputFile ({len(media_obj.data)/1024/1024:.2f} MB)")
                                        should_skip = True
                                elif isinstance(media_obj, bytes):
                                    if len(media_obj) > 9_900_000:
                                        print(f"   🗑 Исключены raw bytes ({len(media_obj)/1024/1024:.2f} MB)")
                                        should_skip = True
                                if should_skip:
                                    continue
                                if isinstance(media_obj, str) and media_obj.startswith('http'):
                                    try:
                                        async with head_session.head(media_obj, timeout=3) as resp:
                                            size = int(resp.headers.get('Content-Length', 0))
                                            if size > 9_500_000:
                                                print(f"   🗑 Исключена жирная ссылка: {size/1024/1024:.2f} MB")
                                                continue 
                                    except Exception:
                                        pass 
                                clean_media_list.append(item)
                        if not clean_media_list:
                            self.stats['errors'] += 1
                            return None 
                        current_content['media'] = clean_media_list
                        await asyncio.sleep(0.5)
                        continue 
                if "message to be replied not found" in err_low:
                    reply_to_mid = None
                    continue 
                elif "chat not found" in err_low or "user not found" in err_low or "blocked" in err_low:
                    raise TelegramForbiddenError(method=e.method, message=e.message)
                elif "flood control" in err_low or "retry after" in err_low:
                    wait_sec = int(re.search(r'\d+', e.message).group()) if re.search(r'\d+', e.message) else 15
                    raise TelegramRetryAfter(method=e.method, message=e.message, retry_after=wait_sec)
                elif "voice_messages_forbidden" in err_low:
                    self.stats['errors'] += 1
                    return None
                elif "wrong remote file identifier" in err_low or "unserialize" in err_low:
                    runtime_logger.warning(f"⚠️ [BROKEN_FILE_ID] Skip bad media for user {uid}: {e}")
                    self.stats['errors'] += 1
                    return None
                else:
                    print(f"⚠️ BadRequest отправки user {uid}: {e}")
                    self.stats['errors'] += 1
                    return None
            except TelegramForbiddenError:
                raise 
            except TelegramRetryAfter:
                raise 
            except (aiohttp.ClientConnectorError, TelegramNetworkError, asyncio.TimeoutError):
                raise TelegramRetryAfter(method="network", message="Network Error", retry_after=5)
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientPayloadError) as e:
                self.stats['ghosts'] += 1
                return None
            except Exception as e:
                self.stats['errors'] += 1
                return None
        return None


async def send_message_to_users(config: BroadcastConfig) -> list:
    """
    Оптимизированная функция массовой рассылки.
    Сложность снижена с O(N*M) до O(N + M) за счет выноса форматирования.
    ВКЛЮЧЕНА ЗАЩИТА ОТ ДУБЛЕЙ (SMART RETRY) И ЛОГИРОВАНИЕ.
    Рассылка с Smart Retry.
    verbose=False -> тихий режим (для отправки автору).
    verbose=True -> пишет отчет в консоль (для массовой).
    """
    broadcaster = MessageBroadcaster(config)
    return await broadcaster.broadcast()
