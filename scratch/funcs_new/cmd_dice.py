@dp.message(Command("dice", "roll100", "d100"))
async def cmd_dice(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    result = random.randint(1, 100)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        roll_text = f"🎲 Rolled: {result}"
    elif lang == 'jp':
        roll_text = f"🎲 出目: {result}"
    else:
        roll_text = f"🎲 Нароллил: {result}"
    try:
        await message.answer(roll_text)
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        import traceback; traceback.print_exc()