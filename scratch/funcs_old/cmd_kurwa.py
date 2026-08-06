@dp.message(Command("kurwa", "polish", "poland"))
async def cmd_kurwa(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(POLISH_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"Γ¢ö [{board_id}] ╨Ü╨á╨ÿ╨ó╨ÿ╨º╨ò╨í╨Ü╨É╨» ╨₧╨¿╨ÿ╨æ╨Ü╨É: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨╛╨╖╨┤╨░╤é╤î ╨┐╨╛╤ü╤é ╨▓ ╨æ╨ö ╨┤╨╗╤Å ╨░╨║╤é╨╕╨▓╨░╤å╨╕╨╕ ╤Ç╨╡╨╢╨╕╨╝╨░ polish.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### ADMIN ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'polish_mode')
    disable_task = spawn_task(disable_mode_after_delay(305, board_id, 'polish_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()