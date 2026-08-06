# BRIEFING — 2026-08-06T23:40:30Z

## Mission
Complete Milestone 1 Exception Hardening across economy_extension.py, admin_manager.py, handlers/message_router.py, site_tgach/main.py, and main.py in dvachbot.

## 🔒 My Identity
- Archetype: Exception Hardening Specialist
- Roles: implementer, qa, specialist
- Working directory: C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_replacement
- Original parent: 98df3431-135a-4b0d-a59e-15bcc0929358
- Milestone: M1 — Broad Exception Auditing & Telegram API Exception Hardening

## 🔒 Key Constraints
- Edit files natively using precise code editing tools.
- Catch TelegramForbiddenError (purge/deactivate blocked users), TelegramRetryAfter (asyncio.sleep backoff), and TelegramBadRequest (clean fallback/logging).
- Eliminate bare `except:` and `except: pass` blocks in target files.
- Run `python -m py_compile` on all modified files to verify.

## Task Summary
- **Target files**:
  1. `economy_extension.py` (29 bare except blocks across economy actions)
  2. `admin_manager.py` (line 856 and admin menu handlers)
  3. `handlers/message_router.py` (lines 179, 555, 866, 917)
  4. `site_tgach/main.py` (lines 1491, 1497)
  5. `main.py` (lines 3770, 3774, 3807, 3811, 3966, 4020, 8088, 8093, 8095, 10015, 10017, 10025, 11591, 11607, 12383, 12391)
- **Verification**: `python -m py_compile` across all M1 modified files.
