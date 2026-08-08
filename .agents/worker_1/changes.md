# Changes Report — worker_1

## Overview
Fixed the `passive_slice` performance regression in `dvachbot` by adding missing single-column indices on `PostFiles` and refactoring legacy unindexed table scans (`WHERE instr(content, ?) > 0` on `Posts`) to use `PostFiles` index mapping.

## Files Modified

### 1. `common/database.py`
- **Single-Column Indices Added**:
  Added `CREATE INDEX IF NOT EXISTS idx_postfiles_orig ON PostFiles(original_file_id);`, `CREATE INDEX IF NOT EXISTS idx_postfiles_thumb ON PostFiles(thumbnail_file_id);`, and `CREATE INDEX IF NOT EXISTS idx_postfiles_post_num ON PostFiles(post_num);` in `_create_indices()`.
- **Refactored `apply_auto_censure()`**:
  Replaced legacy `WHERE instr(content, ?) > 0` on `Posts` with an indexed `PostFiles` query:
  ```sql
  SELECT post_num, content, is_shadow FROM Posts 
  WHERE post_num IN (
      SELECT post_num FROM PostFiles 
      WHERE original_file_id = ? OR thumbnail_file_id = ?
  )
  ```
- **Refactored `find_post_by_file_id()`**:
  Replaced legacy `WHERE instr(content, ?) > 0` on `Posts` with an indexed `PostFiles` query:
  ```sql
  SELECT post_num, board_id, author_id, content, timestamp 
  FROM Posts 
  WHERE post_num IN (
      SELECT post_num FROM PostFiles 
      WHERE original_file_id = ? OR thumbnail_file_id = ?
  )
  ORDER BY timestamp DESC 
  LIMIT 1
  ```

### 2. `backfill_pf.py`
- **Schema Indices Update**:
  Added creation of `idx_postfiles_orig` and `idx_postfiles_thumb` single-column indices alongside table creation.

### 3. `bench_passive_slice.py` (New Benchmark Script)
- Created benchmark diagnostic script measuring:
  - `find_post_by_file_id()` execution time (0.40 ms)
  - `apply_auto_censure()` execution time (0.43 ms)
  - `get_posts_by_file_ids()` execution time (0.26 ms)
  - 50 concurrent simulated `passive_slice` database workflow cycles under global lock contention (0.045 s / 44.87 ms)
- Asserts that total `passive_slice` processing time is strictly < 3.0 seconds.

## Verification & Results
1. `bench_tags.py`:
   - Old method (`instr` scan): 8,249.43 ms
   - New method (`PostFiles` indexed): **1.31 ms** (~6300x speedup)
2. `bench_passive_slice.py`:
   - Total 50-batch slice processing time: **0.045 seconds** (< 3.0s threshold passed)
3. Bot Startup & Import Check:
   - `python -c "import main, delivery_manager, broadcaster, user_manager"` executed with exit code 0.
