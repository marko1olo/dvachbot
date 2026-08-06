@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    user_id = message.from_user.id
    if not board_id: return
    if board_id in THREAD_BOARDS:
        command_payload = (message.text or message.caption or "").split()[1] if len((message.text or message.caption or "").split()) > 1 else None
        if command_payload and command_payload.startswith("thread_"):
            thread_id = command_payload.split('_')[-1]
            b_data = board_data[board_id]
            if thread_id in b_data.get('threads_data', {}):
                b_data['users']['active'].add(user_id)
                await _enter_thread_logic(
                    bot=message.bot, board_id=board_id, user_id=user_id,
                    thread_id=thread_id, message_to_delete=message,
                    stream=stream 
                )
            return
        now = time.time()
        if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
            await message.delete()
            return
        user_last_thread_action[user_id] = now
        text, keyboard = await generate_threads_page(board_id, user_id, page=0, stream=stream)
        if text:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await message.delete()
        return
    b_data = board_data[board_id]
    
    db = await get_pool()

    # 1. ╨ƒ╤Ç╨╛╨▓╨╡╤Ç╤Å╨╡╨╝, ╤ü╤â╤ë╨╡╤ü╤é╨▓╤â╨╡╤é ╨╗╨╕ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î ╨▓ ╨æ╨ö ╨│╨╗╨╛╨▒╨░╨╗╤î╨╜╨╛ (╨╜╨░ ╨╗╤Ä╨▒╨╛╨╣ ╨┤╨╛╤ü╨║╨╡)
    async with db.execute("SELECT 1 FROM Users WHERE user_id = ? LIMIT 1", (user_id,)) as c:
        user_exists_globally = await c.fetchone()

    # 2. ╨ò╤ü╨╗╨╕ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å ╨╜╨╡╤é ╨▓ ╨æ╨ö ΓÇö ╨╛╨╜ ╤ü╤ç╨╕╤é╨░╨╡╤é╤ü╤Å "╨╜╨╛╨▓╤ï╨╝" ╨┤╨╗╤Å ╤Ç╨╡╤ä╨╡╤Ç╨░╨╗╤î╨╜╨╛╨╣ ╤ü╨╕╤ü╤é╨╡╨╝╤ï
    if not user_exists_globally:
        args = (message.text or message.caption or "").split()
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].replace("ref_", ""))
                if referrer_id != user_id:
                    async with db_lock:
                        # ╨¥╨░╤ç╨╕╤ü╨╗╤Å╨╡╨╝ 50╤Ç ╤Ç╨╡╤ä╨╡╤Ç╨╡╤Ç╤â (UPSERT: ╤ü╨╛╨╖╨┤╨░╨╡╨╝ ╨╖╨░╨┐╨╕╤ü╤î, ╨╡╤ü╨╗╨╕ ╨╡╤æ ╨╜╨╡╤é)
                        # ╨¡╤é╨╛ ╨│╨░╤Ç╨░╨╜╤é╨╕╤Ç╤â╨╡╤é, ╤ç╤é╨╛ ╨▒╨╛╨╜╤â╤ü ╨┤╨╛╨╣╨┤╨╡╤é, ╨┤╨░╨╢╨╡ ╨╡╤ü╨╗╨╕ ╨┐╤Ç╨╕╨│╨╗╨░╤ü╨╕╨▓╤ê╨╕╨╣ ╨╡╤ë╨╡ ╨╜╨╡ ╨╛╤é╨║╤Ç╤ï╨▓╨░╨╗ ╨║╨╛╤ê╨╡╨╗╨╡╨║
                        await db.execute("""
                            INSERT INTO Users (user_id, board_id, balance, referrals_count) 
                            VALUES (?, ?, 50, 1) 
                            ON CONFLICT(user_id, board_id) DO UPDATE SET 
                            balance = balance + 50, 
                            referrals_count = referrals_count + 1
                        """, (referrer_id, board_id))
                        
                        async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (referrer_id,)) as c_sum:
                            sum_row = await c_sum.fetchone()
                            ref_balance = sum_row[0] if sum_row and sum_row[0] else 50
                    
                    try:
                        ref_stream = await get_user_stream(referrer_id, board_id)
                        notif_text = REFERRAL_BONUS_MESSAGES.get(ref_stream, REFERRAL_BONUS_MESSAGES['ru']).format(balance=int(ref_balance))
                        await message.bot.send_message(referrer_id, notif_text, parse_mode="HTML")
                    except Exception: pass
            except Exception as e:
                print(f"ΓÜá∩╕Å ╨₧╤ê╨╕╨▒╨║╨░ ╨╛╨▒╤Ç╨░╨▒╨╛╤é╨║╨╕ ╤Ç╨╡╤ä╨╡╤Ç╨░╨╗╨░: {e}")

    # 3. ╨É╨║╤é╨╕╨▓╨╕╤Ç╤â╨╡╨╝ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å (╤ü╨╛╨╖╨┤╨░╨╡╤é ╨╖╨░╨┐╨╕╤ü╤î ╨▓ ╨æ╨ö ╨┤╨╗╤Å ╨╜╨╛╨▓╨╛╨│╨╛ ╤Ä╨╖╨╡╤Ç╨░)
    if user_id not in b_data['users']['active']:
        await add_or_activate_user(user_id, board_id)
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
        print(f"Γ£à [{board_id}] ╨¥╨╛╨▓╤ï╨╣ ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î: {user_id}")
        await send_welcome_sequence(message.bot, user_id, board_id, stream=stream)
        spawn_task(send_active_pin_to_new_user(message.bot, user_id, board_id))
    else:
        start_text = b_data.get('start_message_text', "╨ö╨╛╨▒╤Ç╨╛ ╨┐╨╛╨╢╨░╨╗╨╛╨▓╨░╤é╤î ╨▓ ╨ó╨ô╨É╨º!")
        await message.answer(start_text, parse_mode="HTML", disable_web_page_preview=True)
        menu_text = "≡ƒæç <b>Quick Menu / ╨æ╤ï╤ü╤é╤Ç╨╛╨╡ ╨╝╨╡╨╜╤Ä:</b>"
        await message.answer(menu_text, reply_markup=get_quick_menu_keyboard(board_id, stream=stream), parse_mode="HTML")
        try: await message.delete()
        except Exception: pass