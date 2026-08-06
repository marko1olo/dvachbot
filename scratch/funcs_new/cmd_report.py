@dp.message(Command("report", "mods", "admin", "moderator"))
async def cmd_report(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not message.reply_to_message:
        msg = "⚠️ Ответьте на подозрительное сообщение командой <code>/report</code>, чтобы позвать модераторов."
        if lang == 'en': msg = "⚠️ Reply to a suspicious message with <code>/report</code> to alert moderators."
        elif lang == 'jp': msg = "⚠️ 違反報告するメッセージに返信して <code>/report</code> を送信してください。"
        await message.answer(msg, parse_mode="HTML")
        return

    reported_msg = message.reply_to_message
    
    # Send confirmation to user
    confirm_msg = "✅ Репорт отправлен модераторам. Спасибо!"
    if lang == 'en': confirm_msg = "✅ Report sent to moderators. Thank you!"
    elif lang == 'jp': confirm_msg = "✅ モデレーターに報告しました。ありがとうございます！"
    
    sent_confirm = await message.answer(confirm_msg)
    try: spawn_task(delete_message_after_delay(sent_confirm, 10))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    # Get author id of reported message
    author_id = None
    author_id = await get_author_id_by_reply(message)
    if not author_id:
        author_id = "0"
    
    chat_id = message.chat.id
    msg_id = reported_msg.message_id
    
    # Build inline keyboard for admins
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить пост", callback_data=f"rep:del:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Бан 1ч", callback_data=f"rep:ban1:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Бан 24ч", callback_data=f"rep:ban24:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="Игнор", callback_data=f"rep:ign:{author_id}:{chat_id}:{msg_id}")
    builder.adjust(1, 2, 1)

    admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
    report_text = f"🚨 <b>Новый РЕПОРТ в /{board_id}/</b>\n"
    report_text += f"От кого: <code>{message.from_user.id}</code>\n"
    report_text += f"На кого: <code>{author_id}</code>\n"
    report_text += f"Текст: <i>{escape_html(reported_msg.text or reported_msg.caption or '<медиа>')}</i>"
    
    for admin_id in admins:
        try:
            await message.bot.send_message(
                admin_id,
                report_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception:
            import traceback; traceback.print_exc()