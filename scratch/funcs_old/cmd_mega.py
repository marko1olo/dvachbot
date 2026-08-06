@dp.message(Command("mega"))
async def cmd_mega(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å <b>╨₧╤ê╨╕╨▒╨║╨░:</b> ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┐╨╛╤ü╤é, ╨║╨╛╤é╨╛╤Ç╤ï╨╣ ╤à╨╛╤ç╨╡╤ê╤î ╨╛╨▒╤è╤Å╨▓╨╕╤é╤î ╨▓ ╨£╨╡╨│╨░╤ä╨╛╨╜!", parse_mode="HTML")
        return
    import json
    db = await get_pool()
    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("megaphone_gun"):
        await message.answer("≡ƒôú ╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╨£╨╡╨│╨░╤ä╨╛╨╜╨░! ╨Ü╤â╨┐╨╕ ╨╡╨│╨╛ ╨▓ /shop")
        return
        
    from main import message_to_post, storage_lock
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        pnum = message_to_post.get(key)
        
    if not pnum:
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╤ì╤é╨╛╤é ╨┐╨╛╤ü╤é ╨▓ ╨┐╨░╨╝╤Å╤é╨╕ ╨┤╨╛╤ü╨║╨╕.")
        return
        
    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╨┐╨╛╤ü╤é ╤â╨╢╨╡ ╨╖╨░╨║╤Ç╨╡╨┐╨╗╨╡╨╜
    if board_data[board_id].get('active_pin') == pnum:
        await message.answer("≡ƒôú ╨¡╤é╨╛╤é ╨┐╨╛╤ü╤é ╨ÿ ╨ó╨É╨Ü ╤â╨╢╨╡ ╨▓╨╕╤ü╨╕╤é ╨▓ ╨╖╨░╨║╤Ç╨╡╨┐╨╡! ╨£╨╡╨│╨░╤ä╨╛╨╜ ╨╛╤ü╤é╨░╨╗╤ü╤Å ╤â ╤é╨╡╨▒╤Å.")
        return
        
    active_items["megaphone_gun"] = False
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?", (json.dumps(active_items), user_id, board_id))
        await db.commit()
        
    board_data[board_id]['active_pin'] = pnum
    await update_board_settings(board_id, {'active_pin': pnum})
    
    await message.bot.send_message(message.chat.id, f"≡ƒôú <b>╨Æ╨╜╨╕╨╝╨░╨╜╨╕╨╡ ╨╜╨░ ╨▓╤ü╤Ä ╨┐╨░╨╗╨░╤é╤â!</b>\n╨É╨╜╨╛╨╜ ╨╕╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╗ ╨£╨╡╨│╨░╤ä╨╛╨╜! ╨ƒ╨╛╤ü╤é #{pnum} ╨│╨╗╨╛╨▒╨░╨╗╤î╨╜╨╛ ╨╖╨░╨║╤Ç╨╡╨┐╨╗╨╡╨╜ ╨┤╨╗╤Å ╨▓╤ü╨╡╤à ╤ç╨╕╤é╨░╤é╨╡╨╗╨╡╨╣ ╨▒╨╛╤Ç╨┤╤ï!", parse_mode="HTML")