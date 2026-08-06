@dp.message(Command("invite"))
async def cmd_invite(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_username = BOARD_CONFIG[board_id]['username']
    site_url = f"https://tgach.top/{board_id}/"

    if lang == 'en':
        source_list = INVITE_TEXTS_EN
    elif lang == 'jp':
        source_list = INVITE_TEXTS_JP
    else:
        source_list = INVITE_TEXTS
    invite_text_raw = random.choice(source_list)
    invite_text = invite_text_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)
    
    if lang == 'en':
        header = "≡ƒô¿ <b>Invite text for this board:</b>"
        footer = "<i>Just copy and send</i>"
        site_btn = "≡ƒîÉ Web Version"
    elif lang == 'jp':
        header = "≡ƒô¿ <b>πüôπü«µ¥┐πü«µï¢σ╛àτö¿πâåπé¡πé╣πâê:</b>"
        footer = "<i>πé│πâöπâ╝πüùπüªΘÇüΣ┐íπüùπüªπüÅπüáπüòπüä</i>"
        site_btn = "≡ƒîÉ πéªπéºπâûτëê"
    else:
        header = "≡ƒô¿ <b>╨ó╨╡╨║╤ü╤é ╨┤╨╗╤Å ╨┐╤Ç╨╕╨│╨╗╨░╤ê╨╡╨╜╨╕╤Å ╨░╨╜╨╛╨╜╨╛╨▓ ╨╜╨░ ╤ì╤é╤â ╨┤╨╛╤ü╨║╤â:</b>"
        footer = "<i>╨ƒ╤Ç╨╛╤ü╤é╨╛ ╤ü╨║╨╛╨┐╨╕╤Ç╤â╨╣ ╨╕ ╨╛╤é╨┐╤Ç╨░╨▓╤î</i>"
        site_btn = "≡ƒîÉ ╨Æ╨╡╨▒-╨▓╨╡╤Ç╤ü╨╕╤Å"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=site_btn, url=site_url)]
    ])

    await message.answer(
        f"{header}\n\n<code>{escape_html(invite_text)}</code>\n\n{footer}",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await message.delete()