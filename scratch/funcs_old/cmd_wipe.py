@dp.message(Command("wipe"))
async def cmd_wipe(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    command_args = (message.text or message.caption or "").split()[1:]
    target_id = None
    duration_str = "1h" 
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
        if command_args: duration_str = command_args[0]
    elif command_args:
        try:
            target_id = int(command_args[0])
            if len(command_args) > 1: duration_str = command_args[1]
        except Exception:
            if message.reply_to_message:
                duration_str = command_args[0]
                target_id = await get_author_id_by_reply(message)
            else:
                await message.answer("Γ¥î Invalid User ID.")
                return
    if not target_id:
        await message.answer("Usage: <code>/wipe &lt;id&gt; [time]</code>", parse_mode="HTML")
        return
        
    duration_str = duration_str.lower().replace(" ", "")
    if duration_str.endswith("m"): minutes = int(duration_str[:-1])
    elif duration_str.endswith("h"): minutes = int(duration_str[:-1]) * 60
    elif duration_str.endswith("d"): minutes = int(duration_str[:-1]) * 60 * 24
    else:
        try: minutes = int(duration_str)
        except Exception: minutes = 60

    anon_name = generate_anon_name(target_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="≡ƒöÑ ╨ö╨░, ╤ü╨╢╨╡╤ç╤î!", callback_data=f"admin_action:wipe:{target_id}:{board_id}:{minutes}"),
            InlineKeyboardButton(text="Γ¥î ╨₧╤é╨╝╨╡╨╜╨░", callback_data="admin_action:cancel:0:0:0")
        ]
    ])
    await message.answer(f"ΓÜá∩╕Å ╨Æ╤ï ╤â╨▓╨╡╤Ç╨╡╨╜╤ï, ╤ç╤é╨╛ ╤à╨╛╤é╨╕╤é╨╡ ╨▓╨░╨╣╨┐╨╜╤â╤é╤î ╨┐╨╛╤ü╤é╤ï <b>{anon_name}</b> (ID: <code>{target_id}</code>) ╨╖╨░ ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ {minutes} ╨╝╨╕╨╜╤â╤é?", parse_mode="HTML", reply_markup=kb)
    try: await message.delete()
    except Exception: pass