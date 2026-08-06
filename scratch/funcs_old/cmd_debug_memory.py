@dp.message(Command("debug_memory"))
async def cmd_debug_memory(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    runtime_snapshot = _collect_runtime_snapshot()
    if not tracemalloc.is_tracing():
        tracemalloc.start(10)
        report = [
            _format_runtime_snapshot(runtime_snapshot),
            "",
            "<b>tracemalloc:</b> started now. Repeat /debug_memory after the bot handles some traffic to see Python allocation lines."
        ]
        try:
            await message.answer("\n".join(report), parse_mode="HTML")
        except Exception as e:
            print(f"╨₧╤ê╨╕╨▒╨║╨░ ╨╛╤é╨┐╤Ç╨░╨▓╨║╨╕ debug_memory: {e}")
            print("\n".join(report))
        return
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    report = [_format_runtime_snapshot(runtime_snapshot), "\n<b>≡ƒôè ╨ó╨╛╨┐-10 ╨┐╨╛╤é╤Ç╨╡╨▒╨╕╤é╨╡╨╗╨╡╨╣ ╨┐╨░╨╝╤Å╤é╨╕:</b>\n"]
    for stat in top_stats[:10]:
        line = f"{stat.traceback.format()[0].strip()} -> {stat.size / 1024:.1f} KiB"
        report.append(escape_html(line))
    total_size = sum(stat.size for stat in top_stats) / 1024 / 1024
    report.append(f"\n<b>╨Æ╤ü╨╡╨│╨╛ ╨╛╤é╤ü╨╗╨╡╨╢╨╡╨╜╨╛:</b> {total_size:.2f} MiB")
    try:
        await message.answer("\n".join(report), parse_mode="HTML")
    except Exception as e:
        print(f"╨₧╤ê╨╕╨▒╨║╨░ ╨╛╤é╨┐╤Ç╨░╨▓╨║╨╕ debug_memory: {e}")
        print("\n".join(report))