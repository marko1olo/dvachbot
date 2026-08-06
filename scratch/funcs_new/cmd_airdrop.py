@dp.message(Command("airdrop"))
async def cmd_airdrop(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    try: await message.delete()
    except Exception: pass
    
    async with db_lock:
        db = await get_pool()
        # Выбираем уникальных нищих (у кого СУММАРНЫЙ баланс по всем доскам <= 0)
        async with db.execute("SELECT user_id FROM Users GROUP BY user_id HAVING SUM(balance) <= 0") as cursor:
            users_to_fix_rows = await cursor.fetchall()
        
        users_to_fix = [r[0] for r in users_to_fix_rows]

        if users_to_fix:
            updates = [(random.randint(8, 15), uid) for uid in users_to_fix]
            # Начисляем только в ОДНУ (любую) существующую запись юзера, чтобы избежать дублей
            await db.executemany("""
                UPDATE Users SET balance = ?
                WHERE rowid = (SELECT rowid FROM Users WHERE user_id = ? LIMIT 1)
            """, updates)
            await db.commit()

    # Ответ юзеру за пределами db_lock: он сериализует весь доступ к базе.
    if not users_to_fix:
        await message.answer("🤷‍♂️ У всех и так есть бабки, эирдроп не нужен.")
        return
    await message.answer(f"🚀 <b>ЭИРДРОП ЗАВЕРШЕН!</b>\nНачислил бабки {len(users_to_fix)} нищим анонам.")