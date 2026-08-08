# Requirement R3: Database Concurrency Audit Report

**Target Files**: `common/database.py`, `common/db_pool.py`  
**Auditor**: DB Concurrency Explorer (`explorer_m3`)  
**Date**: 2026-08-08  
**Audit Verdict**: **FAIL (High Risk Regression Introduced)**

---

## 1. Executive Summary

Requirement R3 requested an audit of `common/database.py` and `common/db_pool.py` to:
1. Verify whether direct `await asyncio.sleep` calls inside `database.py` retry loops have been replaced with `await db_sleep`.
2. Verify the implementation of `db_sleep` to ensure it correctly releases `db_lock`, sleeps, and reacquires `db_lock` cleanly.
3. Check for any remaining direct `asyncio.sleep` calls in retry contexts, unhandled lock exceptions, re-entrancy issues, or lock leakage.

### Key Audit Findings:
1. **Replacement Status**: **PASS (Naively Completed)**. All 97 occurrences of `await asyncio.sleep` inside `common/database.py` were replaced with `await db_sleep`. No `asyncio.sleep` calls remain in `common/database.py`.
2. **`db_sleep` Implementation & Design**: **FAIL (Severe Architectural Defect)**.
   - `db_sleep` in `common/db_pool.py` checks `if db_lock.locked(): try: db_lock.release() ...`. However, `db_lock` (an instance of `LazyLock` wrapping `asyncio.Lock`) **does not track task ownership**.
   - As a result, calling `db_sleep` when `db_lock` is held by **another task** causes `db_sleep` to **steal and release the other task's lock mid-transaction**, breaking mutual exclusion.
   - Furthermore, in `finally:`, `db_sleep` executes `await db_lock.acquire()`, forcing the caller to acquire `db_lock` even if the caller was never holding it.
3. **Lock Leakage & Permanent Deadlock in Background Loops**: **FAIL (Critical Severity)**.
   - `scratch/add_db_sleep.py` blindly replaced `await asyncio.sleep` in long-running background tasks.
   - In `postcopies_daily_cleanup_loop` (lines 8199 & 8209 of `common/database.py`), `await db_sleep(max(10, sleep_sec))` is called for a **24-hour sleep**.
   - If `db_lock` happens to be locked when `postcopies_daily_cleanup_loop` starts its 24-hour sleep, `db_sleep` steals the lock, sleeps 24 hours, and upon waking up acquires `db_lock`. Because `postcopies_daily_cleanup_loop` is not in an `async with db_lock:` block, it **never releases `db_lock`**, permanently deadlocking all database queries in the entire application.
4. **Self-Deadlock in Inter-batch Cleanup Loops**: **FAIL (High Severity)**.
   - Inter-batch sleeps outside `async with db_lock:` (e.g., `clean_shadow_posts_chunked` line 6218, `clean_old_postcopies_daily` line 8113, `clean_old_media_reposts_daily` line 8175) call `await db_sleep(0.5)`.
   - If `db_sleep` acquires `db_lock` in its `finally:` block, the caller returns to the top of its loop and executes `async with db_lock:`. Since `asyncio.Lock` is non-reentrant, the task **deadlocks on itself**.
5. **Un-patched DB Retry Loops Outside `database.py`**: **FAIL (Scope Gap)**.
   - `site_tgach/tagging_worker.py` line 849 contains a direct `await asyncio.sleep(0.5 * (attempt + 1))` call inside a database `locked` retry loop.

---

## 2. Codebase & File Inventory

| File Path | Role | Audited Status |
| --- | --- | --- |
| `common/db_pool.py` | Contains `LazyLock` class, `db_lock`, and `db_sleep` helper | Flawed lock release/reacquire logic; missing task ownership tracking |
| `common/database.py` | Primary database module (~8211 lines) | All 97 `asyncio.sleep` calls converted to `db_sleep`, but introduced lock leaks and deadlocks in background/batch loops |
| `scratch/add_db_sleep.py` | Script used to apply patch | Applied simple string replacement `replace('await asyncio.sleep(', 'await db_sleep(')` without context awareness |
| `site_tgach/tagging_worker.py` | Background media tagging worker | Direct `asyncio.sleep` in DB retry loop (line 849) |

---

## 3. Analysis of `db_sleep` Implementation in `common/db_pool.py`

### 3.1 Code Listing (`common/db_pool.py:132-146`)

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

### 3.2 Analysis of `LazyLock` (`common/db_pool.py:8-39`)

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

    async def acquire(self):
        return await self._get_lock().acquire()

    def release(self):
        if self._lock:
            self._lock.release()

    def locked(self):
        return self._get_lock().locked()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()

db_lock = LazyLock()
```

---

## 4. Deep Technical Analysis of Concurrency Vulnerabilities

### Vulnerability 1: Lock Stealing (No Task Ownership Tracking)
- `db_lock.locked()` checks if the underlying `asyncio.Lock` is locked by **any** task in the event loop.
- Python's standard `asyncio.Lock` does **not** record the owning `asyncio.Task`.
- **Scenario**:
  1. Task A (e.g. `save_post`) acquires `db_lock` via `async with db_lock:` and begins executing a multi-statement transaction.
  2. Task B (e.g. `postcopies_daily_cleanup_loop` or a helper not holding `db_lock`) calls `await db_sleep(0.5)`.
  3. Task B checks `if db_lock.locked():` -> returns `True` (because Task A holds it).
  4. Task B calls `db_lock.release()` -> **Task A's lock is forcibly released while Task A is mid-transaction!**
  5. Task C can now acquire `db_lock` concurrently with Task A, corrupting isolation.

### Vulnerability 2: Permanent Lock Leakage & Application Deadlock
- **Location**: `common/database.py` lines 8199 and 8209 in `postcopies_daily_cleanup_loop`:
  ```python
  sleep_sec = (next_run - now_msk).total_seconds()
  await db_sleep(max(10, sleep_sec)) # Sleeping up to 86,400 seconds (24h)
  ```
- **Scenario**:
  1. `postcopies_daily_cleanup_loop` is a background task. It does NOT acquire `db_lock`.
  2. It calls `await db_sleep(86400)`.
  3. If `db_lock` is locked by ANY other task at that precise instant, `db_sleep` sets `lock_released = True`, releases the lock, and calls `await asyncio.sleep(86400)`.
  4. 24 hours later, `db_sleep` finishes `asyncio.sleep`. The `finally:` block executes `if lock_released: await db_lock.acquire()`.
  5. `db_sleep` acquires `db_lock` and returns to `postcopies_daily_cleanup_loop`.
  6. `postcopies_daily_cleanup_loop` does not have an `async with db_lock:` context manager, so it **never releases `db_lock`**.
  7. **Result**: `db_lock` is leaked permanently. Every database call in the entire application that uses `async with db_lock:` will hang forever.

### Vulnerability 3: Self-Deadlock in Inter-batch Cleanup Loops
- **Locations**: `common/database.py` line 6218 (`clean_shadow_posts_chunked`), line 8113 (`clean_old_postcopies_daily`), line 8175 (`clean_old_media_reposts_daily`).
- **Code Pattern**:
  ```python
  while True:
      async with db_lock:
          # Perform batch deletion inside db_lock
          ...
      # Exit async with db_lock block -> db_lock is released!
      await db_sleep(0.5) # Call db_sleep OUTSIDE db_lock!
  ```
- **Scenario**:
  1. Batch deletion finishes, `async with db_lock` exits, releasing `db_lock`.
  2. Line 8113 calls `await db_sleep(0.5)`.
  3. If another task acquired `db_lock` during that microsecond, `db_sleep` steals and releases it, setting `lock_released = True`.
  4. `db_sleep` sleeps 0.5s, then in `finally:` executes `await db_lock.acquire()`.
  5. `db_sleep` returns to `clean_old_postcopies_daily` with `db_lock` acquired!
  6. The loop iterates back to `async with db_lock:`.
  7. `async with db_lock:` calls `await db_lock.acquire()`.
  8. Because Python's `asyncio.Lock` is **non-reentrant**, attempting to acquire a lock already held by the current task causes a **Self-Deadlock**. The task hangs indefinitely waiting for itself.

### Vulnerability 4: Lock Leakage on Task Cancellation
- **Scenario**:
  1. A task is sleeping inside `await db_sleep(delay)`.
  2. The task is cancelled via `task.cancel()`.
  3. `asyncio.sleep(delay)` raises `asyncio.CancelledError`.
  4. The `finally:` block in `db_sleep` executes `if lock_released: await db_lock.acquire()`.
  5. The cancelled task blocks on `await db_lock.acquire()` before propagating `CancelledError`.
  6. Once acquired, `CancelledError` escapes `db_sleep`.
  7. If `db_sleep` was called outside `async with db_lock:`, `db_lock` remains acquired by the dead task and is **never released**.

---

## 5. Verification Matrix & Summary Table

| Requirement Check | Status | Evidence / Observation | Risk Level |
| --- | --- | --- | --- |
| `await asyncio.sleep` replaced in `database.py` | PASS | 97 occurrences replaced with `db_sleep` | Low |
| `db_sleep` releases `db_lock` during retries | PASS (Conditional) | Works when caller legitimately holds `db_lock` | Medium |
| `db_sleep` lock ownership check | FAIL | `LazyLock` has no task tracking; steals other tasks' locks | CRITICAL |
| Background loop safety (`postcopies_daily_cleanup_loop`) | FAIL | 24-hour sleep in `db_sleep` causes permanent lock leak | CRITICAL |
| Batch loop safety (`clean_old_postcopies_daily`) | FAIL | Inter-batch `db_sleep` outside `async with` causes self-deadlock | HIGH |
| External DB modules audited | FAIL | `site_tgach/tagging_worker.py:849` still uses direct `asyncio.sleep` | MEDIUM |

---

## 6. Recommendations & Corrective Specifications

To resolve these defects cleanly without regression:

1. **Implement Task Ownership in `LazyLock`**:
   ```python
   class LazyLock:
       def __init__(self):
           self._lock = None
           self._loop = None
           self._owner_task = None

       async def acquire(self):
           lock = self._get_lock()
           await lock.acquire()
           self._owner_task = asyncio.current_task()

       def release(self):
           if self._lock:
               self._owner_task = None
               self._lock.release()

       def is_owned_by_current_task(self) -> bool:
           return self.locked() and self._owner_task is asyncio.current_task()
   ```

2. **Refactor `db_sleep` to Only Release Lock if Owned by Current Task**:
   ```python
   async def db_sleep(delay: float):
       """Sleeps safely, releasing db_lock ONLY if held by the calling task."""
       is_owner = db_lock.is_owned_by_current_task()
       if is_owner:
           db_lock.release()
       try:
           await asyncio.sleep(delay)
       finally:
           if is_owner:
               await db_lock.acquire()
   ```

3. **Revert Non-Retry Sleeps in `database.py` back to `asyncio.sleep`**:
   - Background scheduling loops (e.g. `postcopies_daily_cleanup_loop` lines 8199, 8209) MUST use `await asyncio.sleep()`.
   - Inter-batch delay sleeps (lines 6218, 8113, 8175) MUST use `await asyncio.sleep()`.

4. **Update External DB Retry Loops**:
   - `site_tgach/tagging_worker.py:849` should use `await db_sleep(...)` or safe lock release logic.
