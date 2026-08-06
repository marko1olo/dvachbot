@dp.message(Command("roast", "prozharka", "╨┐╤Ç╨╛╨╢╨░╤Ç╨║╨░"))
async def cmd_roast(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ≡ƒöÑ ╨ƒ╤Ç╨╛╨╢╨░╤Ç╨║╨░ ╨▒╨╛╤Ç╨┤╤ï ╨╜╨╡╨╣╤Ç╨╛╤ü╨╡╤é╤î╤Ä.

    ╨ñ╤â╨╜╨║╤å╨╕╤Å ╨▒╤ï╨╗╨░ ╨╜╨░╨┐╨╕╤ü╨░╨╜╨░ ╨┐╨╛╨╗╨╜╨╛╤ü╤é╤î╤Ä ΓÇö ╨║╤â╨╗╨┤╨░╤â╨╜, ╤ü╨▒╨╛╤Ç ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╤à 40 ╨┐╨╛╤ü╤é╨╛╨▓ ╨╖╨░
    2 ╤ç╨░╤ü╨░, ╤é╤Ç╤æ╤à╤è╤Å╨╖╤ï╤ç╨╜╤ï╨╡ ╨┐╤Ç╨╛╨╝╨┐╤é╤ï, ╨┐╤Ç╨╛╨│╤Ç╨╡╤ü╤ü-╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡, ╨╛╨▒╤Ç╨░╨▒╨╛╤é╨║╨░ ╨╛╤ê╨╕╨▒╨╛╨║ ΓÇö ╨╜╨╛
    ╤â ╨╜╨╡╤æ ╨╛╤é╤ü╤â╤é╤ü╤é╨▓╨╛╨▓╨░╨╗ ╨┤╨╡╨║╨╛╤Ç╨░╤é╨╛╤Ç, ╨┐╨╛╤ì╤é╨╛╨╝╤â ╨║╨╛╨╝╨░╨╜╨┤╨░ ╨╜╨╡ ╤Ç╨╡╨│╨╕╤ü╤é╤Ç╨╕╤Ç╨╛╨▓╨░╨╗╨░╤ü╤î ╨╕ ╨▒╤ï╨╗╨░
    ╨╜╨╡╨┤╨╛╤ü╤é╨╕╨╢╨╕╨╝╨░. ╨ƒ╤Ç╨╕ ╤ì╤é╨╛╨╝ /help ╨╡╤æ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å╨╝ ╨╛╨▒╨╡╤ë╨░╨╗.
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
        await message.reply(f"ΓÅ│ ╨Ü╨╛╨╝╨░╨╜╨┤╨░ ╨╛╤ü╤é╤ï╨▓╨░╨╡╤é: {rem_m}╨╝ {rem_s}╤ü" if lang == 'ru' else f"ΓÅ│ Cooldown: {rem_m}m {rem_s}s")
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
        await message.reply("≡ƒÆñ ╨£╨░╨╗╨╛ ╨┐╨╛╤ü╤é╨╛╨▓ ╨┤╨╗╤Å ╨┐╤Ç╨╛╨╢╨░╤Ç╨║╨╕" if lang == 'ru' else "≡ƒÆñ Not enough posts")
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
    
    processing_msg = await message.reply("≡ƒöÑ ╨ô╨╛╤é╨╛╨▓╨╕╨╝ ╨┐╤Ç╨╛╨╢╨░╤Ç╨║╤â..." if lang == 'ru' else "≡ƒöÑ Roasting...")
    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[roast] Error: {e}")
        await processing_msg.edit_text("Γ¥î ╨₧╤ê╨╕╨▒╨║╨░ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕" if lang == 'ru' else "Γ¥î Error")
        return
        
    if not summary:
        await processing_msg.edit_text("Γ¥î ╨₧╤ê╨╕╨▒╨║╨░ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕" if lang == 'ru' else "Γ¥î Error")
        return
        
    roast_text = f"≡ƒöÑ <b>╨ƒ╨á╨₧╨û╨É╨á╨Ü╨É ╨º╨É╨ó╨É</b> ≡ƒöÑ\n\n{summary}" if lang == 'ru' else f"≡ƒöÑ <b>CHAT ROAST</b> ≡ƒöÑ\n\n{summary}"
    if lang == 'jp': roast_text = f"≡ƒöÑ <b>τà╜πéè</b> ≡ƒöÑ\n\n{summary}"
    
    await processing_msg.edit_text(roast_text, parse_mode='HTML')