@dp.message(Command("deanon"))
async def cmd_deanon(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    current_time = time.time()
    # storage_lock убран: кулдаун в board_data, исключение даёт deanon_lock.
    async with deanon_lock:
        b_data = board_data[board_id]
        on_cooldown = current_time - b_data.get('last_deanon_time', 0) < DEANON_COOLDOWN
        if not on_cooldown:
            b_data['last_deanon_time'] = current_time
    if on_cooldown:
        cooldown_msg = random.choice(DEANON_COOLDOWN_PHRASES)
        try:
            sent_msg = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent_msg, 5))
        except Exception: pass
        await _safe_delete_user_message(message)
        return
    lang = 'en' if board_id == 'int' else 'ru'
    if not message.reply_to_message:
        reply_text = "👀 Reply to a message to de-anonymize!" if lang == 'en' else "⚠️ Ответьте на анонимное сообщение юзера, чтобы попытаться узнать автора: <code>/deanon</code>"
        await message.answer(reply_text, parse_mode="HTML")
        await _safe_delete_user_message(message)
        return
    user_id = message.from_user.id
    b_data = board_data[board_id] # Переопределение b_data для ясности
    user_location = 'main'
    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
    original_author_id = None
    target_post = None
    original_author_id = await get_author_id_by_reply(message)
    async with storage_lock:
        target_chat_id = message.reply_to_message.chat.id
        target_mid = message.reply_to_message.message_id
        target_post = message_to_post.get((target_chat_id, target_mid))
    if not original_author_id:
        reply_text = "🚫 Could not find the post to de-anonymize..." if lang == 'en' else "🚫 Не удалось найти пост для деанона..."
        await message.answer(reply_text)
        await _safe_delete_user_message(message)
        return
    if original_author_id == 0:
        reply_text = "⚠️ System messages cannot be de-anonymized." if lang == 'en' else "⚠️ Системные сообщения нельзя деанонить."
        await message.answer(reply_text)
        await _safe_delete_user_message(message)
        return
    deanon_text = generate_deanon_info(lang=lang)
    header_text_prefix = "### DEANON ###" if lang == 'en' else "### ДЕАНОН ###"
    now_dt = datetime.now(UTC)
    async def create_and_send_deanon_post(thread_id_override=None):
        content = {"type": "text", "text": deanon_text, "reply_to_post": target_post, "is_system_message": True}
        pnum = await create_post(
            board_id=board_id,
            author_id=0,
            content=content,
            timestamp=now_dt.timestamp(),
            is_from_site=False, stream=stream,
            thread_id_from_bot=thread_id_override
        )
        if not pnum:
            print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /deanon.")
            return
        header_text = await format_header(board_id, pnum)
        content['header'] = f"{header_text_prefix}\n{header_text}"
        content['post_num'] = pnum
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id, 'thread_id': thread_id_override}
            if thread_id_override:
                thread_info = get_thread_info(board_id, thread_id_override)
                if thread_info:
                    thread_info['last_activity_at'] = time.time()
        recipients = None
        if thread_id_override:
            thread_info = get_thread_info(board_id, thread_id_override)
            if thread_info:
                recipients = thread_info.get('subscribers', set())
        else:
            recipients = b_data.get('users', {}).get('active', set())
        if recipients:
            await enqueue_board_message(board_id, {
                "recipients": recipients, "content": content, "post_num": pnum,
                "board_id": board_id, "thread_id": thread_id_override
            })
    if board_id in THREAD_BOARDS and user_location != 'main':
        thread_id = user_location
        thread_info = get_thread_info(board_id, thread_id)
        if thread_info and not thread_info.get('is_archived'):
            await create_and_send_deanon_post(thread_id_override=thread_id)
        else: # Если тред не найден, постим на главную
             await create_and_send_deanon_post()
    else:
        await create_and_send_deanon_post()
    await _safe_delete_user_message(message)