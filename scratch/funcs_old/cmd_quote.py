@dp.message(Command("quote", "╤å╨╕╤é╨░╤é╨░", "random_post"))
async def cmd_quote(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    import html
    db = await get_pool()
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    async with db.execute(
        """SELECT post_num, content, author_id
           FROM Posts
           WHERE board_id = ? AND length(content) > 20 AND is_shadow = 0
           ORDER BY RANDOM() LIMIT 1""",
        (board_id,)
    ) as c:
        row = await c.fetchone()

    if not row:
        no_post = "No posts found." if lang == 'en' else "╨¥╨╡╤é ╨┐╨╛╤ü╤é╨╛╨▓ ╨╜╨░ ╨▒╨╛╤Ç╨┤╨╡."
        await message.answer(no_post)
        return

    post_num, content, author_id = row
    excerpt = content[:400].strip()
    if len(content) > 400:
        excerpt += "ΓÇª"

    anon_tag = f"Anon-{author_id % 10000:04d}" if lang == 'en' else f"╨É╨╜╨╛╨╜-{author_id % 10000:04d}"
    escaped = html.escape(excerpt)
    header = "≡ƒÄ▓ <b>Random post:</b>" if lang == 'en' else "≡ƒÄ▓ <b>╨í╨╗╤â╤ç╨░╨╣╨╜╤ï╨╣ ╨┐╨╛╤ü╤é:</b>"

    text = (
        f"{header}\n"
        f"<blockquote>{escaped}</blockquote>\n"
        f"<i>ΓÇö {anon_tag} | #{post_num} | /{board_id}/</i>"
    )
    try:
        await message.answer(text, parse_mode="HTML")
        await message.delete()
    except Exception:
        import traceback; traceback.print_exc()