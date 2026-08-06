@dp.message(Command("generate"))
async def cmd_generate(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    COOLDOWN_SECONDS = 20
    # storage_lock убран: кулдаун лежит в board_data, взаимное исключение уже
    # даёт generate_locks[user_id]. Ответ юзеру — за пределами лока.
    remaining = 0
    async with generate_locks[user_id]:
        b_data = board_data[board_id]
        last_usage = b_data.get('last_generate_time', {}).get(user_id, 0)
        current_time = time.time()
        on_cooldown = current_time - last_usage < COOLDOWN_SECONDS
        if on_cooldown:
            remaining = int(COOLDOWN_SECONDS - (current_time - last_usage))
        else:
            b_data.setdefault('last_generate_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en': txt = f"⏳ Please wait {remaining} more seconds."
        elif lang == 'jp': txt = f"⏳ あと {remaining} 秒待ってください。"
        else: txt = f"⏳ Подожди еще {remaining} сек."
        try: await message.answer(txt)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    full_command_text = message.text or ""
    text_to_generate = ""
    command_prefix = "/generate "
    if full_command_text.startswith(command_prefix):
        text_to_generate = full_command_text[len(command_prefix):].strip()
    if not text_to_generate:
        if lang == 'en': usage = "Usage: <code>/generate &lt;prompt text&gt;</code>"
        elif lang == 'jp': usage = "使用法: <code>/generate &lt;prompt text&gt;</code>"
        else: usage = "⚠️ Напишите промпт. Пример: <code>/generate Нарисуй кота в космосе</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    working_msg = None
    try:
        wait_txt = "⏳ Generating..." if lang == 'en' else ("⏳ 生成中..." if lang == 'jp' else "⏳ Генерирую высер...")
        working_msg = await message.answer(wait_txt)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_to_generate)
        await working_msg.delete()
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="wipe.png")
            await message.answer_photo(photo)
        else:
            err_txt = "🚫 Failed to generate image." if lang == 'en' else ("🚫 画像の生成に失敗しました。" if lang == 'jp' else "🚫 Не удалось сгенерировать изображение.")
            await message.answer(err_txt)
    except Exception as e:
        print(f"❌ [generate] Error user {user_id}: {e}")
        try:
            if working_msg: await working_msg.delete()
            err_txt = "🚫 Unexpected error." if lang == 'en' else ("🚫 予期しないエラー。" if lang == 'jp' else "🚫 Произошла непредвиденная ошибка.")
            await message.answer(err_txt)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        try: await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError): pass