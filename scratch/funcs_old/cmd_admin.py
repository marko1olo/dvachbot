@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not is_admin(message.from_user.id, board_id):
        lang = 'en' if board_id == 'int' else 'ru'
        contact_url = "https://t.me/voprosy?start=rba30"
        if lang == 'en':
            response_text = "To contact the administration, please use the button below:"
            button_text = "Contact Admin"
        else:
            response_text = "╨ö╨╗╤Å ╤ü╨▓╤Å╨╖╨╕ ╤ü ╨░╨┤╨╝╨╕╨╜╨╛╨╝ ╨╕╤ü╨┐╨╛╨╗╤î╨╖╤â╨╣╤é╨╡ ╨║╨╜╨╛╨┐╨║╤â ╨╜╨╕╨╢╨╡:"
            button_text = "╨í╨▓╤Å╨╖╨░╤é╤î╤ü╤Å ╤ü ╨░╨┤╨╝╨╕╨╜╨╛╨╝"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=contact_url)]])
        try:
            await message.answer(response_text, reply_markup=keyboard)
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media')) # ╨ƒ╨╛╨┤╤ü╤ç╨╡╤é
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    if lang == 'en':
        header_text = f"Admin panel for board {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            "<b>≡ƒùÆ∩╕Å Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia</code> ΓÇö ╨æ╨░╨╜ ╨Æ╨í╨ò╨Ñ ╨╝╨╡╨┤╨╕╨░ ({media_ban_count})\n\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
    elif lang == 'jp':
        header_text = f"{BOARD_CONFIG[board_id]['name']} πü«τ«íτÉåπâæπâìπâ½:"
        memo_text = (
            "<b>≡ƒùÆ∩╕Å πé│πâ₧πâ│πâëπâíπâó:</b>\n"
            "<code>/filter ...</code> - πé╣πâæπâáπâòπéúπâ½πé┐τ«íτÉå\n"
            f"<code>/togglereactions &lt;id&gt;</code> - πâ¬πéóπé»πé╖πâºπâ│τªüµ¡ó ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIFπé╖πâúπâëπéªπâÉπâ│ ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - πé╣πâåπââπé½πâ╝πé╖πâúπâëπéªπâÉπâ│ ({sticker_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (Φ┐öΣ┐í) - πâ¬πéóπé»πé╖πâºπâ│πüùπüƒΣ║║πéÆΦªïπéï"
        )
    else:
        header_text = f"╨É╨┤╨╝╨╕╨╜╨║╨░ ╨┤╨╛╤ü╨║╨╕ {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> ΓÇö ╨æ╨░╨╜/╨á╨░╨╖╨▒╨░╨╜\n"
            "<code>/mute [╨▓╤Ç╨╡╨╝╤Å]</code>, <code>/unmute</code> ΓÇö ╨£╤â╤é\n"
            "<code>/shadowmute [╨▓╤Ç╨╡╨╝╤Å]</code> ΓÇö ╨ó╨╡╨╜╨╡╨▓╨╛╨╣ ╨╝╤â╤é (╨╗╨╛╨║╨░╨╗╤î╨╜╤ï╨╣)\n"
            "<code>/gban</code>, <code>/gunban</code>, <code>/gshadowmute</code> ΓÇö <b>╨ô╨¢╨₧╨æ╨É╨¢╨¼╨¥╨½╨ò</b> ╨╝╨╡╤Ç╤ï\n\n"
            "<code>/del</code> ΓÇö ╨ú╨┤╨░╨╗╨╕╤é╤î ╨┐╨╛╤ü╤é (╨╕ ╨║╨╛╨┐╨╕╨╕)\n"
            "<code>/sdel</code> ΓÇö ╨ó╨╡╨╜╨╡╨▓╨╛╨╡ ╤â╨┤╨░╨╗╨╡╨╜╨╕╨╡ (╨░╨▓╤é╨╛╤Ç ╨╜╨╡ ╨▓╨╕╨┤╨╕╤é)\n"
            "<code>/pin</code>, <code>/unpin</code> ΓÇö ╨ô╨╗╨╛╨▒╨░╨╗╤î╨╜╤ï╨╣ ╨╖╨░╨║╤Ç╨╡╨┐\n\n"
            "<code>/whois [id]</code> ΓÇö ╨ö╨╛╤ü╤î╨╡ ╨╜╨░ ╤Ä╨╖╨╡╤Ç╨░\n"
            "<code>/id</code> ΓÇö ╨ú╨╖╨╜╨░╤é╤î ID\n"
            f"<code>/togglegif</code> ΓÇö ╨ù╨░╨┐╤Ç╨╡╤é GIF (╨Æ╤ü╨╡╨│╨╛: {gif_ban_count})\n"
            f"<code>/togglestickers</code> ΓÇö ╨ù╨░╨┐╤Ç╨╡╤é ╤ü╤é╨╕╨║╨╡╤Ç╨╛╨▓ (╨Æ╤ü╨╡╨│╨╛: {sticker_ban_count})\n\n"
            f"<code>/lie</code> ΓÇö ╨ƒ╨╛╨┤╨╝╨╡╨╜╨░ ╨╝╨╡╨┤╨╕╨░ ╨░╤Ç╤à╨╕╨▓╨╛╨╝ (╨Æ╤ü╨╡╨│╨╛: {lie_media_count})\n\n"
            "<code>/say [╤é╨╡╨║╤ü╤é]</code> ΓÇö ╨ƒ╨╛╤ü╤é ╨╛╤é ╨╕╨╝╨╡╨╜╨╕ ╨É╨┤╨╝╨╕╨╜╨░\n"
            "<code>/ans [╤é╨╡╨║╤ü╤é]</code> ΓÇö ╨₧╤é╨▓╨╡╤é ╨╛╤é ╨╕╨╝╨╡╨╜╨╕ ╨í╨╕╤ü╤é╨╡╨╝╤ï (╤Ç╨╡╨┐╨╗╨░╨╣)\n"
            "<code>/stop</code> ΓÇö ╨Æ╤ï╨║╨╗╤Ä╤ç╨╕╤é╤î ╤Ç╨╡╨╢╨╕╨╝╤ï (╨¿╨╕╨╖╨░ ╨╕ ╤é.╨┤.)"
        )
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="≡ƒôè ╨í╤é╨░╤é╨╕╤ü╤é╨╕╨║╨░", callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text="≡ƒñ¼ ╨í╤é╨╛╨┐-╤ü╨╗╨╛╨▓╨░", callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text="≡ƒÜ½ ╨₧╨│╤Ç╨░╨╜╨╕╤ç╨╡╨╜╨╕╤Å (╨æ╨░╨╜╤ï/╨£╤â╤é╤ï)", callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text="≡ƒöÆ ╨¢╨╛╨║╨┤╨░╤â╨╜ (╨Æ╨Ü╨¢/╨Æ╨½╨Ü╨¢)", callback_data="admin_menu:lockdown")],
        [InlineKeyboardButton(text="≡ƒÆ╛ ╨í╨╛╤à╤Ç╨░╨╜╨╕╤é╤î ╨æ╤ì╨║╨░╨┐", callback_data="save_all")],
    ])
    await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
    await _safe_delete_user_message(message)