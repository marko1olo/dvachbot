@dp.message(Command("stats", "activity", "heatmap"))
async def cmd_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    global _stats_cache

    now = _time_module.time()
    user_id = message.from_user.id
    if not is_admin(user_id, board_id):
        last_used = _stats_cooldown_tracker.get((user_id, board_id), 0)
        if now - last_used < 3600:
            remaining = int(3600 - (now - last_used))
            min_left = remaining // 60
            sec_left = remaining % 60
            try:
                sent = await message.answer(f"ΓÅ│ ╨Ü╨╛╨╝╨░╨╜╨┤╨░ /stats ╨╜╨░ ╨║╤â╨╗╨┤╨░╤â╨╜╨╡. ╨ó╤ï ╨╝╨╛╨╢╨╡╤ê╤î ╨▓╤ï╨╖╨▓╨░╤é╤î ╨╡╤æ ╤ç╨╡╤Ç╨╡╨╖ {min_left} ╨╝╨╕╨╜ {sec_left} ╤ü╨╡╨║.")
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
        await message.answer("≡ƒôè ╨ô╨╡╨╜╨╡╤Ç╨╕╤Ç╤â╤Ä ╤ü╤é╨░╤é╨╕╤ü╤é╨╕╨║╤â, ╨┐╨╛╨┤╨╛╨╢╨┤╨╕ ╨┐╨░╤Ç╤â ╤ü╨╡╨║╤â╨╜╨┤...")
        import asyncio
        loop = asyncio.get_event_loop()
        photos = await loop.run_in_executor(None, _generate_stats_charts, board_id)
        _stats_cache[board_id] = {'ts': now, 'photos': photos}

    if not photos:
        await message.answer("╨¥╨╡╤é ╨┤╨░╨╜╨╜╤ï╤à ╨┤╨╗╤Å ╤ì╤é╨╛╨╣ ╨▒╨╛╤Ç╨┤╤ï.")
        return

    from aiogram.types import BufferedInputFile, InputMediaPhoto
    if len(photos) == 1:
        await message.answer_photo(
            BufferedInputFile(photos[0], filename='stats.png'),
            caption=f"≡ƒôè ╨í╤é╨░╤é╨╕╤ü╤é╨╕╨║╨░ /{board_id}/ ΓÇó ╨╛╨▒╨╜╨╛╨▓╨╗╤Å╨╡╤é╤ü╤Å ╤Ç╨░╨╖ ╨▓ ╤ç╨░╤ü"
        )
    else:
        media = [InputMediaPhoto(media=BufferedInputFile(p, filename=f'stats_{i}.png'))
                 for i, p in enumerate(photos)]
        media[0] = InputMediaPhoto(
            media=BufferedInputFile(photos[0], filename='stats_0.png'),
            caption=f"≡ƒôè ╨í╤é╨░╤é╨╕╤ü╤é╨╕╨║╨░ /{board_id}/ ΓÇó ╨┤╨╡╤é╨░╨╗╤î╨╜╤ï╨╡ ╤Ç╨╕╤é╨╝╤ï (90╨┤) ╨╕ ╤é╨╡╨┐╨╗╨╛╨▓╤ï╨╡ ╨║╨░╤Ç╤é╤ï (180╨┤) ΓÇó ╨╛╨▒╨╜╨╛╨▓╨╗╤Å╨╡╤é╤ü╤Å ╤Ç╨░╨╖ ╨▓ ╤ç╨░╤ü"
        )
        await message.answer_media_group(media)

    try: await message.delete()
    except: pass