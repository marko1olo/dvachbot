@dp.message(Command("getid"))
async def cmd_get_file_id(message: types.Message):
    # Проверяем, есть ли реплай
    if not message.reply_to_message:
        await message.answer("⚠️ Чтобы получить ID, ответь этой командой на гифку, фото или кружок.")
        return
    
    rep = message.reply_to_message
    file_id = None
    file_type = "Неизвестно"

    # Проверяем все возможные типы медиа
    if rep.animation:
        file_id = rep.animation.file_id
        file_type = "Animation (GIF)"
    elif rep.document:
        file_id = rep.document.file_id
        file_type = "Document (File/GIF)"
    elif rep.photo:
        file_id = rep.photo[-1].file_id
        file_type = "Photo"
    elif rep.video:
        file_id = rep.video.file_id
        file_type = "Video"
    elif rep.video_note:
        file_id = rep.video_note.file_id
        file_type = "Video Note (Кружок)"
    elif rep.sticker:
        file_id = rep.sticker.file_id
        file_type = "Sticker"
    elif rep.voice:
        file_id = rep.voice.file_id
        file_type = "Voice"

    if file_id:
        # Enterprise-отклик с готовым кодом для вставки
        response = (
            f"✅ <b>Тип:</b> {file_type}\n"
            f"🆔 <b>FILE_ID:</b>\n<code>{file_id}</code>\n\n"
            f"<i>Скопируй эту строку</i>"
        )
        await message.answer(response, parse_mode="HTML")
    else:
        await message.answer("❌ В этом сообщении нет медиа-файла.")