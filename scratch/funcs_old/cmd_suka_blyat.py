@dp.message(Command("suka_blyat"))
async def cmd_suka_blyat(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    if (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC)) or \
       (user_id in b_data['mutes'] and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            import traceback; traceback.print_exc()
        return
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "≡ƒÆó≡ƒÆó≡ƒÆó ╨É╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜ ╤Ç╨╡╨╢╨╕╨╝ ╨í╨ú╨Ü╨É ╨æ╨¢╨»╨ó╨¼! ≡ƒÆó≡ƒÆó≡ƒÆó\n\n╨Æ╤ü╨╡╤à ╨╜╨░╤à╤â╨╣ ╤Ç╨░╨╖╤è╨╡╨▒╨░╨╗╨╛!",
        "╨æ╨¢╨»╨»╨»╨»╨»╨ó╨¼! ≡ƒÆÑ ╨á╨ò╨û╨ÿ╨£ ╨É╨ô╨á╨ò╨í╨í╨ÿ╨ÿ ╨Æ╨Ü╨¢╨«╨º╨ò╨¥! ╨ƒ╨ÿ╨ù╨ö╨É ╨Æ╨í╨ò╨£╨ú!",
        "╨Æ╨½ ╨º╨ò, ╨₧╨Ñ╨ú╨ò╨¢╨ÿ?! ≡ƒÆó ╨Æ╨║╨╗╤Ä╤ç╨░╤Ä ╤Ç╨╡╨╢╨╕╨╝ '╤ü╤â╨║╨░ ╨▒╨╗╤Å╤é╤î', ╨│╨╛╤é╨╛╨▓╤î╤é╨╡╤ü╤î, ╨┐╨╕╨┤╨╛╤Ç╨░╤ü╤ï!",
        "╨ù╨É╨ò╨æ╨É╨¢╨₧ ╨Æ╨í╨ü ╨¥╨É╨Ñ╨ú╨Ö! ≡ƒÆÑ ╨ƒ╨╡╤Ç╨╡╤à╨╛╨┤╨╕╨╝ ╨▓ ╤Ç╨╡╨╢╨╕╨╝ ╤é╨╛╤é╨░╨╗╤î╨╜╨╛╨╣ ╨╜╨╡╨╜╨░╨▓╨╕╤ü╤é╨╕. ╨í╨ú╨Ü╨É!",
        "≡ƒÆÑ ╨ó╨á╨ò╨⌐╨ÿ╨¥╨É ╨¥╨É╨Ñ╨ú╨Ö! ╨á╨╡╨╢╨╕╨╝ '╨Ñ╨ú╨Ö ╨ƒ╨₧╨¢╨ò╨ù╨ò╨¿╨¼' ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜!",
        "≡ƒº¿ ╨ƒ╨ÿ╨ù╨ö╨ò╨ª ╨¥╨É╨í╨ó╨ú╨ƒ╨ÿ╨¢! ╨Æ╨Ü╨¢╨«╨º╨É╨ò╨£ ╨á╨ò╨û╨ÿ╨£ ╨Ñ╨ú╨ò╨í╨₧╨í╨É╨¥╨ÿ╨»! ╨É╨É╨É ╨æ╨¢╨»╨»╨»╨ó╨¼!",
        "≡ƒö₧ ╨ü╨æ╨É╨¥╨½╨Ö ╨Æ ╨á╨₧╨ó! ╨á╨╡╨╢╨╕╨╝ ╨░╨│╤Ç╨╡╤ü╤ü╨╕╨▓╨╜╨╛╨│╨╛ ╨░╤â╤é╨╕╨╖╨╝╨░ ╨▓╨║╨╗╤Ä╤ç╨╡╨╜! ╨í╨ú╨Ü╨É!",
        "≡ƒñ¼ ╨ƒ╨ÿ╨ù╨ö╨₧╨í ╨¥╨É ╨£╨É╨Ü╨É╨á╨₧╨í! ╨á╨╡╨╢╨╕╨╝ '╨æ╨É╨ó╨» ╨Æ ╨»╨á╨₧╨í╨ó╨ÿ'! ╨Æ╨í╨ò╨£ ╨ƒ╨ÿ╨ù╨ö╨É╨¥╨ú╨ó╨¼╨í╨»!",
        "╨É ╨¥╨ú ╨æ╨¢╨»╨ó╨¼ ╨í╨ú╨Ü╨ÿ ╨í╨«╨ö╨É ╨ƒ╨₧╨ö╨₧╨¿╨¢╨ÿ! ≡ƒÆó ╨á╨╡╨╢╨╕╨╝ '╨▒╨░╤é╨╕ ╨▓ ╤Å╤Ç╨╛╤ü╤é╨╕' ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜!",
        "╨í╨ú╨Ü╨É╨É╨É╨É╨É╨É! ≡ƒÆÑ ╨ƒ╨╕╨╖╨┤╨╡╤å, ╨║╨░╨║ ╨╝╨╡╨╜╤Å ╨▓╤ü╨╡ ╨▒╨╡╤ü╨╕╤é! ╨Æ╨║╨╗╤Ä╤ç╨░╤Ä ╨┐╤Ç╨╛╤é╨╛╨║╨╛╨╗ '╨á╨É╨ù╨¬╨ò╨æ╨É╨ó╨¼'.",
        "╨⌐╨É ╨æ╨ú╨ö╨ò╨ó ╨£╨»╨í╨₧! ≡ƒö¬≡ƒö¬≡ƒö¬ ╨á╨╡╨╢╨╕╨╝ '╤ü╤â╨║╨░ ╨▒╨╗╤Å╤é╤î' ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜. ╨¥╤ï╤é╨╕╨║╨░╨╝ ╨╖╨┤╨╡╤ü╤î ╨╜╨╡ ╨╝╨╡╤ü╤é╨╛!",
        "╨ò╨æ╨É╨¥╨½╨Ö ╨ó╨½ ╨¥╨É╨Ñ╨ú╨Ö! ≡ƒÆó≡ƒÆó≡ƒÆó ╨í ╤ì╤é╨╛╨│╨╛ ╨╝╨╛╨╝╨╡╨╜╤é╨░ ╨│╨╛╨▓╨╛╤Ç╨╕╨╝ ╤é╨╛╨╗╤î╨║╨╛ ╨╝╨░╤é╨╛╨╝. ╨ƒ╨╛╨╜╤Å╨╗╨╕, ╤â╨╡╨▒╨░╨╜╤ï?",
        "╨ó╨É╨Ü, ╨æ╨¢╨»╨ó╨¼! ≡ƒÆÑ ╨í╨╗╤â╤ê╨░╤é╤î ╨╝╨╛╤Ä ╨║╨╛╨╝╨░╨╜╨┤╤â! ╨á╨╡╨╢╨╕╨╝ '╨í╨ú╨Ü╨É ╨æ╨¢╨»╨ó╨¼' ╨░╨║╤é╨╕╨▓╨╡╨╜. ╨Æ╨╛╨╗╤î╨╜╨╛, ╨▒╨╗╤Å╨┤╨╕!",
        "≡ƒÆó ╨ö╨É ╨ó╨½ ╨ü╨æ╨¥╨ú╨ó╨½╨Ö? ╨á╨ò╨û╨ÿ╨£ '╨Ñ╨ú╨Ö ╨ƒ╨₧╨¢╨ò╨ù╨ò╨¿╨¼' ╨É╨Ü╨ó╨ÿ╨Æ╨ÿ╨á╨₧╨Æ╨É╨¥!",
        "≡ƒÉù ╨í╨Æ╨ÿ╨¥╨₧╨ƒ╨É╨í ╨Æ╨½╨¿╨ò╨¢ ╨¥╨É ╨ó╨á╨₧╨ƒ╨ú ╨Æ╨₧╨Ö╨¥╨½! ╨Æ╨Ü╨¢╨«╨º╨É╨ò╨£ ╨á╨ò╨û╨ÿ╨£ ╨Ñ╨ú╨ò╨í╨₧╨í╨É╨¥╨ÿ╨»!",
        "≡ƒö₧ ╨ƒ╨ÿ╨ù╨ö╨ò╨ª ╨¥╨É╨í╨ó╨ú╨ƒ╨ÿ╨¢! ╨Æ╨í╨ò╨£ ╨ƒ╨ÿ╨ù╨ö╨É╨¥╨ú╨ó╨¼╨í╨» ╨Æ ╨ú╨ô╨₧╨¢! ╨É╨É╨É╨É ╨æ╨¢╨»╨»╨»╨ó╨¼!",
        "╨ƒ╨₧╨¿╨¢╨ÿ ╨¥╨É╨Ñ╨ú╨Ö! ≡ƒÆÑ ╨Æ╨í╨ò ╨ƒ╨₧╨¿╨¢╨ÿ ╨¥╨É╨Ñ╨ú╨Ö! ╨á╨╡╨╢╨╕╨╝ ╤Å╤Ç╨╛╤ü╤é╨╕ ╨▓╨║╨╗╤Ä╤ç╨╡╨╜, ╤ü╤â╨║╨╕!",
        "≡ƒñ¼ ╨í╨ú╨Ü╨É ╨æ╨¢╨»╨ó╨¼! ╨á╨ò╨û╨ÿ╨£ '╨æ╨É╨ó╨» ╨Æ ╨»╨á╨₧╨í╨ó╨ÿ' ╨É╨Ü╨ó╨ÿ╨Æ╨ÿ╨á╨₧╨Æ╨É╨¥! ╨Æ╨í╨ò╨£ ╨ƒ╨ÿ╨ù╨ö╨É╨¥╨ú╨ó╨¼╨í╨»!",
        "╨⌐╨É ╨æ╨ú╨ö╨ò╨ó ╨£╨»╨í╨₧! ≡ƒö¬ ╨á╨╡╨╢╨╕╨╝ '╤ü╤â╨║╨░ ╨▒╨╗╤Å╤é╤î' ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜. ╨¥╤ï╤é╨╕╨║╨░╨╝ ╨╖╨┤╨╡╤ü╤î ╨╜╨╡ ╨╝╨╡╤ü╤é╨╛!"
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
        print(f"Γ¢ö [{board_id}] ╨Ü╨á╨ÿ╨ó╨ÿ╨º╨ò╨í╨Ü╨É╨» ╨₧╨¿╨ÿ╨æ╨Ü╨É: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨╛╨╖╨┤╨░╤é╤î ╨┐╨╛╤ü╤é ╨▓ ╨æ╨ö ╨┤╨╗╤Å ╨░╨║╤é╨╕╨▓╨░╤å╨╕╨╕ ╤Ç╨╡╨╢╨╕╨╝╨░ suka_blyat.")
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
    await _activate_mode(board_id, 'suka_blyat_mode')
    disable_task = spawn_task(disable_mode_after_delay(303, board_id, 'suka_blyat_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()