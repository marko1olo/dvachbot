@dp.message(Command("summarize", "sum", "summary", "samamri", "sammary"))
async def cmd_summarize(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        print("[summarize] Board ID not found")
        await message.answer("Ошибка: не удалось определить доску.")
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now_ts = time.time()
    # Выделенного лока у /summarize нет, поэтому storage_lock оставлен, но сжат
    # до самого решения: раньше внутри него шли два сетевых вызова Telegram.
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
            cooldown_text = f"⏳ Command is on cooldown. Please wait {int(remaining)} seconds."
        elif lang == 'jp':
            cooldown_text = f"⏳ コマンドはクールダウン中です。あと {int(remaining)} 秒お待ちください。"
        else:
            cooldown_text = f"⏳ Команда на кулдауне. Подождите еще {int(remaining)} сек."
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
        context_name = f"板 {board_name}"
    else:
        context_name = f"доски {board_name}"

    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
        if user_location != 'main':
            thread_id = user_location
            thread_info = get_thread_info(board_id, thread_id)
            thread_title = thread_info.get('title', '...')
            if lang == 'en':
                context_name = f"thread \"{thread_title}\""
            elif lang == 'jp':
                context_name = f"スレッド「{thread_title}」"
            else:
                context_name = f"треда «{thread_title}»"

    paragraph_count, length_choice, model_preference, chosen_tier = _parse_summarize_args(message.text or message.caption or "")
    
    # Детекция блатного и вархаммер режимов
    is_blat = None
    is_warhammer = None
    if message.text:
        txt_l = (message.text or message.caption or "").lower()
        if any(term in txt_l for term in ['blat', 'блат', 'гоп', 'гопник', 'пацанский', 'ауе', 'ауешка', 'patsan']):
            is_blat = True
        elif any(term in txt_l for term in ['wh40k', 'waha', 'warhammer', 'вархаммер', 'инквизиция']):
            is_warhammer = True

    # Generate prompt and retrieve chat chunk
    prompt, info_text, chunk, is_blat, is_warhammer = await _get_summarize_prompt_and_chunk(
        board_id, thread_id, thread_info, lang, paragraph_count, is_blat=is_blat, is_warhammer=is_warhammer
    )

    hf_token = os.getenv("HF_TOKEN")
    if not chunk or len(chunk) < 100:
        logger.info(f"[summarize] Мало сообщений для summarize (len={len(chunk) if chunk else 0})")
        if lang == 'en':
            err_msg = f"{info_text} there were too few messages to summarize."
        elif lang == 'jp':
            err_msg = f"{info_text} サマリーを作成するのに十分なメッセージがありませんでした。"
        else:
            err_msg = f"{info_text} было мало сообщений для саммари."
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
            err_msg = "サマリーの生成中にエラーが発生しました。"
        else:
            err_msg = "Ошибка при генерации саммари."
        await message.answer(err_msg)
        return

    if not summary:
        print("[summarize] Summary empty or failed")
        if lang == 'en':
            err_msg = "Could not generate summary. Try again later."
        elif lang == 'jp':
            err_msg = "サマリーを作成できませんでした。後ほどもう一度お試しください。"
        else:
            err_msg = "Не удалось сделать саммари. Попробуй позже."
        await message.answer(err_msg)
        return

    should_use_telegraph = (is_blat or is_warhammer or paragraph_count >= 5 or len(summary) >= 900)
    telegraph_url = None

    if should_use_telegraph:
        date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        if is_warhammer:
            title = f"Досье Инквизиции Ордо Маллеус - {date_str}"
            author_name = "Инквизитор Ордо Маллеус"
        elif is_blat:
            title = f"Воровской прогон из Кибер-Хаты - {date_str}"
            author_name = "Кибер-Смотрящий"
        elif lang == 'en':
            title = f"Summary of {context_name} - {date_str}"
            author_name = "TGACH"
        elif lang == 'jp':
            title = f"{context_name} の要約 - {date_str}"
            author_name = "TGACH"
        else:
            title = f"Саммари {context_name} - {date_str}"
            author_name = "ТГАЧ"

        telegraph_url = await create_telegraph_page_async(title, summary, author=author_name)

        if telegraph_url:
            if is_warhammer:
                summary = (
                    f"⚔️ <b>СВЯЩЕННОЕ ДОСЬЕ ИНКВИЗИЦИИ ({date_str})</b> ⚔️\n\n"
                    f"Лорд-Инквизитор Ордо Маллеус завершил расследование ереси в секторе /{board_id}/.\n\n"
                    f"🛡 <b>Выявленные еретики и ксеносы</b>\n🔥 <b>Оценка индекса Экстерминатуса</b>\n📜 <b>Указы и Мысли Дня</b>\n\n"
                    f"👉 <b><a href='{telegraph_url}'>Вскрыть Досье Инквизиции</a></b>"
                )
            elif is_blat:
                intros = [
                    "⚡️ Вечер в хату, босота! Пока вы спали, я тут свежие малявы почитал.",
                    "☕️ Часик в радость, чифир в сладость! Накатал вам прогон за сегодня.",
                    "👀 Зенки протрите, фраера. Смотрящий раскидал по понятиям кто есть кто в чате.",
                    "🎩 Расклад по хате готов. Осторожно, много опущенных пассажиров.",
                    "🔪 Отделил ровных пацанов от петушни. Весь расклад по ссылке."
                ]
                bullet_sets = [
                    "🔥 <b>Кого сегодня определяли у параши</b>\n🔪 <b>Предъявы за гнилые вбросы</b>\n🛠 <b>Базар за движуху</b>",
                    "🛑 <b>Разбор косяков и кидалова</b>\n🤡 <b>Клоуны дня и их высеры</b>\n⚔️ <b>Аргументы из горячих холиваров</b>",
                    "💰 <b>Инсайды по шекелям и общаку</b>\n📸 <b>Шмон по скринам</b>\n🧠 <b>Советы от ровных бродяг</b>"
                ]
                ctas = [
                    "👉 <b><a href='{url}'>Читать воровской прогон</a></b>",
                    "📖 <b><a href='{url}'>Вскрыть маляву</a></b>",
                    "⚡️ <b><a href='{url}'>Пробить пассажиров</a></b>"
                ]
                summary = (
                    f"♠️ <b>Свежий расклад по чату ({date_str})</b>\n\n"
                    f"{random.choice(intros)}\n\n"
                    f"{random.choice(bullet_sets)}\n\n"
                    f"{random.choice(ctas).format(url=telegraph_url)}"
                )
            elif lang == 'en':
                summary = f"📝 <b>DETAILED SUMMARY ({context_name})</b>\n\nToo long to post here! I've published it as a Telegraph article:\n🔗 <a href=\"{telegraph_url}\">Read on Telegraph</a>"
            elif lang == 'jp':
                summary = f"📝 <b>詳細な要約 ({context_name})</b>\n\nここには収まりきらないため、Telegraphに投稿しました：\n🔗 <a href=\"{telegraph_url}\">Telegraphで読む</a>"
            else:
                summary = f"📝 <b>ЕБАНУТЫЙ ЛОНГРИД ({context_name})</b>\n\nНе осилил прочитать чат? Старый анон расписал всё по полочкам в этой статье:\n🔗 <a href=\"{telegraph_url}\">Читать на Telegraph</a>"
        else:
            print("[summarize] Telegraph creation failed, falling back to direct message")
            # Telegram counts chars in UTF-16 code units: Cyrillic/CJK = 2 units each.
            # Hard limit = 4096 UTF-16 units. Safe budget = 3500 (prefix takes ~100-200 more).
            summary = _tg_safe_truncate(summary, max_utf16=3500)
    else:
        if is_blat:
            signet = (
                "\n\n<i><b>♠️ Малява составлена Смотрящим.</b>\n"
                "Жизнь ворам, хуй мусорам! АУЕ!</i>"
            )
            if "Малява составлена Смотрящим" not in summary:
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
            post_text = f"{context_name} の要約:\n\n{summary}"
        else:
            post_text = f"Саммари {context_name}:\n\n{summary}"
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
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /summarize.")
        return
    header_text = await format_header(board_id, pnum)
    content['header'] = header_text
    await update_post_content(pnum, content)
    recipients = set()
    if thread_id:
        thread_info = get_thread_info(board_id, thread_id)
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
            err_msg = "サマリーを送信できませんでした。スレッドがアクティブではありません。"
        else:
            err_msg = "Не удалось отправить саммари, тред больше не активен."
        await message.answer(err_msg)
        return
    logger.info(f"[summarize] Саммари успешно отправлено ({context_name}, post_num={pnum})")