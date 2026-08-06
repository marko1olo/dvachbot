# 5-Component Handoff Report: Async Queue & Task Loop Integrity Audit

**Agent**: Explorer 2 (Async Queue Integrity Specialist)  
**Working Directory**: `C:\Users\danat\Desktop\dvachbot\.agents\explorer_queues`  
**Target Codebase**: `C:\Users\danat\Desktop\dvachbot`  
**Timestamp**: 2026-08-06T23:28:00Z  

---

## 1. Observation

### Obs 1: Silent Queue Item Drop on Error in `delivery_manager.py`
- **File**: `delivery_manager.py` (lines 958–987)
- **Verbatim Code**:
```python
async def message_worker(worker_name: str, board_id: str, bot_instance: Bot):
    queue = message_queues[board_id]
    while True:
        msg_data = await queue.get()
        try:
            if not msg_data:
                await asyncio.sleep(0.05)
                continue

            task = MessageDeliveryTask(worker_name, board_id, bot_instance, queue, msg_data)
            await task.process()

        except asyncio.CancelledError:
            break
        except Exception as e:
            if is_shutting_down or drain_shutdown_requested:
                break
            if "closed database" in str(e).lower():
                ...
                await asyncio.sleep(5)
                continue
            print(f"{worker_name} | ⛔ Критическая ошибка: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(1)
        finally:
            queue.task_done()
```
- **Context**: `msg_data` is popped from `queue` via `queue.get()`. If `task.process()` raises an unhandled exception before delivery (e.g. database error, missing payload fields, or unexpected runtime error during message formatting/sending), `message_worker` catches `Exception`, logs traceback, calls `queue.task_done()`, and proceeds to the next item. `msg_data` is NOT requeued nor persisted if it was not eligible for `DeliveryQueue` DB storage.

### Obs 2: Permanent Supervisor Delay Escalation in `delivery_manager.py` and `main.py`
- **File 1**: `delivery_manager.py` (lines 640–665)
```python
async def _supervise_message_worker(worker_name: str, board_id: str, bot_instance: Bot) -> None:
    delay = WORKER_RESTART_DELAY_SEC
    while not (is_shutting_down or drain_shutdown_requested):
        try:
            await message_worker(worker_name, board_id, bot_instance)
            ...
        except Exception as e:
            ...
            print(f"⛔ {worker_name} упал: ... Перезапуск через {delay:.0f} с.")
        await asyncio.sleep(delay)
        delay = min(delay * 2, WORKER_RESTART_MAX_DELAY_SEC)
```
- **File 2**: `main.py` (lines 14843–14875)
```python
async def _run_background_task(task_factory: Callable[[], Awaitable[Any]], task_name: str):
    INITIAL_RESTART_DELAY = 60
    MAX_RESTART_DELAY = 600
    current_delay = INITIAL_RESTART_DELAY
    while True:
        try:
            task_coro = task_factory()
            await task_coro
            ...
        except Exception as e:
            ...
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RESTART_DELAY)
```
- **Context**: `delay` (and `current_delay`) starts at initial value and doubles on every exception up to the max threshold. However, `delay` is **never reset back to its initial value** upon successful execution or recovery. After a transient network/DB disturbance, subsequent task crashes remain penalized with maximum delays (60s / 600s) forever.

### Obs 3: Silent Item Deletion on Error in `site_tgach/importer.py`
- **File**: `site_tgach/importer.py` (lines 1197–1210)
- **Verbatim Code**:
```python
                    except Exception as e:
                        processed_ids.append(q_id)

                if processed_ids:
                    try:
                        async with db_lock:
                            placeholders = ",".join(["?"] * len(processed_ids))
                            await conn.execute(
                                f"DELETE FROM ImportQueue WHERE id IN ({placeholders})",
                                processed_ids,
                            )
                            await conn.commit()
                    except:
                        pass
```
- **Context**: When processing items from `ImportQueue`, any unhandled exception `e` in an item causes `processed_ids.append(q_id)`. The code then executes `DELETE FROM ImportQueue WHERE id IN (...)` for all `processed_ids`, **permanently deleting failed items from DB without retry or logging**.

### Obs 4: Broken Concurrency Semaphore and Unmonitored Task Creation in `site_tgach/mirror_worker.py`
- **File**: `site_tgach/mirror_worker.py` (lines 335–356)
- **Verbatim Code**:
```python
    SEM = asyncio.Semaphore(20) 

    async def runner(task):
        async with SEM:
            await asyncio.create_task(_process_single_task(task))

    try:
        while True:
            tasks = await get_pending_mirror_tasks(limit=20, allowed_types=allowed_types)
            if not tasks:
                await asyncio.sleep(10)
                continue
            await asyncio.gather(*[runner(t) for t in tasks])
```
- **Context**: Line 339 `await asyncio.create_task(_process_single_task(task))` awaits only the *creation* of the Task, NOT its completion. As a result:
  1. The `async with SEM:` context manager exits immediately upon task scheduling, rendering `SEM = asyncio.Semaphore(20)` completely ineffective.
  2. `_process_single_task` executes as an unmonitored background task with no reference tracking or exception callback.
  3. `asyncio.gather(*[runner(t) for t in tasks])` finishes instantly without waiting for mirror tasks or reporting errors.

### Obs 5: `queue.task_done()` Skipped on Error in `site_tgach/main.py` (and `Dubsite_tgach/main.py`)
- **File**: `site_tgach/main.py` (lines 3823–3837)
- **Verbatim Code**:
```python
async def websocket_broadcaster(queue: asyncio.Queue, manager: "ConnectionManager"):
    logger.info("INFO:     WebSocket broadcaster started.")
    try:
        while True:
            try:
                post_data = await queue.get()
                await manager.broadcast_post(post_data, post_data["board_id"])
                queue.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Broadcaster error: {e}", exc_info=True)
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
```
- **Context**: `queue.task_done()` is located AFTER `await manager.broadcast_post(...)`. If `broadcast_post` raises an exception (e.g., missing `"board_id"` key or WebSocket output error), execution jumps to `except Exception:`, logging the error and sleeping 1s. `queue.task_done()` is **never called for that item**, causing `queue.join()` (if called elsewhere) to block indefinitely.

### Obs 6: Batch Deletion and Processing Inconsistency in `site_posts_broadcaster` and `site_reaction_processor`
- **File 1**: `delivery_manager.py` (lines 1547–1695, `site_posts_broadcaster`)
- **File 2**: `main.py` (lines 15151–15225, `site_reaction_processor`)
- **Context**: Both workers fetch entire batches of items from DB tables (`get_and_clear_broadcast_queue()` and `get_and_clear_reaction_queue()`), which deletes them from DB atomically. If an exception occurs mid-batch while processing item $i$, remaining items $i+1 \dots N$ in the fetched list are skipped for that iteration, and because they were already cleared from DB, those pending items are **silently lost**.

### Obs 7: Orphaned Post Records on Pipeline Errors in `post_processor.py`
- **File**: `post_processor.py` (lines 405–426, `NewPostProcessor.execute`)
- **Context**: `create_post` writes the post to the database in line 412 (`_create_post_record`). If an exception occurs in downstream steps (`_format_and_update_headers()` or `_save_to_memory()`), the outer `except Exception:` catches it and returns `None`. The post remains written in the DB, but is **never enqueued to `message_queues` nor recorded in `messages_storage`**, resulting in an orphaned DB post and lost delivery.

---

## 2. Logic Chain

1. **Premise**: In an asynchronous message queue architecture, every item retrieved via `queue.get()` or DB poll MUST either be successfully processed, retry-scheduled with backoff, or moved to a dead-letter state. Furthermore, background worker loops must be resilient against item-level errors without loop termination or permanent backoff degradation.
2. **Observation 1 (`delivery_manager.py`)**: `message_worker` pops `msg_data` from `message_queues[board_id]` using `queue.get()`. If `task.process()` fails before delivery, `message_worker` logs the error and calls `queue.task_done()`. Because `msg_data` is not requeued nor written to disk (`DeliveryQueue`), the message item is **silently lost**.
3. **Observation 2 (`delivery_manager.py` & `main.py`)**: Supervised loops (`_supervise_message_worker` and `_run_background_task`) double `delay` on failure up to max limits (60s / 600s), but do not reset `delay` back to initial values after successful long-running execution. Therefore, temporary failures cause permanent high-latency restart penalties for all future restarts.
4. **Observation 3 (`site_tgach/importer.py`)**: In `process_import_queue`, items that raise exceptions during import are appended to `processed_ids` and deleted from `ImportQueue` via `DELETE FROM ImportQueue WHERE id IN (...)`. This directly causes **silent data loss of failed import posts**.
5. **Observation 4 (`site_tgach/mirror_worker.py`)**: In `process_mirror_queue`, `await asyncio.create_task(_process_single_task(task))` inside `runner()` releases the semaphore immediately and does not await `_process_single_task`. This bypasses the concurrency semaphore (`SEM = 20`) and leaves tasks unmonitored.
6. **Observation 5 (`site_tgach/main.py`)**: In `websocket_broadcaster`, `queue.task_done()` is outside the `try` block protecting `broadcast_post`. An exception skips `task_done()`, breaking `asyncio.Queue` tracking and causing potential deadlocks on `queue.join()`.
7. **Observation 6 (`delivery_manager.py` & `main.py`)**: `site_posts_broadcaster` and `site_reaction_processor` clear DB queue tables before processing items in memory. An unhandled exception during item processing drops all remaining items in the batch.
8. **Observation 7 (`post_processor.py`)**: `NewPostProcessor.execute` persists posts to DB early in the process. Unhandled exceptions in post-processing steps abort `_enqueue_and_notify()`, leaving posts in DB while skipping delivery to subscribers.

---

## 3. Caveats

- **No Code Modifications Made**: This investigation was strictly read-only per task instructions. No source code changes were committed during this audit.
- **Durable Delivery Feature Flag**: `DURABLE_DELIVERY_QUEUE_ENABLED` in `common/config.py` provides DB persistence for passive delivery items when enabled. However, active/full phase delivery items and non-durable payloads rely solely on RAM `message_queues`.
- **Environment Assumptions**: The findings apply to standard Python `asyncio` execution under Aiogram 3 and FastAPI in `dvachbot`.

---

## 4. Conclusion & Recommended Hardening Strategies

### Hardening Strategy 1: `delivery_manager.py` (lines 958–987)
- **Fix**: Wrap `task.process()` with item-level error handling. If an item fails due to a transient network/DB error, re-enqueue `msg_data` into `queue` up to a maximum retry limit (e.g. 3 retries) with exponential backoff before calling `queue.task_done()`.

### Hardening Strategy 2: Supervisor Delay Reset in `delivery_manager.py` (line 649) and `main.py` (line 14850)
- **Fix**: Reset `delay = WORKER_RESTART_DELAY_SEC` (or `current_delay = INITIAL_RESTART_DELAY`) whenever a worker task runs successfully for more than a threshold period (e.g. 120 seconds) or processes an item without error.

### Hardening Strategy 3: `site_tgach/importer.py` (lines 1197–1210)
- **Fix**: Remove `processed_ids.append(q_id)` from the `except Exception:` block. Update failed items with an `error_count` and retry timestamp instead of deleting them, or log explicit CRITICAL errors and move them to an `ImportQueue_DLQ` table after 5 failed attempts.

### Hardening Strategy 4: `site_tgach/mirror_worker.py` (lines 337–339)
- **Fix**: Change `await asyncio.create_task(_process_single_task(task))` to `await _process_single_task(task)` inside `async with SEM:` so the semaphore properly limits concurrent mirror tasks to 20, and `asyncio.gather` properly awaits all tasks.

### Hardening Strategy 5: `site_tgach/main.py` (lines 3823–3837) & `Dubsite_tgach/main.py`
- **Fix**: Wrap `manager.broadcast_post(...)` in a `try ... finally: queue.task_done()` block so `queue.task_done()` is ALWAYS executed regardless of whether processing succeeded or failed.

### Hardening Strategy 6: `delivery_manager.py` (lines 1547–1695) & `main.py` (lines 15151–15225)
- **Fix**: Wrap individual item processing inside batch loops in an inner `try/except Exception:` block so an error processing post $i$ does not skip processing for posts $i+1 \dots N$.

### Hardening Strategy 7: `post_processor.py` (lines 405–426)
- **Fix**: Ensure `_enqueue_and_notify()` and `_save_to_memory()` are resiliently executed in a guarded block following post creation in `_create_post_record()`, preventing orphaned DB posts.

---

## 5. Verification Method

### Independent Inspection Steps:
1. **Source Inspection**: Use `view_file` to inspect the identified file paths and line numbers:
   - `delivery_manager.py`: lines 640–665, 958–987, 1442–1539, 1547–1696
   - `broadcaster.py`: lines 316–361, 484–548
   - `post_processor.py`: lines 405–426
   - `site_tgach/mirror_worker.py`: lines 335–356
   - `site_tgach/importer.py`: lines 1197–1210
   - `site_tgach/main.py`: lines 3823–3837
   - `main.py`: lines 14843–14875, 15151–15225
2. **Static Code Validation**: Run `python -m py_compile` across modified files after implementer applies hardening patches:
   ```powershell
   python -m py_compile delivery_manager.py broadcaster.py post_processor.py site_tgach/mirror_worker.py site_tgach/importer.py site_tgach/main.py main.py
   ```
3. **Async Test Verification**: Execute existing test suite using `pytest`:
   ```powershell
   pytest tests/
   ```
