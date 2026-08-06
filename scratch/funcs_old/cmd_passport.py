@dp.message(Command("passport", "me", "profile", "stats_me"))
async def cmd_passport(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨ô╨╡╨╜╨╡╤Ç╨╕╤Ç╤â╨╡╤é '╨ƒ╨░╤ü╨┐╨╛╤Ç╤é ╨É╨╜╨╛╨╜╨░'. ╨ƒ╨╛╨╗╨╜╨░╤Å ╨╗╨╛╨║╨░╨╗╨╕╨╖╨░╤å╨╕╤Å.
    ╨É╨┤╨░╨┐╤é╨╕╤Ç╨╛╨▓╨░╨╜╨╛ ╨┐╨╛╨┤ ╨▒╨╡╨╖╨╛╨┐╨░╤ü╨╜╤â╤Ä ╤Ç╨░╨▒╨╛╤é╤â ╤ü ╨æ╨ö (db_lock).
    """
    if not board_id: return

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception: pass

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    user_id = message.from_user.id

    stats = await _get_passport_stats(user_id)
    if stats is None:
        return
    post_count, balance, is_verified = stats
    
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        import json
        active_items = json.loads(active_items_str)
    except:
        active_items = {}

    rank, role = _get_passport_rank_and_role(lang, post_count)
    ctx = PassportContext(
        user_id=user_id,
        lang=lang,
        board_id=board_id,
        post_count=post_count,
        balance=balance,
        is_verified=is_verified,
        rank=rank,
        role=role,
        active_items=active_items
    )
    passport_text = _generate_passport_text(ctx)

    try:
        await message.reply(passport_text, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError):
        try:
            await message.answer(passport_text, parse_mode="HTML")
        except (TelegramBadRequest, TelegramForbiddenError):
            import traceback; traceback.print_exc()
    try: await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError): pass