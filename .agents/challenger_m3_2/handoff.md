# Handoff Report — Milestone M3 Verification & Stress Testing (Challenger 2)

## 1. Observation

1. **Empirical Stress Test Failure in `db_sleep` Cancellation Re-acquisition (`common/db_pool.py`)**:
   - Created stress harness `tests/test_empirical_stress_db_concurrency.py`.
   - Executed `$env:PYTHONPATH='.'; .\venv\Scripts\python.exe -m pytest tests/test_empirical_stress_db_concurrency.py`.
   - **Result**: `2 failed, 3 passed in 4.31s`.
   - **Verbatim Error Log**:
     ```
     FAILED tests/test_empirical_stress_db_concurrency.py::test_db_sleep_cancellation_during_reacquire
     ...
     common\db_pool.py:37: in release
         self._lock.release()
     ...
     RuntimeError: Lock is not acquired.
     ```
   - **Mechanism**:
     When Task A is inside `db_sleep` and attempts `await db_lock.acquire()` inside `finally:`, if Task A is cancelled before `acquire()` completes, Task A unwinds out of `db_sleep` without owning `db_lock`. Task A's outer `async with db_lock:` block executes `__aexit__` -> `db_lock.release()`. Because `release()` does not check if Task A owns the lock, it forcibly releases Task B's lock while Task B is actively executing. Task B subsequently fails with `RuntimeError: Lock is not acquired`.

2. **Full Pytest Suite Failure / Timeout (`tests/test_files_endpoint.py`)**:
   - Executed `$env:PYTHONPATH='.'; .\venv\Scripts\python.exe -m pytest tests/`.
   - **Result**: Timeout during execution of `tests/test_files_endpoint.py`.
   - **Verbatim Error**: `test_telegram_proxy_streaming` in `tests/test_files_endpoint.py` expects HTTP status 200 and proxy streaming, whereas `site_tgach/main.py` line 10607 was updated under R1 to return `RedirectResponse(url=..., status_code=307)`.

3. **AST Static Bindings Verification**:
   - **R1 Audit**: Verified `site_tgach/main.py` lines 10607, 10619, 10627, 10635, 10643, 10653, 10664. All file redirect routes use `RedirectResponse` with `status_code=307` and `headers={"Access-Control-Allow-Origin": "*"}`.
   - **R2 Audit**: Verified `user_manager.py` line 37 (`from post_helpers import format_header`) and `post_helpers.py` line 297 (`def format_header(...)`). Functions `cmd_anime` (line 815), `cmd_zaputin` (line 1363), `cmd_suka_blyat` (line 1470), and `cmd_deanon` (line 1272) call `format_header` cleanly without `NameError`.
   - **R3 Audit**: Verified 96 occurrences of `db_sleep` across `common/database.py` and `site_tgach/tagging_worker.py`. `db_sleep` checks `is_owned_by_current_task()`. However, lock re-acquisition cancellation handling in `db_pool.py` contains a critical bug.

---

## 2. Logic Chain

1. **Lock Stealing via Task Cancellation**:
   - Observation 1 proves that `db_sleep`'s lock re-acquisition in `finally` is vulnerable to cancellation.
   - If Task A is cancelled while waiting on `await db_lock.acquire()`, Task A does not acquire `db_lock`, but `lock_released` remains `True`.
   - When Task A unwinds out of `db_sleep`, Task A's outer `async with db_lock:` block executes `__aexit__`, which invokes `db_lock.release()`.
   - Because `LazyLock.release()` does not check if the current task owns the lock, it releases the lock held by Task B.
   - This corrupts lock state and causes Task B to throw `RuntimeError: Lock is not acquired` when it exits.

2. **Test Suite Discrepancy**:
   - Observation 2 proves that `tests/test_files_endpoint.py` was not updated to align with the R1 requirement changes.
   - Expecting status code 200 in `test_telegram_proxy_streaming` causes test failures and timeouts during `pytest`.

3. **AST Verification**:
   - Observation 3 confirms AST static bindings for `format_header` and HTTP 307 redirects for `/files/` are structurally sound.

---

## 3. Caveats

- Unit tests in `tests/test_db_pool.py`, `tests/test_database.py`, `tests/test_database_sync.py`, and `tests/test_dbchecker.py` (15 tests) pass, but they do NOT cover task cancellation during `db_sleep` re-acquisition.
- No other caveats; empirical reproduction script `tests/test_empirical_stress_db_concurrency.py` conclusively demonstrates the failure mode.

---

## 4. Conclusion

Verdict: **REQUEST_CHANGES**

- **Reason 1**: Critical concurrency vulnerability in `common/db_pool.py` where task cancellation during `db_sleep` lock re-acquisition steals another task's lock and causes `RuntimeError: Lock is not acquired`.
- **Reason 2**: `tests/test_files_endpoint.py` fails/times out due to outdated assertions expecting HTTP 200 streaming instead of HTTP 307 redirects.

### Actionable Remediation Steps for Worker:
1. In `common/db_pool.py`:
   - Update `LazyLock.release()` to verify `is_owned_by_current_task()` or `self._owner is None` before releasing.
   - Update `LazyLock.__aexit__` to only call `release()` if `is_owned_by_current_task()` is True.
2. In `tests/test_files_endpoint.py`:
   - Update `test_telegram_proxy_streaming` to assert `resp.status_code == 307` and verify `RedirectResponse` headers.

---

## 5. Verification Method

To verify the failure and subsequent fixes:
1. Run empirical stress harness:
   ```powershell
   $env:PYTHONPATH='.'
   .\venv\Scripts\python.exe -m pytest tests/test_empirical_stress_db_concurrency.py
   ```
   *Current status*: 2 failed (`test_db_sleep_cancellation_during_reacquire`, `test_high_concurrency_db_sleep_retries`).
   *Expected status after fix*: 5 passed.

2. Run full pytest suite:
   ```powershell
   $env:PYTHONPATH='.'
   .\venv\Scripts\python.exe -m pytest tests/
   ```
   *Expected status after fix*: All tests pass without timeouts.
