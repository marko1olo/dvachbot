# Comprehensive Analysis of `passive_slice` & Runtime Lag Spike

## Executive Summary
The Python-based `dvachbot` main message loop experienced an execution time spike during `passive_slice` processing from ~2s to ~8.9s. Investigation of `delivery_manager.py`, `broadcaster.py`, `common/database.py`, and database schemas revealed that while the `PostFiles` table tag-search optimization itself is fast (1.82ms vs 11,549ms on old `instr` search), `PostFiles` was missing an index on `thumbnail_file_id`. Unindexed queries against `thumbnail_file_id` lock SQLite (`dvach_bot.db`). Under global `db_lock`, SQLite lock contention causes database operations inside `passive_slice` (specifically `add_post_copies` and `_persist_durable_delivery_item`) to hit `OperationalError: database is locked` and enter exponential backoff retry loops (`db_sleep`), adding multiple seconds of lock delay to the ~2s Telegram delivery time.

---

## 1. Codebase Location & Function Tracing

### 1.1 Core Definitions & Parameters
- **`passive_slice` Phase Definition**:
  - Located in `delivery_manager.py` (lines 946–953) and `broadcaster.py` (line 186).
  - Slice size calculation function: `_passive_slice_size_for_content` (`delivery_manager.py:242–260`).
  - Slice sizes:
    - Text messages: `PRIORITY_PASSIVE_SLICE_SIZE` = 60 (`main.py:1383`)
    - Media messages: `PRIORITY_PASSIVE_MEDIA_SLICE_SIZE` = 25 (`main.py:1384`)

### 1.2 Call Graph and Loop Integration
1. **Background Event Loop Worker**:
   - `message_worker` (`delivery_manager.py:957`) loops infinitely, popping items from `message_queues[board_id]`.
2. **Task Instantiation**:
   - For each queue item, `message_worker` instantiates `MessageDeliveryTask` (`delivery_manager.py:700`) and calls `await task.process()`.
3. **Phase Resolution**:
   - `task.process()` calls `_determine_delivery_phases()` (`delivery_manager.py:924`).
   - If `delivery_phase == "passive"` and `len(active_recipients) > self.passive_slice_size`, the batch is sliced into `recipients_to_send` (first 25/60 recipients) and `passive_recipients_for_later` (deferred). `delivery_phase_for_send` is set to `"passive_slice"`.
4. **Durable Storage Persistence**:
   - `_persist_durable_delivery_item()` (`delivery_manager.py:782`) persists deferred recipients to SQLite table `DeliveryQueue` under `async with db_lock:`.
5. **Message Broadcasting**:
   - Calls `send_message_to_users()` (`broadcaster.py:1300`), creating `MessageBroadcaster(config)` and invoking `broadcast()` (`broadcaster.py:316`).
   - `MessageBroadcaster.broadcast()` executes:
     a) `_prepare_content_and_mentions()` (`broadcaster.py:363`): Formats content; if mention/reply data is missing from RAM cache (`messages_storage`), queries `Posts` (`get_post_by_num`) and `PostCopies` (`get_post_copies`) via `async with db_lock:`.
     b) `_process_delivery_queue()` (`broadcaster.py:452`): Sends network API calls (`bot.send_message`/`bot.send_photo`) to Telegram recipients in chunks (`CHUNK_SIZE`).
     c) `_log_delivery_metrics()` (`broadcaster.py:572`): Logs metrics line `⏱ {time_taken:.1f}s` and checks against `DELIVERY_SLOW_PHASE_SEC`.
     d) `_save_copies_to_db()` (`broadcaster.py:652`): Calls `add_post_copies()` (`common/database.py:2645`), executing bulk `INSERT INTO PostCopies` under `async with db_lock:`.
     e) `_remove_blocked_users()` (`broadcaster.py:698`): Purges blocked users from RAM/DB.
6. **Re-enqueueing Deferred Slice**:
   - `task.process()` re-enqueues `passive_recipients_for_later` back to `DeliveryQueue` via `_persist_durable_delivery_item()` and `queue.put(passive_item)`.

---

## 2. Execution Operations Breakdown

During `passive_slice` execution, the following operations occur:

| Category | Operation | Code Location | Mechanism |
|---|---|---|---|
| Network I/O | Async Telegram API calls | `broadcaster.py:755,879` | `bot.send_message`, `bot.send_photo` |
| DB Query | Post & copy resolution | `broadcaster.py:391,402` | `get_post_by_num`, `get_post_copies` (`PostCopies`) |
| DB Write | Durable delivery state | `delivery_manager.py:782,849` | `INSERT/UPDATE DeliveryQueue` via `db_lock` |
| DB Write | Save message copies | `broadcaster.py:690` | `add_post_copies()` (`INSERT INTO PostCopies`) via `db_lock` |
| DB Write | Remove blocked users | `broadcaster.py:700` | `remove_user_from_board()` via `db_lock` |

---

## 3. Root Cause Analysis of Lag Spike (~2s -> ~8.9s)

### 3.1 Primary Bottleneck: Missing Single-Column Index on `PostFiles(thumbnail_file_id)`
- **Observation**: Schema inspection of `PostFiles` (`inspect_db.py`) showed:
  - `CREATE INDEX idx_postfiles_file_ids ON PostFiles (original_file_id, thumbnail_file_id)`
  - `CREATE INDEX idx_postfiles_post_num ON PostFiles (post_num)`
- **Mechanism Failure**: `get_posts_by_file_ids` (`common/database.py:7816`) uses:
  ```sql
  SELECT post_num FROM PostFiles 
  WHERE original_file_id IN (...) 
     OR thumbnail_file_id IN (...)
  ```
  SQLite multi-column index `(original_file_id, thumbnail_file_id)` can optimize lookups for `original_file_id`, but CANNOT optimize `thumbnail_file_id IN (...)` in an `OR` query.
- **Impact**: Any query matching `thumbnail_file_id` triggers a full table scan on `PostFiles`.

### 3.2 Secondary Bottleneck: Global `db_lock` Contention & Retry Backoff Cascade
- **Observation**: `common/database.py:2656` (`add_post_copies`) and all DB operations acquire `async with db_lock:`.
- **Mechanism Failure**:
  - When background tasks (web tag search, daily cleanup, or tag workers) execute full table scans or long operations under `db_lock`, SQLite transitions to `busy/locked`.
  - When `MessageDeliveryTask` during `passive_slice` attempts `add_post_copies()` or `_persist_durable_delivery_item()`, SQLite returns `sqlite3.OperationalError: database is locked`.
  - The retry loop in `add_post_copies()` (lines 2669–2675) calls `db_sleep(0.1 * (attempt + 1))`:
    - Attempt 1: sleep 0.1s
    - Attempt 2: sleep 0.2s
    - Attempt 3: sleep 0.3s
    - Attempt 4: sleep 0.4s ... up to attempt 10.
- **Impact**: Database lock contention adds cumulative backoff delays (several seconds) on top of the ~2s Telegram network send time, pushing `passive_slice` processing time to 8.9s.

### 3.3 Verification of `PostFiles` Benchmark (`bench_tags.py`)
- Executed `bench_tags.py`:
  - **Old Method** (`instr(content, ?) > 0` full table scan on `Posts`): **11,549.75 ms** (~11.5s).
  - **New Method** (`PostFiles` table lookup): **1.82 ms**.
- **Conclusion**: The `PostFiles` table optimization itself is extremely fast (1.82ms), but requires proper individual indexes on `original_file_id` and `thumbnail_file_id` to prevent DB lock contention across concurrent async tasks.

---

## 4. Key Evidence Summary

1. `delivery_manager.py:242, 946–953`: Definition and triggering of `passive_slice`.
2. `broadcaster.py:316, 572, 606, 652`: Metric logging `⏱ {time_taken:.1f}s` and post-broadcast DB copy saving.
3. `common/database.py:2645, 2674, 7816`: `add_post_copies`, `db_sleep` retry backoff, and `get_posts_by_file_ids` query.
4. `bench_tags.py`: Benchmark proof of 11.5s vs 1.82ms for tag search using `PostFiles`.
5. Database Schema (`dvach_bot.db`): Missing `idx_postfiles_thumb ON PostFiles(thumbnail_file_id)`.
