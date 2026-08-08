# dvachbot Audit & Verification Plan

## Overview
Verify recent fixes in `dvachbot` for R1 (Proxy Reversion), R2 (`format_header` Fix), and R3 (Database Concurrency Patch).

## Iteration Strategy
For each milestone (M1, M2, M3):
1. **Explore**: Dispatch Explorers (`teamwork_preview_explorer`) to audit target files, verify line-by-line implementation, check for syntax or import issues, and verify logic.
2. **Implement/Fix (if needed)**: If defects or missing imports are found, dispatch Workers (`teamwork_preview_worker`) to perform native source edits and run tests.
3. **Review & Challenge**: Dispatch Reviewers (`teamwork_preview_reviewer`) and Challengers (`teamwork_preview_challenger`) to independently review code and run stress tests / unit tests.
4. **Audit**: Dispatch Forensic Auditor (`teamwork_preview_auditor`) to verify zero cheating, no dummy mocks, and full integrity.
5. **Gate Check**: Record verdicts in `GATE_STATUS.md`. Mark milestone complete when all gates pass.

## Milestone Breakdown
- **M1: Telegram File Proxy (R1)**
  - Target: `site_tgach/main.py`
  - Check: Ensure `/files/` endpoint returns HTTP 307 Redirect to `api.telegram.org`.
- **M2: `format_header` Fix (R2)**
  - Target: `user_manager.py`, `main.py`
  - Check: Ensure `format_header` is defined and properly imported; check `cmd_anime` and generic mode commands for `NameError`.
- **M3: DB Concurrency Patch (R3)**
  - Target: `common/database.py`, `common/db_pool.py`
  - Check: Ensure `await asyncio.sleep` replaced by `await db_sleep`, and `db_sleep` safely releases/reacquires `db_lock`.
