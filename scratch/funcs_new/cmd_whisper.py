@dp.message(Command("whisper"))
async def cmd_whisper(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: await message.delete()
    except Exception: pass
    if not message.reply_to_message:
        await message.answer("❌ Используй /whisper в ответ на сообщение, автору которого хочешь прошептать.")
        return
    parts = (message.text or message.caption or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Использование: <code>/whisper &lt;текст&gt;</code>", parse_mode="HTML")
        return
    text = parts[1]
    
    target_id = await get_author_id_by_reply(message)
    if not target_id:
        await message.answer("❌ Не удалось найти автора оригинального сообщения.")
        return
        
    if target_id == message.from_user.id:
        await message.answer("❌ Зачем шептать самому себе?")
        return

    # Send to target
    delivered = False
    try:
        await message.bot.send_message(
            target_id, 
            f"🤫 <b>Тебе анонимно шепчут в /{board_id}/:</b>\n<i>{escape_html(text)}</i>", 
            parse_mode="HTML"
        )
        delivered = True
    except Exception as e:
        runtime_logger.error(f"Whisper send failed: {e}", exc_info=True)
        await message.answer("❌ Не удалось доставить шёпот (пользователь не запустил бота или заблокировал его).")
        
    if delivered:
        # Send to admin
        admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
        sender_nick = generate_anon_name(message.from_user.id)
        target_nick = generate_anon_name(target_id)
        for admin_id in admins:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"🕵️‍♂️ <b>(ЭТО СЕКРЕТ) Шёпот в /{board_id}/:</b>\nОт: <code>{sender_nick}</code>\nКому: <code>{target_nick}</code>\nТекст: <i>{escape_html(text)}</i>",
                    parse_mode="HTML"
                )
            except Exception: pass