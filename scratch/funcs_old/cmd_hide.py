@dp.message(Command("hide"))
async def cmd_hide(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = (message.text or message.caption or "").split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    user_hide_set = b_data['user_settings'][user_id]['hide']
    if len(args) < 2:
        if lang == 'en':
            help_text = (
                "<b>Hide Words Management:</b>\n"
                "/hide list - Show hidden words\n"
                "/hide add &lt;word&gt; - Add word to filter\n"
                "/hide remove &lt;word&gt; - Remove word"
            )
        elif lang == 'jp':
            help_text = (
                "<b>NGπâ»πâ╝πâëτ«íτÉå:</b>\n"
                "/hide list - πâ¬πé╣πâêπéÆΦí¿τñ║\n"
                "/hide add <σìÿΦ¬₧> - Φ┐╜σèá\n"
                "/hide remove <σìÿΦ¬₧> - σëèΘÖñ"
            )
        else:
            help_text = (
                "<b>╨ú╨┐╤Ç╨░╨▓╨╗╨╡╨╜╨╕╨╡ ╤ü╨║╤Ç╤ï╤é╨╕╨╡╨╝ ╤ü╨╗╨╛╨▓:</b>\n"
                "/hide list - ╨í╨┐╨╕╤ü╨╛╨║ ╤ü╨║╤Ç╤ï╤é╤ï╤à ╤ü╨╗╨╛╨▓\n"
                "/hide add <╤ü╨╗╨╛╨▓╨╛> - ╨ö╨╛╨▒╨░╨▓╨╕╤é╤î ╤ü╨╗╨╛╨▓╨╛\n"
                "/hide remove <╤ü╨╗╨╛╨▓╨╛> - ╨ú╨▒╤Ç╨░╤é╤î ╤ü╨╗╨╛╨▓╨╛"
            )
        await message.answer(help_text, parse_mode="HTML")
        return
    action = args[1].lower()
    if action == 'list':
        if not user_hide_set:
            if lang == 'en': txt = "Your hidden words list is empty."
            elif lang == 'jp': txt = "NGπâ»πâ╝πâëπâ¬πé╣πâêπü»τ⌐║πüºπüÖπÇé"
            else: txt = "╨Æ╨░╤ê ╤ü╨┐╨╕╤ü╨╛╨║ ╤ü╨║╤Ç╤ï╤é╤ï╤à ╤ü╨╗╨╛╨▓ ╨┐╤â╤ü╤é."
            await message.answer(txt)
        else:
            words_str = ", ".join([f"<code>{escape_html(w)}</code>" for w in user_hide_set])
            if lang == 'en': header = "≡ƒÜ½ <b>Hidden words:</b>"
            elif lang == 'jp': header = "≡ƒÜ½ <b>NGπâ»πâ╝πâë:</b>"
            else: header = "≡ƒÜ½ <b>╨í╨║╤Ç╤ï╤é╤ï╨╡ ╤ü╨╗╨╛╨▓╨░:</b>"
            await message.answer(f"{header}\n{words_str}", parse_mode="HTML")
    elif action == 'add':
        word_part = (message.text or message.caption or "").split(maxsplit=2)
        if len(word_part) < 3:
             err = "Usage: /hide add &lt;word&gt;"
             await message.answer(err)
             return
        word = word_part[2].lower().strip()
        if len(word) < 2:
            if lang == 'en': err = "Word too short."
            elif lang == 'jp': err = "σìÿΦ¬₧πüîτƒ¡πüÖπüÄπü╛πüÖπÇé"
            else: err = "╨í╨╗╨╛╨▓╨╛ ╤ü╨╗╨╕╤ê╨║╨╛╨╝ ╨║╨╛╤Ç╨╛╤é╨║╨╛╨╡."
            await message.answer(err)
            return
        if len(user_hide_set) >= 60:
            if lang == 'en': msg = "≡ƒÜ½ Limit exceeded! Max 60 hidden words allowed."
            elif lang == 'jp': msg = "≡ƒÜ½ σê╢ΘÖÉπéÆΦ╢àπüêπü╛πüùπüƒ∩╝üµ£Çσñº60Φ¬₧πü╛πüºπüºπüÖπÇé"
            else: msg = "≡ƒÜ½ ╨¢╨╕╨╝╨╕╤é ╨┐╤Ç╨╡╨▓╤ï╤ê╨╡╨╜! ╨£╨░╨║╤ü╨╕╨╝╤â╨╝ 60 ╤ü╨║╤Ç╤ï╤é╤ï╤à ╤ü╨╗╨╛╨▓."
            await message.answer(msg, parse_mode="HTML")
            return
        user_hide_set.add(word)
        spawn_task(update_user_settings_db(user_id, board_id, hidden_words=list(user_hide_set)))
        if lang == 'en': msg = f"Γ£à Word '<b>{escape_html(word)}</b>' added to hidden list."
        elif lang == 'jp': msg = f"Γ£à '<b>{escape_html(word)}</b>' πéÆπâ¬πé╣πâêπü½Φ┐╜σèáπüùπü╛πüùπüƒπÇé"
        else: msg = f"Γ£à ╨í╨╗╨╛╨▓╨╛ '<b>{escape_html(word)}</b>' ╨┤╨╛╨▒╨░╨▓╨╗╨╡╨╜╨╛ ╨▓ ╤ü╨║╤Ç╤ï╤é╤ï╨╡."
        await message.answer(msg, parse_mode="HTML")
    elif action == 'remove' or action == 'del':
        word_part = (message.text or message.caption or "").split(maxsplit=2)
        if len(word_part) < 3:
             await message.answer("Usage: /hide remove &lt;word&gt;")
             return
        word = word_part[2].lower().strip()
        if word in user_hide_set:
            user_hide_set.remove(word)
            spawn_task(update_user_settings_db(user_id, board_id, hidden_words=list(user_hide_set)))
            if lang == 'en': msg = f"≡ƒùæ Word '<b>{escape_html(word)}</b>' removed from list."
            elif lang == 'jp': msg = f"≡ƒùæ '<b>{escape_html(word)}</b>' πéÆσëèΘÖñπüùπü╛πüùπüƒπÇé"
            else: msg = f"≡ƒùæ ╨í╨╗╨╛╨▓╨╛ '<b>{escape_html(word)}</b>' ╤â╨┤╨░╨╗╨╡╨╜╨╛ ╨╕╨╖ ╤ü╨┐╨╕╤ü╨║╨░."
            await message.answer(msg, parse_mode="HTML")
        else:
            if lang == 'en': msg = "Word not found in your list."
            elif lang == 'jp': msg = "πâ¬πé╣πâêπü½Φªïπüñπüïπéèπü╛πü¢πéôπÇé"
            else: msg = "╨í╨╗╨╛╨▓╨╛ ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜╨╛ ╨▓ ╨▓╨░╤ê╨╡╨╝ ╤ü╨┐╨╕╤ü╨║╨╡."
            await message.answer(msg)