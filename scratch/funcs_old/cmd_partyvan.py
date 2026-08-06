@dp.message(Command("partyvan"))
async def cmd_partyvan(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å <b>╨₧╤ê╨╕╨▒╨║╨░:</b> ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┤╨╛╨╜╨╛╤ü-╨┐╨╛╤ü╤é ╨╢╨╡╤Ç╤é╨▓╤ï, ╤ç╤é╨╛╨▒╤ï ╨▓╤ï╨╖╨▓╨░╤é╤î ╨ƒ╨░╤é╨╕╨▓╤ì╨╜!", parse_mode="HTML")
        return
    import json
    from datetime import datetime, timedelta, UTC
    db = await get_pool()
    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("partyvan_gun"):
        await message.answer("≡ƒÜö ╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╤Ç╨░╤å╨╕╨╕ ╨┤╨╗╤Å ╨▓╤ï╨╖╨╛╨▓╨░ ╨ƒ╨░╤é╨╕╨▓╤ì╨╜╨░! ╨Ü╤â╨┐╨╕ ╨╡╤æ ╨▓ /shop")
        return
    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0 or target_id == user_id: 
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╛╨┐╤Ç╨╡╨┤╨╡╨╗╨╕╤é╤î ╤å╨╡╨╗╤î ╨┤╨╛╨╜╨╛╤ü╨░.")
        return
        
    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╤å╨╡╨╗╤î ╤â╨╢╨╡ ╨▓ ╨Ü╨ƒ╨ù
    async with storage_lock:
        mute_end = board_data[board_id]['mutes'].get(target_id)
    if mute_end and mute_end > datetime.now(UTC) + timedelta(hours=11):
        await message.answer("≡ƒÜö ╨¡╤é╨╛╤é ╨░╨╜╨╛╨╜ ╨ú╨û╨ò ╨╛╤é╨║╨╕╤ü╨░╨╡╤é ╨▓ ╨Ü╨ƒ╨ù ╨╜╨░╨┤╨╛╨╗╨│╨╛! ╨¥╨╡ ╤é╤Ç╨░╤é╤î ╨▓╤ï╨╖╨╛╨▓ ╨╖╤Ç╤Å, ╤Ç╨░╤å╨╕╤Å ╨╛╤ü╤é╨░╨╗╨░╤ü╤î ╤â ╤é╨╡╨▒╤Å.")
        return
    
    active_items["partyvan_gun"] = False
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?", (json.dumps(active_items), user_id, board_id))
        await db.commit()
    
    async with storage_lock:
        board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(hours=12)
    await apply_regular_mute(target_id, board_id, 12 * 3600)
    
    await message.bot.send_message(message.chat.id, f"≡ƒÜö <b>╨Æ╨¥╨ÿ╨£╨É╨¥╨ÿ╨ò! ╨á╨É╨æ╨₧╨ó╨É╨ò╨ó ╨₧╨£╨₧╨¥!</b> ≡ƒÜö\n╨ƒ╨╛ ╨┤╨╛╨╜╨╛╤ü╤â ╨░╨╜╨╛╨╜╨░ ╨╖╨░ ╨░╨▓╤é╨╛╤Ç╨╛╨╝ ╤ì╤é╨╛╨│╨╛ ╨┐╨╛╤ü╤é╨░ ╨▓╤ï╨╡╤à╨░╨╗ ╨┐╨░╤é╨╕╨▓╤ì╨╜! ╨û╨╡╤Ç╤é╨▓╨░ <code>{target_id}</code> ╨╛╤é╨┐╤Ç╨░╨▓╨╗╨╡╨╜╨░ ╨▓ ╨Ü╨ƒ╨ù (╨╢╨╡╤ü╤é╨║╨╕╨╣ ╨╝╤â╤é) ╨╜╨░ 12 ╤ç╨░╤ü╨╛╨▓!\n<i>╨Æ╤ï╨╣╤é╨╕ ╤Ç╨░╨╜╤î╤ê╨╡ ╨╝╨╛╨╢╨╜╨╛ ╤é╨╛╨╗╤î╨║╨╛ ╨┤╨░╨▓ ╨▓╨╖╤Å╤é╨║╤â ╨▓ /shop.</i>", reply_to_message_id=message.reply_to_message.message_id, parse_mode="HTML")