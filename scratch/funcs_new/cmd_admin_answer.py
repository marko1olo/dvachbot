@dp.message(Command("ans"))
async def cmd_admin_answer(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет системный ответ на пост пользователя.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        err = "Use as reply: /ans &lt;text&gt;" if lang == 'en' else ("返信として使用してください: /ans &lt;text&gt;" if lang == 'jp' else "⚠️ Ответьте на сообщение юзера: <code>/ans &lt;официальный ответ админа&gt;</code>")
        await message.answer(err, parse_mode="HTML")
        return
    raw_html = message.html_text
    answer_text = ""
    if raw_html.startswith("/ans"):
        answer_text = raw_html[4:].strip()
    else:
        answer_text = raw_html.strip()
    if not answer_text:
        err = "Enter answer text." if lang == 'en' else ("回答を入力してください。" if lang == 'jp' else "Введите текст ответа.")
        await message.answer(err)
        return
    target_post_num = None
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        target_post_num = message_to_post.get(key)
    if not target_post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: target_post_num = info[0]
    if not target_post_num:
        await message.answer("Post not found.")
        return
    target_author_id = None
    post_data = messages_storage.get(target_post_num)
    if post_data:
        target_author_id = post_data.get('author_id')
    if not target_author_id:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: target_author_id = info[1]
    now_dt = datetime.now(UTC)
    content = {
        'type': 'text',
        'text': answer_text,
        'is_system_message': True,
        'archive_allowed': True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream,
        reply_to=target_post_num 
    )
    if pnum:
        header = await format_header(board_id, pnum, 0)
        if lang == 'en': prefix = "### ADMIN ###"
        elif lang == 'jp': prefix = "### 管理人 ###"
        else: prefix = "### АДМИН ###"
        content['header'] = f"{prefix}\n{header}"
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 'timestamp': now_dt, 
                'content': content, 'board_id': board_id
            }
        b_data = board_data[board_id]
        reply_info_for_send = {}
        if target_author_id:
             user_copy = post_to_messages.get(target_post_num, {}).get(target_author_id)
             if user_copy:
                 mid = user_copy[0] if isinstance(user_copy, list) else user_copy
                 reply_info_for_send[target_author_id] = mid
        await enqueue_board_message(board_id, {
            "recipients": b_data['users']['active'],
            "content": content,
            "post_num": pnum,
            "board_id": board_id,
            "reply_info": reply_info_for_send
        })
        try: await message.delete()
        except Exception: pass