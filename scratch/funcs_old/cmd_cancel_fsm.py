@dp.message(Command("cancel"))
async def cmd_cancel_fsm(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    ╨₧╤é╨╝╨╡╨╜╤Å╨╡╤é ╨╗╤Ä╨▒╨╛╨╡ FSM ╤ü╨╛╤ü╤é╨╛╤Å╨╜╨╕╨╡, ╨▓ ╨║╨╛╤é╨╛╤Ç╨╛╨╝ ╨╜╨░╤à╨╛╨┤╨╕╤é╤ü╤Å ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î.
    """
    current_state = await state.get_state()
    if current_state is None:
        try:
            await message.delete()
        except TelegramBadRequest:
            import traceback; traceback.print_exc()
        return
    await state.clear()
    if board_id:
        lang = 'en' if board_id == 'int' else 'ru'
        response_text = random.choice(thread_messages[lang]['create_cancelled'])
        await message.answer(response_text)
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()