@dp.message(Command("wallet", "balance", "money"))
async def cmd_wallet(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    
    db = await get_pool()
    
    # 1. ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╨╝ ╨╜╨░╨╗╨╕╤ç╨╕╨╡ ╤Ä╨╖╨╡╤Ç╨░ ╨╕ ╨╡╨│╨╛ ╤ü╤é╨░╤é╤â╤ü ╨ô╨¢╨₧╨æ╨É╨¢╨¼╨¥╨₧
    # last_failed_amount ΓÇö ╨╜╨╛╨▓╨░╤Å ╨║╨╛╨╗╨╛╨╜╨║╨░ ╨┤╨╗╤Å ╤ä╨╕╨║╤ü╨░╤å╨╕╨╕ ╤ü╤â╨╝╨╝╤ï "╨╜╨░╨╡╨▒╨░"
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
            f"≡ƒÆ│ <b>TGACH WALLET</b>\n{'ΓÇö'*22}\n"
            f"≡ƒæñ <b>Account ID:</b> <code>{user_id}</code>\n"
            f"≡ƒöï <b>Verification:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"≡ƒÆ╡ <b>Balance:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "≡ƒôû <b>Recent transactions:</b>\n"
    else:
        text = (
            f"≡ƒÆ│ <b>TGACH WALLET</b>\n{'ΓÇö'*22}\n"
            f"≡ƒæñ <b>ID ╨░╨║╨║╨░╤â╨╜╤é╨░:</b> <code>{user_id}</code>\n"
            f"≡ƒöï <b>╨ú╤Ç╨╛╨▓╨╡╨╜╤î:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"≡ƒÆ╡ <b>╨æ╨░╨╗╨░╨╜╤ü:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "≡ƒôû <b>╨ƒ╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ ╨╛╨┐╨╡╤Ç╨░╤å╨╕╨╕:</b>\n"

    history_body = f"{'ΓÇö'*22}\n{history_header}"
    
    if balance > 0 or is_new_wallet:
        if is_new_wallet or balance <= 15:
            history_body += f"≡ƒƒó +{int(balance)}.00 Γé╜ (Emoji Reactions)\n"
            history_body += f"≡ƒƒí {int(balance)}.00 Γé╜ (Available for withdrawal)\n"
        else:
            # ╨ö╨╡╤é╨╡╤Ç╨╝╨╕╨╜╨╕╤Ç╨╛╨▓╨░╨╜╨╜╤ï╨╣ ╨▒╨╛╨╜╤â╤ü ╨╜╨░ ╨╛╤ü╨╜╨╛╨▓╨╡ ID (╤ç╤é╨╛╨▒╤ï ╨╜╨╡ ╨┐╤Ç╤ï╨│╨░╨╗ ╨┐╤Ç╨╕ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╕)
            bonus = (user_id % 5) + 3
            history_body += f"≡ƒƒó +{bonus}.00 Γé╜ (Loyalty Reward)\n"
            history_body += f"≡ƒƒó +{int(balance - bonus)}.00 Γé╜ (Anon Reactions)\n"
            history_body += f"≡ƒƒí {int(balance)}.00 Γé╜ (Available for withdrawal)\n"
    else:
        # ╨Ü╨á╨É╨í╨¥╨É╨» ╨ÿ╨í╨ó╨₧╨á╨ÿ╨»: ╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╡╨╝ ╨╖╨░╤ä╨╕╨║╤ü╨╕╤Ç╨╛╨▓╨░╨╜╨╜╤â╤Ä ╨▓ ╨æ╨ö ╤ü╤â╨╝╨╝╤â ╨╕╨╗╨╕ ╨╜╨╡╨▒╨╛╨╗╤î╤ê╨╛╨╣ ╤Ç╨░╨╜╨┤╨╛╨╝, ╨╡╤ü╨╗╨╕ ╨╡╤ë╨╡ ╨╜╨╡ ╨▓╤ï╨▓╨╛╨┤╨╕╨╗╨╕
        failed_sum = int(last_failed) if last_failed > 0 else random.randint(20, 70)
        history_body += f"≡ƒö┤ -{failed_sum}.00 Γé╜ (Gateway Reject: 115-FZ)\n"
        history_body += f"≡ƒö┤ -15.00 Γé╜ (Maintenance Fee)\n"
        history_body += f"ΓÜ¬∩╕Å 0.00 Γé╜ (Account Liquidated)\n"

    text += history_body

    bot_user = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{user_id}"

    if lang == 'en':
        btns = ["≡ƒÆ╕ Withdraw", f"≡ƒñ¥ Invite Friend (+50Γé╜)", "≡ƒôè Rates", "≡ƒô£ History"]
    else:
        btns = ["≡ƒÆ╕ ╨Æ╤ï╨▓╨╡╤ü╤é╨╕ ╤ü╤Ç╨╡╨┤╤ü╤é╨▓╨░", f"≡ƒñ¥ ╨ƒ╤Ç╨╕╨│╨╗╨░╤ü╨╕╤é╤î ╨┤╤Ç╤â╨│╨░ (+50Γé╜)", "≡ƒôè ╨Ü╤â╤Ç╤ü ╨▓╨░╨╗╤Ä╤é", "≡ƒô£ ╨ÿ╤ü╤é╨╛╤Ç╨╕╤Å"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btns[0], callback_data="start_withdrawal")],
        [InlineKeyboardButton(text=btns[1], switch_inline_query=f"\n╨ù╨░╤à╨╛╨┤╨╕ ╨▓ ╨ó╨│╨░╤ç, ╤é╤â╤é ╨┐╨╗╨░╤é╤Å╤é ╨╖╨░ ╤Ç╨╡╨░╨║╤å╨╕╨╕! ╨£╨╛╤Å ╤ü╤ü╤ï╨╗╨║╨░: {ref_link}")],
        [InlineKeyboardButton(text=btns[2], callback_data="scam_rates"), 
         InlineKeyboardButton(text=btns[3], callback_data="scam_history")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")