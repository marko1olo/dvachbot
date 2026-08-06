@dp.message(Command("say"))
async def cmd_admin_say(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет сообщение от имени Администрации.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    raw_html = message.html_text or getattr(message, 'caption_html_text', None) or ""
    command_prefix = "/say"
    text_to_say = ""
    if raw_html.startswith(command_prefix):
        text_to_say = raw_html[len(command_prefix):].strip()
    elif message.caption and getattr(message, 'caption_html_text', '').startswith(command_prefix):
         text_to_say = getattr(message, 'caption_html_text', '')[len(command_prefix):].strip()
    else:
        text_to_say = raw_html.strip()
    content_type = message.content_type
    file_id = None
    if content_type in ['photo', 'video', 'animation', 'document', 'audio']:
        file_id_obj = getattr(message, content_type)[-1] if content_type == 'photo' else getattr(message, content_type)
        file_id = file_id_obj.file_id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not text_to_say and not file_id:
        err = "Enter text or attach media." if lang == 'en' else ("テキストを入力するかメディアを添付してください。" if lang == 'jp' else "Введите текст или прикрепите медиа.")
        await message.answer(err)
        return
    content = {
        'type': content_type if file_id else 'text',
        'is_system_message': True,
        'archive_allowed': True
    }
    if file_id:
        content['file_id'] = file_id
        content['caption'] = text_to_say
    else:
        content['text'] = text_to_say
    now_dt = datetime.now(UTC)
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if pnum:
        header = await format_header(board_id, pnum, 0)
        if lang == 'en':
            admin_title = "ADMINISTRATION"
        elif lang == 'jp':
            admin_title = "管理部"
        else:
            admin_title = "АДМИНИСТРАЦИЯ"
        content['header'] = f"🔴 <b>{admin_title}</b> 🔴\n{header}"
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 
                'timestamp': now_dt, 
                'content': content, 
                'board_id': board_id
            }
        b_data = board_data[board_id]
        await enqueue_board_message(board_id, {
            "recipients": b_data['users']['active'],
            "content": content,
            "post_num": pnum,
            "board_id": board_id
        })
        conf_txt = f"✅ Message sent (#{pnum})" if lang == 'en' else (f"✅ 送信完了 (#{pnum})" if lang == 'jp' else f"✅ Сообщение отправлено (#{pnum})")
        sent_conf = await message.answer(conf_txt)
        spawn_task(delete_message_after_delay(sent_conf, 5))
    try: await message.delete()
    except TelegramBadRequest: pass