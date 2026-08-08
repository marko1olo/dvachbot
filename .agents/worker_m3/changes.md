# Changes Summary — Requirement R3 Database Concurrency Patch

## Modified Files

1. `common/db_pool.py`:
   - Updated `LazyLock` class to track lock ownership using `asyncio.current_task()`.
   - Added helper methods `is_owned_by_current_task()` and `locked_by_current_task()` to `LazyLock`.
   - Updated `acquire()` to set `self._owner = asyncio.current_task()`.
   - Updated `release()` to clear `self._owner = None`.
   - Updated `db_sleep(delay: float)` to check task ownership before attempting lock release (`is_owned_by_current_task()`).
   - If the calling task does NOT hold `db_lock`, `db_sleep` simply awaits `asyncio.sleep(delay)` without releasing another task's lock and without reacquiring `db_lock` in `finally`.
   - Made `db_sleep` robust using `getattr(db_lock, "is_owned_by_current_task", None)` when `db_lock` is mocked or replaced in tests.

2. `site_tgach/tagging_worker.py`:
   - Added `db_sleep` to imports from `common.db_pool`.
   - Replaced direct `await asyncio.sleep(0.5 * (attempt + 1))` in the DB retry loop (line 849) with `await db_sleep(0.5 * (attempt + 1))`.

3. `tests/test_db_pool.py`:
   - Updated `asyncSetUp` to initialize `_reconnect_lock` and `db_lock` with `LazyLock()`.
   - Added `test_lazy_lock_ownership_tracking` to verify `LazyLock` ownership tracking per task.
   - Added `test_db_sleep_release_and_reacquire_when_holding_lock` verifying scenario (a): `db_sleep` releases `db_lock` when held by current task and reacquires it after sleep.
   - Added `test_db_sleep_does_not_release_lock_held_by_other_task` verifying scenario (b): `db_sleep` does NOT release `db_lock` when called by a task not holding `db_lock`.
   - Added `test_db_sleep_does_not_acquire_lock_if_not_held_before` verifying scenario (c): `db_sleep` does NOT acquire `db_lock` if calling task didn't hold it before sleep.
   - Added `test_db_sleep_concurrent_tasks_no_lock_stealing_or_deadlock` verifying scenario (d): concurrent tasks run without lock stealing or self-deadlock.

4. `tests/test_database_sync.py`:
   - Updated `db_lock` mocks to use `LazyLock` for consistency across test suites.
