@economy_router.message(Command("mega"))
async def cmd_mega(message: types.Message, board_id: str | None = None):
    if not board_id: return
    user_id = message.from_user.id
    target_id = await get_reply_target(message)
    if not target_id:
        await message.reply("Сделай Reply на СВОЙ пост, который хочешь закрепить!")
        return
    if target_id != user_id:
        await message.reply("Мегафон работает только на свои собственные посты!")
        return
        
    db = await get_pool()
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        active_items_str = row[0] if row and row[0] else "{}"
    try: active_items = json.loads(active_items_str)
    except: active_items = {}
        
    if not active_items.get("megaphone_gun"):
        await message.reply("У тебя нет рупора! Купи его в /shop.")
        return
        
    active_items["megaphone_gun"] = False
    
    # Try to pin the message
    try:
        await message.bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        alert = "📣 Твой пост успешно закреплен с помощью Мегафона!"
    except Exception as e:
        alert = f"❌ Ошибка закрепления: {e}"
        active_items["megaphone_gun"] = True # Refund
    
    async with db_lock:
        await db.execute("UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                         (json.dumps(active_items), user_id, board_id))
        await db.commit()
        
    try: await message.bot.send_message(user_id, alert, parse_mode="HTML")
    except: pass
    
    if "успешно" in alert:
        try:
            await message.bot.send_message(
                message.chat.id, 
                "📣 <b>ВНИМАНИЕ!</b> Кто-то из анонов проплатил закрепление поста через Мегафон!", 
                reply_to_message_id=message.reply_to_message.message_id, 
                parse_mode="HTML"
            )
        except: pass
        
    try: await message.delete()
    except: pass