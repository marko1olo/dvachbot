from common.anon_identity import get_anon_id
import asyncio
import time
from aiogram import Bot
from shared_state import *
try:
    from moderation_config import *
except ImportError:
    import traceback; traceback.print_exc()
from broadcaster import MessageBroadcaster, DeliveryResults, _trim_post_copy_maps_unlocked, _order_recipients_for_delivery, _build_lie_media_content, _format_message_body, add_you_to_my_posts_fast
from utils import split_text
from common.text_utils import clean_html_for_tg
from summarize import summarize_text_with_hf
from common.database import create_post, update_post_content
import itertools
from common.task_manager import spawn_task
import faulthandler
import gc
import psutil
try:
    import ujson as json
except ImportError:
    import json
def _normalize_quote_file_type(raw_type: str | None) -> str:
    if not raw_type: return 'file'
    kind = str(raw_type).lower().strip()
    if kind in {'photo', 'image', 'picture'}: return 'photo'
    if kind in {'video', 'mp4', 'mov'}: return 'video'
    if kind in {'sticker'}: return 'sticker'
    if kind in {'voice', 'audio'}: return 'voice'
    if kind in {'video_note'}: return 'video_note'
    if kind in {'animation', 'gif'}: return 'animation'
    return 'file'

def _quote_info_from_content(replied_content: dict | None) -> dict | None:
    if not isinstance(replied_content, dict):
        return None
    quote_text = replied_content.get('text') or replied_content.get('caption') or ''
    files = []
    content_type = _normalize_quote_file_type(replied_content.get('type'))
    media_items = replied_content.get('media')
    if isinstance(media_items, list):
        for item in media_items:
            if isinstance(item, dict):
                files.append({'type': _normalize_quote_file_type(item.get('type'))})
            else:
                files.append({'type': 'file'})
    elif media_items:
        files.append({'type': content_type})
    file_items = replied_content.get('files')
    if isinstance(file_items, list):
        for item in file_items:
            if isinstance(item, dict):
                files.append({'type': _normalize_quote_file_type(item.get('type'))})
            else:
                files.append({'type': 'file'})
    if replied_content.get('file_id') or replied_content.get('image_bytes') or replied_content.get('image_url'):
        files.append({'type': content_type})
    if content_type in {'sticker', 'video_note', 'voice'} and not files:
        files.append({'type': content_type})
    if replied_content.get('poll_data'):
        files.append({'type': 'poll'})
    return {
        'text': quote_text,
        'quote_text': quote_text,
        'files': files
    }
import logging
import os
import shutil
import tempfile
import tracemalloc
import uuid
import math
import random
import re
import secrets
import html
import signal


import re
import html
import random
import math
from datetime import datetime, timedelta, timezone
UTC = timezone.utc

from shared_state import *
try:
    from moderation_config import *
except ImportError:
    import traceback; traceback.print_exc()

async def format_thread_post_header(board_id: str, local_post_num: int, author_id: int, thread_info: dict, stream: str = 'ru') -> str:

    b_data = board_data[board_id]
    op_marker = " (OP)" if author_id != 0 and author_id == thread_info.get('op_id') else ""
    post_num_formatted = f"{local_post_num}/{MAX_POSTS_PER_THREAD}{op_marker}"
    msk_now = datetime.now(UTC) + timedelta(hours=3)
    hour = msk_now.hour
    is_night = hour >= 23 or hour < 6
    circle = ""
    rand = random.random()
    if is_night:
        if rand < 0.003: circle = "🌑 "
        elif rand < 0.006: circle = "🌒 "
        elif rand < 0.009: circle = "🌓 "
        elif rand < 0.012: circle = "🌔 "
        elif rand < 0.015: circle = "🌝 "
        elif rand < 0.018: circle = "🌙 "
    else:
        if rand < 0.003: circle = "🔴 "
        elif rand < 0.006: circle = "🟢 "
        elif rand < 0.009: circle = "☢️ "
        elif rand < 0.012: circle = "🟡 "
        elif rand < 0.015: circle = "🔵 "
        elif rand < 0.018: circle = "⭐ "
    if b_data['slavaukraine_mode']: return f"💙💛 Пост №{post_num_formatted}"
    if b_data['zaputin_mode']: return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data['anime_mode']: return f"🌸 投稿 {post_num_formatted} 番"
    if b_data['suka_blyat_mode']: return f"💥 Пост №{post_num_formatted}"
    if b_data['polish_mode']: return f"🇵🇱 Post №{post_num_formatted}"
    if b_data.get('schizo_mode'): return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data['warhammer_mode']: return f"⚡ Донесение №{post_num_formatted}"
    if b_data['imperial_mode']: return f"📜 Депеша №{post_num_formatted}"
    if b_data.get('matrix_mode'): return f"🟩 Пакет №{post_num_formatted}"
    if b_data.get('america_mode'): return f"🦅 Freedom Post №{post_num_formatted}"
    if b_data.get('holiday_mode'): return f"🎅 Подарок №{post_num_formatted}"
    if b_data.get('oldweb_mode'): return f"🖥️ Сообщение #{post_num_formatted}"
    if b_data.get('jewish_mode'): return f"📜 Казус №{post_num_formatted}"
    prefix = _get_random_header_prefix(lang=stream)
    if stream == 'en':
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    elif stream == 'jp':
        return f"{circle}{prefix}πâ¼πé╣番 {post_num_formatted}"
    else:
        return f"{circle}{prefix}Пост №{post_num_formatted}"

async def format_header(board_id: str, post_num: int, author_id: int = 0, stream: str = 'ru') -> str:
    """
    Форматирование заголовка с поддержкой VIP префиксов из Теневого Магазина.
    """
    custom_prefix = ""
    if author_id > 0:
        from common.db_pool import get_pool
        import time
        import json
        db = await get_pool()
        has_poop = False
        has_vomit = False
        has_flag_ua = False
        has_flag_ru = False
        prefix_str = ""
        badge_emoji = ""
        COLOR_EMOJIS = {
            "red": "🔴", "green": "🟢", "blue": "🔵", "purple": "🟣",
            "gold": "🟡", "orange": "🟠", "white": "⚪", "black": "🏴", "rainbow": "🌈"
        }
        now_ts = int(time.time())
        async with db.execute("SELECT active_items, custom_prefix, prefix_expires_at FROM Users WHERE user_id = ?", (author_id,)) as c:
            async for row in c:
                if row[0]:
                    try:
                        items = json.loads(row[0])
                        if items.get("shit_until", 0) > now_ts:
                            has_poop = True
                        if items.get("vomit_until", 0) > now_ts:
                            has_vomit = True
                        if items.get("flag_ua_until", 0) > now_ts:
                            has_flag_ua = True
                        if items.get("flag_ru_until", 0) > now_ts:
                            has_flag_ru = True
                        if items.get("badge_color_expires", 0) > now_ts or items.get("badge_color_active"):
                            b_col = items.get("badge_color", "gold")
                            badge_emoji = f"{COLOR_EMOJIS.get(b_col, '🟣')} "
                    except Exception:
                        pass
                if row[1] and row[2] and now_ts < row[2]:
                    prefix_str = f"{row[1]} "
        
        debuff_icons = ("💩 " if has_poop else "") + ("🤮 " if has_vomit else "") + ("🇺🇦 " if has_flag_ua else "") + ("🇷🇺 " if has_flag_ru else "")
        custom_prefix = badge_emoji + debuff_icons + prefix_str
                    
    res = await _format_header_inner(board_id, post_num, stream)
    return custom_prefix + res

def apply_shadow_autoreplace(content: dict) -> dict:
    if not content:
        return content
        
    modified = content.copy()
    
    def replacer(match):
        return random.choice(SHADOW_REPLACEMENTS)
        
    def die_replacer(match):
        matched_text = match.group(1).lower().replace(" ", "")
        if "те" in matched_text:
            return "обоссыте меня"
        return "обоссы меня"
        
    for key in ('text', 'caption'):
        text_val = modified.get(key)
        if text_val:
            words = text_val.split()
            if len(words) <= 12:
                text_val = SHADOW_WORDS_REGEX.sub(replacer, text_val)
                text_val = DIE_WORDS_REGEX.sub(die_replacer, text_val)
                for pattern, replacements in POLITICAL_REPLACEMENTS:
                    text_val = pattern.sub(lambda m, reps=replacements: random.choice(reps), text_val)
                modified[key] = text_val
                
    return modified

def check_post_numerals(post_num: int) -> int | None:
    """
    Проверяет номер поста на наличие повторяющихся цифр в конце (даблы/квадриплы)
    или юбилейных круглых чисел (миллионники, полумиллионники, десятки тысяч).
    Возвращает "уровень редкости" (4..8) или None.
    """
    if post_num < 1000:
        return None

    # Проверка круглых юбилейных чисел
    if post_num >= 1000000 and post_num % 1000000 == 0:
        return 8 # Миллионник
    if post_num >= 500000 and post_num % 500000 == 0:
        return 7 # Полумиллионник
    if post_num >= 100000 and post_num % 100000 == 0:
        return 6 # Сотка тысяч
    if post_num >= 10000 and post_num % 10000 == 0:
        return 5 # Десятитысячник

    s = str(post_num)
    length = len(s)
    last_char = s[-1]
    count = 1
    for i in range(length - 2, -1, -1):
        if s[i] == last_char:
            count += 1
        else:
            break
    if count >= 8:
        return 8
    elif count in SPECIAL_NUMERALS_CONFIG:
        return count
    return None

async def execute_auto_roast(board_id: str, stream: str = 'ru', bot_instance=None):
    b_data = board_data.get(board_id)
    if not b_data: return
    now_ts = time.time()
    
    async with storage_lock:
        last_usage = b_data.get('last_auto_roast_time', 0)
        if now_ts - last_usage < ROAST_COOLDOWN:
            return
        b_data['last_auto_roast_time'] = now_ts

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    msgs = []
    cutoff = time.time() - 3600
    
    async with storage_lock:
        for p_info in reversed(messages_storage.values()):
            if len(msgs) >= 40: break
            if p_info.get('board_id') == board_id:
                ts = p_info.get('timestamp', 0)
                if hasattr(ts, 'timestamp'):
                    ts = ts.timestamp()
                if ts > cutoff:
                    if not p_info.get('thread_id'):
                        msgs.append(p_info)
                
    msgs.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
    
    if not msgs:
        return
        
    chunk_parts = []
    for p in msgs:
        text = p.get('content', {}).get('text', '') if isinstance(p.get('content'), dict) else ''
        if text:
            chunk_parts.append(f"[Anon]: {text}")
            
    chunk = " | ".join(chunk_parts)
    if len(chunk) < 50:
        return
        
    if lang == 'en':
        prompt = random.choice(ROAST_PROMPTS_EN)
    elif lang == 'jp':
        prompt = random.choice(ROAST_PROMPTS_JP)
    else:
        prompt = random.choice(ROAST_PROMPTS)
        
    hf_token = os.getenv("HF_TOKEN")
    try:
        summary = await summarize_text_with_hf(prompt, chunk)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[auto-roast] Error: {e}")
        return
        
    if not summary:
        return
        
    roast_text = f"🔥 <b>АВТО-ПРОЖАРКА СРАЧА</b> 🔥\n\n{summary}" if lang == 'ru' else f"🔥 <b>AUTO-ROAST</b> 🔥\n\n{summary}"
    if lang == 'jp':
        roast_text = f"🔥 <b>自動煽り</b> 🔥\n\n{summary}"
    
    content_payload = {
        'type': 'text',
        'text': roast_text,
        'is_system_message': True,
        'archive_allowed': True
    }
    
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content_payload,
        timestamp=time.time(),
        is_from_site=False,
        stream=stream
    )
    if pnum:
        header = await format_header(board_id, pnum)
        content_payload['header'] = header
        await update_post_content(pnum, content_payload)
        async with storage_lock:
            messages_storage[pnum] = {'author_id': 0, 'timestamp': datetime.now(UTC), 'content': content_payload, 'board_id': board_id}
            
        base_recipients = b_data['users']['active'] - b_data['users']['banned']
        if ENABLE_MULTILANG and board_id != 'int':
            stream_users = await get_stream_active_users(board_id, stream)
            base_recipients = base_recipients.intersection(stream_users)
            
        await enqueue_board_message(board_id, {
            'recipients': base_recipients,
            'content': content_payload,
            'post_num': pnum,
            'board_id': board_id
        })
def _format_post_text(content: dict, msg_type: str) -> str | None:
    text = content.get('text') or content.get('caption') or ""
    text = re.sub(r'<[^>]+>', '', text).strip()
    if text:
        return text
    if msg_type in ('photo', 'video', 'document', 'animation', 'media_group', 'sticker', 'voice', 'video_note'):
        return f"[{msg_type}]"
    return None

def _get_author_name(post: dict, content: dict, board_id: str, lang: str | None) -> str:
    name = content.get('username') or content.get('name') or content.get('author_name')
    if not name:
        if not lang:
            lang = 'en' if board_id == 'int' else 'ru'
        author_id = post.get('author_id')
        if author_id and author_id != 0:
            aid = get_anon_id(author_id, stream=lang)
            if lang == 'en':
                name = f"Anon [{aid}]"
            elif lang == 'jp':
                name = f"名無し [{aid}]"
            else:
                name = f"Анон [{aid}]"
        else:
            if lang == 'en':
                name = "Anon"
            elif lang == 'jp':
                name = "名無し"
            else:
                name = "Анон"
    return name

def _get_reply_suffix(post: dict, content: dict, board_id: str, lang: str | None) -> str:
    reply_to = content.get('reply_to_post') or post.get('reply_to_post_num')
    reply_suffix = ""
    if reply_to:
        if not lang:
            lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            reply_suffix = f" (reply to #{reply_to})"
        elif lang == 'jp':
            reply_suffix = f" (>>{reply_to})"
        else:
            reply_suffix = f" (Ответ на #{reply_to})"
    return reply_suffix


async def delete_single_post(post_num: int, bot_instance: Bot) -> int:
    """
    Удаляет один конкретный пост отовсюду: из БД, RAM, ЛС пользователей и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    """
    board_id = None
    try:
        db = await get_pool()
        async with db.execute("SELECT board_id FROM Posts WHERE post_num = ?", (post_num,)) as cursor:
            row = await cursor.fetchone()
            if row:
                board_id = row[0]
    except Exception:
        import traceback; traceback.print_exc()

    channel_copies = await get_all_channel_copies(post_num)
    messages_to_delete_info = await get_post_copies(post_num)
    deleted_from_db = await delete_post_by_num(post_num)
    if not deleted_from_db and not messages_to_delete_info and not channel_copies:
        return 0
    async with storage_lock:
        post_data = messages_storage.pop(post_num, None)
        if post_data:
            if not board_id:
                board_id = post_data.get('board_id')
            if board_id and board_id in THREAD_BOARDS:
                thread_id = post_data.get('thread_id')
                if thread_id:
                    b_data = board_data.get(board_id, {})
                    threads_data = b_data.get('threads_data', {})
                    if thread_id in threads_data:
                        try:
                            if 'posts' in threads_data[thread_id]:
                                threads_data[thread_id]['posts'].remove(post_num)
                        except (ValueError, KeyError):
                            import traceback; traceback.print_exc()
        message_copies_in_mem = post_to_messages.pop(post_num, {})
        for uid, mid_or_list in message_copies_in_mem.items():
            if isinstance(mid_or_list, list):
                for mid in mid_or_list:
                    message_to_post.pop((uid, mid), None)
            else:
                message_to_post.pop((uid, mid_or_list), None)
    if channel_copies:
        archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
        deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(board_id) or bot_instance)
        for chan_id, msg_id in channel_copies:
            try:
                await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
            except Exception:
                import traceback; traceback.print_exc()
    if not messages_to_delete_info:
        return 0 if deleted_from_db else 0
        
    tasks = [_delete_message_with_retries(bot_instance, uid, mid, board_id) for uid, mid in messages_to_delete_info]
    results = await asyncio.gather(*tasks)
    deleted_count = sum(1 for res in results if res is True)
    return deleted_count

async def delete_thread_atomic(bot_instance: Bot, board_id: str, thread_id: str, notify_users: bool = True, initiator_id: int = None):
    """
    Централизованное и производительное удаление треда.
    """
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})
    thread_info = threads_data.get(thread_id)
    if not thread_info:
        print(f"[THREAD DELETE] Тред {thread_id} не найден на доске {board_id}.")
        return
    posts_to_delete = list(thread_info.get('posts', []))
    users_in_thread = [uid for uid, ustate in b_data.get('user_state', {}).items() if ustate.get('location') == thread_id]
    async with storage_lock:
        for post_num in posts_to_delete:
            messages_storage.pop(post_num, None)
            message_copies = post_to_messages.pop(post_num, {})
            if message_copies:
                for user_id, message_id in message_copies.items():
                    message_to_post.pop((user_id, message_id), None)
        threads_data.pop(thread_id, None)
        b_data.get('thread_locks', {}).pop(thread_id, None)
        for uid in users_in_thread:
            if uid in b_data['user_state']:
                b_data['user_state'][uid]['location'] = 'main'
    if notify_users:
        lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            notify_text = "Thread has been deleted by admin. You have been returned to the main board."
        elif lang == 'jp':
            notify_text = "管理人がスレッドを削除しました。メイン板に戻されました。"
        else:
            notify_text = "Тред был удалён администратором. Вы возвращены на главную доску."
        for uid in users_in_thread:
            try:
                await bot_instance.send_message(uid, notify_text)
            except Exception:
                import traceback; traceback.print_exc()
    print(f"[THREAD DELETE] [{board_id}] Тред {thread_id} удалён. Пользователей переведено: {len(users_in_thread)}. Инициатор: {initiator_id}")

async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
    """
    Массовое удаление постов пользователя за период.
    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
    """
    try:
        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()

        posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete = await _delete_user_posts_from_db(
            user_id, time_threshold_ts, board_id
        )

        if not posts_to_delete_nums:
            return 0

        await _clean_posts_from_ram(posts_to_delete_nums, board_id)
        _clean_posts_from_caches(posts_to_delete_nums)
        await _delete_posts_from_channels(channel_messages_to_delete, bot_instance)
        spawn_task(_delete_posts_from_pm_api(messages_to_delete_from_api, bot_instance))
        
        return len(posts_to_delete_nums)
    except Exception as e:
        import traceback
        print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
        return 0

async def execute_sdel_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
    """
    Теневое удаление постов пользователя за период (sdel wipe).
    Удаляет копии у всех получателей кроме самого автора,
    удаляет из каналов, и помечает посты в БД как is_shadow = 1.
    """
    try:
        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()
        
        from common.db_pool import get_pool, db_lock, db_transaction
        async with db_lock:
            db = await get_pool()
            async with db_transaction(db):
                query = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
                async with db.execute(query, (user_id, board_id, time_threshold_ts)) as cursor:
                    rows = await cursor.fetchall()
                user_posts = [r[0] for r in rows]
                
                if not user_posts:
                    return 0
                    
                posts_json = json.dumps(user_posts)
                
                await db.execute(
                    "UPDATE Posts SET is_shadow = 1 WHERE post_num IN (SELECT value FROM json_each(?))",
                    (posts_json,)
                )
                
                query_copies = """
                    SELECT pc.recipient_id, pc.message_id, p.board_id
                    FROM PostCopies pc
                    JOIN Posts p ON pc.post_num = p.post_num
                    WHERE pc.post_num IN (SELECT value FROM json_each(?))
                      AND pc.recipient_id != ?
                """
                async with db.execute(query_copies, (posts_json, user_id)) as cursor:
                    messages_to_delete_from_api = await cursor.fetchall()
                    
                query_channels = """
                    SELECT cc.channel_id, cc.message_id, p.board_id
                    FROM ChannelCopies cc
                    JOIN Posts p ON cc.post_num = p.post_num
                    WHERE cc.post_num IN (SELECT value FROM json_each(?))
                """
                async with db.execute(query_channels, (posts_json,)) as cursor:
                    channel_messages_to_delete = await cursor.fetchall()
                    
                await db.execute(
                    "DELETE FROM PostCopies WHERE post_num IN (SELECT value FROM json_each(?)) AND recipient_id != ?",
                    (posts_json, user_id)
                )
                await db.execute(
                    "DELETE FROM ChannelCopies WHERE post_num IN (SELECT value FROM json_each(?))",
                    (posts_json,)
                )

        await _delete_posts_from_channels(channel_messages_to_delete, bot_instance)
        spawn_task(_delete_posts_from_pm_api(messages_to_delete_from_api, bot_instance))
        
        async with storage_lock:
            for p_num in user_posts:
                if p_num in messages_storage:
                    messages_storage[p_num]['is_shadow'] = 1
                copies = post_to_messages.get(p_num, {})
                for uid, mid in list(copies.items()):
                    if uid != user_id:
                        if isinstance(mid, list):
                            for m in mid: message_to_post.pop((uid, m), None)
                        else:
                            message_to_post.pop((uid, mid), None)
                        copies.pop(uid, None)
                        
        return len(user_posts)
    except Exception as e:
        import traceback
        print(f"Критическая ошибка в execute_sdel_user_posts: {e}\n{traceback.format_exc()}")
        return 0

def _get_random_header_prefix(lang: str = 'ru') -> str:

    rand_prefix = random.random()
    if lang == 'en':
        if rand_prefix < 0.005: return "### ADMIN ### "
        if rand_prefix < 0.008: return "Me - "
        if rand_prefix < 0.01: return "Faggot - "
        if rand_prefix < 0.012: return "### DEGENERATE ### "
        if rand_prefix < 0.016: return "Biden - "
        if rand_prefix < 0.021: return "EMPEROR CONAN - "
        if rand_prefix < 0.023: return "### TRANNY ### "
        if rand_prefix < 0.05: return "Anon - " # Чаще для английского
        return ""
    if lang == 'jp':
        if rand_prefix < 0.005: return "### 管理人 ### " # Kanrinin (Admin)
        if rand_prefix < 0.008: return "俺 - " # Ore (Me)
        if rand_prefix < 0.01: return "ホモ - " # Homo (Faggot)
        if rand_prefix < 0.012: return "### 変質者 ### " # Henshitsu-sha (Degenerate)
        if rand_prefix < 0.016: return "岸田 - " # Kishida (PM context)
        if rand_prefix < 0.021: return "コナン皇帝 - " # Emperor Conan
        if rand_prefix < 0.023: return "### オカマ ### " # Okama (Tranny)
        if rand_prefix < 0.030: return "お前 - " # Omae (You)
        if rand_prefix < 0.040: return "暇人 - " # Himajin (Bitard/Neet)
        if rand_prefix < 0.08: return "名無し - " # Nanashi (Anon) - самый частый
        return ""
    if rand_prefix < 0.005: return "### АДМИН ### "
    if rand_prefix < 0.008: return "Абу - "
    if rand_prefix < 0.01: return "Пидор - "
    if rand_prefix < 0.012: return "### ДЖУЛУП ### "
    if rand_prefix < 0.014: return "### Хуесос ### "
    if rand_prefix < 0.016: return "Пыня - "
    if rand_prefix < 0.018: return "Нариман Намазов - "
    if rand_prefix < 0.021: return "ИМПЕРАТОР КОНАН - "
    if rand_prefix < 0.023: return "Антон Бабкин - "
    if rand_prefix < 0.025: return "НАРИМАН НАМАЗОВ - "
    if rand_prefix < 0.027: return "ПУТИН - "
    if rand_prefix < 0.028: return "Гей - "
    if rand_prefix < 0.030: return "Анархист - "
    if rand_prefix < 0.033: return "Имбецил - "
    if rand_prefix < 0.035: return "### ЧМО ### "
    if rand_prefix < 0.037: return "### ОНАНИСТ ### "
    if rand_prefix < 0.040: return "### ЧЕЧЕНЕЦ ### "
    if rand_prefix < 0.042: return "АААААААА - "
    if rand_prefix < 0.044: return "### Аниме девочка ### "
    if rand_prefix < 0.046: return "ChatGPT 5.4 - "
    if rand_prefix < 0.048: return "Безумец - "
    if rand_prefix < 0.050: return "Битард - "
    if rand_prefix < 0.052: return "Мегумин - "
    if rand_prefix < 0.054: return "Гопник - "
    if rand_prefix < 0.056: return "Шизик - "
    if rand_prefix < 0.058: return "Джефри Эпштейн - "
    if rand_prefix < 0.060: return "Максим Тесак - "
    if rand_prefix < 0.062: return "Навальный - "
    if rand_prefix < 0.064: return "Рамзанка дыров - "
    if rand_prefix < 0.066: return "СВОШНИК - "
    if rand_prefix < 0.068: return "Герой Украины - "
    if rand_prefix < 0.070: return "Claude Opus 4.6 - "
    if rand_prefix < 0.076: return "Администратор - "
    if rand_prefix < 0.08: return "Админ - "
    if rand_prefix < 0.085: return "Модератор - "
    if rand_prefix < 0.1: return "Анон - "
    if rand_prefix < 0.115: return "Анонимус - "
    if rand_prefix < 0.13: return "Анонимный пользователь - "
    if rand_prefix < 0.132: return "Мочекрад - "
    if rand_prefix < 0.134: return "Семён - "
    if rand_prefix < 0.136: return "Макака - "
    if rand_prefix < 0.138: return "РНН-господин - "
    if rand_prefix < 0.140: return "Омеган - "
    if rand_prefix < 0.142: return "Сыч - "
    if rand_prefix < 0.144: return "Куколд - "
    if rand_prefix < 0.146: return "Хач - "
    if rand_prefix < 0.148: return "Педофил - "
    if rand_prefix < 0.150: return "Зеленский - "
    if rand_prefix < 0.152: return "Мыкола - "
    return ""

async def _format_header_inner(board_id: str, post_num: int, stream: str = 'ru') -> str:
    board_data[board_id].setdefault('board_post_count', 0)
    board_data[board_id]['board_post_count'] += 1
    post_num_formatted = str(post_num)
    msk_now = datetime.now(UTC) + timedelta(hours=3)
    hour = msk_now.hour
    is_night = hour >= 23 or hour < 6
    circle = ""
    rand = random.random()
    if is_night:
        if rand < 0.003: circle = "🌑 "
        elif rand < 0.006: circle = "🌒 "
        elif rand < 0.009: circle = "🌓 "
        elif rand < 0.012: circle = "🌔 "
        elif rand < 0.015: circle = "🌝 "
        elif rand < 0.018: circle = "🌌 "
    else:
        if rand < 0.003: circle = "🔴 "
        elif rand < 0.006: circle = "🟢 "
        elif rand < 0.009: circle = "☢️ "
        elif rand < 0.012: circle = "🟡 "
        elif rand < 0.015: circle = "🔵 "
        elif rand < 0.018: circle = "⭕ "
    if board_id == 'int':
        prefix = _get_random_header_prefix(lang='en')
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    b_data = board_data[board_id]
    if b_data['slavaukraine_mode']:
        headers = [f"💙💛 Пiст №{post_num_formatted}", f"🇺🇦 Повiдомлення №{post_num_formatted}"]
        return random.choice(headers)
    if b_data['zaputin_mode']:
        return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data['anime_mode']:
        return f"🌸 投稿 {post_num_formatted} 番"
    if b_data['suka_blyat_mode']:
        return f"💢 Пост №{post_num_formatted}"
    if b_data['gopnik_mode']:
        return f"🤙 Малява №{post_num_formatted}"
    if b_data.get('schizo_mode'):
        return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data['polish_mode']:
        return f"🇵🇱 Post №{post_num_formatted}"
    if b_data['warhammer_mode']:
        return f"⚔️ Донесение №{post_num_formatted}"
    if b_data['imperial_mode']:
        return f"📜 Депеша №{post_num_formatted}"
    if b_data.get('matrix_mode'):
        return f"🟩 Пакет №{post_num_formatted}"
    if b_data.get('america_mode'):
        return f"🦅 Freedom Post №{post_num_formatted}"
    if b_data.get('holiday_mode'):
        return f"🎄 Подарок №{post_num_formatted}"
    if b_data.get('oldweb_mode'):
        return f"🖥️ Сообщение #{post_num_formatted}"
    if b_data.get('jewish_mode'):
        return f"📜 Казус №{post_num_formatted}"
    prefix_lang = 'en' if stream == 'en' else 'ru' 
    prefix = _get_random_header_prefix(lang=prefix_lang)
    if stream == 'en':
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    elif stream == 'jp':
        return f"{circle}{prefix}レス番 {post_num_formatted}"
    else:
        return f"{circle}{prefix}Пост №{post_num_formatted}"

