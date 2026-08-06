@dp.message(Command("shop", "store", "market"))
async def cmd_shop(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    db = await get_pool()
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        balance = row[0] if row and row[0] is not None else 0
    text = (
        f"≡ƒ¢Æ <b>╨ó╨╡╨╜╨╡╨▓╨╛╨╣ ╨£╨░╨│╨░╨╖╨╕╨╜ (Black Market)</b>\n"
        f"╨ó╨▓╨╛╨╣ ╨▒╨░╨╗╨░╨╜╤ü: <code>{int(balance)}.00 ╨¿╨╡╨║╨╡╨╗╨╡╨╣</code>\n\n"
        f"╨ó╤Ç╨░╤é╤î ╤ü╨▓╨╛╨╕ ╤ê╨╡╨║╨╡╨╗╨╕ ╨╜╨░ ╨│╤Ç╤Å╨╖╤î ╨╕ ╨▓╨╗╨░╤ü╤é╤î:\n"
        f"1. ≡ƒº╣ <b>╨æ╨╕╨╗╨╡╤é ╨ö╨▓╨╛╤Ç╨╜╨╕╨║╨░ (6╤ç)</b> ΓÇö <i>1000 ╨¿╨╡╨║</i> (╨ƒ╤Ç╨░╨▓╨░ /del)\n"
        f"2. ≡ƒöç <b>╨£╤â╤é-╨ô╨░╨╜ (1╤ç)</b> ΓÇö <i>600 ╨¿╨╡╨║</i> (╨Ü╨╕╨║╨╜╤â╤é╤î ╤Ç╨╡╨┐╨╗╨░╨╡╨╝ /shoot)\n"
        f"3. ≡ƒ¢í∩╕Å <b>╨ù╨╡╤Ç╨║╨░╨╗╤î╨╜╤ï╨╣ ╨⌐╨╕╤é (6╤ç)</b> ΓÇö <i>800 ╨¿╨╡╨║</i> (╨á╨╕╨║╨╛╤ê╨╡╤é ╨£╤â╤é-╨ô╨░╨╜╨░)\n"
        f"4. ≡ƒææ <b>VIP ╨ƒ╤Ç╨╡╤ä╨╕╨║╤ü (24╤ç)</b> ΓÇö <i>400 ╨¿╨╡╨║</i> (╨Ü╨░╤ü╤é╨╛╨╝╨╜╤ï╨╣ ╨┐╤Ç╨╡╤ä╨╕╨║╤ü)\n"
        f"5. ≡ƒÜö <b>╨ƒ╨░╤é╨╕╨▓╤ì╨╜-╨ô╨░╨╜</b> ΓÇö <i>2000 ╨¿╨╡╨║</i> (╨Æ╤ï╨╖╨╛╨▓ ╨₧╨£╨₧╨¥╨░ ╤ç╨╡╤Ç╨╡╨╖ /partyvan)\n"
        f"6. ≡ƒÉÆ <b>╨Ü╤â╤ü╨╛╨║ ╨│╨╛╨▓╨╜╨░</b> ΓÇö <i>100 ╨¿╨╡╨║</i> (╨Ü╨╕╨╜╤â╤é╤î /shit, ╨┤╨╡╨▒╨░╤ä╤ä ╨╜╨░ ╤ç╨░╤ü)\n"
        f"7. ≡ƒÆè <b>╨É╨╝╨╕╨╜╨░╨╖╨╕╨╜</b> ΓÇö <i>100 ╨¿╨╡╨║</i> (╨í╨╜╤Å╤é╤î ╨┤╨╡╨▒╨░╤ä╤ä╤ï)\n"
        f"8. ≡ƒö¬ <b>╨ù╨░╤é╨╛╤ç╨║╨░</b> ΓÇö <i>400 ╨¿╨╡╨║</i> (╨₧╨│╤Ç╨░╨▒╨╕╤é╤î ╨░╨╜╨╛╨╜╨░ ╨╜╨░ 10-30% ╤ç╨╡╤Ç╨╡╨╖ /rob)\n"
        f"9. ≡ƒæ╜ <b>╨¿╨░╨┐╨╛╤ç╨║╨░ ╨╕╨╖ ╤ä╨╛╨╗╤î╨│╨╕ (6╤ç)</b> ΓÇö <i>800 ╨¿╨╡╨║</i> (╨ù╨░╤ë╨╕╤é╨░ ╨╛╤é /shit ╨╕ /rob)\n"
        f"10. ≡ƒô£ <b>╨Æ╨╖╤Å╤é╨║╨░ (╨ÿ╨╜╨┤╤â╨╗╤î╨│╨╡╨╜╤å╨╕╤Å)</b> ΓÇö <i>1200 ╨¿╨╡╨║</i> (╨í╨╜╨╕╨╝╨░╨╡╤é ╨╝╤â╤é)\n"
        f"11. ≡ƒÜ╜ <b>╨í╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡</b> ΓÇö <i>800 ╨¿╨╡╨║</i> (╨ƒ╤Ç╨╛╨║╨╗╤Å╤é╨╕╨╡: ╨┐╨╛╤ü╤é╤ï ╨┤╨╛ 50 ╤ü╨╕╨╝╨▓. ╤ç╨╡╤Ç╨╡╨╖ /curse)\n"
        f"12. ≡ƒôú <b>╨£╨╡╨│╨░╤ä╨╛╨╜</b> ΓÇö <i>2000 ╨¿╨╡╨║</i> (╨ù╨░╨║╤Ç╨╡╨┐╨╕╤é╤î ╤ü╨▓╨╛╨╣ ╨┐╨╛╤ü╤é ╤ç╨╡╤Ç╨╡╨╖ /mega)\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="≡ƒº╣ ╨ö╨▓╨╛╤Ç╨╜╨╕╨║ (1000)", callback_data="shop_buy_janitor"), InlineKeyboardButton(text="≡ƒöç ╨£╤â╤é-╨ô╨░╨╜ (600)", callback_data="shop_buy_mute")],
        [InlineKeyboardButton(text="≡ƒ¢í∩╕Å ╨⌐╨╕╤é (800)", callback_data="shop_buy_shield"), InlineKeyboardButton(text="≡ƒææ ╨ƒ╤Ç╨╡╤ä╨╕╨║╤ü (400)", callback_data="shop_buy_prefix")],
        [InlineKeyboardButton(text="≡ƒÜö ╨ƒ╨░╤é╨╕╨▓╤ì╨╜ (2000)", callback_data="shop_buy_partyvan"), InlineKeyboardButton(text="≡ƒÉÆ ╨Ü╤â╤ü╨╛╨║ ╨│╨╛╨▓╨╜╨░ (100)", callback_data="shop_buy_shit")],
        [InlineKeyboardButton(text="≡ƒÆè ╨É╨╝╨╕╨╜╨░╨╖╨╕╨╜ (100)", callback_data="shop_buy_pills"), InlineKeyboardButton(text="≡ƒö¬ ╨ù╨░╤é╨╛╤ç╨║╨░ (400)", callback_data="shop_buy_knife")],
        [InlineKeyboardButton(text="≡ƒæ╜ ╨ñ╨╛╨╗╤î╨│╨░ (800)", callback_data="shop_buy_tinfoil"), InlineKeyboardButton(text="≡ƒô£ ╨Æ╨╖╤Å╤é╨║╨░ (1200)", callback_data="shop_buy_bribe")],
        [InlineKeyboardButton(text="≡ƒÜ╜ ╨í╨╗╨░╨▒╨╕╤é╨╡╨╗╤î╨╜╨╛╨╡ (800)", callback_data="shop_buy_laxative"), InlineKeyboardButton(text="≡ƒôú ╨£╨╡╨│╨░╤ä╨╛╨╜ (2000)", callback_data="shop_buy_megaphone")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")