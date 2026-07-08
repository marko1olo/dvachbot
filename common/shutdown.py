import asyncio

async def _graceful_shutdown_impl(
    is_shutting_down_state,
    set_shutting_down_cb,
    shutdown_event,
    dp,
    runtime_logger,
    pending_edit_lock,
    pending_edit_tasks,
    git_executor,
    save_executor,
    get_pool,
    db_lock,
    close_pool,
    bots=None,
    healthcheck_site=None,
    emergency=False
):
    if is_shutting_down_state:
        return
    set_shutting_down_cb(True)
    shutdown_event.set()

    reason = "АВАРИЙНЫЙ (OOM)" if emergency else "ШТАТНЫЙ"
    print(f"🛑 [{reason}] Начинаем процедуру остановки...")

    try:
        await dp.stop_polling()
        print("⏸ Polling остановлен.")
    except Exception as e:
        print(f"⚠️ Ошибка при остановке polling: {e}")
        runtime_logger.warning(f"Ошибка при остановке polling: {e}")

    print("💾 Сброс данных из WAL на диск...")
    try:
        async with db_lock:
            db = await get_pool()
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            print("✅ Данные успешно сохранены на диск (WAL Truncated).")
    except Exception as e:
        print(f"⛔ Ошибка сохранения WAL: {e}")

    try:
        print("🛑 Отмена фоновых задач перед закрытием БД...")
        async with pending_edit_lock:
            for task in pending_edit_tasks.values():
                task.cancel()

        if healthcheck_site:
            await healthcheck_site.stop()
        await asyncio.sleep(2.0)

        await close_pool()

        git_executor.shutdown(wait=False, cancel_futures=True)
        save_executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        print(f"⚠️ Ошибка при shutdown: {e}")

    print("✅ Готово к выходу.")
