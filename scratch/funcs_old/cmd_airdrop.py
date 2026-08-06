@dp.message(Command("airdrop"))
async def cmd_airdrop(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    try: await message.delete()
    except Exception: pass
    
    async with db_lock:
        db = await get_pool()
        # ╨Æ╤ï╨▒╨╕╤Ç╨░╨╡╨╝ ╤â╨╜╨╕╨║╨░╨╗╤î╨╜╤ï╤à ╨╜╨╕╤ë╨╕╤à (╤â ╨║╨╛╨│╨╛ ╨í╨ú╨£╨£╨É╨á╨¥╨½╨Ö ╨▒╨░╨╗╨░╨╜╤ü ╨┐╨╛ ╨▓╤ü╨╡╨╝ ╨┤╨╛╤ü╨║╨░╨╝ <= 0)
        async with db.execute("SELECT user_id FROM Users GROUP BY user_id HAVING SUM(balance) <= 0") as cursor:
            users_to_fix_rows = await cursor.fetchall()
        
        users_to_fix = [r[0] for r in users_to_fix_rows]

        if users_to_fix:
            updates = [(random.randint(8, 15), uid) for uid in users_to_fix]
            # ╨¥╨░╤ç╨╕╤ü╨╗╤Å╨╡╨╝ ╤é╨╛╨╗╤î╨║╨╛ ╨▓ ╨₧╨ö╨¥╨ú (╨╗╤Ä╨▒╤â╤Ä) ╤ü╤â╤ë╨╡╤ü╤é╨▓╤â╤Ä╤ë╤â╤Ä ╨╖╨░╨┐╨╕╤ü╤î ╤Ä╨╖╨╡╤Ç╨░, ╤ç╤é╨╛╨▒╤ï ╨╕╨╖╨▒╨╡╨╢╨░╤é╤î ╨┤╤â╨▒╨╗╨╡╨╣
            await db.executemany("""
                UPDATE Users SET balance = ?
                WHERE rowid = (SELECT rowid FROM Users WHERE user_id = ? LIMIT 1)
            """, updates)
            await db.commit()

    # ╨₧╤é╨▓╨╡╤é ╤Ä╨╖╨╡╤Ç╤â ╨╖╨░ ╨┐╤Ç╨╡╨┤╨╡╨╗╨░╨╝╨╕ db_lock: ╨╛╨╜ ╤ü╨╡╤Ç╨╕╨░╨╗╨╕╨╖╤â╨╡╤é ╨▓╨╡╤ü╤î ╨┤╨╛╤ü╤é╤â╨┐ ╨║ ╨▒╨░╨╖╨╡.
    if not users_to_fix:
        await message.answer("≡ƒñ╖ΓÇìΓÖé∩╕Å ╨ú ╨▓╤ü╨╡╤à ╨╕ ╤é╨░╨║ ╨╡╤ü╤é╤î ╨▒╨░╨▒╨║╨╕, ╤ì╨╕╤Ç╨┤╤Ç╨╛╨┐ ╨╜╨╡ ╨╜╤â╨╢╨╡╨╜.")
        return
    await message.answer(f"≡ƒÜÇ <b>╨¡╨ÿ╨á╨ö╨á╨₧╨ƒ ╨ù╨É╨Æ╨ò╨á╨¿╨ò╨¥!</b>\n╨¥╨░╤ç╨╕╤ü╨╗╨╕╨╗ ╨▒╨░╨▒╨║╨╕ {len(users_to_fix)} ╨╜╨╕╤ë╨╕╨╝ ╨░╨╜╨╛╨╜╨░╨╝.")