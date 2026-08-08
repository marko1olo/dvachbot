# Handoff Report: Requirement R3 Database Concurrency Audit

## 1. Observation

1. **File Replacement Verification**:
   - Standard search in `common/database.py` for `asyncio.sleep`: 0 matches.
   - Standard search in `common/database.py` for `db_sleep`: 97 matches.
   - Script `scratch/add_db_sleep.py` lines 33-34:
     ```python
     db_content = db_content.replace('from .db_pool import get_pool, create_pool, close_pool, db_lock', 'from .db_pool import get_pool, create_pool, close_pool, db_lock, db_sleep')
     db_content = db_content.replace('await asyncio.sleep(', 'await db_sleep(')
     ```

2. **`db_sleep` Implementation in `common/db_pool.py` (lines 132-146)**:
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

3. **`LazyLock` Class Definition in `common/db_pool.py` (lines 8-31)**:
   ```python
   class LazyLock:
       def __init__(self):
           self._lock = None
           self._loop = None

       def _get_lock(self):
           try:
               loop = asyncio.get_running_loop()
           except RuntimeError:
               loop = None
           if self._lock is None or (loop and self._loop is not loop):
               self._lock = asyncio.Lock()
               self._loop = loop
           return self._lock
   ```
   No task ownership property (e.g. `_owner_task`) exists in `LazyLock`.

4. **Background Task & Batch Loop Sleep Contexts in `common/database.py`**:
   - Line 8199 in `postcopies_daily_cleanup_loop`:
     ```python
     sleep_sec = (next_run - now_msk).total_seconds()
     await db_sleep(max(10, sleep_sec))
     ```
   - Line 8209 in `postcopies_daily_cleanup_loop`:
     ```python
     await db_sleep(3600)
     ```
   - Line 8113 in `clean_old_postcopies_daily`:
     ```python
     await db_sleep(0.5)
     ```
   - Line 8175 in `clean_old_media_reposts_daily`:
     ```python
     await db_sleep(0.5)
     ```
   - Line 6218 in `clean_shadow_posts_chunked`:
     ```python
     await db_sleep(0.5)
     ```

5. **Direct `asyncio.sleep` in External DB Retry Loops**:
   - `site_tgach/tagging_worker.py` line 849:
     ```python
     if "locked" in str(e).lower():
         await asyncio.sleep(0.5 * (attempt + 1))
         continue
     ```

---

## 2. Logic Chain

1. **Observation 1 & Observation 3**: `scratch/add_db_sleep.py` performed a naive string replacement (`replace('await asyncio.sleep(', 'await db_sleep(')`). `LazyLock` wraps `asyncio.Lock` without tracking `asyncio.current_task()`. `db_lock.locked()` checks only if the lock is held globally by *any* task.
2. **Observation 2 & Observation 3 -> Lock Stealing**: When Task B calls `await db_sleep(delay)` while Task A holds `db_lock` inside `async with db_lock:`, `db_sleep` observes `db_lock.locked() == True`. Task B calls `db_lock.release()`, which forcibly unlocks `db_lock` out from under Task A during Task A's transaction. This breaks Task A's concurrency protection.
3. **Observation 2 & Observation 4 -> Permanent Lock Leak**: In `postcopies_daily_cleanup_loop` (lines 8199/8209), `db_sleep` is called for a 24-hour sleep without being inside an `async with db_lock:` block. If `db_lock` was locked by any task when `db_sleep` started, `lock_released` is set to `True`. After 24 hours, `finally:` executes `await db_lock.acquire()`. `db_sleep` returns to `postcopies_daily_cleanup_loop` with `db_lock` acquired. Because `postcopies_daily_cleanup_loop` does not have an `async with db_lock:` block, `db_lock` is never released, causing a permanent deadlock across the entire bot.
4. **Observation 2 & Observation 4 -> Self-Deadlock**: In batch deletion loops (lines 6218, 8113, 8175), `db_sleep` is called OUTSIDE `async with db_lock:`. If `db_sleep` reacquires `db_lock` in `finally:`, the loop returns to `async with db_lock:`. Since `asyncio.Lock` is non-reentrant, the task attempts to acquire a lock it already holds, causing a permanent self-deadlock.
5. **Observation 5**: `site_tgach/tagging_worker.py` still contains direct `asyncio.sleep` calls in DB retry contexts, meaning the patch was incomplete across non-`database.py` DB operations.

---

## 3. Caveats

1. **Unchecked Non-Core Background Tasks**: Modules in `site_tgach/` (`main.py`, `importer.py`, `neuro_scanner.py`) were inspected via static pattern matching; full line-by-line runtime execution traces of every `site_tgach` worker were not performed under high concurrency load.
2. **Code Modifiability Constraint**: As an explorer subagent, no code modifications were made to test fixes directly in-place.

---

## 4. Conclusion

Requirement R3 **FAILS** validation. While `await asyncio.sleep` calls inside `common/database.py` were textually replaced with `await db_sleep`, the replacement was done blindly via global find-and-replace without task ownership tracking in `LazyLock`. This introduced severe regression hazards:
- **Lock Stealing**: `db_sleep` releases locks held by other concurrent tasks.
- **Permanent Application Deadlock**: Long background sleeps (24 hours) in `postcopies_daily_cleanup_loop` leak `db_lock` permanently if `db_lock` was locked at sleep initiation.
- **Self-Deadlock**: Inter-batch sleeps outside `async with db_lock:` cause self-deadlocking on non-reentrant locks.

---

## 5. Verification Method

1. **Verify Absence of `asyncio.sleep` in `common/database.py`**:
   Command: `powershell -Command "Select-String -Path 'common/database.py' -Pattern 'asyncio\.sleep'"`
   Expected Output: 0 matches.

2. **Verify `db_sleep` Implementation Defect**:
   Inspect `common/db_pool.py:132-146` to confirm lack of task ownership validation before `db_lock.release()`.

3. **Verify Background Loop Sleep Misuse**:
   Inspect `common/database.py:8199` and `8209` to confirm `await db_sleep` is called for 24-hour / 1-hour background sleeps outside `async with db_lock:`.

4. **Verify Test Suite Status**:
   Command: `.\venv\Scripts\python -m pytest tests/test_db_pool.py`
   Expected Output: 2 passed.
