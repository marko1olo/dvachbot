@dp.message(Command("redact"))
async def cmd_redact(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: await message.delete()
    except Exception: pass
    if not message.reply_to_message:
        await message.answer("❌ Используй /redact в ответ на свое сообщение.")
        return

    key = (message.chat.id, message.reply_to_message.message_id)
    post_num = message_to_post.get(key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
        
    if not post_num:
        await message.answer("❌ Не найдено в базе.")
        return
        
    target_id = await get_author_id_by_reply(message)
    if target_id != message.from_user.id:
        await message.answer("❌ Ты не можешь редактировать чужие сообщения!")
        return

    msg_status = await message.answer("⏳ Удаляем контент из всех копий...")
    
    # Get board_id of the post
    post_board = None
    if post_num in messages_storage:
        post_board = messages_storage[post_num].get('board_id')
    if not post_board:
        db = await get_pool()
        async with db.execute("SELECT board_id FROM Posts WHERE post_num = ?", (post_num,)) as c:
            row = await c.fetchone()
            if row:
                post_board = row[0]
    if not post_board:
        post_board = board_id

    # Get all user copies
    db_copies = await get_post_copies(post_num)
    success_count = 0
    for rec_id, msg_id in db_copies:
        try:
            # Используем правильного бота доски для ЛС
            target_bot = GLOBAL_BOTS.get(post_board) or message.bot
            try:
                await target_bot.edit_message_text(
                    chat_id=rec_id,
                    message_id=msg_id,
                    text="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                    parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                err_str = str(e).lower()
                if "message is not modified" in err_str:
                    pass
                elif "there is no text in the message" in err_str or "message to edit not found" not in err_str:
                    try:
                        await target_bot.edit_message_caption(
                            chat_id=rec_id,
                            message_id=msg_id,
                            caption="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        import traceback; traceback.print_exc()
            success_count += 1
            await asyncio.sleep(0.04)
        except Exception:
            import traceback; traceback.print_exc()

    # Get and update all channel copies (mirrors)
    from common.database import get_all_channel_copies
    channel_copies = await get_all_channel_copies(post_num)
    if channel_copies:
        target_bot = GLOBAL_BOTS.get(post_board) or message.bot
        for chan_id, msg_id in channel_copies:
            try:
                try:
                    await target_bot.edit_message_text(
                        chat_id=chan_id,
                        message_id=msg_id,
                        text="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                        parse_mode="HTML"
                    )
                except TelegramBadRequest as e:
                    err_str = str(e).lower()
                    if "message is not modified" in err_str:
                        pass
                    elif "there is no text in the message" in err_str or "message to edit not found" not in err_str:
                        try:
                            await target_bot.edit_message_caption(
                                chat_id=chan_id,
                                message_id=msg_id,
                                caption="<b>[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]</b>",
                                parse_mode="HTML"
                            )
                        except Exception:
                            import traceback; traceback.print_exc()
                success_count += 1
                await asyncio.sleep(0.04)
            except Exception:
                import traceback; traceback.print_exc()

    async with storage_lock:
        if post_num in messages_storage:
            content_dict = messages_storage[post_num].get('content', {})
            if 'text' in content_dict:
                content_dict['text'] = "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"
            if 'caption' in content_dict:
                content_dict['caption'] = "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"
                
    # Update SQLite explicitly using the database connection
    try:
        from common.database import update_post_content
        content_dict = {}
        if post_num in messages_storage:
            content_dict = messages_storage[post_num].get('content', {})
        else:
            content_dict = {"type": "text", "text": "[ДАННЫЕ УДАЛЕНЫ АВТОРОМ]"}
        await update_post_content(post_num, content_dict)
    except Exception as e:
        runtime_logger.warning(f"Could not update db text for redact: {e}")
    
    try: await msg_status.delete()
    except Exception: pass
    
    st_msg = await message.answer(f"✅ Успешно удалено у {success_count} пользователей/зеркал.")
    await asyncio.sleep(4)
    try: await st_msg.delete()
    except Exception: pass