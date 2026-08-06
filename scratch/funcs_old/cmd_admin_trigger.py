@dp.message(Command("trigger"))
async def cmd_admin_trigger(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨ƒ╤Ç╨╕╨╜╤â╨┤╨╕╤é╨╡╨╗╤î╨╜╨╛ ╤é╤Ç╨╕╨│╨│╨╡╤Ç╨╕╤é ╨┐╨╡╤Ç╤ü╨╛╨╜╨░-╨▒╨╛╤é╨░ (╨░╨┤╨╝╨╕╨╜╤ü╨║╨░╤Å ╨║╨╛╨╝╨░╨╜╨┤╨░).
    ╨ò╤ü╨╗╨╕ ╨╜╨╡ ╤â╨║╨░╨╖╨░╨╜╨╛ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ ╨┤╨╗╤Å ╤Ç╨╡╨┐╨╗╨░╤Å, ╨▓╤ï╨▒╨╕╤Ç╨░╨╡╤é ╤ü╨╗╤â╤ç╨░╨╣╨╜╨╛╨│╨╛ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    
    text_chunk = ""
    target_post_num = 0

    if message.reply_to_message:
        target_post_num = None
        async with storage_lock:
            key = (message.chat.id, message.reply_to_message.message_id)
            target_post_num = message_to_post.get(key)
        
        if not target_post_num and message.chat.type == 'private':
            text_chunk = message.reply_to_message.text or message.reply_to_message.caption or ""
            if not text_chunk:
                await message.answer("╨ú ╤ì╤é╨╛╨│╨╛ ╨┐╨╛╤ü╤é╨░ ╨╜╨╡╤é ╤é╨╡╨║╤ü╤é╨░ ╨┤╨╗╤Å ╨╛╤é╨▓╨╡╤é╨░.")
                return
            await message.answer("≡ƒñû [╨É╨ö╨£╨ÿ╨¥ ╨¢╨í] ╨ƒ╨╛╤ü╤é ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜ ╨▓ ╨æ╨ö, ╨╜╨╛ ╤é╨╡╨║╤ü╤é ╨┐╨╛╨╗╤â╤ç╨╡╨╜. ╨ù╨░╨┐╤â╤ü╨║╨░╤Ä ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╤Ä...")
            photo_id = message.reply_to_message.photo[-1].file_id if message.reply_to_message.photo else None
            spawn_task(schedule_persona_reply(message.bot, board_id, 0, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))
            return
            
        if not target_post_num:
            await message.answer("╨ƒ╨╛╤ü╤é ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜ ╨▓ ╨╝╨░╨┐╨┐╨╕╨╜╨│╨╡.")
            return

        photo_id = None
        post_data = messages_storage.get(target_post_num)
        if post_data:
            c = post_data.get('content', {})
            text_chunk = c.get('text', '') or c.get('caption', '') or '[╨╝╨╡╨┤╨╕╨░-╨┐╨╛╤ü╤é]'
            if c.get('type') == 'photo':
                photo_id = c.get('file_id')
            elif c.get('type') == 'media_group' and c.get('media'):
                for m in c['media']:
                    if m.get('type') == 'photo' and m.get('file_id'):
                        photo_id = m['file_id']
                        break
            
        if not text_chunk:
            await message.answer("╨ú ╤ì╤é╨╛╨│╨╛ ╨┐╨╛╤ü╤é╨░ ╨╜╨╡╤é ╤é╨╡╨║╤ü╤é╨░ ╨╕╨╗╨╕ ╨╝╨╡╨┤╨╕╨░ ╨┤╨╗╤Å ╨╛╤é╨▓╨╡╤é╨░.")
            return
            
        await message.answer("≡ƒñû [╨É╨ö╨£╨ÿ╨¥] ╨¥╨╡╨╣╤Ç╨╛╨░╨╜╨╛╨╜ ╨┐╤Ç╨╕╨╜╤â╨┤╨╕╤é╨╡╨╗╤î╨╜╨╛ ╤Ç╨░╨╖╨▒╤â╨╢╨╡╨╜. ╨ù╨░╨┐╤â╤ü╨║╨░╤Ä ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╤Ä...")
        spawn_task(schedule_persona_reply(message.bot, board_id, target_post_num, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))
    else:
        candidates = []
        fav_candidates = []
        now_dt = datetime.now(UTC)
        async with storage_lock:
            b_data = board_data.get(board_id, {})
            # ╨æ╨╡╤Ç╨╡╨╝ ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ 5000 ╨│╨╗╨╛╨▒╨░╨╗╤î╨╜╤ï╤à ╨┐╨╛╤ü╤é╨╛╨▓, ╤ç╤é╨╛╨▒╤ï ╨│╨░╤Ç╨░╨╜╤é╨╕╤Ç╨╛╨▓╨░╨╜╨╜╨╛ ╨╜╨░╨╣╤é╨╕ 150 ╨┤╨╗╤Å ╤é╨╡╨║╤â╤ë╨╡╨╣ ╨┤╨╛╤ü╨║╨╕
            board_posts = [
                (pnum, data) for pnum, data in list(messages_storage.items())[-5000:]
                if data.get('board_id') == board_id and data.get('author_id', 0) != 0
            ]
            for pnum, data in board_posts[-150:]:
                c = data.get('content', {})
                t = c.get('text') or c.get('caption') or ''
                p_id = None
                if c.get('type') == 'photo':
                    p_id = c.get('file_id')
                elif c.get('type') == 'media_group' and c.get('media'):
                    for m in c['media']:
                        if m.get('type') == 'photo' and m.get('file_id'):
                            p_id = m['file_id']
                            break
                if len(t) > 5 or p_id:
                    t_val = t or '[╨║╨░╤Ç╤é╨╕╨╜╨║╨░]'
                    candidates.append((pnum, t_val, p_id))
                    if data.get('author_id') in b_data.get('persona_favorites', {}):
                        fav_candidates.append((pnum, t_val, p_id))
        
        if fav_candidates and random.random() < 0.75:
            candidates = fav_candidates

        if not candidates:
            await message.answer("ΓÜá∩╕Å ╨¥╨╡╤é ╨┐╨╛╨┤╤à╨╛╨┤╤Å╤ë╨╕╤à ╨┐╨╛╤ü╤é╨╛╨▓ ╨┤╨╗╤Å ╤é╤Ç╨╕╨│╨│╨╡╤Ç╨░ ╨╜╨░ ╤ì╤é╨╛╨╣ ╨┤╨╛╤ü╨║╨╡.")
            return
            
        target_post_num, text_chunk, photo_id = random.choice(candidates)
        await message.answer(f"≡ƒñû [╨É╨ö╨£╨ÿ╨¥] ╨Æ╤ï╨▒╤Ç╨░╨╜ ╤ü╨╗╤â╤ç╨░╨╣╨╜╤ï╨╣ ╨┐╨╛╤ü╤é #{target_post_num} ╨┤╨╗╤Å ╨░╤é╨░╨║╨╕. ╨ù╨░╨┐╤â╤ü╨║╨░╤Ä ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╤Ä...")
        spawn_task(schedule_persona_reply(message.bot, board_id, target_post_num, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))