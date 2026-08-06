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
            usage = "Σ╜┐τö¿µ│ò: <code>/togglereactions &lt;ID&gt;</code> πü╛πüƒπü»Φ┐öΣ┐íπÇé"
        else:
            usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/togglereactions &lt;user_id&gt;</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é╨╛╨╝ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    response_text = ""
    # reaction_banned_users ╨╢╨╕╨▓╤æ╤é ╨▓ board_data, ╨░ storage_lock ╨╛╤à╤Ç╨░╨╜╤Å╨╡╤é
    # messages_storage ΓÇö ╤é╨╛ ╨╡╤ü╤é╤î ╨╖╨┤╨╡╤ü╤î ╨╛╨╜ ╨▒╤ï╨╗ ╨╗╨╛╨╢╨╜╨╛╨╣ ╨╖╨░╨▓╨╕╤ü╨╕╨╝╨╛╤ü╤é╤î╤Ä ╨╕ ╨┐╤Ç╨╕ ╤ì╤é╨╛╨╝
    # ╤â╨┤╨╡╤Ç╨╢╨╕╨▓╨░╨╗╤ü╤Å ╤ç╨╡╤Ç╨╡╨╖ ╨º╨ò╨ó╨½╨á╨ò ╨╛╨▒╤Ç╨░╤ë╨╡╨╜╨╕╤Å ╨║ ╨æ╨ö (add/remove_reaction_ban ╨╕ ╨┤╨▓╨░
    # log_global_event). ╨ƒ╨╛╨┤ ╨╗╨╛╨║╨╛╨╝ ╨╛╤ü╤é╨░╨▓╨╗╨╡╨╜╨╛ ╤é╨╛╨╗╤î╨║╨╛ ╤ü╨░╨╝╨╛ ╨┐╨╡╤Ç╨╡╨║╨╗╤Ä╤ç╨╡╨╜╨╕╨╡
    # ╨╝╨╜╨╛╨╢╨╡╤ü╤é╨▓╨░: ╨╛╨╜╨╛ ╨┤╨╛╨╗╨╢╨╜╨╛ ╨▒╤ï╤é╤î ╨░╤é╨╛╨╝╨░╤Ç╨╜╤ï╨╝, ╤ç╤é╨╛╨▒╤ï ╨┤╨▓╨░ ╨░╨┤╨╝╨╕╨╜╨░ ╨╛╨┤╨╜╨╛╨▓╤Ç╨╡╨╝╨╡╨╜╨╜╨╛ ╨╜╨╡
    # ╨┐╨╛╨╗╤â╤ç╨╕╨╗╨╕ ╨┐╤Ç╨╛╤é╨╕╨▓╨╛╨┐╨╛╨╗╨╛╨╢╨╜╤ï╨╡ ╤Ç╨╡╨╖╤â╨╗╤î╤é╨░╤é╤ï. ╨ù╨░╨┐╨╕╤ü╤î ╨▓ ╨æ╨ö ΓÇö ╤â╨╢╨╡ ╨▒╨╡╨╖ ╨╗╨╛╨║╨░.
    async with storage_lock:
        banned_set = board_data[board_id].setdefault('reaction_banned_users', set())
        now_allowed = target_id in banned_set
        if now_allowed:
            banned_set.remove(target_id)
        else:
            banned_set.add(target_id)
    if now_allowed:
        await remove_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"≡ƒÄ¡ REAC_OK: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╨á╨É╨ù╨á╨ò╨¿╨ÿ╨¢ ╤Ç╨╡╨░╨║╤å╨╕╨╕ ╨┤╨╗╤Å {target_id} ╨╜╨░ /{board_id}/")
        if lang == 'en':
            response_text = f"Γ£à User <code>{target_id}</code> can now use reactions again."
        elif lang == 'jp':
            response_text = f"Γ£à πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πü«πâ¬πéóπé»πé╖πâºπâ│τªüµ¡óπéÆΦºúΘÖñπüùπü╛πüùπüƒπÇé"
        else:
            response_text = f"Γ£à ╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î <code>{target_id}</code> ╤é╨╡╨┐╨╡╤Ç╤î ╤ü╨╜╨╛╨▓╨░ ╨╝╨╛╨╢╨╡╤é ╤ü╤é╨░╨▓╨╕╤é╤î ╤Ç╨╡╨░╨║╤å╨╕╨╕."
    else:
        await add_reaction_ban(target_id, board_id)
        await log_global_event('bot', f"≡ƒÄ¡ REAC_BAN: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╨ù╨É╨ƒ╨á╨ò╨ó╨ÿ╨¢ ╤Ç╨╡╨░╨║╤å╨╕╨╕ ╨┤╨╗╤Å {target_id} ╨╜╨░ /{board_id}/")
        if lang == 'en':
            response_text = f"≡ƒÜ½ User <code>{target_id}</code> is now banned from using reactions."
        elif lang == 'jp':
            response_text = f"≡ƒÜ½ πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πü«πâ¬πéóπé»πé╖πâºπâ│πéÆτªüµ¡óπüùπü╛πüùπüƒπÇé"
        else:
            response_text = f"≡ƒÜ½ ╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Ä <code>{target_id}</code> ╤é╨╡╨┐╨╡╤Ç╤î ╨╖╨░╨┐╤Ç╨╡╤ë╨╡╨╜╨╛ ╤ü╤é╨░╨▓╨╕╤é╤î ╤Ç╨╡╨░╨║╤å╨╕╨╕."
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()