## 2026-08-08T16:24:00Z
Objective: Fix Requirement R3 Database Concurrency Patch in common/db_pool.py, common/database.py, and site_tgach/tagging_worker.py.

Defects to remediate:
1. In `common/db_pool.py`:
   - Update `LazyLock` to track lock ownership by the current task (`asyncio.current_task()`). Provide helper methods/properties such as `is_owned_by_current_task()` or `locked_by_current_task()`.
   - Update `db_sleep(delay: float)` so that it ONLY releases `db_lock` if the calling task actually holds `db_lock`. If the current task does NOT hold `db_lock`, `db_sleep` must simply `await asyncio.sleep(delay)` without releasing another task's lock and without reacquiring `db_lock` in `finally`.
2. In `common/database.py`:
   - Ensure background loop sleeps (e.g. `postcopies_daily_cleanup_loop` 24-hour/3600-second sleeps, and batch inter-iteration sleeps like `clean_old_postcopies_daily`, `clean_old_media_reposts_daily`, `clean_shadow_posts_chunked`) do not leak locks or cause self-deadlocks. With the updated `db_sleep` ownership check, `db_sleep` will safely sleep without acquiring `db_lock` if not already held.
3. In `site_tgach/tagging_worker.py`:
   - Update DB retry loop (around line 849) to use `await db_sleep(...)` instead of direct `await asyncio.sleep(...)`.
