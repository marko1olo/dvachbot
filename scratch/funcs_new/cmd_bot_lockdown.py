@dp.message(Command("lockdown"))
async def cmd_bot_lockdown(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = (message.text or message.caption or "").split()
    if len(args) < 2:
        await message.answer("Использование: `/lockdown on` или `/lockdown off`", parse_mode="Markdown")
        return
    enabled = args[1].lower() == "on"
    from common.database import set_system_setting
    await set_system_setting('lockdown_enabled', "true" if enabled else "false")
    status_text = "ВКЛЮЧИЛ" if enabled else "ВЫКЛЮЧИЛ"
    await log_global_event('bot', f"🚨 LOCKDOWN: Админ {message.from_user.id} {status_text} режим бункера")
    await message.answer(f"✅ Режим бункера {'активирован' if enabled else 'деактивирован'} везде.")