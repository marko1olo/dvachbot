## 2026-08-06T23:45:00Z

<USER_REQUEST>
You are Worker 2 (Async Queue & Task Loop Integrity Specialist). Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_m2_queues.

MUST read C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md before starting.

Your task: Implement Milestone 2 Asynchronous Queue Integrity & Loop Resilience natively across dvachbot codebase (C:\Users\danat\Desktop\dvachbot).

Refer to:
- C:\Users\danat\Desktop\dvachbot\.agents\explorer_queues\handoff.md
- C:\Users\danat\Desktop\dvachbot\PROJECT.md

Scope of files to edit natively:
- delivery_manager.py
- post_processor.py
- site_tgach/importer.py
- site_tgach/mirror_worker.py
- site_tgach/main.py
- Dubsite_tgach/main.py
- main.py (`_run_background_task`, `site_reaction_processor`)

Key hardening requirements to implement:
1. In `delivery_manager.py` (`message_worker` lines 958-987): wrap `task.process()` with item-level error handling. If an item fails due to a transient error, retry it (up to max retry limit with exponential backoff) or preserve it in durable storage before calling `queue.task_done()`, preventing silent item drops.
2. In `delivery_manager.py` (`_supervise_message_worker` line 649) and `main.py` (`_run_background_task` line 14850): reset `delay` back to initial value (`WORKER_RESTART_DELAY_SEC` / `INITIAL_RESTART_DELAY`) whenever a worker task runs successfully for more than a threshold period (e.g. 120 seconds) or processes an item without error, preventing permanent 600s restart penalties.
3. In `site_tgach/importer.py` (lines 1197-1210): remove `processed_ids.append(q_id)` from the `except Exception:` block so failed import items are NOT deleted from `ImportQueue` without retry or logging; update retry timestamp/error count or log CRITICAL error to DLQ.
4. In `site_tgach/mirror_worker.py` (lines 335-356): change `await asyncio.create_task(_process_single_task(task))` to `await _process_single_task(task)` inside `async with SEM:` so the semaphore properly limits concurrent mirror tasks to 20, and `asyncio.gather` properly awaits all tasks.
5. In `site_tgach/main.py` (lines 3823-3837) & `Dubsite_tgach/main.py`: wrap `manager.broadcast_post(...)` in a `try ... finally: queue.task_done()` block so `queue.task_done()` is ALWAYS executed regardless of whether processing succeeded or failed, preventing `queue.join()` deadlocks.
6. In `delivery_manager.py` (lines 1547-1695 `site_posts_broadcaster`) & `main.py` (lines 15151-15225 `site_reaction_processor`): wrap individual item processing inside batch loops in an inner `try/except Exception:` block so an error processing item i does not drop processing for items i+1 ... N.
7. In `post_processor.py` (lines 405-426 `NewPostProcessor.execute`): ensure post notification and memory caching are resiliently executed in a guarded block following post creation, preventing orphaned DB posts.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Verification:
- Run `python -m py_compile` across all modified files (`delivery_manager.py`, `post_processor.py`, `site_tgach/importer.py`, `site_tgach/mirror_worker.py`, `site_tgach/main.py`, `Dubsite_tgach/main.py`, `main.py`).

Output requirements:
- Maintain progress.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_m2_queues\progress.md.
- Write handoff.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_m2_queues\handoff.md detailing all code changes made, py_compile output, and test verification.
- Send a message to orchestrator with summary and handoff path.
</USER_REQUEST>
