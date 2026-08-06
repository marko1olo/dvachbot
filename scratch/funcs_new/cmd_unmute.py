@dp.message(Command("unmute"))
async def cmd_unmute(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not is_adm:
        if board_id not in THREAD_BOARDS: return
        b_data = board_data[board_id]
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main': return
        thread_info = get_thread_info(board_id, location)
        if not thread_info or thread_info.get('op_id') != user_id: return
        if not message.reply_to_message: await message.delete(); return
        target_id = None
        target_id = await get_author_id_by_reply(message)
        if not target_id: await message.delete(); return
        if target_id in thread_info.get('local_mutes', {}):
            del thread_info['local_mutes'][target_id]
            resp = random.choice(thread_messages[lang]['op_unmute_success'])
            await message.answer(f"🔊 {resp}", parse_mode=None)
        await message.delete()
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    else:
        parts = (message.text or message.caption or "").split()
        if len(parts) == 2:
            try: target_id = int(parts[1])
            except ValueError: pass
    if not target_id:
        msg = "Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай.")
        await message.answer(msg); return
    unmuted = False
    async with storage_lock:
        if board_data[board_id]['mutes'].pop(target_id, None): unmuted = True
    await remove_regular_mute(target_id, board_id)
    if unmuted: 
        if lang == 'en': txt = f"🔊 User {target_id} unmuted."
        elif lang == 'jp': txt = f"🔊 ユーザー {target_id} のミュートを解除しました。"
        else: txt = f"🔊 Пользователь {target_id} размучен."
        await message.answer(txt)
    else: 
        if lang == 'en': txt = f"User {target_id} was not muted."
        elif lang == 'jp': txt = f"ユーザー {target_id} はミュートされていません。"
        else: txt = f"Пользователь {target_id} не был в муте."
        await message.answer(txt)
    try: await message.delete()
    except Exception: pass