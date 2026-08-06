@dp.message(Command("anime", "nya", "kawai", "kawaii"))
async def cmd_anime(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "にゃあ～！アニメモードがアクティベートされました！\n\n^_^",
        "お兄ちゃん、大変！アニメモードの時間だよ！ UWU",
        "アニメの力がこのチャットに満ちています！(ﾉ´ヮ´)ﾉ*:･ﾟ✧",
        "『プロジェクトA』発動！これよりチャットはアキハバラ自治区となる！",
        "このチャットは「人間」をやめるぞ！ジョジョーーッ！\n\nア ニ メ モ ー ド だ！",
        "君も... 見えるのか？『チャットのスタンド』が...！アニメモード発動！",
        "チャットの皆さん、聞いてください！私、魔法少女になっちゃった！\n\nアニメモード、オン！",
        "三百年の孤独に、光が射した… アニメモードの時間だ。",
        "異世界転生したらチャットが全部日本語になっていた件。\n\nアニメモード、スタート！",
        "🌸 お前はもう死んでいる... АНИМЕ РЕЖИМ: OMAE WA MOU SHINDEIRU!",
        "✧･ﾟ: *✧･ﾟ♡ ВКЛЮЧАЕМ КАВАЙНЫЙ АД! ♡･ﾟ✧*:･ﾟ✧",
        "⚡ 千 本 桜 ⚡ НЯ!",
        "ばか！へんたい！すけべ！アニメモードの時間なんだからね！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！",
        "アニメモードが始まったよ！みんな、準備はいい？",
        "アニメモード、オン！さあ、みんなで楽しい時間を過ごそう！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！"
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
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима anime.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### 管理者 ###\n{header}"
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