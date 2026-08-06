@dp.message(Command("restrict_anime"))
async def cmd_restrict_anime(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return

    target_id = None
    args = (message.text or message.caption or "").split()
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len(args) > 1 and args[1].isdecimal():
        # isdecimal, не isdigit — см. пояснение в cmd_random_media
        target_id = int(args[1])

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if not target_id:
        msg = "Usage: <code>/restrict_anime &lt;id&gt;</code> or reply." if lang != 'ru' else "Использование: <code>/restrict_anime &lt;id&gt;</code> или ответ на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return

    b_data = board_data[board_id]
    async with storage_lock:
        if target_id in b_data['anime_strict_limits']:
            b_data['anime_strict_limits'].remove(target_id)
            action_log = "REMOVED FROM STRICT LIMITS"
            if lang == 'en':
                res = f"✅ User <code>{target_id}</code> removed from strict anime limits."
            elif lang == 'jp':
                res = f"✅ ユーザー <code>{target_id}</code> のアニメリミットを解除しました。"
            else:
                res = f"✅ С пользователя <code>{target_id}</code> снято жесткое ограничение на аниме."
        else:
            b_data['anime_strict_limits'].add(target_id)
            action_log = "ADDED TO STRICT LIMITS (10/day)"
            if lang == 'en':
                res = f"🚫 User <code>{target_id}</code> now restricted to 10 anime images per 24h."
            elif lang == 'jp':
                res = f"🚫 ユーザー <code>{target_id}</code> に1日10枚の制限をかけました。"
            else:
                res = f"🚫 Пользователю <code>{target_id}</code> установлено ограничение: 10 картинок в сутки."

    await log_global_event('bot', f"🛡️ ANIME_LIMIT: Админ {message.from_user.id} {action_log} для {target_id} на /{board_id}/")
    await message.answer(res, parse_mode="HTML")
    try:
        await message.delete()
    except Exception:
        import traceback; traceback.print_exc()