## 2026-08-08T14:50:04Z

<USER_REQUEST>
You are a Worker subagent (worker_ui_remediation_fresh) for project dvachbot at working directory C:\Users\danat\Desktop\dvachbot.
Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_ui_remediation_fresh.

MANDATORY INSTRUCTION: You MUST read the original request file at C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md (specifically the latest follow-up header: ## Follow-up — 2026-08-08T13:33:45Z) and C:\Users\danat\Desktop\dvachbot\.agents\reviewer_ui_2\handoff.md before doing anything else.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Task: Remediate Jinja2 Proxy Prioritization, JS Fallbacks, and Playwright Assertions.

1. **Jinja2 Templates Refactoring (`site_tgach/templates/`)**:
   - In `catalog.jinja2`, `thread.jinja2`, `board.jinja2`, and `gallery.jinja2`: Update media URL selection logic to PRIORITIZE local `/files/{file_id}` proxy URLs FIRST whenever `thumbnail_file_id` or `original_file_id` exists, BEFORE evaluating external `thumbnail_url` / `original_url` (which point to external host `catbox.moe` that fails with ORB/HTTP2 errors in local environments).
     - Example for thumbnail: `{% set thumb_url = (file0.thumbnail_file_id and '/files/' ~ file0.thumbnail_file_id) or (file0.original_file_id and '/files/' ~ file0.original_file_id) or file0.thumbnail_url or file0.original_url %}`
     - Example for original: `{% set orig_url = (file0.original_file_id and '/files/' ~ file0.original_file_id) or file0.original_url %}`
   - Fix HTML syntax typo in `site_tgach/templates/thread.jinja2` (lines ~348-349) where `<video clas<video class=...` was duplicated.

2. **Frontend JS Refactoring (`site_tgach/static/js/main.src.js` & `main.js`)**:
   - Ensure `createCatalogCard` and client-side DOM media rendering prioritize `/files/${f.thumbnail_file_id}` or `/files/${f.original_file_id}` proxy endpoints FIRST when rendering `img.src` or `video.poster`.
   - Ensure `main.js` is byte-for-byte synced with `main.src.js`.

3. **Strengthen Playwright Multi-Angle Simulation (`scratch/pw_multiangle_test.py`)**:
   - Update `scratch/pw_multiangle_test.py` to:
     - Check image natural dimensions: assert that rendered catalog and thread images have `complete == true` and `naturalWidth > 0`.
     - Assert zero failed requests (`len(failed_requests) == 0`) for `/files/...` proxy media endpoints.
   - Execute `scratch/pw_multiangle_test.py` (`.\venv\Scripts\python.exe scratch/pw_multiangle_test.py`) to regenerate `scratch/pw_catalog.png` and `scratch/pw_thread.png`.

4. **Testing & Reporting**:
   - Run pytest suite (`.\venv\Scripts\python.exe -m pytest tests/`).
   - Write change summary to `C:\Users\danat\Desktop\dvachbot\.agents\worker_ui_remediation_fresh\changes.md`.
   - Write handoff report to `C:\Users\danat\Desktop\dvachbot\.agents\worker_ui_remediation_fresh\handoff.md`.
   - Send a message back to orchestrator when complete.
</USER_REQUEST>
