@dp.message(Command("addmoney"))
async def cmd_add_money_admin(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    try: await message.delete()
    except Exception: pass
    
    args = (message.text or message.caption or "").split()
    if len(args) < 3:
        await message.answer("Юзай: /addmoney &lt;ID&gt; &lt;сумма&gt;")
        return
        
    try:
        target_id, amount = int(args[1]), int(args[2])
        async with db_lock:
            db = await get_pool()
            # 1. Гарантируем, что запись на ТЕКУЩЕЙ доске существует
            await db.execute("INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)", (target_id, board_id))
            # 2. Начисляем деньги ТОЛЬКО в эту запись (избегаем умножения)
            await db.execute("UPDATE Users SET balance = balance + ? WHERE user_id = ? AND board_id = ?", (amount, target_id, board_id))
            await db.commit()
        
        await message.answer(f"✅ Нарисовано {amount} рублей для юзера {target_id}. Баланс пополнен (корзина /{board_id}/).")
        try:
            await message.bot.send_message(target_id, f"🎁 <b>Администрация начислила вам бонус: {amount} RUB! Кошелек - /wallet </b>", parse_mode="HTML")
        except Exception:
            import traceback; traceback.print_exc()
    except Exception as e:
        await message.answer(f"Ошибка: {e}", parse_mode=None)