@economy_router.message(Command("partyvan"))
async def cmd_partyvan(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Нужно сделать Reply на пост того, за кем высылаем Пативэн!")
        return
    if target_id == user_id:
        await message.reply("Нельзя вызвать Пативэн на самого себя, шиз.")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try:
        active_items = json.loads(active_items_str)
    except:
        active_items = {}
        
    if not active_items.get("partyvan_gun"):
        await message.reply("У тебя нет доступа к вызову Пативэна! Купи его в /shop.")
        return
        
    now = int(time.time())
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as c:
        row = await c.fetchone()
        target_items_str = row[0] if row and row[0] else "{}"
    try: target_items = json.loads(target_items_str)
    except: target_items = {}

    if target_items.get("tinfoil_hat", 0) > now:
        active_items["partyvan_gun"] = False
        async with db_lock:
            await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                             (json.dumps(active_items), user_id, board_id))
            await db.commit()
        try: await message.bot.send_message(user_id, "🚔 Твой вызов ОМОНа отменили! У жертвы была надета Шапочка из фольги, они не смогли её запеленговать.", parse_mode="HTML")
        except: pass
        try: await message.bot.send_message(target_id, f"👽 Анон <code>{user_id}</code> попытался вызвать на тебя Пативэн, но Шапочка из фольги скрыла твои координаты!", parse_mode="HTML")
        except: pass
        try: await message.delete()
        except: pass
        return
        
    active_items["partyvan_gun"] = False
    
    from main import apply_regular_mute, board_data, storage_lock
    async with storage_lock:
        if board_id in board_data and 'mutes' in board_data[board_id]:
            board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(seconds=12*3600)
    await apply_regular_mute(target_id, board_id, 12*3600)
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
        
    try:
        await message.bot.send_message(
            target_id, 
            "🚔 <b>ВНИМАНИЕ! РАБОТАЕТ ОМОН!</b>\nЗа тобой выехал Пативэн (вызван кем-то из анонов).\nТы запакован в бобик и улетаешь в мут на 12 часов.", 
            parse_mode="HTML"
        )
    except: pass
    try:
        await message.bot.send_message(
            user_id, 
            f"🚔 Пативэн успешно выслан за аноном <code>{target_id}</code>!", 
            parse_mode="HTML"
        )
    except: pass
    try:
        await message.delete()
    except:
        pass