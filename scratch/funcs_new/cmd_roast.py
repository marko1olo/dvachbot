@dp.message(Command("roast", "prozharka", "прожарка"))
async def cmd_roast(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    🔥 Прожарка борды нейросетью.

    Функция была написана полностью — кулдаун, сбор последних 40 постов за
    2 часа, трёхъязычные промпты, прогресс-сообщение, обработка ошибок — но
    у неё отсутствовал декоратор, поэтому команда не регистрировалась и была
    недостижима. При этом /help её пользователям обещал.
    """
    if not board_id:
        return

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data.get(board_id)
    if not b_data:
        return
        
    now_ts = time.time()
    last_usage = b_data.get('last_roast_time', 0)
    if now_ts - last_usage < ROAST_COOLDOWN:
        rem_m = int((ROAST_COOLDOWN - (now_ts - last_usage)) // 60)
        rem_s = int((ROAST_COOLDOWN - (now_ts - last_usage)) % 60)
        await message.reply(f"⏳ Команда остывает: {rem_m}м {rem_s}с" if lang == 'ru' else f"⏳ Cooldown: {rem_m}m {rem_s}s")
        return

    b_data['last_roast_time'] = now_ts
    
    msgs = []
    cutoff = time.time() - (3600 * 2)
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
    
    if len(msgs) < 5:
        await message.reply("💤 Мало постов для прожарки" if lang == 'ru' else "💤 Not enough posts")
        return
        
    chunk_parts = []
    for p in msgs:
        text = p.get('content', {}).get('text', '') if isinstance(p.get('content'), dict) else ''
        if text:
            chunk_parts.append(f"[Anon]: {text}")
            
    chunk = " | ".join(chunk_parts)
    
    if lang == 'en':
        prompt = random.choice(ROAST_PROMPTS_EN)
    elif lang == 'jp':
        prompt = random.choice(ROAST_PROMPTS_JP)
    else:
        prompt = random.choice(ROAST_PROMPTS)
        
    hf_token = os.getenv("HF_TOKEN")
    
    processing_msg = await message.reply("🔥 Готовим прожарку..." if lang == 'ru' else "🔥 Roasting...")
    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[roast] Error: {e}")
        await processing_msg.edit_text("❌ Ошибка генерации" if lang == 'ru' else "❌ Error")
        return
        
    if not summary:
        await processing_msg.edit_text("❌ Ошибка генерации" if lang == 'ru' else "❌ Error")
        return
        
    roast_text = f"🔥 <b>ПРОЖАРКА ЧАТА</b> 🔥\n\n{summary}" if lang == 'ru' else f"🔥 <b>CHAT ROAST</b> 🔥\n\n{summary}"
    if lang == 'jp': roast_text = f"🔥 <b>煽り</b> 🔥\n\n{summary}"
    
    await processing_msg.edit_text(roast_text, parse_mode='HTML')