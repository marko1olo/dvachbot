@dp.message(Command("gunban"))
async def cmd_gunban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨í╨╜╨╕╨╝╨░╨╡╤é ╨æ╨É╨¥ ╨╕ ╨ó╨ò╨¥╨ò╨Æ╨₧╨Ö ╨£╨ú╨ó ╤ü ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Å ╨í╨á╨É╨ù╨ú ╨¥╨É ╨Æ╨í╨ò╨Ñ ╨┤╨╛╤ü╨║╨░╤à.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        target_id = await get_author_id_by_reply(message)
    elif len((message.text or message.caption or "").split()) > 1:
        try: target_id = int((message.text or message.caption or "").split()[1])
        except Exception: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID/Reply needed." if lang != 'ru' else "╨¥╤â╨╢╨╡╨╜ ID ╨╕╨╗╨╕ ╤Ç╨╡╨┐╨╗╨░╨╣.")
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    if lang == 'en': msg = f"≡ƒòè∩╕Å Global Amnesty for <code>{target_id}</code>..."
    elif lang == 'jp': msg = f"≡ƒòè∩╕Å <code>{target_id}</code> πü╕πü«πé░πâ¡πâ╝πâÉπâ½µü⌐Φ╡ª..."
    else: msg = f"≡ƒòè∩╕Å ╨ô╨╗╨╛╨▒╨░╨╗╤î╨╜╨░╤Å ╨░╨╝╨╜╨╕╤ü╤é╨╕╤Å ╨┤╨╗╤Å <code>{target_id}</code>..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    count = 0
    for b_id in BOARDS:
        try:
            unbanned = False
            async with storage_lock:
                b_data_local = board_data[b_id]
                if target_id in b_data_local['users']['banned']:
                    b_data_local['users']['banned'].discard(target_id)
                    b_data_local['users']['active'].add(target_id)
                    unbanned = True
                if target_id in b_data_local['shadow_mutes']:
                    del b_data_local['shadow_mutes'][target_id]
                    unbanned = True
            if unbanned:
                await add_or_activate_user(target_id, b_id)
                await update_shadow_mute(target_id, b_id, 0)
                count += 1
        except Exception as e:
            runtime_logger.error(f"Error during global unban on board {b_id} for user {target_id}: {e}", exc_info=True)
    await log_global_event('bot', f"≡ƒòè∩╕Å GUNBAN: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} ╨ô╨¢╨₧╨æ╨É╨¢╨¼╨¥╨₧ ╨á╨É╨ù╨æ╨É╨¥╨ÿ╨¢ {target_id} ╨╜╨░ {count} ╨┤╨╛╤ü╨║╨░╤à")
    if lang == 'en': final = f"Γ£à User <code>{target_id}</code> unbanned/unmuted on {count} boards."
    elif lang == 'jp': final = f"Γ£à πâªπâ╝πé╢πâ╝ <code>{target_id}</code> πéÆ {count} σÇïπü«µ¥┐πüºBAN/πâƒπâÑπâ╝πâêΦºúΘÖñπüùπü╛πüùπüƒπÇé"
    else: final = f"Γ£à ╨ƒ╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤î <code>{target_id}</code> ╤Ç╨░╨╖╨▒╨░╨╜╨╡╨╜/╤Ç╨░╨╖╨╝╤â╤ç╨╡╨╜ ╨╜╨░ {count} ╨┤╨╛╤ü╨║╨░╤à."
    await status_msg.edit_text(final, parse_mode="HTML")