# Project: Dvachbot Web Platform Media & Frontend Restoration (`site_tgach`)

## Architecture
- **Backend**: FastAPI web application (`site_tgach/main.py`), Jinja2 templating (`site_tgach/templates/`), SQLite database (`dvach_bot.db`), background tagging and thumbnail workers (`site_tgach/tagging_worker.py`).
- **Media Proxy**: In-memory and disk cache for Telegram files, bot token rotation pool, ffmpeg frame extraction fallback, CDN mirror integration (ImgBB, PixHost, FreeImage).
- **Frontend Core**: Monolithic client script `site_tgach/static/js/main.src.js` (compiled to `main.js` and `main.js.gz`), CSS stylesheets `site_tgach/static/css/style.src.css` (compiled to `style.css` and `style.css.gz`).
- **Build Pipeline**: `scratch/minify_assets.py` synchronizes source CSS/JS into minified and gzipped browser bundles.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R1-A: Video Poster Template Fallback | Ensure `<video poster="...">` in all templates uses video thumbnail endpoints (`/thumb/` / dynamic extraction) rather than raw video `/files/BAAC...` streams. | M1 | Survey Media |
| 2 | R1-B: Video Thumbnail Proxy & FFmpeg Extraction | Add video `file_id -> thumbnail_id` lookup in `FileRegistry` and dynamic 1-frame ffmpeg JPEG extraction in `/thumb/` & `/preview/` endpoints. | M1 | Survey Media |
| 3 | R1-C: Bot Token Batch Probing & Cache De-poisoning | Eliminate 2-bot probing bottleneck and 120s negative cache poisoning in `get_cached_file_path`; allow protected tokens for board bots. | M1 | Survey Media |
| 4 | R2-A: Search Gallery Client-Side Error Fallback | Add `onerror="handleImageError(this)"` to `search_results.jinja2` image rendering to trigger immediate fallback to Telegram media proxy on CDN 404s. | M2 | Survey Media |
| 5 | R2-B: Fast Telegram Proxy Fallback (Bypass Wait Loop) | Ensure media fallback requests with `skip` parameters bypass the 7.5s sleep wait loop in `get_telegram_file` for sub-second responses. | M2 | Survey Media |
| 6 | R3-A: Chat Mascot Foreground Layering | Bring chat mascot to foreground (`--z-mascot: 100`) across both desktop and mobile viewports by fixing `@media (max-width: 768px)` override. | M3 | Survey Frontend |
| 7 | R3-B: Mascot Pointer-Events Isolation | Maintain `pointer-events: none` on `#mascot-wrapper` container and `pointer-events: auto` on `.mascot-body` so underlying post interactions remain clickable. | M3 | Survey Frontend |
| 8 | R4-A: Instant Guest Chat Notice Banner | Fix Jinja2 condition in `chat.jinja2` (`session.user.is_guest` handling) to immediately display `"❌ Гости могут только читать чат. Войдите для общения."`. | M4 | Survey Frontend |
| 9 | R4-B: Guest Form Input Disabling | Disable textarea, submit buttons, formatting controls, and file attachments in `chat.jinja2` for guest users. | M4 | Survey Frontend |
| 10 | R5-A: `FormManager.hideFloating()` Null-Check Safeguard | Add defensive box retrieval and optional chaining in `FormManager.hideFloating()` to eliminate `Uncaught TypeError: Cannot read properties of null (reading 'querySelector')`. | M5 | Survey JS Core |
| 11 | R5-B: Global Keyboard Listener Safeguards & Module Exports | Harden `Alt+Enter`, `Escape`, `KeyR` shortcuts in `main.src.js`; export `FormManager` in `module.exports` for unit testing; compile assets via `minify_assets.py`. | M5 | Survey JS Core |
| 12 | E2E-TEST: Opaque-Box Test Suite (Tiers 1-4) | Comprehensive test suite validating video previews, CDN fallbacks, mascot z-index, guest notice, and JS runtime execution without errors. | E2E-TEST | Survey JS Core |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Video Previews & Media Proxy Restoration | R1-A, R1-B, R1-C: Template poster fallback, `/thumb/` dynamic ffmpeg video extraction, token probing fix. | none | PLANNED |
| M2 | Tag Search & Media Fallback Optimization | R2-A, R2-B: `search_results.jinja2` `onerror` handler, `get_telegram_file` instant fallback bypass. | none | PLANNED |
| M3 | Chat Mascot Foreground Layering | R3-A, R3-B: `--z-mascot: 100` in `style.src.css`, mobile override fix, pointer-events isolation, CSS asset build. | none | PLANNED |
| M4 | Instant Guest Notice in Chat | R4-A, R4-B: `chat.jinja2` guest authentication logic, instant banner display, guest input controls disabled. | none | PLANNED |
| M5 | Frontend JavaScript TypeError Fix | R5-A, R5-B: `main.src.js` `FormManager.hideFloating()` null-checks, keyboard handler guards, module exports, asset build. | none | PLANNED |
| E2E-TEST | Opaque-Box E2E Test Suite | Test runner and 4-tier test cases covering R1-R5 requirements, publishing `TEST_READY.md`. | none | PLANNED |
| M_FINAL | Full E2E Verification & Adversarial Hardening | Verify 100% pass on Tiers 1-4 and execute Tier 5 adversarial testing. | M1, M2, M3, M4, M5, E2E-TEST | PLANNED |

## Interface Contracts
### Media Proxy & Video Previews ↔ Frontend Templates
- Route: `/thumb/{file_id}` or `/preview/{file_id}`
- Behavior for video files (`BAAC...`, `CQAC...`, `video/mp4`):
  - Returns `image/jpeg` MIME type (extracted 1st frame JPEG or registered thumbnail).
  - Never returns `video/mp4` stream for thumbnail endpoints.
- Client error fallback:
  - `<img onerror="handleImageError(this)">`
  - `<video poster="..." onerror="handleImageError(this)">`
  - When external CDN mirror fails, client requests `/files/{file_id}?skip=imgbb,pixhost,freeimage` or `/thumb/{file_id}?skip=...`.

### Mascot & Post Interaction Layering
- CSS Variables:
  - `--z-mascot: 100`
  - `--z-content: 1`
- `#mascot-wrapper`: `z-index: var(--z-mascot)`, `pointer-events: none`
- `.mascot-body`, `.mascot-bubble`: `pointer-events: auto`

### Chat Guest Authentication
- Backend Context: `session.user = {"id": str, "is_guest": bool, "is_admin": bool}`
- Unauthenticated / Guest state check: `{% if not session.user or session.user.is_guest %}`
- Banner HTML:
  ```html
  <div class="guest-chat-notice">
      <span>❌ Гости могут только читать чат. <a href="/login?redirect={{ request.url.path }}">Войдите для общения</a>.</span>
  </div>
  ```
- Form controls: `disabled`, `pointer-events: none`

### FormManager Frontend Lifecycle
- `FormManager.hideFloating(fromHistory = false)`:
  - Safe against `this === null`, `this === undefined`, `this.floatingBox === null`.
  - DOM query: `const box = this?.floatingBox || document.getElementById('floating-reply-box');`
  - QuerySelector: `box?.querySelector?.(...)`
  - No uncaught TypeErrors when invoked without an open floating box.

## Code Layout
- `site_tgach/main.py`: Media proxy endpoints (`get_telegram_file`, `get_cached_file_path`), auth dependency (`get_current_user_or_guest`), chat route (`read_board_chat`).
- `site_tgach/templates/chat.jinja2`: Chat UI template, guest notice banner, form inputs, video poster attributes.
- `site_tgach/templates/search_results.jinja2`: Tag search gallery templates, `onerror` fallback handlers.
- `site_tgach/templates/thread.jinja2`, `board.jinja2`, `overboard.jinja2`, `gallery.jinja2`: Video poster thumbnail bindings.
- `site_tgach/static/css/style.src.css`: Source stylesheet (compiled to `style.css` and `style.css.gz`).
- `site_tgach/static/js/main.src.js`: Source JavaScript (compiled to `main.js` and `main.js.gz`).
- `scratch/minify_assets.py`: Asset compilation script.
- `tests/`: Automated unit, integration, and E2E test suites.
