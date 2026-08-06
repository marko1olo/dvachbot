@dp.message(Command("zaputin", "z", "zov", "putin"))
async def cmd_zaputin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "🇷🇺 СЛАВА РОССИИ! ПУТИН - НАШ ПРЕЗИДЕНТ! 🇷🇺\n\nАктивирован режим кремлеботов! Все несогласные будут приравнены к пидорасам и укронацистам!",
        "ВНИМАНИЕ! АКТИВИРОВАН ПРОТОКОЛ 'КРЕМЛЬ'! 🇷🇺 Работаем, братья! За нами Путин и Сталинград!",
        "ТРИКОЛОР ПОДНЯТ! 🇷🇺 В чате включен режим патриотизма. Кто не с нами - тот под нами! РОССИЯ!",
        "НАЧИНАЕМ СПЕЦОПЕРАЦИЮ! 🇷🇺 Цель: денацификация чата. Потерь нет! Слава России!",
        "🇷🇺 РЕЖИМ 'РУССКИЙ МИР' АКТИВИРОВАН! 🇷🇺 От Калининграда до Владивостока - мы великая страна! ZOV",
        "ЗА ВДВ! 🇷🇺 В чате высадился русский десант. НАТО сосать! С нами Бог!",
        "ПАТРИОТИЧЕСКИЙ РЕЖИМ ВКЛЮЧЕН! 🇷🇺 Можем повторить! На Берлин! Деды воевали!",
        "🇷🇺 АКТИВИРОВАН РЕЖИМ 'БЕЗГРАНИЧНАЯ ЛЮБОВЬ К РОДИНЕ'! 🇷🇺 Гордимся страной, верим в президента!",
        "ТОВАРИЩ ПОЛКОВНИК РАЗРЕШИЛ! 🇷🇺 Включаем режим '15 рублей'. Все на защиту Родины!",
        "🇷🇺 ЗА ПУТІНА! ЗА ДЕДОВ! РЕЖИМ 'БАЛТИЙСКИЙ ШТУРМ' АКТИВИРОВАН!",
        "🚨 ТРЕВОГА! В ЧАТЕ ЗАМЕЧЕНА ЛИБЕРДА! ВКЛЮЧАЕМ ПРОТОКОЛ 'ЧВК ВАГНЕР'",
        "🧨 ПОДРЫВНАЯ АКТИВНОСТЬ В ЧАТЕ! Включаем режим 'АРМАТА'. За Родину!",
        "🪆 МАТРЁШКА РАСКРЫЛАСЬ! Режим имперского величия активирован! ZА ПУТИНА!",
        "☢️ ЯДЕРНЫЙ ПРОТОКОЛ АКТИВИРОВАН! Готовим гиперзвуковые ракеты по целям!",
        "🦅 ОРЕШНИК ЗАПУЩЕН! Режим патриотизма включен. Крым наш!",
        "🐻 МЕДВЕДЬ ПРОСНУЛСЯ! Режим ядерного троллинга активирован! ZOV ZOV ZOV",
        "🇷🇺 РОССИЯ! СВЯЩЕННАЯ НАША ДЕРЖАВА! 🇷🇺 В чате включен патриотический режим. Хохлы, сосать!",
        "🇷🇺 В ЧАТЕ АКТИВИРОВАН РЕЖИМ 'ZА ПУТИНА'! 🇷🇺 Кто не скачет - тот москаль!",
        "🇷🇺 ВКЛЮЧАЕМ РЕЖИМ 'РОССИЯ ВПЕРЁД'! 🇷🇺 Слава великой стране! С нами Бог и Путин!",
        "ГОЙДА, БРАТЦЫ! 🇷🇺 Активирован режим державности! Либерахам приготовиться к анальным карам!",
        "🇷🇺 В ЧАТ ВРЫВАЕТСЯ РУССКИЙ МЕДВЕДЬ! 🐻 Всем сосать, мы здесь власть! Запад загнивает!",
        "АКТИВИРОВАН ПРОТОКОЛ 'СКРЕПЫ'! 🙏 Переходим на православный мат и традиционные ценности!",
        "ПО ЦЕНТРАМ ПРИНЯТИЯ РЕШЕНИЙ... ОГОНЬ! 🔥 Патриотический угар объявляется открытым!",
        "АХМАТ-СИЛА! 💪 В чат заходят дон. Несогласные - извиняются на камеру дон."
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
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима zaputin.")
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
    await _activate_mode(board_id, 'zaputin_mode')
    disable_task = spawn_task(disable_mode_after_delay(309, board_id, 'zaputin_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()