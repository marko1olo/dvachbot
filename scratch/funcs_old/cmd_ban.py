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
        await message.answer("╨¥╤â╨╢╨╜╨╛ ╨╛╤é╨▓╨╡╤é╨╕╤é╤î ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ ╨╕╨╗╨╕ ╤â╨║╨░╨╖╨░╤é╤î ID: <code>/ban &lt;id&gt;</code>", parse_mode="HTML")
        return

    anon_name = generate_anon_name(target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="≡ƒöÑ ╨ö╨░, ╤ü╨╢╨╡╤ç╤î!", callback_data=f"admin_action:ban:{target_id}:{board_id}:0"),
            InlineKeyboardButton(text="Γ¥î ╨₧╤é╨╝╨╡╨╜╨░", callback_data="admin_action:cancel:0:0:0")
        ]
    ])
    await message.answer(f"ΓÜá∩╕Å ╨Æ╤ï ╤â╨▓╨╡╤Ç╨╡╨╜╤ï, ╤ç╤é╨╛ ╤à╨╛╤é╨╕╤é╨╡ ╨╖╨░╨▒╨░╨╜╨╕╤é╤î <b>{anon_name}</b> (ID: <code>{target_id}</code>) ╨╕ ╤ü╨╜╨╡╤ü╤é╨╕ ╨╡╨│╨╛ ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ ╨┐╨╛╤ü╤é╤ï?", parse_mode="HTML", reply_markup=kb)
    try: await message.delete()
    except Exception: pass