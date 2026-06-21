import re
import sys

def patch_main():
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add ROAST imports
    import_str_old = "    SUMMARIZE_PROMPTS_BOARD, SUMMARIZE_PROMPTS_BOARD_EN, SUMMARIZE_PROMPTS_BOARD_JP,"
    import_str_new = import_str_old + "\n    ROAST_PROMPTS, ROAST_PROMPTS_EN, ROAST_PROMPTS_JP,"
    content = content.replace(import_str_old, import_str_new)

    # 2. Add ROAST_COOLDOWN and clean_html_for_tg
    cooldown_old = "SUMMARIZE_COOLDOWN = 60 * 30"
    cooldown_new = """SUMMARIZE_COOLDOWN = 60 * 30
ROAST_COOLDOWN = 60 * 5  # 5 minutes

def clean_html_for_tg(text: str) -> str:
    \"\"\"Convert some markdown to HTML and strip unsupported tags.\"\"\"
    if not text: return ""
    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\\*\\*(.*?)\\*\\*', r'<b>\\1</b>', text)
    # Convert *italic* to <i>italic</i> (only if not preceded/followed by *)
    text = re.sub(r'(?<!\\*)\\*(?!\\*)(.*?)(?<!\\*)\\*(?!\\*)', r'<i>\\1</i>', text)
    # Convert `code` to <code>code</code>
    text = re.sub(r'`(.*?)`', r'<code>\\1</code>', text)
    
    # Strip dangerous unclosed tags or unsupported tags using a simple regex
    # We will just replace <br> with newline
    text = text.replace('<br>', '\\n').replace('<br/>', '\\n').replace('<br />', '\\n')
    
    # Very rudimentary unclosed tag fix:
    # Just rely on the prompt instructing the LLM, and escape any raw < that is not part of a known tag
    text = re.sub(r'<(?!/?(b|i|u|s|code|pre|a\\b)[>\\s])', '&lt;', text)
    return text
"""
    content = content.replace(cooldown_old, cooldown_new)

    # 3. Patch cmd_summarize to use clean_html_for_tg
    summarize_success_old = "summary = await summarize_text_with_hf(prompt, chunk, hf_token)"
    summarize_success_new = "summary = await summarize_text_with_hf(prompt, chunk, hf_token)\n        summary = clean_html_for_tg(summary)"
    content = content.replace(summarize_success_old, summarize_success_new)

    # 4. Add cmd_roast
    # I'll insert it right after cmd_summarize
    
    # Let's find the end of cmd_summarize
    end_summarize = "dp.message.register(cmd_summarize, Command(commands=['summarize', 'summary', 'sum']))"
    
    roast_code = """
@dp.message(Command("roast", "prozharka"))
async def cmd_roast(message: types.Message):
    board_id = get_board_id(message)
    if not board_id:
        await message.answer("Ошибка: Команда должна использоваться в контексте борды.")
        return
        
    b_data = board_data[board_id]
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now_ts = time.time()
    
    async with storage_lock:
        last_usage = b_data.get('last_roast_time', 0)
        if now_ts - last_usage < ROAST_COOLDOWN:
            remaining = ROAST_COOLDOWN - (now_ts - last_usage)
            await message.answer(f"🕒 Команда на кулдауне. Жди {int(remaining)} секунд.")
            return
        b_data['last_roast_time'] = time.time()

    board_name = escape_html(BOARD_CONFIG[board_id]['name'])
    
    # Fetch last 100 messages from messages_storage for this board
    import itertools
    
    msgs = []
    # We need to find recent messages in the board. Since messages_storage maps message_id to post_info,
    # and we want them ordered by time, we collect all and sort.
    # Alternatively, use get_board_chunk logic but without threads filtering and fixed 100 limit.
    # We can just iterate over the last 300 posts in the board.
    
    cutoff = time.time() - (3600 * 2) # last 2 hours max
    for msg_id, p_info in messages_storage.items():
        if p_info.get('board_id') == board_id and p_info.get('timestamp', 0) > cutoff:
            if not p_info.get('thread_id'): # exclude threads if we want infinite chat only, or include all
                msgs.append(p_info)
                
    # Sort by timestamp
    msgs.sort(key=lambda x: x.get('timestamp', 0))
    # Take last 100
    msgs = msgs[-100:]
    
    if not msgs:
        await message.answer("Недостаточно сообщений для прожарки.")
        return
        
    chunk_parts = []
    for p in msgs:
        author = p.get('author', 'Anon')
        text = p.get('text', '')
        if text:
            chunk_parts.append(f"[{author}]: {text}")
            
    chunk = " | ".join(chunk_parts)
    if len(chunk) < 50:
        await message.answer("Слишком мало текста для прожарки.")
        return
        
    if lang == 'en':
        prompt = random.choice(ROAST_PROMPTS_EN)
    elif lang == 'jp':
        prompt = random.choice(ROAST_PROMPTS_JP)
    else:
        prompt = random.choice(ROAST_PROMPTS)
        
    await message.answer("😈 Разогреваю печь для прожарки чата...")
    
    hf_token = os.getenv("HF_TOKEN")
    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[roast] Error: {e}")
        await message.answer("Ошибка генерации прожарки.")
        return
        
    if not summary:
        await message.answer("Не удалось сгенерировать прожарку.")
        return
        
    try:
        await message.answer(f"🔥 <b>ШИЗО-ПРОЖАРКА ЧАТА</b> 🔥\\n\\n{summary}", parse_mode="HTML")
    except Exception as e:
        print(f"[roast] TG send error: {e}")
        # fallback without html
        try:
            await message.answer(f"🔥 ШИЗО-ПРОЖАРКА ЧАТА 🔥\\n\\n{summary}", parse_mode=None)
        except:
            pass
"""
    if "async def cmd_roast(" not in content:
        content = content.replace(end_summarize, end_summarize + "\n\n" + roast_code)

    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    patch_main()
    print("Patch applied.")
