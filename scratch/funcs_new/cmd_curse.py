@economy_router.message(Command("curse"))
async def cmd_curse(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Сам себе слабительное?")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except: active_items = {}
        
    if not active_items.get("laxative_gun"):
        await message.reply("У тебя нет слабительного! Купи его в /shop.")
        return
        
    active_items["laxative_gun"] = False
    now = int(time.time())

    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🚽 Твоё проклятие отскочило от Шапочки из фольги жертвы! Своё слабительное ты потратил впустую.", parse_mode="HTML")
        except: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <code>{user_id}</code> попытался подсыпать тебе слабительное, но твоя Шапочка из фольги спасла твои штаны!", parse_mode="HTML")
        except: pass
        try: await message.delete()
        except: pass
        return

    curse_until = now + 3600
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.execute("UPDATE Users SET cursed_until = ? WHERE user_id = ? AND board_id = ?",
                         (curse_until, target_id, board_id))
        await db.commit()
        
    try: await message.bot.send_message(target_id, "🚽 Тебе подсыпали слабительное! В течение 1 часа ты не сможешь писать посты длиннее 50 символов (не успеешь дописать и побежишь в туалет).", parse_mode="HTML")
    except: pass
    try: await message.bot.send_message(user_id, f"🚽 Ты успешно подсыпал слабительное анону <code>{target_id}</code>!", parse_mode="HTML")
    except: pass
    try: await message.delete()
    except: pass