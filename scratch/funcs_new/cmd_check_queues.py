@dp.message(Command("queues"))
async def cmd_check_queues(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    from common.database import get_system_queue_counts
    db_stats = await get_system_queue_counts()
    runtime_snapshot = _collect_runtime_snapshot()
    queues = runtime_snapshot.get("queues", {})
    delivery_priority = runtime_snapshot.get("delivery_priority", {})
    recipients_snapshot = runtime_snapshot.get("recipients", {})
    anime_media_snapshot = runtime_snapshot.get("anime_media", {})
    durable_delivery_snapshot = runtime_snapshot.get("durable_delivery", {})
    mode_punchup_snapshot = runtime_snapshot.get("mode_punchup", {})
    mode_punchup_stats = mode_punchup_snapshot.get("stats", {})
    contextual_snapshot = runtime_snapshot.get("contextual_replies", {})
    contextual_stats = contextual_snapshot.get("stats", {})
    reply_coverage = runtime_snapshot.get("reply_coverage", {})
    ram_queue_size = message_queues[board_id].qsize()
    top_queue = ", ".join(f"{b}:{n}" for b, n in queues.get("top", [])) or "empty"
    priority_by_board = delivery_priority.get("by_board", {})
    board_delivery = runtime_snapshot.get("delivery", {}).get(board_id, {})
    last_delivery = board_delivery.get("last") or {}
    live_queue_info = queues.get("age_by_board", {}).get(board_id, {})
    live_current = queues.get("in_flight", {}).get(board_id, {})
    live_queue_text = (
        f"oldest {live_queue_info.get('oldest_age_sec', 0)}s "
        f"avg {live_queue_info.get('avg_age_sec', 0)}s "
        f"post #{live_queue_info.get('oldest_post', '-')}"
    )
    live_current_text = (
        f"#{live_current.get('post_num')} {live_current.get('phase', 'full')} "
        f"run {live_current.get('run_sec')}s age {live_current.get('age_sec')}s "
        f"rec {live_current.get('recipients', '-')}/{live_current.get('original_recipients', '-')}"
        if live_current else "none"
    )
    board_reply_coverage = reply_coverage.get("by_board", {}).get(board_id, {})
    reply_coverage_text = (
        f"all {reply_coverage.get('copy_posts', 0)} posts/{reply_coverage.get('total_copies', 0)} copies "
        f"span {reply_coverage.get('min_post', '-')}-{reply_coverage.get('max_post', '-')} "
        f"gap {reply_coverage.get('gap_from_latest', '-')}; "
        f"{board_id} {board_reply_coverage.get('copy_posts', 0)} posts "
        f"{board_reply_coverage.get('min_post', '-')}-{board_reply_coverage.get('max_post', '-')}"
    )
    if last_delivery:
        last_age = last_delivery.get("post_age_sec")
        last_age_text = f" age {round(last_age, 1)}s" if last_age is not None else ""
        last_delivery_text = (
            f"#{last_delivery.get('post_num')} "
            f"{last_delivery.get('phase', 'full')} "
            f"{last_delivery.get('success')}/{last_delivery.get('phase_recipients', last_delivery.get('recipients'))}"
            f"/{last_delivery.get('original_recipients', last_delivery.get('recipients'))} "
            f"{last_delivery.get('seconds')}s "
            f"{last_age_text} "
            f"def {last_delivery.get('deferred_recipients', 0)} "
            f"prio {last_delivery.get('priority_recipients')} "
            f"retry {last_delivery.get('retries')}"
        )
    else:
        last_delivery_text = "none"
    memory = runtime_snapshot.get("memory", {})
    text = (
        f"📊 <b>Состояние очередей:</b>\n\n"
        f"🚀 <b>RAM (Рассылка):</b> {ram_queue_size}\n"
        f"🧵 <b>RAM total/top:</b> {queues.get('total', 0)} | <code>{escape_html(top_queue)}</code>\n"
        f"⏳ <b>Live age/current:</b> <code>{escape_html(live_queue_text)} | {escape_html(live_current_text)}</code>\n"
        f"👥 <b>Telegram recipients:</b> {recipients_snapshot.get('telegram_active_by_board', {}).get(board_id, '?')} on /{board_id}/; all {recipients_snapshot.get('telegram_active_total', '?')}\n"
        f"↩️ <b>Reply copies:</b> <code>{escape_html(reply_coverage_text)}</code>\n"
        f"⚡ <b>Priority active:</b> {priority_by_board.get(board_id, 0)} / {delivery_priority.get('total_weekly_active', 0)} за {delivery_priority.get('days', WEEKLY_ACTIVE_DAYS)}d split={delivery_priority.get('split_fanout')} slice={delivery_priority.get('passive_slice_size')}/{delivery_priority.get('passive_media_slice_size')} pressure>={delivery_priority.get('pressure_slice_age_sec')}s:{delivery_priority.get('pressure_passive_slice_size')}/{delivery_priority.get('pressure_passive_media_slice_size')} priority_budget={delivery_priority.get('priority_phase_budget_sec')}s passive_budget={delivery_priority.get('passive_phase_budget_sec')}s guard={delivery_priority.get('delivery_phase_guard_sec')}s preempt={delivery_priority.get('passive_max_preemptions')} chunk={delivery_priority.get('delivery_initial_chunk_size')}/{delivery_priority.get('delivery_min_chunk_size')} uid_timeout={delivery_priority.get('delivery_per_recipient_timeout_sec')}s uid_retries={delivery_priority.get('delivery_max_recipient_retries')}\n"
        f"🧷 <b>Durable delivery:</b> enabled={durable_delivery_snapshot.get('enabled')} DB pending={db_stats.get('delivery', 0)} saved={durable_delivery_snapshot.get('persisted', 0)} fail={durable_delivery_snapshot.get('persist_failed', 0)} restored={durable_delivery_snapshot.get('restored_items', 0)}/{durable_delivery_snapshot.get('restored_recipients', 0)} deleted={durable_delivery_snapshot.get('deleted', 0)}\n"
        f"🖼 <b>Anime media:</b> conc={anime_media_snapshot.get('concurrency')} b_max={anime_media_snapshot.get('b_max_stacked_images')} url={anime_media_snapshot.get('url_parallel')}x/{anime_media_snapshot.get('url_timeout_sec')}s total={anime_media_snapshot.get('url_total_sec')}s dl={anime_media_snapshot.get('download_parallel')}x/{anime_media_snapshot.get('download_timeout_sec')}s\n"
        f"🎭 <b>Mode punch-up:</b> runtime={mode_punchup_snapshot.get('runtime_enabled')} shed={mode_punchup_snapshot.get('queue_shed_sec')}s calls={mode_punchup_stats.get('calls', 0)} skip_load={mode_punchup_stats.get('skipped_load', 0)}\n"
        f"💬 <b>Context replies:</b> enabled={contextual_snapshot.get('enabled')} groups={contextual_snapshot.get('groups_ru')} tracked={contextual_snapshot.get('tracked_users')} sent={contextual_stats.get('sent', 0)} skip_cd/daily={contextual_stats.get('skipped_cooldown', 0)}/{contextual_stats.get('skipped_daily_limit', 0)} cd={contextual_snapshot.get('cooldown_sec')}s limit={contextual_snapshot.get('daily_limit')}\n"
        f"📨 <b>Last delivery:</b> <code>{escape_html(last_delivery_text)}</code> avg/max <code>{board_delivery.get('avg_sec', 0)} / {board_delivery.get('max_sec', 0)}s</code>\n"
        f"💾 <b>DB (Broadcast):</b> {db_stats.get('broadcast', 0)}\n"
        f"🔔 <b>DB (Уведомления):</b> {db_stats.get('notif', 0)}\n"
        f"🪞 <b>DB (Зеркала файлов):</b> {db_stats.get('mirror', 0)}\n"
        f"👮 <b>DB (Модерация):</b> {db_stats.get('mod', 0)}\n"
        f"🧠 <b>RSS/private:</b> {memory.get('rss_mb', '?')} / {memory.get('private_mb', '?')} MB"
    )
    await message.answer(text, parse_mode="HTML")