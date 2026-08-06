@dp.message(Command("trigger"))
async def cmd_admin_trigger(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Принудительно триггерит персона-бота (админская команда).
    Если не указано сообщение для реплая, выбирает случайного пользователя.
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
                await message.answer("У этого поста нет текста для ответа.")
                return
            await message.answer("🤖 [АДМИН ЛС] Пост не найден в БД, но текст получен. Запускаю генерацию...")
            photo_id = message.reply_to_message.photo[-1].file_id if message.reply_to_message.photo else None
            spawn_task(schedule_persona_reply(message.bot, board_id, 0, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))
            return
            
        if not target_post_num:
            await message.answer("Пост не найден в маппинге.")
            return

        photo_id = None
        post_data = messages_storage.get(target_post_num)
        if post_data:
            c = post_data.get('content', {})
            text_chunk = c.get('text', '') or c.get('caption', '') or '[медиа-пост]'
            if c.get('type') == 'photo':
                photo_id = c.get('file_id')
            elif c.get('type') == 'media_group' and c.get('media'):
                for m in c['media']:
                    if m.get('type') == 'photo' and m.get('file_id'):
                        photo_id = m['file_id']
                        break
            
        if not text_chunk:
            await message.answer("У этого поста нет текста или медиа для ответа.")
            return
            
        await message.answer("🤖 [АДМИН] Нейроанон принудительно разбужен. Запускаю генерацию...")
        spawn_task(schedule_persona_reply(message.bot, board_id, target_post_num, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))
    else:
        candidates = []
        fav_candidates = []
        now_dt = datetime.now(UTC)
        async with storage_lock:
            b_data = board_data.get(board_id, {})
            # Берем последние 5000 глобальных постов, чтобы гарантированно найти 150 для текущей доски
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
                    t_val = t or '[картинка]'
                    candidates.append((pnum, t_val, p_id))
                    if data.get('author_id') in b_data.get('persona_favorites', {}):
                        fav_candidates.append((pnum, t_val, p_id))
        
        if fav_candidates and random.random() < 0.75:
            candidates = fav_candidates

        if not candidates:
            await message.answer("⚠️ Нет подходящих постов для триггера на этой доске.")
            return
            
        target_post_num, text_chunk, photo_id = random.choice(candidates)
        await message.answer(f"🤖 [АДМИН] Выбран случайный пост #{target_post_num} для атаки. Запускаю генерацию...")
        spawn_task(schedule_persona_reply(message.bot, board_id, target_post_num, text_chunk, stream, is_admin_trigger=True, photo_file_id=photo_id))