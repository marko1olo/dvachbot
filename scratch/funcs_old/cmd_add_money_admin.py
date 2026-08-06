@dp.message(Command("addmoney"))
async def cmd_add_money_admin(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    try: await message.delete()
    except Exception: pass
    
    args = (message.text or message.caption or "").split()
    if len(args) < 3:
        await message.answer("╨«╨╖╨░╨╣: /addmoney &lt;ID&gt; &lt;╤ü╤â╨╝╨╝╨░&gt;")
        return
        
    try:
        target_id, amount = int(args[1]), int(args[2])
        async with db_lock:
            db = await get_pool()
            # 1. ╨ô╨░╤Ç╨░╨╜╤é╨╕╤Ç╤â╨╡╨╝, ╤ç╤é╨╛ ╨╖╨░╨┐╨╕╤ü╤î ╨╜╨░ ╨ó╨ò╨Ü╨ú╨⌐╨ò╨Ö ╨┤╨╛╤ü╨║╨╡ ╤ü╤â╤ë╨╡╤ü╤é╨▓╤â╨╡╤é
            await db.execute("INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)", (target_id, board_id))
            # 2. ╨¥╨░╤ç╨╕╤ü╨╗╤Å╨╡╨╝ ╨┤╨╡╨╜╤î╨│╨╕ ╨ó╨₧╨¢╨¼╨Ü╨₧ ╨▓ ╤ì╤é╤â ╨╖╨░╨┐╨╕╤ü╤î (╨╕╨╖╨▒╨╡╨│╨░╨╡╨╝ ╤â╨╝╨╜╨╛╨╢╨╡╨╜╨╕╤Å)
            await db.execute("UPDATE Users SET balance = balance + ? WHERE user_id = ? AND board_id = ?", (amount, target_id, board_id))
            await db.commit()
        
        await message.answer(f"Γ£à ╨¥╨░╤Ç╨╕╤ü╨╛╨▓╨░╨╜╨╛ {amount} ╤Ç╤â╨▒╨╗╨╡╨╣ ╨┤╨╗╤Å ╤Ä╨╖╨╡╤Ç╨░ {target_id}. ╨æ╨░╨╗╨░╨╜╤ü ╨┐╨╛╨┐╨╛╨╗╨╜╨╡╨╜ (╨║╨╛╤Ç╨╖╨╕╨╜╨░ /{board_id}/).")
        try:
            await message.bot.send_message(target_id, f"≡ƒÄü <b>╨É╨┤╨╝╨╕╨╜╨╕╤ü╤é╤Ç╨░╤å╨╕╤Å ╨╜╨░╤ç╨╕╤ü╨╗╨╕╨╗╨░ ╨▓╨░╨╝ ╨▒╨╛╨╜╤â╤ü: {amount} RUB! ╨Ü╨╛╤ê╨╡╨╗╨╡╨║ - /wallet </b>", parse_mode="HTML")
        except Exception:
            import traceback; traceback.print_exc()
    except Exception as e:
        await message.answer(f"╨₧╤ê╨╕╨▒╨║╨░: {e}", parse_mode=None)