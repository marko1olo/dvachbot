@dp.message(Command("search"))
async def cmd_search(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Выполняет поиск по всем постам.
    """
    if not board_id: return
    board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    query = (message.text or message.caption or "").split(maxsplit=1)
    if len(query) < 2 or not query[1].strip():
        if lang == 'en':
            txt = "Usage: <code>/search &lt;text&gt;</code>"
        elif lang == 'jp':
            txt = "使用法: <code>/search &lt;テキスト&gt;</code>"
        else:
            txt = "Использование: <code>/search &lt;текст для поиска&gt;</code>"
        await message.answer(txt, parse_mode="HTML")
        return
    search_query = query[1].strip()
    results = await search_posts(search_query, board_id=board_id, limit=10)
    if not results:
        if lang == 'en':
            txt = f"No results found for «{escape_html(search_query)}»."
        elif lang == 'jp':
            txt = f"「{escape_html(search_query)}」の検索結果はありません。"
        else:
            txt = f"По запросу «{escape_html(search_query)}» ничего не найдено."
        await message.answer(txt, parse_mode="HTML")
        return
    if lang == 'en':
        header = f"<b>Search results for «{escape_html(search_query)}»:</b>"
        post_prefix = "Post"
    elif lang == 'jp':
        header = f"<b>「{escape_html(search_query)}」の検索結果:</b>"
        post_prefix = "レス"
    else:
        header = f"<b>Результаты поиска по запросу «{escape_html(search_query)}»:</b>"
        post_prefix = "Пост"
    response_lines = [header]
    for post in results:
        post_num = post['id']
        text_snippet = escape_html(post['content'].get('text', '')[:100])
        response_lines.append(f"\n• <b>{post_prefix} #{post_num}</b>: <i>{text_snippet}...</i>")
    await message.answer("\n".join(response_lines), parse_mode="HTML")