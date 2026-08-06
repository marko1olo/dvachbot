# Scratch file from extraction pass
"""
This module was created as a scratch pad during function extraction.
All active functions live in post_processor.py, post_helpers.py, and main.py.
"""

import math
from datetime import datetime

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
                        import traceback; traceback.print_exc()
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