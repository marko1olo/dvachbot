@economy_router.message(Command("shit"))
async def cmd_shit(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост жертвы!")
        return
    if target_id == user_id:
        await message.reply("Ты и так говно.")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        active_items = json.loads(active_items_str)
    except:
        active_items = {}
        
    if not active_items.get("shit_gun"):
        await message.reply("У тебя нет говна в карманах! Купи его в /shop.")
        return
        
    active_items["shit_gun"] = False
    
    now = int(time.time())
    
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        # Bounce 100% due to tinfoil
        bounce = True
    else:
        bounce = random.random() < 0.20
    
    final_target = user_id if bounce else target_id
    
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (final_target, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try:
        target_items = json.loads(target_items_str)
    except:
        target_items = {}
        
    target_items["shit_until"] = int(time.time()) + 3600
    
    async with db_lock:
        if bounce:
            target_items["shit_gun"] = False # they consume the item when throwing
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), user_id, board_id))
        else:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(target_items), target_id, board_id))
        await db.commit()
        
    if bounce:
        try:
            await message.bot.send_message(
                user_id, 
                "🐒 Ты попытался метнуть говно, но ветер дунул в лицо! Ты сам обмазан говном на час 💩", 
                parse_mode="HTML"
            )
        except: pass
    else:
        try:
            await message.bot.send_message(
                target_id, 
                "🐒 В тебя метнули кусок говна! Ты обмазан говном на час 💩", 
                parse_mode="HTML"
            )
        except: pass
        try:
            await message.bot.send_message(
                user_id, 
                f"🐒 Ты успешно метнул кусок говна в <code>{target_id}</code>!", 
                parse_mode="HTML"
            )
        except: pass
    try:
        await message.delete()
    except:
        pass