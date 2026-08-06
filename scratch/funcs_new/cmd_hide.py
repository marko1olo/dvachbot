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
                "<b>NGワード管理:</b>\n"
                "/hide list - リストを表示\n"
                "/hide add <単語> - 追加\n"
                "/hide remove <単語> - 削除"
            )
        else:
            help_text = (
                "<b>Управление скрытием слов:</b>\n"
                "/hide list - Список скрытых слов\n"
                "/hide add <слово> - Добавить слово\n"
                "/hide remove <слово> - Убрать слово"
            )
        await message.answer(help_text, parse_mode="HTML")
        return
    action = args[1].lower()
    if action == 'list':
        if not user_hide_set:
            if lang == 'en': txt = "Your hidden words list is empty."
            elif lang == 'jp': txt = "NGワードリストは空です。"
            else: txt = "Ваш список скрытых слов пуст."
            await message.answer(txt)
        else:
            words_str = ", ".join([f"<code>{escape_html(w)}</code>" for w in user_hide_set])
            if lang == 'en': header = "🚫 <b>Hidden words:</b>"
            elif lang == 'jp': header = "🚫 <b>NGワード:</b>"
            else: header = "🚫 <b>Скрытые слова:</b>"
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
            elif lang == 'jp': err = "単語が短すぎます。"
            else: err = "Слово слишком короткое."
            await message.answer(err)
            return
        if len(user_hide_set) >= 60:
            if lang == 'en': msg = "🚫 Limit exceeded! Max 60 hidden words allowed."
            elif lang == 'jp': msg = "🚫 制限を超えました！最大60語までです。"
            else: msg = "🚫 Лимит превышен! Максимум 60 скрытых слов."
            await message.answer(msg, parse_mode="HTML")
            return
        user_hide_set.add(word)
        spawn_task(update_user_settings_db(user_id, board_id, hidden_words=list(user_hide_set)))
        if lang == 'en': msg = f"✅ Word '<b>{escape_html(word)}</b>' added to hidden list."
        elif lang == 'jp': msg = f"✅ '<b>{escape_html(word)}</b>' をリストに追加しました。"
        else: msg = f"✅ Слово '<b>{escape_html(word)}</b>' добавлено в скрытые."
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
            if lang == 'en': msg = f"🗑 Word '<b>{escape_html(word)}</b>' removed from list."
            elif lang == 'jp': msg = f"🗑 '<b>{escape_html(word)}</b>' を削除しました。"
            else: msg = f"🗑 Слово '<b>{escape_html(word)}</b>' удалено из списка."
            await message.answer(msg, parse_mode="HTML")
        else:
            if lang == 'en': msg = "Word not found in your list."
            elif lang == 'jp': msg = "リストに見つかりません。"
            else: msg = "Слово не найдено в вашем списке."
            await message.answer(msg)