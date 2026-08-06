@dp.message(Command("gshadowmute"))
async def cmd_gshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨Æ╤ï╨┤╨░╨╡╤é ╨ó╨ò╨¥╨ò╨Æ╨₧╨Ö ╨£╨ú╨ó ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Ä ╨í╨á╨É╨ù╨ú ╨¥╨É ╨Æ╨í╨ò╨Ñ ╨┤╨╛╤ü╨║╨░╤à.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
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
        except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en': usage = "Usage: <code>/gshadowmute &lt;id&gt; [time]</code> or reply."
        elif lang == 'jp': usage = "Σ╜┐τö¿µ│ò: <code>/gshadowmute &lt;ID&gt; [µÖéΘûô]</code> πü╛πüƒπü»Φ┐öΣ┐íπÇé"
        else: usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/gshadowmute &lt;id&gt; [╨▓╤Ç╨╡╨╝╤Å]</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é╨╛╨╝."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except Exception: pass
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} min"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} h"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} d"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} min"
        total_seconds = min(total_seconds, 2592000) 
    except (ValueError, AttributeError):
        await message.answer("Γ¥î Error format" if lang != 'ru' else "Γ¥î ╨¥╨╡╨▓╨╡╤Ç╨╜╤ï╨╣ ╤ä╨╛╤Ç╨╝╨░╤é ╨▓╤Ç╨╡╨╝╨╡╨╜╨╕")
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    if lang == 'en': msg = f"≡ƒæ╗ Applying GLOBAL SHADOW on <code>{target_id}</code> ({time_str})..."
    elif lang == 'jp': msg = f"≡ƒæ╗ <code>{target_id}</code> πü½πé░πâ¡πâ╝πâÉπâ½πé╖πâúπâëπéªπéÆΘü⌐τö¿Σ╕¡ ({time_str})..."
    else: msg = f"≡ƒæ╗ ╨¥╨░╨║╨╗╨░╨┤╤ï╨▓╨░╤Ä ╨ô╨¢╨₧╨æ╨É╨¢╨¼╨¥╨ú╨« ╤é╨╡╨╜╤î ╨╜╨░ <code>{target_id}</code> ({time_str})..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    mute_count = 0
    expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
    expires_ts = expires_dt.timestamp()
    for b_id in BOARDS:
        try:
            await update_shadow_mute(target_id, b_id, expires_ts)
            async with storage_lock:
                board_data[b_id]['shadow_mutes'][target_id] = expires_dt
            mute_count += 1
        except Exception: pass
    await log_global_event('bot', f"≡ƒæ╗ G-SHADOW: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╨▓╤ï╨┤╨░╨╗ ╨ô╨¢╨₧╨æ╨É╨¢╨¼╨¥╨ú╨« ╨ó╨ò╨¥╨¼ {target_id} ╨╜╨░ {mute_count} ╨┤╨╛╤ü╨║╨░╤à ╨┤╨╛ {expires_dt.strftime('%H:%M')}")
    if lang == 'en':
        final = f"≡ƒæ╗ <b>Global Shadowban Active.</b>\nTarget: <code>{target_id}</code>\nBoards: {mute_count}\nDuration: {time_str}\n\n<i>Ignored everywhere.</i>"
    elif lang == 'jp':
        final = f"≡ƒæ╗ <b>πé░πâ¡πâ╝πâÉπâ½πé╖πâúπâëπéªπâÉπâ│µ£ëσè╣πÇé</b>\nσ»╛Φ▒í: <code>{target_id}</code>\nµ¥┐µò░: {mute_count}\nµ£ƒΘûô: {time_str}\n\n<i>πü⌐πüôπüºπééτäíΦªûπüòπéîπü╛πüÖπÇé</i>"
    else:
        final = f"≡ƒæ╗ <b>╨ô╨╗╨╛╨▒╨░╨╗╤î╨╜╤ï╨╣ Shadowban ╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜.</b>\n╨ª╨╡╨╗╤î: <code>{target_id}</code>\n╨ö╨╛╤ü╨╛╨║: {mute_count}\n╨ö╨╗╨╕╤é╨╡╨╗╤î╨╜╨╛╤ü╤é╤î: {time_str}\n\n<i>╨ò╨│╨╛ ╨┐╨╛╤ü╤é╤ï ╨▒╤â╨┤╤â╤é ╨╝╨╛╨╗╤ç╨░ ╨╕╨│╨╜╨╛╤Ç╨╕╤Ç╨╛╨▓╨░╤é╤î╤ü╤Å ╨▓╨╡╨╖╨┤╨╡.</i>"
    await status_msg.edit_text(final, parse_mode="HTML")