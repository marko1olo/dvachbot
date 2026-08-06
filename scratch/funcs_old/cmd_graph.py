@dp.message(Command("graph"))
async def cmd_graph(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not GRAPH_LIBS_AVAILABLE:
        if lang == 'en':
            error_text = "Graph generation module is not available (dependencies missing)."
        elif lang == 'jp':
            error_text = "πé░πâ⌐πâòτöƒµêÉπâóπé╕πâÑπâ╝πâ½πüîσê⌐τö¿πüºπüìπü╛πü¢πéô∩╝êΣ╛¥σ¡ÿΘûóΣ┐éπüîΣ╕ìΦ╢│πüùπüªπüäπü╛πüÖ∩╝ëπÇé"
        else:
            error_text = "╨£╨╛╨┤╤â╨╗╤î ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕ ╨│╤Ç╨░╤ä╨╕╨║╨╛╨▓ ╨╜╨╡╨┤╨╛╤ü╤é╤â╨┐╨╡╨╜ (╨╛╤é╤ü╤â╤é╤ü╤é╨▓╤â╤Ä╤é ╨╖╨░╨▓╨╕╤ü╨╕╨╝╨╛╤ü╤é╨╕)."
        try:
            await message.answer(error_text)
            await message.delete()
        except Exception: pass
        return
    INFO_CMD_COOLDOWN = 60
    # storage_lock ╤â╨▒╤Ç╨░╨╜ ╨║╨░╨║ ╨╗╨╛╨╢╨╜╨░╤Å ╨╖╨░╨▓╨╕╤ü╨╕╨╝╨╛╤ü╤é╤î: ╨║╤â╨╗╨┤╨░╤â╨╜ ╨▓ board_data, ╨░ ╨╗╨╛╨║
    # ╨╖╨░╤ë╨╕╤ë╨░╨╡╤é messages_storage. ╨ÿ╤ü╨║╨╗╤Ä╤ç╨╡╨╜╨╕╨╡ ╤â╨╢╨╡ ╨┤╨░╤æ╤é info_cmd_lock.
    remaining = 0
    async with info_cmd_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < INFO_CMD_COOLDOWN
        if on_cooldown:
            remaining = int(INFO_CMD_COOLDOWN - (current_time - last_usage))
        else:
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en':
            cooldown_text = f"ΓÅ│ You can use this command in {remaining} seconds."
        elif lang == 'jp':
            cooldown_text = f"ΓÅ│ πüôπü«πé│πâ₧πâ│πâëπü»πüéπü¿ {remaining} τºÆσ╛îπü½Σ╜┐τö¿πüºπüìπü╛πüÖπÇé"
        else:
            cooldown_text = f"ΓÅ│ ╨Ü╨╛╨╝╨░╨╜╨┤╤â ╨╝╨╛╨╢╨╜╨╛ ╨╕╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╤î ╤ç╨╡╤Ç╨╡╨╖ {remaining} ╤ü╨╡╨║."
        try:
            sent_msg = await message.answer(cooldown_text)
            spawn_task(delete_message_after_delay(sent_msg, 5))
            await message.delete()
        except Exception: pass
        return
    args = (message.text or message.caption or "").split()
    days = 7  # ╨ƒ╨╛ ╤â╨╝╨╛╨╗╤ç╨░╨╜╨╕╤Ä 7 ╨┤╨╜╨╡╨╣
    if len(args) > 1:
        arg = args[1].lower()
        if arg.endswith('d') and arg[:-1].isdigit():
            try:
                days = int(arg[:-1])
                days = max(1, min(30, days))
            except ValueError:
                import traceback; traceback.print_exc()
    working_msg = None
    try:
        await message.delete()
        if lang == 'en':
            working_text = "≡ƒÄ¿ Drawing the graph..."
        elif lang == 'jp':
            working_text = "≡ƒÄ¿ πé░πâ⌐πâòπéÆµÅÅτö╗Σ╕¡..."
        else:
            working_text = "≡ƒÄ¿ ╨á╨╕╤ü╤â╤Ä ╨│╤Ç╨░╤ä╨╕╨║..."
        working_msg = await message.answer(working_text)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(
            None,
            generate_statistics_graph,
            board_id,
            days
        )
        await working_msg.delete()
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename=f"graph_{board_id}_{days}d.png")
            await message.answer_photo(photo)
        else:
            if lang == 'en':
                no_data_text = "No data available to build a graph for this period."
            elif lang == 'jp':
                no_data_text = "πüôπü«µ£ƒΘûôπü«πé░πâ⌐πâòπéÆΣ╜£µêÉπüÖπéïπüƒπéüπü«πâçπâ╝πé┐πüîπüéπéèπü╛πü¢πéôπÇé"
            else:
                no_data_text = "╨¥╨╡╤é ╨┤╨░╨╜╨╜╤ï╤à ╨┤╨╗╤Å ╨┐╨╛╤ü╤é╤Ç╨╛╨╡╨╜╨╕╤Å ╨│╤Ç╨░╤ä╨╕╨║╨░ ╨╖╨░ ╤ì╤é╨╛╤é ╨┐╨╡╤Ç╨╕╨╛╨┤."
            await message.answer(no_data_text)
    except Exception as e:
        print(f"Γ¢ö ╨₧╤ê╨╕╨▒╨║╨░ ╨▓ ╨╛╨▒╤Ç╨░╨▒╨╛╤é╤ç╨╕╨║╨╡ /graph: {e}")
        try:
            if working_msg:
                await working_msg.delete()
            if lang == 'en':
                error_text = "An error occurred while creating the graph."
            elif lang == 'jp':
                error_text = "πé░πâ⌐πâòπü«Σ╜£µêÉΣ╕¡πü½πé¿πâ⌐πâ╝πüîτÖ║τöƒπüùπü╛πüùπüƒπÇé"
            else:
                error_text = "╨ƒ╤Ç╨╛╨╕╨╖╨╛╤ê╨╗╨░ ╨╛╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╤ü╨╛╨╖╨┤╨░╨╜╨╕╨╕ ╨│╤Ç╨░╤ä╨╕╨║╨░."
            await message.answer(error_text)
        except Exception:
            import traceback; traceback.print_exc()