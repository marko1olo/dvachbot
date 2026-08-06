@dp.message(Command("unshadowmute"))
async def cmd_unshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Единый обработчик снятия теневого бана.
    - Админ: Снимает теневой бан с пользователя на всей доске.
    - ОП треда: Снимает локальный теневой бан внутри треда.
    """
    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if not is_adm:
        if board_id not in THREAD_BOARDS: 
            try: await message.delete()
            except Exception: pass
            return
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main':
            await message.delete()
            return
        thread_info = get_thread_info(board_id, location)
        if not thread_info or thread_info.get('op_id') != user_id:
            await message.delete()
            return
        now_ts = time.time()
        if now_ts - user_s.get('last_op_command_ts', 0) < OP_COMMAND_COOLDOWN:
            await message.delete()
            return
        user_s['last_op_command_ts'] = now_ts
        if not message.reply_to_message:
            await message.delete()
            return
        target_id = None
        target_id = await get_author_id_by_reply(message)
        if not target_id:
            await message.delete()
            return
        local_shadow_mutes = thread_info.get('local_shadow_mutes', {})
        if target_id in local_shadow_mutes:
            del local_shadow_mutes[target_id]
            phrases = thread_messages.get(lang, {}).get('op_unmute_success', ["Unmuted."])
            response_text = random.choice(phrases)
            await message.answer(f"👻 (shadow) {response_text}", parse_mode=None)
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
        if lang == 'en':
            msg = "Usage: <code>/unshadowmute &lt;id&gt;</code> or reply."
        elif lang == 'jp':
            msg = "使用法: <code>/unshadowmute &lt;ID&gt;</code> または返信。"
        else:
            msg = "Использование: <code>/unshadowmute &lt;id&gt;</code> или ответом на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return
    was_muted = False
    async with storage_lock:
        if target_id in b_data['shadow_mutes']:
            del b_data['shadow_mutes'][target_id]
            was_muted = True
    await update_shadow_mute(target_id, board_id, 0)
    if was_muted:
        if lang == 'en':
            resp = f"👻 User <code>{target_id}</code> un-shadowmuted."
        elif lang == 'jp':
            resp = f"👻 ユーザー <code>{target_id}</code> のシャドウミュートを解除しました。"
        else:
            resp = f"👻 С пользователя <code>{target_id}</code> снят теневой мут."
        await message.answer(resp, parse_mode="HTML")
    else:
        if lang == 'en':
            resp = f"User <code>{target_id}</code> was not shadowmuted."
        elif lang == 'jp':
            resp = f"ユーザー <code>{target_id}</code> はシャドウミュートされていません。"
        else:
            resp = f"Пользователь <code>{target_id}</code> не был в теневом муте."
        await message.answer(resp, parse_mode="HTML")
    try:
        await message.delete()
    except Exception:
        import traceback; traceback.print_exc()