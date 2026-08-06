@dp.message(Command("bot_stats"))
async def cmd_bot_stats(message: types.Message):
    if not is_admin(message.from_user.id, 'b'): # check if admin on at least board b
        await message.answer("Γ¥î Access denied.")
        return
    await periodic_publisher.send_stats_to_user(message.bot, message.chat.id)