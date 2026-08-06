@dp.message(Command("lie"))
async def cmd_lie_media(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply: /lie &lt;id&gt;" if lang == 'en' else "Need ID or reply: /lie &lt;id&gt;")
        return
    b_data = board_data[board_id]
    if target_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[target_id] = {
            'nsfw': False, 'hide': set(),
            'shadow_gif': False, 'shadow_sticker': False, 'shadow_media': False,
            'lie_media': False,
        }
    settings = b_data['user_settings'][target_id]
    settings.setdefault('nsfw', False)
    settings.setdefault('hide', set())
    new_val = not settings.get('lie_media', False)
    settings['lie_media'] = new_val
    spawn_task(update_user_settings_db(target_id, board_id, lie_media=1 if new_val else 0))
    status = "ENABLED" if new_val else "DISABLED"
    await log_global_event('bot', f"LIE_MEDIA_TOGGLE: admin {message.from_user.id} {status} archive media substitution for {target_id} on /{board_id}/")
    await message.answer(f"Lie media for <code>{target_id}</code>: {status}", parse_mode="HTML")
    try: await message.delete()
    except Exception: pass