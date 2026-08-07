# Project: dvachbot Ecosystem Audit & Enhancement

## Architecture
- Telegram Bot / Web Board ecosystem built with Python asyncio
- Database: SQLite with custom locking (`db_lock`) and `aiosqlite` connection pool
- Memory Management: In-memory media caches (`_VIDEO_CACHE`, `_IMAGE_CACHE`, `_THREAD_CACHE`), post lookup maps (`messages_storage`), rate limit deques, and event loop task supervision (`spawn_task`)
- Multi-Modal AI: Groq Whisper STT (voice & video notes), dynamic 2ch-style AI roasting, multi-lingual stream fallback (`ru`, `en`, `jp`), Groq key rotation pool (`groq_pool`)

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | F1.1 Coroutine Cancellation Safety | Replace bare `except:` blocks in `common/database.py` & `site_tgach/` so `asyncio.CancelledError` is re-raised | M1 | survey_1 |
| 2 | F1.2 Silent Exception Logging | Replace `except Exception: pass` swallows in `common/database.py`, `main.py`, `user_manager.py`, `admin_manager.py`, `handlers/message_router.py` with structured logging | M1 | survey_1 |
| 3 | F1.3 Task Supervision Enforcement | Audit and enforce 100% `spawn_task` supervision across all background coroutines | M1 | survey_1 |
| 4 | F1.4 Structured Logging | Replace `print()` & `traceback.print_exc()` with `runtime_logger` in `main.py` | M1 | survey_1 |
| 5 | F2.1 DB Lock Scoping | Remove `asyncio.sleep` from inside `async with db_lock:` blocks across `common/database.py` & `common/db_pool.py` | M2 | survey_2 |
| 6 | F2.2 Transaction Conflict Fix | Fix explicit `BEGIN IMMEDIATE` calls inside active `aiosqlite` transactions | M2 | survey_2 |
| 7 | F2.3 Bounded Media Caches | Add hard upper bounds / LRU eviction to `_VIDEO_CACHE`, `_IMAGE_CACHE`, `_THREAD_CACHE` | M2 | survey_2 |
| 8 | F2.4 Post Storage Inline Trimming | Add inline length limits to `messages_storage`, `post_to_messages`, `message_to_post` maps | M2 | survey_2 |
| 9 | F2.5 Bounded Rate Limit Deques | Add `maxlen` to `POST_RATE_LIMITER` deques in `site_tgach/main.py` & `Dubsite_tgach/main.py` | M2 | survey_2 |
| 10 | F3.1 AI Roast Function Signature Fix | Fix `_execute_groq_post` call signature bug in `ai_manager.py:206` | M3 | survey_3 |
| 11 | F3.2 STT Pre-checks & Key Pool | Add file size/duration pre-checks, key rotation pool (`groq_pool`), and retry handling for Voice/Video note STT | M3 | survey_3 |
| 12 | F3.3 Multi-Lingual Roast & STT | Support localized prompts and fallback for `ru`, `en`, `jp` streams in voice note pipeline | M3 | survey_3 |
| 13 | F4.1 Empirical & Automated Tests | Comprehensive automated unit, integration, and stress tests for M1, M2, M3 criteria | M4 | survey |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 0 | Survey | Codebase mapping across safety, DB, voice domains | none | DONE |
| 1 | System Safety | Error logging, exception handling, task supervision (F1.1 - F1.4) | M0 | IN_PROGRESS |
| 2 | DB & Memory | SQLite locking, transaction scoping, bounded caches (F2.1 - F2.5) | M1 | PLANNED |
| 3 | Voice & AI | Whisper STT, AI roasting fix, multi-lingual fallback (F3.1 - F3.3) | M2 | PLANNED |
| 4 | E2E Verification | Automated test suite, stress verification, Victory Audit proof (F4.1) | M3 | PLANNED |

## Interface Contracts
- Task Spawner: `spawn_task(coro, name: str = None) -> asyncio.Task` in `common/task_manager.py`
- Database Lock: `async with db_lock:` in `common/database.py` — MUST NOT contain `await asyncio.sleep(...)` or external async network calls.
- Groq AI Helper: `_execute_groq_post` in `site_tgach/neuro_poster.py` signature: `async def _execute_groq_post(client, url: str, headers: dict, json_data: dict)`
- Voice Note STT & Roast: `async def transcribe_and_roast_voice_note(bot, message: Message, board_id: str = 'b', stream: str = 'ru')` in `ai_manager.py`

## Code Layout
- `common/database.py`: Core SQLite queries, transaction scoping, and media caches
- `common/db_pool.py`: Database connection pool & lock primitives
- `common/task_manager.py`: `spawn_task` implementation & task registry
- `ai_manager.py`: Voice/Video note STT (`whisper-large-v3-turbo`) & AI roasting pipeline
- `site_tgach/neuro_poster.py`: Groq API post helpers & key pool interaction
- `site_tgach/main.py`: Rate limiters & message processing
- `main.py`: Telegram bot entry point, cleanup cron, message mapping storage
- `user_manager.py` & `admin_manager.py`: Telegram bot command & permission handlers
- `handlers/message_router.py`: Message router & voice note handler dispatch
