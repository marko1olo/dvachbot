@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Открывает быстрое меню по команде /menu.
    """
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "👇 <b>Quick Menu:</b>"
    elif lang == 'jp':
        text = "👇 <b>クイックメニュー:</b>"
    else:
        text = "👇 <b>Быстрое меню:</b>"
    await message.answer(
        text, 
        reply_markup=get_quick_menu_keyboard(board_id, stream=stream), 
        parse_mode="HTML"
    )
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()