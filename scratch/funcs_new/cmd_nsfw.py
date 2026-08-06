@dp.message(Command("nsfw"))
async def cmd_nsfw(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    current_status = b_data['user_settings'][user_id]['nsfw']
    if len(args) < 2:
        status_on = "ON"
        status_off = "OFF"
        if lang == 'en':
            msg = f"Current NSFW Spoiler status: <b>{status_on if current_status else status_off}</b>.\nUsage: <code>/nsfw on</code> or <code>/nsfw off</code>"
        elif lang == 'jp':
            msg = f"現在のNSFW設定: <b>{status_on if current_status else status_off}</b>\n使い方: <code>/nsfw on</code> または <code>/nsfw off</code>"
        else:
            msg = f"Текущий статус NSFW спойлера: <b>{status_on if current_status else status_off}</b>.\nИспользование: <code>/nsfw on</code> или <code>/nsfw off</code>"
        await message.answer(msg, parse_mode="HTML")
        return
    action = args[1].lower()
    new_status = None
    if action in ['on', 'enable', '1', 'вкл']:
        new_status = True
    elif action in ['off', 'disable', '0', 'выкл']:
        new_status = False
    if new_status is not None:
        b_data['user_settings'][user_id]['nsfw'] = new_status
        spawn_task(update_user_settings_db(user_id, board_id, nsfw=1 if new_status else 0))
        if lang == 'en':
            reply = "✅ NSFW Spoilers enabled." if new_status else "☑️ NSFW Spoilers disabled."
        elif lang == 'jp':
            reply = "✅ NSFWスポイラーを有効にしました。" if new_status else "☑️ NSFWスポイラーを無効にしました。"
        else:
            reply = "✅ Спойлеры для картинок включены." if new_status else "☑️ Спойлеры для картинок выключены."
        await message.answer(reply)
    else:
        err = "Error: Use 'on' or 'off'." if lang != 'ru' else "Ошибка: Используйте 'on' или 'off'."
        await message.answer(err)