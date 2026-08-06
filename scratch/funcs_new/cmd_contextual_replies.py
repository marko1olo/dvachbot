@dp.message(Command("autoreply", "autoreplies", "contextual", "contextreply"))
async def cmd_contextual_replies(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or "").split()
    await message.delete()