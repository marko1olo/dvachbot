import asyncio
import aiohttp
import time
import sys

# Target routes
BASE_URL = "http://127.0.0.1:8000"
ROUTES = [
    "/b/catalog.json",
    "/api/media-feed/b",
    "/api/threads/b",
    "/api/admin/stats",
    "/api/admin/recent_posts"
]

CONCURRENCY = 100
TOTAL_REQUESTS = 1000

async def fetch(session, url, stats):
    start = time.time()
    try:
        async with session.get(url) as response:
            await response.read()
            elapsed = time.time() - start
            stats['success'] += 1
            stats['latencies'].append(elapsed)
    except Exception as e:
        stats['errors'] += 1

async def worker(queue, session, stats):
    while True:
        url = await queue.get()
        await fetch(session, url, stats)
        queue.task_done()

async def main():
    print(f"Starting web stress test: {TOTAL_REQUESTS} requests, {CONCURRENCY} concurrency.")
    stats = {'success': 0, 'errors': 0, 'latencies': []}
    queue = asyncio.Queue()
    
    for i in range(TOTAL_REQUESTS):
        queue.put_nowait(BASE_URL + ROUTES[i % len(ROUTES)])
        
    async with aiohttp.ClientSession() as session:
        tasks = []
        for _ in range(CONCURRENCY):
            task = asyncio.create_task(worker(queue, session, stats))
            tasks.append(task)
            
        start_time = time.time()
        await queue.join()
        total_time = time.time() - start_time
        
        for task in tasks:
            task.cancel()
            
    if stats['latencies']:
        avg_latency = sum(stats['latencies']) / len(stats['latencies'])
        max_latency = max(stats['latencies'])
    else:
        avg_latency = max_latency = 0
        
    print("\n--- Web Stress Test Results ---")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Requests per second: {TOTAL_REQUESTS / total_time:.2f} RPS")
    print(f"Success: {stats['success']}")
    print(f"Errors: {stats['errors']}")
    print(f"Average Latency: {avg_latency*1000:.2f} ms")
    print(f"Max Latency: {max_latency*1000:.2f} ms")

if __name__ == "__main__":
    asyncio.run(main())
