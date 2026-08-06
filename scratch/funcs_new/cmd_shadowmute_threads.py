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
            usage = "使用法: <code>/shadowmute_threads &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute_threads &lt;user_id&gt; [время]</code> или ответ на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
    except (ValueError, AttributeError):
        await message.answer("❌ Error format. Ex: 10m, 2h, 1d" if lang == 'en' else "❌ Неверный формат. Примеры: 10m, 2h, 1d")
        await message.delete()
        return
    expires_ts = time.time() + total_seconds
    b_data = board_data[board_id]
    threads_data = get_threads_data(board_id)
    for thread_info in threads_data.values():
        thread_info.setdefault('local_shadow_mutes', {})[target_id] = expires_ts
    phrases = thread_messages.get(lang, {}).get('shadowmute_threads_success', ["Shadowmuted in threads."])
    response_text = random.choice(phrases).format(
        user_id=target_id, 
        duration=str(int(total_seconds / 60))
    )
    await message.answer(response_text)
    await message.delete()