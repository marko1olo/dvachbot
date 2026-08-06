@dp.message(Command("shadowmute"))
async def cmd_shadowmute(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if args:
            duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1:
                duration_str = args[1]
        except ValueError:
            import traceback; traceback.print_exc()
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "Σ╜┐τö¿µ│ò: <code>/shadowmute &lt;user_id&gt; [µÖéΘûô]</code> πü╛πüƒπü»Φ┐öΣ┐íπÇé"
        else:
            usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/shadowmute &lt;user_id&gt; [╨▓╤Ç╨╡╨╝╤Å]</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é╨╛╨╝ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} ╨╝╨╕╨╜"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} ╤ç╨░╤ü"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} ╨┤╨╜╨╡╨╣"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} ╨╝╨╕╨╜"
        total_seconds = min(total_seconds, 2592000)
        expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
        async with storage_lock:
            b_data = board_data[board_id]
            b_data['shadow_mutes'][target_id] = expires_dt
        await update_shadow_mute(target_id, board_id, expires_dt.timestamp())
        await log_global_event('bot', f"≡ƒæ╗ SHADOWMUTE: ╨£╨╛╨┤ {message.from_user.id} ╤ü╨║╤Ç╤ï╨╗ {target_id} ╨╜╨░ /{board_id}/ ╨┤╨╛ {expires_dt.strftime('%H:%M:%S')}")
        board_name = BOARD_CONFIG[board_id]['name']
        if lang == 'en':
            msg = f"≡ƒæ╗ Shadowmuted user <code>{target_id}</code> for {time_str} on {board_name}."
        elif lang == 'jp':
            msg = f"≡ƒæ╗ πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πéÆ {board_name} πüº {time_str} πé╖πâúπâëπéªπâƒπâÑπâ╝πâêπüùπü╛πüùπüƒπÇé"
        else:
            msg = f"≡ƒæ╗ ╨ó╨╕╤à╨╛ ╨╖╨░╨╝╤â╤ç╨╡╨╜ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î <code>{target_id}</code> ╨╜╨░ {time_str} ╨╜╨░ ╨┤╨╛╤ü╨║╨╡ {board_name}."
        await message.answer(msg, parse_mode="HTML")
    except ValueError:
        err = "Γ¥î Invalid format. Ex: <code>30m</code>, <code>2h</code>" if lang == 'en' else "Γ¥î ╨¥╨╡╨▓╨╡╤Ç╨╜╤ï╨╣ ╤ä╨╛╤Ç╨╝╨░╤é ╨▓╤Ç╨╡╨╝╨╡╨╜╨╕. ╨ƒ╤Ç╨╕╨╝╨╡╤Ç╤ï: <code>30m</code>, <code>2h</code>, <code>1d</code>"
        await message.answer(err, parse_mode="HTML")
    await message.delete()