@dp.message(Command("whois", "info"))
async def cmd_whois(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID needed." if lang == 'en' else "Нужен ID.")
        return
        
    anon_name = generate_anon_name(target_id)
    balance = 0
    post_count = 0
    try:
        async with db_lock:
            db = await get_pool()
            async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (target_id,)) as cursor:
                row = await cursor.fetchone()
                balance = row[0] if row and row[0] else 0
            async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (target_id,)) as cursor:
                row = await cursor.fetchone()
                post_count = row[0] if row and row[0] else 0
    except Exception: pass

    if lang == 'en': header = f"🗂 <b>Dossier on {anon_name}:</b>\n<code>{'—'*20}</code>"
    elif lang == 'jp': header = f"🗂 <b>{anon_name} の調査書:</b>\n<code>{'—'*20}</code>"
    else: header = f"🗂 <b>Досье на {anon_name}:</b>\n<code>{'—'*20}</code>"
    
    report = [header]
    report.append(f"🆔 <b>ID:</b> <code>{target_id}</code>")
    report.append(f"💸 <b>Баланс:</b> {int(balance)} RUB")
    report.append(f"💩 <b>Постов:</b> {post_count}")
    report.append(f"<code>{'—'*20}</code>")

    total_activity = False
    now_dt = datetime.now(UTC)
    for b_id in BOARDS:
        b_data = board_data[b_id]
        status = []
        if target_id in b_data['users']['banned']:
            status.append("🚫 BAN")
        elif target_id in b_data['users']['active']:
            status.append("✅ Active")
            
        mute_end = b_data['mutes'].get(target_id, datetime.min.replace(tzinfo=UTC))
        if mute_end > now_dt:
            td = mute_end - now_dt
            status.append(f"🔇 Mute ({int(td.total_seconds()//60)}m)")
            
        smute_end = b_data['shadow_mutes'].get(target_id, datetime.min.replace(tzinfo=UTC))
        if smute_end > now_dt:
            td = smute_end - now_dt
            status.append(f"👻 Shadow ({int(td.total_seconds()//60)}m)")
            
        u_set = b_data.get('user_settings', {}).get(target_id, {})
        if u_set.get('shadow_gif'): status.append("NoGIF")
        if u_set.get('shadow_sticker'): status.append("NoSticker")
        if u_set.get('lie_media'): status.append("LieMedia")
        spam_v_data = b_data.get('spam_violations', {}).get(target_id, {})
        spam_level = spam_v_data.get('level', 0) if isinstance(spam_v_data, dict) else 0
        if spam_level > 0: status.append(f"⚠️ Spam Level: {spam_level}")
        
        if status:
            total_activity = True
            board_name = BOARD_CONFIG[b_id]['name']
            report.append(f"<b>{board_name}</b>: {', '.join(status)}")
            
    if not total_activity:
        if lang == 'en': report.append("<i>No info (not active on any board).</i>")
        elif lang == 'jp': report.append("<i>情報なし（どの板でも活動していません）。</i>")
        else: report.append("<i>Информации нет (не активен ни на одной доске).</i>")
        
    await message.answer("\n".join(report), parse_mode="HTML")