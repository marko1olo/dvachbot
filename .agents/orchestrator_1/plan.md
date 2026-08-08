# Execution Plan: dvachbot Performance Regression Repair

## Objectives
1. Profile and identify the exact cause of `passive_slice` execution time spiking to 8.9s.
2. Fix the bottleneck in the runtime/DB query path without breaking `PostFiles` tag-search optimizations.
3. Verify tag search using `bench_tags.py` remains ~30-50ms.
4. Implement a benchmark/diagnostic script proving `passive_slice` runs in < 3s.
5. Verify clean bot startup and overall code integrity.

## Phase 1: Reconnaissance & Investigation (Milestone M4.1)
- Dispatch 3 Explorers in parallel:
  - `explorer_1`: Trace `passive_slice` definition, callers, loop execution in codebase (`periodic_publisher.py`, `main.py`, `delivery_manager.py`, etc.).
  - `explorer_2`: Analyze SQLite queries, schema, indexes, locking behavior, and `PostFiles` usage in `common/database.py` and `bench_tags.py`.
  - `explorer_3`: Profile execution bottlenecks, synchronous blocking I/O in async loops, and formulate fix strategies preserving `PostFiles` tag search.

## Phase 2: Implementation (Milestone M4.2)
- Dispatch `worker_1` (`teamwork_preview_worker`):
  - Apply the recommended fix strategy.
  - Ensure `PostFiles` tag-search logic is untouched and `bench_tags.py` passes.
  - Create the diagnostic/benchmark verification script.
  - Verify bot startup.

## Phase 3: Review, Stress Verification & Audit (Milestone M4.3)
- Dispatch 2 Reviewers (`teamwork_preview_reviewer`) to independently review implementation, correctness, and safety.
- Dispatch 2 Challengers (`teamwork_preview_challenger`) to stress-test `passive_slice`, `bench_tags.py`, and startup.
- Dispatch 1 Forensic Auditor (`teamwork_preview_auditor`) to verify zero cheating, zero hardcoded benchmarks, and genuine implementation.
- Gate Evaluation & Victory Report to Sentinel.
