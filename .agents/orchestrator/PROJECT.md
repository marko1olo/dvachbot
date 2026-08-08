# Project: dvachbot Verification & Audit

## Architecture
- Python Telegram bot & web service (`site_tgach/main.py`, `user_manager.py`, `main.py`, `common/database.py`, `common/db_pool.py`).
- Component 1: `site_tgach/main.py` — Web interface for Telegram file proxy (/files/ endpoint returning 307 Redirects to api.telegram.org).
- Component 2: `user_manager.py` & `main.py` — Command handlers (e.g. `cmd_anime`) using `format_header` helper for formatted output.
- Component 3: `common/database.py` & `common/db_pool.py` — Async database pool & locking mechanism (`db_sleep` releasing `db_lock` during retries).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Telegram File Proxy 307 Redirects | `/files/` endpoint returns HTTP 307 redirect directly to `api.telegram.org` without server streaming | M1 | R1 |
| 2 | `format_header` Definition & Imports | `format_header` imported/defined across `user_manager.py` and `main.py` to prevent `NameError` | M2 | R2 |
| 3 | `db_sleep` Database Concurrency Patch | `await asyncio.sleep` replaced by `await db_sleep` releasing/reacquiring `db_lock` in `database.py` | M3 | R3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Telegram File Proxy 307 Verification | Audit `site_tgach/main.py` /files/ endpoint redirect logic | None | PLANNED |
| M2 | `format_header` Import Verification | Audit `user_manager.py` & `main.py` for `format_header` usage & imports | None | PLANNED |
| M3 | Database `db_sleep` Lock Verification | Audit `common/database.py` & `common/db_pool.py` for `db_sleep` lock behavior | None | PLANNED |

## Interface Contracts
### `site_tgach/main.py`
- Route `/files/...` -> HTTP 307 Redirect (`Location: https://api.telegram.org/file/bot<token>/<file_path>`)

### `user_manager.py` / `main.py`
- `format_header(title: str, ...) -> str`: Must be imported or defined in `user_manager.py` and `main.py` wherever used.

### `common/database.py` / `common/db_pool.py`
- `db_sleep(seconds: float)`: Releases `db_lock` if held, sleeps for `seconds`, reacquires `db_lock`.
- `common/database.py`: All lock-wait retry loops must call `await db_sleep(...)` instead of direct `await asyncio.sleep(...)`.
