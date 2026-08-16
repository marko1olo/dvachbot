import shared_state
import asyncio
import logging
import re
import html
import random
import time
import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Tuple
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaAnimation
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError
import aiohttp

from common.board_config import BOARD_CONFIG
from common.html_utils import escape_html
from common.task_manager import spawn_task
from common.database import update_post_content, add_channel_copy, create_post, get_stream_active_users

from text_assets import VERIFICATION_SUCCESS_MESSAGES
from shared_state import *
from archive_manager import _forward_post_to_realtime_archive, post_special_num_to_channel
from broadcaster import send_message_to_users
from media_utils import _download_image_with_proxy, _resize_image_if_needed
from post_helpers import format_header, format_thread_post_header, apply_shadow_autoreplace, check_post_numerals, execute_auto_roast
from thread_texts import thread_messages
from utils import split_text
import __main__ as main

UTC = timezone.utc

async def update_user_verification_stats(user_id: int, board_id: str, bot: Bot, stream: str):
    if user_id <= 0: return
    
    from common.db_pool import get_pool, db_lock
    db = await get_pool()

    # Функция спавнится на КАЖДЫЙ пост, а db_lock сериализует весь доступ к базе
    # в процессе. Поздравление о верификации отправляем уже после выхода из
    # лока, иначе сетевой вызов Telegram останавливал бы работу с БД во всём боте.
    should_notify = False
    async with db_lock:
        try:
            await db.execute("BEGIN IMMEDIATE")
            
            await db.execute(
                """
                INSERT INTO Users (user_id, board_id, posts_count) 
                VALUES (?, ?, 1) 
                ON CONFLICT(user_id, board_id) DO UPDATE SET 
                posts_count = Users.posts_count + 1
                """,
                (user_id, board_id)
            )
            
            cursor = await db.execute(
                """
                UPDATE Users 
                SET is_verified_b = 1 
                WHERE user_id = ? AND board_id = ? 
                AND posts_count >= 10 AND is_verified_b = 0
                """,
                (user_id, board_id)
            )
            
            should_notify = cursor.rowcount > 0

            await db.execute("COMMIT")

        except Exception as e:
            should_notify = False
            try:
                await db.execute("ROLLBACK")
            except Exception:
                import traceback; traceback.print_exc()
            print(f"⚠️ Ошибка верификации для {user_id}: {e}")

    if should_notify:
        lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
        msg_text = VERIFICATION_SUCCESS_MESSAGES.get(lang, VERIFICATION_SUCCESS_MESSAGES['ru'])
        try:
            await bot.send_message(user_id, msg_text, parse_mode="HTML")
        except Exception:
            import traceback; traceback.print_exc()

@dataclass
class NewPostContext:
    bot_instance: Bot
    board_id: str
    user_id: int
    content: dict
    reply_to_post: int | None
    is_shadow_muted: bool
    stream: str = 'ru'

class NewPostProcessor:
    def __init__(self, context: NewPostContext):
        self.bot_instance = context.bot_instance
        self.board_id = context.board_id
        self.user_id = context.user_id
        self.content = context.content.copy()
        self.reply_to_post = context.reply_to_post
        self.is_shadow_muted = context.is_shadow_muted
        self.stream = context.stream

        self.b_data = board_data.get(self.board_id, {})
        self.current_post_num = None
        self.thread_id = None
        self.recipients = set()
        self.reply_info_for_author = {}
        self.author_content = {}
        self.final_content = {}
        self.image_bytes_to_send = None
        self.author_image_bytes = None
        self.author_results = None
        self.fallback_fetchers = self.content.pop('__fallback_fetcher_tasks', [])

    async def _determine_recipients_and_thread(self):
        user_location = self.b_data.get('user_state', {}).get(self.user_id, {}).get('location', 'main')
        if self.board_id in THREAD_BOARDS and user_location != 'main':
            self.thread_id = user_location
            thread_info = self.b_data.get('threads_data', {}).get(self.thread_id)
            if not thread_info or thread_info.get('is_archived'):
                self.b_data.setdefault('user_state', {}).setdefault(self.user_id, {})['location'] = 'main'
                lang = 'en' if self.board_id == 'int' else 'ru'
                try:
                    await self.bot_instance.send_message(self.user_id, random.choice(thread_messages[lang]['thread_not_found']))
                except Exception:
                    import traceback; traceback.print_exc()
                return False
            if self.user_id in thread_info.get('local_mutes', {}) and time.time() < thread_info['local_mutes'][self.user_id]:
                return False
            if self.user_id in thread_info.get('local_shadow_mutes', {}) and time.time() < thread_info['local_shadow_mutes'][self.user_id]:
                self.is_shadow_muted = True
            self.recipients = thread_info.get('subscribers', set()) - {self.user_id}
        else:
            if self.board_id == 'int' or not ENABLE_MULTILANG:
                self.recipients = self.b_data.get('users', {}).get('active', set()) - {self.user_id}
            else:
                stream_users = await get_stream_active_users(self.board_id, self.stream)
                active_stream_users = stream_users.intersection(self.b_data.get('users', {}).get('active', set()))
                self.recipients = active_stream_users - {self.user_id}
        return True

    async def _apply_content_transformations(self):
        apply_transform = None
        try:
            import main
            apply_transform = getattr(main, '_apply_mode_transformations', None)
        except Exception:
            pass
        if not apply_transform:
            try:
                import __main__ as main_entry
                apply_transform = getattr(main_entry, '_apply_mode_transformations', None)
            except Exception:
                pass

        if apply_transform:
            self.author_content = await apply_transform(self.content, self.board_id)
        else:
            self.author_content = self.content.copy()
        if self.user_id > 0:
            from common.db_pool import get_pool
            import time
            db = await get_pool()
            async with db.execute("SELECT cursed_until, active_items FROM Users WHERE user_id = ?", (self.user_id,)) as c:
                async for row in c:
                    is_cursed = False
                    if row[0] and int(time.time()) < row[0]:
                        is_cursed = True
                    if row[1]:
                        try:
                            itms = json.loads(row[1])
                            if itms.get("cursed_until", 0) > int(time.time()):
                                is_cursed = True
                        except Exception:
                            import traceback; traceback.print_exc()
                    if is_cursed:
                        if 'text' in self.author_content and self.author_content['text']:
                            if "[Я ХУЕСОС 🤮]" not in self.author_content['text']:
                                self.author_content['text'] += "\n\n<i>[Я ХУЕСОС 🤮]</i>"
                        break
                        
        self.final_content = apply_shadow_autoreplace(self.author_content)
        self.final_content['reply_to_post'] = self.reply_to_post
        self.author_content['reply_to_post'] = self.reply_to_post
        
        self.image_bytes_to_send = self.final_content.pop('image_bytes', None)
        self.author_image_bytes = self.author_content.pop('image_bytes', None)

    async def _create_post_record(self, now_dt):
        self.current_post_num = await create_post(
            board_id=self.board_id,
            author_id=self.user_id,
            content=self.final_content,
            timestamp=now_dt.timestamp(),
            reply_to=self.reply_to_post,
            is_shadow_muted=self.is_shadow_muted,
            is_from_site=False,
            thread_id_from_bot=self.thread_id,
            stream=self.stream
        )
        if self.current_post_num is not None and self.user_id > 0:
            spawn_task(update_user_verification_stats(self.user_id, self.board_id, self.bot_instance, self.stream))

        if self.current_post_num is None:
            if self.reply_to_post:
                try:
                    lang = 'en' if self.board_id == 'int' else 'ru'
                    error_text = "Error: The post you are replying to has been deleted." if lang == 'en' else "Ошибка: пост, на который вы отвечаете, был удален."
                    await self.bot_instance.send_message(self.user_id, error_text)
                except (TelegramForbiddenError, TelegramBadRequest):
                    import traceback; traceback.print_exc()
            return False

        if not self.is_shadow_muted:
            mark_weekly_active_delivery_user(self.board_id, self.user_id)
        locally_created_posts.append(self.current_post_num)
        self.final_content['post_num'] = self.current_post_num
        self.author_content['post_num'] = self.current_post_num
        return True

    async def _format_and_update_headers(self):
        if self.thread_id:
            thread_info = self.b_data.get('threads_data', {}).get(self.thread_id)
            local_post_num = len(thread_info.get('posts', [])) + 1
            header_text = await format_thread_post_header(self.board_id, local_post_num, self.user_id, thread_info, stream=self.stream)
        else:
            header_text = await format_header(self.board_id, self.current_post_num, author_id=self.user_id, stream=self.stream)
        # Метка баяна идёт первой строкой заголовка. Заголовок и так собирается
        # здесь перед отправкой, поэтому это конкатенация строки — ни одного
        # лишнего запроса к Telegram (реакцией это стоило бы по вызову API
        # на КАЖДОГО получателя).
        repost_count = self.content.get('repost_count')
        if isinstance(repost_count, int) and repost_count > 1:
            header_text = f"🪗 БАЯН ×{repost_count}\n{header_text}"
        self.final_content['header'] = header_text
        self.author_content['header'] = header_text
        await update_post_content(self.current_post_num, self.final_content)
        if self.image_bytes_to_send:
            self.final_content['image_bytes'] = self.image_bytes_to_send
        if self.author_image_bytes:
            self.author_content['image_bytes'] = self.author_image_bytes

    async def _execute_fallback_rescue(self, e):
        print(f"ℹ️ Ошибка отправки поста #{self.current_post_num} по URL. Запускаю 'Спасательный Цикл'...")
        loop = asyncio.get_running_loop()
        fallback_succeeded = False
        initial_url = self.final_content.get('image_url')
        async def initial_fetcher(): return initial_url
        all_fetchers = [initial_fetcher] + self.fallback_fetchers
        random.shuffle(all_fetchers)
        for i, fetcher in enumerate(all_fetchers):
            print(f"  -> Попытка спасения #{i + 1}/{len(all_fetchers)}...")
            try:
                url_to_try = await fetcher()
                if not url_to_try:
                    print("    -> Получен пустой URL, пропускаю.")
                    continue
                download_result = await _download_image_with_proxy(url_to_try)
                if not download_result:
                    print("    -> Скачивание не удалось.")
                    continue
                processed_bytes = await loop.run_in_executor(None, _resize_image_if_needed, download_result[0])
                fallback_content = self.author_content.copy()
                fallback_content.pop('image_url', None)
                fallback_content['image_bytes'] = processed_bytes
                self.author_results = await send_message_to_users(shared_state.BroadcastConfig(
                    bot_instance=self.bot_instance, board_id=self.board_id, recipients={self.user_id},
                    content=fallback_content, reply_info=self.reply_info_for_author
                ))
                if self.author_results:
                    self.final_content.pop('image_url', None)
                    self.final_content['image_bytes'] = processed_bytes
                    fallback_succeeded = True
                    print(f"✅ 'Спасательный Цикл' для поста #{self.current_post_num} успешен.")
                    break
                else:
                    print("    -> Отправка байтов также не удалась. Пробую следующий источник.")
            except Exception as ex:
                print(f"    -> Ошибка в цикле спасения: {type(ex).__name__}: {ex}")
                continue
        if not fallback_succeeded:
            print(f"⚠️ 'Спасательный цикл' не помог для поста #{self.current_post_num}. Ошибка: {e}. Пост будет обработан без message_id автора.")

    async def _send_to_author_with_fallback(self):
        try:
            self.author_results = await send_message_to_users(shared_state.BroadcastConfig(
                bot_instance=self.bot_instance,
                board_id=self.board_id,
                recipients={self.user_id},
                content=self.author_content,
                reply_info=self.reply_info_for_author,
                verbose=False
            ))
        except TelegramBadRequest as e:
            if 'image_url' in self.final_content:
                await self._execute_fallback_rescue(e)
            else:
                print(f"⚠️ Не удалось отправить текстовый пост #{self.current_post_num} автору из-за ошибки: {e}. Пост будет обработан без message_id автора.")
        except Exception as e:
            print(f"⚠️ Не удалось отправить пост #{self.current_post_num} автору из-за сетевой/другой ошибки: {e}. Пост будет обработан без message_id автора.")

    async def _save_to_memory(self, now_dt):
        async with storage_lock:
            state['post_counter'] = max(state.get('post_counter', 0), self.current_post_num)
            if self.thread_id:
                thread_info_safe = self.b_data.get('threads_data', {}).get(self.thread_id)
                if thread_info_safe:
                    thread_info_safe['posts'].append(self.current_post_num)
                    thread_info_safe['last_activity_at'] = time.time()
            content_for_ram = self.final_content.copy()
            content_for_ram.pop('image_bytes', None)
            
            chain_depth = 0
            reply_to = self.final_content.get('reply_to_post')
            if reply_to:
                parent_data = messages_storage.get(reply_to)
                if parent_data:
                    chain_depth = parent_data.get('chain_depth', 0) + 1
                    
            messages_storage[self.current_post_num] = {
                'author_id': self.user_id, 'timestamp': now_dt,
                'content': content_for_ram,
                'author_message_id': None, 'board_id': self.board_id, 'thread_id': self.thread_id,
                'chain_depth': chain_depth
            }
            
            if chain_depth > 0 and chain_depth % 15 == 0:
                try:
                    bot_for_roast = GLOBAL_BOTS.get(self.board_id)
                    stream_to_pass = self.stream if self.stream else 'ru'
                    spawn_task(execute_auto_roast(self.board_id, stream_to_pass, bot_for_roast))
                except Exception as e:
                    print(f"Error triggering auto_roast: {e}")

        # Вторая фаза вынесена из-под storage_lock: внутри неё идёт
        # update_post_content — запись в БД, а это ГОРЯЧИЙ путь, он исполняется
        # на КАЖДЫЙ пост. Раньше на время этого запроса замирал весь доступ к
        # messages_storage / main.post_to_messages / main.message_to_post, то есть
        # доставка и реакции на всех досках.
        if self.author_results and self.author_results[0] and self.author_results[0][1]:
                sent_messages = self.author_results[0][1]
                messages_to_process = sent_messages if isinstance(sent_messages, list) else [sent_messages]
                if self.final_content.get('type') == 'media_group' and messages_to_process:
                    new_media_items = []
                    for msg in messages_to_process:
                        item = {}
                        if msg.photo: item = {'type': 'photo', 'file_id': msg.photo[-1].file_id}
                        elif msg.video: item = {'type': 'video', 'file_id': msg.video.file_id}
                        elif msg.document: item = {'type': 'document', 'file_id': msg.document.file_id}
                        elif msg.audio: item = {'type': 'audio', 'file_id': msg.audio.file_id}
                        if item: new_media_items.append(item)
                    if new_media_items: 
                        self.final_content['media'] = new_media_items
                        self.final_content.pop('image_url', None)
                        self.final_content.pop('image_bytes', None)
                elif messages_to_process:
                    msg = messages_to_process[0]
                    file_id_to_persist = None
                    if msg.photo: file_id_to_persist = msg.photo[-1].file_id
                    elif msg.video: file_id_to_persist = msg.video.file_id
                    elif msg.animation: file_id_to_persist = msg.animation.file_id
                    if file_id_to_persist:
                        self.final_content['file_id'] = file_id_to_persist
                        self.final_content.pop('image_url', None)
                        self.final_content.pop('image_bytes', None)
                await update_post_content(self.current_post_num, self.final_content)
                author_message_ids_to_archive = [m.message_id for m in (sent_messages if isinstance(sent_messages, list) else [sent_messages])]
                messages_to_save = sent_messages if isinstance(sent_messages, list) else [sent_messages]
                async with storage_lock:
                    stored = messages_storage.get(self.current_post_num)
                    if stored is not None:
                        stored['author_message_id'] = author_message_ids_to_archive
                        stored['content'] = self.final_content
                    post_to_messages.setdefault(self.current_post_num, {})[self.user_id] = (
                        author_message_ids_to_archive[0] if len(author_message_ids_to_archive) == 1 else author_message_ids_to_archive
                    )
                    for m in messages_to_save:
                        message_to_post[(self.user_id, m.message_id)] = self.current_post_num

    async def _enqueue_and_notify(self):
        p_num = self.current_post_num
        c_type = self.final_content.get('type', 'text')
        t_info = f" (тред: #{self.thread_id})" if self.thread_id else ""
        recip_count = len(self.recipients) if self.recipients else 0
        try:
            print(f"📥 Пост #{p_num} [/{self.board_id}/]{t_info} получен (тип: {c_type}, получателей: {recip_count})")
        except Exception:
            try:
                print(f"[Received] Post #{p_num} [/{self.board_id}/]{t_info} (type: {c_type}, recipients: {recip_count})")
            except Exception:
                pass

        if not self.is_shadow_muted and self.recipients:
            from delivery_manager import enqueue_board_message
            await enqueue_board_message(self.board_id, {
                'recipients': self.recipients, 'content': self.final_content, 'post_num': self.current_post_num,
                'board_id': self.board_id, 'thread_id': self.thread_id
            })
        if not self.final_content.get('is_system_message') or self.final_content.get('archive_allowed'):
            spawn_task(_forward_post_to_realtime_archive(
                bot_instance=self.bot_instance, board_id=self.board_id, post_num=self.current_post_num, content=self.final_content, is_shadow_muted=self.is_shadow_muted
            ))
        numeral_level = check_post_numerals(self.current_post_num)
        if numeral_level:
            spawn_task(post_special_num_to_channel(
                bots=GLOBAL_BOTS, board_id=self.board_id, post_num=self.current_post_num,
                level=numeral_level, content=self.final_content, author_id=self.user_id
            ))
        if self.thread_id:
            thread_info = self.b_data.get('threads_data', {}).get(self.thread_id)
            if thread_info:
                posts_count = len(thread_info.get('posts', []))
                milestones = [50, 150, 220]
                if posts_count in milestones and posts_count not in thread_info.get('announced_milestones', []):
                    thread_info.setdefault('announced_milestones', []).append(posts_count)
                    spawn_task(post_thread_notification_to_channel(
                        bots=GLOBAL_BOTS, board_id=self.board_id, thread_id=self.thread_id,
                        thread_info=thread_info, event_type='milestone',
                        details={'posts': posts_count}
                    ))
        if self.user_id in self.b_data.get('troll_targets', set()):
            pass

    async def execute(self):
        try:
            if not await self._determine_recipients_and_thread():
                return None

            now_dt = datetime.now(UTC)
            await self._apply_content_transformations()

            if not await self._create_post_record(now_dt):
                return None

            try:
                await self._format_and_update_headers()
            except Exception as e:
                print(f"⚠️ Ошибка при форматировании заголовков для поста #{self.current_post_num}: {e}")

            try:
                await self._send_to_author_with_fallback()
            except Exception as e:
                print(f"⚠️ Ошибка при отправке подтверждения автору поста #{self.current_post_num}: {e}")

            try:
                await self._save_to_memory(now_dt)
            except Exception as e:
                print(f"⚠️ Ошибка при сохранении в память поста #{self.current_post_num}: {e}")

            try:
                await self._enqueue_and_notify()
            except Exception as e:
                print(f"⚠️ Ошибка при добавлении в очередь поста #{self.current_post_num}: {e}")

            return self.current_post_num
        except Exception as e:
            import traceback
            print(f"🔥🔥🔥 ФАТАЛЬНАЯ ОШИБКА в process_new_post для user {self.user_id}: {e}\n{traceback.format_exc()}")
            return self.current_post_num if getattr(self, 'current_post_num', None) else None


def mark_weekly_active_delivery_user(board_id: str, user_id: int):
    if not PRIORITY_DELIVERY_ENABLED or user_id <= 0:
        return
    weekly_active_users.setdefault(board_id, set()).add(user_id)


async def post_thread_notification_to_channel(bots: dict[str, Bot], board_id: str, thread_id: str, thread_info: dict, event_type: str, details: dict | None = None):
    """
    Отправляет унифицированное уведомление о событиях треда в служебный канал.
    :param bots: Словарь с инстансами ботов.
    :param board_id: ID доски.
    :param thread_id: ID треда.
    :param thread_info: Словарь с данными треда.
    :param event_type: Тип события ('new_thread', 'milestone', 'high_activity').
    :param details: Дополнительная информация (например, {'posts': 150} или {'activity': 25.5}).
    """
    bot_instance = bots.get(ARCHIVE_POSTING_BOT_ID)
    if not bot_instance:
        print(f"⛔ Ошибка: бот для постинга ('{ARCHIVE_POSTING_BOT_ID}') не найден.")
        return
    details = details or {}
    title = escape_html(thread_info.get('title', 'Без названия'))
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
    message_text = ""
    if event_type == 'new_thread':
        message_text = (
            f"<b>🌱 Создан новый тред</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    elif event_type == 'milestone':
        posts_count = details.get('posts', 0)
        message_text = (
            f"<b>📈 Тред набрал {posts_count} постов</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    elif event_type == 'high_activity':
        activity = details.get('activity', 0)
        message_text = (
            f"<b>🔥 Высокая активность в треде ({activity:.1f} п/ч)</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    else:
        return
    try:
        await bot_instance.send_message(
            chat_id=ARCHIVE_CHANNEL_ID,
            text=message_text,
            parse_mode="HTML"
        )
        print(f"✅ Уведомление о треде '{title}' (событие: {event_type}) отправлено в канал.")
    except Exception as e:
        print(f"⛔ Не удалось отправить уведомление о треде '{title}' в канал: {e}")

async def process_new_post(params: shared_state.NewPostParams) -> int | None:
    """
    Унифицированная функция для обработки, сохранения и постановки в очередь нового поста.
    Версия 8.0: Гарантирует регистрацию поста в памяти даже при сбое отправки. НИКАКИХ УДАЛЕНИЙ.
    """
    context = NewPostContext(
        bot_instance=params.bot_instance,
        board_id=params.board_id,
        user_id=params.user_id,
        content=params.content,
        reply_to_post=params.reply_to_post,
        is_shadow_muted=params.is_shadow_muted,
        stream=params.stream
    )
    processor = NewPostProcessor(context)
    return await processor.execute()
