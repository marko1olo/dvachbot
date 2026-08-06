@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not is_admin(message.from_user.id, board_id):
        lang = 'en' if board_id == 'int' else 'ru'
        contact_url = "https://t.me/voprosy?start=rba30"
        if lang == 'en':
            response_text = "To contact the administration, please use the button below:"
            button_text = "Contact Admin"
        else:
            response_text = "Для связи с админом используйте кнопку ниже:"
            button_text = "Связаться с админом"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=contact_url)]])
        try:
            await message.answer(response_text, reply_markup=keyboard)
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media')) # Подсчет
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    if lang == 'en':
        header_text = f"Admin panel for board {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            "<b>🗒️ Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia</code> — Бан ВСЕХ медиа ({media_ban_count})\n\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
    elif lang == 'jp':
        header_text = f"{BOARD_CONFIG[board_id]['name']} の管理パネル:"
        memo_text = (
            "<b>🗒️ コマンドメモ:</b>\n"
            "<code>/filter ...</code> - スパムフィルタ管理\n"
            f"<code>/togglereactions &lt;id&gt;</code> - リアクション禁止 ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIFシャドウバン ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - ステッカーシャドウバン ({sticker_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (返信) - リアクションした人を見る"
        )
    else:
        header_text = f"Админка доски {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> — Бан/Разбан\n"
            "<code>/mute [время]</code>, <code>/unmute</code> — Мут\n"
            "<code>/shadowmute [время]</code> — Теневой мут (локальный)\n"
            "<code>/gban</code>, <code>/gunban</code>, <code>/gshadowmute</code> — <b>ГЛОБАЛЬНЫЕ</b> меры\n\n"
            "<code>/del</code> — Удалить пост (и копии)\n"
            "<code>/sdel</code> — Теневое удаление (автор не видит)\n"
            "<code>/pin</code>, <code>/unpin</code> — Глобальный закреп\n\n"
            "<code>/whois [id]</code> — Досье на юзера\n"
            "<code>/id</code> — Узнать ID\n"
            f"<code>/togglegif</code> — Запрет GIF (Всего: {gif_ban_count})\n"
            f"<code>/togglestickers</code> — Запрет стикеров (Всего: {sticker_ban_count})\n\n"
            f"<code>/lie</code> — Подмена медиа архивом (Всего: {lie_media_count})\n\n"
            "<code>/say [текст]</code> — Пост от имени Админа\n"
            "<code>/ans [текст]</code> — Ответ от имени Системы (реплай)\n"
            "<code>/stop</code> — Выключить режимы (Шиза и т.д.)"
        )
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text="🤬 Стоп-слова", callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text="🚫 Ограничения (Баны/Муты)", callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text="🔒 Локдаун (ВКЛ/ВЫКЛ)", callback_data="admin_menu:lockdown")],
        [InlineKeyboardButton(text="💾 Сохранить Бэкап", callback_data="save_all")],
    ])
    await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
    await _safe_delete_user_message(message)