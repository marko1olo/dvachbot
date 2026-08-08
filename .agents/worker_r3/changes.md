# Changes Summary — Worker R3 (DB Concurrency Patch Remediation)

## 1. Updated Imports in `common/database.py`
- **File**: `C:\Users\danat\Desktop\dvachbot\common\database.py`
- **Line 36**: Changed `from common.db_pool import get_pool` to `from common.db_pool import get_pool, db_sleep, db_lock`.
- **Rationale**: `common/database.py` contains 96 calls to `await db_sleep(...)` across retry loops and batch processing functions. Without importing `db_sleep` and `db_lock` at top-level, any database retry attempt raised `NameError: name 'db_sleep' is not defined`.

## 2. Unsafe Lock Release Fix in `postcopies_daily_cleanup_loop`
- **File**: `C:\Users\danat\Desktop\dvachbot\common\database.py`
- **Lines ~8199 & ~8209**: Replaced `await db_sleep(max(10, sleep_sec))` and `await db_sleep(3600)` with `await asyncio.sleep(max(10, sleep_sec))` and `await asyncio.sleep(3600)`.
- **Rationale**: `postcopies_daily_cleanup_loop` is a long-running background task sleeping until midnight MSK (or 1 hour on error). It does NOT hold `db_lock`. Calling `db_sleep` while NOT holding `db_lock` would check `if db_lock.locked(): db_lock.release()`, which forcibly released `db_lock` out from under other active tasks holding `db_lock`, and then acquired `db_lock` in `finally:`, blocking other database operations indefinitely.

## 3. Verification & Testing
- `python -m py_compile common/database.py common/db_pool.py`: Exit code 0 (Passed).
- `python -m unittest tests/test_database_sync.py`: Ran 4 tests, 4 Passed (OK).
- `python -m unittest tests/test_db_pool.py`: Ran 7 tests, 7 Passed (OK).
- `python -m unittest tests/test_database.py`: Ran 1 test, 1 Passed (OK).
