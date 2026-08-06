@dp.message(Command("global_top", "gtop"))
async def cmd_global_top(message: types.Message, board_id: str | None, stream: str = 'ru'):
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    wait_txt = "≡ƒÅå ╨É╨╜╨░╨╗╨╕╨╖╨╕╤Ç╤â╤Ä ╨▒╨░╨╖╤â ╨┤╨░╨╜╨╜╤ï╤à ╨┤╨╗╤Å ╨┐╨╛╤ü╤é╤Ç╨╛╨╡╨╜╨╕╤Å ╤é╨╛╨┐╨╛╨▓..." if lang != 'en' else "≡ƒÅå Computing leaderboards..."
    wait_msg = await message.answer(wait_txt)
    
    top_posters = []
    top_rich = []
    
    try:
        async with db_lock:
            db = await get_pool()
            # Top 10 by posts
            q_posts = "SELECT author_id, COUNT(*) as cnt FROM Posts GROUP BY author_id ORDER BY cnt DESC LIMIT 10"
            async with db.execute(q_posts) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    if r[0]: top_posters.append((r[0], r[1]))
            
            # Top 10 by balance
            q_rich = "SELECT user_id, SUM(balance) as bal FROM Users GROUP BY user_id ORDER BY bal DESC LIMIT 10"
            async with db.execute(q_rich) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    if r[0]: top_rich.append((r[0], r[1]))
    except Exception as e:
        print(f"Error fetching top: {e}")
        return

    def format_table(data_list, value_suffix=""):
        lines = []
        for i, (uid, val) in enumerate(data_list, 1):
            name = generate_anon_name(uid)
            val_str = f"{int(val)}{value_suffix}"
            lines.append(f"{i:2}. {name:<25} | {val_str:>8}")
        return "\n".join(lines) if lines else "Empty"

    if lang == 'en':
        header = "≡ƒÅå <b>TGACH LEADERBOARD</b> ≡ƒÅå"
        cat1 = "≡ƒô¥ <b>Top 10 Shitposters</b>"
        cat2 = "≡ƒÆ░ <b>Top 10 Richest</b>"
    elif lang == 'jp':
        header = "≡ƒÅå <b>TGπüíπéâπéô πâ⌐πâ│πé¡πâ│πé░</b> ≡ƒÅå"
        cat1 = "≡ƒô¥ <b>πâêπââπâù10 πâ¼πé╣µò░</b>"
        cat2 = "≡ƒÆ░ <b>πâêπââπâù10 σ»îΦ▒¬</b>"
    else:
        header = "≡ƒÅå <b>╨ö╨₧╨í╨Ü╨É ╨ƒ╨₧╨º╨ò╨ó╨É ╨ó╨ô╨É╨º╨É</b> ≡ƒÅå"
        cat1 = "≡ƒô¥ <b>╨ó╨╛╨┐-10 ╨⌐╨╕╤é╨┐╨╛╤ü╤é╨╡╤Ç╨╛╨▓ (╨┐╨╛╤ü╤é╤ï)</b>"
        cat2 = "≡ƒÆ░ <b>╨ó╨╛╨┐-10 ╨æ╨╛╨│╨░╤ç╨╡╨╣ (╨▒╨░╨╗╨░╨╜╤ü)</b>"

    text = f"{header}\n\n"
    text += f"{cat1}\n<pre>{format_table(top_posters)}</pre>\n\n"
    text += f"{cat2}\n<pre>{format_table(top_rich, ' Γé╜')}</pre>"
    
    try:
        await wait_msg.delete()
        await message.answer(text, parse_mode="HTML")
    except Exception: pass