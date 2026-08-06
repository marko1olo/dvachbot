@dp.message(Command("shop", "store", "market"))
async def cmd_shop(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    db = await get_pool()
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        balance = row[0] if row and row[0] is not None else 0
    text = (
        f"🛒 <b>Теневой Магазин (Black Market)</b>\n"
        f"Твой баланс: <code>{int(balance)}.00 Шекелей</code>\n\n"
        f"Трать свои шекели на грязь и власть:\n"
        f"1. 🧹 <b>Билет Дворника (6ч)</b> — <i>1000 Шек</i> (Права /del)\n"
        f"2. 🔇 <b>Мут-Ган (1ч)</b> — <i>600 Шек</i> (Кикнуть реплаем /shoot)\n"
        f"3. 🛡️ <b>Зеркальный Щит (6ч)</b> — <i>800 Шек</i> (Рикошет Мут-Гана)\n"
        f"4. 👑 <b>VIP Префикс (24ч)</b> — <i>400 Шек</i> (Кастомный префикс)\n"
        f"5. 🚔 <b>Пативэн-Ган</b> — <i>2000 Шек</i> (Вызов ОМОНа через /partyvan)\n"
        f"6. 🐒 <b>Кусок говна</b> — <i>100 Шек</i> (Кинуть /shit, дебафф на час)\n"
        f"7. 💊 <b>Аминазин</b> — <i>100 Шек</i> (Снять дебаффы)\n"
        f"8. 🔪 <b>Заточка</b> — <i>400 Шек</i> (Ограбить анона на 10-30% через /rob)\n"
        f"9. 👽 <b>Шапочка из фольги (6ч)</b> — <i>800 Шек</i> (Защита от /shit и /rob)\n"
        f"10. 📜 <b>Взятка (Индульгенция)</b> — <i>1200 Шек</i> (Снимает мут)\n"
        f"11. 🚽 <b>Слабительное</b> — <i>800 Шек</i> (Проклятие: посты до 50 симв. через /curse)\n"
        f"12. 📣 <b>Мегафон</b> — <i>2000 Шек</i> (Закрепить свой пост через /mega)\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Дворник (1000)", callback_data="shop_buy_janitor"), InlineKeyboardButton(text="🔇 Мут-Ган (600)", callback_data="shop_buy_mute")],
        [InlineKeyboardButton(text="🛡️ Щит (800)", callback_data="shop_buy_shield"), InlineKeyboardButton(text="👑 Префикс (400)", callback_data="shop_buy_prefix")],
        [InlineKeyboardButton(text="🚔 Пативэн (2000)", callback_data="shop_buy_partyvan"), InlineKeyboardButton(text="🐒 Кусок говна (100)", callback_data="shop_buy_shit")],
        [InlineKeyboardButton(text="💊 Аминазин (100)", callback_data="shop_buy_pills"), InlineKeyboardButton(text="🔪 Заточка (400)", callback_data="shop_buy_knife")],
        [InlineKeyboardButton(text="👽 Фольга (800)", callback_data="shop_buy_tinfoil"), InlineKeyboardButton(text="📜 Взятка (1200)", callback_data="shop_buy_bribe")],
        [InlineKeyboardButton(text="🚽 Слабительное (800)", callback_data="shop_buy_laxative"), InlineKeyboardButton(text="📣 Мегафон (2000)", callback_data="shop_buy_megaphone")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")