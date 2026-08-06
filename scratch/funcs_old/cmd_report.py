@dp.message(Command("report", "mods", "admin", "moderator"))
async def cmd_report(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not message.reply_to_message:
        msg = "ΓÜá∩╕Å ╨₧╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╨┐╨╛╨┤╨╛╨╖╤Ç╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ ╨║╨╛╨╝╨░╨╜╨┤╨╛╨╣ <code>/report</code>, ╤ç╤é╨╛╨▒╤ï ╨┐╨╛╨╖╨▓╨░╤é╤î ╨╝╨╛╨┤╨╡╤Ç╨░╤é╨╛╤Ç╨╛╨▓."
        if lang == 'en': msg = "ΓÜá∩╕Å Reply to a suspicious message with <code>/report</code> to alert moderators."
        elif lang == 'jp': msg = "ΓÜá∩╕Å ΘüòσÅìσá▒σæèπüÖπéïπâíπââπé╗πâ╝πé╕πü½Φ┐öΣ┐íπüùπüª <code>/report</code> πéÆΘÇüΣ┐íπüùπüªπüÅπüáπüòπüäπÇé"
        await message.answer(msg, parse_mode="HTML")
        return

    reported_msg = message.reply_to_message
    
    # Send confirmation to user
    confirm_msg = "Γ£à ╨á╨╡╨┐╨╛╤Ç╤é ╨╛╤é╨┐╤Ç╨░╨▓╨╗╨╡╨╜ ╨╝╨╛╨┤╨╡╤Ç╨░╤é╨╛╤Ç╨░╨╝. ╨í╨┐╨░╤ü╨╕╨▒╨╛!"
    if lang == 'en': confirm_msg = "Γ£à Report sent to moderators. Thank you!"
    elif lang == 'jp': confirm_msg = "Γ£à πâóπâçπâ¼πâ╝πé┐πâ╝πü½σá▒σæèπüùπü╛πüùπüƒπÇéπüéπéèπüîπü¿πüåπüöπüûπüäπü╛πüÖ∩╝ü"
    
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
    builder.button(text="╨ú╨┤╨░╨╗╨╕╤é╤î ╨┐╨╛╤ü╤é", callback_data=f"rep:del:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="╨æ╨░╨╜ 1╤ç", callback_data=f"rep:ban1:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="╨æ╨░╨╜ 24╤ç", callback_data=f"rep:ban24:{author_id}:{chat_id}:{msg_id}")
    builder.button(text="╨ÿ╨│╨╜╨╛╤Ç", callback_data=f"rep:ign:{author_id}:{chat_id}:{msg_id}")
    builder.adjust(1, 2, 1)

    admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
    report_text = f"≡ƒÜ¿ <b>╨¥╨╛╨▓╤ï╨╣ ╨á╨ò╨ƒ╨₧╨á╨ó ╨▓ /{board_id}/</b>\n"
    report_text += f"╨₧╤é ╨║╨╛╨│╨╛: <code>{message.from_user.id}</code>\n"
    report_text += f"╨¥╨░ ╨║╨╛╨│╨╛: <code>{author_id}</code>\n"
    report_text += f"╨ó╨╡╨║╤ü╤é: <i>{escape_html(reported_msg.text or reported_msg.caption or '<╨╝╨╡╨┤╨╕╨░>')}</i>"
    
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