@dp.message(Command("mute"))
async def cmd_mute(message: Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not is_adm:
        if board_id not in THREAD_BOARDS:
            return 
        b_data = board_data[board_id]
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main': return
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info or thread_info.get('op_id') != user_id: return
        now_ts = time.time()
        if now_ts - user_s.get('last_op_command_ts', 0) < OP_COMMAND_COOLDOWN:
            await message.delete(); return
        user_s['last_op_command_ts'] = now_ts
        if not message.reply_to_message: await message.delete(); return
        target_id = None
        target_id = await get_author_id_by_reply(message)
        if not target_id: await message.delete(); return
        thread_info.setdefault('local_mutes', {})[target_id] = time.time() + 600 # 10 ╨╝╨╕╨╜╤â╤é
        resp = random.choice(thread_messages[lang]['op_mute_success'])
        await message.answer(f"≡ƒöç {resp}", parse_mode=None); await message.delete()
        return
    args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if args: duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1: duration_str = args[1]
        except ValueError: pass
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/mute &lt;id&gt; [time]</code>"
        elif lang == 'jp':
            usage = "Σ╜┐τö¿µ│ò: <code>/mute &lt;ID&gt; [µÖéΘûô]</code>"
        else:
            usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/mute &lt;id&gt; [╨▓╤Ç╨╡╨╝╤Å]</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        multipliers = {'m': 60, 'h': 3600, 'd': 86400}
        unit = duration_str[-1]
        if unit in multipliers:
            val = int(duration_str[:-1])
            mult = multipliers[unit]
        else:
            val = int(duration_str)
            mult = 60
        mute_seconds = min(val * mult, 2592000) 
        if mute_seconds < 3600: 
            duration_text = f"{mute_seconds // 60} m" if lang=='en' else (f"{mute_seconds // 60}σêå" if lang=='jp' else f"{mute_seconds // 60} ╨╝╨╕╨╜")
        elif mute_seconds < 86400: 
            duration_text = f"{mute_seconds // 3600} h" if lang=='en' else (f"{mute_seconds // 3600}µÖéΘûô" if lang=='jp' else f"{mute_seconds // 3600} ╤ç╨░╤ü")
        else: 
            duration_text = f"{mute_seconds // 86400} d" if lang=='en' else (f"{mute_seconds // 86400}µùÑ" if lang=='jp' else f"{mute_seconds // 86400} ╨┤╨╜")
    except (ValueError, IndexError):
        await message.answer("Error format." if lang != 'ru' else "╨¥╨╡╨▓╨╡╤Ç╨╜╤ï╨╣ ╤ä╨╛╤Ç╨╝╨░╤é ╨▓╤Ç╨╡╨╝╨╡╨╜╨╕."); return
    deleted = await delete_user_posts(message.bot, target_id, 5, board_id)
    async with storage_lock:
        board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(seconds=mute_seconds)
    await apply_regular_mute(target_id, board_id, mute_seconds)
    await log_global_event('bot', f"≡ƒöç MUTE: ╨£╨╛╨┤ {message.from_user.id} ╨╖╨░╨╝╤â╤é╨╕╨╗ {target_id} ╨╜╨░ /{board_id}/ ╨╜╨░ {duration_text}")
    if lang == 'en':
        msg = f"≡ƒöç User <code>{target_id}</code> muted for {duration_text}. Deleted: {deleted}"
    elif lang == 'jp':
        msg = f"≡ƒöç πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πéÆ {duration_text} πâƒπâÑπâ╝πâêπüùπü╛πüùπüƒπÇéσëèΘÖñ: {deleted}"
    else:
        msg = f"≡ƒöç ╨«╨╖╨╡╤Ç <code>{target_id}</code> ╨╖╨░╨╝╤â╤ç╨╡╨╜ ╨╜╨░ {duration_text}. ╨ú╨┤╨░╨╗╨╡╨╜╨╛: {deleted}"
    await message.answer(msg, parse_mode="HTML")
    await send_moderation_notice(target_id, "mute", board_id, duration=duration_text, deleted_posts=deleted, stream=stream)
    try: await message.delete()
    except Exception: pass