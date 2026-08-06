@dp.message(Command("duel"))
async def cmd_duel(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    args = (message.text or message.caption or "").split()[1:]

    if args and args[0].lower() in ("accept", "принять", "+"):
        await _handle_duel_accept(message, board_id)
    else:
        await _handle_duel_create(message, board_id, args, stream)