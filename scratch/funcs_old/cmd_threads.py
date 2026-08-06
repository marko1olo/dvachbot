@dp.message(Command("threads"))
async def cmd_threads(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or board_id not in THREAD_BOARDS:
        await message.delete()
        return
    user_id = message.from_user.id
    now = time.time()
    if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
        await message.delete()
        return
    user_last_thread_action[user_id] = now
    text, keyboard = await generate_threads_page(board_id, user_id, page=0, stream=stream)
    if text:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await message.delete()