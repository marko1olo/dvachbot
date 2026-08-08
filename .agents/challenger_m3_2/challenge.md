# Empirical Challenge Report — Milestone M3 (Empirical Challenger 2)

## Challenge Summary

**Overall risk assessment**: CRITICAL

Empirical stress testing of database lock concurrency and `db_sleep` behavior under edge conditions revealed a **CRITICAL concurrency vulnerability** (lock stealing and lock corruption upon task cancellation) in `common/db_pool.py`. Furthermore, full test suite execution identified a test failure/hang in `tests/test_files_endpoint.py` due to outdated expectations regarding HTTP 307 redirects.

---

## Challenges

### [Critical] Challenge 1: Lock Stealing & Lock Corruption in `db_sleep` / `LazyLock` upon Task Cancellation

- **Assumption challenged**: `db_sleep` safely releases and reacquires `db_lock` without leaking locks, corrupting lock state, or releasing another task's lock if the sleeping task is cancelled.
- **Attack scenario**:
  1. Task A enters `async with db_lock:` and acquires `db_lock`.
  2. Task A calls `await db_sleep(delay)`. `db_sleep` calls `db_lock.release()` and sets `lock_released = True`.
  3. Task B enters `async with db_lock:` and acquires `db_lock`. Task B is now the registered owner (`_owner = Task B`).
  4. Task A finishes `asyncio.sleep` and enters `finally: await db_lock.acquire()` to reacquire the lock. Task A blocks waiting for Task B.
  5. Task A is CANCELLED (`task.cancel()`) while waiting inside `db_lock.acquire()`.
  6. `await db_lock.acquire()` raises `asyncio.CancelledError`. Task A **does NOT acquire** `db_lock`.
  7. Task A unwinds out of `db_sleep` with `CancelledError`.
  8. Task A's outer `async with db_lock:` context manager executes `__aexit__`, which calls `db_lock.release()`.
  9. Because `LazyLock.release()` does **not** check whether the calling task is the registered owner, Task A's `release()` call **forcibly releases Task B's lock** while Task B is actively executing inside its critical section!
  10. Task B loses mutual exclusion protection mid-execution. When Task B eventually finishes and exits its `async with db_lock:` block, `db_lock.release()` is called on an already unlocked lock, raising `RuntimeError: Lock is not acquired`.
- **Empirical reproduction**:
  - Test case `test_db_sleep_cancellation_during_reacquire` in `tests/test_empirical_stress_db_concurrency.py`:
    ```python
    RuntimeError: Lock is not acquired.
    ```
- **Blast radius**: Production background workers and web handlers using `db_sleep` can steal locks from active tasks upon task cancellation or timeout, causing race conditions, data corruption, and unhandled `RuntimeError` exceptions.
- **Suggested mitigation**:
  1. Update `LazyLock.release()` to verify `is_owned_by_current_task()` before releasing:
     ```python
     def release(self):
         if self._lock and self._lock.locked():
             if self.is_owned_by_current_task() or self._owner is None:
                 self._owner = None
                 self._lock.release()
     ```
  2. Update `LazyLock.__aexit__` to only call `release()` if `is_owned_by_current_task()` is True:
     ```python
     async def __aexit__(self, exc_type, exc_val, exc_tb):
         if self.is_owned_by_current_task():
             self.release()
     ```
  3. Ensure `db_sleep` sets `lock_released = False` if re-acquisition in `finally` fails or is cancelled.

---

### [High] Challenge 2: Test Suite Regression in `tests/test_files_endpoint.py`

- **Assumption challenged**: Running `pytest` on all project tests produces 100% pass rate with zero regressions.
- **Attack scenario**: `tests/test_files_endpoint.py` contains `test_telegram_proxy_streaming`, which asserts `resp.status_code == 200` and verifies `_proxy_protected_telegram_file` is called. However, Requirement R1 updated `/files/` endpoints in `site_tgach/main.py` to issue `HTTP 307 RedirectResponse` directly to Telegram API. When running `pytest`, `test_files_endpoint.py` failed/timed out due to this mismatch.
- **Blast radius**: Broken test suite, failing CI/CD, unvalidated endpoint assertions.
- **Suggested mitigation**: Update `tests/test_files_endpoint.py` (`test_telegram_proxy_streaming`) to assert HTTP status code 307 and verify `RedirectResponse` headers (`location` and `Access-Control-Allow-Origin: *`).

---

## Stress Test Results

| Scenario | Expected Behavior | Actual Behavior | Pass/Fail |
|---|---|---|---|
| Non-owner task calling `db_sleep(delay)` | Skips lock release & reacquire, sleeps safely | Skips lock release & reacquire, sleeps safely | **PASS** |
| Task cancelled during `asyncio.sleep` inside `db_sleep` | Reacquires lock in `finally`, unwinds through `__aexit__`, releases lock cleanly | Reacquires lock, unwinds, releases lock cleanly | **PASS** |
| Task cancelled during `db_lock.acquire()` re-acquisition in `db_sleep` | Task unwinds without releasing Task B's lock; Task B finishes cleanly | Task A calls `release()`, steals Task B's lock while Task B runs, causing `RuntimeError` on Task B exit | **FAIL** |
| High concurrency (50 tasks) using `db_sleep` inside `async with db_lock:` | Mutual exclusion preserved across critical section | Critical section lost atomicity when lock released mid-block; overlapping executions occurred | **FAIL** |
| Static AST audit of `format_header` bindings | Correctly imported and bound in `user_manager.py` and `main.py` | Defined in `post_helpers.py`, explicitly imported in `user_manager.py` (`from post_helpers import format_header`) | **PASS** |
| Static AST audit of `/files/` HTTP 307 redirects | `/files/` and aliases issue HTTP 307 RedirectResponse | Verified in `site_tgach/main.py` lines 10607, 10619, 10627, 10635 | **PASS** |

---

## Unchallenged Areas

- Non-database web routing endpoints outside `/files/` — out of scope for M3 empirical challenge.
