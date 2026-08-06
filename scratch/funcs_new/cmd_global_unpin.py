@dp.message(Command("unpin"))
async def cmd_global_unpin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Снимает закреп и удаляет его из памяти/БД.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    old_pin = b_data.get('active_pin')
    b_data['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    target_post_num = None
    if message.reply_to_message:
        # Под локом только чтение карты message_to_post. Запрос к БД (фолбэк,
        # когда пост уже выгружен из RAM) вынесен наружу: раньше он выполнялся
        # удерживая storage_lock.
        async with storage_lock:
            key = (message.chat.id, message.reply_to_message.message_id)
            target_post_num = message_to_post.get(key)
        if not target_post_num:
            post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if post_info: target_post_num = post_info[0]
    else:
        target_post_num = old_pin
    if not target_post_num:
        msg = "✅ Pin reset in DB. No active post found to unpin." if lang == 'en' else ("✅ DBのピン留めをリセットしました。解除する投稿が見つかりません。" if lang == 'jp' else "✅ Закреп сброшен в БД. Активных постов для открепления не найдено.")
        await message.answer(msg)
        return
    msg_start = f"❌ Unpinning post #{target_post_num}..." if lang == 'en' else (f"❌ 投稿 #{target_post_num} のピン留めを解除中..." if lang == 'jp' else f"❌ Снимаю закреп поста #{target_post_num}...")
    status_msg = await message.answer(msg_start)
    copies = await get_post_copies(target_post_num)
    if copies:
        async def unpin_one(uid, mid):
            try:
                await message.bot.unpin_chat_message(chat_id=uid, message_id=mid)
                return True
            except Exception: return False
        CHUNK_SIZE = 40
        count = 0
        for i in range(0, len(copies), CHUNK_SIZE):
            chunk = copies[i:i + CHUNK_SIZE]
            res = await asyncio.gather(*[unpin_one(uid, mid) for uid, mid in chunk])
            count += sum(res)
            await asyncio.sleep(1.0)
        await log_global_event('bot', f"📍 UNPIN: Админ {message.from_user.id} снял закреп поста #{target_post_num} на /{board_id}/")
        if lang == 'en': final = f"✅ Post #{target_post_num} unpinned for {count} users."
        elif lang == 'jp': final = f"✅ 投稿 #{target_post_num} のピン留めを {count} 人のユーザーから解除しました。"
        else: final = f"✅ Пост #{target_post_num} откреплен у {count} юзеров. Из памяти удален."
        await status_msg.edit_text(final)
    else:
        if lang == 'en': final = f"✅ Post #{target_post_num} removed from pin settings."
        elif lang == 'jp': final = f"✅ 投稿 #{target_post_num} をピン留め設定から削除しました。"
        else: final = f"✅ Пост #{target_post_num} удален из настроек закрепа."
        await status_msg.edit_text(final)