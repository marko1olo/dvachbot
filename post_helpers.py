from common.anon_identity import get_anon_id
import asyncio
import time
import re
from functools import lru_cache
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

ROAST_COOLDOWN = 300  # 5 minutes cooldown for auto-roast

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
    if b_data.get('slavaukraine_mode'): return f"💙💛 Пост №{post_num_formatted}"
    if b_data.get('zaputin_mode'): return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data.get('anime_mode'): return f"🌸 投稿 {post_num_formatted} 番"
    if b_data.get('suka_blyat_mode'): return f"💥 Пост №{post_num_formatted}"
    if b_data.get('polish_mode'): return f"🇵🇱 Post №{post_num_formatted}"
    if b_data.get('schizo_mode'): return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data.get('warhammer_mode'): return f"⚡ Донесение №{post_num_formatted}"
    if b_data.get('imperial_mode'): return f"📜 Депеша №{post_num_formatted}"
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

    try:
        from ai_manager import (
            build_cyberchad_context,
            CYBERCHAD_SYSTEM_JSON_PROMPT,
            parse_cyberchad_response,
        )
        from common.tts_engine import synthesize_cyberchad_voice_with_meta

        rich_context = await build_cyberchad_context(
            board_id=board_id,
            limit_board=55,
            limit_author=0,
            limit_chad=5
        )

        user_prompt = (
            f"{rich_context}\n\n"
            f"Оцени текущую атмосферу и активность в треде/чате /{board_id}/. "
            f"Ворвись и выдай мощный, брутальный вердикт Киберчеда (верни строго валидный JSON согласно инструкции):"
        )

        raw = await summarize_text_with_hf(
            prompt=CYBERCHAD_SYSTEM_JSON_PROMPT,
            text_dump=user_prompt,
            model_preference="persona"
        )

        if not raw:
            return

        parsed = parse_cyberchad_response(raw)
        if not parsed.get("reply", True):
            print(f"ℹ️ [Auto-Roast] Киберчед отказался от интервенции (reply=False): {parsed.get('reason_if_skipped', 'не указана')}")
            return

        roast_text = parsed.get("text", "").strip()
        if not roast_text or len(roast_text) < 5:
            return

        if parsed.get("generate_image"):
            print(f"🎨 [Auto-Roast] Запрошена генерация изображения: '{parsed.get('image_prompt')}'")

        # Синтезируем голос Киберчеда
        voice_bytes = None
        try:
            voice_res = await synthesize_cyberchad_voice_with_meta(roast_text)
            if isinstance(voice_res, tuple):
                voice_bytes = voice_res[0]
            else:
                voice_bytes = voice_res
        except Exception as tts_err:
            print(f"⚠️ [Auto-Roast] TTS synthesis error: {tts_err}")

        content_payload = {
            'type': 'voice' if voice_bytes else 'text',
            'is_system_message': True,
            'archive_allowed': True,
            'is_ai_roast': True,
            'is_ai': True,
            'is_cyberchad': True
        }

        if voice_bytes:
            content_payload['voice_bytes'] = voice_bytes
            content_payload['caption'] = '🔥 Разъёб от Киберчеда'
            content_payload['text'] = roast_text
        else:
            content_payload['text'] = roast_text
        
        pnum = await create_post(
            board_id=board_id,
            author_id=0,
            content=content_payload,
            timestamp=time.time(),
            is_from_site=False,
            stream=stream
        )
        if pnum:
            header = await format_header(board_id, pnum, 0)
            content_payload['header'] = f"🔥 КИБЕРЧЕД 🔥\n{header}" if stream == 'ru' else f"🔥 CYBERCHAD 🔥\n{header}"
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
            print(f"✅ [Auto-Roast] Киберчед успешно опубликовал пост #{pnum} на /{board_id}/ (voice={bool(voice_bytes)}).")
    except Exception as e:
        print(f"[auto-roast] Error: {e}")
        return
_MEDIA_DESC_CACHE: dict[str, dict] = {}

RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_MULTI_NEWLINES = re.compile(r'\n{2,}')

_MEDIA_ERROR_TAGS = frozenset({
    'error', 'download_failed', 'dead', 'no_tags', 'format_unsupported',
    'error_no_tags', 'error_too_large', 'unknown', 'none', 'null'
})

@lru_cache(maxsize=16384)
def _get_cached_anon_name(author_id: int, stream_lang: str) -> str:
    aid = get_anon_id(author_id, stream=stream_lang)
    if stream_lang == 'en':
        return f"Anon [{aid}]"
    elif stream_lang == 'jp':
        return f"名無し [{aid}]"
    return f"Анон [{aid}]"

def _format_media_context(
    media_meta: dict | None,
    max_desc_len: int = 150,
    max_tags_len: int = 80,
    smart_boundary: bool = True
) -> str | None:
    if not media_meta or not isinstance(media_meta, dict):
        return None

    if 'formatted' in media_meta and max_desc_len == 150 and max_tags_len == 80:
        return media_meta['formatted']

    raw_desc = media_meta.get('description')
    raw_tags = media_meta.get('tags')

    # Sanitize description
    desc = ""
    if raw_desc and isinstance(raw_desc, str):
        d_clean = raw_desc.strip()
        d_lower = d_clean.lower()
        if (d_lower not in _MEDIA_ERROR_TAGS
                and not d_lower.startswith('error')
                and 'download_failed' not in d_lower):
            desc = d_clean

    # Sanitize tags
    clean_tags_list = []
    if raw_tags:
        if isinstance(raw_tags, str):
            tag_items = [t.strip() for t in raw_tags.split(',') if t.strip()]
        elif isinstance(raw_tags, (list, tuple, set)):
            tag_items = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            tag_items = []

        for t in tag_items:
            t_lower = t.lower()
            if t_lower in _MEDIA_ERROR_TAGS or t_lower.startswith('error') or 'download_failed' in t_lower:
                continue
            clean_tags_list.append(t)

    if not desc and not clean_tags_list:
        if max_desc_len == 150 and max_tags_len == 80:
            media_meta['formatted'] = None
        return None

    # Truncate descriptions smartly at word boundary without chopping words in half
    if desc:
        if len(desc) > max_desc_len:
            cut = desc[:max_desc_len].rstrip()
            last_space = cut.rfind(' ')
            if smart_boundary and last_space > int(max_desc_len * 0.75):
                d_short = cut[:last_space].rstrip() + "..."
            else:
                d_short = cut + "..."
        else:
            d_short = desc
    else:
        d_short = ""

    # Truncate tags by whole items up to max_tags_len without cutting tags mid-word
    if clean_tags_list:
        chosen_tags = []
        cur_t_len = 0
        for tag in clean_tags_list:
            item_len = len(tag) + (2 if chosen_tags else 0)
            if cur_t_len + item_len > max_tags_len:
                break
            chosen_tags.append(tag)
            cur_t_len += item_len
        if chosen_tags:
            t_short = ", ".join(chosen_tags)
            if len(chosen_tags) < len(clean_tags_list):
                t_short += "..."
        else:
            t_short = clean_tags_list[0][:max_tags_len].rstrip() + "..."
    else:
        t_short = ""

    d_short_clean = d_short.rstrip('.').rstrip()
    if d_short_clean and t_short:
        desc_and_tags = f"{d_short_clean}. Теги: {t_short}"
    elif d_short_clean:
        desc_and_tags = d_short
    else:
        desc_and_tags = t_short

    formatted = f"[Фото: {desc_and_tags}]"
    if max_desc_len == 150 and max_tags_len == 80:
        media_meta['formatted'] = formatted
    return formatted

def _format_post_text(
    content: dict,
    msg_type: str,
    media_meta: dict | None = None,
    max_desc_len: int | None = None,
    max_tags_len: int | None = None
) -> str | None:
    if not isinstance(content, dict):
        return None

    text = content.get('text') or content.get('caption') or ""
    if isinstance(text, str) and text:
        text = RE_HTML_TAGS.sub('', text).strip() if '<' in text else text.strip()
    else:
        text = ""

    if media_meta:
        if max_desc_len is not None and max_tags_len is not None:
            media_annotation = _format_media_context(
                media_meta,
                max_desc_len=max_desc_len,
                max_tags_len=max_tags_len,
                smart_boundary=True
            )
        else:
            media_annotation = media_meta.get('formatted')
            if media_annotation is None and ('description' in media_meta or 'tags' in media_meta):
                media_annotation = _format_media_context(media_meta)
    else:
        media_annotation = None

    if media_annotation:
        return f"{media_annotation} {text}" if text else media_annotation
    if text:
        return text
    if msg_type in ('photo', 'video', 'document', 'animation', 'media_group', 'sticker', 'voice', 'video_note'):
        return f"[{msg_type}]"
    return None

def _get_author_name(post: dict, content: dict, board_id: str, lang: str | None) -> str:
    name = content.get('username') or content.get('name') or content.get('author_name')
    if not name:
        stream_lang = lang or ('en' if board_id == 'int' else 'ru')
        author_id = post.get('author_id')
        if author_id and author_id != 0:
            name = _get_cached_anon_name(author_id, stream_lang)
        else:
            name = "Anon" if stream_lang == 'en' else ("名無し" if stream_lang == 'jp' else "Анон")
    return name

def _get_reply_suffix(post: dict, content: dict, board_id: str, lang: str | None) -> str:
    reply_to = content.get('reply_to_post') or post.get('reply_to_post_num')
    if not reply_to:
        return ""
    stream_lang = lang or ('en' if board_id == 'int' else 'ru')
    if stream_lang == 'en':
        return f" (reply to #{reply_to})"
    elif stream_lang == 'jp':
        return f" (>>{reply_to})"
    return f" (Ответ на #{reply_to})"


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

async def _delete_user_posts_from_db(user_id: int, time_threshold_ts: float, board_id: str = None) -> tuple[list[int], list, list]:
    from common.db_pool import get_pool, db_lock, db_transaction
    import json
    for attempt in range(10):
        try:
            db = await get_pool()
            async with db_transaction(db):
                if board_id and board_id != 'all':
                    query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
                    params = (user_id, board_id, time_threshold_ts)
                else:
                    query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND timestamp >= ?"
                    params = (user_id, time_threshold_ts)
                    
                async with db.execute(query_posts, params) as cursor:
                    rows = await cursor.fetchall()
                user_posts = [row[0] for row in rows]

                if not user_posts:
                    return [], [], []
                    
                posts_to_delete_set = set(user_posts)
                threads_to_delete = []

                if user_posts:
                    p_strs_json = json.dumps([str(p) for p in user_posts])
                    p_nums_json = json.dumps(user_posts)
                    query = """
                        SELECT thread_id FROM Threads
                        WHERE thread_id IN (SELECT value FROM json_each(?))
                           OR thread_num IN (SELECT value FROM json_each(?))
                    """
                    async with db.execute(query, (p_strs_json, p_nums_json)) as cursor:
                        t_rows = await cursor.fetchall()
                        for tr in t_rows:
                            threads_to_delete.append(tr[0])

                if threads_to_delete:
                    t_ids = []
                    for t_id in threads_to_delete:
                        t_ids.append(t_id)
                        try: t_id_int = int(t_id)
                        except ValueError: t_id_int = 0
                        t_ids.append(str(t_id_int))

                    t_ids = list(set(t_ids))
                    t_ids_json = json.dumps(t_ids)

                    query = "SELECT post_num FROM Posts WHERE thread_id IN (SELECT value FROM json_each(?))"
                    async with db.execute(query, (t_ids_json,)) as cursor:
                        p_rows = await cursor.fetchall()
                        for pr in p_rows:
                            posts_to_delete_set.add(pr[0])

                posts_to_delete_nums = list(posts_to_delete_set)
                posts_json = json.dumps(posts_to_delete_nums)

                query_copies = """
                    SELECT pc.recipient_id, pc.message_id, p.board_id
                    FROM PostCopies pc
                    JOIN Posts p ON pc.post_num = p.post_num
                    WHERE pc.post_num IN (SELECT value FROM json_each(?))
                """
                async with db.execute(query_copies, (posts_json,)) as cursor:
                    messages_to_delete_from_api = await cursor.fetchall()
                    
                query_channels = """
                    SELECT cc.channel_id, cc.message_id, p.board_id
                    FROM ChannelCopies cc
                    JOIN Posts p ON cc.post_num = p.post_num
                    WHERE cc.post_num IN (SELECT value FROM json_each(?))
                """
                async with db.execute(query_channels, (posts_json,)) as cursor:
                    channel_messages_to_delete = await cursor.fetchall()

                await db.execute("DELETE FROM Posts WHERE post_num IN (SELECT value FROM json_each(?))", (posts_json,))
                await db.execute("DELETE FROM PostCopies WHERE post_num IN (SELECT value FROM json_each(?))", (posts_json,))
                await db.execute("DELETE FROM ChannelCopies WHERE post_num IN (SELECT value FROM json_each(?))", (posts_json,))
                await db.execute("DELETE FROM BroadcastQueue WHERE post_num IN (SELECT value FROM json_each(?))", (posts_json,))
                await db.execute("DELETE FROM UserReplies WHERE post_num IN (SELECT value FROM json_each(?)) OR parent_num IN (SELECT value FROM json_each(?))", (posts_json, posts_json))

                if threads_to_delete:
                    threads_json = json.dumps(threads_to_delete)
                    await db.execute("DELETE FROM Threads WHERE thread_id IN (SELECT value FROM json_each(?))", (threads_json,))

                return posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete

        except Exception as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                pass
            else:
                print(f"⛔ DB Error in delete_user_posts: {e}")
                return [], [], []
        await asyncio.sleep(0.2 * (attempt + 1))
    return [], [], []

async def _clean_posts_from_ram(posts_to_delete_nums: list[int], board_id: str):
    from common.thread_manager import get_threads_data
    async with storage_lock:
        for post_num in posts_to_delete_nums:
            post_data = messages_storage.pop(post_num, None)
            if post_data:
                target_b = board_id or post_data.get('board_id')
                if target_b and target_b in THREAD_BOARDS:
                    thread_id = post_data.get('thread_id')
                    if thread_id:
                        b_data = board_data.get(target_b, {})
                        threads_data = get_threads_data(target_b)
                        if thread_id in threads_data:
                            try:
                                if 'posts' in threads_data[thread_id]:
                                    threads_data[thread_id]['posts'].remove(post_num)
                            except (ValueError, KeyError):
                                pass
            message_copies_in_mem = post_to_messages.pop(post_num, {})
            for uid, mid_or_list in message_copies_in_mem.items():
                if isinstance(mid_or_list, list):
                    for mid in mid_or_list:
                        message_to_post.pop((uid, mid), None)
                else:
                    message_to_post.pop((uid, mid_or_list), None)

def _clean_posts_from_caches(posts_to_delete_nums: list[int]):
    from common.database import _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE
    for post_id_int in posts_to_delete_nums:
        post_id_str = str(post_id_int)
        for b in list(_THREAD_CACHE.keys()):
            if post_id_str in _THREAD_CACHE[b]:
                try: _THREAD_CACHE[b].remove(post_id_str)
                except Exception: pass
        for b in list(_VIDEO_CACHE.keys()):
            _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
        for b in list(_IMAGE_CACHE.keys()):
            _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]

async def _delete_posts_from_channels(channel_messages_to_delete: list, bot_instance):
    if not channel_messages_to_delete:
        return
    from common.config import ARCHIVE_POSTING_BOT_ID
    archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
    for item in channel_messages_to_delete:
        if len(item) == 3:
            chan_id, msg_id, b_id = item
        elif len(item) == 2:
            chan_id, msg_id = item
            b_id = None
        else:
            continue
            
        bot_candidates = []
        if archive_bot:
            bot_candidates.append(archive_bot)
        if b_id and b_id in GLOBAL_BOTS and GLOBAL_BOTS[b_id] and GLOBAL_BOTS[b_id] not in bot_candidates:
            bot_candidates.append(GLOBAL_BOTS[b_id])
        if bot_instance and bot_instance not in bot_candidates:
            bot_candidates.append(bot_instance)
        for b in GLOBAL_BOTS.values():
            if b and b not in bot_candidates:
                bot_candidates.append(b)
                
        for b in bot_candidates:
            try:
                await b.delete_message(chat_id=chan_id, message_id=msg_id)
                break
            except Exception:
                continue

async def _delete_message_with_retries(bot_instance, uid: int, mid: int, b_id: str = None) -> bool:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
    import aiohttp
    deleter = GLOBAL_BOTS.get(b_id) or bot_instance if b_id else bot_instance
    if not deleter:
        return False
    try:
        await deleter.delete_message(uid, mid)
        return True
    except (TelegramBadRequest, TelegramForbiddenError):
        if deleter != bot_instance and bot_instance:
            try:
                await bot_instance.delete_message(uid, mid)
                return True
            except Exception:
                pass
        return False
    except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientOSError):
        await asyncio.sleep(0.5)
        try:
            await deleter.delete_message(uid, mid)
            return True
        except Exception:
            return False
    except Exception:
        return False

async def _delete_posts_from_pm_api(messages_to_delete_from_api: list, bot_instance) -> int:
    CHUNK_SIZE = 47
    DELAY_BETWEEN_CHUNKS = 0.11
    total_deleted_count = 0
    for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
        chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
        tasks = [_delete_message_with_retries(bot_instance, uid, mid, b_id) for uid, mid, b_id in chunk]
        results = await asyncio.gather(*tasks)
        total_deleted_count += sum(1 for res in results if res is True)
        if i + CHUNK_SIZE < len(messages_to_delete_from_api):
            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
    return total_deleted_count

async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str = None) -> int:
    """
    Массовое удаление постов пользователя за период.
    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
    """
    try:
        from datetime import datetime, timedelta, UTC
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
    if b_data.get('slavaukraine_mode'):
        headers = [f"💙💛 Пiст №{post_num_formatted}", f"🇺🇦 Повiдомлення №{post_num_formatted}"]
        return random.choice(headers)
    if b_data.get('zaputin_mode'):
        return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data.get('anime_mode'):
        return f"🌸 投稿 {post_num_formatted} 番"
    if b_data.get('suka_blyat_mode'):
        return f"💢 Пост №{post_num_formatted}"
    if b_data.get('gopnik_mode'):
        return f"🤙 Малява №{post_num_formatted}"
    if b_data.get('schizo_mode'):
        return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data.get('polish_mode'):
        return f"🇵🇱 Post №{post_num_formatted}"
    if b_data.get('warhammer_mode'):
        return f"⚔️ Донесение №{post_num_formatted}"
    if b_data.get('imperial_mode'):
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


async def get_reply_target(message):
    """Resolves the author user_id of the message being replied to."""
    if not message or not getattr(message, 'reply_to_message', None):
        return None
    try:
        from common.db_pool import get_pool
        db = await get_pool()
        async with db.execute(
            "SELECT author_id FROM PostCopies JOIN Posts ON PostCopies.post_num = Posts.post_num WHERE recipient_id = ? AND message_id = ?",
            (message.chat.id, message.reply_to_message.message_id)
        ) as c:
            row = await c.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return None

