## 2026-08-06T23:28:35Z
You are Worker 1 (Exception Hardening Specialist). Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_exceptions.

MUST read C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md before starting work.

Your task: Implement Milestone 1 Exception Hardening natively across dvachbot codebase (C:\Users\danat\Desktop\dvachbot).

Refer to:
- C:\Users\danat\Desktop\dvachbot\.agents\explorer_exceptions\handoff.md
- C:\Users\danat\Desktop\dvachbot\PROJECT.md

Scope of files to edit natively:
- user_manager.py
- periodic_publisher.py
- broadcaster.py
- economy_extension.py
- admin_manager.py
- handlers/message_router.py
- site_tgach/main.py
- main.py (Telegram API exception blocks: whisper, reply_notifier_task, economy/fun commands, photo galleries, event media groups)

Key requirements for your implementation:
1. Import explicit Aiogram 3 exception classes: `from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramAPIError`.
2. Handle `TelegramForbiddenError` (HTTP 403): Call `main.purge_users_from_board_ram(board_id, [uid])` / `remove_users_from_board_batch`, or register blocked user in `self.blocked_users` / DB so blocked users are deactivated and purged from active delivery lists.
3. Handle `TelegramRetryAfter` (HTTP 429): Parse `e.retry_after` (or default 5s), `await asyncio.sleep(...)`, and retry the API call safely.
4. Handle `TelegramBadRequest` (HTTP 400): Provide clean fallbacks (e.g., plain-text degraded send if HTML parse fails; suppress deletion errors if message already deleted; log clean warning instead of dumping 10-line traceback to stderr).
5. Remove all 29 bare `except: pass` blocks in `economy_extension.py` and bare `except: pass` in `main.py` economy/fun handlers, replacing them with explicit exception handling.
6. Replace unformatted `traceback.print_exc()` with structured `logger.exception(...)` or `logger.error(..., exc_info=True)`.

Verification:
- Run `python -m py_compile` on all modified files.
- Run `pytest tests/` if applicable and verify test suite status.
