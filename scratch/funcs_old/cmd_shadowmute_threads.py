@dp.message(Command("shadowmute_threads"))
async def cmd_shadowmute_threads(message: Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        await message.delete()
        return
    args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "10m" 
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if args: duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1: duration_str = args[1]
        except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute_threads &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "Σ╜┐τö¿µ│ò: <code>/shadowmute_threads &lt;user_id&gt; [µÖéΘûô]</code> πü╛πüƒπü»Φ┐öΣ┐íπÇé"
        else:
            usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/shadowmute_threads &lt;user_id&gt; [╨▓╤Ç╨╡╨╝╤Å]</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} ╨╝╨╕╨╜"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} ╤ç╨░╤ü"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} ╨┤╨╜╨╡╨╣"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} ╨╝╨╕╨╜"
    except (ValueError, AttributeError):
        await message.answer("Γ¥î Error format. Ex: 10m, 2h, 1d" if lang == 'en' else "Γ¥î ╨¥╨╡╨▓╨╡╤Ç╨╜╤ï╨╣ ╤ä╨╛╤Ç╨╝╨░╤é. ╨ƒ╤Ç╨╕╨╝╨╡╤Ç╤ï: 10m, 2h, 1d")
        await message.delete()
        return
    expires_ts = time.time() + total_seconds
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})
    for thread_info in threads_data.values():
        thread_info.setdefault('local_shadow_mutes', {})[target_id] = expires_ts
    phrases = thread_messages.get(lang, {}).get('shadowmute_threads_success', ["Shadowmuted in threads."])
    response_text = random.choice(phrases).format(
        user_id=target_id, 
        duration=str(int(total_seconds / 60))
    )
    await message.answer(response_text)
    await message.delete()