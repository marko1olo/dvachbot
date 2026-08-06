@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except Exception: pass
        return
    all_modes = MODE_FLAGS
    async with storage_lock:
        b_data = board_data[board_id]
        if b_data.get('active_mode_task') and not b_data['active_mode_task'].done():
            b_data['active_mode_task'].cancel()
            b_data['active_mode_task'] = None
        for mode in all_modes:
            b_data[mode] = False
        b_data['last_mode_activation'] = None
    settings_updates = {mode: False for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        msg = f"≡ƒ¢æ All active modes on board {board_name} have been stopped."
    elif lang == 'jp':
        msg = f"≡ƒ¢æ {board_name} µ¥┐πü«πüÖπü╣πüªπü«πéóπé»πâåπéúπâûπâóπâ╝πâëπéÆσü£µ¡óπüùπü╛πüùπüƒπÇé"
    else:
        msg = f"≡ƒ¢æ ╨Æ╤ü╨╡ ╨░╨║╤é╨╕╨▓╨╜╤ï╨╡ ╤Ç╨╡╨╢╨╕╨╝╤ï ╨╜╨░ ╨┤╨╛╤ü╨║╨╡ {board_name} ╨╛╤ü╤é╨░╨╜╨╛╨▓╨╗╨╡╨╜╤ï."
    await message.answer(msg)
    try: await message.delete()
    except Exception: pass