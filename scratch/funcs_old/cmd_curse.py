@dp.message(Command("curse", "vomit"))
async def cmd_curse(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å <b>╨₧╤ê╨╕╨▒╨║╨░:</b> ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┐╨╛╤ü╤é ╨╢╨╡╤Ç╤é╨▓╤ï, ╤ç╤é╨╛╨▒╤ï ╨┐╨╛╨┤╨╗╨╕╤é╤î ╤ü╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡!", parse_mode="HTML")
        return
    import time, json
    db = await get_pool()
    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("laxative_gun"):
        await message.answer("≡ƒÜ╜ ╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╨í╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨│╨╛! ╨Ü╤â╨┐╨╕ ╨╡╨│╨╛ ╨▓ ╨╝╨░╨│╨░╨╖╨╕╨╜╨╡: /shop")
        return
    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0 or target_id == user_id: 
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╤å╨╡╨╗╤î ╨╕╨╗╨╕ ╤é╤ï ╨┐╤ï╤é╨░╨╡╤ê╤î╤ü╤Å ╨┐╤Ç╨╛╨║╨╗╤Å╤ü╤é╤î ╤ü╨░╨╝ ╤ü╨╡╨▒╤Å.")
        return
    
    current_time = int(time.time())
    t_items = await _get_user_active_items(db, target_id, board_id)
    
    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╤å╨╡╨╗╤î ╤â╨╢╨╡ ╨┐╤Ç╨╛╨║╨╗╤Å╤é╨░
    if t_items.get("cursed_until", 0) > current_time:
        await message.answer("≡ƒÜ╜ ╨ú ╤ì╤é╨╛╨│╨╛ ╨░╨╜╨╛╨╜╨░ ╨ÿ ╨ó╨É╨Ü ╤ü╨╗╨╛╨▓╨╡╤ü╨╜╤ï╨╣ ╨┐╨╛╨╜╨╛╤ü! ╨Æ╤ï╨▒╨╡╤Ç╨╕ ╨┤╤Ç╤â╨│╤â╤Ä ╨╢╨╡╤Ç╤é╨▓╤â. ╨í╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡ ╨╛╤ü╤é╨░╨╗╨╛╤ü╤î ╤â ╤é╨╡╨▒╤Å.")
        return
        
    active_items["laxative_gun"] = False
    t_items["cursed_until"] = current_time + 3600

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
    await message.answer("≡ƒÜ╜ <b>╨ƒ╨á╨₧╨Ü╨¢╨»╨ó╨ÿ╨ò ╨í╨á╨É╨æ╨₧╨ó╨É╨¢╨₧!</b>\n╨ó╤ï ╨┐╨╛╨┤╨╗╨╕╨╗ ╤ü╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡ ╨▓ ╤ç╨░╨╣ ╤ì╤é╨╛╨╝╤â ╨░╨╜╨╛╨╜╤â. ╨ú ╨╜╨╡╨│╨╛ ╨╜╨░╤ç╨░╨╗╤ü╤Å ╤ü╨╗╨╛╨▓╨╡╤ü╨╜╤ï╨╣ ╨┐╨╛╨╜╨╛╤ü: ╨╛╨╜ ╤å╨╡╨╗╤ï╨╣ ╤ç╨░╤ü ╨╜╨╡ ╤ü╨╝╨╛╨╢╨╡╤é ╨┐╨╕╤ü╨░╤é╤î ╨┐╨╛╤ü╤é╤ï ╨┤╨╗╨╕╨╜╨╜╨╡╨╡ 50 ╤ü╨╕╨╝╨▓╨╛╨╗╨╛╨▓!", parse_mode="HTML")