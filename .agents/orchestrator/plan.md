# dvachbot Enhancement Master Plan

## Overview
Comprehensive audit and architectural enhancement of the dvachbot Telegram/web board ecosystem focusing on system safety, high-performance database & memory hygiene, advanced voice & multi-modal AI features, and end-to-end empirical verification.

## Milestones

### Phase 0: Survey & Codebase Mapping (COMPLETED)
- [x] Dispatch 3 parallel Explorers to scan codebase against R1, R2, R3.
- [x] Aggregate findings into Feature Inventory & Code Layout in `PROJECT.md`.

### Phase 1: Milestone 1 — Deep System Audit & Error Resilience (IN PROGRESS)
- [ ] Implement F1.1: Replace bare `except:` blocks with `except Exception:` so `asyncio.CancelledError` is re-raised.
- [ ] Implement F1.2: Replace silent `except Exception: pass` swallows with structured `logger.warning`/`logger.error` in `common/database.py`, `main.py`, `user_manager.py`, `admin_manager.py`, `handlers/message_router.py`.
- [ ] Implement F1.3: Audit & enforce 100% `spawn_task` usage across background coroutines.
- [ ] Implement F1.4: Replace raw `print()` / `traceback.print_exc()` with `runtime_logger` in `main.py`.
- [ ] Gate verification (Reviewers, Challenger, Auditor).

### Phase 2: Milestone 2 — High-Performance Database & Memory Hygiene
- [ ] Implement F2.1: Remove `asyncio.sleep(...)` inside `async with db_lock:` blocks.
- [ ] Implement F2.2: Fix explicit `BEGIN IMMEDIATE` calls inside active `aiosqlite` transactions.
- [ ] Implement F2.3: Enforce hard upper bounds (`maxsize` / LRU / bounded dict) on `_VIDEO_CACHE`, `_IMAGE_CACHE`, `_THREAD_CACHE`.
- [ ] Implement F2.4: Enforce inline upper bounds on `messages_storage`, `post_to_messages`, `message_to_post` maps.
- [ ] Implement F2.5: Enforce `maxlen` on `POST_RATE_LIMITER` deques in `site_tgach/main.py` & `Dubsite_tgach/main.py`.
- [ ] Gate verification (Reviewers, Challenger, Auditor).

### Phase 3: Milestone 3 — Advanced Voice & Multi-Modal AI Features
- [ ] Implement F3.1: Fix `_execute_groq_post` call signature bug in `ai_manager.py:206`.
- [ ] Implement F3.2: Add size/duration pre-checks, key rotation pool (`groq_pool`), and retry handling for Voice/Video note STT.
- [ ] Implement F3.3: Localize voice note prompts and mock fallbacks for `ru`, `en`, `jp` streams.
- [ ] Gate verification (Reviewers, Challenger, Auditor).

### Phase 4: Milestone 4 — Comprehensive Automated & Empirical Verification
- [ ] Implement F4.1: Automated test suite covering `spawn_task` supervision, non-blocking `db_lock`, bounded memory, STT & AI roast error handling.
- [ ] Victory Audit verification & handoff.
