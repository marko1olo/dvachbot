# Dispatch Assignment — worker_m3_gen3

## Identity
- Role: teamwork_preview_worker (Media Resiliency & TestClient Deadlock Fix Specialist)
- Working Directory: C:\Users\danat\Desktop\dvachbot\.agents\worker_m3_gen3
- Target Project Directory: C:\Users\danat\Desktop\dvachbot
- Original Request File: C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md
- Scope Document: C:\Users\danat\Desktop\dvachbot\.agents\orchestrator\PROJECT.md
- Reviewer Failure Report: C:\Users\danat\Desktop\dvachbot\.agents\reviewer_m3_1\handoff.md

## Objective — Milestone 3 (M3) Remediation
Fix the `TestClient` cross-event-loop `aiosqlite` deadlock in `site_tgach/main.py` / `tests/test_files_endpoint.py`.

Specifically:
1. **Fix `get_telegram_file` in `site_tgach/main.py`**:
   - In `get_telegram_file`, wrap `await is_file_permanently_failed(file_id)` in a `try...except Exception:` block, or check `if db.pool and await is_file_permanently_failed(file_id):` so that when `TestClient` runs HTTP requests in a sync thread without an active `aiosqlite` pool, it gracefully falls through to standard file resolution instead of hanging/deadlocking.
2. **Execute pytest**:
   - Run `venv\Scripts\python.exe -m pytest tests/test_media_resiliency.py tests/test_files_endpoint.py -v`.
   - Confirm BOTH test suites pass with Exit Code 0 and ZERO timeouts.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output Requirements
Write your handoff report to C:\Users\danat\Desktop\dvachbot\.agents\worker_m3_gen3\handoff.md with passing pytest outputs for both `tests/test_media_resiliency.py` AND `tests/test_files_endpoint.py`.
