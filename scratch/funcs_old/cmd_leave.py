@dp.message(Command("leave"))
async def cmd_leave(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if board_id not in THREAD_BOARDS:
        try: await message.delete()
        except Exception: pass
        return
    user_id = message.from_user.id
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    user_s = b_data['user_state'].setdefault(user_id, {})
    current_location = user_s.get('location', 'main')
    if current_location == 'main':
        await message.delete()
        return
    now_ts = time.time()
    last_switch = user_s.get('last_location_switch', 0)
    if now_ts - last_switch < LOCATION_SWITCH_COOLDOWN:
        cooldown_phrases = thread_messages.get(lang, {}).get('location_switch_cooldown', [])
        if lang == 'en':
            default_cooldown_text = "Switching locations too fast, please wait."
        elif lang == 'jp':
            default_cooldown_text = "τº╗σïòπüîΘÇƒπüÖπüÄπü╛πüÖπÇüσ░æπüùσ╛àπüúπüªπüÅπüáπüòπüäπÇé"
        else:
            default_cooldown_text = "╨í╨╗╨╕╤ê╨║╨╛╨╝ ╤ç╨░╤ü╤é╨╛╨╡ ╨┐╨╡╤Ç╨╡╨║╨╗╤Ä╤ç╨╡╨╜╨╕╨╡, ╨┐╨╛╨┤╨╛╨╢╨┤╨╕╤é╨╡."
        cooldown_text = random.choice(cooldown_phrases) if cooldown_phrases else default_cooldown_text
        await message.answer(cooldown_text)
        await message.delete()
        return
    thread_id = current_location
    thread_info = b_data.get('threads_data', {}).get(thread_id)
    if thread_info:
        last_thread_post = thread_info.get('posts', [0])[-1] if thread_info.get('posts') else 0
        user_s.setdefault('last_seen_threads', {})[thread_id] = last_thread_post
    user_s['location'] = 'main'
    await update_user_location(user_id, board_id, 'main')
    user_s['last_location_switch'] = now_ts
    await message.delete()
    await send_missed_messages(message.bot, board_id, user_id, 'main', stream=stream)
    response_phrases = thread_messages.get(lang, {}).get('leave_thread_success', [])
    if lang == 'en':
        default_response_text = "You have returned to the main board."
    elif lang == 'jp':
        default_response_text = "πâíπéñπâ│µ¥┐πü½µê╗πéèπü╛πüùπüƒπÇé"
    else:
        default_response_text = "╨Æ╤ï ╨▓╨╡╤Ç╨╜╤â╨╗╨╕╤ü╤î ╨╜╨░ ╨╛╤ü╨╜╨╛╨▓╨╜╤â╤Ä ╨┤╨╛╤ü╨║╤â."
    response_text = random.choice(response_phrases) if response_phrases else default_response_text
    leave_keyboard = _get_leave_thread_keyboard(board_id, stream=stream)
    await message.answer(response_text, reply_markup=leave_keyboard)