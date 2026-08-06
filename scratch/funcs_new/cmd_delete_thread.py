@dp.message(Command("deletethread", "delthread", "delete_thread"))
async def cmd_delete_thread(message: Message, board_id: str | None, stream: str = 'ru'):
    """
    Удаляет тред: помечает архивным в БД и вычищает из RAM.

    Команда объявлена в админском меню (setup_bot_commands), а рабочая
    delete_thread_atomic существовала без единого вызова — админ видел
    /deletethread в меню, но она ничего не делала. Здесь связаны обе части:
    archive_thread_in_db даёт персистентность (иначе тред вернулся бы после
    рестарта из таблицы Threads), delete_thread_atomic убирает его из памяти
    и возвращает читателей на главную.
    """
    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        try:
            await message.delete()
        except TelegramBadRequest:
            import traceback; traceback.print_exc()
        return

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    args = (message.text or message.caption or "").split()[1:]
    b_data = board_data[board_id]
    threads_data = get_threads_data(board_id)

    # Без аргумента удаляем тред, в котором админ сейчас находится.
    thread_id = args[0].lstrip('#') if args else None
    if not thread_id:
        location = b_data.get('user_state', {}).get(message.from_user.id, {}).get('location', 'main')
        if location and location != 'main':
            thread_id = str(location)

    if not thread_id:
        if lang == 'en':
            usage = "Usage: <code>/deletethread &lt;thread_id&gt;</code>, or run it inside the thread."
        elif lang == 'jp':
            usage = "使用法: <code>/deletethread &lt;thread_id&gt;</code>、またはスレッド内で実行。"
        else:
            usage = "Использование: <code>/deletethread &lt;id треда&gt;</code>, либо вызови внутри треда."
        await message.answer(usage, parse_mode="HTML")
        return

    thread_info = threads_data.get(thread_id)
    if not thread_info:
        if lang == 'en':
            not_found = f"❌ Thread <code>{escape_html(thread_id)}</code> not found on this board."
        elif lang == 'jp':
            not_found = f"❌ スレッド <code>{escape_html(thread_id)}</code> はこの板に存在しません。"
        else:
            not_found = f"❌ Тред <code>{escape_html(thread_id)}</code> не найден на этой доске."
        await message.answer(not_found, parse_mode="HTML")
        return

    title = thread_info.get('title') or thread_id
    posts_count = len(thread_info.get('posts', []))

    # Сначала персистентно: если упадём после очистки RAM, тред не должен
    # «воскреснуть» активным при следующем старте.
    try:
        from common.database import archive_thread_in_db
        await archive_thread_in_db(int(thread_id))
    except (TypeError, ValueError):
        print(f"⚠️ [/deletethread] thread_id '{thread_id}' не приводится к int, пропускаю запись в БД.")
    except Exception as e:
        print(f"⛔ [/deletethread] Не удалось архивировать тред #{thread_id} в БД: {e}")
        if lang == 'en':
            await message.answer("❌ DB error, thread left untouched.")
        else:
            await message.answer("❌ Ошибка БД, тред не тронут.")
        return

    await delete_thread_atomic(
        message.bot, board_id, thread_id,
        notify_users=True, initiator_id=message.from_user.id
    )

    if lang == 'en':
        done = f"🗑 Thread <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) deleted, {posts_count} posts purged."
    elif lang == 'jp':
        done = f"🗑 スレッド <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) を削除しました（{posts_count} レス）。"
    else:
        done = f"🗑 Тред <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) удалён, вычищено постов: {posts_count}."
    await message.answer(done, parse_mode="HTML")
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()