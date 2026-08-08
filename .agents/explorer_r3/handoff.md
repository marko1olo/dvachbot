# Handoff Report — Explorer R3 (Database Concurrency Patch Verification)

**Target Requirement**: R3 — Verify Database Concurrency Patch in `common/database.py` and `common/db_pool.py`  
**Working Directory**: `C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3`  
**Author**: Explorer R3  

---

## 1. Observation

1. **`common/database.py` Top-Level Imports**:
   - `C:\Users\danat\Desktop\dvachbot\common\database.py`, line 36:
     ```python
     36: from common.db_pool import get_pool
     ```
   - `db_sleep` and `db_lock` are **NOT imported** at module level in `common/database.py`.

2. **Automated Search Results**:
   - `common/database.py` contains **98 call sites** executing `await db_sleep(...)`.
   - **96 database functions** call `db_sleep` without local or top-level import statements.
   - `asyncio.sleep` calls in `common/database.py` retry loops: **0**.

3. **Unit Test Exception Output**:
   - Running `python -X utf8 C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3\run_all_db_tests.py` executing `tests/test_database_sync.py::test_retry_on_locked`:
     ```
     ======================================================================
     ERROR: test_retry_on_locked (tests.test_database_sync.TestSyncBoardsWithConfig.test_retry_on_locked)
     ----------------------------------------------------------------------
     Traceback (most recent call last):
       File "C:\Users\danat\Desktop\dvachbot\common\database.py", line 4099, in sync_boards_with_config
         await db.execute("BEGIN IMMEDIATE")
     sqlite3.OperationalError: database is locked

     During handling of the above exception, another exception occurred:

       File "C:\Users\danat\Desktop\dvachbot\common\database.py", line 4128, in sync_boards_with_config
         await db_sleep(0.5 * (attempt + 1))
               ^^^^^^^^
     NameError: name 'db_sleep' is not defined
     ```

4. **`db_sleep` Implementation in `common/db_pool.py`**:
   - Lines 132–146:
     ```python
     async def db_sleep(delay: float):
         """Безопасный sleep для отпускания db_lock во время ожидания."""
         lock_released = False
         if db_lock.locked():
             try:
                 db_lock.release()
                 lock_released = True
             except RuntimeError:
                 pass
         try:
             await asyncio.sleep(delay)
         finally:
             if lock_released:
                 await db_lock.acquire()
     ```

5. **Non-Lock-Holding Routine Call to `db_sleep`**:
   - `common/database.py`, lines 8188–8210 (`postcopies_daily_cleanup_loop`):
     - Line 8199: `await db_sleep(max(10, sleep_sec))`
     - Line 8209: `await db_sleep(3600)`
     - This routine does not acquire `db_lock`. `db_lock.locked()` checks global lock state (`asyncio.Lock.locked()`), causing `db_sleep` to release whatever other task currently holds `db_lock` and acquire `db_lock` in `finally:`.

---

## 2. Logic Chain

1. **Premise 1 (Observation 1 & 2)**: `database.py` contains 98 `await db_sleep(...)` statements, but line 36 only imports `get_pool` from `common.db_pool`. 96 functions lack a `db_sleep` import.
2. **Premise 2 (Observation 3)**: When a database operation encounters SQLite `OperationalError: database is locked`, control enters the `except sqlite3.OperationalError:` block and attempts to evaluate `await db_sleep(...)`.
3. **Step 1**: Because `db_sleep` is undefined in scope for 96 functions, Python raises `NameError: name 'db_sleep' is not defined`.
4. **Step 2**: The operation crashes immediately instead of retrying or sleeping, completely breaking database concurrency handling under lock contention.
5. **Premise 3 (Observation 4 & 5)**: `db_sleep` checks `db_lock.locked()`, which returns `True` if *any* task holds `db_lock`. `postcopies_daily_cleanup_loop` calls `db_sleep` without holding `db_lock`.
6. **Step 3**: If `postcopies_daily_cleanup_loop` calls `db_sleep` while another task holds `db_lock`, it forcibly releases the other task's lock and then acquires `db_lock` upon waking up, corrupting lock state across coroutines.
7. **Conclusion**: Requirement 3 is **FAILED / PENDING FIX**. The patch attempted to replace `asyncio.sleep` with `db_sleep`, but failed to import `db_sleep` in `common/database.py`, introducing a runtime `NameError` crash across 96 functions.

---

## 3. Caveats

- No caveats. The codebase was fully inspected, static call graphs were analyzed, and test execution directly reproduced the runtime `NameError` failure.

---

## 4. Conclusion

Requirement 3 verification status: **FAILED (REJECTED)**.

- **Defect 1**: Critical runtime `NameError: name 'db_sleep' is not defined` in `common/database.py` due to missing module-level import `from common.db_pool import get_pool, db_lock, db_sleep`.
- **Defect 2**: Lock state corruption vulnerability in `postcopies_daily_cleanup_loop` (lines 8199/8209) due to calling `db_sleep` from a task that does not hold `db_lock`.

### Actionable Fixes Required:
1. In `common/database.py`, line 36: update import to `from common.db_pool import get_pool, db_lock, db_sleep`.
2. In `common/database.py`, lines 8199 & 8209: change `db_sleep(...)` to `asyncio.sleep(...)`.

---

## 5. Verification Method

To verify the patch after applying fixes:

1. **Module-level import check**:
   Inspect line 36 of `common/database.py` to confirm `db_sleep` is imported.

2. **Unit Test Execution**:
   Run the database sync unit test:
   ```cmd
   python -X utf8 -m unittest tests.test_database_sync
   ```
   **Pass Condition**: `test_retry_on_locked` passes without `NameError`.

3. **Full DB Test Suite**:
   Run all database unit tests:
   ```cmd
   python -X utf8 -m unittest tests.test_db_pool tests.test_database_sync
   ```
   **Pass Condition**: 0 failures, 0 errors.
