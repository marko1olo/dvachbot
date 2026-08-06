@dp.message(Command("generate"))
async def cmd_generate(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    COOLDOWN_SECONDS = 20
    # storage_lock ╤â╨▒╤Ç╨░╨╜: ╨║╤â╨╗╨┤╨░╤â╨╜ ╨╗╨╡╨╢╨╕╤é ╨▓ board_data, ╨▓╨╖╨░╨╕╨╝╨╜╨╛╨╡ ╨╕╤ü╨║╨╗╤Ä╤ç╨╡╨╜╨╕╨╡ ╤â╨╢╨╡
    # ╨┤╨░╤æ╤é generate_locks[user_id]. ╨₧╤é╨▓╨╡╤é ╤Ä╨╖╨╡╤Ç╤â ΓÇö ╨╖╨░ ╨┐╤Ç╨╡╨┤╨╡╨╗╨░╨╝╨╕ ╨╗╨╛╨║╨░.
    remaining = 0
    async with generate_locks[user_id]:
        b_data = board_data[board_id]
        last_usage = b_data.get('last_generate_time', {}).get(user_id, 0)
        current_time = time.time()
        on_cooldown = current_time - last_usage < COOLDOWN_SECONDS
        if on_cooldown:
            remaining = int(COOLDOWN_SECONDS - (current_time - last_usage))
        else:
            b_data.setdefault('last_generate_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en': txt = f"ΓÅ│ Please wait {remaining} more seconds."
        elif lang == 'jp': txt = f"ΓÅ│ πüéπü¿ {remaining} τºÆσ╛àπüúπüªπüÅπüáπüòπüäπÇé"
        else: txt = f"ΓÅ│ ╨ƒ╨╛╨┤╨╛╨╢╨┤╨╕ ╨╡╤ë╨╡ {remaining} ╤ü╨╡╨║."
        try: await message.answer(txt)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    full_command_text = message.text or ""
    text_to_generate = ""
    command_prefix = "/generate "
    if full_command_text.startswith(command_prefix):
        text_to_generate = full_command_text[len(command_prefix):].strip()
    if not text_to_generate:
        if lang == 'en': usage = "Usage: <code>/generate &lt;prompt text&gt;</code>"
        elif lang == 'jp': usage = "Σ╜┐τö¿µ│ò: <code>/generate &lt;prompt text&gt;</code>"
        else: usage = "ΓÜá∩╕Å ╨¥╨░╨┐╨╕╤ê╨╕╤é╨╡ ╨┐╤Ç╨╛╨╝╨┐╤é. ╨ƒ╤Ç╨╕╨╝╨╡╤Ç: <code>/generate ╨¥╨░╤Ç╨╕╤ü╤â╨╣ ╨║╨╛╤é╨░ ╨▓ ╨║╨╛╤ü╨╝╨╛╤ü╨╡</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    working_msg = None
    try:
        wait_txt = "ΓÅ│ Generating..." if lang == 'en' else ("ΓÅ│ τöƒµêÉΣ╕¡..." if lang == 'jp' else "ΓÅ│ ╨ô╨╡╨╜╨╡╤Ç╨╕╤Ç╤â╤Ä ╨▓╤ï╤ü╨╡╤Ç...")
        working_msg = await message.answer(wait_txt)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_to_generate)
        await working_msg.delete()
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="wipe.png")
            await message.answer_photo(photo)
        else:
            err_txt = "≡ƒÜ½ Failed to generate image." if lang == 'en' else ("≡ƒÜ½ τö╗σâÅπü«τöƒµêÉπü½σñ▒µòùπüùπü╛πüùπüƒπÇé" if lang == 'jp' else "≡ƒÜ½ ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨│╨╡╨╜╨╡╤Ç╨╕╤Ç╨╛╨▓╨░╤é╤î ╨╕╨╖╨╛╨▒╤Ç╨░╨╢╨╡╨╜╨╕╨╡.")
            await message.answer(err_txt)
    except Exception as e:
        print(f"Γ¥î [generate] Error user {user_id}: {e}")
        try:
            if working_msg: await working_msg.delete()
            err_txt = "≡ƒÜ½ Unexpected error." if lang == 'en' else ("≡ƒÜ½ Σ║êµ£ƒπüùπü¬πüäπé¿πâ⌐πâ╝πÇé" if lang == 'jp' else "≡ƒÜ½ ╨ƒ╤Ç╨╛╨╕╨╖╨╛╤ê╨╗╨░ ╨╜╨╡╨┐╤Ç╨╡╨┤╨▓╨╕╨┤╨╡╨╜╨╜╨░╤Å ╨╛╤ê╨╕╨▒╨║╨░.")
            await message.answer(err_txt)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        try: await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError): pass