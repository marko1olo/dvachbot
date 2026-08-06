@economy_router.message(Command("rob"))
async def cmd_rob(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Нельзя ограбить самого себя.")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except: active_items = {}
        
    if not active_items.get("knife_gun"):
        await message.reply("У тебя нет заточки! Купи её в /shop.")
        return
        
    active_items["knife_gun"] = False
    
    async with db.execute("SELECT balance, active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_balance = row[0] if row and row[0] else 0
        target_items_str = row[1] if row and row[1] else "{}"
    try: target_items = json.loads(target_items_str)
    except: target_items = {}
    
    now = int(time.time())
    if target_items.get("tinfoil_hat", 0) > now:
        # Tinfoil blocks the attack
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось.", parse_mode="HTML")
        except: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <code>{user_id}</code> попытался ограбить тебя, но твоя Шапочка из фольги спасла твои шекели!", parse_mode="HTML")
        except: pass
        try: await message.delete()
        except: pass
        return

    if target_balance < 50:
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🔪 Ты приставил заточку, но у жертвы в карманах только дыры... Грабить нечего.", parse_mode="HTML")
        except: pass
        try: await message.delete()
        except: pass
        return

    stolen = min(1000, int(target_balance * random.uniform(0.1, 0.3)))

    async with db_lock:
        # Сначала СПИСЫВАЕМ, и только если сумма реально есть.
        # target_balance читался выше вне лока и к этому моменту мог устареть:
        # жертва успела потратиться или её уже грабанул кто-то другой. Условие
        # `balance >= ?` делает проверку и списание одной атомарной операцией.
        # Без него несколько одновременных грабежей уводили баланс жертвы в
        # минус, а грабителям начислялось то, чего у неё не было.
        cursor = await db.execute(
            "UPDATE Users SET balance = balance - ? WHERE user_id = ? AND board_id = ? AND balance >= ?",
            (stolen, target_id, board_id, stolen))
        # Корректность обеспечивает условие `balance >= ?` в самом UPDATE:
        # списать больше, чем есть, оно не даст ни при какой конкуренции.
        # rowcount нужен только чтобы решить, начислять ли грабителю. Доверяем
        # ему лишь когда это настоящее целое: aiosqlite всегда отдаёт int, а
        # тестовые дубли — то None, то авто-атрибут MagicMock. В неясном случае
        # считаем, что списание прошло, то есть ведём себя как прежний код.
        rowcount = getattr(cursor, "rowcount", None)
        robbed = (rowcount == 1) if isinstance(rowcount, int) else True
        # Заточка расходуется в любом случае — попытка была.
        await db.execute("UPDATE Users SET balance = balance + ?, active_items = ? WHERE user_id = ? AND board_id = ?",
                         (stolen if robbed else 0, json.dumps(active_items), user_id, board_id))
        await db.commit()

    if not robbed:
        try: await message.bot.send_message(user_id, "🔪 Пока ты замахивался, у жертвы кончились шекели. Заточка потрачена впустую.", parse_mode="HTML")
        except: pass
        try: await message.delete()
        except: pass
        return

    try: await message.bot.send_message(target_id, f"🔪 В подворотне тебя пырнул Анон <code>{user_id}</code> и отобрал <b>{stolen} Шекелей</b>!", parse_mode="HTML")
    except: pass
    try: await message.bot.send_message(user_id, f"🔪 Ограбление прошло успешно! Ты отжал у лоха <code>{target_id}</code> <b>{stolen} Шекелей</b>.", parse_mode="HTML")
    except: pass
    try: await message.delete()
    except: pass