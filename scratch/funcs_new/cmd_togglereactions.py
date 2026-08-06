@dp.message(Command("togglereactions"))
async def cmd_togglereactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    else:
        parts = (message.text or message.caption or "").split()
        if len(parts) == 2:
            try: target_id = int(parts[1])
            except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/togglereactions &lt;user_id&gt;</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/togglereactions &lt;ID&gt;</code> または返信。"
        else:
            usage = "Использование: <code>/togglereactions &lt;user_id&gt;</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    response_text = ""
    # reaction_banned_users живёт в board_data, а storage_lock охраняет
    # messages_storage — то есть здесь он был ложной зависимостью и при этом
    # удерживался через ЧЕТЫРЕ обращения к БД (add/remove_reaction_ban и два
    # log_global_event). Под локом оставлено только само переключение
    # множества: оно должно быть атомарным, чтобы два админа одновременно не
    # получили противоположные результаты. Запись в БД — уже без лока.
    async with storage_lock:
        banned_set = board_data[board_id].setdefault('reaction_banned_users', set())
        now_allowed = target_id in banned_set
        if now_allowed:
            banned_set.remove(target_id)
        else:
            banned_set.add(target_id)
    if now_allowed:
        await remove_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"🎭 REAC_OK: Админ {message.from_user.id} РАЗРЕШИЛ реакции для {target_id} на /{board_id}/")
        if lang == 'en':
            response_text = f"✅ User <code>{target_id}</code> can now use reactions again."
        elif lang == 'jp':
            response_text = f"✅ ユーザー <code>{target_id}</code> のリアクション禁止を解除しました。"
        else:
            response_text = f"✅ Пользователь <code>{target_id}</code> теперь снова может ставить реакции."
    else:
        await add_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"🎭 REAC_BAN: Админ {message.from_user.id} ЗАПРЕТИЛ реакции для {target_id} на /{board_id}/")
        if lang == 'en':
            response_text = f"🚫 User <code>{target_id}</code> is now banned from using reactions."
        elif lang == 'jp':
            response_text = f"🚫 ユーザー <code>{target_id}</code> のリアクションを禁止しました。"
        else:
            response_text = f"🚫 Пользователю <code>{target_id}</code> теперь запрещено ставить реакции."
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()