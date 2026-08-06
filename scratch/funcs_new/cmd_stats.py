@dp.message(Command("stats", "activity", "heatmap"))
async def cmd_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return

    now = _time_module.time()
    user_id = message.from_user.id
    if not is_admin(user_id, board_id):
        last_used = _stats_cooldown_tracker.get((user_id, board_id), 0)
        if now - last_used < 3600:
            remaining = int(3600 - (now - last_used))
            min_left = remaining // 60
            sec_left = remaining % 60
            try:
                sent = await message.answer(f"⏳ Команда /stats на кулдауне. Ты можешь вызвать её через {min_left} мин {sec_left} сек.")
                spawn_task(delete_message_after_delay(sent, 10))
            except Exception:
                import traceback; traceback.print_exc()
            try: await message.delete()
            except Exception: pass
            return
        _stats_cooldown_tracker[(user_id, board_id)] = now

    cached = _stats_cache.get(board_id)
    if cached and now - cached['ts'] < _STATS_TTL:
        photos = cached['photos']
    else:
        await message.answer("📊 Генерирую статистику, подожди пару секунд...")
        import asyncio
        loop = asyncio.get_event_loop()
        photos = await loop.run_in_executor(None, _generate_stats_charts, board_id)
        _stats_cache[board_id] = {'ts': now, 'photos': photos}

    if not photos:
        await message.answer("Нет данных для этой борды.")
        return

    from aiogram.types import BufferedInputFile, InputMediaPhoto
    if len(photos) == 1:
        await message.answer_photo(
            BufferedInputFile(photos[0], filename='stats.png'),
            caption=f"📊 Статистика /{board_id}/ • обновляется раз в час"
        )
    else:
        media = [InputMediaPhoto(media=BufferedInputFile(p, filename=f'stats_{i}.png'))
                 for i, p in enumerate(photos)]
        media[0] = InputMediaPhoto(
            media=BufferedInputFile(photos[0], filename='stats_0.png'),
            caption=f"📊 Статистика /{board_id}/ • детальные ритмы (90д) и тепловые карты (180д) • обновляется раз в час"
        )
        await message.answer_media_group(media)

    try: await message.delete()
    except: pass