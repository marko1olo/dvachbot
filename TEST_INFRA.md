# E2E Test Infra: dvachbot Concurrency, Deadlock & Event Loop Swarm Audit

## Test Philosophy
- Opaque-box and stress-driven validation under high concurrent load.
- Zero event loop stalls: verify event loop lag stays < 100ms under 50+ concurrent requests.
- Zero SQLite `database is locked` errors during parallel concurrent writes.
- 100% Admin immunity guarantee across all handlers and rate limiters.

## Feature Inventory & Test Coverage
| # | Feature | Requirement | Tier 1 (Unit) | Tier 2 (Boundary) | Tier 3 (Concurrency) | Tier 4 (Swarm Stress) |
|---|---------|-------------|:-------------:|:-----------------:|:--------------------:|:---------------------:|
| 1 | Log & Watchdog State | No fatal crashes (`psutil.open_files`), safe watchdog | ✓ | ✓ | ✓ | ✓ |
| 2 | Non-Blocking Event Loop | Zero blocking calls (`ssl`, `os.path.getsize`, PIL) | ✓ | ✓ | ✓ | ✓ |
| 3 | DB Lock Bounding | `db_lock` never held across network requests | ✓ | ✓ | ✓ | ✓ |
| 4 | SSL / TLS Non-Blocking | `TCPConnector(ssl=False)` / `_NO_VERIFY_SSL` | ✓ | ✓ | ✓ | ✓ |
| 5 | Admin Immunity | ADMIN_IDS 100% exempt from all filters & cooldowns | ✓ | ✓ | ✓ | ✓ |
| 6 | Swarm Stress Test | 50+ concurrent tasks, parallel writes, queue slicing | ✓ | ✓ | ✓ | ✓ |

## Test Architecture
- Test Runner: `python scratch/stress_test_full_swarm.py`
- Unit / Regression Tests: `python -m unittest` / `pytest`
- Code Syntax Validation: `python -m py_compile` across all repository files
