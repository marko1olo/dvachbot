# Scope: Performance Regression Repair (`passive_slice`)

## Architecture
- Codebase: `dvachbot` (Aiogram 3, SQLite `common/database.py`, main loop / background worker tasks)
- Key target areas: `passive_slice` function/query execution path, SQLite locks/indexes, `PostFiles` table usage in tag search, `bench_tags.py`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `passive_slice` Root Cause Analysis | Investigate main loop execution, DB queries, unindexed table scans, sync I/O, or DB locking | M4.1 | ORIGINAL_REQUEST |
| 2 | Performance Fix Implementation | Resolve `passive_slice` bottleneck (<3s execution) without reverting `PostFiles` tag-search optimizations | M4.2 | ORIGINAL_REQUEST |
| 3 | Benchmark Verification Script | Create diagnostic/benchmark script proving `passive_slice` <3s and tag search ~30-50ms | M4.3 | ORIGINAL_REQUEST |
| 4 | Bot Startup & Integrity Verification | Verify clean bot startup, review correctness, stress test, and audit integrity | M4.3 | ORIGINAL_REQUEST |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M4.1 | Root Cause Analysis & Investigation | Main loop, `passive_slice`, `common/database.py`, `PostFiles` queries, `bench_tags.py` | None | DONE |
| M4.2 | Bottleneck Resolution & Optimization | Fix `passive_slice` bottleneck while keeping `PostFiles` tag search intact | M4.1 | DONE |
| M4.3 | Verification, Benchmark & Audit Gate | Run benchmark script, verify startup, code review, challenger stress testing, forensic audit | M4.2 | DONE |

## Interface Contracts
- `passive_slice()` execution time: < 3.0 seconds (reduced from ~8.9s spike)
- Tag search performance: ~30-50ms via `PostFiles` table (verifiable via `bench_tags.py`)
- Bot startup: error-free initialization without syntax or logic crashes
