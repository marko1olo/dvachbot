@dp.message(Command("summarize", "sum", "summary", "samamri", "sammary"))
async def cmd_summarize(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        print("[summarize] Board ID not found")
        await message.answer("╨₧╤ê╨╕╨▒╨║╨░: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╛╨┐╤Ç╨╡╨┤╨╡╨╗╨╕╤é╤î ╨┤╨╛╤ü╨║╤â.")
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now_ts = time.time()
    # ╨Æ╤ï╨┤╨╡╨╗╨╡╨╜╨╜╨╛╨│╨╛ ╨╗╨╛╨║╨░ ╤â /summarize ╨╜╨╡╤é, ╨┐╨╛╤ì╤é╨╛╨╝╤â storage_lock ╨╛╤ü╤é╨░╨▓╨╗╨╡╨╜, ╨╜╨╛ ╤ü╨╢╨░╤é
    # ╨┤╨╛ ╤ü╨░╨╝╨╛╨│╨╛ ╤Ç╨╡╤ê╨╡╨╜╨╕╤Å: ╤Ç╨░╨╜╤î╤ê╨╡ ╨▓╨╜╤â╤é╤Ç╨╕ ╨╜╨╡╨│╨╛ ╤ê╨╗╨╕ ╨┤╨▓╨░ ╤ü╨╡╤é╨╡╨▓╤ï╤à ╨▓╤ï╨╖╨╛╨▓╨░ Telegram.
    remaining = 0
    async with storage_lock:
        last_usage = b_data.get('last_summarize_time', 0)
        on_cooldown = now_ts - last_usage < SUMMARIZE_COOLDOWN
        if on_cooldown:
            remaining = SUMMARIZE_COOLDOWN - (now_ts - last_usage)
        else:
            b_data['last_summarize_time'] = time.time()
    if on_cooldown:
        if lang == 'en':
            cooldown_text = f"ΓÅ│ Command is on cooldown. Please wait {int(remaining)} seconds."
        elif lang == 'jp':
            cooldown_text = f"ΓÅ│ πé│πâ₧πâ│πâëπü»πé»πâ╝πâ½πâÇπéªπâ│Σ╕¡πüºπüÖπÇéπüéπü¿ {int(remaining)} τºÆπüèσ╛àπüíπüÅπüáπüòπüäπÇé"
        else:
            cooldown_text = f"ΓÅ│ ╨Ü╨╛╨╝╨░╨╜╨┤╨░ ╨╜╨░ ╨║╤â╨╗╨┤╨░╤â╨╜╨╡. ╨ƒ╨╛╨┤╨╛╨╢╨┤╨╕╤é╨╡ ╨╡╤ë╨╡ {int(remaining)} ╤ü╨╡╨║."
        try:
            await message.answer(cooldown_text)
            await message.delete()
        except Exception:
            import traceback; traceback.print_exc()
        return
    thread_id = None
    thread_info = {}

    board_name = escape_html(BOARD_CONFIG[board_id]['name'])
    if lang == 'en':
        context_name = f"board {board_name}"
    elif lang == 'jp':
        context_name = f"µ¥┐ {board_name}"
    else:
        context_name = f"╨┤╨╛╤ü╨║╨╕ {board_name}"

    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
        if user_location != 'main':
            thread_id = user_location
            thread_info = b_data.get('threads_data', {}).get(thread_id, {})
            thread_title = thread_info.get('title', '...')
            if lang == 'en':
                context_name = f"thread \"{thread_title}\""
            elif lang == 'jp':
                context_name = f"πé╣πâ¼πââπâëπÇî{thread_title}πÇì"
            else:
                context_name = f"╤é╤Ç╨╡╨┤╨░ ┬½{thread_title}┬╗"

    paragraph_count, length_choice, model_preference, chosen_tier = _parse_summarize_args(message.text or message.caption or "")
    
    # ╨ö╨╡╤é╨╡╨║╤å╨╕╤Å ╨▒╨╗╨░╤é╨╜╨╛╨│╨╛ ╨╕ ╨▓╨░╤Ç╤à╨░╨╝╨╝╨╡╤Ç ╤Ç╨╡╨╢╨╕╨╝╨╛╨▓
    is_blat = None
    is_warhammer = None
    if message.text:
        txt_l = (message.text or message.caption or "").lower()
        if any(term in txt_l for term in ['blat', '╨▒╨╗╨░╤é', '╨│╨╛╨┐', '╨│╨╛╨┐╨╜╨╕╨║', '╨┐╨░╤å╨░╨╜╤ü╨║╨╕╨╣', '╨░╤â╨╡', '╨░╤â╨╡╤ê╨║╨░', 'patsan']):
            is_blat = True
        elif any(term in txt_l for term in ['wh40k', 'waha', 'warhammer', '╨▓╨░╤Ç╤à╨░╨╝╨╝╨╡╤Ç', '╨╕╨╜╨║╨▓╨╕╨╖╨╕╤å╨╕╤Å']):
            is_warhammer = True

    # Generate prompt and retrieve chat chunk
    prompt, info_text, chunk, is_blat, is_warhammer = await _get_summarize_prompt_and_chunk(
        board_id, thread_id, thread_info, lang, paragraph_count, is_blat=is_blat, is_warhammer=is_warhammer
    )

    hf_token = os.getenv("HF_TOKEN")
    if not chunk or len(chunk) < 100:
        logger.info(f"[summarize] ╨£╨░╨╗╨╛ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╣ ╨┤╨╗╤Å summarize (len={len(chunk) if chunk else 0})")
        if lang == 'en':
            err_msg = f"{info_text} there were too few messages to summarize."
        elif lang == 'jp':
            err_msg = f"{info_text} πé╡πâ₧πâ¬πâ╝πéÆΣ╜£µêÉπüÖπéïπü«πü½σìüσêåπü¬πâíπââπé╗πâ╝πé╕πüîπüéπéèπü╛πü¢πéôπüºπüùπüƒπÇé"
        else:
            err_msg = f"{info_text} ╨▒╤ï╨╗╨╛ ╨╝╨░╨╗╨╛ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╣ ╨┤╨╗╤Å ╤ü╨░╨╝╨╝╨░╤Ç╨╕."
        await message.answer(err_msg)
        return

    status_text = _get_summarize_status_text(lang, length_choice, paragraph_count)
    await message.answer(status_text)

    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token, model_preference=model_preference)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[summarize] Error during HF summarize: {e}")
        if lang == 'en':
            err_msg = "Error generating summary."
        elif lang == 'jp':
            err_msg = "πé╡πâ₧πâ¬πâ╝πü«τöƒµêÉΣ╕¡πü½πé¿πâ⌐πâ╝πüîτÖ║τöƒπüùπü╛πüùπüƒπÇé"
        else:
            err_msg = "╨₧╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕ ╤ü╨░╨╝╨╝╨░╤Ç╨╕."
        await message.answer(err_msg)
        return

    if not summary:
        print("[summarize] Summary empty or failed")
        if lang == 'en':
            err_msg = "Could not generate summary. Try again later."
        elif lang == 'jp':
            err_msg = "πé╡πâ₧πâ¬πâ╝πéÆΣ╜£µêÉπüºπüìπü╛πü¢πéôπüºπüùπüƒπÇéσ╛îπü╗πü⌐πééπüåΣ╕Çσ║ªπüèΦ⌐ªπüùπüÅπüáπüòπüäπÇé"
        else:
            err_msg = "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨┤╨╡╨╗╨░╤é╤î ╤ü╨░╨╝╨╝╨░╤Ç╨╕. ╨ƒ╨╛╨┐╤Ç╨╛╨▒╤â╨╣ ╨┐╨╛╨╖╨╢╨╡."
        await message.answer(err_msg)
        return

    should_use_telegraph = (is_blat or is_warhammer or paragraph_count >= 5 or len(summary) >= 900)
    telegraph_url = None

    if should_use_telegraph:
        date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        if is_warhammer:
            title = f"╨ö╨╛╤ü╤î╨╡ ╨ÿ╨╜╨║╨▓╨╕╨╖╨╕╤å╨╕╨╕ ╨₧╤Ç╨┤╨╛ ╨£╨░╨╗╨╗╨╡╤â╤ü - {date_str}"
            author_name = "╨ÿ╨╜╨║╨▓╨╕╨╖╨╕╤é╨╛╤Ç ╨₧╤Ç╨┤╨╛ ╨£╨░╨╗╨╗╨╡╤â╤ü"
        elif is_blat:
            title = f"╨Æ╨╛╤Ç╨╛╨▓╤ü╨║╨╛╨╣ ╨┐╤Ç╨╛╨│╨╛╨╜ ╨╕╨╖ ╨Ü╨╕╨▒╨╡╤Ç-╨Ñ╨░╤é╤ï - {date_str}"
            author_name = "╨Ü╨╕╨▒╨╡╤Ç-╨í╨╝╨╛╤é╤Ç╤Å╤ë╨╕╨╣"
        elif lang == 'en':
            title = f"Summary of {context_name} - {date_str}"
            author_name = "TGACH"
        elif lang == 'jp':
            title = f"{context_name} πü«Φªüτ┤ä - {date_str}"
            author_name = "TGACH"
        else:
            title = f"╨í╨░╨╝╨╝╨░╤Ç╨╕ {context_name} - {date_str}"
            author_name = "╨ó╨ô╨É╨º"

        telegraph_url = await create_telegraph_page_async(title, summary, author=author_name)

        if telegraph_url:
            if is_warhammer:
                summary = (
                    f"ΓÜö∩╕Å <b>╨í╨Æ╨»╨⌐╨ò╨¥╨¥╨₧╨ò ╨ö╨₧╨í╨¼╨ò ╨ÿ╨¥╨Ü╨Æ╨ÿ╨ù╨ÿ╨ª╨ÿ╨ÿ ({date_str})</b> ΓÜö∩╕Å\n\n"
                    f"╨¢╨╛╤Ç╨┤-╨ÿ╨╜╨║╨▓╨╕╨╖╨╕╤é╨╛╤Ç ╨₧╤Ç╨┤╨╛ ╨£╨░╨╗╨╗╨╡╤â╤ü ╨╖╨░╨▓╨╡╤Ç╤ê╨╕╨╗ ╤Ç╨░╤ü╤ü╨╗╨╡╨┤╨╛╨▓╨░╨╜╨╕╨╡ ╨╡╤Ç╨╡╤ü╨╕ ╨▓ ╤ü╨╡╨║╤é╨╛╤Ç╨╡ /{board_id}/.\n\n"
                    f"≡ƒ¢í <b>╨Æ╤ï╤Å╨▓╨╗╨╡╨╜╨╜╤ï╨╡ ╨╡╤Ç╨╡╤é╨╕╨║╨╕ ╨╕ ╨║╤ü╨╡╨╜╨╛╤ü╤ï</b>\n≡ƒöÑ <b>╨₧╤å╨╡╨╜╨║╨░ ╨╕╨╜╨┤╨╡╨║╤ü╨░ ╨¡╨║╤ü╤é╨╡╤Ç╨╝╨╕╨╜╨░╤é╤â╤ü╨░</b>\n≡ƒô£ <b>╨ú╨║╨░╨╖╤ï ╨╕ ╨£╤ï╤ü╨╗╨╕ ╨ö╨╜╤Å</b>\n\n"
                    f"≡ƒæë <b><a href='{telegraph_url}'>╨Æ╤ü╨║╤Ç╤ï╤é╤î ╨ö╨╛╤ü╤î╨╡ ╨ÿ╨╜╨║╨▓╨╕╨╖╨╕╤å╨╕╨╕</a></b>"
                )
            elif is_blat:
                intros = [
                    "ΓÜí∩╕Å ╨Æ╨╡╤ç╨╡╤Ç ╨▓ ╤à╨░╤é╤â, ╨▒╨╛╤ü╨╛╤é╨░! ╨ƒ╨╛╨║╨░ ╨▓╤ï ╤ü╨┐╨░╨╗╨╕, ╤Å ╤é╤â╤é ╤ü╨▓╨╡╨╢╨╕╨╡ ╨╝╨░╨╗╤Å╨▓╤ï ╨┐╨╛╤ç╨╕╤é╨░╨╗.",
                    "Γÿò∩╕Å ╨º╨░╤ü╨╕╨║ ╨▓ ╤Ç╨░╨┤╨╛╤ü╤é╤î, ╤ç╨╕╤ä╨╕╤Ç ╨▓ ╤ü╨╗╨░╨┤╨╛╤ü╤é╤î! ╨¥╨░╨║╨░╤é╨░╨╗ ╨▓╨░╨╝ ╨┐╤Ç╨╛╨│╨╛╨╜ ╨╖╨░ ╤ü╨╡╨│╨╛╨┤╨╜╤Å.",
                    "≡ƒæÇ ╨ù╨╡╨╜╨║╨╕ ╨┐╤Ç╨╛╤é╤Ç╨╕╤é╨╡, ╤ä╤Ç╨░╨╡╤Ç╨░. ╨í╨╝╨╛╤é╤Ç╤Å╤ë╨╕╨╣ ╤Ç╨░╤ü╨║╨╕╨┤╨░╨╗ ╨┐╨╛ ╨┐╨╛╨╜╤Å╤é╨╕╤Å╨╝ ╨║╤é╨╛ ╨╡╤ü╤é╤î ╨║╤é╨╛ ╨▓ ╤ç╨░╤é╨╡.",
                    "≡ƒÄ⌐ ╨á╨░╤ü╨║╨╗╨░╨┤ ╨┐╨╛ ╤à╨░╤é╨╡ ╨│╨╛╤é╨╛╨▓. ╨₧╤ü╤é╨╛╤Ç╨╛╨╢╨╜╨╛, ╨╝╨╜╨╛╨│╨╛ ╨╛╨┐╤â╤ë╨╡╨╜╨╜╤ï╤à ╨┐╨░╤ü╤ü╨░╨╢╨╕╤Ç╨╛╨▓.",
                    "≡ƒö¬ ╨₧╤é╨┤╨╡╨╗╨╕╨╗ ╤Ç╨╛╨▓╨╜╤ï╤à ╨┐╨░╤å╨░╨╜╨╛╨▓ ╨╛╤é ╨┐╨╡╤é╤â╤ê╨╜╨╕. ╨Æ╨╡╤ü╤î ╤Ç╨░╤ü╨║╨╗╨░╨┤ ╨┐╨╛ ╤ü╤ü╤ï╨╗╨║╨╡."
                ]
                bullet_sets = [
                    "≡ƒöÑ <b>╨Ü╨╛╨│╨╛ ╤ü╨╡╨│╨╛╨┤╨╜╤Å ╨╛╨┐╤Ç╨╡╨┤╨╡╨╗╤Å╨╗╨╕ ╤â ╨┐╨░╤Ç╨░╤ê╨╕</b>\n≡ƒö¬ <b>╨ƒ╤Ç╨╡╨┤╤è╤Å╨▓╤ï ╨╖╨░ ╨│╨╜╨╕╨╗╤ï╨╡ ╨▓╨▒╤Ç╨╛╤ü╤ï</b>\n≡ƒ¢á <b>╨æ╨░╨╖╨░╤Ç ╨╖╨░ ╨┤╨▓╨╕╨╢╤â╤à╤â</b>",
                    "≡ƒ¢æ <b>╨á╨░╨╖╨▒╨╛╤Ç ╨║╨╛╤ü╤Å╨║╨╛╨▓ ╨╕ ╨║╨╕╨┤╨░╨╗╨╛╨▓╨░</b>\n≡ƒñí <b>╨Ü╨╗╨╛╤â╨╜╤ï ╨┤╨╜╤Å ╨╕ ╨╕╤à ╨▓╤ï╤ü╨╡╤Ç╤ï</b>\nΓÜö∩╕Å <b>╨É╤Ç╨│╤â╨╝╨╡╨╜╤é╤ï ╨╕╨╖ ╨│╨╛╤Ç╤Å╤ç╨╕╤à ╤à╨╛╨╗╨╕╨▓╨░╤Ç╨╛╨▓</b>",
                    "≡ƒÆ░ <b>╨ÿ╨╜╤ü╨░╨╣╨┤╤ï ╨┐╨╛ ╤ê╨╡╨║╨╡╨╗╤Å╨╝ ╨╕ ╨╛╨▒╤ë╨░╨║╤â</b>\n≡ƒô╕ <b>╨¿╨╝╨╛╨╜ ╨┐╨╛ ╤ü╨║╤Ç╨╕╨╜╨░╨╝</b>\n≡ƒºá <b>╨í╨╛╨▓╨╡╤é╤ï ╨╛╤é ╤Ç╨╛╨▓╨╜╤ï╤à ╨▒╤Ç╨╛╨┤╤Å╨│</b>"
                ]
                ctas = [
                    "≡ƒæë <b><a href='{url}'>╨º╨╕╤é╨░╤é╤î ╨▓╨╛╤Ç╨╛╨▓╤ü╨║╨╛╨╣ ╨┐╤Ç╨╛╨│╨╛╨╜</a></b>",
                    "≡ƒôû <b><a href='{url}'>╨Æ╤ü╨║╤Ç╤ï╤é╤î ╨╝╨░╨╗╤Å╨▓╤â</a></b>",
                    "ΓÜí∩╕Å <b><a href='{url}'>╨ƒ╤Ç╨╛╨▒╨╕╤é╤î ╨┐╨░╤ü╤ü╨░╨╢╨╕╤Ç╨╛╨▓</a></b>"
                ]
                summary = (
                    f"ΓÖá∩╕Å <b>╨í╨▓╨╡╨╢╨╕╨╣ ╤Ç╨░╤ü╨║╨╗╨░╨┤ ╨┐╨╛ ╤ç╨░╤é╤â ({date_str})</b>\n\n"
                    f"{random.choice(intros)}\n\n"
                    f"{random.choice(bullet_sets)}\n\n"
                    f"{random.choice(ctas).format(url=telegraph_url)}"
                )
            elif lang == 'en':
                summary = f"≡ƒô¥ <b>DETAILED SUMMARY ({context_name})</b>\n\nToo long to post here! I've published it as a Telegraph article:\n≡ƒöù <a href=\"{telegraph_url}\">Read on Telegraph</a>"
            elif lang == 'jp':
                summary = f"≡ƒô¥ <b>Φ⌐│τ┤░πü¬Φªüτ┤ä ({context_name})</b>\n\nπüôπüôπü½πü»σÅÄπü╛πéèπüìπéëπü¬πüäπüƒπéüπÇüTelegraphπü½µèòτ¿┐πüùπü╛πüùπüƒ∩╝Ü\n≡ƒöù <a href=\"{telegraph_url}\">TelegraphπüºΦ¬¡πéÇ</a>"
            else:
                summary = f"≡ƒô¥ <b>╨ò╨æ╨É╨¥╨ú╨ó╨½╨Ö ╨¢╨₧╨¥╨ô╨á╨ÿ╨ö ({context_name})</b>\n\n╨¥╨╡ ╨╛╤ü╨╕╨╗╨╕╨╗ ╨┐╤Ç╨╛╤ç╨╕╤é╨░╤é╤î ╤ç╨░╤é? ╨í╤é╨░╤Ç╤ï╨╣ ╨░╨╜╨╛╨╜ ╤Ç╨░╤ü╨┐╨╕╤ü╨░╨╗ ╨▓╤ü╤æ ╨┐╨╛ ╨┐╨╛╨╗╨╛╤ç╨║╨░╨╝ ╨▓ ╤ì╤é╨╛╨╣ ╤ü╤é╨░╤é╤î╨╡:\n≡ƒöù <a href=\"{telegraph_url}\">╨º╨╕╤é╨░╤é╤î ╨╜╨░ Telegraph</a>"
        else:
            print("[summarize] Telegraph creation failed, falling back to direct message")
            # Telegram counts chars in UTF-16 code units: Cyrillic/CJK = 2 units each.
            # Hard limit = 4096 UTF-16 units. Safe budget = 3500 (prefix takes ~100-200 more).
            summary = _tg_safe_truncate(summary, max_utf16=3500)
    else:
        if is_blat:
            signet = (
                "\n\n<i><b>ΓÖá∩╕Å ╨£╨░╨╗╤Å╨▓╨░ ╤ü╨╛╤ü╤é╨░╨▓╨╗╨╡╨╜╨░ ╨í╨╝╨╛╤é╤Ç╤Å╤ë╨╕╨╝.</b>\n"
                "╨û╨╕╨╖╨╜╤î ╨▓╨╛╤Ç╨░╨╝, ╤à╤â╨╣ ╨╝╤â╤ü╨╛╤Ç╨░╨╝! ╨É╨ú╨ò!</i>"
            )
            if "╨£╨░╨╗╤Å╨▓╨░ ╤ü╨╛╤ü╤é╨░╨▓╨╗╨╡╨╜╨░ ╨í╨╝╨╛╤é╤Ç╤Å╤ë╨╕╨╝" not in summary:
                # Truncate body first, then append signet so footer is always visible
                summary = _tg_safe_truncate(summary, max_utf16=3000)
                summary += signet
        else:
            summary = _tg_safe_truncate(summary, max_utf16=3500)

    logger.debug(f"[summarize] Final summary length: {len(summary)}")
    now_dt = datetime.now(UTC)

    if should_use_telegraph and telegraph_url:
        post_text = summary
    else:
        if is_blat:
            post_text = summary
        elif lang == 'en':
            post_text = f"Summary of {context_name}:\n\n{summary}"
        elif lang == 'jp':
            post_text = f"{context_name} πü«Φªüτ┤ä:\n\n{summary}"
        else:
            post_text = f"╨í╨░╨╝╨╝╨░╤Ç╨╕ {context_name}:\n\n{summary}"
        # Final safety clamp on post_text
        post_text = _tg_safe_truncate(post_text, max_utf16=4000)

    content = {
        'type': 'text',
        'text': post_text,
        'is_system_message': True,
        'archive_allowed': True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream,
        thread_id_from_bot=thread_id
    )
    if not pnum:
        print(f"Γ¢ö [{board_id}] ╨Ü╨á╨ÿ╨ó╨ÿ╨º╨ò╨í╨Ü╨É╨» ╨₧╨¿╨ÿ╨æ╨Ü╨É: ╨╜╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╤ü╨╛╨╖╨┤╨░╤é╤î ╨┐╨╛╤ü╤é ╨▓ ╨æ╨ö ╨┤╨╗╤Å /summarize.")
        return
    header_text = await format_header(board_id, pnum)
    content['header'] = header_text
    await update_post_content(pnum, content)
    recipients = set()
    if thread_id:
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if thread_info and not thread_info.get('is_archived'):
            recipients = thread_info.get('subscribers', set())
    else:
        recipients = b_data['users']['active']
    if recipients:
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 'timestamp': now_dt, 'content': content,
                'board_id': board_id, 'thread_id': thread_id
            }
        await enqueue_board_message(board_id, {
            "recipients": recipients, "content": content, "post_num": pnum, 
            "board_id": board_id, "thread_id": thread_id
        })
    else:
        await delete_post_by_num(pnum)
        if lang == 'en':
            err_msg = "Failed to send summary, thread is no longer active."
        elif lang == 'jp':
            err_msg = "πé╡πâ₧πâ¬πâ╝πéÆΘÇüΣ┐íπüºπüìπü╛πü¢πéôπüºπüùπüƒπÇéπé╣πâ¼πââπâëπüîπéóπé»πâåπéúπâûπüºπü»πüéπéèπü╛πü¢πéôπÇé"
        else:
            err_msg = "╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╛╤é╨┐╤Ç╨░╨▓╨╕╤é╤î ╤ü╨░╨╝╨╝╨░╤Ç╨╕, ╤é╤Ç╨╡╨┤ ╨▒╨╛╨╗╤î╤ê╨╡ ╨╜╨╡ ╨░╨║╤é╨╕╨▓╨╡╨╜."
        await message.answer(err_msg)
        return
    logger.info(f"[summarize] ╨í╨░╨╝╨╝╨░╤Ç╨╕ ╤â╤ü╨┐╨╡╤ê╨╜╨╛ ╨╛╤é╨┐╤Ç╨░╨▓╨╗╨╡╨╜╨╛ ({context_name}, post_num={pnum})")