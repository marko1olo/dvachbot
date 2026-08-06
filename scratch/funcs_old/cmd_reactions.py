@dp.message(Command("reactions"))
async def cmd_reactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

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
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    post_num = None
    reactions_data = {}
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num and post_num in messages_storage:
        post_data = messages_storage[post_num]
        reactions_data = post_data.get('reactions', {}).get('users', {})
    if not post_num:
        if lang == 'en': err = "Post not found in DB."
        elif lang == 'jp': err = "πâçπâ╝πé┐πâÖπâ╝πé╣πü½µèòτ¿┐πüîΦªïπüñπüïπéèπü╛πü¢πéôπÇé"
        else: err = "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╤ì╤é╨╛╤é ╨┐╨╛╤ü╤é ╨▓ ╨▒╨░╨╖╨╡."
        try: await message.answer(err); await message.delete()
        except TelegramBadRequest: pass
        return
    if not reactions_data:
        if lang == 'en': msg = f"Post #{post_num} has no reactions yet."
        elif lang == 'jp': msg = f"µèòτ¿┐ #{post_num} πü½πü»πü╛πüáπâ¬πéóπé»πé╖πâºπâ│πüîπüéπéèπü╛πü¢πéôπÇé"
        else: msg = f"╨¥╨░ ╨┐╨╛╤ü╤é #{post_num} ╨╡╤ë╨╡ ╨╜╨╡╤é ╤Ç╨╡╨░╨║╤å╨╕╨╣."
        try: await message.answer(msg); await message.delete()
        except TelegramBadRequest: pass
        return
    if lang == 'en': header = f"<b>Reactions to post #{post_num}:</b>\n\n"
    elif lang == 'jp': header = f"<b>µèòτ¿┐ #{post_num} πü╕πü«πâ¬πéóπé»πé╖πâºπâ│:</b>\n\n"
    else: header = f"<b>╨á╨╡╨░╨║╤å╨╕╨╕ ╨╜╨░ ╨┐╨╛╤ü╤é #{post_num}:</b>\n\n"
    lines = []
    sorted_reactors = sorted(reactions_data.items())
    MAX_USERS_TO_SHOW = 50
    for user_id, emoji_list in sorted_reactors[:MAX_USERS_TO_SHOW]:
        emojis_str = "".join(emoji_list)
        lines.append(f"ΓÇó ID <code>{user_id}</code>: {emojis_str}")
    response_text = header + "\n".join(lines)
    if len(sorted_reactors) > MAX_USERS_TO_SHOW:
        diff = len(sorted_reactors) - MAX_USERS_TO_SHOW
        if lang == 'en': footer = f"\n<i>...and {diff} more users.</i>"
        elif lang == 'jp': footer = f"\n<i>...Σ╗û {diff} πâªπâ╝πé╢πâ╝πÇé</i>"
        else: footer = f"\n<i>...╨╕ ╨╡╤ë╨╡ {diff} ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╨╡╨╣.</i>"
        response_text += footer
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()