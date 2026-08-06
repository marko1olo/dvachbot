@dp.message(Command("unpin"))
async def cmd_global_unpin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨í╨╜╨╕╨╝╨░╨╡╤é ╨╖╨░╨║╤Ç╨╡╨┐ ╨╕ ╤â╨┤╨░╨╗╤Å╨╡╤é ╨╡╨│╨╛ ╨╕╨╖ ╨┐╨░╨╝╤Å╤é╨╕/╨æ╨ö.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    old_pin = b_data.get('active_pin')
    b_data['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    target_post_num = None
    if message.reply_to_message:
        # ╨ƒ╨╛╨┤ ╨╗╨╛╨║╨╛╨╝ ╤é╨╛╨╗╤î╨║╨╛ ╤ç╤é╨╡╨╜╨╕╨╡ ╨║╨░╤Ç╤é╤ï message_to_post. ╨ù╨░╨┐╤Ç╨╛╤ü ╨║ ╨æ╨ö (╤ä╨╛╨╗╨▒╤ì╨║,
        # ╨║╨╛╨│╨┤╨░ ╨┐╨╛╤ü╤é ╤â╨╢╨╡ ╨▓╤ï╨│╤Ç╤â╨╢╨╡╨╜ ╨╕╨╖ RAM) ╨▓╤ï╨╜╨╡╤ü╨╡╨╜ ╨╜╨░╤Ç╤â╨╢╤â: ╤Ç╨░╨╜╤î╤ê╨╡ ╨╛╨╜ ╨▓╤ï╨┐╨╛╨╗╨╜╤Å╨╗╤ü╤Å
        # ╤â╨┤╨╡╤Ç╨╢╨╕╨▓╨░╤Å storage_lock.
        async with storage_lock:
            key = (message.chat.id, message.reply_to_message.message_id)
            target_post_num = message_to_post.get(key)
        if not target_post_num:
            post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if post_info: target_post_num = post_info[0]
    else:
        target_post_num = old_pin
    if not target_post_num:
        msg = "Γ£à Pin reset in DB. No active post found to unpin." if lang == 'en' else ("Γ£à DBπü«πâöπâ│τòÖπéüπéÆπâ¬πé╗πââπâêπüùπü╛πüùπüƒπÇéΦºúΘÖñπüÖπéïµèòτ¿┐πüîΦªïπüñπüïπéèπü╛πü¢πéôπÇé" if lang == 'jp' else "Γ£à ╨ù╨░╨║╤Ç╨╡╨┐ ╤ü╨▒╤Ç╨╛╤ê╨╡╨╜ ╨▓ ╨æ╨ö. ╨É╨║╤é╨╕╨▓╨╜╤ï╤à ╨┐╨╛╤ü╤é╨╛╨▓ ╨┤╨╗╤Å ╨╛╤é╨║╤Ç╨╡╨┐╨╗╨╡╨╜╨╕╤Å ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜╨╛.")
        await message.answer(msg)
        return
    msg_start = f"Γ¥î Unpinning post #{target_post_num}..." if lang == 'en' else (f"Γ¥î µèòτ¿┐ #{target_post_num} πü«πâöπâ│τòÖπéüπéÆΦºúΘÖñΣ╕¡..." if lang == 'jp' else f"Γ¥î ╨í╨╜╨╕╨╝╨░╤Ä ╨╖╨░╨║╤Ç╨╡╨┐ ╨┐╨╛╤ü╤é╨░ #{target_post_num}...")
    status_msg = await message.answer(msg_start)
    copies = await get_post_copies(target_post_num)
    if copies:
        async def unpin_one(uid, mid):
            try:
                await message.bot.unpin_chat_message(chat_id=uid, message_id=mid)
                return True
            except Exception: return False
        CHUNK_SIZE = 40
        count = 0
        for i in range(0, len(copies), CHUNK_SIZE):
            chunk = copies[i:i + CHUNK_SIZE]
            res = await asyncio.gather(*[unpin_one(uid, mid) for uid, mid in chunk])
            count += sum(res)
            await asyncio.sleep(1.0)
        await log_global_event('bot', f"≡ƒôì UNPIN: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╤ü╨╜╤Å╨╗ ╨╖╨░╨║╤Ç╨╡╨┐ ╨┐╨╛╤ü╤é╨░ #{target_post_num} ╨╜╨░ /{board_id}/")
        if lang == 'en': final = f"Γ£à Post #{target_post_num} unpinned for {count} users."
        elif lang == 'jp': final = f"Γ£à µèòτ¿┐ #{target_post_num} πü«πâöπâ│τòÖπéüπéÆ {count} Σ║║πü«πâªπâ╝πé╢πâ╝πüïπéëΦºúΘÖñπüùπü╛πüùπüƒπÇé"
        else: final = f"Γ£à ╨ƒ╨╛╤ü╤é #{target_post_num} ╨╛╤é╨║╤Ç╨╡╨┐╨╗╨╡╨╜ ╤â {count} ╤Ä╨╖╨╡╤Ç╨╛╨▓. ╨ÿ╨╖ ╨┐╨░╨╝╤Å╤é╨╕ ╤â╨┤╨░╨╗╨╡╨╜."
        await status_msg.edit_text(final)
    else:
        if lang == 'en': final = f"Γ£à Post #{target_post_num} removed from pin settings."
        elif lang == 'jp': final = f"Γ£à µèòτ¿┐ #{target_post_num} πéÆπâöπâ│τòÖπéüΦ¿¡σ«ÜπüïπéëσëèΘÖñπüùπü╛πüùπüƒπÇé"
        else: final = f"Γ£à ╨ƒ╨╛╤ü╤é #{target_post_num} ╤â╨┤╨░╨╗╨╡╨╜ ╨╕╨╖ ╨╜╨░╤ü╤é╤Ç╨╛╨╡╨║ ╨╖╨░╨║╤Ç╨╡╨┐╨░."
        await status_msg.edit_text(final)