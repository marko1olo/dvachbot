@dp.message(Command("punchup", "modepunchup"))
async def cmd_mode_punchup(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    global mode_punchup_runtime_enabled
    args = (message.text or "").split()
    action = args[1].lower() if len(args) > 1 else "status"
    note = ""
    if action in {"on", "enable", "1", "вкл"}:
        if MODE_PUNCHUP_ENABLED:
            mode_punchup_runtime_enabled = True
            note = "runtime enabled"
        else:
            note = "env disabled; set BOT_MODE_PUNCHUP_ENABLED=1 and restart"
    elif action in {"off", "disable", "0", "выкл"}:
        mode_punchup_runtime_enabled = False
        note = "runtime disabled"
    elif action in {"reset", "clear"}:
        mode_punchup_stats.clear()
        note = "stats reset"
    snapshot = _collect_runtime_snapshot().get("mode_punchup", {})
    stats = snapshot.get("stats", {})
    top = ", ".join(
        f"{mode}:{data.get('avg_us', 0)}/{data.get('max_us', 0)}us"
        for mode, data in stats.get("top", [])
    ) or "none"
    text = (
        "<b>Mode punch-up</b>\n"
        f"env/runtime: <code>{snapshot.get('enabled')} / {snapshot.get('runtime_enabled')}</code>\n"
        f"shed/slow: <code>{snapshot.get('queue_shed_sec')}s / {snapshot.get('slow_log_us')}us</code>\n"
        f"calls avg/max: <code>{stats.get('calls', 0)} | {stats.get('avg_us', 0)} / {stats.get('max_us', 0)}us</code>\n"
        f"skips load/disabled: <code>{stats.get('skipped_load', 0)} / {stats.get('skipped_disabled', 0)}</code>\n"
        f"top: <code>{escape_html(top)}</code>"
    )
    if note:
        text += f"\nstate: <code>{escape_html(note)}</code>"
    await message.answer(text, parse_mode="HTML")