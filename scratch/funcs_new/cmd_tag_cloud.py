@dp.message(Command("tags", "tagcloud", "теги", "тег"))
async def cmd_tag_cloud(message: types.Message, board_id: str | None = None, stream: str = 'ru'):
    """
    Выводит облако тегов медиафайлов из FileRegistry с кнопками просмотра.
    """
    try:
        args = (message.text or message.caption or "").split(maxsplit=1)
        if len(args) > 1 and not args[1].startswith("-"):
            target_tag = args[1].strip().lower().lstrip("#")
            await show_tagged_photos_gallery(message, target_tag, offset=0)
            return

        # Через общий пул. Раньше здесь было aiosqlite.connect("dvach_bot.db"),
        # но aiosqlite в main.py не импортирован ВООБЩЕ — на этой строке
        # вылетал NameError, его глотал except ниже, и команда всегда
        # отвечала «Не удалось загрузить облако тегов». Заодно уходит
        # относительный путь (зависел от рабочего каталога) и второе
        # соединение в обход настроек пула.
        db = await get_pool()
        async with db.execute("SELECT tags FROM FileRegistry WHERE tags IS NOT NULL AND tags != '' ORDER BY created_at DESC LIMIT 500;") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await message.answer("🏷️ Теги медиафайлов пока не сгенерированы. Отправьте несколько картинок в чат!")
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
            await message.answer("🏷️ Пока нет достаточно популярных тегов.")
            return

        lines = ["🏷️ <b>ОБЛАКО ТЕГОВ МЕДИАФАЙЛОВ</b>\n", "Популярные категории пикч из бота и сайта:\n"]
        keyboard_buttons = []
        row_btns = []
        for tag, count in top_tags:
            lines.append(f"• <code>#{tag}</code> — {count} пикч")
            row_btns.append(types.InlineKeyboardButton(text=f"#{tag} ({count})", callback_data=f"tagview:{tag[:20]}:0"))
            if len(row_btns) == 2:
                keyboard_buttons.append(row_btns)
                row_btns = []
        if row_btns:
            keyboard_buttons.append(row_btns)

        lines.append("\nНажмите на тег ниже или введите <code>/tag название</code> для просмотра картинки!")
        kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        print(f"⚠️ Ошибка в cmd_tag_cloud: {e}")
        await message.answer("⚠️ Не удалось загрузить облако тегов.")