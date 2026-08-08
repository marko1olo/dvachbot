# Dispatch Assignment — worker_m4

## Identity
- Role: teamwork_preview_worker (E2E Integration & Verification Suite Writer)
- Working Directory: C:\Users\danat\Desktop\dvachbot\.agents\worker_m4
- Target Project Directory: C:\Users\danat\Desktop\dvachbot
- Original Request File: C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md
- Scope Document: C:\Users\danat\Desktop\dvachbot\.agents\orchestrator\PROJECT.md

## Objective — Milestone 4 (M4): Unified E2E Acceptance Test Suite
Create and run a comprehensive E2E integration test suite verifying all 3 Acceptance Criteria in `ORIGINAL_REQUEST.md`:

1. **Verify 404 Link Generation**:
   - Verify post text `>>1234 https://domain.com/b/res/343717.html'>ТГАЧ` converts into clean `<a href="...">` without `&#039;&gt;ТГАЧ` leaks inside `href`.
   - Verify multi-parameter query strings (`?q=1&lang=en` and YouTube `watch?v=123&t=30s`) maintain parameter integrity in `href`.
2. **Verify Frontend Fallback**:
   - Run JS fallback test suite verifying 404 responses trigger EXACTLY 1 network request per session, enter `FailedMediaCache`, and yield zero retries on WebSocket DOM updates or re-renders.
3. **Verify Worker Safety**:
   - Verify Telegram worker failure UPSERTs into `FileRegistry` with `tags='download_failed'`, and post API endpoints output `is_broken: true`, `original_url: ""` for failed media.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output Requirements
Write your handoff report to C:\Users\danat\Desktop\dvachbot\.agents\worker_m4\handoff.md with passing outputs for both backend Python and frontend JS integration test suites.
