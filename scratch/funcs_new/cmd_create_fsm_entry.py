@dp.message(Command("create"))
async def cmd_create_fsm_entry(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает команду /create и служит точкой входа в FSM-сценарий создания треда.
    """
    if not board_id or board_id not in THREAD_BOARDS:
        return
    current_state = await state.get_state()
    lang = 'en' if board_id == 'int' else 'ru'
    if current_state is not None:
        cancel_phrases = thread_messages.get(lang, {}).get('create_cancelled', [])
        if lang == 'en':
            default_cancel_text = "You are already creating a thread. Use /cancel."
        elif lang == 'jp':
            default_cancel_text = "すでにスレッドを作成中です。/cancel を使用してください。"
        else:
            default_cancel_text = "Вы уже создаете тред. Используйте /cancel."
        text = random.choice(cancel_phrases) if cancel_phrases else default_cancel_text
        try:
            await message.answer(text)
            await message.delete()
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    command_args = (message.text or message.caption or "").split(maxsplit=1)
    if len(command_args) > 1 and command_args[1].strip():
        raw_html_text = message.html_text.split(maxsplit=1)[1]
        safe_html_text = sanitize_html(raw_html_text)
        await state.update_data(op_post_text=safe_html_text)
        await state.set_state(ThreadCreateStates.waiting_for_confirmation)
        if lang == 'en':
            confirmation_text = f"You want to create a thread with this opening post:\n\n---\n{safe_html_text}\n---\n\nCreate?"
            button_create, button_edit = "✅ Create Thread", "✏️ Edit Text"
        elif lang == 'jp':
            confirmation_text = f"以下の内容でスレッドを作成しますか？\n\n---\n{safe_html_text}\n---\n\n作成しますか？"
            button_create, button_edit = "✅ スレ作成", "✏️ 編集"
        else:
            confirmation_text = f"Вы хотите создать тред с таким ОП-постом:\n\n---\n{safe_html_text}\n---\n\nСоздаем?"
            button_create, button_edit = "✅ Создать тред", "✏️ Редактировать"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=button_create, callback_data="create_thread_confirm"),
                InlineKeyboardButton(text=button_edit, callback_data="create_thread_edit")
            ]
        ])
        await message.answer(confirmation_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await state.set_state(ThreadCreateStates.waiting_for_op_post)
        prompt_phrases = thread_messages.get(lang, {}).get('create_prompt_op_post', [])
        if lang == 'en':
            default_prompt = "Please send the text for your opening post."
        elif lang == 'jp':
            default_prompt = "スレッドの本文（OP）を送信してください。"
        else:
            default_prompt = "Отправьте текст для вашего ОП-поста."
        prompt_text = random.choice(prompt_phrases) if prompt_phrases else default_prompt
        await message.answer(prompt_text)
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()