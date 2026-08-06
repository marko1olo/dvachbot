@dp.message(Command("yer", "imperial", "imperia", "dorev"))
async def cmd_yer(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(IMPERIAL_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### HIS MAJESTY ###"
    elif stream == 'jp': prefix = "### τÜçσ╕¥ΘÖ¢Σ╕ï ###"
    else: prefix = "### ╨ô╨₧╨í╨ú╨ö╨É╨á╨¼ ╨ÿ╨£╨ƒ╨ò╨á╨É╨ó╨₧╨á╨¬ ###"
    content['header'] = f"{prefix}\n{header}"
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
    await _activate_mode(board_id, 'imperial_mode')
    disable_task = spawn_task(disable_mode_after_delay(320, board_id, 'imperial_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass