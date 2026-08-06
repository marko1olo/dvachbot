@dp.message(Command("gshadowmute"))
async def cmd_gshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Выдает ТЕНЕВОЙ МУТ пользователю СРАЗУ НА ВСЕХ досках.
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
        elif lang == 'jp': usage = "使用法: <code>/gshadowmute &lt;ID&gt; [時間]</code> または返信。"
        else: usage = "Использование: <code>/gshadowmute &lt;id&gt; [время]</code> или ответом."
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
        await message.answer("❌ Error format" if lang != 'ru' else "❌ Неверный формат времени")
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    if lang == 'en': msg = f"👻 Applying GLOBAL SHADOW on <code>{target_id}</code> ({time_str})..."
    elif lang == 'jp': msg = f"👻 <code>{target_id}</code> にグローバルシャドウを適用中 ({time_str})..."
    else: msg = f"👻 Накладываю ГЛОБАЛЬНУЮ тень на <code>{target_id}</code> ({time_str})..."
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
    await log_global_event('bot', f"👻 G-SHADOW: Админ {message.from_user.id} выдал ГЛОБАЛЬНУЮ ТЕНЬ {target_id} на {mute_count} досках до {expires_dt.strftime('%H:%M')}")
    if lang == 'en':
        final = f"👻 <b>Global Shadowban Active.</b>\nTarget: <code>{target_id}</code>\nBoards: {mute_count}\nDuration: {time_str}\n\n<i>Ignored everywhere.</i>"
    elif lang == 'jp':
        final = f"👻 <b>グローバルシャドウバン有効。</b>\n対象: <code>{target_id}</code>\n板数: {mute_count}\n期間: {time_str}\n\n<i>どこでも無視されます。</i>"
    else:
        final = f"👻 <b>Глобальный Shadowban активирован.</b>\nЦель: <code>{target_id}</code>\nДосок: {mute_count}\nДлительность: {time_str}\n\n<i>Его посты будут молча игнорироваться везде.</i>"
    await status_msg.edit_text(final, parse_mode="HTML")