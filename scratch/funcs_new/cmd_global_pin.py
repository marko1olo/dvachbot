@dp.message(Command("pin"))
async def cmd_global_pin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Закрепляет сообщение. Сохраняет ID в память и БД, чтобы закреп пережил перезагрузку.
    """
    if not board_id: return
    if not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply to a message: <code>/del</code>" if lang == 'en' else ("返信して使ってください: <code>/del</code>" if lang == 'jp' else "⚠️ Ответьте на сообщение, которое хотите удалить: <code>/del</code>")
        await message.answer(msg, parse_mode="HTML")
        return
    post_num = None
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if post_info: post_num = post_info[0]
    if not post_num:
        err = "Post not found in DB." if lang == 'en' else ("データベースに投稿が見つかりません。" if lang == 'jp' else "Не удалось найти пост в базе.")
        await message.answer(err)
        return
    b_data = board_data[board_id]
    b_data['active_pin'] = post_num
    await update_board_settings(board_id, {'active_pin': post_num})
    copies = await get_post_copies(post_num)
    if lang == 'en':
        status_txt = f"📌 <b>New Pin:</b> Post #{post_num}\nSaved to DB ✅\nPinning for {len(copies)} users..."
    elif lang == 'jp':
        status_txt = f"📌 <b>新しいピン留め:</b> 投稿 #{post_num}\nDBに保存 ✅\n{len(copies)} 人のユーザーにピン留め中..."
    else:
        status_txt = f"📌 <b>Новый закреп:</b> Пост #{post_num}\nСохранено в памяти и БД: ✅\nЗакрепляю у {len(copies)} текущих пользователей..."
    status_msg = await message.answer(status_txt, parse_mode="HTML")
    if not copies:
        return
    count_success = 0
    async def pin_one(uid, mid):
        try:
            await message.bot.pin_chat_message(chat_id=uid, message_id=mid, disable_notification=True)
            return True
        except Exception: return False
    await log_global_event('bot', f"📌 PIN: Админ {message.from_user.id} закрепил пост #{post_num} на /{board_id}/")
    CHUNK_SIZE = 30
    for i in range(0, len(copies), CHUNK_SIZE):
        chunk = copies[i:i + CHUNK_SIZE]
        results = await asyncio.gather(*[pin_one(uid, mid) for uid, mid in chunk])
        count_success += sum(results)
        await asyncio.sleep(1.1)
    if lang == 'en':
        final = f"✅ Post #{post_num} pinned (Success: {count_success})."
    elif lang == 'jp':
        final = f"✅ 投稿 #{post_num} をピン留めしました (成功: {count_success})。"
    else:
        final = f"✅ Пост #{post_num} закреплен (Успешно: {count_success}).\nНовые пользователи тоже увидят его."
    await status_msg.edit_text(final)