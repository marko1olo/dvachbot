@dp.message(Command("gban"))
async def cmd_gban(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID/Reply needed." if lang != 'ru' else "Нужен ID или реплай.")
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    if lang == 'en': msg = f"🔨 GLOBAL BANNING <code>{target_id}</code>..."
    elif lang == 'jp': msg = f"🔨 <code>{target_id}</code> をグローバルBAN中..."
    else: msg = f"🔨 Выписываю ГЛОБАЛЬНЫЙ БАН для <code>{target_id}</code>..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    banned_count = 0
    for b_id in BOARDS:
        if b_id == 'test': continue
        try:
            await delete_user_posts(GLOBAL_BOTS[b_id], target_id, 10, b_id)
            await update_user_status(target_id, b_id, 'banned')
            async with storage_lock:
                b_data_local = board_data[b_id]
                if target_id in b_data_local['users']['active']:
                    b_data_local['users']['active'].discard(target_id)
                b_data_local['users']['banned'].add(target_id)
                if 'user_settings' in b_data_local: b_data_local['user_settings'].pop(target_id, None)
                b_data_local['last_activity'].pop(target_id, None)
                b_data_local['spam_violations'].pop(target_id, None)
            banned_count += 1
        except Exception: pass
    await log_global_event('bot', f"☢️ GBAN: Админ {message.from_user.id} выдал ГЛОБАЛЬНЫЙ БАН пользователю {target_id} на {banned_count} досках")
    if lang == 'en': final = f"☠️ User <code>{target_id}</code> destroyed on {banned_count} boards."
    elif lang == 'jp': final = f"☠️ ユーザー <code>{target_id}</code> を {banned_count} 個の板で抹殺しました。"
    else: final = f"☠️ Пользователь <code>{target_id}</code> уничтожен на {banned_count} досках."
    await status_msg.edit_text(final, parse_mode="HTML")