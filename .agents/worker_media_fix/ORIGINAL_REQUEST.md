## 2026-07-29T19:48:19Z

<USER_REQUEST>
You are a Worker subagent (worker_media_fix).
Your working directory is: C:\Users\danat\Desktop\dvachbot\.agents\worker_media_fix
Target project directory: C:\Users\danat\Desktop\dvachbot

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Objective:
Implement all fixes and automated verification test probes for site_tgach media/image/thumbnail pipeline as identified in the audit.

Detailed Tasks:
1. Route Aliases in `site_tgach/main.py`:
   - Register FastAPI route aliases for `/file/{file_id:path}`, `/thumb/{file_id:path}`, `/i/{file_id:path}`, `/preview/{file_id:path}`, `/{board_id}/src/{file_id:path}`, `/{board_id}/thumb/{file_id:path}` delegating to `get_telegram_file`. Ensure filename and skip parameters are cleanly forwarded.

2. Headers & CORS in `site_tgach/main.py`:
   - Inject `"Access-Control-Allow-Origin": "*"` into response headers across `get_telegram_file`, `_proxy_protected_telegram_file`, and `_proxy_external_url` for both redirects (307) and proxied media streams.
   - Ensure proper `Content-Type` and `Content-Disposition` headers are preserved/set.

3. Dead File Redis Sync in `site_tgach/main.py`:
   - In `_mark_random_dead_file(file_id)`, populate Redis key `dead_file:public:{file_id}` in backend cache so dead file checks in `get_telegram_file` hit Redis instantly across worker processes.

4. Session Reuse & Bot Probing Optimization in `site_tgach/main.py`:
   - Replace per-request `aiohttp.ClientSession` creation in proxy functions (`_proxy_protected_telegram_file`, `_proxy_external_url`) with a shared app-level session pool.
   - Cap bot probing in `get_cached_file_path` to max 2 bot candidates to prevent thundering herd rate limits on Telegram API.

5. Mirror Module Corrections:
   - `site_tgach/pixhost.py`: Fix direct image link construction so direct image URLs (`https://img{dir}.pixhost.to/images/{dir}/{file}`) are returned/stored instead of HTML viewer page links (`https://pixhost.to/show/...`).
   - `site_tgach/mirror_worker.py`: Add `freeimage` to allowed mirror upload types when `FREEIMAGE_API_KEY` is configured.

6. R2 CDN Support in `site_tgach/main.py`:
   - Add R2 mirror support in `_select_mirror_strategically` and `get_telegram_file` (supporting HTTP 307 redirect to R2 URL when present, skipping R2 when `"r2"` is in `skip`).

7. Automated Test Suite & Media Loading Probe (Requirement R2):
   - Create `tests/test_files_endpoint.py` using pytest / FastAPI TestClient or httpx to test `/files/{file_id}`, `/file/{file_id}`, `/thumb/{file_id}`, `/i/{file_id}`, `/preview/{file_id}`, `skip` filtering, CORS headers (`Access-Control-Allow-Origin`), and 307 redirects.
   - Create `verification_scripts/media_loading_probe.py` that probes endpoint routes and verifies 200 OK / 307 responses, correct Content-Type headers, and valid image binary data.

8. Execution & Verification:
   - Run the test suite (`pytest` or `python -m pytest tests/test_files_endpoint.py`) and `python verification_scripts/media_loading_probe.py`.
   - Ensure all tests pass with 0 errors.

Output Requirements:
- Write your changes summary to `C:\Users\danat\Desktop\dvachbot\.agents\worker_media_fix\changes.md`.
- Write your completion handoff report to `C:\Users\danat\Desktop\dvachbot\.agents\worker_media_fix\handoff.md` with explicit build/test execution output logs.
- Send a message to the orchestrator when complete.
</USER_REQUEST>
