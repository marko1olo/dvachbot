@dp.message(Command("shoot"))
async def cmd_shoot(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å ╨í╨┤╨╡╨╗╨░╨╣ Reply ╨╜╨░ ╨┐╨╛╤ü╤é ╨╢╨╡╤Ç╤é╨▓╤ï ╤ü ╨║╨╛╨╝╨░╨╜╨┤╨╛╨╣ /shoot!")
        return

    import time
    db = await get_pool()

    active_items = await _get_user_active_items(db, user_id, board_id)
    if not active_items.get("mute_gun"):
        await message.answer("╨ú ╤é╨╡╨▒╤Å ╨╜╨╡╤é ╨£╤â╤é-╨ô╨░╨╜╨░! ╨Ü╤â╨┐╨╕ ╨╡╨│╨╛ ╨▓ ╨╝╨░╨│╨░╨╖╨╕╨╜╨╡: /shop")
        return

    target_id = await get_author_id_by_reply(message)
    if not target_id or target_id == 0:
        await message.answer("≡ƒÜ½ ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╨░╨▓╤é╨╛╤Ç╨░ ╨┐╨╛╤ü╤é╨░...")
        return
    if target_id == user_id:
        await message.answer("╨ó╤ï ╨┐╤ï╤é╨░╨╡╤ê╤î╤ü╤Å ╨▓╤ï╤ü╤é╤Ç╨╡╨╗╨╕╤é╤î ╨▓ ╤ü╨░╨╝╨╛╨│╨╛ ╤ü╨╡╨▒╤Å? ╨ÿ╨┤╨╕╨╛╤é.")
        return

    # ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╨╝ ╨ù╨╡╤Ç╨║╨░╨╗╤î╨╜╤ï╨╣ ╨⌐╨╕╤é ╤â ╤å╨╡╨╗╨╕
    t_items = await _get_user_active_items(db, target_id, board_id)
    current_time = int(time.time())

    if t_items.get("reflect_shield_until", 0) > current_time:
        # ╨á╨╕╨║╨╛╤ê╨╡╤é!
        # t_items ╨┐╨╡╤Ç╨╡╨┤╨░╤æ╨╝ ╨Æ╨¥╨ú╨ó╨á╨ÿ ╨║╨╛╨╜╤é╨╡╨║╤ü╤é╨░: ╨╢╨╕╨▓╨░╤Å _handle_shoot_bounce
        # ╨┐╤Ç╨╕╨╜╨╕╨╝╨░╨╡╤é ╨╛╨┤╨╕╨╜ ╨░╤Ç╨│╤â╨╝╨╡╨╜╤é. ╨Æ╤é╨╛╤Ç╤ï╨╝ ╨┐╨╛╨╖╨╕╤å╨╕╨╛╨╜╨╜╤ï╨╝ ╤ì╤é╨╛ ╨▒╤ï╨╗ TypeError,
        # ╤é╨╛ ╨╡╤ü╤é╤î ╨ù╨╡╤Ç╨║╨░╨╗╤î╨╜╤ï╨╣ ╨⌐╨╕╤é ╨╜╨╡ ╤ü╤Ç╨░╨▒╨░╤é╤ï╨▓╨░╨╗ ╨╜╨╕ ╤Ç╨░╨╖╤â.
        await _handle_shoot_bounce(ShootContext(message, db, db_lock, board_id, user_id, target_id, active_items, t_items))
        return

    # ╨ÿ╨┤╨╡╨╝╨┐╨╛╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î: ╤å╨╡╨╗╤î ╤â╨╢╨╡ ╨▓ ╨╝╤â╤é╨╡
    from datetime import datetime, UTC
    from main import storage_lock, board_data
    async with storage_lock:
        current_mute = board_data[board_id]['mutes'].get(target_id)
        
    if current_mute and current_mute > datetime.now(UTC):
        await message.answer("ΓÜá∩╕Å ╨¡╤é╨░ ╤å╨╡╨╗╤î ╨ú╨û╨ò ╨╜╨░╤à╨╛╨┤╨╕╤é╤ü╤Å ╨▓ ╨╝╤â╤é╨╡! ╨Æ╤ï╨▒╨╡╤Ç╨╕ ╨║╨╛╨│╨╛-╤é╨╛ ╨┤╤Ç╤â╨│╨╛╨│╨╛. ╨£╤â╤é-╨ô╨░╨╜ ╨╛╤ü╤é╨░╨╗╤ü╤Å ╤â ╤é╨╡╨▒╤Å.")
        # ╨ù╨┤╨╡╤ü╤î ╤ü╤é╨╛╤Å╨╗ ╨▓╤ï╨╖╨╛╨▓ _handle_shoot_bounce. ╨₧╨╜ ╨á╨É╨æ╨₧╨ó╨É╨¢, ╨╕ ╨▓ ╤ì╤é╨╛╨╝ ╨▒╤ï╨╗╨░
        # ╨┐╤Ç╨╛╨▒╨╗╨╡╨╝╨░: ╤Ç╨╕╨║╨╛╤ê╨╡╤é ╤ü╨┐╨╕╤ü╤ï╨▓╨░╨╡╤é ╨╝╤â╤é-╨│╨░╨╜ ╨╕ ╤ü╨░╨╢╨░╨╡╤é ╨▓ ╨╝╤â╤é ╨╜╨░ ╤ç╨░╤ü ╤ü╨░╨╝╨╛╨│╨╛
        # ╤ü╤é╤Ç╨╡╨╗╨║╨░, ╨╛╤é╨┐╤Ç╨░╨▓╨╗╤Å╤Å ╨▓╨┤╨╛╨│╨╛╨╜╨║╤â ┬½≡ƒ¢í∩╕Å ╨ù╨ò╨á╨Ü╨É╨¢╨¼╨¥╨½╨Ö ╨⌐╨ÿ╨ó!┬╗. ╨ó╨╛ ╨╡╤ü╤é╤î ╨╜╨░ ╨┐╨╛╨┐╤ï╤é╨║╤â
        # ╨▓╤ï╤ü╤é╤Ç╨╡╨╗╨╕╤é╤î ╨▓ ╤â╨╢╨╡ ╨╖╨░╨╝╤â╤ç╨╡╨╜╨╜╨╛╨│╨╛ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î ╨┐╨╛╨╗╤â╤ç╨░╨╗ ╨┤╨▓╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╤Å
        # ╨┐╨╛╨┤╤Ç╤Å╨┤ ╤ü ╨┐╤Ç╨╛╤é╨╕╨▓╨╛╨┐╨╛╨╗╨╛╨╢╨╜╤ï╨╝ ╤ü╨╝╤ï╤ü╨╗╨╛╨╝ ╨╕ ╤é╨╡╤Ç╤Å╨╗ ╨┐╤Ç╨╡╨┤╨╝╨╡╤é ΓÇö ╨┐╤Ç╤Å╨╝╨╛ ╨▓╨╛╨┐╤Ç╨╡╨║╨╕
        # ╤ü╤é╤Ç╨╛╨║╨╡ ╨▓╤ï╤ê╨╡, ╨│╨┤╨╡ ╨╡╨╝╤â ╤ü╨║╨░╨╖╨░╨╜╨╛ ┬½╨£╤â╤é-╨ô╨░╨╜ ╨╛╤ü╤é╨░╨╗╤ü╤Å ╤â ╤é╨╡╨▒╤Å┬╗.
        # ╨Æ╨╡╤é╨║╨░ ┬½╤å╨╡╨╗╤î ╤â╨╢╨╡ ╨▓ ╨╝╤â╤é╨╡┬╗ ╨╜╨╡ ╤Ç╨╕╨║╨╛╤ê╨╡╤é: ╨┐╤Ç╨╡╨┤╤â╨┐╤Ç╨╡╨╢╨┤╨░╨╡╨╝ ╨╕ ╨▓╤ï╤à╨╛╨┤╨╕╨╝, ╨╜╨╕╤ç╨╡╨│╨╛
        # ╨╜╨╡ ╤ü╨┐╨╕╤ü╤ï╨▓╨░╤Å. ╨¡╤é╨╛ ╤ü╨╛╨╖╨╜╨░╤é╨╡╨╗╤î╨╜╨╛╨╡ ╨╕╨╖╨╝╨╡╨╜╨╡╨╜╨╕╨╡ ╨┐╨╛╨▓╨╡╨┤╨╡╨╜╨╕╤Å, ╨░ ╨╜╨╡ ╤ä╨╕╨║╤ü ╨┐╨░╨┤╨╡╨╜╨╕╤Å.
        return

    # ╨₧╨▒╤ï╤ç╨╜╤ï╨╣ ╨╝╤â╤é ╤å╨╡╨╗╨╕
    await _handle_shoot_success(ShootContext(message, db, db_lock, board_id, user_id, target_id, active_items))