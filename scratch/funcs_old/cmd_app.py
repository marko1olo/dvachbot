@dp.message(Command("app"))
async def cmd_app(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨₧╤é╨┐╤Ç╨░╨▓╨╗╤Å╨╡╤é ╨║╨╜╨╛╨┐╨║╤â ╨┤╨╗╤Å ╨╛╤é╨║╤Ç╤ï╤é╨╕╤Å ╨▓╨╡╨▒-╨┐╤Ç╨╕╨╗╨╛╨╢╨╡╨╜╨╕╤Å (╤ü╨░╨╣╤é╨░).
    """
    if not board_id: return
    WEBAPP_URL = "https://tgach.top" 
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "Click the button below to open the TGACH web interface:"
        btn_text = "Open Web App"
    elif lang == 'jp':
        text = "Σ╕ïπü«πâ£πé┐πâ│πéÆπé»πâ¬πââπé»πüùπüªTGπüíπéâπéôπü«Webπéñπâ│πé┐πâ╝πâòπéºπâ╝πé╣πéÆΘûïπüìπü╛πüÖ:"
        btn_text = "Webπéóπâùπâ¬πéÆΘûïπüÅ"
    else:
        text = "╨¥╨░╨╢╨╝╨╕╤é╨╡ ╨╜╨░ ╨║╨╜╨╛╨┐╨║╤â ╨╜╨╕╨╢╨╡, ╤ç╤é╨╛╨▒╤ï ╨╛╤é╨║╤Ç╤ï╤é╤î ╨▓╨╡╨▒-╨╕╨╜╤é╨╡╤Ç╤ä╨╡╨╣╤ü ╨ó╨ô╨É╨º:"
        btn_text = "╨₧╤é╨║╤Ç╤ï╤é╤î ╨▓╨╡╨▒-╨┐╤Ç╨╕╨╗╨╛╨╢╨╡╨╜╨╕╨╡"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(text, reply_markup=keyboard)