@dp.message(Command("suka_blyat"))
async def cmd_suka_blyat(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    if (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC)) or \
       (user_id in b_data['mutes'] and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            import traceback; traceback.print_exc()
        return
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "💢💢💢 Активирован режим СУКА БЛЯТЬ! 💢💢💢\n\nВсех нахуй разъебало!",
        "БЛЯЯЯЯЯТЬ! 💥 РЕЖИМ АГРЕССИИ ВКЛЮЧЕН! ПИЗДА ВСЕМУ!",
        "ВЫ ЧЕ, ОХУЕЛИ?! 💢 Включаю режим 'сука блять', готовьтесь, пидорасы!",
        "ЗАЕБАЛО ВСЁ НАХУЙ! 💥 Переходим в режим тотальной ненависти. СУКА!",
        "💥 ТРЕЩИНА НАХУЙ! Режим 'ХУЙ ПОЛЕЗЕШЬ' активирован!",
        "🧨 ПИЗДЕЦ НАСТУПИЛ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ! ААА БЛЯЯЯТЬ!",
        "🔞 ЁБАНЫЙ В РОТ! Режим агрессивного аутизма включен! СУКА!",
        "🤬 ПИЗДОС НА МАКАРОС! Режим 'БАТЯ В ЯРОСТИ'! ВСЕМ ПИЗДАНУТЬСЯ!",
        "А НУ БЛЯТЬ СУКИ СЮДА ПОДОШЛИ! 💢 Режим 'бати в ярости' активирован!",
        "СУКАААААА! 💥 Пиздец, как меня все бесит! Включаю протокол 'РАЗЪЕБАТЬ'.",
        "ЩА БУДЕТ МЯСО! 🔪🔪🔪 Режим 'сука блять' активирован. Нытикам здесь не место!",
        "ЕБАНЫЙ ТЫ НАХУЙ! 💢💢💢 С этого момента говорим только матом. Поняли, уебаны?",
        "ТАК, БЛЯТЬ! 💥 Слушать мою команду! Режим 'СУКА БЛЯТЬ' активен. Вольно, бляди!",
        "💢 ДА ТЫ ЁБНУТЫЙ? РЕЖИМ 'ХУЙ ПОЛЕЗЕШЬ' АКТИВИРОВАН!",
        "🐗 СВИНОПАС ВЫШЕЛ НА ТРОПУ ВОЙНЫ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ!",
        "🔞 ПИЗДЕЦ НАСТУПИЛ! ВСЕМ ПИЗДАНУТЬСЯ В УГОЛ! АААА БЛЯЯЯТЬ!",
        "ПОШЛИ НАХУЙ! 💥 ВСЕ ПОШЛИ НАХУЙ! Режим ярости включен, суки!",
        "🤬 СУКА БЛЯТЬ! РЕЖИМ 'БАТЯ В ЯРОСТИ' АКТИВИРОВАН! ВСЕМ ПИЗДАНУТЬСЯ!",
        "ЩА БУДЕТ МЯСО! 🔪 Режим 'сука блять' активирован. Нытикам здесь не место!"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима suka_blyat.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'suka_blyat_mode')
    disable_task = spawn_task(disable_mode_after_delay(303, board_id, 'suka_blyat_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()