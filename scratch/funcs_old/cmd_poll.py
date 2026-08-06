@dp.message(Command("poll", "opros"))
async def cmd_poll(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    ╨ó╨╛╤ç╨║╨░ ╨▓╤à╨╛╨┤╨░ ╨▓ FSM ╨┤╨╗╤Å ╤ü╨╛╨╖╨┤╨░╨╜╨╕╤Å ╨╛╨┐╤Ç╨╛╤ü╨░.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now = time.time()
    if now - last_poll_creation_time[user_id] < 60:
        await message.delete()
        try:
            if lang == 'en':
                cooldown_msg = "ΓÅ│ Poll creation is allowed once per minute."
            elif lang == 'jp':
                cooldown_msg = "ΓÅ│ µèòτÑ¿πü«Σ╜£µêÉπü»1σêåπü½1σ¢₧πü╛πüºπüºπüÖπÇé"
            else:
                cooldown_msg = "ΓÅ│ ╨í╨╛╨╖╨┤╨░╨▓╨░╤é╤î ╨╛╨┐╤Ç╨╛╤ü╤ï ╨╝╨╛╨╢╨╜╨╛ ╤Ç╨░╨╖ ╨▓ ╨╝╨╕╨╜╤â╤é╤â."
            sent = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent, 5))
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    full_text = message.text or message.caption or ""
    if message.reply_to_message and message.reply_to_message.media_group_id:
        await message.delete()
        if lang == 'en':
            error_text = "Attaching media groups to polls is not supported. Please reply to a single photo or video."
        elif lang == 'jp':
            error_text = "πâíπâçπéúπéóπé░πâ½πâ╝πâùπéÆµèòτÑ¿πü½µ╖╗Σ╗ÿπüÖπéïπüôπü¿πü»πüºπüìπü╛πü¢πéôπÇéσìÿΣ╕Çπü«τö╗σâÅπü╛πüƒπü»σïòτö╗πü½Φ┐öΣ┐íπüùπüªπüÅπüáπüòπüäπÇé"
        else:
            error_text = "╨ƒ╤Ç╨╕╨║╤Ç╨╡╨┐╨╗╨╡╨╜╨╕╨╡ ╨╝╨╡╨┤╨╕╨░╨│╤Ç╤â╨┐╨┐ ╨║ ╨╛╨┐╤Ç╨╛╤ü╨░╨╝ ╨╜╨╡ ╨┐╨╛╨┤╨┤╨╡╤Ç╨╢╨╕╨▓╨░╨╡╤é╤ü╤Å. ╨ƒ╨╛╨╢╨░╨╗╤â╨╣╤ü╤é╨░, ╨╛╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╨╛╨┤╨╜╨╛ ╨║╨╛╨╜╨║╤Ç╨╡╤é╨╜╨╛╨╡ ╤ä╨╛╤é╨╛ ╨╕╨╗╨╕ ╨▓╨╕╨┤╨╡╨╛."
        try:
            await message.answer(error_text)
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    command_part, *data_parts = full_text.split('|', 1)
    question_text = command_part.replace("/poll", "").replace("/opros", "").strip()
    options = [opt.strip() for opt in data_parts[0].split('|')] if data_parts else []
    if not question_text or len(options) < 2 or len(options) > 5:
        await message.delete()
        if lang == 'en':
            usage_text = (
                "<b>Invalid format!</b>\n"
                "Use the separator `|` between the question and each option.\n\n"
                "<u>Example:</u>\n"
                "<code>/poll Is Abu gay? | Yes | Of course | Absolutely</code>\n\n"
                "<i>(2 to 5 options)</i>"
            )
        elif lang == 'jp':
            usage_text = (
                "<b>πâòπé⌐πâ╝πâ₧πââπâêπé¿πâ⌐πâ╝∩╝ü</b>\n"
                "Φ│¬σòÅπü¿σÉäΘü╕µè₧Φéóπü«Θûôπü½σî║σêçπéèµûçσ¡ù `|` πéÆΣ╜┐τö¿πüùπüªπüÅπüáπüòπüäπÇé\n\n"
                "<u>Σ╛ï:</u>\n"
                "<code>/poll Abuπü»πâ¢πâó∩╝ƒ | πü»πüä | πééπüíπéìπéô | τ╡╢σ»╛πü½</code>\n\n"
                "<i>(Θü╕µè₧Φéóπü»2πÇ£5σÇï)</i>"
            )
        else:
            usage_text = (
                "<b>╨¥╨╡╨▓╨╡╤Ç╨╜╤ï╨╣ ╤ä╨╛╤Ç╨╝╨░╤é!</b>\n"
                "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╣╤é╨╡ ╤Ç╨░╨╖╨┤╨╡╨╗╨╕╤é╨╡╨╗╤î `|` ╨╝╨╡╨╢╨┤╤â ╨▓╨╛╨┐╤Ç╨╛╤ü╨╛╨╝ ╨╕ ╨║╨░╨╢╨┤╤ï╨╝ ╨▓╨░╤Ç╨╕╨░╨╜╤é╨╛╨╝ ╨╛╤é╨▓╨╡╤é╨░.\n\n"
                "<u>╨ƒ╤Ç╨╕╨╝╨╡╤Ç:</u>\n"
                "<code>/poll ╨É╨▒╤â ╤ü╨╛╤ü╨╡╤é ╤à╤â╨╣? | ╨ö╨░ | ╨Ü╨╛╨╜╨╡╤ç╨╜╨╛ | ╨æ╨╡╨╖╤â╤ü╨╗╨╛╨▓╨╜╨╛</code>\n\n"
                "<i>(╨₧╤é 2 ╨┤╨╛ 5 ╨▓╨░╤Ç╨╕╨░╨╜╤é╨╛╨▓ ╨╛╤é╨▓╨╡╤é╨░)</i>"
            )
        try:
            await message.answer(usage_text, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    attached_media = None
    reply_to_check = message
    if message.text and message.reply_to_message:
        reply_to_check = message.reply_to_message
    media_type = reply_to_check.content_type
    if media_type in ['photo', 'video', 'animation']:
        file_id_obj = getattr(reply_to_check, media_type)
        if isinstance(file_id_obj, list): file_id_obj = file_id_obj[-1]
        attached_media = {'type': media_type, 'file_id': file_id_obj.file_id}
    poll_fsm_data = {
        'question': question_text,
        'options': options,
        'attached_media': attached_media
    }
    await state.set_state(PollCreationStates.waiting_for_confirmation)
    await state.update_data(poll_data=poll_fsm_data)
    last_poll_creation_time[user_id] = now
    temp_poll_display_data = {
        'question': question_text,
        'options': options,
        'votes': {str(i): [] for i in range(len(options))}
    }
    preview_text = generate_poll_text_display(temp_poll_display_data)
    if lang == 'en':
        confirm_text = f"Here is how your poll will look:\n\n{preview_text}\n\nCreate?"
        btn_yes, btn_no = "Γ£à Yes, create", "Γ¥î Cancel"
    elif lang == 'jp':
        confirm_text = f"µèòτÑ¿πü»Σ╗ÑΣ╕ïπü«πéêπüåπü½πü¬πéèπü╛πüÖ:\n\n{preview_text}\n\nΣ╜£µêÉπüùπü╛πüÖπüï∩╝ƒ"
        btn_yes, btn_no = "Γ£à Σ╜£µêÉ", "Γ¥î πé¡πâúπâ│πé╗πâ½"
    else:
        confirm_text = f"╨ó╨░╨║ ╨▒╤â╨┤╨╡╤é ╨▓╤ï╨│╨╗╤Å╨┤╨╡╤é╤î ╨▓╨░╤ê ╨╛╨┐╤Ç╨╛╤ü:\n\n{preview_text}\n\n╨í╨╛╨╖╨┤╨░╨╡╨╝?"
        btn_yes, btn_no = "Γ£à ╨ö╨░, ╤ü╨╛╨╖╨┤╨░╤é╤î", "Γ¥î ╨₧╤é╨╝╨╡╨╜╨░"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=btn_yes, callback_data="poll_confirm_create"),
            InlineKeyboardButton(text=btn_no, callback_data="poll_cancel_create")
        ]
    ])
    try:
        if attached_media:
            media_type = attached_media['type']
            file_id = attached_media['file_id']
            caption = confirm_text
            if len(caption) > 1024: caption = caption[:1021] + "..."
            if media_type == 'photo':
                await message.answer_photo(photo=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'video':
                await message.answer_video(video=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'animation':
                await message.answer_animation(animation=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(confirm_text, reply_markup=keyboard, parse_mode="HTML")
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        print(f"╨₧╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╨╛╤é╨┐╤Ç╨░╨▓╨║╨╡ ╨┐╤Ç╨╡╨┤╨┐╤Ç╨╛╤ü╨╝╨╛╤é╤Ç╨░ ╨╛╨┐╤Ç╨╛╤ü╨░: {e}")
        await state.clear()
        try:
            err_msg = "Failed to send preview." if lang == 'en' else ("πâùπâ¼πâôπâÑπâ╝πü«ΘÇüΣ┐íπü½σñ▒µòùπüùπü╛πüùπüƒπÇé" if lang == 'jp' else "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╛╤é╨┐╤Ç╨░╨▓╨╕╤é╤î ╨┐╤Ç╨╡╨┤╨┐╤Ç╨╛╤ü╨╝╨╛╤é╤Ç.")
            await message.answer(err_msg)
            await message.delete()
        except Exception:
            import traceback; traceback.print_exc()