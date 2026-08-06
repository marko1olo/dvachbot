@dp.message(Command("tags", "tagcloud", "╤é╨╡╨│╨╕", "╤é╨╡╨│"))
async def cmd_tag_cloud(message: types.Message, board_id: str | None = None, stream: str = 'ru'):
    """
    ╨Æ╤ï╨▓╨╛╨┤╨╕╤é ╨╛╨▒╨╗╨░╨║╨╛ ╤é╨╡╨│╨╛╨▓ ╨╝╨╡╨┤╨╕╨░╤ä╨░╨╣╨╗╨╛╨▓ ╨╕╨╖ FileRegistry ╤ü ╨║╨╜╨╛╨┐╨║╨░╨╝╨╕ ╨┐╤Ç╨╛╤ü╨╝╨╛╤é╤Ç╨░.
    """
    try:
        args = (message.text or message.caption or "").split(maxsplit=1)
        if len(args) > 1 and not args[1].startswith("-"):
            target_tag = args[1].strip().lower().lstrip("#")
            await show_tagged_photos_gallery(message, target_tag, offset=0)
            return

        # ╨º╨╡╤Ç╨╡╨╖ ╨╛╨▒╤ë╨╕╨╣ ╨┐╤â╨╗. ╨á╨░╨╜╤î╤ê╨╡ ╨╖╨┤╨╡╤ü╤î ╨▒╤ï╨╗╨╛ aiosqlite.connect("dvach_bot.db"),
        # ╨╜╨╛ aiosqlite ╨▓ main.py ╨╜╨╡ ╨╕╨╝╨┐╨╛╤Ç╤é╨╕╤Ç╨╛╨▓╨░╨╜ ╨Æ╨₧╨₧╨æ╨⌐╨ò ΓÇö ╨╜╨░ ╤ì╤é╨╛╨╣ ╤ü╤é╤Ç╨╛╨║╨╡
        # ╨▓╤ï╨╗╨╡╤é╨░╨╗ NameError, ╨╡╨│╨╛ ╨│╨╗╨╛╤é╨░╨╗ except ╨╜╨╕╨╢╨╡, ╨╕ ╨║╨╛╨╝╨░╨╜╨┤╨░ ╨▓╤ü╨╡╨│╨┤╨░
        # ╨╛╤é╨▓╨╡╤ç╨░╨╗╨░ ┬½╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╖╨░╨│╤Ç╤â╨╖╨╕╤é╤î ╨╛╨▒╨╗╨░╨║╨╛ ╤é╨╡╨│╨╛╨▓┬╗. ╨ù╨░╨╛╨┤╨╜╨╛ ╤â╤à╨╛╨┤╨╕╤é
        # ╨╛╤é╨╜╨╛╤ü╨╕╤é╨╡╨╗╤î╨╜╤ï╨╣ ╨┐╤â╤é╤î (╨╖╨░╨▓╨╕╤ü╨╡╨╗ ╨╛╤é ╤Ç╨░╨▒╨╛╤ç╨╡╨│╨╛ ╨║╨░╤é╨░╨╗╨╛╨│╨░) ╨╕ ╨▓╤é╨╛╤Ç╨╛╨╡
        # ╤ü╨╛╨╡╨┤╨╕╨╜╨╡╨╜╨╕╨╡ ╨▓ ╨╛╨▒╤à╨╛╨┤ ╨╜╨░╤ü╤é╤Ç╨╛╨╡╨║ ╨┐╤â╨╗╨░.
        db = await get_pool()
        async with db.execute("SELECT tags FROM FileRegistry WHERE tags IS NOT NULL AND tags != '' ORDER BY created_at DESC LIMIT 500;") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await message.answer("≡ƒÅ╖∩╕Å ╨ó╨╡╨│╨╕ ╨╝╨╡╨┤╨╕╨░╤ä╨░╨╣╨╗╨╛╨▓ ╨┐╨╛╨║╨░ ╨╜╨╡ ╤ü╨│╨╡╨╜╨╡╤Ç╨╕╤Ç╨╛╨▓╨░╨╜╤ï. ╨₧╤é╨┐╤Ç╨░╨▓╤î╤é╨╡ ╨╜╨╡╤ü╨║╨╛╨╗╤î╨║╨╛ ╨║╨░╤Ç╤é╨╕╨╜╨╛╨║ ╨▓ ╤ç╨░╤é!")
            return

        from collections import Counter
        tag_counts = Counter()
        for (tags_str,) in rows:
            for t in tags_str.split(','):
                t_clean = t.strip().lower()
                if t_clean and len(t_clean) > 2 and t_clean not in ('image', 'photo', 'picture', 'file'):
                    tag_counts[t_clean] += 1

        top_tags = tag_counts.most_common(20)
        if not top_tags:
            await message.answer("≡ƒÅ╖∩╕Å ╨ƒ╨╛╨║╨░ ╨╜╨╡╤é ╨┤╨╛╤ü╤é╨░╤é╨╛╤ç╨╜╨╛ ╨┐╨╛╨┐╤â╨╗╤Å╤Ç╨╜╤ï╤à ╤é╨╡╨│╨╛╨▓.")
            return

        lines = ["≡ƒÅ╖∩╕Å <b>╨₧╨æ╨¢╨É╨Ü╨₧ ╨ó╨ò╨ô╨₧╨Æ ╨£╨ò╨ö╨ÿ╨É╨ñ╨É╨Ö╨¢╨₧╨Æ</b>\n", "╨ƒ╨╛╨┐╤â╨╗╤Å╤Ç╨╜╤ï╨╡ ╨║╨░╤é╨╡╨│╨╛╤Ç╨╕╨╕ ╨┐╨╕╨║╤ç ╨╕╨╖ ╨▒╨╛╤é╨░ ╨╕ ╤ü╨░╨╣╤é╨░:\n"]
        keyboard_buttons = []
        row_btns = []
        for tag, count in top_tags:
            lines.append(f"ΓÇó <code>#{tag}</code> ΓÇö {count} ╨┐╨╕╨║╤ç")
            row_btns.append(types.InlineKeyboardButton(text=f"#{tag} ({count})", callback_data=f"tagview:{tag[:20]}:0"))
            if len(row_btns) == 2:
                keyboard_buttons.append(row_btns)
                row_btns = []
        if row_btns:
            keyboard_buttons.append(row_btns)

        lines.append("\n╨¥╨░╨╢╨╝╨╕╤é╨╡ ╨╜╨░ ╤é╨╡╨│ ╨╜╨╕╨╢╨╡ ╨╕╨╗╨╕ ╨▓╨▓╨╡╨┤╨╕╤é╨╡ <code>/tag ╨╜╨░╨╖╨▓╨░╨╜╨╕╨╡</code> ╨┤╨╗╤Å ╨┐╤Ç╨╛╤ü╨╝╨╛╤é╤Ç╨░ ╨║╨░╤Ç╤é╨╕╨╜╨║╨╕!")
        kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        print(f"ΓÜá∩╕Å ╨₧╤ê╨╕╨▒╨║╨░ ╨▓ cmd_tag_cloud: {e}")
        await message.answer("ΓÜá∩╕Å ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╖╨░╨│╤Ç╤â╨╖╨╕╤é╤î ╨╛╨▒╨╗╨░╨║╨╛ ╤é╨╡╨│╨╛╨▓.")