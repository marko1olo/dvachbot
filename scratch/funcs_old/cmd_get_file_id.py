@dp.message(Command("getid"))
async def cmd_get_file_id(message: types.Message):
    # ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╨╝, ╨╡╤ü╤é╤î ╨╗╨╕ ╤Ç╨╡╨┐╨╗╨░╨╣
    if not message.reply_to_message:
        await message.answer("ΓÜá∩╕Å ╨º╤é╨╛╨▒╤ï ╨┐╨╛╨╗╤â╤ç╨╕╤é╤î ID, ╨╛╤é╨▓╨╡╤é╤î ╤ì╤é╨╛╨╣ ╨║╨╛╨╝╨░╨╜╨┤╨╛╨╣ ╨╜╨░ ╨│╨╕╤ä╨║╤â, ╤ä╨╛╤é╨╛ ╨╕╨╗╨╕ ╨║╤Ç╤â╨╢╨╛╨║.")
        return
    
    rep = message.reply_to_message
    file_id = None
    file_type = "╨¥╨╡╨╕╨╖╨▓╨╡╤ü╤é╨╜╨╛"

    # ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╨╝ ╨▓╤ü╨╡ ╨▓╨╛╨╖╨╝╨╛╨╢╨╜╤ï╨╡ ╤é╨╕╨┐╤ï ╨╝╨╡╨┤╨╕╨░
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
        file_type = "Video Note (╨Ü╤Ç╤â╨╢╨╛╨║)"
    elif rep.sticker:
        file_id = rep.sticker.file_id
        file_type = "Sticker"
    elif rep.voice:
        file_id = rep.voice.file_id
        file_type = "Voice"

    if file_id:
        # Enterprise-╨╛╤é╨║╨╗╨╕╨║ ╤ü ╨│╨╛╤é╨╛╨▓╤ï╨╝ ╨║╨╛╨┤╨╛╨╝ ╨┤╨╗╤Å ╨▓╤ü╤é╨░╨▓╨║╨╕
        response = (
            f"Γ£à <b>╨ó╨╕╨┐:</b> {file_type}\n"
            f"≡ƒåö <b>FILE_ID:</b>\n<code>{file_id}</code>\n\n"
            f"<i>╨í╨║╨╛╨┐╨╕╤Ç╤â╨╣ ╤ì╤é╤â ╤ü╤é╤Ç╨╛╨║╤â</i>"
        )
        await message.answer(response, parse_mode="HTML")
    else:
        await message.answer("Γ¥î ╨Æ ╤ì╤é╨╛╨╝ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╕ ╨╜╨╡╤é ╨╝╨╡╨┤╨╕╨░-╤ä╨░╨╣╨╗╨░.")