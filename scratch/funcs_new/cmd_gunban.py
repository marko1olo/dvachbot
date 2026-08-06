@dp.message(Command("gunban"))
async def cmd_gunban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Снимает БАН и ТЕНЕВОЙ МУТ с пользователя СРАЗУ НА ВСЕХ досках.
    """
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
    if lang == 'en': msg = f"🕊️ Global Amnesty for <code>{target_id}</code>..."
    elif lang == 'jp': msg = f"🕊️ <code>{target_id}</code> へのグローバル恩赦..."
    else: msg = f"🕊️ Глобальная амнистия для <code>{target_id}</code>..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    count = 0
    for b_id in BOARDS:
        try:
            unbanned = False
            async with storage_lock:
                b_data_local = board_data[b_id]
                if target_id in b_data_local['users']['banned']:
                    b_data_local['users']['banned'].discard(target_id)
                    b_data_local['users']['active'].add(target_id)
                    unbanned = True
                if target_id in b_data_local['shadow_mutes']:
                    del b_data_local['shadow_mutes'][target_id]
                    unbanned = True
            if unbanned:
                await add_or_activate_user(target_id, b_id)
                await update_shadow_mute(target_id, b_id, 0)
                count += 1
        except Exception as e:
            runtime_logger.error(f"Error during global unban on board {b_id} for user {target_id}: {e}", exc_info=True)
    await log_global_event('bot', f"🕊️ GUNBAN: Админ {message.from_user.id} ГЛОБАЛЬНО РАЗБАНИЛ {target_id} на {count} досках")
    if lang == 'en': final = f"✅ User <code>{target_id}</code> unbanned/unmuted on {count} boards."
    elif lang == 'jp': final = f"✅ ユーザー <code>{target_id}</code> を {count} 個の板でBAN/ミュート解除しました。"
    else: final = f"✅ Пользователь <code>{target_id}</code> разбанен/размучен на {count} досках."
    await status_msg.edit_text(final, parse_mode="HTML")