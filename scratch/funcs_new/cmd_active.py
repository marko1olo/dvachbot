@dp.message(Command("active"))
async def cmd_active(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    INFO_CMD_COOLDOWN = 30 
    # storage_lock убран как ложная зависимость: кулдаун лежит в board_data, а
    # не в messages_storage. Взаимное исключение даёт info_cmd_lock, внутри
    # которого нет ни одного await — проверка и запись времени атомарны.
    async with info_cmd_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < INFO_CMD_COOLDOWN
        if not on_cooldown:
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    if on_cooldown:
        try: await message.delete()
        except Exception: pass
        return
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    timestamps_for_analysis = []
    async with storage_lock:
        for post_data in reversed(messages_storage.values()):
            post_time = post_data.get("timestamp")
            if not post_time or post_time < day_ago: break
            timestamps_for_analysis.append(post_time)
    posts_last_24h = len(timestamps_for_analysis)
    activity_lines = []
    for b_id in BOARDS:
        if b_id == 'test': continue
        activity = await get_board_activity_last_hours(b_id, hours=2)
        board_name = escape_html(BOARD_CONFIG[b_id]['name'])
        if lang == 'en':
            line = f"<b>{board_name}</b> - {activity:.1f} posts/hr"
        elif lang == 'jp':
            line = f"<b>{board_name}</b> - {activity:.1f} レス/時"
        else:
            line = f"<b>{board_name}</b> - {activity:.1f} п/ч"
        activity_lines.append(line)
    if lang == 'en':
        header_text = "📊 <b>Boards Activity (last 2h):</b>"
        total_text = f"\n\n📅 Total posts in last 24h: {posts_last_24h}"
        pm_sent = "✅ Stats sent to PM."
        unlock = "❌ Unblock the bot to receive stats."
    elif lang == 'jp':
        header_text = "📊 <b>板の勢い (過去2時間):</b>"
        total_text = f"\n\n📅 24時間の総レス数: {posts_last_24h}"
        pm_sent = "✅ 統計をDMで送信しました。"
        unlock = "❌ DMを受け取るにはボットのブロックを解除してください。"
    else:
        header_text = "📊 <b>Активность досок (за 2ч):</b>"
        total_text = f"\n\n📅 Всего постов за 24 часа: {posts_last_24h}"
        pm_sent = "✅ Статистика отправлена вам в личные сообщения."
        unlock = "❌ Разблокируйте бота, чтобы получить статистику в ЛС."
    full_activity_text = f"{header_text}\n\n" + "\n".join(activity_lines) + total_text
    try:
        await message.bot.send_message(user_id, full_activity_text, parse_mode="HTML")
        temp_msg = await message.answer(pm_sent)
        spawn_task(delete_message_after_delay(temp_msg, 5))
    except TelegramForbiddenError:
        await message.answer(unlock)
    except Exception: pass
    try: await message.delete()
    except Exception: pass