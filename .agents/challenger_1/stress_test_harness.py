import asyncio
import time
import sys
import os
import sqlite3
import random
import statistics

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to sys.path
PROJECT_ROOT = r'C:\Users\danat\Desktop\dvachbot'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.database import (
    get_posts_by_file_ids,
    find_post_by_file_id,
    apply_auto_censure,
    get_post_copies,
    add_post_copies,
    upsert_delivery_queue_item,
    delete_delivery_queue_item,
)
from common.db_pool import get_pool, create_pool, db_lock

DB_PATH = os.path.join(PROJECT_ROOT, 'dvach_bot.db')

async def background_writer(stop_event: asyncio.Event, stats: dict):
    """Simulates background write operations on the database (creating posts, updating queues)."""
    db = await get_pool()
    counter = 888000
    while not stop_event.is_set():
        try:
            counter += 1
            # Write to DeliveryQueue
            durable_id = await upsert_delivery_queue_item(
                board_id="b",
                post_num=counter,
                recipients=[1001, 1002, 1003],
                content={"text": f"Background write test {counter}"},
                delivery_phase="passive",
                original_recipients=3,
                enqueued_at=time.time()
            )
            # Write to PostCopies
            await add_post_copies(counter, [(1001, counter * 10), (1002, counter * 10 + 1)])
            # Delete from DeliveryQueue
            if durable_id:
                await delete_delivery_queue_item(durable_id)
            stats['background_writes'] += 1
            await asyncio.sleep(0.005)  # 5ms delay between writes
        except Exception as e:
            stats['write_errors'] += 1
            print(f"[BACKGROUND WRITER ERROR] {e}")
            await asyncio.sleep(0.05)

async def background_reader(stop_event: asyncio.Event, stats: dict, sample_file_ids: list):
    """Simulates background read operations on the database."""
    while not stop_event.is_set():
        try:
            file_id = random.choice(sample_file_ids) if sample_file_ids else "test_file_id_12345"
            await find_post_by_file_id(file_id)
            await get_posts_by_file_ids([file_id])
            stats['background_reads'] += 1
            await asyncio.sleep(0.005)
        except Exception as e:
            stats['read_errors'] += 1
            print(f"[BACKGROUND READER ERROR] {e}")
            await asyncio.sleep(0.05)

async def stress_test_passive_slice(sample_file_ids: list, num_batches=10, batch_size=50):
    """
    Stress test passive_slice database execution under concurrent load.
    Executes num_batches of batch_size simulated passive_slice DB operations.
    """
    print(f"\n--- [TEST 1] STRESS TESTING passive_slice PATH ({num_batches} batches x {batch_size} ops = {num_batches*batch_size} total ops) ---")
    
    batch_durations = []
    
    async def run_single_op(i):
        test_post_num = 777000 + i
        await upsert_delivery_queue_item(test_post_num, "b", "pending", "passive_slice", 1, "test_recipients")
        await get_post_copies(test_post_num)
        await add_post_copies(test_post_num, [(2001, 20), (2002, 21), (2003, 22)])
        await find_post_by_file_id(sample_file_ids[0] if sample_file_ids else "test_id")
        await delete_delivery_queue_item(test_post_num)

    overall_t0 = time.perf_counter()
    
    for b in range(num_batches):
        t0 = time.perf_counter()
        tasks = [run_single_op(b * batch_size + i) for i in range(batch_size)]
        await asyncio.gather(*tasks)
        dt = time.perf_counter() - t0
        batch_durations.append(dt)
        print(f"  Batch {b+1}/{num_batches} ({batch_size} ops): {dt*1000:.2f} ms ({dt:.3f} s)")

    total_time_sec = time.perf_counter() - overall_t0
    avg_batch_ms = statistics.mean(batch_durations) * 1000
    max_batch_sec = max(batch_durations)
    
    print(f"\n[passive_slice SUMMARY]")
    print(f"  Total time for {num_batches*batch_size} operations: {total_time_sec:.3f} s")
    print(f"  Average batch time (50 ops): {avg_batch_ms:.2f} ms")
    print(f"  Max batch time (50 ops): {max_batch_sec:.3f} s")
    
    # Requirement: passive_slice time < 3.0s
    pass_condition = total_time_sec < 3.0 and max_batch_sec < 3.0
    print(f"  VERDICT: {'PASS' if pass_condition else 'FAIL'} (Threshold: < 3.0s)")
    return pass_condition, total_time_sec, avg_batch_ms, max_batch_sec

async def stress_test_tag_search(num_queries=100):
    """
    Stress test PostFiles tag search performance under load.
    Runs num_queries tag lookup queries using the new PostFiles strategy.
    """
    print(f"\n--- [TEST 2] STRESS TESTING TAG SEARCH PERFORMANCE ({num_queries} queries) ---")
    
    # Get active file_ids for realistic queries
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    tag = '1boy'
    query_fts = '''
        SELECT file_id, bm25(FileTagsFTS) as score, tags
        FROM FileTagsFTS
        WHERE FileTagsFTS MATCH ?
        ORDER BY score ASC
        LIMIT 60 OFFSET 0
    '''
    try:
        cursor.execute(query_fts, (f'"{tag}"*', ))
        res = cursor.fetchall()
        file_ids = [r[0] for r in res]
    except Exception as e:
        print(f"[WARN] FTS query warning: {e}, using fallback sample file_ids")
        file_ids = []

    if not file_ids:
        cursor.execute("SELECT original_file_id FROM PostFiles WHERE original_file_id IS NOT NULL AND original_file_id != '' LIMIT 60")
        file_ids = [r[0] for r in cursor.fetchall()]

    if not file_ids:
        file_ids = ["sample_fid_1", "sample_fid_2"]

    print(f"  Tag query using {len(file_ids)} file_ids")

    # New strategy query on PostFiles
    placeholders = ','.join(['?']*len(file_ids))
    params2 = file_ids + file_ids
    query_postfiles = f'''
        SELECT count(DISTINCT post_num)
        FROM PostFiles 
        WHERE original_file_id IN ({placeholders})
           OR thumbnail_file_id IN ({placeholders})
    '''

    durations_ms = []
    
    # Benchmark 1: Synchronous direct execution under load
    for i in range(num_queries):
        t0 = time.perf_counter()
        cursor.execute(query_postfiles, params2)
        count = cursor.fetchone()[0]
        dt_ms = (time.perf_counter() - t0) * 1000
        durations_ms.append(dt_ms)

    conn.close()

    p50 = statistics.median(durations_ms)
    p95 = statistics.quantiles(durations_ms, n=20)[18] if len(durations_ms) >= 20 else max(durations_ms)
    p99 = max(durations_ms)
    avg_ms = statistics.mean(durations_ms)

    print(f"\n[TAG SEARCH SUMMARY]")
    print(f"  Queries executed: {num_queries}")
    print(f"  Mean latency: {avg_ms:.2f} ms")
    print(f"  Median (p50): {p50:.2f} ms")
    print(f"  95th percentile (p95): {p95:.2f} ms")
    print(f"  Max (p99): {p99:.2f} ms")

    # Target: ~30-50ms or faster. We set strict threshold p95 < 50ms and avg < 30ms.
    pass_condition = p95 <= 50.0 and avg_ms <= 30.0
    print(f"  VERDICT: {'PASS' if pass_condition else 'FAIL'} (Threshold: p95 <= 50ms, avg <= 30ms)")
    return pass_condition, avg_ms, p50, p95, p99

async def main_stress_harness():
    print("=" * 70)
    print("      DVACHBOT EMPIRICAL STRESS TEST HARNESS — CHALLENGER 1      ")
    print("=" * 70)
    
    # Initialize DB pool
    await create_pool()

    # Get sample file IDs
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT original_file_id FROM PostFiles WHERE original_file_id IS NOT NULL AND original_file_id != '' LIMIT 20")
    sample_file_ids = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()

    # Start background stress generators (writers & readers)
    stop_event = asyncio.Event()
    stats = {'background_writes': 0, 'background_reads': 0, 'write_errors': 0, 'read_errors': 0}
    
    writer_tasks = [asyncio.create_task(background_writer(stop_event, stats)) for _ in range(3)]
    reader_tasks = [asyncio.create_task(background_reader(stop_event, stats, sample_file_ids)) for _ in range(3)]

    print("\n[INFO] Background DB stress workers started (3 writers, 3 readers)...")
    await asyncio.sleep(0.5)

    try:
        # Run passive_slice stress test (10 batches of 50 = 500 ops)
        passive_pass, total_sec, avg_b_ms, max_b_sec = await stress_test_passive_slice(sample_file_ids, num_batches=10, batch_size=50)

        # Run tag search stress test (100 queries)
        tag_pass, tag_avg, tag_p50, tag_p95, tag_p99 = await stress_test_tag_search(num_queries=100)

    finally:
        stop_event.set()
        await asyncio.gather(*writer_tasks, *reader_tasks, return_exceptions=True)

    print("\n" + "=" * 70)
    print(f"Background Load Stats: {stats['background_writes']} writes, {stats['background_reads']} reads | Errors: {stats['write_errors']} w, {stats['read_errors']} r")
    
    overall_pass = passive_pass and tag_pass and stats['write_errors'] == 0 and stats['read_errors'] == 0
    
    print("\n" + "=" * 70)
    print(f"FINAL STRESS HARNESS VERDICT: {'APPROVE' if overall_pass else 'REQUEST_CHANGES'}")
    print("=" * 70)

    return overall_pass

if __name__ == '__main__':
    success = asyncio.run(main_stress_harness())
    sys.exit(0 if success else 1)
