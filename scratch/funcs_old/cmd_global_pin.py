@dp.message(Command("pin"))
async def cmd_global_pin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨ù╨░╨║╤Ç╨╡╨┐╨╗╤Å╨╡╤é ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡. ╨í╨╛╤à╤Ç╨░╨╜╤Å╨╡╤é ID ╨▓ ╨┐╨░╨╝╤Å╤é╤î ╨╕ ╨æ╨ö, ╤ç╤é╨╛╨▒╤ï ╨╖╨░╨║╤Ç╨╡╨┐ ╨┐╨╡╤Ç╨╡╨╢╨╕╨╗ ╨┐╨╡╤Ç╨╡╨╖╨░╨│╤Ç╤â╨╖╨║╤â.
    """
    if not board_id: return
    if not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply to a message: <code>/del</code>" if lang == 'en' else ("Φ┐öΣ┐íπüùπüªΣ╜┐πüúπüªπüÅπüáπüòπüä: <code>/del</code>" if lang == 'jp' else "ΓÜá∩╕Å ╨₧╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡, ╨║╨╛╤é╨╛╤Ç╨╛╨╡ ╤à╨╛╤é╨╕╤é╨╡ ╤â╨┤╨░╨╗╨╕╤é╤î: <code>/del</code>")
        await message.answer(msg, parse_mode="HTML")
        return
    post_num = None
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if post_info: post_num = post_info[0]
    if not post_num:
        err = "Post not found in DB." if lang == 'en' else ("πâçπâ╝πé┐πâÖπâ╝πé╣πü½µèòτ¿┐πüîΦªïπüñπüïπéèπü╛πü¢πéôπÇé" if lang == 'jp' else "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╨┐╨╛╤ü╤é ╨▓ ╨▒╨░╨╖╨╡.")
        await message.answer(err)
        return
    b_data = board_data[board_id]
    b_data['active_pin'] = post_num
    await update_board_settings(board_id, {'active_pin': post_num})
    copies = await get_post_copies(post_num)
    if lang == 'en':
        status_txt = f"≡ƒôî <b>New Pin:</b> Post #{post_num}\nSaved to DB Γ£à\nPinning for {len(copies)} users..."
    elif lang == 'jp':
        status_txt = f"≡ƒôî <b>µû░πüùπüäπâöπâ│τòÖπéü:</b> µèòτ¿┐ #{post_num}\nDBπü½Σ┐¥σ¡ÿ Γ£à\n{len(copies)} Σ║║πü«πâªπâ╝πé╢πâ╝πü½πâöπâ│τòÖπéüΣ╕¡..."
    else:
        status_txt = f"≡ƒôî <b>╨¥╨╛╨▓╤ï╨╣ ╨╖╨░╨║╤Ç╨╡╨┐:</b> ╨ƒ╨╛╤ü╤é #{post_num}\n╨í╨╛╤à╤Ç╨░╨╜╨╡╨╜╨╛ ╨▓ ╨┐╨░╨╝╤Å╤é╨╕ ╨╕ ╨æ╨ö: Γ£à\n╨ù╨░╨║╤Ç╨╡╨┐╨╗╤Å╤Ä ╤â {len(copies)} ╤é╨╡╨║╤â╤ë╨╕╤à ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╨╡╨╣..."
    status_msg = await message.answer(status_txt, parse_mode="HTML")
    if not copies:
        return
    count_success = 0
    async def pin_one(uid, mid):
        try:
            await message.bot.pin_chat_message(chat_id=uid, message_id=mid, disable_notification=True)
            return True
        except Exception: return False
    await log_global_event('bot', f"≡ƒôî PIN: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╨╖╨░╨║╤Ç╨╡╨┐╨╕╨╗ ╨┐╨╛╤ü╤é #{post_num} ╨╜╨░ /{board_id}/")
    CHUNK_SIZE = 30
    for i in range(0, len(copies), CHUNK_SIZE):
        chunk = copies[i:i + CHUNK_SIZE]
        results = await asyncio.gather(*[pin_one(uid, mid) for uid, mid in chunk])
        count_success += sum(results)
        await asyncio.sleep(1.1)
    if lang == 'en':
        final = f"Γ£à Post #{post_num} pinned (Success: {count_success})."
    elif lang == 'jp':
        final = f"Γ£à µèòτ¿┐ #{post_num} πéÆπâöπâ│τòÖπéüπüùπü╛πüùπüƒ (µêÉσèƒ: {count_success})πÇé"
    else:
        final = f"Γ£à ╨ƒ╨╛╤ü╤é #{post_num} ╨╖╨░╨║╤Ç╨╡╨┐╨╗╨╡╨╜ (╨ú╤ü╨┐╨╡╤ê╨╜╨╛: {count_success}).\n╨¥╨╛╨▓╤ï╨╡ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╨╕ ╤é╨╛╨╢╨╡ ╤â╨▓╨╕╨┤╤Å╤é ╨╡╨│╨╛."
    await status_msg.edit_text(final)