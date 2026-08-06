@dp.message(Command("help"))
async def cmd_help(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    text_map = b_data.get('start_message_map', {})
    start_text = text_map.get(lang, b_data.get('start_message_text', "Help info missing."))
    await _send_thread_info_if_applicable(message, board_id)
    await message.answer(start_text, reply_markup=get_help_keyboard("main", board_id, stream), parse_mode="HTML", disable_web_page_preview=True)
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()