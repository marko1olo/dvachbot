@dp.message(Command("top", "leaderboard", "╤é╨╛╨┐"))
async def cmd_top(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return

    db = await get_pool()

    # ╨ó╨╛╨┐ ╨┐╨╛ ╨▒╨░╨╗╨░╨╜╤ü╤â ΓÇö ╨┐╨╛╨║╨░╨╖╤ï╨▓╨░╨╡╨╝ ╤é╨╛╨╗╤î╨║╨╛ anon_id (╨┐╨╛╤ü╤é-╨╜╨╛╨╝╨╡╤Ç ╨┐╨░╤ü╨┐╨╛╤Ç╤é╨░), ╨╜╨╡ username
    async with db.execute(
        """SELECT user_id, SUM(balance) as bal, MAX(custom_prefix) as prefix
           FROM Users WHERE board_id = ?
           GROUP BY user_id HAVING bal > 0
           ORDER BY bal DESC LIMIT 15""",
        (board_id,)
    ) as c:
        rows = await c.fetchall()

    if not rows:
        await message.answer("╨ƒ╨╛╨║╨░ ╨╜╨╕╨║╤é╨╛ ╨╜╨╡ ╨╜╨░╨║╨╛╨┐╨╕╨╗ ╨╜╨╕╤ç╨╡╨│╨╛.")
        return

    medals = ["≡ƒÑç", "≡ƒÑê", "≡ƒÑë"]
    caller_id = message.from_user.id

    lines = [f"≡ƒÆ░ <b>╨ó╨╛╨┐ ╨▒╨╛╨│╨░╤ç╨╡╨╣ /{board_id}/</b>\n{'ΓÇö'*20}"]
    for i, (uid, bal, prefix) in enumerate(rows):
        medal  = medals[i] if i < 3 else f"<b>{i+1}.</b>"
        # ╨ƒ╨░╤ü╨┐╨╛╤Ç╤é╨╜╤ï╨╣ ╨╜╨╛╨╝╨╡╤Ç = ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ 4 ╤å╨╕╤ä╤Ç╤ï user_id (╨┤╨╡╤é╨╡╤Ç╨╝╨╕╨╜╨╕╤Ç╨╛╨▓╨░╨╜╨╛, ╨╜╨╡ ╤Ç╨░╤ü╨║╤Ç╤ï╨▓╨░╨╡╤é ╨╗╨╕╤ç╨╜╨╛╤ü╤é╤î)
        anon_tag = f"╨É╨╜╨╛╨╜-{uid % 10000:04d}"
        pfx = f" {prefix}" if prefix else ""
        you = " ΓåÉ ╤é╤ï" if uid == caller_id else ""
        lines.append(f"{medal} {anon_tag}{pfx} ΓÇö <code>{int(bal)} RUB</code>{you}")

    lines.append(f"\n<i>╨ÿ╨╝╨╡╨╜╨░ ╨╜╨╡ ╤Ç╨░╤ü╨║╤Ç╤ï╨▓╨░╤Ä╤é╤ü╤Å. ╨ù╨░╤Ç╨░╨▒╨╛╤é╨░╨╣ ╨▓ ╤Ç╨╡╨░╨║╤å╨╕╤Å╤à ╨╕╨╗╨╕ /shop.</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")
    try: await message.delete()
    except: pass