# Handoff Report: `passive_slice` Performance Investigation

## 1. Observation

- **`passive_slice` Location & Triggering**:
  - `delivery_manager.py:242`: `def _passive_slice_size_for_content(content: dict, board_id: str | None = None) -> int:` returns slice limits (60 for text, 25 for media).
  - `delivery_manager.py:946–953`: When `delivery_phase == "passive"` and `len(active_recipients) > self.passive_slice_size`, `delivery_phase_for_send` is set to `"passive_slice"` and `deferred_reason = "passive_slice"`.
  - `broadcaster.py:186`: Phase budget check for `"passive_slice"`.
  - `broadcaster.py:606`: Formatted output `⏱ {time_taken:.1f}s` logged during message broadcast.
  
- **Database Schema Inspection (`dvach_bot.db`)**:
  - `inspect_db.py` output on `PostFiles`:
    - `('index', 'idx_postfiles_file_ids', 'CREATE INDEX idx_postfiles_file_ids ON PostFiles (original_file_id, thumbnail_file_id)')`
    - `('index', 'idx_postfiles_post_num', 'CREATE INDEX idx_postfiles_post_num ON PostFiles (post_num)')`
  - Missing standalone index on `thumbnail_file_id` for `OR` query matching.

- **Query Execution & Benchmarks**:
  - `common/database.py:7816` (`get_posts_by_file_ids`):
    ```sql
    SELECT post_num FROM PostFiles 
    WHERE original_file_id IN ({placeholders}) 
       OR thumbnail_file_id IN ({placeholders})
    ```
  - `bench_tags.py` benchmark execution output:
    - `Old method returned 56 posts in 11549.75ms`
    - `New method returned 56 posts in 1.82ms`

- **Database Lock & Backoff Mechanics**:
  - `common/database.py:2656–2675` (`add_post_copies`): Wrapped in `async with db_lock:`. On `sqlite3.OperationalError: database is locked`, retries up to 10 times with `await db_sleep(0.1 * (attempt + 1))`.
  - `common/db_pool.py:132` (`db_sleep`): Releases `db_lock`, sleeps, and re-acquires `db_lock`.

---

## 2. Logic Chain

1. `message_worker` (`delivery_manager.py:957`) processes pending post broadcasts by calling `MessageDeliveryTask.process()` (`delivery_manager.py:700`).
2. When the recipient list exceeds `passive_slice_size` (25 for media, 60 for text), `_determine_delivery_phases()` (`delivery_manager.py:946`) assigns phase `"passive_slice"` to the first batch.
3. During `task.process()`, multiple database calls occur under global `async with db_lock`:
   - `_persist_durable_delivery_item()` (`DeliveryQueue`)
   - `get_post_by_num()` and `get_post_copies()` (`Posts` and `PostCopies`)
   - `add_post_copies()` (`PostCopies`)
   - `_remove_blocked_users()` (`Users`)
4. In `add_post_copies()` (`common/database.py:2645`), bulk inserts are executed inside `BEGIN IMMEDIATE; ... COMMIT;` under `db_lock`.
5. When concurrent queries (e.g. tag lookups or file queries) search `thumbnail_file_id` without an index on `PostFiles(thumbnail_file_id)`, SQLite experiences table scans and holds DB locks.
6. When `add_post_copies()` or `_persist_durable_delivery_item()` encounters a locked database, it enters the 10-attempt retry loop calling `db_sleep(0.1 * (attempt + 1))` (sleeping 0.1s, 0.2s, 0.3s, 0.4s... totaling up to 5.5s of cumulative backoff delay).
7. Adding several seconds of lock contention backoff to the ~2s Telegram delivery time causes the overall `passive_slice` execution time to spike from ~2s to ~8.9s.

---

## 3. Caveats

- **No Code Modifications Made**: This investigation was strictly read-only per role instructions. No files in `C:\Users\danat\Desktop\dvachbot` outside `.agents/explorer_1/` were modified.
- **Network Variance**: Actual Telegram API latency depends on network conditions and Telegram server response times; the database lock backoff is additive to Telegram API latency.

---

## 4. Conclusion

The lag spike in `passive_slice` (from ~2s to ~8.9s) is caused by **SQLite database lock contention** during `passive_slice` database persistence steps (`add_post_copies` and `_persist_durable_delivery_item`). The root cause of the lock contention is an **unindexed column `thumbnail_file_id` in `PostFiles`**, which leads to table scans on `PostFiles` during `OR` queries in `get_posts_by_file_ids` and tag searches.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify `PostFiles` Index Deficiency**:
   Run: `python -c "import sqlite3; c = sqlite3.connect('dvach_bot.db').cursor(); print(c.execute(\"PRAGMA index_list('PostFiles')\").fetchall())"`
   Observe that there is no standalone index on `thumbnail_file_id`.

2. **Verify Tag Search Benchmark**:
   Run: `python bench_tags.py`
   Confirm that the `PostFiles` method completes in under 5ms (1.82ms measured) while maintaining correct tag mapping.

3. **Verify Lock Backoff Code**:
   Inspect `common/database.py` lines 2656–2675 (`add_post_copies`) and `common/db_pool.py:132` (`db_sleep`) to verify the exponential retry loop under `db_lock`.
