import asyncio
import aiosqlite
import time
import random
import json

DB_NAME = "dvach_bot.db"
CONCURRENCY = 50
TOTAL_POSTS = 5000

async def bot_worker(worker_id, num_posts, stats):
    try:
        async with aiosqlite.connect(DB_NAME, timeout=60.0, isolation_level=None) as db:
            for i in range(num_posts):
                start = time.time()
                try:
                    # Simulate complex bot insert transaction
                    board_id = "b"
                    author_id = random.randint(100000, 999999)
                    content = {"text": f"Stress test post {worker_id}-{i}", "files": []}
                    
                    # 1. Insert Post
                    post_query = """
                        INSERT INTO Posts (board_id, author_id, content, timestamp, thread_id, reply_to_post_num, stream, is_shadow, ip)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    async with db.execute(post_query, (board_id, author_id, json.dumps(content), time.time(), None, None, 'main', 0, '127.0.0.1')) as cur:
                        post_num = cur.lastrowid
                    
                    # 2. Insert PostFiles
                    file_id = f"file_{worker_id}_{i}"
                    file_query = """
                        INSERT INTO PostFiles (post_num, file_type, original_file_id, thumbnail_file_id)
                        VALUES (?, ?, ?, ?)
                    """
                    await db.execute(file_query, (post_num, 'photo', file_id, file_id + "_thumb"))
                    
                    elapsed = time.time() - start
                    stats['success'] += 1
                    stats['latencies'].append(elapsed)
                except Exception as e:
                    if "database is locked" in str(e).lower():
                        stats['locks'] += 1
                    else:
                        stats['errors'] += 1
                        print(f"Error: {e}")
    except Exception as e:
        print(f"Worker {worker_id} failed to connect: {e}")

async def main():
    print(f"Starting bot DB stress test: {TOTAL_POSTS} posts, {CONCURRENCY} concurrency.")
    stats = {'success': 0, 'locks': 0, 'errors': 0, 'latencies': []}
    
    posts_per_worker = TOTAL_POSTS // CONCURRENCY
    tasks = []
    
    start_time = time.time()
    for i in range(CONCURRENCY):
        tasks.append(asyncio.create_task(bot_worker(i, posts_per_worker, stats)))
        
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    if stats['latencies']:
        avg_latency = sum(stats['latencies']) / len(stats['latencies'])
        max_latency = max(stats['latencies'])
    else:
        avg_latency = max_latency = 0
        
    print("\n--- Bot DB Stress Test Results ---")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Inserts per second: {TOTAL_POSTS / total_time:.2f} IPS")
    print(f"Success: {stats['success']}")
    print(f"DB Locks: {stats['locks']}")
    print(f"Other Errors: {stats['errors']}")
    print(f"Average Insert Latency: {avg_latency*1000:.2f} ms")
    print(f"Max Insert Latency: {max_latency*1000:.2f} ms")

if __name__ == "__main__":
    asyncio.run(main())
