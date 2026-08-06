@dp.message(Command("togglemedia"))
async def cmd_toggle_media(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply." if lang == 'en' else ("IDπü╛πüƒπü»Φ┐öΣ┐íπüîσ┐àΦªüπüºπüÖπÇé" if lang == 'jp' else "╨¥╤â╨╢╨╡╨╜ ID ╨╕╨╗╨╕ ╤Ç╨╡╨┐╨╗╨░╨╣."))
        return
    b_data = board_data[board_id]
    if target_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[target_id] = {
            'nsfw': False, 'hide': set(), 
            'shadow_gif': False, 'shadow_sticker': False, 'shadow_media': False
        }
    settings = b_data['user_settings'][target_id]
    new_val = not settings.get('shadow_media', False)
    settings['shadow_media'] = new_val
    spawn_task(update_user_settings_db(target_id, board_id, shadow_media=1 if new_val else 0))
    act = "╨ù╨É╨ƒ╨á╨ò╨ó╨ÿ╨¢ ╨▓╤ü╨╡ ╨╝╨╡╨┤╨╕╨░" if new_val else "╨á╨É╨ù╨á╨ò╨¿╨ÿ╨¢ ╨╝╨╡╨┤╨╕╨░"
    await log_global_event('bot', f"≡ƒöç MEDIA_TOGGLE: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} {act} ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Ä {target_id} ╨╜╨░ /{board_id}/ (Text-only mode)")
    if lang == 'en':
        status = "BANNED ≡ƒÜ½ (Shadow)" if new_val else "ALLOWED Γ£à"
        msg = f"All Media for {target_id}: {status} (Text only mode)"
    elif lang == 'jp':
        status = "τªüµ¡ó ≡ƒÜ½ (πé╖πâúπâëπéª)" if new_val else "Φ¿▒σÅ» Γ£à"
        msg = f"{target_id} πü«σà¿πâíπâçπéúπéó: {status} (πâåπé¡πé╣πâêπü«πü┐)"
    else:
        status = "╨ù╨É╨ƒ╨á╨ò╨⌐╨ò╨¥╨½ ≡ƒÜ½ (╨ó╨╡╨╜╨╡╨▓╨╛╨╣)" if new_val else "╨á╨É╨ù╨á╨ò╨¿╨ò╨¥╨½ Γ£à"
        msg = f"╨¢╤Ä╨▒╤ï╨╡ ╨╝╨╡╨┤╨╕╨░ ╨┤╨╗╤Å {target_id} ╤é╨╡╨┐╨╡╤Ç╤î: {status} (╨á╨░╨╖╤Ç╨╡╤ê╨╡╨╜ ╤é╨╛╨╗╤î╨║╨╛ ╤é╨╡╨║╤ü╤é)"
    await message.answer(msg)
    try: await message.delete()
    except Exception: pass