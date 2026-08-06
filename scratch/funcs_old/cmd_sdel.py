@dp.message(Command("sdel", "swipe"))
async def cmd_sdel(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    "╨ó╨╡╨╜╨╡╨▓╨╛╨╡" ╤â╨┤╨░╨╗╨╡╨╜╨╕╨╡ ╨┐╨╛╤ü╤é╨░. ╨ú╨┤╨░╨╗╤Å╨╡╤é ╨▓╤ü╨╡ ╨║╨╛╨┐╨╕╨╕ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╤Å, ╨║╤Ç╨╛╨╝╨╡
    ╨║╨╛╨┐╨╕╨╕ ╤â ╨░╨▓╤é╨╛╤Ç╨░ ╨╛╤Ç╨╕╨│╨╕╨╜╨░╨╗╤î╨╜╨╛╨│╨╛ ╨┐╨╛╤ü╤é╨░. ╨ö╨╛╤ü╤é╤â╨┐╨╜╨╛ ╤é╨╛╨╗╤î╨║╨╛ ╨░╨┤╨╝╨╕╨╜╨░╨╝.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Reply to a message to use this: <code>/sdel</code>"
        elif lang == 'jp': msg = "Φ┐öΣ┐íπüùπüªΣ╜┐πüúπüªπüÅπüáπüòπüä: <code>/sdel</code>"
        else: msg = "ΓÜá∩╕Å ╨₧╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡, ╨║╨╛╤é╨╛╤Ç╨╛╨╡ ╤à╨╛╤é╨╕╤é╨╡ ╤é╨╕╤à╨╛ ╤â╨┤╨░╨╗╨╕╤é╤î: <code>/sdel</code>"
        await message.answer(msg, parse_mode="HTML")
        await message.delete()
        return
    post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
    if not post_info:
        err = "Post not found in DB." if lang == 'en' else "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╨╕╤ü╤à╨╛╨┤╨╜╤ï╨╣ ╨┐╨╛╤ü╤é ╨▓ ╨▒╨░╨╖╨╡ ╨┤╨░╨╜╨╜╤ï╤à."
        await message.answer(err)
        await message.delete()
        return
    post_num, author_id = post_info
    all_copies = await get_post_copies(post_num)
    if not all_copies:
        err = f"No copies found for #{post_num}." if lang == 'en' else f"╨¥╨╡ ╨╜╨░╨╣╨┤╨╡╨╜╨╛ ╨╛╤é╨┐╤Ç╨░╨▓╨╗╨╡╨╜╨╜╤ï╤à ╨║╨╛╨┐╨╕╨╣ ╨┤╨╗╤Å ╨┐╨╛╤ü╤é╨░ #{post_num}."
        await message.answer(err)
        await message.delete()
        return
    wait_txt = "≡ƒº╣ ╨í╨╜╨╛╤ê╤â ╨┐╨╛╤ü╤é╤ï ╤ì╤é╨╛╨│╨╛ ╤Ä╨╖╨╡╤Ç╨░..." if lang != 'en' else "≡ƒº╣ Wiping posts..."
    wait_msg = await message.answer(wait_txt)
    tasks = []
    for recipient_id, message_id in all_copies:
        if recipient_id != author_id:
            task = message.bot.delete_message(recipient_id, message_id)
            tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    deleted_count = sum(1 for res in results if res is True)
    await log_global_event('bot', f"≡ƒæ╗ SDEL: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╤ü╨║╤Ç╤ï╤é╨╜╨╛ ╤â╨┤╨░╨╗╨╕╨╗ ╨┐╨╛╤ü╤é #{post_num} ╨╜╨░ /{board_id}/ (╤â╨┤╨░╨╗╨╡╨╜╨╛ {deleted_count} ╨║╨╛╨┐╨╕╨╣)")
    if lang == 'en':
        report = f"≡ƒæ╗ Post #{post_num} shadow deleted.\nRemoved copies: {deleted_count} of {len(all_copies) - 1}."
    elif lang == 'jp':
        report = f"≡ƒæ╗ µèòτ¿┐ #{post_num} πéÆπé╖πâúπâëπéªσëèΘÖñπüùπü╛πüùπüƒπÇé\nσëèΘÖñµò░: {deleted_count} / {len(all_copies) - 1}."
    else:
        report = f"≡ƒæ╗ ╨ƒ╨╛╤ü╤é #{post_num} ╨▒╤ï╨╗ '╤é╨╡╨╜╨╡╨▓╤ï╨╝' ╨╛╨▒╤Ç╨░╨╖╨╛╨╝ ╤â╨┤╨░╨╗╨╡╨╜.\n╨ú╨┤╨░╨╗╨╡╨╜╨╛ ╨║╨╛╨┐╨╕╨╣: {deleted_count} ╨╕╨╖ {len(all_copies) - 1}."
    try: await wait_msg.delete()
    except Exception: pass
    await message.answer(report)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()