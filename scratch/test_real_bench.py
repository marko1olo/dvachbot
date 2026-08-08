import asyncio
import sqlite3
import time
import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.database import find_post_by_file_id, get_posts_by_file_ids, apply_auto_censure
from common.db_pool import create_pool

async def main():
    await create_pool()
    conn = sqlite3.connect('dvach_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT original_file_id FROM PostFiles WHERE original_file_id NOT LIKE '%mock%' AND original_file_id IS NOT NULL LIMIT 10")
    ids = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    
    print('Testing with real IDs:', len(ids))
    
    t0 = time.perf_counter()
    post = await find_post_by_file_id(ids[0])
    print(f'find_post_by_file_id time: {(time.perf_counter() - t0)*1000:.2f} ms. Found post: {bool(post)}')
    
    t0 = time.perf_counter()
    posts = await get_posts_by_file_ids(ids)
    print(f'get_posts_by_file_ids time: {(time.perf_counter() - t0)*1000:.2f} ms. Returned count: {len(posts)}')

if __name__ == '__main__':
    asyncio.run(main())
