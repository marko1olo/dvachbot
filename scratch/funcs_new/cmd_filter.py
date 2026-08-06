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
            elif lang == 'jp': resp = "フィルターリストは空です。"
            else: resp = "Список стоп-слов для этой доски пуст."
        else:
            sorted_words = sorted(list(spam_words))
            word_list = "\n".join([f"• <code>{escape_html(word)}</code>" for word in sorted_words])
            board_name = BOARD_CONFIG[board_id]['name']
            if lang == 'en':
                resp = f"<b>Stop-words on {board_name}:</b>\n\n{word_list}"
            elif lang == 'jp':
                resp = f"<b>{board_name} のNGワード:</b>\n\n{word_list}"
            else:
                resp = f"<b>Текущие стоп-слова на доске {board_name}:</b>\n\n{word_list}"
        await message.answer(resp, parse_mode="HTML")
    elif subcommand == "add":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter add &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter add &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter add &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_add = parts[2].lower().strip()
            if await add_spam_word(board_id, word_to_add):
                b_data['spam_filter_words'].add(word_to_add)
                if lang == 'en': msg = f"✅ Added '<code>{escape_html(word_to_add)}</code>'."
                elif lang == 'jp': msg = f"✅ '<code>{escape_html(word_to_add)}</code>' を追加しました。"
                else: msg = f"✅ Слово '<code>{escape_html(word_to_add)}</code>' добавлено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("❌ DB Error.")
    elif subcommand == "remove":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter remove &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter remove &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter remove &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_remove = parts[2].lower().strip()
            if await remove_spam_word(board_id, word_to_remove):
                b_data['spam_filter_words'].discard(word_to_remove)
                if lang == 'en': msg = f"🗑 Removed '<code>{escape_html(word_to_remove)}</code>'."
                elif lang == 'jp': msg = f"🗑 '<code>{escape_html(word_to_remove)}</code>' を削除しました。"
                else: msg = f"🗑 Слово '<code>{escape_html(word_to_remove)}</code>' удалено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("ℹ️ Word not found.")
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
                "<b>スパムフィルタ管理:</b>\n"
                "<code>/filter list</code> - リスト表示\n"
                "<code>/filter add &lt;単語&gt;</code> - 追加\n"
                "<code>/filter remove &lt;単語&gt;</code> - 削除"
            )
        else:
            usage = (
                "<b>Управление спам-фильтром:</b>\n"
                "<code>/filter list</code> - Показать текущие стоп-слова\n"
                "<code>/filter add &lt;слово&gt;</code> - Добавить слово\n"
                "<code>/filter remove &lt;слово&gt;</code> - Удалить слово"
            )
        await message.answer(usage, parse_mode="HTML")
    try: await message.delete()
    except TelegramBadRequest: pass