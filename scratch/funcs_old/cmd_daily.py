@dp.message(Command("daily", "bonus", "╨╡╨╢╨╡╨┤╨╜╨╡╨▓╨╜╨╛"))
async def cmd_daily(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    import time, json

    db = await get_pool()

    # active_items ╤à╤Ç╨░╨╜╨╕╤é daily_last_claim (unix timestamp)
    async with db.execute(
        "SELECT active_items, SUM(balance) FROM Users WHERE user_id = ? AND board_id = ?",
        (user_id, board_id)
    ) as c:
        row = await c.fetchone()

    ai_str  = (row[0] if row and row[0] else "{}") if row else "{}"
    balance = (row[1] if row and row[1] else 0) if row else 0
    try:
        ai = json.loads(ai_str)
    except:
        ai = {}

    now   = int(time.time())
    last  = ai.get("daily_last_claim", 0)
    cd    = 86400  # 24 hours
    since = now - last

    if since < cd:
        hours_left = (cd - since) // 3600
        mins_left  = ((cd - since) % 3600) // 60
        await message.answer(
            f"ΓÅ│ ╨ò╨╢╨╡╨┤╨╜╨╡╨▓╨╜╤ï╨╣ ╨▒╨╛╨╜╤â╤ü ╤â╨╢╨╡ ╨┐╨╛╨╗╤â╤ç╨╡╨╜.\n"
            f"╨í╨╗╨╡╨┤╤â╤Ä╤ë╨╕╨╣ ╨┤╨╛╤ü╤é╤â╨┐╨╡╨╜ ╤ç╨╡╤Ç╨╡╨╖: <b>{hours_left}╤ç {mins_left}╨╝╨╕╨╜</b>",
            parse_mode="HTML"
        )
        return

    # ╨æ╨╛╨╜╤â╤ü: ╨▒╨░╨╖╨╛╨▓╤ï╨╡ 75 RUB + streak ╨╝╨╜╨╛╨╢╨╕╤é╨╡╨╗╤î
    streak = ai.get("daily_streak", 0)
    if since < cd * 2:  # ╨╜╨╡ ╨┐╤Ç╨╛╨┐╤â╤ü╤é╨╕╨╗ ╨▓╤ç╨╡╤Ç╨░
        streak += 1
    else:
        streak = 1  # ╤ü╨▒╤Ç╨╛╤ü ╤ü╨╡╤Ç╨╕╨╕
    ai["daily_streak"]      = streak
    ai["daily_last_claim"]  = now

    bonus = 75
    streak_bonus = min(streak - 1, 7) * 10  # +10 RUB ╨╖╨░ ╨║╨░╨╢╨┤╤ï╨╣ ╨┤╨╡╨╜╤î ╤ü╨╡╤Ç╨╕╨╕, ╨╝╨░╨║╤ü +70
    total_bonus  = bonus + streak_bonus

    async with db_lock:
        await db.execute(
            "UPDATE Users SET balance = balance + ?, active_items = ? WHERE user_id = ? AND board_id = ?",
            (total_bonus, json.dumps(ai), user_id, board_id)
        )
        await db.commit()

    streak_msg = ""
    if streak > 1:
        streak_msg = f"\n≡ƒöÑ ╨í╨╡╤Ç╨╕╤Å: <b>{streak} ╨┤╨╜╨╡╨╣</b> ΓåÆ ╨▒╨╛╨╜╤â╤ü +{streak_bonus} RUB"

    await message.answer(
        f"Γ£à <b>╨ò╨╢╨╡╨┤╨╜╨╡╨▓╨╜╤ï╨╣ ╨▒╨╛╨╜╤â╤ü ╨┐╨╛╨╗╤â╤ç╨╡╨╜!</b>\n"
        f"╨¥╨░╤ç╨╕╤ü╨╗╨╡╨╜╨╛: <code>+{total_bonus} RUB</code>{streak_msg}\n"
        f"╨¥╨╛╨▓╤ï╨╣ ╨▒╨░╨╗╨░╨╜╤ü: <code>{int(balance + total_bonus)} RUB</code>\n\n"
        f"<i>╨ƒ╤Ç╨╕╤à╨╛╨┤╨╕ ╨╖╨░╨▓╤é╤Ç╨░ ΓÇö ╤ü╨╡╤Ç╨╕╤Å ╨┤╨░╤æ╤é ╨┤╨╛ +70 RUB ╤ü╨▓╨╡╤Ç╤à╤â.</i>",
        parse_mode="HTML"
    )
    try: await message.delete()
    except: pass