@dp.message(Command("app"))
async def cmd_app(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет кнопку для открытия веб-приложения (сайта).
    """
    if not board_id: return
    WEBAPP_URL = "https://tgach.top" 
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "Click the button below to open the TGACH web interface:"
        btn_text = "Open Web App"
    elif lang == 'jp':
        text = "下のボタンをクリックしてTGちゃんのWebインターフェースを開きます:"
        btn_text = "Webアプリを開く"
    else:
        text = "Нажмите на кнопку ниже, чтобы открыть веб-интерфейс ТГАЧ:"
        btn_text = "Открыть веб-приложение"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(text, reply_markup=keyboard)