@dp.message(Command("filter"))
async def cmd_filter(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    parts = (message.text or message.caption or "").split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"
    if subcommand == "list":
        spam_words = b_data.get('spam_filter_words', set())
        if not spam_words:
            if lang == 'en': resp = "Filter list is empty."
            elif lang == 'jp': resp = "πâòπéúπâ½πé┐πâ╝πâ¬πé╣πâêπü»τ⌐║πüºπüÖπÇé"
            else: resp = "╨í╨┐╨╕╤ü╨╛╨║ ╤ü╤é╨╛╨┐-╤ü╨╗╨╛╨▓ ╨┤╨╗╤Å ╤ì╤é╨╛╨╣ ╨┤╨╛╤ü╨║╨╕ ╨┐╤â╤ü╤é."
        else:
            sorted_words = sorted(list(spam_words))
            word_list = "\n".join([f"ΓÇó <code>{escape_html(word)}</code>" for word in sorted_words])
            board_name = BOARD_CONFIG[board_id]['name']
            if lang == 'en':
                resp = f"<b>Stop-words on {board_name}:</b>\n\n{word_list}"
            elif lang == 'jp':
                resp = f"<b>{board_name} πü«NGπâ»πâ╝πâë:</b>\n\n{word_list}"
            else:
                resp = f"<b>╨ó╨╡╨║╤â╤ë╨╕╨╡ ╤ü╤é╨╛╨┐-╤ü╨╗╨╛╨▓╨░ ╨╜╨░ ╨┤╨╛╤ü╨║╨╡ {board_name}:</b>\n\n{word_list}"
        await message.answer(resp, parse_mode="HTML")
    elif subcommand == "add":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter add &lt;word&gt;</code>"
            elif lang == 'jp': txt = "Σ╜┐τö¿µ│ò: <code>/filter add &lt;σìÿΦ¬₧&gt;</code>"
            else: txt = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/filter add &lt;╤ü╨╗╨╛╨▓╨╛&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_add = parts[2].lower().strip()
            if await add_spam_word(board_id, word_to_add):
                b_data['spam_filter_words'].add(word_to_add)
                if lang == 'en': msg = f"Γ£à Added '<code>{escape_html(word_to_add)}</code>'."
                elif lang == 'jp': msg = f"Γ£à '<code>{escape_html(word_to_add)}</code>' πéÆΦ┐╜σèáπüùπü╛πüùπüƒπÇé"
                else: msg = f"Γ£à ╨í╨╗╨╛╨▓╨╛ '<code>{escape_html(word_to_add)}</code>' ╨┤╨╛╨▒╨░╨▓╨╗╨╡╨╜╨╛."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("Γ¥î DB Error.")
    elif subcommand == "remove":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter remove &lt;word&gt;</code>"
            elif lang == 'jp': txt = "Σ╜┐τö¿µ│ò: <code>/filter remove &lt;σìÿΦ¬₧&gt;</code>"
            else: txt = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/filter remove &lt;╤ü╨╗╨╛╨▓╨╛&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_remove = parts[2].lower().strip()
            if await remove_spam_word(board_id, word_to_remove):
                b_data['spam_filter_words'].discard(word_to_remove)
                if lang == 'en': msg = f"≡ƒùæ Removed '<code>{escape_html(word_to_remove)}</code>'."
                elif lang == 'jp': msg = f"≡ƒùæ '<code>{escape_html(word_to_remove)}</code>' πéÆσëèΘÖñπüùπü╛πüùπüƒπÇé"
                else: msg = f"≡ƒùæ ╨í╨╗╨╛╨▓╨╛ '<code>{escape_html(word_to_remove)}</code>' ╤â╨┤╨░╨╗╨╡╨╜╨╛."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("Γä╣∩╕Å Word not found.")
    else:
        if lang == 'en':
            usage = (
                "<b>Spam Filter Management:</b>\n"
                "<code>/filter list</code> - Show list\n"
                "<code>/filter add &lt;word&gt;</code> - Add\n"
                "<code>/filter remove &lt;word&gt;</code> - Remove"
            )
        elif lang == 'jp':
            usage = (
                "<b>πé╣πâæπâáπâòπéúπâ½πé┐τ«íτÉå:</b>\n"
                "<code>/filter list</code> - πâ¬πé╣πâêΦí¿τñ║\n"
                "<code>/filter add &lt;σìÿΦ¬₧&gt;</code> - Φ┐╜σèá\n"
                "<code>/filter remove &lt;σìÿΦ¬₧&gt;</code> - σëèΘÖñ"
            )
        else:
            usage = (
                "<b>╨ú╨┐╤Ç╨░╨▓╨╗╨╡╨╜╨╕╨╡ ╤ü╨┐╨░╨╝-╤ä╨╕╨╗╤î╤é╤Ç╨╛╨╝:</b>\n"
                "<code>/filter list</code> - ╨ƒ╨╛╨║╨░╨╖╨░╤é╤î ╤é╨╡╨║╤â╤ë╨╕╨╡ ╤ü╤é╨╛╨┐-╤ü╨╗╨╛╨▓╨░\n"
                "<code>/filter add &lt;╤ü╨╗╨╛╨▓╨╛&gt;</code> - ╨ö╨╛╨▒╨░╨▓╨╕╤é╤î ╤ü╨╗╨╛╨▓╨╛\n"
                "<code>/filter remove &lt;╤ü╨╗╨╛╨▓╨╛&gt;</code> - ╨ú╨┤╨░╨╗╨╕╤é╤î ╤ü╨╗╨╛╨▓╨╛"
            )
        await message.answer(usage, parse_mode="HTML")
    try: await message.delete()
    except TelegramBadRequest: pass