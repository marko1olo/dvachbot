@dp.message(Command("roll", "roulette", "ruletka", "rulet", "fortune", "╤ä╨╛╤Ç╤é╤â╨╜╨░"))
async def cmd_roll(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: 
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    # storage_lock ╨╖╨┤╨╡╤ü╤î ╨▒╤ï╨╗ ╨╗╨╛╨╢╨╜╨╛╨╣ ╨╖╨░╨▓╨╕╤ü╨╕╨╝╨╛╤ü╤é╤î╤Ä: ╨╛╨╜ ╨╖╨░╤ë╨╕╤ë╨░╨╡╤é messages_storage /
    # post_to_messages / message_to_post, ╨░ ╨║╤â╨╗╨┤╨░╤â╨╜ ╨╗╨╡╨╢╨╕╤é ╨▓ board_data, ╨║
    # ╨║╨╛╤é╨╛╤Ç╨╛╨╝╤â 111 ╨╕╨╖ 146 ╨╛╨▒╤Ç╨░╤ë╨╡╨╜╨╕╨╣ ╨▓ ╤ì╤é╨╛╨╝ ╤ä╨░╨╣╨╗╨╡ ╨╕╨┤╤â╤é ╨▓╨╛╨╛╨▒╤ë╨╡ ╨▒╨╡╨╖ ╨╜╨╡╨│╨╛.
    # ╨Æ╨╖╨░╨╕╨╝╨╜╨╛╨╡ ╨╕╤ü╨║╨╗╤Ä╤ç╨╡╨╜╨╕╨╡ ╤â╨╢╨╡ ╨┤╨░╤æ╤é roulette_lock. ╨Æ╨╜╤â╤é╤Ç╨╕ ╨╗╨╛╨║╨░ ╨╜╨╡╤é ╨╜╨╕ ╨╛╨┤╨╜╨╛╨│╨╛
    # await, ╨┐╨╛╤ì╤é╨╛╨╝╤â ╨┐╤Ç╨╛╨▓╨╡╤Ç╨║╨░ ╨╕ ╨╖╨░╨┐╨╕╤ü╤î ╨▓╤Ç╨╡╨╝╨╡╨╜╨╕ ╨░╤é╨╛╨╝╨░╤Ç╨╜╤ï; ╨╛╤é╨▓╨╡╤é ╤Ä╨╖╨╡╤Ç╤â ╤â╤ê╤æ╨╗
    # ╨╜╨░╤Ç╤â╨╢╤â, ╤ç╤é╨╛╨▒╤ï flood-wait ╨╜╨╡ ╨┤╨╡╤Ç╨╢╨░╨╗ ╨╗╨╛╨║ ╤Ç╤â╨╗╨╡╤é╨║╨╕.
    async with roulette_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_roll_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < 60
        if not on_cooldown:
            b_data.setdefault('last_roll_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en': cooldown_msg = "ΓÅ│ Roulette is on cooldown!"
        elif lang == 'jp': cooldown_msg = "ΓÅ│ πâ½πâ╝πâ¼πââπâêπü»πé»πâ╝πâ½πâÇπéªπâ│Σ╕¡πüºπüÖ∩╝ü"
        else: cooldown_msg = random.choice(ROULETTE_COOLDOWN_PHRASES)
        try:
            sent_msg = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent_msg, 5))
        except (TelegramBadRequest, TelegramForbiddenError): pass
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not ROULETTE_EVENTS:
        if lang == 'en': error_text = "Roulette data is not loaded."
        elif lang == 'jp': error_text = "πâ½πâ╝πâ¼πââπâêπâçπâ╝πé┐πüîΦ¬¡πü┐Φ╛╝πü╛πéîπüªπüäπü╛πü¢πéôπÇé"
        else: error_text = "╨ö╨░╨╜╨╜╤ï╨╡ ╤Ç╤â╨╗╨╡╤é╨║╨╕ ╨╜╨╡ ╨╖╨░╨│╤Ç╤â╨╢╨╡╨╜╤ï."
        try: await message.answer(error_text)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    working_msg = None
    try:
        if lang == 'en': work_txt = "ΓÅ│ Spinning the wheel..."
        elif lang == 'jp': work_txt = "ΓÅ│ πâ½πâ╝πâ¼πââπâêπéÆσ¢₧πüùπüªπüäπü╛πüÖ..."
        else: work_txt = "ΓÅ│ ╨Ü╤Ç╤â╤ç╤â ╨▒╨░╤Ç╨░╨▒╨░╨╜..."
        working_msg = await message.answer(work_txt)
        event = get_random_event(ROULETTE_EVENTS)
        if not event:
            raise ValueError("Failed to get random event.")
        event_id = event.get('id', '???')
        event_desc_plain = event.get('description', '...')
        text_for_image = f"[{event_id}]\n\n{event_desc_plain}"
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_for_image)
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="roll_result.png")
            caption_header = random.choice(ROULETTE_RESULT_PHRASES) # ╨ƒ╨╛╨║╨░ ╨╛╤ü╤é╨░╨▓╨╕╨╝ ╨╛╨▒╤ë╨╕╨╡
            await message.answer_photo(photo, caption=caption_header)
        else:
            print(f"ΓÜá∩╕Å [cmd_roll] Image generation failed. Sending text.")
            result_header = random.choice(ROULETTE_RESULT_PHRASES)
            event_desc_html = escape_html(event_desc_plain)
            result_text = f"{result_header}\n\n<b>[{event_id}]</b> {event_desc_html}"
            await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        print(f"Γ¢ö ╨₧╤ê╨╕╨▒╨║╨░ ╨▓ cmd_roll: {e}")
        if lang == 'en': err = "Error during roulette spin."
        elif lang == 'jp': err = "πâ½πâ╝πâ¼πââπâêΣ╕¡πü½πé¿πâ⌐πâ╝πüîτÖ║τöƒπüùπü╛πüùπüƒπÇé"
        else: err = "╨ƒ╤Ç╨╛╨╕╨╖╨╛╤ê╨╗╨░ ╨╛╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╨▓╤ï╨┐╨╛╨╗╨╜╨╡╨╜╨╕╨╕ ╤Ç╨╛╨╗╨╗╨░."
        try: await message.answer(err)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass
        try: await message.delete()
        except TelegramBadRequest: pass