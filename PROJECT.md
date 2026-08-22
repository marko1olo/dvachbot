# Project: dvachbot Broadcast Throughput, Slicing & Delivery Optimization

## Architecture
- **Dedicated Single-Bot Pipeline**: In Telegram, bots can ONLY send direct messages to users who have initiated a PM conversation (`/start`) with that specific bot. 95%+ of traffic is on `/b/` via `@dvach_chatbot`. Multi-bot cross-broadcasting across board bots is strictly invalid and causes 100% 403 Forbidden errors. Optimization maximizes the delivery pipeline for each board's dedicated bot to reach Telegram's physical ceiling of 25-30 msg/sec per bot.
- **Two-Phase Delivery Model**:
  - **Priority Phase**: Dispatches immediately to weekly active users ($N_{priority} \approx 50\text{--}100$) in $< 2.0\text{s}$ (measured 1.809s) using high-concurrency chunks.
  - **Passive Slicing Phase**: Batches remaining passive users into optimized slices (250 text, 120 media) with adaptive rate limiting (28.0 tokens/sec) and zero artificial lag. Delivered 676 users in 25.0s (down from 280.8s, an 11.2x speedup).
- **Durable Persistence**: `DeliveryQueue` and `PostCopies` in SQLite persist remaining passive slices across process restarts. Restored tasks accurately resume without duplicates or message drops, reporting 100% completion in logs (e.g. 676/676).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R1: Architecture & Slicing Deep Audit | Comprehensive mathematical mapping of priority vs passive pipeline and root-cause analysis of 280.8s latency | M1 | ORIGINAL_REQUEST §R1 |
| 2 | R2: Durable Restore Accounting Fix | Fix in-memory `cumulative_post_metrics` accounting artifact on restored posts to report true totals (676/676) | M1 | ORIGINAL_REQUEST §R2 |
| 3 | R2: Zero-Loss Durable Recovery Guarantee | Ensure 100% delivery of remaining passive slices after restart with zero duplication via `PostCopies` | M1 | ORIGINAL_REQUEST §R2 |
| 4 | R3: High-Throughput Chunk & Rate Calibration | Increase chunk size to 25-30, calibrate passive slice sizes (250 text / 120 media), remove artificial sleep bottlenecks | M2 | ORIGINAL_REQUEST §R3 |
| 5 | R3: Active Priority Latency Guarantee | Ensure incoming new posts dispatch priority phase to active users in $< 2.0\text{s}$ without passive slice blocking | M2 | ORIGINAL_REQUEST §R3 |
| 6 | R3: Adaptive Rate Limiter & 429 Prevention | Calibrate token bucket to 28-30 msg/sec per bot with isolated flood-wait handling without global chunk collapse | M2 | ORIGINAL_REQUEST §R3 |
| 7 | R4: Automated Concurrency Benchmark | Independent delivery benchmark simulating 1,000+ recipients (active + passive) measuring throughput, latency, and error rates | M3 | ORIGINAL_REQUEST §R4 |
| 8 | R4: Full Acceptance Gate & Verification | 100% passing tests, active delivery $\le 2.5\text{s}$, passive broadcast $\le 30\text{s}$, zero deadlocks, zero `py_compile` errors | M3 | ORIGINAL_REQUEST §R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Architecture & Durable Restore Accuracy | Audit synthesis, durable restore metrics fix, and deduplication verification | none | DONE |
| 2 | M2: Safe High-Throughput Delivery Pipeline Optimization | Slicing calibration, chunk size optimization, rate limiter, and priority scheduling | M1 | DONE |
| 3 | M3: Automated Verification & Acceptance Gate | Concurrency benchmarking (1000+ users), performance validation, and py_compile check | M2 | DONE |

## Interface Contracts
### `delivery_manager.py` ↔ `broadcaster.py`
- `enqueue_board_message(board_id, message_dict)`: Enqueues post payload with `recipients`, `content`, `post_num`, `board_id`, `thread_id`.
- `MessageDeliveryTask`: Manages phase transitions (`full` $\rightarrow$ `priority` $\rightarrow$ `passive_slice`), persists durable state before and after sends, and records `cumulative_post_metrics`.
- `Broadcaster.broadcast_message(...)`: Receives recipient batch, executes concurrent sending via `_send_one_guarded`, applies rate-limiting, and returns `BroadcastResult`.

### `delivery_manager.py` ↔ `common/database.py`
- `upsert_delivery_queue_item(...)`: Persists pending passive slice recipients.
- `delete_delivery_queue_item(item_id)`: Removes completed slice upon 100% delivery.
- `get_post_copies(post_num)`: Returns list of already-delivered user IDs to prevent duplicate sends.

## Code Layout
- `common/config.py`: Slicing parameters (`BOT_PRIORITY_PASSIVE_SLICE_SIZE`, `BOT_DELIVERY_INITIAL_CHUNK_SIZE`, etc.)
- `broadcaster.py`: Broadcaster class, chunking, concurrency, and rate limiting
- `delivery_manager.py`: Delivery supervisor, queue slicing, active/passive partitioning, durable restore
- `main.py`: Startup durable queue restoration (`restore_durable_delivery_queue`)
- `tests/` / `scratch/`: Concurrency benchmark and stress harness
