import asyncio
import time
import sqlite3
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r'C:\Users\danat\Desktop\dvachbot')

# Fetch sample file_ids FIRST before opening pool
conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cur = conn.cursor()
cur.execute("SELECT original_file_id FROM PostFiles WHERE original_file_id IS NOT NULL AND original_file_id != '' AND original_file_id NOT LIKE '%mock%' LIMIT 10")
sample_file_ids = [r[0] for r in cur.fetchall() if r[0]]
conn.close()

print(f"Sample real file_ids: {sample_file_ids[:3]}")
sys.stdout.flush()

from common.database import (
    get_posts_by_file_ids,
    find_post_by_file_id,
    apply_auto_censure,
    get_post_copies,
    add_post_copies,
    upsert_delivery_queue_item,
    delete_delivery_queue_item,
)
from common.db_pool import get_pool, create_pool

async def main():
    await create_pool()

    t0 = time.perf_counter()
    post_res = await find_post_by_file_id(sample_file_ids[0])
    t_find_post = (time.perf_counter() - t0) * 1000
    print(f"find_post_by_file_id: {t_find_post:.2f} ms (Found: {post_res is not None})")
    sys.stdout.flush()

    t0 = time.perf_counter()
    censure_res = await apply_auto_censure(sample_file_ids[0], action="shadow")
    t_censure = (time.perf_counter() - t0) * 1000
    print(f"apply_auto_censure: {t_censure:.2f} ms (Affected: {len(censure_res)})")
    sys.stdout.flush()

    t0 = time.perf_counter()
    posts_res = await get_posts_by_file_ids(sample_file_ids)
    t_get_posts = (time.perf_counter() - t0) * 1000
    print(f"get_posts_by_file_ids: {t_get_posts:.2f} ms (Returned: {len(posts_res)})")
    sys.stdout.flush()

    # 50 simulated passive slice DB cycles
    t0 = time.perf_counter()
    async def run_simulated_slice_op(i):
        test_post_num = 999000 + i
        await upsert_delivery_queue_item(test_post_num, "test_board", "pending", "passive_slice", 1, "test_recipients")
        await get_post_copies(test_post_num)
        await add_post_copies(test_post_num, [(1001, 10), (1002, 11), (1003, 12)])
        await find_post_by_file_id(sample_file_ids[0])
        await delete_delivery_queue_item(test_post_num)

    tasks = [run_simulated_slice_op(i) for i in range(50)]
    await asyncio.gather(*tasks)

    total_time_sec = time.perf_counter() - t0
    print(f"50 passive_slice DB cycles total time: {total_time_sec * 1000:.2f} ms ({total_time_sec:.3f} s)")
    sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
