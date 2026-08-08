## 2026-08-08T18:40:42Z

You are the Project Orchestrator for the dvachbot performance regression task.
Working directory: C:\Users\danat\Desktop\dvachbot
Your agent folder: C:\Users\danat\Desktop\dvachbot\.agents\orchestrator_1
User request record: C:\Users\danat\Desktop\dvachbot\ORIGINAL_REQUEST.md

Task Goal:
1. Identify and fix the bottleneck in dvachbot's main loop causing `passive_slice` execution time to spike from ~2s to ~9s (⏱ 8.9s).
2. Ensure recent tag-search optimizations using the `PostFiles` table remain intact (do not revert `PostFiles` mapping or break `bench_tags.py`).
3. Write a benchmark or diagnostic verification script that proves `passive_slice` execution time is back under 3 seconds and tag search is ~30-50ms.
4. Ensure bot starts up correctly without crashes or errors.

Orchestration rules:
- Create plan.md, progress.md, and handoff.md in your agent folder (`C:\Users\danat\Desktop\dvachbot\.agents\orchestrator_1`).
- Spawn specialized subagents (explorers, implementers, reviewers) to investigate, fix, and verify.
- Keep progress.md updated continuously.
- When all acceptance criteria are met, report victory / completion to Sentinel so Sentinel can trigger the Victory Audit.
