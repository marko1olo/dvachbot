## 2026-08-08T13:40:27Z
<USER_REQUEST>
You are a Worker subagent (worker_playwright_multiangle) for project dvachbot at working directory C:\Users\danat\Desktop\dvachbot.
Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_playwright_multiangle.

MANDATORY INSTRUCTION: You MUST read the original request file at C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md (specifically the latest follow-up header: ## Follow-up — 2026-08-08T13:33:45Z) and C:\Users\danat\Desktop\dvachbot\.agents\worker_ui_fix\handoff.md before doing anything else.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Task: Implement and execute Multi-Angle Playwright Browser Simulation (Milestone UI-R2).

1. **Write Playwright Script (`scratch/pw_multiangle_test.py`)**:
   - Launch Playwright headless Chromium. Ensure the local dev server is running on `http://127.0.0.1:8000` (or start it in background if down).
   - Set up event listeners:
     - `page.on('console', ...)` — log JS console errors/warnings.
     - `page.on('requestfailed', ...)` — track failed HTTP requests.
     - `page.on('response', ...)` — verify HTTP status codes for media (`/files/...`).
   - **Step A: Catalog Navigation**:
     - Navigate to Thread Catalog (`http://127.0.0.1:8000/b/` or `http://127.0.0.1:8000/b/catalog`).
     - Wait for network idle and DOM content to settle.
     - Assert `page.locator('img, video').count() > 0`.
     - Capture full-page screenshot and save to `C:\Users\danat\Desktop\dvachbot\scratch\pw_catalog.png`.
   - **Step B: Thread Navigation**:
     - Extract a valid thread link from the catalog (or navigate directly to an active thread with media, e.g. `http://127.0.0.1:8000/b/res/<thread_id>.html`).
     - Wait for network idle and DOM content to settle.
     - Assert `page.locator('img, video').count() > 0`.
     - Capture full-page screenshot and save to `C:\Users\danat\Desktop\dvachbot\scratch\pw_thread.png`.
   - **Step C: Network & Console Assertions**:
     - Assert ZERO HTTP 404 Not Found errors on media requests (`/files/...`).
     - Assert ZERO uncaught JS exceptions/errors.

2. **Execute Script & Verify Screenshots**:
   - Run `pw_multiangle_test.py` using project Python environment (e.g. `.\venv\Scripts\python.exe scratch/pw_multiangle_test.py`).
   - Verify `scratch/pw_catalog.png` and `scratch/pw_thread.png` exist, are non-empty, and contain real rendered page captures.

3. **Reporting**:
   - Write script output and log execution details to `C:\Users\danat\Desktop\dvachbot\.agents\worker_playwright_multiangle\changes.md`.
   - Write handoff report to `C:\Users\danat\Desktop\dvachbot\.agents\worker_playwright_multiangle\handoff.md`.
   - Send a message back to orchestrator when complete.
</USER_REQUEST>
