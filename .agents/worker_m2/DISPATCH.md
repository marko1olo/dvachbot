# Dispatch Assignment — worker_m2

## Identity
- Role: teamwork_preview_worker (Frontend Media 404 Fallback Specialist)
- Working Directory: C:\Users\danat\Desktop\dvachbot\.agents\worker_m2
- Target Project Directory: C:\Users\danat\Desktop\dvachbot
- Original Request File: C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md
- Scope Document: C:\Users\danat\Desktop\dvachbot\.agents\orchestrator\PROJECT.md
- Explorer Findings: C:\Users\danat\Desktop\dvachbot\.agents\explorer_r2\handoff.md

## Objective — Milestone 2 (M2): Frontend 404 Fallback & Retry Suppression
Implement the frontend 404 media error fallback and retry loop suppression system in `site_tgach/static/js/main.src.js` and `site_tgach/static/js/main.js`.

Specifically:
1. **Implement `FailedMediaCache` Session Singleton**:
   - Create a global in-memory session cache `FailedMediaCache` (with `isFailed(url)`, `markFailed(url)`, `normalizeUrl(url)`).
2. **Refactor `handleImageError(img)`**:
   - Immediately unbind `img.onerror = null;` upon entry.
   - For local `/files/` URLs or failed media, record URL in `FailedMediaCache.markFailed(url)`.
   - Cease setting `img.src = url + "?skip="` which causes recursive 404 loops.
   - Replace thumbnail container with a static error placeholder element (`⚠️ Media Unavailable`).
3. **Eliminate Timestamp Cache-Buster Loops**:
   - In `SmartLoader.onLoadFinished` and `MediaStreamManager.loadVideoWithRetry`, remove `?retry=${Date.now()}` timestamp generation.
   - Intercept enqueued media in `SmartLoader` and check `FailedMediaCache.isFailed(url)` before starting HTTP requests.
4. **WebSocket Re-render Protection**:
   - In `PostRenderer.create` / `initializePostFeatures`, check `FailedMediaCache.isFailed(url)` before creating `<img>` / `<video>` tags so DOM re-renders do not fire new GET requests for broken media.
5. **Synchronize JS Files**:
   - Apply all JS changes identically to both `site_tgach/static/js/main.src.js` AND `site_tgach/static/js/main.js`.
6. **Automated Verification Test**:
   - Create/run a Node JS test script `node tests/test_frontend_fallback.js` simulating 404 responses on `/files/...` and verifying exact 1 HTTP GET request sent per URL and zero retries on re-render.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output Requirements
Write your handoff report to C:\Users\danat\Desktop\dvachbot\.agents\worker_m2\handoff.md with full execution and test results.
