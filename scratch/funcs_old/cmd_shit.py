@dp.message(Command("shit"))
async def cmd_shit(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å <b>╨₧╤ê╨╕╨▒╨║╨░:</b> ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┐╨╛╤ü╤é ╨╢╨╡╤Ç╤é╨▓╤ï, ╨▓ ╨║╨╛╤é╨╛╤Ç╤â╤Ä ╤à╨╛╤ç╨╡╤ê╤î ╨║╨╕╨╜╤â╤é╤î ╨│╨╛╨▓╨╜╨╛╨╝!", parse_mode="HTML")
        return
    import time
    import json
    db = await get_pool()
    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("shit_gun"):
        await message.answer("≡ƒÉÆ ╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╨║╤â╤ü╨║╨░ ╨│╨╛╨▓╨╜╨░! ╨Ü╤â╨┐╨╕ ╨╡╨│╨╛ ╨▓ ╤é╨╡╨╜╨╡╨▓╨╛╨╝ ╨╝╨░╨│╨░╨╖╨╕╨╜╨╡: /shop")
        return
    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0 or target_id == user_id: 
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨┐╤Ç╨╕╤å╨╡╨╗╨╕╤é╤î╤ü╤Å ╨╕╨╗╨╕ ╤é╤ï ╨┐╤ï╤é╨░╨╡╤ê╤î╤ü╤Å ╨╛╨▒╨╝╨░╨╖╨░╤é╤î ╤ü╨░╨╝ ╤ü╨╡╨▒╤Å.")
        return
    
    t_items = await _get_user_active_items(db, target_id, board_id)
    current_time = int(time.time())
    
    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╤å╨╡╨╗╤î ╤â╨╢╨╡ ╨▓ ╨│╨╛╨▓╨╜╨╡
    if t_items.get("shit_until", 0) > current_time:
        await message.answer("≡ƒÆ⌐ ╨¡╤é╨░ ╤å╨╡╨╗╤î ╨ú╨û╨ò ╨╛╨▒╨╝╨░╨╖╨░╨╜╨░ ╨│╨╛╨▓╨╜╨╛╨╝! ╨Æ╤ï╨▒╨╡╤Ç╨╕ ╨║╨╛╨│╨╛-╨╜╨╕╨▒╤â╨┤╤î ╤ç╨╕╤ü╤é╨╛╨│╨╛. ╨Ü╤â╤ü╨╛╨║ ╨│╨╛╨▓╨╜╨░ ╨╛╤ü╤é╨░╨╗╤ü╤Å ╤â ╤é╨╡╨▒╤Å.")
        return

    active_items["shit_gun"] = False
    
    if t_items.get("tinfoil_hat", 0) > current_time:
        active_items["shit_until"] = current_time + 3600
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?", (json.dumps(active_items), user_id, board_id))
            await db.commit()
        await message.answer("≡ƒæ╜ <b>╨¿╨É╨ƒ╨₧╨º╨Ü╨É ╨ÿ╨ù ╨ñ╨₧╨¢╨¼╨ô╨ÿ!</b>\n╨û╨╡╤Ç╤é╨▓╨░ ╨╛╨║╨░╨╖╨░╨╗╨░╤ü╤î ╨┐╨╛╨┤ ╨╖╨░╤ë╨╕╤é╨╛╨╣! ╨ô╨╛╨▓╨╜╨╛ ╨╛╤é╤ü╨║╨╛╤ç╨╕╨╗╨╛ ╨╛╤é ╤ä╨╛╨╗╤î╨│╨╕ ╨┐╤Ç╤Å╨╝╨╛ ╤é╨╡╨▒╨╡ ╨▓ ╨╗╨╕╤å╨╛. ╨ó╨╡╨┐╨╡╤Ç╤î ╨ó╨½ ╨╛╨▒╨╝╨░╨╖╨░╨╜ ╨│╨╛╨▓╨╜╨╛╨╝ ╨╜╨░ 1 ╤ç╨░╤ü!", parse_mode="HTML")
        return

    t_items["shit_until"] = current_time + 3600
    async with db_lock:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
            (user_id, board_id, json.dumps(active_items))
        )
        await db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
            (target_id, board_id, json.dumps(t_items))
        )
        await db.commit()
    await message.answer("≡ƒÉÆ <b>╨ƒ╨₧╨ƒ╨É╨ö╨É╨¥╨ÿ╨ò!</b>\n╨ó╤ï ╨╝╨╡╤é╨║╨╛ ╨║╨╕╨╜╤â╨╗ ╨║╤â╤ü╨╛╨║ ╨│╨╛╨▓╨╜╨░! ╨û╨╡╤Ç╤é╨▓╨░ ╨╛╨▒╨╝╨░╨╖╨░╨╜╨░ ╨╜╨░ 1 ╤ç╨░╤ü ╨╕ ╨┐╨╛╨╗╤â╤ç╨╕╤é ╨╕╨║╨╛╨╜╨║╤â ≡ƒÆ⌐ ╨▓╨╛ ╨▓╤ü╨╡╤à ╤ü╨▓╨╛╨╕╤à ╨┐╨╛╤ü╤é╨░╤à.", parse_mode="HTML")
    try: await message.bot.send_message(target_id, "≡ƒÉÆ <b>╨Æ ╨ó╨ò╨æ╨» ╨Ü╨ÿ╨¥╨ú╨¢╨ÿ ╨ô╨₧╨Æ╨¥╨₧╨£!</b>\n╨Ü╨░╨║╨╛╨╣-╤é╨╛ ╨░╨╜╨╛╨╜ ╨╛╨▒╨╝╨░╨╖╨░╨╗ ╤é╨╡╨▒╤Å. ╨ú ╤é╨╡╨▒╤Å ╤ü╤é╨░╤é╤â╤ü ≡ƒÆ⌐ ╨╜╨░ 1 ╤ç╨░╤ü.\n╨¢╨╡╨║╨░╤Ç╤ü╤é╨▓╨╛ ╨╛╤é ╤ü╤é╨░╤é╤â╤ü╨░: ╨É╨╝╨╕╨╜╨░╨╖╨╕╨╜ ╨▓ /shop.", parse_mode="HTML")
    except: pass