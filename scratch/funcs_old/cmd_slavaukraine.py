@dp.message(Command("slavaukraine", "slava_ukraine", "ukraine", "ukraina", "hohol"))
async def cmd_slavaukraine(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except TelegramBadRequest as e:
            if "message to delete not found" not in e.message.lower():
                print(f"╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤â╨┤╨░╨╗╨╕╤é╤î ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ {message.message_id} ╨▓ cmd_slavaukraine (INT): {e}")
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "╨ú╨Æ╨É╨ô╨É! ╨É╨Ü╨ó╨ÿ╨Æ╨₧╨Æ╨É╨¥╨₧ ╨ú╨Ü╨á╨É╨ç╨¥╨í╨¼╨Ü╨ÿ╨Ö ╨á╨ò╨û╨ÿ╨£!\n\n≡ƒÆÖ≡ƒÆ¢ ╨í╨¢╨É╨Æ╨É ╨ú╨Ü╨á╨É╨ç╨¥╨å! ≡ƒÆ¢≡ƒÆÖ\n╨ô╨ò╨á╨₧╨»╨£ ╨í╨¢╨É╨Æ╨É!\n\n╨Ñ╤é╨╛ ╨╜╨╡ ╤ü╨║╨░╨╢╨╡ '╨ƒ╤â╤é╤û╨╜ ╤à╤â╨╣╨╗╨╛' - ╤é╨╛╨╣ ╨╝╨╛╤ü╨║╨░╨╗╤î ╤û ╨┐╤û╨┤╨░╤Ç!",
        "╨ú╨Ü╨á╨É╨ç╨¥╨í╨¼╨Ü╨ÿ╨Ö ╨á╨ò╨û╨ÿ╨£ ╨ú╨Æ╨å╨£╨Ü╨¥╨ò╨¥╨₧! ≡ƒç║≡ƒçª ╨Æ╤ü╤û ╨╝╨╛╤ü╨║╨░╨╗╤û ╨▒╤â╨┤╤â╤é╤î ╨┤╨╡╨╜╨░╤å╨╕╤ä╤û╨║╨╛╨▓╨░╨╜╤û ╤é╨░ ╨┤╨╡╨╝╤û╨╗╤û╤é╨░╤Ç╨╕╨╖╨╛╨▓╨░╨╜╤û. ╨í╨╝╨╡╤Ç╤é╤î ╨▓╨╛╤Ç╨╛╨│╨░╨╝!",
        "╨ú╨Æ╨É╨ô╨É! ╨Æ ╤ç╨░╤é╤û ╨╛╨│╨╛╨╗╨╛╤ê╨╡╨╜╨╛ ╨║╨╛╨╜╤é╤Ç╨╜╨░╤ü╤é╤â╨┐! ≡ƒÜ£ ╨í╨¢╨É╨Æ╨É ╨¥╨É╨ª╨å╨ç! ╨ƒ╨ÿ╨ù╨ö╨ò╨ª╨¼ ╨á╨₧╨í╨å╨Ö╨í╨¼╨Ü╨å╨Ö ╨ñ╨ò╨ö╨ò╨á╨É╨ª╨å╨ç!",
        "≡ƒÆÖ≡ƒÆ¢ ╨ƒ╨╡╤Ç╨╡╤à╨╛╨┤╨╕╨╝╨╛ ╨╜╨░ ╤ü╨╛╨╗╨╛╨▓'╤ù╨╜╤â! ╨Ñ╤é╨╛ ╨╜╨╡ ╤ü╨║╨░╤ç╨╡, ╤é╨╛╨╣ ╨╝╨╛╤ü╨║╨░╨╗╤î! ╨í╨¢╨É╨Æ╨É ╨ù╨í╨ú!",
        "╨É╨Ü╨ó╨ÿ╨Æ╨₧╨Æ╨É╨¥╨₧ ╨á╨ò╨û╨ÿ╨£ '╨æ╨É╨¥╨ö╨ò╨á╨₧╨£╨₧╨æ╨å╨¢╨¼'! ≡ƒç║≡ƒçª ╨ù╨░╨▓╨░╨╜╤é╨░╨╢╤â╤ö╨╝╨╛ Javelin... ╨ª╤û╨╗╤î: ╨Ü╤Ç╨╡╨╝╨╗╤î.",
        "╨ú╨Ü╨á╨É╨ç╨¥╨í╨¼╨Ü╨ÿ╨Ö ╨ƒ╨₧╨á╨»╨ö╨₧╨Ü ╨¥╨É╨Æ╨ò╨ö╨ò╨¥╨₧! ≡ƒ½í ╨ô╨╛╤é╤â╨╣╤é╨╡╤ü╤Å ╨┤╨╛ ╨┐╨╛╨▓╨╜╨╛╨│╨╛ ╤Ç╨╛╨╖╨│╤Ç╨╛╨╝╤â ╤Ç╤â╤ü╨╜╤û. ╨ƒ╤â╤é╤û╨╜ - ╤à╤â╨╣╨╗╨╛!",
        "╨ó╨ò╨á╨£╨å╨¥╨₧╨Æ╨₧! ╨Æ ╤ç╨░╤é╤û ╨▓╨╕╤Å╨▓╨╗╨╡╨╜╨╛ ╤Ç╤â╤ü╨╜╤Ä! ╨É╨║╤é╨╕╨▓╨╛╨▓╨░╨╜╨╛ ╨┐╤Ç╨╛╤é╨╛╨║╨╛╨╗ '╨É╨ù╨₧╨Æ'. ≡ƒç║≡ƒçª ╨í╨╗╨░╨▓╨░ ╨ú╨║╤Ç╨░╤ù╨╜╤û!",
        "╨á╨╡╨╢╨╕╨╝ '╨ƒ╨á╨ÿ╨Æ╨ÿ╨ö ╨Ü╨ÿ╨ä╨Æ╨É' ╨░╨║╤é╨╕╨▓╨╛╨▓╨░╨╜╨╛! Γ£ê∩╕Å ╨Æ╨╕╨╗╤û╤é╨░╤ö╨╝╨╛ ╨╜╨░ ╨▒╨╛╨╣╨╛╨▓╨╡ ╨╖╨░╨▓╨┤╨░╨╜╨╜╤Å. ╨á╤â╤ü╨║╤û╨╣ ╨▓╨╛╤ö╨╜╨╜╨╕╨╣ ╨║╨╛╤Ç╨░╨▒╨╗╤î, ╤û╨┤╤û ╨╜╨░╤à╤â╨╣!",
        "╨¥╨░╤ü╤é╤â╨┐╨╜╤û 5 ╤à╨▓╨╕╨╗╨╕╨╜ ╨▓ ╤ç╨░╤é╤û - ╨╗╨╕╤ê╨╡ ╤â╨║╤Ç╨░╤ù╨╜╤ü╤î╨║╨░ ╨╝╨╛╨▓╨░! ≡ƒÆÖ≡ƒÆ¢ ╨ù╨░ ╨╜╨╡╨┐╨╛╨║╨╛╤Ç╤â - ╤Ç╨╛╨╖╤ü╤é╤Ç╤û╨╗ ╨╜╨░╤à╤â╨╣. ╨ô╨╡╤Ç╨╛╤Å╨╝ ╨í╨╗╨░╨▓╨░!",
        "≡ƒÆÖ≡ƒÆ¢ ╨Æ╨É╨Ñ╨ó╨É ╨¥╨É ╨ù╨É╨Æ╨É╨¢╨å! ╨Æ╨╝╨╕╨║╨░╤ö╨╝╨╛ ╤Ç╨╡╨╢╨╕╨╝ '╨Ü╨å╨æ╨ò╨á╨ƒ╨₧╨¢╨Ü ╨É╨ù╨₧╨Æ'! ╨í╨£╨ò╨á╨ó╨¼ ╨á╨ú╨í╨¥╨å!",
        "╨æ╨É╨¥╨ö╨ò╨á╨₧╨Æ╨ò╨ª╨¼ ╨Æ ╨º╨É╨ó╨å! ≡ƒÆ¢≡ƒÆÖ ╨ƒ╨╡╤Ç╨╡╤à╨╛╨┤╨╕╨╝╨╛ ╨╜╨░ ╤â╨║╤Ç╨░╤ù╨╜╤ü╤î╨║╨╕╨╣ ╤é╤Ç╨╛╨╗╤û╨╜╨│. ╨ƒ╤â╤é╤û╨╜ - ╤à╤â╨╣╨╗╨╛!",
        "≡ƒÆú ╨Ñ╨ò╨á╨í╨₧╨¥╨¼ ╨¥╨É╨¿! ╨á╨╡╨╢╨╕╨╝ '╨ö╨á╨₧╨¥-╨Ü╨É╨£╨ÿ╨Ü╨É╨ö╨ù╨ò' ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜! ╨í╨¢╨É╨Æ╨É ╨ù╨í╨ú!",
        "≡ƒöÑ ╨ö╨ò╨£╨₧╨¥╨å╨º╨¥╨ÿ╨Ö ╨á╨ò╨û╨ÿ╨£ ╨Æ╨Æ╨å╨£╨Ü╨¥╨ò╨¥╨₧! ╨ù╨░╨┐╨░╨╗╤Ä╤ö╨╝╨╛ ╤Ç╤â╤ü╤ü╨║╤û╨╣ ╨║╨╛╤Ç╨░╨▒╨╗╤î! ╨å╨ö╨ÿ ╨¥╨É╨Ñ╨ú╨Ö!",
        "≡ƒ¬û ╨ó╨ò╨á╨₧╨æ╨₧╨á╨₧╨¥╨ò╨ª╨¼ ╨ú ╨º╨É╨ó╨å! ╨ƒ╨╡╤Ç╨╡╤à╨╛╨┤╨╕╨╝╨╛ ╨╜╨░ ╤â╨║╤Ç╨░╤ù╨╜╤ü╤î╨║╨╕╨╣ ╤é╤Ç╨╛╨╗╤û╨╜╨│. ╨ƒ╤â╤é╤û╨╜ - ╤à╤â╨╣╨╗╨╛!",
        "ΓÜö∩╕Å ╨¿╨É╨Ñ╨ó╨É╨á╨í╨¼╨Ü╨ÿ╨Ö ╨¥╨É╨í╨ó╨ú╨ƒ! ╨á╨╡╨╢╨╕╨╝ '╨í╨¢╨É╨Æ╨É ╨¥╨É╨ª╨å╨ç' ╨░╨║╤é╨╕╨▓╨╛╨▓╨░╨╜╨╛! ╨ô╨ò╨á╨₧╨»╨£ ╨í╨¢╨É╨Æ╨É!",
        "≡ƒö▒ ╨ó╨ò╨á╨£╨å╨¥╨₧╨Æ╨₧! ╨ú ╨º╨É╨ó╨å ╨ù'╨»╨Æ╨ÿ╨Æ╨í╨» ╨Ñ╨É╨í╨Ü! ╨á╨╡╨╢╨╕╨╝ '╨í╨¢╨É╨Æ╨É ╨¥╨É╨ª╨å╨ç' ╨░╨║╤é╨╕╨▓╨╛╨▓╨░╨╜╨╛!",
        "╨ú╨Æ╨É╨ô╨É! ╨ó╨╡╤Ç╨╕╤é╨╛╤Ç╤û╤Å ╤å╤î╨╛╨│╨╛ ╤ç╨░╤é╤â ╨╛╨│╨╛╨╗╨╛╤ê╤â╤ö╤é╤î╤ü╤Å ╤ü╤â╨▓╨╡╤Ç╨╡╨╜╨╜╨╛╤Ä ╤é╨╡╤Ç╨╕╤é╨╛╤Ç╤û╤ö╤Ä ╨ú╨║╤Ç╨░╤ù╨╜╨╕! ≡ƒç║≡ƒçª ╨í╨¢╨É╨Æ╨É ╨ú╨Ü╨á╨É╨ç╨¥╨å!"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"Γ¢ö [{board_id}] ╨Ü╨á╨ÿ╨ó╨ÿ╨º╨ò╨í╨Ü╨É╨» ╨₧╨¿╨ÿ╨æ╨Ü╨É: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨╛╨╖╨┤╨░╤é╤î ╨┐╨╛╤ü╤é ╨▓ ╨æ╨ö ╨┤╨╗╤Å ╨░╨║╤é╨╕╨▓╨░╤å╨╕╨╕ ╤Ç╨╡╨╢╨╕╨╝╨░ slavaukraine.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum) 
    header = f"### ╨É╨┤╨╝╨╕╨╜ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'slavaukraine_mode')
    disable_task = spawn_task(disable_mode_after_delay(310, board_id, 'slavaukraine_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest as e:
        if "message to delete not found" not in e.message.lower():
            print(f"╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤â╨┤╨░╨╗╨╕╤é╤î ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ {message.message_id} ╨▓ cmd_slavaukraine: {e}")