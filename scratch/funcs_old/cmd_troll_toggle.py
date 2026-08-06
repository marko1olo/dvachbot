@dp.message(Command("troll"))
async def cmd_troll_toggle(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    
    parts = (message.text or message.caption or "").split()
    if not target_id and len(parts) > 1:
        try:
            target_id = int(parts[1])
        except ValueError:
            import traceback; traceback.print_exc()

    if not target_id:
        await message.answer("ΓÜá∩╕Å ╨₧╤é╨▓╨╡╤é╤î╤é╨╡ ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡ ╤Ä╨╖╨╡╤Ç╨░ ╨╕╨╗╨╕ ╤â╨║╨░╨╢╨╕╤é╨╡ ╨╡╨│╨╛ ID: <code>/troll &lt;ID&gt;</code>", parse_mode="HTML")
        return
    b_data = board_data[board_id]
    if 'troll_targets' not in b_data:
        b_data['troll_targets'] = set()
    
    if target_id in b_data['troll_targets']:
        b_data['troll_targets'].remove(target_id)
        await message.answer(f"Shadow-Troll OFF for {target_id}")
    else:
        b_data['troll_targets'].add(target_id)
        await message.answer(f"Shadow-Troll ON for {target_id}")
        
    # Also log global event
    from common.database import log_global_event
    await log_global_event('bot', f"≡ƒñí TROLL: Admin {message.from_user.id} toggled troll for {target_id} on {board_id}")