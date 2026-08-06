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
        header = "📨 <b>Invite text for this board:</b>"
        footer = "<i>Just copy and send</i>"
        site_btn = "🌐 Web Version"
    elif lang == 'jp':
        header = "📨 <b>この板の招待用テキスト:</b>"
        footer = "<i>コピーして送信してください</i>"
        site_btn = "🌐 ウェブ版"
    else:
        header = "📨 <b>Текст для приглашения анонов на эту доску:</b>"
        footer = "<i>Просто скопируй и отправь</i>"
        site_btn = "🌐 Веб-версия"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=site_btn, url=site_url)]
    ])

    await message.answer(
        f"{header}\n\n<code>{escape_html(invite_text)}</code>\n\n{footer}",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await message.delete()