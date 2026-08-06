@dp.message(Command("unban"))
async def cmd_unban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    
    args = (message.text or message.caption or "").split()
    if len(args) >= 2:
        try:
            target_id = int(args[1])
        except ValueError:
            import traceback; traceback.print_exc()
            
    if target_id is None:
        if lang == 'en': usage = "Usage: <code>/unban &lt;user_id&gt;</code> or reply to user message."
        elif lang == 'jp': usage = "Σ╜┐τö¿µ│ò: <code>/unban &lt;user_id&gt;</code> πü╛πüƒπü»πâªπâ╝πé╢πâ╝πâíπââπé╗πâ╝πé╕πü½Φ┐öΣ┐íπüùπü╛πüÖπÇé"
        else: usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/unban &lt;user_id&gt;</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except Exception: pass
        return
        
    unbanned = False
    async with storage_lock:
        b_data = board_data[board_id]
        if target_id in b_data['users']['banned']:
            b_data['users']['banned'].discard(target_id)
            b_data['users']['active'].add(target_id)
            unbanned = True
            
    board_name = BOARD_CONFIG[board_id]['name']
    if unbanned:
        await add_or_activate_user(target_id, board_id) 
        if lang == 'en': msg = f"User {target_id} unbanned on {board_name}."
        elif lang == 'jp': msg = f"πâªπâ╝πé╢πâ╝ {target_id} πü«BANπéÆΦºúΘÖñπüùπü╛πüùπüƒ ({board_name})πÇé"
        else: msg = f"╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î {target_id} ╤Ç╨░╨╖╨▒╨░╨╜╨╡╨╜ ╨╜╨░ ╨┤╨╛╤ü╨║╨╡ {board_name}."
        await message.answer(msg)
    else:
        if lang == 'en': msg = f"User {target_id} was not banned."
        elif lang == 'jp': msg = f"πâªπâ╝πé╢πâ╝ {target_id} πü»BANπüòπéîπüªπüäπü╛πü¢πéôπÇé"
        else: msg = f"╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î {target_id} ╨╜╨╡ ╨▒╤ï╨╗ ╨╖╨░╨▒╨░╨╜╨╡╨╜ ╨╜╨░ ╤ì╤é╨╛╨╣ ╨┤╨╛╤ü╨║╨╡."
        await message.answer(msg)
    try: await message.delete()
    except Exception: pass