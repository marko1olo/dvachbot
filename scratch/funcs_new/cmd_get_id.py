@dp.message(Command("id"))
async def cmd_get_id(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if not is_admin(message.from_user.id, board_id):
        await message.delete()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = message.from_user.id
    if lang == 'en': info_header = "🆔 <b>Info about you:</b>\n\n"
    elif lang == 'jp': info_header = "🆔 <b>あなたについて:</b>\n\n"
    else: info_header = "🆔 <b>Информация о вас:</b>\n\n"
    if message.reply_to_message:
        replied_author_id = None
        replied_author_id = await get_author_id_by_reply(message)
        if replied_author_id == 0:
            msg = "ℹ️ System message (bot)." if lang == 'en' else ("ℹ️ システムメッセージ（ボット）。" if lang == 'jp' else "ℹ️ Вы ответили на системное сообщение (автор: бот).")
            await message.answer(msg)
            await message.delete()
            return
        if replied_author_id:
            target_id = replied_author_id
            if lang == 'en': info_header = "🆔 <b>User Info:</b>\n\n"
            elif lang == 'jp': info_header = "🆔 <b>ユーザー情報:</b>\n\n"
            else: info_header = "🆔 <b>Информация о пользователе:</b>\n\n"
    try:
        user_chat_info = await message.bot.get_chat(target_id)
        info = info_header
        info += f"ID: <code>{target_id}</code>\n"
        if user_chat_info.first_name:
            name_lbl = "Name" if lang == 'en' else ("名前" if lang == 'jp' else "Имя")
            info += f"{name_lbl}: {escape_html(user_chat_info.first_name)}\n"
        if user_chat_info.last_name:
            sname_lbl = "Surname" if lang == 'en' else ("名字" if lang == 'jp' else "Фамилия")
            info += f"{sname_lbl}: {escape_html(user_chat_info.last_name)}\n"
        if user_chat_info.username:
            info += f"Username: @{user_chat_info.username}\n"
        b_data = board_data[board_id]
        status_lbl = f"Status on {BOARD_CONFIG[board_id]['name']}" if lang == 'en' else (f"{BOARD_CONFIG[board_id]['name']} でのステータス" if lang == 'jp' else f"Статус на доске {BOARD_CONFIG[board_id]['name']}")
        if target_id in b_data['users']['banned']:
            info += f"\n⛔️ {status_lbl}: BANNED"
        elif target_id in b_data['users']['active']:
            info += f"\n✅ {status_lbl}: Active"
        else:
            info += f"\nℹ️ {status_lbl}: Inactive"
        await message.answer(info, parse_mode="HTML")
    except Exception:
        msg = f"User ID: <code>{target_id}</code>" if lang == 'en' else (f"ユーザーID: <code>{target_id}</code>" if lang == 'jp' else f"ID пользователя: <code>{target_id}</code>")
        await message.answer(msg, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()