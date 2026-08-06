@dp.message(Command("roll", "roulette", "ruletka", "rulet", "fortune", "фортуна"))
async def cmd_roll(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: 
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    # storage_lock здесь был ложной зависимостью: он защищает messages_storage /
    # post_to_messages / message_to_post, а кулдаун лежит в board_data, к
    # которому 111 из 146 обращений в этом файле идут вообще без него.
    # Взаимное исключение уже даёт roulette_lock. Внутри лока нет ни одного
    # await, поэтому проверка и запись времени атомарны; ответ юзеру ушёл
    # наружу, чтобы flood-wait не держал лок рулетки.
    async with roulette_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_roll_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < 60
        if not on_cooldown:
            b_data.setdefault('last_roll_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en': cooldown_msg = "⏳ Roulette is on cooldown!"
        elif lang == 'jp': cooldown_msg = "⏳ ルーレットはクールダウン中です！"
        else: cooldown_msg = random.choice(ROULETTE_COOLDOWN_PHRASES)
        try:
            sent_msg = await message.answer(cooldown_msg)
            spawn_task(delete_message_after_delay(sent_msg, 5))
        except (TelegramBadRequest, TelegramForbiddenError): pass
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not ROULETTE_EVENTS:
        if lang == 'en': error_text = "Roulette data is not loaded."
        elif lang == 'jp': error_text = "ルーレットデータが読み込まれていません。"
        else: error_text = "Данные рулетки не загружены."
        try: await message.answer(error_text)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    working_msg = None
    try:
        if lang == 'en': work_txt = "⏳ Spinning the wheel..."
        elif lang == 'jp': work_txt = "⏳ ルーレットを回しています..."
        else: work_txt = "⏳ Кручу барабан..."
        working_msg = await message.answer(work_txt)
        event = get_random_event(ROULETTE_EVENTS)
        if not event:
            raise ValueError("Failed to get random event.")
        event_id = event.get('id', '???')
        event_desc_plain = event.get('description', '...')
        text_for_image = f"[{event_id}]\n\n{event_desc_plain}"
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_for_image)
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="roll_result.png")
            caption_header = random.choice(ROULETTE_RESULT_PHRASES) # Пока оставим общие
            await message.answer_photo(photo, caption=caption_header)
        else:
            print(f"⚠️ [cmd_roll] Image generation failed. Sending text.")
            result_header = random.choice(ROULETTE_RESULT_PHRASES)
            event_desc_html = escape_html(event_desc_plain)
            result_text = f"{result_header}\n\n<b>[{event_id}]</b> {event_desc_html}"
            await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Ошибка в cmd_roll: {e}")
        if lang == 'en': err = "Error during roulette spin."
        elif lang == 'jp': err = "ルーレット中にエラーが発生しました。"
        else: err = "Произошла ошибка при выполнении ролла."
        try: await message.answer(err)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass
        try: await message.delete()
        except TelegramBadRequest: pass