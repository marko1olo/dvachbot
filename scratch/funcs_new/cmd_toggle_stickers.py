@dp.message(Command("togglestickers"))
async def cmd_toggle_stickers(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай."))
        return
    b_data = board_data[board_id]
    if target_id not in b_data['user_settings']:
        b_data['user_settings'][target_id] = {'nsfw': False, 'hide': set(), 'shadow_gif': False, 'shadow_sticker': False}
    settings = b_data['user_settings'][target_id]
    new_val = not settings.get('shadow_sticker', False)
    settings['shadow_sticker'] = new_val
    spawn_task(update_user_settings_db(target_id, board_id, shadow_sticker=1 if new_val else 0))
    act = "ЗАПРЕТИЛ стикеры" if new_val else "РАЗРЕШИЛ стикеры"
    await log_global_event('bot', f"🃏 STICK_TOGGLE: Админ {message.from_user.id} {act} пользователю {target_id} на /{board_id}/")
    if lang == 'en':
        status = "BANNED 🚫 (Shadow)" if new_val else "ALLOWED ✅"
        msg = f"Stickers for {target_id}: {status}"
    elif lang == 'jp':
        status = "禁止 🚫 (シャドウ)" if new_val else "許可 ✅"
        msg = f"{target_id} のステッカー: {status}"
    else:
        status = "ЗАПРЕЩЕНЫ 🚫 (Теневой)" if new_val else "РАЗРЕШЕНЫ ✅"
        msg = f"Стикеры для {target_id} теперь: {status}"
    await message.answer(msg)
    try: await message.delete()
    except Exception: pass