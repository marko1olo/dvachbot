@dp.message(Command("lockdown"))
async def cmd_bot_lockdown(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or message.caption or "").split()
    if len(args) < 2:
        await message.answer("╨ÿ╤ü╨┐╨╛╨╗╤î╨╖╨╛╨▓╨░╨╜╨╕╨╡: `/lockdown on` ╨╕╨╗╨╕ `/lockdown off`", parse_mode="Markdown")
        return
    enabled = args[1].lower() == "on"
    from common.database import set_system_setting
    await set_system_setting('lockdown_enabled', "true" if enabled else "false")
    status_text = "╨Æ╨Ü╨¢╨«╨º╨ÿ╨¢" if enabled else "╨Æ╨½╨Ü╨¢╨«╨º╨ÿ╨¢"
    await log_global_event('bot', f"≡ƒÜ¿ LOCKDOWN: ╨É╨┤╨╝╨╕╨╜ {message.from_user.id} {status_text} ╤Ç╨╡╨╢╨╕╨╝ ╨▒╤â╨╜╨║╨╡╤Ç╨░")
    await message.answer(f"Γ£à ╨á╨╡╨╢╨╕╨╝ ╨▒╤â╨╜╨║╨╡╤Ç╨░ {'╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜' if enabled else '╨┤╨╡╨░╨║╤é╨╕╨▓╨╕╤Ç╨╛╨▓╨░╨╜'} ╨▓╨╡╨╖╨┤╨╡.")