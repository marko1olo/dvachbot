@dp.message(Command("daily", "bonus", "ежедневно"))
async def cmd_daily(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    import time, json

    db = await get_pool()

    # active_items хранит daily_last_claim (unix timestamp)
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
            f"⏳ Ежедневный бонус уже получен.\n"
            f"Следующий доступен через: <b>{hours_left}ч {mins_left}мин</b>",
            parse_mode="HTML"
        )
        return

    # Бонус: базовые 75 RUB + streak множитель
    streak = ai.get("daily_streak", 0)
    if since < cd * 2:  # не пропустил вчера
        streak += 1
    else:
        streak = 1  # сброс серии
    ai["daily_streak"]      = streak
    ai["daily_last_claim"]  = now

    bonus = 75
    streak_bonus = min(streak - 1, 7) * 10  # +10 RUB за каждый день серии, макс +70
    total_bonus  = bonus + streak_bonus

    async with db_lock:
        await db.execute(
            "UPDATE Users SET balance = balance + ?, active_items = ? WHERE user_id = ? AND board_id = ?",
            (total_bonus, json.dumps(ai), user_id, board_id)
        )
        await db.commit()

    streak_msg = ""
    if streak > 1:
        streak_msg = f"\n🔥 Серия: <b>{streak} дней</b> → бонус +{streak_bonus} RUB"

    await message.answer(
        f"✅ <b>Ежедневный бонус получен!</b>\n"
        f"Начислено: <code>+{total_bonus} RUB</code>{streak_msg}\n"
        f"Новый баланс: <code>{int(balance + total_bonus)} RUB</code>\n\n"
        f"<i>Приходи завтра — серия даёт до +70 RUB сверху.</i>",
        parse_mode="HTML"
    )
    try: await message.delete()
    except: pass