@dp.message(Command("sdel", "swipe"))
async def cmd_sdel(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    "Теневое" удаление поста. Удаляет все копии сообщения, кроме
    копии у автора оригинального поста. Доступно только админам.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Reply to a message to use this: <code>/sdel</code>"
        elif lang == 'jp': msg = "返信して使ってください: <code>/sdel</code>"
        else: msg = "⚠️ Ответьте на сообщение, которое хотите тихо удалить: <code>/sdel</code>"
        await message.answer(msg, parse_mode="HTML")
        await message.delete()
        return
    post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
    if not post_info:
        err = "Post not found in DB." if lang == 'en' else "Не удалось найти исходный пост в базе данных."
        await message.answer(err)
        await message.delete()
        return
    post_num, author_id = post_info
    all_copies = await get_post_copies(post_num)
    if not all_copies:
        err = f"No copies found for #{post_num}." if lang == 'en' else f"Не найдено отправленных копий для поста #{post_num}."
        await message.answer(err)
        await message.delete()
        return
    wait_txt = "🧹 Сношу посты этого юзера..." if lang != 'en' else "🧹 Wiping posts..."
    wait_msg = await message.answer(wait_txt)
    tasks = []
    for recipient_id, message_id in all_copies:
        if recipient_id != author_id:
            task = message.bot.delete_message(recipient_id, message_id)
            tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    deleted_count = sum(1 for res in results if res is True)
    await log_global_event('bot', f"👻 SDEL: Админ {message.from_user.id} скрытно удалил пост #{post_num} на /{board_id}/ (удалено {deleted_count} копий)")
    if lang == 'en':
        report = f"👻 Post #{post_num} shadow deleted.\nRemoved copies: {deleted_count} of {len(all_copies) - 1}."
    elif lang == 'jp':
        report = f"👻 投稿 #{post_num} をシャドウ削除しました。\n削除数: {deleted_count} / {len(all_copies) - 1}."
    else:
        report = f"👻 Пост #{post_num} был 'теневым' образом удален.\nУдалено копий: {deleted_count} из {len(all_copies) - 1}."
    try: await wait_msg.delete()
    except Exception: pass
    await message.answer(report)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()