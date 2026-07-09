@dp.message(Command("shop", "store", "market"))
async def cmd_shop(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    from common.db_pool import get_pool
    db = await get_pool()
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        balance = row[0] if row and row[0] is not None else 0
    text = (
        f"🛒 <b>Теневой Магазин (Black Market)</b>\n"
        f"Твой баланс: <code>{int(balance)}.00 RUB</code>\n\n"
        f"Трать свои фейк-рубли на грязь и власть:\n"
        f"1. 🧹 <b>Билет Дворника (6 часов)</b> — <i>700 RUB</i>\n"
        f"   (Временные права удалять спам через /del. Лимит: 10 удалений)\n"
        f"2. 🔇 <b>Мут-Ган (1 час)</b> — <i>500 RUB</i>\n"
        f"   (Выстрели в анона реплаем с /shoot — он улетает в мут)\n"
        f"3. 🛡️ <b>Зеркальный Щит (24ч)</b> — <i>400 RUB</i>\n"
        f"   (Автоматический рикошет Мут-Гана обратно в стрелка)\n"
        f"4. 👑 <b>VIP Префикс (24ч)</b> — <i>300 RUB</i>\n"
        f"   (Случайный префикс к твоему ID: от позора до элиты)\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Билет Дворника (700)", callback_data="shop_buy_janitor")],
        [InlineKeyboardButton(text="🔇 Купить Мут-Ган (500)", callback_data="shop_buy_mute")],
        [InlineKeyboardButton(text="🛡️ Зеркальный Щит (400)", callback_data="shop_buy_shield")],
        [InlineKeyboardButton(text="👑 Ролл Префикса (300)", callback_data="shop_buy_prefix")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("shop_buy_"))
async def cb_shop_buy(callback: types.CallbackQuery, board_id: str | None):
    if not board_id: return
    user_id = callback.from_user.id
    item = callback.data.split("_")[2]  # janitor, mute, shield, prefix
    costs = {"janitor": 700, "mute": 500, "shield": 400, "prefix": 300}
    price = costs.get(item, 999999)
    from common.db_pool import get_pool, db_lock
    db = await get_pool()
    async with db.execute("SELECT SUM(balance), MAX(active_items) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        balance = row[0] if row and row[0] is not None else 0
        active_items_str = row[1] if row and len(row) > 1 and row[1] else "{}"
    if balance < price:
        await callback.answer(f"❌ Не хватает бабок! Нужно {price} RUB, у тебя {int(balance)} RUB.", show_alert=True)
        return
    import json
    import time
    import random
    try:
        active_items = json.loads(active_items_str)
    except:
        active_items = {}
    msg = ""
    # 0. Janitor Ticket
    if item == "janitor":
        current_time = int(time.time())
        base_time = max(current_time, active_items.get("janitor_until", 0))
        active_items["janitor_until"] = base_time + 6 * 3600
        active_items["janitor_deletes_left"] = active_items.get("janitor_deletes_left", 0) + 10
        left = active_items["janitor_deletes_left"]
        msg = (
            f"🧹 Ты купил Билет Дворника на 6 часов!\n"
            f"Как использовать: найди спам в чате, нажми Reply и отправь /del.\n"
            f"Лимит удалений: {left}. Каждый успешный /del уменьшает счётчик на 1."
        )
    # 1. Mute-Gun
    elif item == "mute":
        if active_items.get("mute_gun"):
            await callback.answer("У тебя уже есть Мут-Ган! Сделай Reply на пост с командой /shoot", show_alert=True)
            return
        active_items["mute_gun"] = True
        msg = (
            f"🔫 Ты купил Мут-Ган!\n"
            f"Как использовать: найди пост жертвы, нажми Reply и отправь /shoot.\n"
            f"Эффект: жертва получает мут на 1 час.\n"
            f"⚠️ Осторожно: если у цели активен Зеркальный Щит, выстрел отразится обратно в тебя!"
        )
    # 2. Reflect Shield
    elif item == "shield":
        current_time = int(time.time())
        base_time = max(current_time, active_items.get("reflect_shield_until", 0))
        active_items["reflect_shield_until"] = base_time + 24 * 3600
        msg = (
            f"🛡️ Ты купил Зеркальный Щит на 24 часа!\n"
            f"Щит работает пассивно: при первой попытке выстрелить в тебя из Мут-Гана\n"
            f"выстрел автоматически отразится в стрелка (мут 1 час), а щит израсходуется."
        )
    # 3. Prefix
    elif item == "prefix":
        prefixes = [
            "[Скуф]", "[Опущенный]",
            "[Калоед]", "[Подпивас]",
            "[Шитпостер]", "[Гой]",
            "[Мамкин Трейдер]",
            "[Инцел]", "[Анимешник]",
            "[Чмо]", "[Вумен ☕️]",
            "[Гигачад]", "[Бог Борды]",
            "[VIP Анон]", "[Владелец]"
        ]
        chosen = random.choice(prefixes[:10]) if random.random() < 0.9 else random.choice(prefixes[10:])
        expires = int(time.time()) + 86400
        async with db_lock:
            await db.execute("UPDATE Users SET custom_prefix = ?, prefix_expires_at = ? WHERE user_id = ?", (chosen, expires, user_id))
        msg = (
            f"👑 Рулетка крутится...\n"
            f"Тебе выпал префикс: {chosen}\n"
            f"Виден в /passport и заголовках постов 24 часа."
        )
    # Списываем баланс
    async with db_lock:
        await db.execute(
            "UPDATE Users SET balance = balance - ?, active_items = ? WHERE user_id = ? AND board_id = ?",
            (price, json.dumps(active_items), user_id, board_id)
        )
        await db.commit()
    await callback.answer(msg, show_alert=True)
    new_bal = balance - price
    text = callback.message.html_text.replace(f"{int(balance)}.00", f"{int(new_bal)}.00")
    try:
        await callback.message.edit_text(text, reply_markup=callback.message.reply_markup, parse_mode="HTML")
    except:
        pass

import json

async def _get_user_active_items(db, user_id: int, board_id: str) -> dict:
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        return json.loads(active_items_str)
    except:
        return {}

async def _handle_shoot_bounce(message: types.Message, db, db_lock, board_id: str, user_id: int, target_id: int, active_items: dict, t_items: dict):
    t_items["reflect_shield_until"] = 0
    active_items["mute_gun"] = False
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(t_items), target_id, board_id))
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
    async with storage_lock:
        board_data[board_id]['mutes'][user_id] = datetime.now(UTC) + timedelta(seconds=3600)
    await apply_regular_mute(user_id, board_id, 3600)
    bounce = (
        f"🛡️ <b>ЗЕРКАЛЬНЫЙ ЩИТ!</b>\n\n"
        f"Анон попытался выстрелить из Мут-Гана в <code>{target_id}</code>, "
        f"но у цели сработал Зеркальный Щит!\n"
        f"Выстрел срикошетил. Стрелок <code>{user_id}</code> улетает в мут на 1 час 🤡\n"
        f"<i>(Щит цели израсходован.)</i>"
    )
    await message.bot.send_message(
        message.chat.id, bounce,
        reply_to_message_id=message.reply_to_message.message_id, parse_mode="HTML"
    )
    try:
        await message.bot.send_message(
            user_id,
            "💥 <b>Твой выстрел срикошетил!</b>\n"
            "Ты попытался выстрелить в анона с Зеркальным Щитом — выстрел отразился обратно. "
            "Ты в муте на 1 час.",
            parse_mode="HTML"
        )
    except:
        pass
    try:
        await message.delete()
    except:
        pass

async def _handle_shoot_success(message: types.Message, db, db_lock, board_id: str, user_id: int, target_id: int, active_items: dict):
    async with storage_lock:
        board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(seconds=3600)
    await apply_regular_mute(target_id, board_id, 3600)
    active_items["mute_gun"] = False
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
    alert = (
        f"💥 <b>ВЫСТРЕЛ ИЗ МУТ-ГАНА!</b>\n\n"
        f"Богатенький анон купил Мут-Ган за 500 RUB и пристрелил автора этого поста!\n"
        f"Жертва <code>{target_id}</code> отправляется в мут на 1 час.\n"
        f"<i>(Защита от Мут-Гана — Зеркальный Щит в /shop.)</i>"
    )
    await message.bot.send_message(
        message.chat.id, alert,
        reply_to_message_id=message.reply_to_message.message_id, parse_mode="HTML"
    )
    try:
        await message.bot.send_message(
            target_id,
            "💥 <b>В тебя выстрелили из Мут-Гана!</b>\n"
            "Тебя отправили в мут на 1 час — ты временно не можешь писать на этой доске.\n"
            "Защититься от будущих выстрелов можно купив Зеркальный Щит в /shop.",
            parse_mode="HTML"
        )
    except:
        pass
    try:
        await message.delete()
    except:
        pass


