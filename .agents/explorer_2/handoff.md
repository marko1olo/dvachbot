# Handoff Report — `explorer_2` (Database & Query Performance Investigator)

## 1. Observation
- **`bench_tags.py` Benchmark Execution Results**:
  - **Old Method** (`instr(content, ?) > 0` on `Posts` table): **8,119.06 ms** (~8.1 seconds).
  - **New Method** (`PostFiles` indexed query): **0.78 ms** (< 1 ms).
- **Tag Search Query & Index Evidence**:
  - `PostFiles` indexes verified in `dvach_bot.db`: `idx_postfiles_orig` on `original_file_id`, `idx_postfiles_thumb` on `thumbnail_file_id`, `idx_postfiles_post_num` on `post_num`.
  - SQLite `EXPLAIN QUERY PLAN` for `PostFiles` tag query confirms:
    `MULTI-INDEX OR` search using `idx_postfiles_orig` and `idx_postfiles_thumb`.
- **`passive_slice` Database Execution Path**:
  - Module `delivery_manager.py` (lines 740-850) and `broadcaster.py` (lines 330-360, 650-700) manage `passive_slice` delivery.
  - Database operations during `passive_slice`:
    - `upsert_delivery_queue_item()` (`common/database.py:2747`) — runs `BEGIN IMMEDIATE` + `SELECT/UPDATE/INSERT` on `DeliveryQueue`.
    - `add_post_copies()` (`common/database.py:2645`) — runs `BEGIN IMMEDIATE` + `INSERT OR IGNORE INTO PostCopies`.
    - `get_post_copies()` (`common/database.py:2714`) — runs `SELECT FROM PostCopies WHERE post_num = ?`.
    - `delete_delivery_queue_item()` (`common/database.py:2860`) — runs `BEGIN IMMEDIATE` + `DELETE FROM DeliveryQueue`.
- **Global Lock & Unindexed Table Scans**:
  - All DB operations wrap execution in `async with db_lock:` (`common/db_pool.py:70`, single global `asyncio.Lock()`).
  - Legacy functions in `common/database.py` (e.g. `find_post_by_file_id` at line 6464 and `apply_file_action_by_hash` at line 4248) execute `WHERE instr(content, ?) > 0` on `Posts`.
  - Executing `instr(content, ?)` on `Posts` performs a full table scan (`SCAN Posts`), taking **~8.1 seconds** while holding `db_lock`.
  - During this 8.1s window, `passive_slice` DB calls (`upsert_delivery_queue_item`, `add_post_copies`, `delete_delivery_queue_item`) block on `db_lock`, encounter SQLite busy locks, and enter exponential backoff retries (`db_sleep(0.1 * (attempt + 1))`), inflating total `passive_slice` runtime to ~8.9s.

---

## 2. Logic Chain
1. **Observation**: `bench_tags.py` proves full table scans using `instr(content, ?) > 0` on `Posts` take **8,119.06 ms**, whereas `PostFiles` indexed queries take **0.78 ms**.
2. **Observation**: Legacy functions in `common/database.py` (`find_post_by_file_id:6464`, `apply_file_action_by_hash:4248`) still execute `WHERE instr(content, ?) > 0` on `Posts`.
3. **Observation**: All DB interactions (reads and write transactions) in `common/database.py` and `delivery_manager.py` acquire the global `db_lock` (`LazyLock` in `common/db_pool.py:70`).
4. **Reasoning**: When a background task or request calls a legacy `instr(content, ?)` search, it holds `db_lock` for ~8.1 seconds while scanning `Posts`.
5. **Reasoning**: While `db_lock` is held by the 8.1s scan (or by write transactions competing for `db_lock`), any concurrent `passive_slice` execution task in `delivery_manager.py` attempting `upsert_delivery_queue_item` or `add_post_copies` is blocked.
6. **Reasoning**: Blocked tasks encounter `sqlite3.OperationalError: database is locked` and trigger retry delays (`await db_sleep(...)`), causing the main loop processing time for `passive_slice` to spike from ~2s to **8.9s**.
7. **Conclusion**: The lag spike is caused by global `db_lock` contention aggravated by remaining unindexed `instr(content, ?)` table scans on `Posts` blocking `passive_slice` database transactions. Replacing remaining `instr()` calls with `PostFiles` index lookups and releasing `db_lock` on read-only queries will restore `passive_slice` runtime to <3s while preserving the 0.78ms `PostFiles` tag search.

---

## 3. Caveats
- No direct source code changes were made to `dvachbot` runtime files (read-only investigation constraint).
- Database lock behavior was analyzed statically and via single-process query plan/benchmark execution; actual multi-process contention depends on concurrent site (`Dubsite_tgach` / `site_tgach`) activity accessing `dvach_bot.db`.

---

## 4. Conclusion
- **Tag Search Optimization (`PostFiles`)**: Verified working as intended (**0.78 ms** execution time vs 30-50ms requirement). Must NOT be reverted.
- **Root Cause of 8.9s `passive_slice` Lag**: Global `db_lock` contention caused by legacy unindexed `instr(content, ?)` table scans on `Posts` (taking ~8.1s) blocking `DeliveryQueue` and `PostCopies` transaction writes during `passive_slice` execution.
- **Actionable Fix Strategy for Implementer**:
  1. Replace remaining `instr(content, ?)` calls on `Posts` in `common/database.py` with `PostFiles` indexed queries.
  2. Avoid holding global `db_lock` during non-transactional read queries in WAL mode.

---

## 5. Verification Method
1. Run `python bench_tags.py` to confirm tag search performance (**0.78 ms**).
2. Run `python .agents/explorer_2/db_investigation.py` to verify query plans on `PostFiles` and `DeliveryQueue`.
3. Run `python .agents/explorer_2/find_table_scans.py` to verify remaining `SCAN Posts` queries.
