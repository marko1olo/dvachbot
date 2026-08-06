@dp.message(Command("top", "leaderboard", "топ"))
async def cmd_top(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return

    db = await get_pool()

    # Топ по балансу — показываем только anon_id (пост-номер паспорта), не username
    async with db.execute(
        """SELECT user_id, SUM(balance) as bal, MAX(custom_prefix) as prefix
           FROM Users WHERE board_id = ?
           GROUP BY user_id HAVING bal > 0
           ORDER BY bal DESC LIMIT 15""",
        (board_id,)
    ) as c:
        rows = await c.fetchall()

    if not rows:
        await message.answer("Пока никто не накопил ничего.")
        return

    medals = ["🥇", "🥈", "🥉"]
    caller_id = message.from_user.id

    lines = [f"💰 <b>Топ богачей /{board_id}/</b>\n{'—'*20}"]
    for i, (uid, bal, prefix) in enumerate(rows):
        medal  = medals[i] if i < 3 else f"<b>{i+1}.</b>"
        # Паспортный номер = последние 4 цифры user_id (детерминировано, не раскрывает личность)
        anon_tag = f"Анон-{uid % 10000:04d}"
        pfx = f" {prefix}" if prefix else ""
        you = " ← ты" if uid == caller_id else ""
        lines.append(f"{medal} {anon_tag}{pfx} — <code>{int(bal)} RUB</code>{you}")

    lines.append(f"\n<i>Имена не раскрываются. Заработай в реакциях или /shop.</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")
    try: await message.delete()
    except: pass