@dp.message(Command("nuke_pins"))
async def cmd_nuke_pins_surgical(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Радикальный сброс: unpin_all_chat_messages.
    Снимает ВООБЩЕ ВСЕ закрепы в личке с ботом у активных юзеров.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): 
        return
    if board_id in board_data:
        board_data[board_id]['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    users = await get_all_active_subscribers(board_id)
    if not users:
        await message.answer("🤷‍♂️ Юзеров не найдено.")
        return
    status_msg = await message.answer(
        f"☢️ <b>Запуск NUKE PINS (Total Wipe)</b>\n"
        f"Целей: {len(users)}\n"
        f"Метод: unpin_all_chat_messages (Снимает ВСЁ)\n"
        f"⏳ Поехали...",
        parse_mode="HTML"
    )
    stats = {'ok': 0, 'error': 0, 'block': 0}
    time.time()
    BATCH_SIZE = 20
    for i, chat_id in enumerate(users):
        if i % 100 == 0 and i > 0:
            try:
                await status_msg.edit_text(f"☢️ <b>Прогресс: {i} / {len(users)}</b>")
            except Exception: pass
        try:
            await message.bot.unpin_all_chat_messages(chat_id=chat_id)
            stats['ok'] += 1
        except TelegramForbiddenError:
            stats['block'] += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await message.bot.unpin_all_chat_messages(chat_id=chat_id)
                stats['ok'] += 1
            except Exception: stats['error'] += 1
        except Exception:
            stats['error'] += 1
        if i % BATCH_SIZE == 0:
            await asyncio.sleep(0.5)
    await status_msg.edit_text(
        f"✅ <b>TOTAL NUKE COMPLETE</b>\n"
        f"Всего: {len(users)}\n"
        f"✅ Снято у: {stats['ok']}\n"
        f"🚫 Блоков: {stats['block']}\n"
        f"❌ Ошибок: {stats['error']}"
    )