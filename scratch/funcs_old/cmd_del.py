@dp.message(Command("del"))
async def cmd_del(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    admin_status = is_admin(user_id, board_id)
    is_janitor = False
    janitor_deletes_left = 0
    active_items = {}
    db = None
    if not admin_status:
        import json
        import time
        db = await get_pool()
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)
        ) as c:
            row = await c.fetchone()
            ai_str = row[0] if row and row[0] else "{}"
        try:
            active_items = json.loads(ai_str)
        except:
            active_items = {}
        janitor_until = active_items.get("janitor_until", 0)
        janitor_deletes_left = active_items.get("janitor_deletes_left", 0)
        if janitor_until > time.time() and janitor_deletes_left > 0:
            is_janitor = True
    if not admin_status and not is_janitor:
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply to a message: <code>/del</code>" if lang == 'en' else               ("Φ┐öΣ┐íπüùπüªΣ╜┐πüúπüªπüÅπüáπüòπüä: <code>/del</code>" if lang == 'jp' else                "ΓÜá∩╕Å ╨₧╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡, ╨║╨╛╤é╨╛╤Ç╨╛╨╡ ╤à╨╛╤é╨╕╤é╨╡ ╤â╨┤╨░╨╗╨╕╤é╤î: <code>/del</code>")
        await message.answer(msg, parse_mode="HTML")
        return
    post_num = None
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num is None:
        err = "Post not found." if lang == 'en' else               ("µèòτ¿┐πüîΦªïπüñπüïπéèπü╛πü¢πéôπÇé" if lang == 'jp' else                "╨¥╨╡ ╨╜╨░╤ê╤æ╨╗ ╤ì╤é╨╛╤é ╨┐╨╛╤ü╤é (╨▓╨╛╨╖╨╝╨╛╨╢╨╜╨╛, ╨╛╨╜ ╤ü╨╗╨╕╤ê╨║╨╛╨╝ ╤ü╤é╨░╤Ç╤ï╨╣ ╨╕╨╗╨╕ ╤â╨┤╨░╨╗╤æ╨╜).")
        await message.answer(err)
        return
    if is_janitor:
        import json
        if not db:
            db = await get_pool()
        janitor_deletes_left -= 1
        active_items["janitor_deletes_left"] = janitor_deletes_left
        async with db_lock:
            await db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                (json.dumps(active_items), user_id, board_id)
            )
            await db.commit()
    deleted_count = await delete_single_post(post_num, message.bot)
    role_str = "╨É╨┤╨╝╨╕╨╜" if admin_status else "╨ö╨▓╨╛╤Ç╨╜╨╕╨║"
    await log_global_event('bot', f"≡ƒùæ∩╕Å DEL: {role_str} {user_id} ╤â╨┤╨░╨╗╨╕╨╗ ╨┐╨╛╤ü╤é #{post_num} ╨╜╨░ /{board_id}/ (╨╕ {deleted_count} ╨║╨╛╨┐╨╕╨╣)")
    if lang == 'en':
        resp = f"≡ƒùæ Post #{post_num} deleted ({deleted_count} copies)."
        if is_janitor:
            resp += f" ≡ƒº╣ Janitor Ticket: {janitor_deletes_left} deletes remaining."
    elif lang == 'jp':
        resp = f"≡ƒùæ µèòτ¿┐ #{post_num} πü¿πé│πâöπâ╝ ({deleted_count}Σ╗╢) πéÆσëèΘÖñπüùπü╛πüùπüƒπÇé"
        if is_janitor:
            resp += f" ≡ƒº╣ µÄâΘÖñσôíπâüπé▒πââπâê: µ«ïπéè {janitor_deletes_left} σ¢₧πÇé"
    else:
        resp = f"≡ƒùæ ╨ƒ╨╛╤ü╤é Γäû{post_num} ╨╕ ╨║╨╛╨┐╨╕╨╕ ({deleted_count}) ╤â╨┤╨░╨╗╨╡╨╜╤ï."
        if is_janitor:
            resp += f" ≡ƒº╣ ╨ú╨┤╨░╨╗╨╡╨╜╨╛ ╨║╨░╨║ ╨ö╨▓╨╛╤Ç╨╜╨╕╨║ (╨┐╨╛ ╨æ╨╕╨╗╨╡╤é╤â). ╨₧╤ü╤é╨░╨╗╨╛╤ü╤î: {janitor_deletes_left} ╤â╨┤╨░╨╗╨╡╨╜╨╕╨╣."
    await message.answer(resp)
    try: await message.delete()
    except Exception: pass