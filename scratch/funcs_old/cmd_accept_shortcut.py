@dp.message(Command("accept", "yes", "ok", "╨┐╤Ç╨╕╨╜╤Å╤é╤î"))
async def cmd_accept_shortcut(message: Message, board_id: str | None):
    if not board_id: return
    # ╨í╤Ç╨░╨▒╨░╤é╤ï╨▓╨░╨╡╤é ╨í╨ó╨á╨₧╨ô╨₧ ╨┐╨╛ Reply ╨║ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╤Ä ╨┤╤â╤ì╨╗╨╕
    if not message.reply_to_message:
        return
        
    reply_msg_id = message.reply_to_message.message_id
    now = time.time()
    found_ch = None
    for ch_id, duel in list(_active_duels.items()):
        if duel.get("msg_id") == reply_msg_id and duel["board_id"] == board_id and now - duel["ts"] < _DUEL_TIMEOUT:
            found_ch = ch_id
            break
            
    if found_ch:
        await accept_duel_logic(message, found_ch, board_id)