@dp.message(Command("nsfw"))
async def cmd_nsfw(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    current_status = b_data['user_settings'][user_id]['nsfw']
    if len(args) < 2:
        status_on = "ON"
        status_off = "OFF"
        if lang == 'en':
            msg = f"Current NSFW Spoiler status: <b>{status_on if current_status else status_off}</b>.\nUsage: <code>/nsfw on</code> or <code>/nsfw off</code>"
        elif lang == 'jp':
            msg = f"τÅ╛σ£¿πü«NSFWΦ¿¡σ«Ü: <b>{status_on if current_status else status_off}</b>\nΣ╜┐πüäµû╣: <code>/nsfw on</code> πü╛πüƒπü» <code>/nsfw off</code>"
        else:
            msg = f"╨ó╨╡╨║╤â╤ë╨╕╨╣ ╤ü╤é╨░╤é╤â╤ü NSFW ╤ü╨┐╨╛╨╣╨╗╨╡╤Ç╨░: <b>{status_on if current_status else status_off}</b>.\n╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/nsfw on</code> ╨╕╨╗╨╕ <code>/nsfw off</code>"
        await message.answer(msg, parse_mode="HTML")
        return
    action = args[1].lower()
    new_status = None
    if action in ['on', 'enable', '1', '╨▓╨║╨╗']:
        new_status = True
    elif action in ['off', 'disable', '0', '╨▓╤ï╨║╨╗']:
        new_status = False
    if new_status is not None:
        b_data['user_settings'][user_id]['nsfw'] = new_status
        spawn_task(update_user_settings_db(user_id, board_id, nsfw=1 if new_status else 0))
        if lang == 'en':
            reply = "Γ£à NSFW Spoilers enabled." if new_status else "Γÿæ∩╕Å NSFW Spoilers disabled."
        elif lang == 'jp':
            reply = "Γ£à NSFWπé╣πâ¥πéñπâ⌐πâ╝πéÆµ£ëσè╣πü½πüùπü╛πüùπüƒπÇé" if new_status else "Γÿæ∩╕Å NSFWπé╣πâ¥πéñπâ⌐πâ╝πéÆτäíσè╣πü½πüùπü╛πüùπüƒπÇé"
        else:
            reply = "Γ£à ╨í╨┐╨╛╨╣╨╗╨╡╤Ç╤ï ╨┤╨╗╤Å ╨║╨░╤Ç╤é╨╕╨╜╨╛╨║ ╨▓╨║╨╗╤Ä╤ç╨╡╨╜╤ï." if new_status else "Γÿæ∩╕Å ╨í╨┐╨╛╨╣╨╗╨╡╤Ç╤ï ╨┤╨╗╤Å ╨║╨░╤Ç╤é╨╕╨╜╨╛╨║ ╨▓╤ï╨║╨╗╤Ä╤ç╨╡╨╜╤ï."
        await message.answer(reply)
    else:
        err = "Error: Use 'on' or 'off'." if lang != 'ru' else "╨₧╤ê╨╕╨▒╨║╨░: ╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╣╤é╨╡ 'on' ╨╕╨╗╨╕ 'off'."
        await message.answer(err)