# Project: dvachbot Codebase Audit & Repair

## Architecture
- **Framework**: Aiogram 3 (`aiogram==3.10.0`), FastAPI (`site_tgach`, `Dubsite_tgach`), `asyncio` queues, SQLite (`common/database.py`).
- **Core Services**:
  - `main.py`: Primary bot entry point, handlers, reply notifier, command routing.
  - `delivery_manager.py`: Async message queues (`message_queues`), worker loops, durable queue delivery.
  - `broadcaster.py`: Mass notification sender, semaphore workers, blocked user tracking.
  - `periodic_publisher.py`: Scheduled content publisher background task.
  - `user_manager.py`: User state tracking, whispers, reports, deactivation.
  - `post_processor.py`: Telegraph page generation, post delivery notifications.
  - `economy_extension.py`: Interactive economy commands (`/work`, `/shop`, `/rob`, `/pay`, `/gift`, `/buy`).
  - `admin_manager.py`: Admin panel navigation and management.
  - `site_tgach/`: Web API, `importer.py` (ImportQueue), `mirror_worker.py` (MirrorQueue), `main.py` (websocket_broadcaster).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Telegram Exception Hardening (`periodic_publisher.py`, `broadcaster.py`, `user_manager.py`, `main.py`, `economy_extension.py`, `admin_manager.py`, `site_tgach/main.py`) | Catch `TelegramForbiddenError` (purge blocked users), `TelegramRetryAfter` (asyncio.sleep backoff), `TelegramBadRequest` (plain text fallback / clean handle), eliminate bare `except: pass` | M1 | Survey |
| 2 | Asynchronous Queue Integrity & Fault Tolerance (`delivery_manager.py`, `broadcaster.py`, `post_processor.py`, `site_tgach/importer.py`, `site_tgach/mirror_worker.py`, `site_tgach/main.py`, `Dubsite_tgach/main.py`, `main.py`) | Protect worker loops and queues from silent item drops; fix supervisor delay resets; fix mirror semaphore; ensure `task_done()` in `finally:`; protect batch loops | M2 | Survey |
| 3 | Verification & Static Analysis (`python -m py_compile`, `pytest`, Code Reviews, Challenger Stress Tests, Forensic Audit) | Verify all modified files compile cleanly, tests pass, zero suppressed errors, zero cheating | M3 | Survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Broad Exception Auditing & Telegram API Exception Hardening | `user_manager.py`, `periodic_publisher.py`, `broadcaster.py`, `economy_extension.py`, `admin_manager.py`, `handlers/message_router.py`, `site_tgach/main.py`, `main.py` | None | DONE |
| M2 | Asynchronous Queue Integrity & Loop Resilience | `delivery_manager.py`, `broadcaster.py`, `post_processor.py`, `site_tgach/importer.py`, `site_tgach/mirror_worker.py`, `site_tgach/main.py`, `Dubsite_tgach/main.py`, `main.py` | M1 | DONE |
| M3 | Comprehensive Verification & Forensic Audit Gate | Entire codebase | M1, M2 | DONE |

## Code Layout
- Root modules: `main.py`, `broadcaster.py`, `delivery_manager.py`, `periodic_publisher.py`, `user_manager.py`, `post_processor.py`, `admin_manager.py`, `economy_extension.py`
- Handlers: `handlers/message_router.py`
- Common: `common/database.py`, `common/config.py`, `common/board_config.py`
- Web app: `site_tgach/main.py`, `site_tgach/importer.py`, `site_tgach/mirror_worker.py`, `Dubsite_tgach/main.py`
