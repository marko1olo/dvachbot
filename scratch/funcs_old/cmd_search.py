@dp.message(Command("search"))
async def cmd_search(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨Æ╤ï╨┐╨╛╨╗╨╜╤Å╨╡╤é ╨┐╨╛╨╕╤ü╨║ ╨┐╨╛ ╨▓╤ü╨╡╨╝ ╨┐╨╛╤ü╤é╨░╨╝.
    """
    if not board_id: return
    board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    query = (message.text or message.caption or "").split(maxsplit=1)
    if len(query) < 2 or not query[1].strip():
        if lang == 'en':
            txt = "Usage: <code>/search &lt;text&gt;</code>"
        elif lang == 'jp':
            txt = "Σ╜┐τö¿µ│ò: <code>/search &lt;πâåπé¡πé╣πâê&gt;</code>"
        else:
            txt = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/search &lt;╤é╨╡╨║╤ü╤é ╨┤╨╗╤Å ╨┐╨╛╨╕╤ü╨║╨░&gt;</code>"
        await message.answer(txt, parse_mode="HTML")
        return
    search_query = query[1].strip()
    results = await search_posts(search_query, board_id=board_id, limit=10)
    if not results:
        if lang == 'en':
            txt = f"No results found for ┬½{escape_html(search_query)}┬╗."
        elif lang == 'jp':
            txt = f"πÇî{escape_html(search_query)}πÇìπü«µñ£τ┤óτ╡Éµ₧£πü»πüéπéèπü╛πü¢πéôπÇé"
        else:
            txt = f"╨ƒ╨╛ ╨╖╨░╨┐╤Ç╨╛╤ü╤â ┬½{escape_html(search_query)}┬╗ ╨╜╨╕╤ç╨╡╨│╨╛ ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜╨╛."
        await message.answer(txt, parse_mode="HTML")
        return
    if lang == 'en':
        header = f"<b>Search results for ┬½{escape_html(search_query)}┬╗:</b>"
        post_prefix = "Post"
    elif lang == 'jp':
        header = f"<b>πÇî{escape_html(search_query)}πÇìπü«µñ£τ┤óτ╡Éµ₧£:</b>"
        post_prefix = "πâ¼πé╣"
    else:
        header = f"<b>╨á╨╡╨╖╤â╨╗╤î╤é╨░╤é╤ï ╨┐╨╛╨╕╤ü╨║╨░ ╨┐╨╛ ╨╖╨░╨┐╤Ç╨╛╤ü╤â ┬½{escape_html(search_query)}┬╗:</b>"
        post_prefix = "╨ƒ╨╛╤ü╤é"
    response_lines = [header]
    for post in results:
        post_num = post['id']
        text_snippet = escape_html(post['content'].get('text', '')[:100])
        response_lines.append(f"\nΓÇó <b>{post_prefix} #{post_num}</b>: <i>{text_snippet}...</i>")
    await message.answer("\n".join(response_lines), parse_mode="HTML")