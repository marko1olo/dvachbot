@dp.message(Command("restrict_anime"))
async def cmd_restrict_anime(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return

    target_id = None
    args = (message.text or message.caption or "").split()
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len(args) > 1 and args[1].isdecimal():
        # isdecimal, ╨╜╨╡ isdigit ΓÇö ╤ü╨╝. ╨┐╨╛╤Å╤ü╨╜╨╡╨╜╨╕╨╡ ╨▓ cmd_random_media
        target_id = int(args[1])

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if not target_id:
        msg = "Usage: <code>/restrict_anime &lt;id&gt;</code> or reply." if lang != 'ru' else "╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: <code>/restrict_anime &lt;id&gt;</code> ╨╕╨╗╨╕ ╨╛╤é╨▓╨╡╤é ╨╜╨░ ╤ü╨╛╨╛╨▒╤ë╨╡╨╜╨╕╨╡."
        await message.answer(msg, parse_mode="HTML")
        return

    b_data = board_data[board_id]
    async with storage_lock:
        if target_id in b_data['anime_strict_limits']:
            b_data['anime_strict_limits'].remove(target_id)
            action_log = "REMOVED FROM STRICT LIMITS"
            if lang == 'en':
                res = f"Γ£à User <code>{target_id}</code> removed from strict anime limits."
            elif lang == 'jp':
                res = f"Γ£à πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πü«πéóπâïπâíπâ¬πâƒπââπâêπéÆΦºúΘÖñπüùπü╛πüùπüƒπÇé"
            else:
                res = f"Γ£à ╨í ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å <code>{target_id}</code> ╤ü╨╜╤Å╤é╨╛ ╨╢╨╡╤ü╤é╨║╨╛╨╡ ╨╛╨│╤Ç╨░╨╜╨╕╤ç╨╡╨╜╨╕╨╡ ╨╜╨░ ╨░╨╜╨╕╨╝╨╡."
        else:
            b_data['anime_strict_limits'].add(target_id)
            action_log = "ADDED TO STRICT LIMITS (10/day)"
            if lang == 'en':
                res = f"≡ƒÜ½ User <code>{target_id}</code> now restricted to 10 anime images per 24h."
            elif lang == 'jp':
                res = f"≡ƒÜ½ πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πü½1µùÑ10µ₧Üπü«σê╢ΘÖÉπéÆπüïπüæπü╛πüùπüƒπÇé"
            else:
                res = f"≡ƒÜ½ ╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Ä <code>{target_id}</code> ╤â╤ü╤é╨░╨╜╨╛╨▓╨╗╨╡╨╜╨╛ ╨╛╨│╤Ç╨░╨╜╨╕╤ç╨╡╨╜╨╕╨╡: 10 ╨║╨░╤Ç╤é╨╕╨╜╨╛╨║ ╨▓ ╤ü╤â╤é╨║╨╕."

    await log_global_event('bot', f"≡ƒ¢í∩╕Å ANIME_LIMIT: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} {action_log} ╨┤╨╗╤Å {target_id} ╨╜╨░ /{board_id}/")
    await message.answer(res, parse_mode="HTML")
    try:
        await message.delete()
    except Exception:
        import traceback; traceback.print_exc()