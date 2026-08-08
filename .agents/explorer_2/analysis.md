# Database & Query Performance Analysis — `dvachbot`

## Executive Summary
This report analyzes database and query performance in `dvachbot`, focusing on the runtime lag spike in `passive_slice` (processing time jumping from ~2s to ~8.9s) and tag search performance using `PostFiles`.

---

## Key Findings

### 1. Tag Search Performance Benchmark (`bench_tags.py`)
- **Old Method** (`instr(content, ?) > 0` on `Posts` table):
  - **Execution Time**: **8,119.06 ms** (~8.1 seconds).
  - **Mechanism**: Full table scan on `Posts` table (`SCAN Posts`), reading all JSON content strings across 500,000+ posts.
- **New Method** (`PostFiles` table mapping):
  ```sql
  SELECT count(DISTINCT post_num)
  FROM PostFiles 
  WHERE original_file_id IN (...) OR thumbnail_file_id IN (...)
  ```
  - **Execution Time**: **0.78 ms** (<1 ms).
  - **Query Plan**: `MULTI-INDEX OR` lookup using covering indexes:
    - `SEARCH PostFiles USING INDEX idx_postfiles_orig (original_file_id=?)`
    - `SEARCH PostFiles USING INDEX idx_postfiles_thumb (thumbnail_file_id=?)`
  - **Status**: The `PostFiles` optimization is working exceptionally well (~0.78ms vs target requirement of 30-50ms) and MUST be preserved.

---

### 2. Bottleneck & Root Cause in `passive_slice` (8.9s Lag Spike)

#### A. Architecture of `passive_slice`
`passive_slice` is the delivery phase for distributing board posts to inactive/passive recipients in slices (`passive_slice_size`).
During `passive_slice` processing in `delivery_manager.py` & `broadcaster.py`:
1. `MessageDeliveryTask._determine_delivery_phases()` splits recipients into slices.
2. `_persist_durable_delivery_item()` calls `upsert_delivery_queue_item()` in `common/database.py` BEFORE sending.
3. `send_message_to_users()` broadcasts Telegram messages in chunks.
4. `_save_copies_to_db()` calls `add_post_copies()` in `common/database.py` AFTER sending each chunk.
5. `_persist_durable_delivery_item()` is called for deferred recipients.
6. `_remove_already_delivered_recipients()` calls `get_post_copies()`.
7. `_delete_durable_delivery_item()` calls `delete_delivery_queue_item()`.

#### B. The `db_lock` Contention Bottleneck
- In `common/db_pool.py`, `db_lock` is a single global `asyncio.Lock()` (`LazyLock`) used to serialize database operations across the process.
- **Problem 1: Read Queries Under `db_lock`**:
  Read-only functions (`get_post_copies`, `get_post_by_num`, `get_pending_delivery_queue_items`, `get_user_status`, `find_post_by_file_id`) acquire `async with db_lock:`.
- **Problem 2: Unindexed Scans Holding `db_lock`**:
  Functions like `find_post_by_file_id` (line 6464 in `common/database.py`) and `apply_file_action_by_hash` (line 4248) still execute full table scans using `WHERE instr(content, ?) > 0` on `Posts`.
  When `find_post_by_file_id` or similar legacy functions run under `db_lock`, they hold the global lock for **~8.1 seconds**.
- **Problem 3: Transaction Blocking & Exponential Retry Backoff**:
  While `db_lock` is held by a slow scan or a write transaction (`BEGIN IMMEDIATE` in `upsert_delivery_queue_item`, `add_post_copies`, `delete_delivery_queue_item`), all `passive_slice` DB operations attempt `async with db_lock:`.
  When `sqlite3.OperationalError: database is locked` occurs during transaction startup, functions loop with exponential backoff (`await db_sleep(0.1 * (attempt + 1))`).
  This causes `passive_slice` processing time to stall for **8.9 seconds** (matching the ~8.1s scan duration + retry backoff delays).

---

## Detailed Evidence Matrix

| Area / Module | File & Line | Query / Mechanism | Performance / Plan |
|---|---|---|---|
| Tag Search (Old) | `bench_tags.py:27` | `SELECT count(*) FROM Posts WHERE (instr(content, ?) > 0 ...)` | **8,119.06 ms** (`SCAN Posts`) |
| Tag Search (New) | `bench_tags.py:38` | `SELECT count(DISTINCT post_num) FROM PostFiles WHERE original_file_id IN (...) OR ...` | **0.78 ms** (`SEARCH PostFiles USING INDEX idx_postfiles_orig / thumb`) |
| Queue Upsert | `common/database.py:2784` | `SELECT id FROM DeliveryQueue WHERE status = 'pending' AND board_id = ? ...` | `SEARCH DeliveryQueue USING COVERING INDEX idx_deliveryqueue_post_phase` |
| Queue Get | `common/database.py:2902` | `SELECT ... FROM DeliveryQueue WHERE status = 'pending' AND id > ? ORDER BY id LIMIT ?` | `SEARCH DeliveryQueue USING INDEX idx_deliveryqueue_pending_enqueued` |
| Legacy File Search | `common/database.py:6464` | `SELECT ... FROM Posts WHERE instr(content, ?) > 0` | `SCAN Posts` (holds `db_lock` for ~8s) |
| Post Copy Insert | `common/database.py:2662` | `INSERT OR IGNORE INTO PostCopies (post_num, recipient_id, message_id)` | Indexed on `(recipient_id, message_id)` PK, `idx_postcopies_post_num` |
| Post Copy Read | `common/database.py:2742` | `SELECT recipient_id, message_id FROM PostCopies WHERE post_num = ?` | Uses `idx_postcopies_post_num` |

---

## Schema & Index Verification

### `PostFiles` Table & Indexes
- Table structure: `id` (PK AUTOINCREMENT), `post_num`, `file_type`, `original_file_id`, `thumbnail_file_id`, `original_url`, `thumbnail_url`.
- Active Indexes:
  - `idx_postfiles_orig`: `PostFiles(original_file_id)`
  - `idx_postfiles_thumb`: `PostFiles(thumbnail_file_id)`
  - `idx_postfiles_post_num`: `PostFiles(post_num)`
  - `idx_postfiles_file_ids`: `PostFiles(original_file_id, thumbnail_file_id)`

### `DeliveryQueue` Table & Indexes
- Table structure: `id` (PK AUTOINCREMENT), `board_id`, `post_num`, `recipients`, `content`, `delivery_phase`, `original_recipients`, `thread_id`, `enqueued_at`, `updated_at`, `attempts`, `status`.
- Active Indexes:
  - `idx_deliveryqueue_post_phase`: `DeliveryQueue(post_num, board_id, delivery_phase, status)`
  - `idx_deliveryqueue_status_board`: `DeliveryQueue(status, board_id, id)`
  - `idx_deliveryqueue_pending_enqueued`: `DeliveryQueue(status, enqueued_at) WHERE status = 'pending'`

---

## Proposed Remediation Principles for Implementer

1. **Eliminate Legacy `instr(content, ?)` Table Scans**:
   Replace legacy file lookups in `common/database.py` (e.g. `find_post_by_file_id` and `apply_file_action_by_hash`) with `PostFiles` indexed queries:
   ```sql
   SELECT p.* FROM Posts p
   JOIN PostFiles pf ON p.post_num = pf.post_num
   WHERE pf.original_file_id = ? OR pf.thumbnail_file_id = ?
   ```
2. **Optimize Lock Granularity in `db_lock`**:
   - In WAL mode (`PRAGMA journal_mode=WAL`), SQLite supports concurrent read queries without blocking write transactions.
   - Pure SELECT queries (such as `get_post_copies`, `get_post_by_num`, `get_user_status`) do not need `BEGIN IMMEDIATE` or global `db_lock` if they do not modify state.
3. **Preserve `PostFiles` Optimization**:
   Keep `bench_tags.py` and `PostFiles` tag search mapping intact (0.78ms execution time).
