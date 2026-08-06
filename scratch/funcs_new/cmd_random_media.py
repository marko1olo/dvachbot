@dp.message(Command("random", "randpic", "randvid", "rand"))
@throttle(rate=5)
async def cmd_random_media(message: types.Message):
    args = (message.text or message.caption or "").split()
    count = 1
    # isdecimal, а не isdigit: у isdigit истинны надстрочные и кружковые
    # цифры ('²', '③'), которые int() НЕ принимает, и /random ² роняло
    # обработчик с ValueError. isdecimal истинно ровно для того, что int()
    # разбирает, включая арабо-индийские цифры.
    if len(args) > 1 and args[1].isdecimal():
        count = int(args[1])
        count = max(1, min(10, count))
    
    command = args[0].lower()
    is_video_req = "vid" in command
    
    media_items = []
    
    for _ in range(count * 2): # Try more times in case of invalid media
        if len(media_items) >= count:
            break
            
        if is_video_req:
            post = await get_random_video_post(allowed_boards=None)
        else:
            post = await get_random_image_post(allowed_boards=None)
            
        if not post or "content" not in post:
            continue
            
        files = post["content"].get("files", [])
        idx = post.get("_selected_file_index", 0)
        
        if idx < len(files):
            f = files[idx]
            file_id = f.get("original_file_id") or f.get("file_id")
            if file_id:
                type_ = f.get("type", "")
                is_vid = type_ in ("video", "animation", "video_note")
                media_items.append((file_id, is_vid))

    if not media_items:
        await message.answer("❌ В пуле нет подходящих медиа.", disable_notification=True)
        return

    import hashlib
    import os
    secret = os.environ["SECRET_KEY"]
    user_hash = hashlib.sha256((str(message.from_user.id) + secret).encode()).hexdigest()[:12]
    caption = f"🎲 Рандом (x{len(media_items)}) | #{user_hash}"
    
    if len(media_items) == 1:
        file_id, is_vid = media_items[0]
        try:
            if is_vid:
                await message.answer_video(file_id, caption=caption, parse_mode="HTML")
            else:
                await message.answer_photo(file_id, caption=caption, parse_mode="HTML")
        except Exception as e:
            print(f"Error sending random media: {e}")
            await message.answer("❌ Ошибка при отправке. Возможно файл удален с серверов Telegram.")
    else:
        media_group = []
        for i, (file_id, is_vid) in enumerate(media_items):
            cap = caption if i == 0 else None
            if is_vid:
                media_group.append(InputMediaVideo(media=file_id, caption=cap, parse_mode="HTML"))
            else:
                media_group.append(InputMediaPhoto(media=file_id, caption=cap, parse_mode="HTML"))
        
        try:
            await message.answer_media_group(media_group)
        except Exception as e:
            print(f"Error sending random media group: {e}")
            await message.answer("❌ Ошибка при отправке альбома.")