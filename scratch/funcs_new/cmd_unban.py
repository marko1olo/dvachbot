@dp.message(Command("unban"))
async def cmd_unban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    
    args = (message.text or message.caption or "").split()
    if len(args) >= 2:
        try:
            target_id = int(args[1])
        except ValueError:
            import traceback; traceback.print_exc()
            
    if target_id is None:
        if lang == 'en': usage = "Usage: <code>/unban &lt;user_id&gt;</code> or reply to user message."
        elif lang == 'jp': usage = "使用法: <code>/unban &lt;user_id&gt;</code> またはユーザーメッセージに返信します。"
        else: usage = "Использование: <code>/unban &lt;user_id&gt;</code> или ответ на сообщение пользователя."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except Exception: pass
        return
        
    unbanned = False
    async with storage_lock:
        b_data = board_data[board_id]
        if target_id in b_data['users']['banned']:
            b_data['users']['banned'].discard(target_id)
            b_data['users']['active'].add(target_id)
            unbanned = True
            
    board_name = BOARD_CONFIG[board_id]['name']
    if unbanned:
        await add_or_activate_user(target_id, board_id) 
        if lang == 'en': msg = f"User {target_id} unbanned on {board_name}."
        elif lang == 'jp': msg = f"ユーザー {target_id} のBANを解除しました ({board_name})。"
        else: msg = f"Пользователь {target_id} разбанен на доске {board_name}."
        await message.answer(msg)
    else:
        if lang == 'en': msg = f"User {target_id} was not banned."
        elif lang == 'jp': msg = f"ユーザー {target_id} はBANされていません。"
        else: msg = f"Пользователь {target_id} не был забанен на этой доске."
        await message.answer(msg)
    try: await message.delete()
    except Exception: pass