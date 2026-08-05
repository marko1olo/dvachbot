import asyncio
from shared_state import *
try:
    from moderation_config import *
except ImportError:
    pass
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
from datetime import datetime

from shared_state import *
try:
    from moderation_config import *
except ImportError:
    pass

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
        if rand < 0.003: circle = "≡ƒîæ "
        elif rand < 0.006: circle = "≡ƒîÆ "
        elif rand < 0.009: circle = "≡ƒîô "
        elif rand < 0.012: circle = "≡ƒîö "
        elif rand < 0.015: circle = "≡ƒî¥ "
        elif rand < 0.018: circle = "≡ƒîî "
    else:
        if rand < 0.003: circle = "≡ƒö┤ "
        elif rand < 0.006: circle = "≡ƒƒó "
        elif rand < 0.009: circle = "Γÿó∩╕Å "
        elif rand < 0.012: circle = "≡ƒƒí "
        elif rand < 0.015: circle = "≡ƒö╡ "
        elif rand < 0.018: circle = "Γ¡ò "
    if b_data['slavaukraine_mode']: return f"≡ƒÆÖ≡ƒÆ¢ ╨ƒi╤ü╤é Γäû{post_num_formatted}"
    if b_data['zaputin_mode']: return f"≡ƒç╖≡ƒç║ ╨ƒ╨╛╤ü╤é Γäû{post_num_formatted}"
    if b_data['anime_mode']: return f"≡ƒî╕ µèòτ¿┐ {post_num_formatted} τò¬"
    if b_data['suka_blyat_mode']: return f"≡ƒÆó ╨ƒ╨╛╤ü╤é Γäû{post_num_formatted}"
    if b_data['polish_mode']: return f"≡ƒç╡≡ƒç▒ Post Γäû{post_num_formatted}"
    if b_data.get('schizo_mode'): return f"++ ╨í╨ÿ╨ô╨¥╨É╨¢ #{post_num_formatted} ++"
    if b_data['warhammer_mode']: return f"ΓÜö∩╕Å ╨ö╨╛╨╜╨╡╤ü╨╡╨╜╨╕╨╡ Γäû{post_num_formatted}"
    if b_data['imperial_mode']: return f"≡ƒô£ ╨ö╨╡╨┐╨╡╤ê╨░ Γäû{post_num_formatted}"
    if b_data.get('matrix_mode'): return f"≡ƒƒ⌐ ╨ƒ╨░╨║╨╡╤é Γäû{post_num_formatted}"
    if b_data.get('america_mode'): return f"≡ƒªà Freedom Post Γäû{post_num_formatted}"
    if b_data.get('holiday_mode'): return f"≡ƒÄä ╨ƒ╨╛╨┤╨░╤Ç╨╛╨║ Γäû{post_num_formatted}"
    if b_data.get('oldweb_mode'): return f"≡ƒûÑ∩╕Å ╨í╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ #{post_num_formatted}"
    if b_data.get('jewish_mode'): return f"≡ƒô£ ╨Ü╨░╨╖╤â╤ü Γäû{post_num_formatted}"
    prefix = _get_random_header_prefix(lang=stream)
    if stream == 'en':
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    elif stream == 'jp':
        return f"{circle}{prefix}πâ¼πé╣τò¬ {post_num_formatted}"
    else:
        return f"{circle}{prefix}╨ƒ╨╛╤ü╤é Γäû{post_num_formatted}"

async def format_header(board_id: str, post_num: int, author_id: int = 0, stream: str = 'ru') -> str:
    """
    ╨ñ╨╛╤Ç╨╝╨░╤é╨╕╤Ç╨╛╨▓╨░╨╜╨╕╨╡ ╨╖╨░╨│╨╛╨╗╨╛╨▓╨║╨░ ╤ü ╨┐╨╛╨┤╨┤╨╡╤Ç╨╢╨║╨╛╨╣ VIP ╨┐╤Ç╨╡╤ä╨╕╨║╤ü╨╛╨▓ ╨╕╨╖ ╨ó╨╡╨╜╨╡╨▓╨╛╨│╨╛ ╨£╨░╨│╨░╨╖╨╕╨╜╨░.
    """
    custom_prefix = ""
    if author_id > 0:
        from common.db_pool import get_pool
        import time
        import json
        db = await get_pool()
        has_poop = False
        prefix_str = ""
        async with db.execute("SELECT active_items, custom_prefix, prefix_expires_at FROM Users WHERE user_id = ?", (author_id,)) as c:
            async for row in c:
                if row[0]:
                    try:
                        items = json.loads(row[0])
                        if items.get("shit_until", 0) > int(time.time()):
                            has_poop = True
                    except Exception:
                        pass
                if row[1] and row[2] and int(time.time()) < row[2]:
                    prefix_str = f"<b>{row[1]}</b> "
        if has_poop:
            custom_prefix = "≡ƒÆ⌐ " + prefix_str
        else:
            custom_prefix = prefix_str
                    
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
        if "╤é╨╡" in matched_text:
            return "╨╛╨▒╨╛╤ü╤ü╤ï╤é╨╡ ╨╝╨╡╨╜╤Å"
        return "╨╛╨▒╨╛╤ü╤ü╤ï ╨╝╨╡╨╜╤Å"
        
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
    ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╤é ╨╜╨╛╨╝╨╡╤Ç ╨┐╨╛╤ü╤é╨░ ╨╜╨░ ╨╜╨░╨╗╨╕╤ç╨╕╨╡ ╨┐╨╛╨▓╤é╨╛╤Ç╤Å╤Ä╤ë╨╕╤à╤ü╤Å ╤å╨╕╤ä╤Ç ╨▓ ╨║╨╛╨╜╤å╨╡.
    ╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╡╤é ╨╛╨┐╤é╨╕╨╝╨╕╨╖╨╕╤Ç╨╛╨▓╨░╨╜╨╜╤ï╨╣ ╨┐╨╛╤ü╨╕╨╝╨▓╨╛╨╗╤î╨╜╤ï╨╣ ╨░╨╜╨░╨╗╨╕╨╖ ╤ü ╨║╨╛╨╜╤å╨░.
    ╨Æ╨╛╨╖╨▓╤Ç╨░╤ë╨░╨╡╤é "╤â╤Ç╨╛╨▓╨╡╨╜╤î ╤Ç╨╡╨┤╨║╨╛╤ü╤é╨╕" (╨║╨╛╨╗╨╕╤ç╨╡╤ü╤é╨▓╨╛ ╨┐╨╛╨▓╤é╨╛╤Ç╨╛╨▓) ╨╕╨╗╨╕ None.
    """
    s = str(post_num)
    length = len(s)
    if length < 4:
        return None
    last_char = s[-1]
    count = 1
    for i in range(length - 2, -1, -1):
        if s[i] == last_char:
            count += 1
        else:
            break
    if count in SPECIAL_NUMERALS_CONFIG:
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
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[auto-roast] Error: {e}")
        return
        
    if not summary:
        return
        
    roast_text = f"≡ƒöÑ <b>╨É╨Æ╨ó╨₧-╨ƒ╨á╨₧╨û╨É╨á╨Ü╨É ╨í╨á╨É╨º╨É</b> ≡ƒöÑ\n\n{summary}" if lang == 'ru' else f"≡ƒöÑ <b>AUTO-ROAST</b> ≡ƒöÑ\n\n{summary}"
    if lang == 'jp':
        roast_text = f"≡ƒöÑ <b>Φç¬σïòτà╜πéè</b> ≡ƒöÑ\n\n{summary}"
    
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
            suffix = str(author_id)[-4:]
            if lang == 'en':
                name = f"Anon #{suffix}"
            elif lang == 'jp':
                name = f"名無し #{suffix}"
            else:
                name = f"Анон #{suffix}"
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
        pass

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
                            pass
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
                pass
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
                pass
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
        total_deleted_count = await _delete_posts_from_pm_api(messages_to_delete_from_api, bot_instance)
        
        return total_deleted_count
    except Exception as e:
        import traceback
        print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
        return 0
