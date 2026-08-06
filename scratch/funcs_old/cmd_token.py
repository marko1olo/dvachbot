@dp.message(Command("token"))
async def cmd_token(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    ╨ô╨╡╨╜╨╡╤Ç╨╕╤Ç╤â╨╡╤é ╨╕╨╗╨╕ ╨┐╨╛╨║╨░╨╖╤ï╨▓╨░╨╡╤é ╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╤é╨╡╨╗╤Ä ╨╡╨│╨╛ ╨┐╨╡╤Ç╤ü╨╛╨╜╨░╨╗╤î╨╜╤ï╨╣ ╤é╨╛╨║╨╡╨╜ ╨┤╨╗╤Å ╨▓╤à╨╛╨┤╨░ ╨╜╨░ ╤ü╨░╨╣╤é.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    try:
        token = await get_or_create_api_token(user_id, generate_unique_token)
        WEBAPP_URL_DISPLAY = "https://tgach.top" 
        if lang == 'en':
            response_text = (
                "≡ƒöæ **Your personal token for website access:**\n\n"
                f"Use it to log in on {WEBAPP_URL_DISPLAY}. **Do not share it with anyone.**\n\n"
                "Tap the token below to copy it:"
            )
        elif lang == 'jp':
            response_text = (
                "≡ƒöæ **πéªπéºπâûπé╡πéñπâêπéóπé»πé╗πé╣πü«πüƒπéüπü«σÇïΣ║║πâêπâ╝πé»πâ│:**\n\n"
                f"{WEBAPP_URL_DISPLAY} πüºπâ¡πé░πéñπâ│πüÖπéïπüƒπéüπü½Σ╜┐τö¿πüùπü╛πüÖπÇé**Σ╗ûΣ║║πü½πü»µòÖπüêπü¬πüäπüºπüÅπüáπüòπüäπÇé**\n\n"
                "Σ╕ïπü«πâêπâ╝πé»πâ│πéÆπé┐πââπâùπüùπüªπé│πâöπâ╝:"
            )
        else:
            response_text = (
                "≡ƒöæ **╨Æ╨░╤ê ╤é╨╛╨║╨╡╨╜ ╨┤╨╗╤Å ╨▓╤à╨╛╨┤╨░ ╨╜╨░ ╤ü╨░╨╣╤é ╨ó╨ô╨É╨º╨░:**\n\n"
                f"╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╤â╨╣╤é╨╡ ╨╡╨│╨╛ ╨┤╨╗╤Å ╨▓╤à╨╛╨┤╨░ ╨╜╨░ {WEBAPP_URL_DISPLAY}.\n**╨¥╨╕╨║╨╛╨╝╤â ╨╡╨│╨╛ ╨╜╨╡ ╨┐╨╛╨║╨░╨╖╤ï╨▓╨░╨╣╤é╨╡.**\n\n"
                "╨¥╨░╨╢╨╝╨╕╤é╨╡ ╨╜╨░ ╤é╨╛╨║╨╡╨╜ ╨╜╨╕╨╢╨╡, ╤ç╤é╨╛╨▒╤ï ╤ü╨║╨╛╨┐╨╕╤Ç╨╛╨▓╨░╤é╤î ╨╡╨│╨╛:"
            )
        token_display = f"<code>{token}</code>"
        await message.answer(response_text, parse_mode="HTML")
        await message.answer(token_display, parse_mode="HTML")
    except Exception as e:
        print(f"Γ¢ö ╨Ü╤Ç╨╕╤é╨╕╤ç╨╡╤ü╨║╨░╤Å ╨╛╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕ ╤é╨╛╨║╨╡╨╜╨░ ╨┤╨╗╤Å user {user_id}: {e}")
        if lang == 'en': error = "An error occurred while creating the token."
        elif lang == 'jp': error = "πâêπâ╝πé»πâ│πü«Σ╜£µêÉΣ╕¡πü½πé¿πâ⌐πâ╝πüîτÖ║τöƒπüùπü╛πüùπüƒπÇé"
        else: error = "╨ƒ╤Ç╨╛╨╕╨╖╨╛╤ê╨╗╨░ ╨╛╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╤ü╨╛╨╖╨┤╨░╨╜╨╕╨╕ ╤é╨╛╨║╨╡╨╜╨░."
        await message.answer(error)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        import traceback; traceback.print_exc()