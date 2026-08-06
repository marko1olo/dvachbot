@dp.message(Command("nuke_pins"))
async def cmd_nuke_pins_surgical(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨á╨░╨┤╨╕╨║╨░╨╗╤î╨╜╤ï╨╣ ╤ü╨▒╤Ç╨╛╤ü: unpin_all_chat_messages.
    ╨í╨╜╨╕╨╝╨░╨╡╤é ╨Æ╨₧╨₧╨æ╨⌐╨ò ╨Æ╨í╨ò ╨╖╨░╨║╤Ç╨╡╨┐╤ï ╨▓ ╨╗╨╕╤ç╨║╨╡ ╤ü ╨▒╨╛╤é╨╛╨╝ ╤â ╨░╨║╤é╨╕╨▓╨╜╤ï╤à ╤Ä╨╖╨╡╤Ç╨╛╨▓.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): 
        return
    if board_id in board_data:
        board_data[board_id]['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    users = await get_all_active_subscribers(board_id)
    if not users:
        await message.answer("≡ƒñ╖ΓÇìΓÖé∩╕Å ╨«╨╖╨╡╤Ç╨╛╨▓ ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜╨╛.")
        return
    status_msg = await message.answer(
        f"Γÿó∩╕Å <b>╨ù╨░╨┐╤â╤ü╨║ NUKE PINS (Total Wipe)</b>\n"
        f"╨ª╨╡╨╗╨╡╨╣: {len(users)}\n"
        f"╨£╨╡╤é╨╛╨┤: unpin_all_chat_messages (╨í╨╜╨╕╨╝╨░╨╡╤é ╨Æ╨í╨ü)\n"
        f"ΓÅ│ ╨ƒ╨╛╨╡╤à╨░╨╗╨╕...",
        parse_mode="HTML"
    )
    stats = {'ok': 0, 'error': 0, 'block': 0}
    time.time()
    BATCH_SIZE = 20
    for i, chat_id in enumerate(users):
        if i % 100 == 0 and i > 0:
            try:
                await status_msg.edit_text(f"Γÿó∩╕Å <b>╨ƒ╤Ç╨╛╨│╤Ç╨╡╤ü╤ü: {i} / {len(users)}</b>")
            except Exception: pass
        try:
            await message.bot.unpin_all_chat_messages(chat_id=chat_id)
            stats['ok'] += 1
        except TelegramForbiddenError:
            stats['block'] += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await message.bot.unpin_all_chat_messages(chat_id=chat_id)
                stats['ok'] += 1
            except Exception: stats['error'] += 1
        except Exception:
            stats['error'] += 1
        if i % BATCH_SIZE == 0:
            await asyncio.sleep(0.5)
    await status_msg.edit_text(
        f"Γ£à <b>TOTAL NUKE COMPLETE</b>\n"
        f"╨Æ╤ü╨╡╨│╨╛: {len(users)}\n"
        f"Γ£à ╨í╨╜╤Å╤é╨╛ ╤â: {stats['ok']}\n"
        f"≡ƒÜ½ ╨æ╨╗╨╛╨║╨╛╨▓: {stats['block']}\n"
        f"Γ¥î ╨₧╤ê╨╕╨▒╨╛╨║: {stats['error']}"
    )