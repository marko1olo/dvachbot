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
            usage = "使用法: <code>/shadowmute &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute &lt;user_id&gt; [время]</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
        total_seconds = min(total_seconds, 2592000)
        expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
        async with storage_lock:
            b_data = board_data[board_id]
            b_data['shadow_mutes'][target_id] = expires_dt
        await update_shadow_mute(target_id, board_id, expires_dt.timestamp())
        await log_global_event('bot', f"👻 SHADOWMUTE: Мод {message.from_user.id} скрыл {target_id} на /{board_id}/ до {expires_dt.strftime('%H:%M:%S')}")
        board_name = BOARD_CONFIG[board_id]['name']
        if lang == 'en':
            msg = f"👻 Shadowmuted user <code>{target_id}</code> for {time_str} on {board_name}."
        elif lang == 'jp':
            msg = f"👻 ユーザー <code>{target_id}</code> を {board_name} で {time_str} シャドウミュートしました。"
        else:
            msg = f"👻 Тихо замучен пользователь <code>{target_id}</code> на {time_str} на доске {board_name}."
        await message.answer(msg, parse_mode="HTML")
    except ValueError:
        err = "❌ Invalid format. Ex: <code>30m</code>, <code>2h</code>" if lang == 'en' else "❌ Неверный формат времени. Примеры: <code>30m</code>, <code>2h</code>, <code>1d</code>"
        await message.answer(err, parse_mode="HTML")
    await message.delete()