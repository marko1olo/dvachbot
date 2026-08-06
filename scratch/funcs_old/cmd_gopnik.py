@dp.message(Command("gopnik", "blyat", "gopota"))
async def cmd_gopnik(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int': # ╨₧╤é╨║╨╗╤Ä╤ç╨░╨╡╨╝ ╨╜╨░ int
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(GOPNIK_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
        print(f"Γ¢ö [{board_id}] Error activating gopnik mode.")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### ADMIN ###"
    elif stream == 'jp': prefix = "### τ«íτÉåΣ║║ ###"
    else: prefix = "### ╨É╨ö╨£╨ÿ╨¥ ###"
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
    await _activate_mode(board_id, 'gopnik_mode')
    disable_task = spawn_task(disable_mode_after_delay(300, board_id, 'gopnik_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass