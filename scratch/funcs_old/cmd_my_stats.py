@dp.message(Command("my_stats", "mystats", "statsme", "╨┐╤Ç╨╛╤ä╨╕╨╗╤î"))
async def cmd_my_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "╨É╨╜╨╛╨╜╨╕╨╝"
    
    sent_msg = await message.answer("≡ƒôè ╨á╨╕╤ü╤â╤Ä ╤é╨▓╨╛╤Ä ╨╗╨╕╤ç╨╜╤â╤Ä ╨║╨░╤Ç╤é╤â ╨┤╨╡╨│╤Ç╨░╨┤╨░╤å╨╕╨╕...")
    
    from stats_generator import generate_user_stats_card
    from aiogram.types import BufferedInputFile
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        photo_buf, text_report = await loop.run_in_executor(None, generate_user_stats_card, user_id, board_id, username)
        if photo_buf:
            photo = BufferedInputFile(photo_buf.getvalue(), filename='mystats.png')
            await message.answer_photo(photo, caption=text_report, parse_mode="HTML")
        else:
            await message.answer(text_report, parse_mode="HTML")
    except Exception:
        await message.answer("ΓÜá∩╕Å ╨₧╤ê╨╕╨▒╨║╨░ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕ ╤ü╤é╨░╤é╨╕╤ü╤é╨╕╨║╨╕. ╨ƒ╨╛╨╢╨░╨╗╤â╨╣╤ü╤é╨░, ╨┐╨╛╨┐╤Ç╨╛╨▒╤â╨╣╤é╨╡ ╨┐╨╛╨╖╨╢╨╡.")

    try: await sent_msg.delete()
    except Exception: pass
    try: await message.delete()
    except Exception: pass