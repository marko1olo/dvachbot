## 2026-08-06T23:40:13Z
<USER_REQUEST>
You are Replacement Worker 1 (Exception Hardening Specialist). Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_replacement.

MUST read C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md before starting.

Prior worker worker_m1_exceptions completed items 1-3 (user_manager.py, periodic_publisher.py, broadcaster.py).
Your task: Resume and complete Milestone 1 Exception Hardening across the remaining files in dvachbot (C:\Users\danat\Desktop\dvachbot).

Refer to:
- C:\Users\danat\Desktop\dvachbot\.agents\explorer_exceptions\handoff.md
- C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_exceptions\progress.md
- C:\Users\danat\Desktop\dvachbot\PROJECT.md

Files to edit natively:
1. economy_extension.py: Replace all 29 bare `except: pass` and `except:` blocks across economy actions (/work, /shop, /rob, /pay, /gift, /buy) with explicit TelegramForbiddenError (purge/deactivate user), TelegramBadRequest, and TelegramRetryAfter handling.
2. admin_manager.py: (Line 856 and admin menu handlers) catch TelegramBadRequest (stale markup / message unmodified) and TelegramForbiddenError cleanly instead of generic except Exception as e: print(...).
3. handlers/message_router.py: (Lines 179, 555, 866, 917) catch TelegramForbiddenError, TelegramBadRequest (original message missing), and log via logger.exception(...).
4. site_tgach/main.py: (Lines 1491, 1497) catch TelegramForbiddenError (deactivate/remove admin ID) and TelegramRetryAfter (asyncio.sleep retry) in web admin notifications.
5. main.py: (Lines 3770, 3774, 3807, 3811, 3966, 4020, 8088, 8093, 8095, 10015, 10017, 10025, 11591, 11607, 12383, 12391) catch TelegramForbiddenError (call purge_users_from_board_ram), TelegramRetryAfter (sleep retry_after and retry), TelegramBadRequest (plain text fallback / clean warning), and remove bare except: pass in /roll, /shit, /curse.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Verification:
- Run `python -m py_compile` on all modified files (user_manager.py, periodic_publisher.py, broadcaster.py, economy_extension.py, admin_manager.py, handlers/message_router.py, site_tgach/main.py, main.py).

Output requirements:
- Maintain progress.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_replacement\progress.md.
- Write handoff.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_replacement\handoff.md detailing all changes made and py_compile results.
- Send a message to orchestrator with summary and handoff path.
</USER_REQUEST>
