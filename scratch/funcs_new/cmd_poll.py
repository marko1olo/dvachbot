@dp.message(Command("poll", "opros"))
async def cmd_poll(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Точка входа в FSM для создания опроса.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now = time.time()
    if now - last_poll_creation_time[user_id] < 60:
        await message.delete()
        try:
            if lang == 'en':
                cooldown_msg = "⏳ Poll creation is allowed once per minute."
            elif lang == 'jp':
                cooldown_msg = "⏳ 投票の作成は1分に1回までです。"
            else:
                cooldown_msg = "⏳ Создавать опросы можно раз в минуту."
            sent = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent, 5))
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    full_text = message.text or message.caption or ""
    if message.reply_to_message and message.reply_to_message.media_group_id:
        await message.delete()
        if lang == 'en':
            error_text = "Attaching media groups to polls is not supported. Please reply to a single photo or video."
        elif lang == 'jp':
            error_text = "メディアグループを投票に添付することはできません。単一の画像または動画に返信してください。"
        else:
            error_text = "Прикрепление медиагрупп к опросам не поддерживается. Пожалуйста, ответьте на одно конкретное фото или видео."
        try:
            await message.answer(error_text)
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    command_part, *data_parts = full_text.split('|', 1)
    question_text = command_part.replace("/poll", "").replace("/opros", "").strip()
    options = [opt.strip() for opt in data_parts[0].split('|')] if data_parts else []
    if not question_text or len(options) < 2 or len(options) > 5:
        await message.delete()
        if lang == 'en':
            usage_text = (
                "<b>Invalid format!</b>\n"
                "Use the separator `|` between the question and each option.\n\n"
                "<u>Example:</u>\n"
                "<code>/poll Is Abu gay? | Yes | Of course | Absolutely</code>\n\n"
                "<i>(2 to 5 options)</i>"
            )
        elif lang == 'jp':
            usage_text = (
                "<b>フォーマットエラー！</b>\n"
                "質問と各選択肢の間に区切り文字 `|` を使用してください。\n\n"
                "<u>例:</u>\n"
                "<code>/poll Abuはホモ？ | はい | もちろん | 絶対に</code>\n\n"
                "<i>(選択肢は2〜5個)</i>"
            )
        else:
            usage_text = (
                "<b>Неверный формат!</b>\n"
                "Используйте разделитель `|` между вопросом и каждым вариантом ответа.\n\n"
                "<u>Пример:</u>\n"
                "<code>/poll Абу сосет хуй? | Да | Конечно | Безусловно</code>\n\n"
                "<i>(От 2 до 5 вариантов ответа)</i>"
            )
        try:
            await message.answer(usage_text, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            import traceback; traceback.print_exc()
        return
    attached_media = None
    reply_to_check = message
    if message.text and message.reply_to_message:
        reply_to_check = message.reply_to_message
    media_type = reply_to_check.content_type
    if media_type in ['photo', 'video', 'animation']:
        file_id_obj = getattr(reply_to_check, media_type)
        if isinstance(file_id_obj, list): file_id_obj = file_id_obj[-1]
        attached_media = {'type': media_type, 'file_id': file_id_obj.file_id}
    poll_fsm_data = {
        'question': question_text,
        'options': options,
        'attached_media': attached_media
    }
    await state.set_state(PollCreationStates.waiting_for_confirmation)
    await state.update_data(poll_data=poll_fsm_data)
    last_poll_creation_time[user_id] = now
    temp_poll_display_data = {
        'question': question_text,
        'options': options,
        'votes': {str(i): [] for i in range(len(options))}
    }
    preview_text = generate_poll_text_display(temp_poll_display_data)
    if lang == 'en':
        confirm_text = f"Here is how your poll will look:\n\n{preview_text}\n\nCreate?"
        btn_yes, btn_no = "✅ Yes, create", "❌ Cancel"
    elif lang == 'jp':
        confirm_text = f"投票は以下のようになります:\n\n{preview_text}\n\n作成しますか？"
        btn_yes, btn_no = "✅ 作成", "❌ キャンセル"
    else:
        confirm_text = f"Так будет выглядеть ваш опрос:\n\n{preview_text}\n\nСоздаем?"
        btn_yes, btn_no = "✅ Да, создать", "❌ Отмена"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=btn_yes, callback_data="poll_confirm_create"),
            InlineKeyboardButton(text=btn_no, callback_data="poll_cancel_create")
        ]
    ])
    try:
        if attached_media:
            media_type = attached_media['type']
            file_id = attached_media['file_id']
            caption = confirm_text
            if len(caption) > 1024: caption = caption[:1021] + "..."
            if media_type == 'photo':
                await message.answer_photo(photo=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'video':
                await message.answer_video(video=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'animation':
                await message.answer_animation(animation=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(confirm_text, reply_markup=keyboard, parse_mode="HTML")
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        print(f"Ошибка при отправке предпросмотра опроса: {e}")
        await state.clear()
        try:
            err_msg = "Failed to send preview." if lang == 'en' else ("プレビューの送信に失敗しました。" if lang == 'jp' else "Не удалось отправить предпросмотр.")
            await message.answer(err_msg)
            await message.delete()
        except Exception:
            import traceback; traceback.print_exc()