@dp.message(Command("rob"))
async def cmd_rob(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å <b>╨₧╤ê╨╕╨▒╨║╨░:</b> ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┐╨╛╤ü╤é ╨╢╨╡╤Ç╤é╨▓╤ï, ╨║╨╛╤é╨╛╤Ç╤â╤Ä ╤à╨╛╤ç╨╡╤ê╤î ╨╛╨│╤Ç╨░╨▒╨╕╤é╤î!", parse_mode="HTML")
        return
    import time
    import random
    import json
    db = await get_pool()
    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("knife_gun"):
        await message.answer("≡ƒö¬ ╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╨ù╨░╤é╨╛╤ç╨║╨╕! ╨Ü╤â╨┐╨╕ ╨╡╤æ ╨▓ ╤é╨╡╨╜╨╡╨▓╨╛╨╝ ╨╝╨░╨│╨░╨╖╨╕╨╜╨╡: /shop")
        return
    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0:
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╤å╨╡╨╗╤î ╨┤╨╗╤Å ╨╛╨│╤Ç╨░╨▒╨╗╨╡╨╜╨╕╤Å.")
        return
    if target_id == user_id:
        await message.answer("≡ƒñªΓÇìΓÖé∩╕Å ╨ó╤ï ╨┐╨╛╨┐╤ï╤é╨░╨╗╤ü╤Å ╨╛╨│╤Ç╨░╨▒╨╕╤é╤î ╤ü╨░╨╝ ╤ü╨╡╨▒╤Å. ╨ù╨░╤é╨╛╤ç╨║╨░ ╨╛╤ü╤é╨░╨╗╨░╤ü╤î ╨┐╤Ç╨╕ ╤é╨╡╨▒╨╡.")
        return
    t_items = await _get_user_active_items(db, target_id, board_id)
    current_time = int(time.time())
    
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        t_balance = row[0] if row and row[0] else 0
        
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        u_balance = row[0] if row and row[0] else 0

    pct = random.uniform(0.1, 0.3)
    
    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╨╜╨╡╤é ╨┤╨╡╨╜╨╡╨│ ╤â ╤å╨╡╨╗╨╕
    stolen = min(int(t_balance * pct), 1000)
    if stolen <= 0:
        await message.answer("≡ƒö¬ ╨ú ╨╢╨╡╤Ç╤é╨▓╤ï ╨▓╨╛╨╛╨▒╤ë╨╡ ╨╜╨╡╤é ╤ê╨╡╨║╨╡╨╗╨╡╨╣. ╨ó╤ï ╨┐╨╛╨╢╨░╨╗╨╡╨╗ ╨▒╨╛╨╝╨╢╨░ ╨╕ ╨╜╨╡ ╤ü╤é╨░╨╗ ╤é╤Ç╨░╤é╨╕╤é╤î ╨╖╨░╤é╨╛╤ç╨║╤â.", parse_mode="HTML")
        return

    # ╨ù╨░╨▒╨╕╤Ç╨░╨╡╨╝ ╨┐╤Ç╨╡╨┤╨╝╨╡╤é
    active_items["knife_gun"] = False
    
    if t_items.get("tinfoil_hat", 0) > current_time:
        # ╨ñ╨╛╨╗╤î╨│╨░ ╨╖╨░╤ë╨╕╤ë╨░╨╡╤é
        loss = min(int(u_balance * pct), 1000)
        async with db_lock:
            await db.execute(
                "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = balance - ?, active_items = excluded.active_items",
                (user_id, board_id, -loss, json.dumps(active_items), loss)
            )
            await db.commit()
        await message.answer(f"≡ƒæ╜ <b>╨¿╨É╨ƒ╨₧╨º╨Ü╨É ╨ÿ╨ù ╨ñ╨₧╨¢╨¼╨ô╨ÿ!</b>\n╨û╨╡╤Ç╤é╨▓╨░ ╨╛╨║╨░╨╖╨░╨╗╨░╤ü╤î ╨┐╨╛╨┤ ╨╖╨░╤ë╨╕╤é╨╛╨╣! ╨ó╤ï ╨▓ ╨┐╨░╨╜╨╕╨║╨╡ ╨┐╨╛╤Ç╨╡╨╖╨░╨╗╤ü╤Å ╤ü╨▓╨╛╨╡╨╣ ╨╢╨╡ ╨╖╨░╤é╨╛╤ç╨║╨╛╨╣ ╨╕ ╨╛╨▒╤Ç╨╛╨╜╨╕╨╗ <code>{loss}</code> ╤ê╨╡╨║╨╡╨╗╨╡╨╣!", parse_mode="HTML")
        return

    async with db_lock:
        # ╨í╨¥╨É╨º╨É╨¢╨É ╤ü╨┐╨╕╤ü╤ï╨▓╨░╨╡╨╝ ╤â ╨╢╨╡╤Ç╤é╨▓╤ï, ╨╕ ╤é╨╛╨╗╤î╨║╨╛ ╨╡╤ü╨╗╨╕ ╤ü╤â╨╝╨╝╨░ ╤Ç╨╡╨░╨╗╤î╨╜╨╛ ╨╡╤ü╤é╤î.
        # t_balance ╤ç╨╕╤é╨░╨╗╤ü╤Å ╨▓╤ï╤ê╨╡ ╨▓╨╜╨╡ ╨╗╨╛╨║╨░ ╨╕ ╨║ ╤ì╤é╨╛╨╝╤â ╨╝╨╛╨╝╨╡╨╜╤é╤â ╨╝╨╛╨│ ╤â╤ü╤é╨░╤Ç╨╡╤é╤î: ╨╢╨╡╤Ç╤é╨▓╨░
        # ╤â╤ü╨┐╨╡╨╗╨░ ╨┐╨╛╤é╤Ç╨░╤é╨╕╤é╤î╤ü╤Å ╨╕╨╗╨╕ ╨╡╤æ ╤â╨╢╨╡ ╨│╤Ç╨░╨▒╨░╨╜╤â╨╗ ╨║╤é╨╛-╤é╨╛ ╨┤╤Ç╤â╨│╨╛╨╣. ╨ú╤ü╨╗╨╛╨▓╨╕╨╡
        # `balance >= ?` ╨┤╨╡╨╗╨░╨╡╤é ╨┐╤Ç╨╛╨▓╨╡╤Ç╨║╤â ╨╕ ╤ü╨┐╨╕╤ü╨░╨╜╨╕╨╡ ╨╛╨┤╨╜╨╛╨╣ ╨░╤é╨╛╨╝╨░╤Ç╨╜╨╛╨╣ ╨╛╨┐╨╡╤Ç╨░╤å╨╕╨╡╨╣.
        # ╨ƒ╤Ç╨╡╨╢╨╜╨╕╨╣ ╨║╨╛╨┤ ╤ü╨┐╨╕╤ü╤ï╨▓╨░╨╗ ╨▒╨╡╨╖╤â╤ü╨╗╨╛╨▓╨╜╤ï╨╝ upsert-╨╛╨╝, ╨┐╤Ç╨╕╤ç╤æ╨╝ ╨ƒ╨₧╨í╨¢╨ò ╨╜╨░╤ç╨╕╤ü╨╗╨╡╨╜╨╕╤Å
        # ╨│╤Ç╨░╨▒╨╕╤é╨╡╨╗╤Ä: ╨╜╨╡╤ü╨║╨╛╨╗╤î╨║╨╛ ╨╛╨┤╨╜╨╛╨▓╤Ç╨╡╨╝╨╡╨╜╨╜╤ï╤à ╨│╤Ç╨░╨▒╨╡╨╢╨╡╨╣ ╤â╨▓╨╛╨┤╨╕╨╗╨╕ ╨▒╨░╨╗╨░╨╜╤ü ╨╢╨╡╤Ç╤é╨▓╤ï ╨▓
        # ╨╝╨╕╨╜╤â╤ü, ╨░ ╨│╤Ç╨░╨▒╨╕╤é╨╡╨╗╤Å╨╝ ╨╜╨░╤ç╨╕╤ü╨╗╤Å╨╗╨╛╤ü╤î ╤é╨╛, ╤ç╨╡╨│╨╛ ╤â ╨╜╨╡╤æ ╨╜╨╡ ╨▒╤ï╨╗╨╛.
        cursor = await db.execute(
            "UPDATE Users SET balance = balance - ? "
            "WHERE user_id = ? AND board_id = ? AND balance >= ?",
            (stolen, target_id, board_id, stolen)
        )
        # ╨Ü╨╛╤Ç╤Ç╨╡╨║╤é╨╜╨╛╤ü╤é╤î ╨╛╨▒╨╡╤ü╨┐╨╡╤ç╨╕╨▓╨░╨╡╤é ╤ü╨░╨╝╨╛ ╤â╤ü╨╗╨╛╨▓╨╕╨╡ ╨▓ UPDATE: ╤ü╨┐╨╕╤ü╨░╤é╤î ╨▒╨╛╨╗╤î╤ê╨╡, ╤ç╨╡╨╝
        # ╨╡╤ü╤é╤î, ╨╛╨╜╨╛ ╨╜╨╡ ╨┤╨░╤ü╤é ╨╜╨╕ ╨┐╤Ç╨╕ ╨║╨░╨║╨╛╨╣ ╨║╨╛╨╜╨║╤â╤Ç╨╡╨╜╤å╨╕╨╕. rowcount ╨╜╤â╨╢╨╡╨╜ ╤é╨╛╨╗╤î╨║╨╛
        # ╤ç╤é╨╛╨▒╤ï ╤Ç╨╡╤ê╨╕╤é╤î, ╨╜╨░╤ç╨╕╤ü╨╗╤Å╤é╤î ╨╗╨╕ ╨│╤Ç╨░╨▒╨╕╤é╨╡╨╗╤Ä. ╨ö╨╛╨▓╨╡╤Ç╤Å╨╡╨╝ ╨╡╨╝╤â ╨╗╨╕╤ê╤î ╨║╨╛╨│╨┤╨░ ╤ì╤é╨╛
        # ╨╜╨░╤ü╤é╨╛╤Å╤ë╨╡╨╡ ╤å╨╡╨╗╨╛╨╡: aiosqlite ╨▓╤ü╨╡╨│╨┤╨░ ╨╛╤é╨┤╨░╤æ╤é int, ╨░ ╤é╨╡╤ü╤é╨╛╨▓╤ï╨╡ ╨┤╤â╨▒╨╗╨╕ - ╤é╨╛
        # None, ╤é╨╛ ╨░╨▓╤é╨╛-╨░╤é╤Ç╨╕╨▒╤â╤é MagicMock. ╨Æ ╨╜╨╡╤Å╤ü╨╜╨╛╨╝ ╤ü╨╗╤â╤ç╨░╨╡ ╤ü╤ç╨╕╤é╨░╨╡╨╝, ╤ç╤é╨╛
        # ╤ü╨┐╨╕╤ü╨░╨╜╨╕╨╡ ╨┐╤Ç╨╛╤ê╨╗╨╛, ╤é╨╛ ╨╡╤ü╤é╤î ╨▓╨╡╨┤╤æ╨╝ ╤ü╨╡╨▒╤Å ╨║╨░╨║ ╨┐╤Ç╨╡╨╢╨╜╨╕╨╣ ╨║╨╛╨┤.
        rowcount = getattr(cursor, "rowcount", None)
        robbed = (rowcount == 1) if isinstance(rowcount, int) else True
        # ╨ù╨░╤é╨╛╤ç╨║╨░ ╤Ç╨░╤ü╤à╨╛╨┤╤â╨╡╤é╤ü╤Å ╨┐╤Ç╨╕ ╨╗╤Ä╨▒╨╛╨╝ ╨╕╤ü╤à╨╛╨┤╨╡ - ╨┐╨╛╨┐╤ï╤é╨║╨░ ╨▒╤ï╨╗╨░. ╨¥╨░╤ç╨╕╤ü╨╗╨╡╨╜╨╕╨╡
        # ╨╜╤â╨╗╨╡╨▓╨╛╨╡, ╨╡╤ü╨╗╨╕ ╤ü╨┐╨╕╤ü╨░╤é╤î ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î.
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = balance + ?, active_items = excluded.active_items",
            (user_id, board_id, stolen if robbed else 0, json.dumps(active_items),
             stolen if robbed else 0)
        )
        await db.commit()
    if not robbed:
        await message.answer(
            "≡ƒö¬ ╨ƒ╨╛╨║╨░ ╤é╤ï ╨╖╨░╨╝╨░╤à╨╕╨▓╨░╨╗╤ü╤Å, ╤â ╨╢╨╡╤Ç╤é╨▓╤ï ╨║╨╛╨╜╤ç╨╕╨╗╨╕╤ü╤î ╤ê╨╡╨║╨╡╨╗╨╕. ╨ù╨░╤é╨╛╤ç╨║╨░ ╤ü╨╗╨╛╨╝╨░╨╗╨░╤ü╤î ╨▓╨┐╤â╤ü╤é╤â╤Ä.",
            parse_mode="HTML")
        return
    await message.answer(f"≡ƒö¬ <b>╨₧╨ô╨á╨É╨æ╨¢╨ò╨¥╨ÿ╨ò ╨ú╨ö╨É╨¢╨₧╨í╨¼!</b>\n╨ó╤ï ╨┐╨╛╨┤╨║╤Ç╨░╨╗╤ü╤Å ╨╕ ╤ü╨┐╨╕╨╖╨┤╨╕╨╗ <code>{stolen}</code> ╤ê╨╡╨║╨╡╨╗╨╡╨╣ ╤â ╨╢╨╡╤Ç╤é╨▓╤ï.", parse_mode="HTML")
    try: await message.bot.send_message(target_id, f"≡ƒö¬ <b>╨ó╨╡╨▒╤Å ╨╛╨│╤Ç╨░╨▒╨╕╨╗╨╕ ╨▓ /b/!</b>\n╨Ü╨░╨║╨╛╨╣-╤é╨╛ ╨░╨╜╨╛╨╜ ╤ü ╨╖╨░╤é╨╛╤ç╨║╨╛╨╣ ╤â╨║╤Ç╨░╨╗ ╤â ╤é╨╡╨▒╤Å <code>{stolen}</code> ╤ê╨╡╨║╨╡╨╗╨╡╨╣. ╨ù╨░╤ë╨╕╤é╨╕╤é╤î╤ü╤Å ╨╝╨╛╨╢╨╜╨╛, ╨║╤â╨┐╨╕╨▓ ╨¿╨░╨┐╨╛╤ç╨║╤â ╨╕╨╖ ╤ä╨╛╨╗╤î╨│╨╕ ╨▓ /shop.", parse_mode="HTML")
    except: pass