@dp.message(Command("ban"))
async def cmd_ban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    parts = (message.text or message.caption or "").split()
    if len(parts) == 2:
        try: target_id = int(parts[1])
        except ValueError: pass
    if not target_id:
        await message.answer("Нужно ответить на сообщение или указать ID: <code>/ban &lt;id&gt;</code>", parse_mode="HTML")
        return

    anon_name = generate_anon_name(target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Да, сжечь!", callback_data=f"admin_action:ban:{target_id}:{board_id}:0"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_action:cancel:0:0:0")
        ]
    ])
    await message.answer(f"⚠️ Вы уверены, что хотите забанить <b>{anon_name}</b> (ID: <code>{target_id}</code>) и снести его последние посты?", parse_mode="HTML", reply_markup=kb)
    try: await message.delete()
    except Exception: pass