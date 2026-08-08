# DISPATCH — Worker R3 (DB Concurrency Fix)

**Scope**: Requirement 3 (R3) Remediation
**Target Files**:
- `C:\Users\danat\Desktop\dvachbot\common\database.py`
- `C:\Users\danat\Desktop\dvachbot\common\db_pool.py`
**Original Request Path**: `C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md`

## Task
1. Inspect `common/database.py` line 36.
2. Add `db_sleep` and `db_lock` to the import from `common.db_pool` (e.g. `from common.db_pool import get_pool, db_sleep, db_lock`).
3. Verify that all 96 calls to `await db_sleep(...)` in `common/database.py` now resolve cleanly without `NameError`.
4. Fix any `postcopies_daily_cleanup_loop` lock ownership issues if `db_sleep` is called without holding `db_lock` (use `asyncio.sleep` instead for background loops that do not hold `db_lock`).
5. Run `python -m py_compile common/database.py` and `pytest tests/test_database_sync.py` or existing db unit tests to verify 100% pass rate.
6.15: Deliver `C:\Users\danat\Desktop\dvachbot\.agents\worker_r3\changes.md` and `handoff.md`.
16: 
17: ## 2026-08-08T12:25:17Z
18: Task: Remediate the Database Concurrency Patch (R3) defects identified by the Explorer:
19: 1. Edit `C:\Users\danat\Desktop\dvachbot\common\database.py` to import `db_sleep` and `db_lock` from `common.db_pool` (change `from common.db_pool import get_pool` to `from common.db_pool import get_pool, db_sleep, db_lock`).
20: 2. Verify in `common/database.py` that all `await db_sleep(...)` calls resolve without `NameError`.
21: 3. Check `postcopies_daily_cleanup_loop` (around lines 8199 & 8209) — if it calls `db_sleep` without holding `db_lock`, replace with `await asyncio.sleep(...)` so it does not forcibly release other tasks' locks.
22: 4. Run `python -m py_compile common/database.py` and run any unit tests (e.g. `pytest tests/test_database_sync.py` or similar).
23: 5. MANDATORY INTEGRITY WARNING: DO NOT CHEAT.
24: 6. Write your changes summary to `C:\Users\danat\Desktop\dvachbot\.agents\worker_r3\changes.md` and deliver `C:\Users\danat\Desktop\dvachbot\.agents\worker_r3\handoff.md`.
25: 7. Send a message to the orchestrator upon completion.
