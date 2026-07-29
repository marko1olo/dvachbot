# Orchestration Plan — site_tgach Media Pipeline Audit & Fix

## Objectives & Requirements
- **R1. Image & Media Loading Pipeline Audit & Fix**: Investigate how images, thumbnails, media previews, Catbox/Telegram mirrors, and Freeimage/Pixhost/ImgBB fallbacks are loaded and served by site_tgach (`main.py`, `imgbb.py`, `pixhost.py`, `tagging_worker.py`). Resolve any broken routes, missing headers, 404/500 errors, or failed download fallbacks.
- **R2. End-to-End Verification & Browser Probe**: Verify image rendering and API image endpoints (`/file/...`, `/thumb/...`, `/i/...`, `/preview/...`) via automated checks, ensuring HTTP 200 responses, correct Content-Type headers, and valid image binary data.

## Milestones
1. **Milestone 1: Codebase & Pipeline Audit (Explorers)**
   - Dispatch 3 Explorers to audit `main.py`, `imgbb.py`, `pixhost.py`, `tagging_worker.py`, Catbox/Telegram mirrors, image routes (`/file/`, `/thumb/`, `/i/`, `/preview/`), headers, and error handling.
   - Synthesize findings into concrete root causes and fix strategies.

2. **Milestone 2: Fix Implementation & Hardening (Worker)**
   - Dispatch Worker to implement fixes for all identified bugs, broken fallbacks, missing headers, or bad proxy/mirror routes.
   - Worker must run unit tests and manual endpoint verification.

3. **Milestone 3: Verification, Adversarial Testing, & Forensic Audit**
   - Dispatch 2 Reviewers to independently review code changes, headers, and exception handling.
   - Dispatch 2 Challengers to perform automated endpoint & media probe tests (verifying 200 OK, Content-Type, binary validity).
   - Dispatch 1 Forensic Auditor (`teamwork_preview_auditor`) to verify zero cheating, zero mock responses, and complete authentic implementation.

## Iteration Gates
- All build/unit tests pass.
- Reviewers approve.
- Challengers confirm end-to-end endpoint validity.
- Forensic Auditor verdict is CLEAN.
