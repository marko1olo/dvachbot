@dp.message(Command("slavaukraine", "slava_ukraine", "ukraine", "ukraina", "hohol"))
async def cmd_slavaukraine(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except TelegramBadRequest as e:
            if "message to delete not found" not in e.message.lower():
                print(f"Не удалось удалить сообщение {message.message_id} в cmd_slavaukraine (INT): {e}")
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "УВАГА! АКТИВОВАНО УКРАЇНСЬКИЙ РЕЖИМ!\n\n💙💛 СЛАВА УКРАЇНІ! 💛💙\nГЕРОЯМ СЛАВА!\n\nХто не скаже 'Путін хуйло' - той москаль і підар!",
        "УКРАЇНСЬКИЙ РЕЖИМ УВІМКНЕНО! 🇺🇦 Всі москалі будуть денацифіковані та демілітаризовані. Смерть ворогам!",
        "УВАГА! В чаті оголошено контрнаступ! 🚜 СЛАВА НАЦІЇ! ПИЗДЕЦЬ РОСІЙСЬКІЙ ФЕДЕРАЦІЇ!",
        "💙💛 Переходимо на солов'їну! Хто не скаче, той москаль! СЛАВА ЗСУ!",
        "АКТИВОВАНО РЕЖИМ 'БАНДЕРОМОБІЛЬ'! 🇺🇦 Завантажуємо Javelin... Ціль: Кремль.",
        "УКРАЇНСЬКИЙ ПОРЯДОК НАВЕДЕНО! 🫡 Готуйтеся до повного розгрому русні. Путін - хуйло!",
        "ТЕРМІНОВО! В чаті виявлено русню! Активовано протокол 'АЗОВ'. 🇺🇦 Слава Україні!",
        "Режим 'ПРИВИД КИЄВА' активовано! ✈️ Вилітаємо на бойове завдання. Рускій воєнний корабль, іді нахуй!",
        "Наступні 5 хвилин в чаті - лише українська мова! 💙💛 За непокору - розстріл нахуй. Героям Слава!",
        "💙💛 ВАХТА НА ЗАВАЛІ! Вмикаємо режим 'КІБЕРПОЛК АЗОВ'! СМЕРТЬ РУСНІ!",
        "БАНДЕРОВЕЦЬ В ЧАТІ! 💛💙 Переходимо на український тролінг. Путін - хуйло!",
        "💣 ХЕРСОНЬ НАШ! Режим 'ДРОН-КАМИКАДЗЕ' активирован! СЛАВА ЗСУ!",
        "🔥 ДЕМОНІЧНИЙ РЕЖИМ ВВІМКНЕНО! Запалюємо русскій корабль! ІДИ НАХУЙ!",
        "🪖 ТЕРОБОРОНЕЦЬ У ЧАТІ! Переходимо на український тролінг. Путін - хуйло!",
        "⚔️ ШАХТАРСЬКИЙ НАСТУП! Режим 'СЛАВА НАЦІЇ' активовано! ГЕРОЯМ СЛАВА!",
        "🔱 ТЕРМІНОВО! У ЧАТІ З'ЯВИВСЯ ХАСК! Режим 'СЛАВА НАЦІЇ' активовано!",
        "УВАГА! Територія цього чату оголошується суверенною територією України! 🇺🇦 СЛАВА УКРАЇНІ!"
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
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима slavaukraine.")
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
    await _activate_mode(board_id, 'slavaukraine_mode')
    disable_task = spawn_task(disable_mode_after_delay(310, board_id, 'slavaukraine_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest as e:
        if "message to delete not found" not in e.message.lower():
            print(f"Не удалось удалить сообщение {message.message_id} в cmd_slavaukraine: {e}")