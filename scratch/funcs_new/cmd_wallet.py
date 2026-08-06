@dp.message(Command("wallet", "balance", "money"))
async def cmd_wallet(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    
    db = await get_pool()
    
    # 1. Проверяем наличие юзера и его статус ГЛОБАЛЬНО
    # last_failed_amount — новая колонка для фиксации суммы "наеба"
    async with db.execute("SELECT SUM(balance), MAX(is_verified_b), MAX(last_failed_amount) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
    
    balance = row[0] if row and row[0] is not None else 0
    is_verified = row[1] if row and row[1] is not None else 0
    last_failed = row[2] if row and len(row) > 2 and row[2] is not None else 0
    
    is_new_wallet = False
    if balance == 0 and is_verified == 0 and last_failed == 0:
        start_bal = float(random.randint(8, 15))
        is_new_wallet = True
        async with db_lock:
            await db.execute(
                "INSERT INTO Users (user_id, board_id, balance, is_verified_b) VALUES (?, ?, ?, 0) "
                "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = ?",
                (user_id, board_id, start_bal, start_bal)
            )
        balance, is_verified = start_bal, 0

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if lang == 'en':
        text = (
            f"💳 <b>TGACH WALLET</b>\n{'—'*22}\n"
            f"👤 <b>Account ID:</b> <code>{user_id}</code>\n"
            f"🔋 <b>Verification:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"💵 <b>Balance:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "📖 <b>Recent transactions:</b>\n"
    else:
        text = (
            f"💳 <b>TGACH WALLET</b>\n{'—'*22}\n"
            f"👤 <b>ID аккаунта:</b> <code>{user_id}</code>\n"
            f"🔋 <b>Уровень:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"💵 <b>Баланс:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "📖 <b>Последние операции:</b>\n"

    history_body = f"{'—'*22}\n{history_header}"
    
    if balance > 0 or is_new_wallet:
        if is_new_wallet or balance <= 15:
            history_body += f"🟢 +{int(balance)}.00 ₽ (Emoji Reactions)\n"
            history_body += f"🟡 {int(balance)}.00 ₽ (Available for withdrawal)\n"
        else:
            # Детерминированный бонус на основе ID (чтобы не прыгал при обновлении)
            bonus = (user_id % 5) + 3
            history_body += f"🟢 +{bonus}.00 ₽ (Loyalty Reward)\n"
            history_body += f"🟢 +{int(balance - bonus)}.00 ₽ (Anon Reactions)\n"
            history_body += f"🟡 {int(balance)}.00 ₽ (Available for withdrawal)\n"
    else:
        # КРАСНАЯ ИСТОРИЯ: Используем зафиксированную в БД сумму или небольшой рандом, если еще не выводили
        failed_sum = int(last_failed) if last_failed > 0 else random.randint(20, 70)
        history_body += f"🔴 -{failed_sum}.00 ₽ (Gateway Reject: 115-FZ)\n"
        history_body += f"🔴 -15.00 ₽ (Maintenance Fee)\n"
        history_body += f"⚪️ 0.00 ₽ (Account Liquidated)\n"

    text += history_body

    bot_user = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{user_id}"

    if lang == 'en':
        btns = ["💸 Withdraw", f"🤝 Invite Friend (+50₽)", "📊 Rates", "📜 History"]
    else:
        btns = ["💸 Вывести средства", f"🤝 Пригласить друга (+50₽)", "📊 Курс валют", "📜 История"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btns[0], callback_data="start_withdrawal")],
        [InlineKeyboardButton(text=btns[1], switch_inline_query=f"\nЗаходи в Тгач, тут платят за реакции! Моя ссылка: {ref_link}")],
        [InlineKeyboardButton(text=btns[2], callback_data="scam_rates"), 
         InlineKeyboardButton(text=btns[3], callback_data="scam_history")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")