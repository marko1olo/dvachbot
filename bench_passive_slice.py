import asyncio
import time
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add working directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

async def benchmark_passive_slice():
    print("=" * 60)
    print("Starting passive_slice Database Performance Benchmark")
    print("=" * 60)

    # Initialize DB pool
    await create_pool()

    import sqlite3
    conn = sqlite3.connect('dvach_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT original_file_id FROM PostFiles WHERE original_file_id IS NOT NULL AND original_file_id != '' LIMIT 10")
    sample_file_ids = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()

    if not sample_file_ids:
        sample_file_ids = ["test_file_id_12345"]

    print(f"[INFO] Using sample file_ids: {sample_file_ids[:3]}...")

    # 1. Measure find_post_by_file_id
    t0 = time.perf_counter()
    post_res = await find_post_by_file_id(sample_file_ids[0])
    t_find_post = (time.perf_counter() - t0) * 1000
    print(f"[BENCHMARK] find_post_by_file_id: {t_find_post:.2f} ms (Result: {'Found' if post_res else 'Not Found'})")

    # 2. Measure apply_auto_censure
    t0 = time.perf_counter()
    censure_res = await apply_auto_censure(sample_file_ids[0], action="shadow")
    t_censure = (time.perf_counter() - t0) * 1000
    print(f"[BENCHMARK] apply_auto_censure: {t_censure:.2f} ms (Affected posts: {len(censure_res)})")

    # 3. Measure get_posts_by_file_ids
    t0 = time.perf_counter()
    posts_res = await get_posts_by_file_ids(sample_file_ids)
    t_get_posts = (time.perf_counter() - t0) * 1000
    print(f"[BENCHMARK] get_posts_by_file_ids ({len(sample_file_ids)} IDs): {t_get_posts:.2f} ms (Returned: {len(posts_res)} posts)")

    # 4. Measure simulated passive_slice batch database operations (50 iterations)
    t0 = time.perf_counter()

    async def run_simulated_slice_op(i):
        test_post_num = 999000 + i
        # Simulate delivery queue item save, copy lookup, copy insert, file lookup
        await upsert_delivery_queue_item(test_post_num, "test_board", "pending", "passive_slice", 1, "test_recipients")
        await get_post_copies(test_post_num)
        await add_post_copies(test_post_num, [(1001, 10), (1002, 11), (1003, 12)])
        await find_post_by_file_id(sample_file_ids[0])
        await delete_delivery_queue_item(test_post_num)

    # Run 50 simulated slice ops concurrently
    tasks = [run_simulated_slice_op(i) for i in range(50)]
    await asyncio.gather(*tasks)

    total_time_sec = time.perf_counter() - t0
    print(f"[BENCHMARK] Simulated 50 passive_slice DB cycles: {total_time_sec * 1000:.2f} ms ({total_time_sec:.3f} s)")

    print("=" * 60)
    print(f"Summary: passive_slice processing time = {total_time_sec:.3f} seconds")
    
    # Target condition check: < 3.0 seconds
    if total_time_sec < 3.0:
        print(f"SUCCESS: passive_slice execution completed in {total_time_sec:.3f}s (< 3.0s limit).")
        return True
    else:
        print(f"FAILURE: passive_slice execution took {total_time_sec:.3f}s (exceeds 3.0s limit).")
        return False

if __name__ == "__main__":
    success = asyncio.run(benchmark_passive_slice())
    sys.exit(0 if success else 1)
