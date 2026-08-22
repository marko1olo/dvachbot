# Project: dvachbot Concurrency, Deadlock & Event Loop Swarm Audit

## Architecture
- **Process Model**: Asyncio event-loop core (`main.py`) with a dedicated background thread watchdog (`bot_watchdog.py`, `_RawHealthcheckServer`) and task manager (`common/task_manager.py`).
- **Database Layer**: SQLite via aiosqlite with process-wide asynchronous lock synchronization (`common.db_pool.db_lock` / `LazyLock`) and bounded timeouts.
- **Networking**: aiohttp / aiogram with non-blocking TLS configurations (`TCPConnector(ssl=False)` / `_NO_VERIFY_SSL`) to eliminate synchronous Windows CryptoAPI certificate store queries.
- **Admin & Moderation**: Global `ADMIN_IDS` and board-level admin exemptions guarding against spam filters, rate limits, shadow mutes, lockdowns, and economy combat debuffs.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Forensic Log & Watchdog Remediation | Fix `psutil.Process().open_files()` native crash, circular imports in `archive_manager.py`, and `BEGIN IMMEDIATE` contention | M1 | survey_logs_watchdog |
| 2 | Event Loop Non-Blocking Assurance | Eliminate synchronous Windows cert store lookups, offload disk/image I/O (`os.path.getsize`, Pillow) to threads | M1, M2 | survey_logs_watchdog, survey_locks_async |
| 3 | Lock Concurrency & DB Transaction Bounding | Move external network calls outside `db_lock`, fix TOCTOU in `deduct_user_global_balance`, enforce bounded DB transactions | M2 | survey_locks_async |
| 4 | SSL / TLS Non-Blocking Configuration | Ensure all `aiohttp.ClientSession` use `TCPConnector(ssl=False)` or pre-cached SSL contexts to prevent loop freezes | M2 | survey_locks_async |
| 5 | Admin & Anti-Abuse 100% Exemption | Verify and enforce 100% exemption for `ADMIN_IDS` across rate limits, spam filters, shadow mutes, cooldowns, and combat debuffs | M3 | survey_admin_stress |
| 6 | Swarm Concurrency Stress Harness | Implement `scratch/stress_test_full_swarm.py` with 50+ concurrent tasks, parallel SQLite writes, queue slicing, and media downloads | M4 | survey_admin_stress |
| 7 | Full Codebase Clean Compilation & Audit | Verify `py_compile` across all Python files and pass 100% forensic integrity audit | M5 | original_request |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Live Log & Watchdog Remediation | `main.py`, `japanese_translator.py`, `archive_manager.py`, `site_tgach/tagging_worker.py` | Survey | DONE |
| M2 | Lock & Event Loop Hardening | `main.py`, `common/database.py`, `site_tgach/main.py`, `Dubsite_tgach/main.py` | M1 | DONE |
| M3 | Admin Immunity Hardening | `handlers/message_router.py`, `common/spam_filter.py`, `main.py` | M2 | DONE |
| M4 | Swarm Stress Test Execution | `scratch/stress_test_full_swarm.py` (50+ concurrency, SQLite, queue slicing) | M3 | IN_PROGRESS |
| M5 | Forensic Audit & Acceptance Gate | Full project integrity check, `py_compile`, zero loop stalls | M4 | PLANNED |

## Code Layout
- `common/`: Core database, config, task manager, spam filter, and utility modules.
- `handlers/`: Telegram message routers, callback handlers, admin commands, and media processing.
- `site_tgach/`, `Dubsite_tgach/`: External site sync and tagging workers.
- `logs/`: Production logs, deadlock watchdog traces, crash reports, and heartbeat telemetry.
- `scratch/`: Diagnostic scripts, stress test harnesses, and temporary verification benchmarks.
