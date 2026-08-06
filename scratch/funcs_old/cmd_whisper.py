@dp.message(Command("whisper"))
async def cmd_whisper(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    try: await message.delete()
    except Exception: pass
    if not message.reply_to_message:
        await message.answer("Γ¥î ╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╣ /whisper ╨▓ ╨╛╤é╨▓╨╡╤é ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡, ╨░╨▓╤é╨╛╤Ç╤â ╨║╨╛╤é╨╛╤Ç╨╛╨│╨╛ ╤à╨╛╤ç╨╡╤ê╤î ╨┐╤Ç╨╛╤ê╨╡╨┐╤é╨░╤é╤î.")
        return
    parts = (message.text or message.caption or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Γ¥î ╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/whisper &lt;╤é╨╡╨║╤ü╤é&gt;</code>", parse_mode="HTML")
        return
    text = parts[1]
    
    target_id = await get_author_id_by_reply(message)
    if not target_id:
        await message.answer("Γ¥î ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨╜╨░╨╣╤é╨╕ ╨░╨▓╤é╨╛╤Ç╨░ ╨╛╤Ç╨╕╨│╨╕╨╜╨░╨╗╤î╨╜╨╛╨│╨╛ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╤Å.")
        return
        
    if target_id == message.from_user.id:
        await message.answer("Γ¥î ╨ù╨░╤ç╨╡╨╝ ╤ê╨╡╨┐╤é╨░╤é╤î ╤ü╨░╨╝╨╛╨╝╤â ╤ü╨╡╨▒╨╡?")
        return

    # Send to target
    delivered = False
    try:
        await message.bot.send_message(
            target_id, 
            f"≡ƒñ½ <b>╨ó╨╡╨▒╨╡ ╨░╨╜╨╛╨╜╨╕╨╝╨╜╨╛ ╤ê╨╡╨┐╤ç╤â╤é ╨▓ /{board_id}/:</b>\n<i>{escape_html(text)}</i>", 
            parse_mode="HTML"
        )
        delivered = True
    except Exception as e:
        runtime_logger.error(f"Whisper send failed: {e}", exc_info=True)
        await message.answer("Γ¥î ╨¥╨╡ ╤â╨┤╨░╨╗╨╛╤ü╤î ╨┤╨╛╤ü╤é╨░╨▓╨╕╤é╤î ╤ê╤æ╨┐╨╛╤é (╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î ╨╜╨╡ ╨╖╨░╨┐╤â╤ü╤é╨╕╨╗ ╨▒╨╛╤é╨░ ╨╕╨╗╨╕ ╨╖╨░╨▒╨╗╨╛╨║╨╕╤Ç╨╛╨▓╨░╨╗ ╨╡╨│╨╛).")
        
    if delivered:
        # Send to admin
        admins = BOARD_CONFIG.get(board_id, {}).get('admins', set())
        sender_nick = generate_anon_name(message.from_user.id)
        target_nick = generate_anon_name(target_id)
        for admin_id in admins:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"≡ƒò╡∩╕ÅΓÇìΓÖé∩╕Å <b>(╨¡╨ó╨₧ ╨í╨ò╨Ü╨á╨ò╨ó) ╨¿╤æ╨┐╨╛╤é ╨▓ /{board_id}/:</b>\n╨₧╤é: <code>{sender_nick}</code>\n╨Ü╨╛╨╝╤â: <code>{target_nick}</code>\n╨ó╨╡╨║╤ü╤é: <i>{escape_html(text)}</i>",
                    parse_mode="HTML"
                )
            except Exception: pass