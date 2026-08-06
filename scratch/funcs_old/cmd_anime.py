@dp.message(Command("anime", "nya", "kawai", "kawaii"))
async def cmd_anime(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "πü½πéâπüé∩╜₧∩╝üπéóπâïπâíπâóπâ╝πâëπüîπéóπé»πâåπéúπâÖπâ╝πâêπüòπéîπü╛πüùπüƒ∩╝ü\n\n^_^",
        "πüèσàäπüíπéâπéôπÇüσñºσñë∩╝üπéóπâïπâíπâóπâ╝πâëπü«µÖéΘûôπüáπéê∩╝ü UWU",
        "πéóπâïπâíπü«σè¢πüîπüôπü«πâüπâúπââπâêπü½µ║Çπüíπüªπüäπü╛πüÖ∩╝ü(∩╛ë┬┤πâ«┬┤)∩╛ë*:∩╜Ñ∩╛ƒΓ£º",
        "πÇÄπâùπâ¡πé╕πéºπé»πâêAπÇÅτÖ║σïò∩╝üπüôπéîπéêπéèπâüπâúπââπâêπü»πéóπé¡πâÅπâÉπâ⌐Φç¬µ▓╗σî║πü¿πü¬πéï∩╝ü",
        "πüôπü«πâüπâúπââπâêπü»πÇîΣ║║ΘûôπÇìπéÆπéäπéüπéïπü₧∩╝üπé╕πâºπé╕πâºπâ╝πâ╝πââ∩╝ü\n\nπéó πâï πâí πâó πâ╝ πâë πüá∩╝ü",
        "σÉ¢πéé... Φªïπüêπéïπü«πüï∩╝ƒπÇÄπâüπâúπââπâêπü«πé╣πé┐πâ│πâëπÇÅπüî...∩╝üπéóπâïπâíπâóπâ╝πâëτÖ║σïò∩╝ü",
        "πâüπâúπââπâêπü«τÜåπüòπéôπÇüΦü₧πüäπüªπüÅπüáπüòπüä∩╝üτºüπÇüΘ¡öµ│òσ░æσÑ│πü½πü¬πüúπüíπéâπüúπüƒ∩╝ü\n\nπéóπâïπâíπâóπâ╝πâëπÇüπé¬πâ│∩╝ü",
        "Σ╕ëτÖ╛σ╣┤πü«σ¡ñτï¼πü½πÇüσàëπüîσ░äπüùπüƒΓÇª πéóπâïπâíπâóπâ╝πâëπü«µÖéΘûôπüáπÇé",
        "τò░Σ╕ûτòîΦ╗óτöƒπüùπüƒπéëπâüπâúπââπâêπüîσà¿Θâ¿µùÑµ£¼Φ¬₧πü½πü¬πüúπüªπüäπüƒΣ╗╢πÇé\n\nπéóπâïπâíπâóπâ╝πâëπÇüπé╣πé┐πâ╝πâê∩╝ü",
        "≡ƒî╕ πüèσëìπü»πééπüåµ¡╗πéôπüºπüäπéï... ╨É╨¥╨ÿ╨£╨ò ╨á╨ò╨û╨ÿ╨£: OMAE WA MOU SHINDEIRU!",
        "Γ£º∩╜Ñ∩╛ƒ: *Γ£º∩╜Ñ∩╛ƒΓÖí ╨Æ╨Ü╨¢╨«╨º╨É╨ò╨£ ╨Ü╨É╨Æ╨É╨Ö╨¥╨½╨Ö ╨É╨ö! ΓÖí∩╜Ñ∩╛ƒΓ£º*:∩╜Ñ∩╛ƒΓ£º",
        "ΓÜí σìâ µ£¼ µí£ ΓÜí ╨¥╨»!",
        "πü░πüï∩╝üπü╕πéôπüƒπüä∩╝üπüÖπüæπü╣∩╝üπéóπâïπâíπâóπâ╝πâëπü«µÖéΘûôπü¬πéôπüáπüïπéëπü¡∩╝ü",
        "πéóπâïπâíπâóπâ╝πâëπÇüτÖ║σïò∩╝üπü┐πéôπü¬πüºΣ╕Çτ╖Æπü½πé½πâ»πéñπéñπéÆσÅ½πü╝πüå∩╝ü",
        "πéóπâïπâíπâóπâ╝πâëπüîσºïπü╛πüúπüƒπéê∩╝üπü┐πéôπü¬πÇüµ║ûσéÖπü»πüäπüä∩╝ƒ",
        "πéóπâïπâíπâóπâ╝πâëπÇüπé¬πâ│∩╝üπüòπüéπÇüπü┐πéôπü¬πüºµÑ╜πüùπüäµÖéΘûôπéÆΘüÄπüöπü¥πüå∩╝ü",
        "πéóπâïπâíπâóπâ╝πâëπÇüτÖ║σïò∩╝üπü┐πéôπü¬πüºΣ╕Çτ╖Æπü½πé½πâ»πéñπéñπéÆσÅ½πü╝πüå∩╝ü"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True,
        "archive_allowed": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"Γ¢ö [{board_id}] ╨Ü╨á╨ÿ╨ó╨ÿ╨º╨ò╨í╨Ü╨É╨» ╨₧╨¿╨ÿ╨æ╨Ü╨É: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨╛╨╖╨┤╨░╤é╤î ╨┐╨╛╤ü╤é ╨▓ ╨æ╨ö ╨┤╨╗╤Å ╨░╨║╤é╨╕╨▓╨░╤å╨╕╨╕ ╤Ç╨╡╨╢╨╕╨╝╨░ anime.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### τ«íτÉåΦÇà ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'anime_mode')
    disable_task = spawn_task(disable_mode_after_delay(330, board_id, 'anime_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        import traceback; traceback.print_exc()