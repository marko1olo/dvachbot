@dp.message(Command("deletethread", "delthread", "delete_thread"))
async def cmd_delete_thread(message: Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨ú╨┤╨░╨╗╤Å╨╡╤é ╤é╤Ç╨╡╨┤: ╨┐╨╛╨╝╨╡╤ç╨░╨╡╤é ╨░╤Ç╤à╨╕╨▓╨╜╤ï╨╝ ╨▓ ╨æ╨ö ╨╕ ╨▓╤ï╤ç╨╕╤ë╨░╨╡╤é ╨╕╨╖ RAM.

    ╨Ü╨╛╨╝╨░╨╜╨┤╨░ ╨╛╨▒╤è╤Å╨▓╨╗╨╡╨╜╨░ ╨▓ ╨░╨┤╨╝╨╕╨╜╤ü╨║╨╛╨╝ ╨╝╨╡╨╜╤Ä (setup_bot_commands), ╨░ ╤Ç╨░╨▒╨╛╤ç╨░╤Å
    delete_thread_atomic ╤ü╤â╤ë╨╡╤ü╤é╨▓╨╛╨▓╨░╨╗╨░ ╨▒╨╡╨╖ ╨╡╨┤╨╕╨╜╨╛╨│╨╛ ╨▓╤ï╨╖╨╛╨▓╨░ ΓÇö ╨░╨┤╨╝╨╕╨╜ ╨▓╨╕╨┤╨╡╨╗
    /deletethread ╨▓ ╨╝╨╡╨╜╤Ä, ╨╜╨╛ ╨╛╨╜╨░ ╨╜╨╕╤ç╨╡╨│╨╛ ╨╜╨╡ ╨┤╨╡╨╗╨░╨╗╨░. ╨ù╨┤╨╡╤ü╤î ╤ü╨▓╤Å╨╖╨░╨╜╤ï ╨╛╨▒╨╡ ╤ç╨░╤ü╤é╨╕:
    archive_thread_in_db ╨┤╨░╤æ╤é ╨┐╨╡╤Ç╤ü╨╕╤ü╤é╨╡╨╜╤é╨╜╨╛╤ü╤é╤î (╨╕╨╜╨░╤ç╨╡ ╤é╤Ç╨╡╨┤ ╨▓╨╡╤Ç╨╜╤â╨╗╤ü╤Å ╨▒╤ï ╨┐╨╛╤ü╨╗╨╡
    ╤Ç╨╡╤ü╤é╨░╤Ç╤é╨░ ╨╕╨╖ ╤é╨░╨▒╨╗╨╕╤å╤ï Threads), delete_thread_atomic ╤â╨▒╨╕╤Ç╨░╨╡╤é ╨╡╨│╨╛ ╨╕╨╖ ╨┐╨░╨╝╤Å╤é╨╕
    ╨╕ ╨▓╨╛╨╖╨▓╤Ç╨░╤ë╨░╨╡╤é ╤ç╨╕╤é╨░╤é╨╡╨╗╨╡╨╣ ╨╜╨░ ╨│╨╗╨░╨▓╨╜╤â╤Ä.
    """
    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        try:
            await message.delete()
        except TelegramBadRequest:
            import traceback; traceback.print_exc()
        return

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    args = (message.text or message.caption or "").split()[1:]
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})

    # ╨æ╨╡╨╖ ╨░╤Ç╨│╤â╨╝╨╡╨╜╤é╨░ ╤â╨┤╨░╨╗╤Å╨╡╨╝ ╤é╤Ç╨╡╨┤, ╨▓ ╨║╨╛╤é╨╛╤Ç╨╛╨╝ ╨░╨┤╨╝╨╕╨╜ ╤ü╨╡╨╣╤ç╨░╤ü ╨╜╨░╤à╨╛╨┤╨╕╤é╤ü╤Å.
    thread_id = args[0].lstrip('#') if args else None
    if not thread_id:
        location = b_data.get('user_state', {}).get(message.from_user.id, {}).get('location', 'main')
        if location and location != 'main':
            thread_id = str(location)

    if not thread_id:
        if lang == 'en':
            usage = "Usage: <code>/deletethread &lt;thread_id&gt;</code>, or run it inside the thread."
        elif lang == 'jp':
            usage = "Σ╜┐τö¿µ│ò: <code>/deletethread &lt;thread_id&gt;</code>πÇüπü╛πüƒπü»πé╣πâ¼πââπâëσåàπüºσ«ƒΦíîπÇé"
        else:
            usage = "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/deletethread &lt;id ╤é╤Ç╨╡╨┤╨░&gt;</code>, ╨╗╨╕╨▒╨╛ ╨▓╤ï╨╖╨╛╨▓╨╕ ╨▓╨╜╤â╤é╤Ç╨╕ ╤é╤Ç╨╡╨┤╨░."
        await message.answer(usage, parse_mode="HTML")
        return

    thread_info = threads_data.get(thread_id)
    if not thread_info:
        if lang == 'en':
            not_found = f"Γ¥î Thread <code>{escape_html(thread_id)}</code> not found on this board."
        elif lang == 'jp':
            not_found = f"Γ¥î πé╣πâ¼πââπâë <code>{escape_html(thread_id)}</code> πü»πüôπü«µ¥┐πü½σ¡ÿσ£¿πüùπü╛πü¢πéôπÇé"
        else:
            not_found = f"Γ¥î ╨ó╤Ç╨╡╨┤ <code>{escape_html(thread_id)}</code> ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜ ╨╜╨░ ╤ì╤é╨╛╨╣ ╨┤╨╛╤ü╨║╨╡."
        await message.answer(not_found, parse_mode="HTML")
        return

    title = thread_info.get('title') or thread_id
    posts_count = len(thread_info.get('posts', []))

    # ╨í╨╜╨░╤ç╨░╨╗╨░ ╨┐╨╡╤Ç╤ü╨╕╤ü╤é╨╡╨╜╤é╨╜╨╛: ╨╡╤ü╨╗╨╕ ╤â╨┐╨░╨┤╤æ╨╝ ╨┐╨╛╤ü╨╗╨╡ ╨╛╤ç╨╕╤ü╤é╨║╨╕ RAM, ╤é╤Ç╨╡╨┤ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╡╨╜
    # ┬½╨▓╨╛╤ü╨║╤Ç╨╡╤ü╨╜╤â╤é╤î┬╗ ╨░╨║╤é╨╕╨▓╨╜╤ï╨╝ ╨┐╤Ç╨╕ ╤ü╨╗╨╡╨┤╤â╤Ä╤ë╨╡╨╝ ╤ü╤é╨░╤Ç╤é╨╡.
    try:
        from common.database import archive_thread_in_db
        await archive_thread_in_db(int(thread_id))
    except (TypeError, ValueError):
        print(f"ΓÜá∩╕Å [/deletethread] thread_id '{thread_id}' ╨╜╨╡ ╨┐╤Ç╨╕╨▓╨╛╨┤╨╕╤é╤ü╤Å ╨║ int, ╨┐╤Ç╨╛╨┐╤â╤ü╨║╨░╤Ä ╨╖╨░╨┐╨╕╤ü╤î ╨▓ ╨æ╨ö.")
    except Exception as e:
        print(f"Γ¢ö [/deletethread] ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨░╤Ç╤à╨╕╨▓╨╕╤Ç╨╛╨▓╨░╤é╤î ╤é╤Ç╨╡╨┤ #{thread_id} ╨▓ ╨æ╨ö: {e}")
        if lang == 'en':
            await message.answer("Γ¥î DB error, thread left untouched.")
        else:
            await message.answer("Γ¥î ╨₧╤ê╨╕╨▒╨║╨░ ╨æ╨ö, ╤é╤Ç╨╡╨┤ ╨╜╨╡ ╤é╤Ç╨╛╨╜╤â╤é.")
        return

    await delete_thread_atomic(
        message.bot, board_id, thread_id,
        notify_users=True, initiator_id=message.from_user.id
    )

    if lang == 'en':
        done = f"≡ƒùæ Thread <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) deleted, {posts_count} posts purged."
    elif lang == 'jp':
        done = f"≡ƒùæ πé╣πâ¼πââπâë <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) πéÆσëèΘÖñπüùπü╛πüùπüƒ∩╝ê{posts_count} πâ¼πé╣∩╝ëπÇé"
    else:
        done = f"≡ƒùæ ╨ó╤Ç╨╡╨┤ <b>{escape_html(str(title))}</b> (<code>{escape_html(thread_id)}</code>) ╤â╨┤╨░╨╗╤æ╨╜, ╨▓╤ï╤ç╨╕╤ë╨╡╨╜╨╛ ╨┐╨╛╤ü╤é╨╛╨▓: {posts_count}."
    await message.answer(done, parse_mode="HTML")
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()