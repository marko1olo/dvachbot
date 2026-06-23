import asyncio
import time
import aiosqlite

async def main():
    db = await aiosqlite.connect(':memory:')
    await db.execute("CREATE TABLE IF NOT EXISTS Threads (board_id TEXT, thread_id TEXT, last_updated_at REAL)")
    # Insert 10000 rows
    for i in range(10000):
        await db.execute("INSERT INTO Threads VALUES (?, ?, ?)", (f"board_{i%10}", f"thread_{i}", time.time() - i))
    await db.commit()

    async def benchmark_current_sqlite():
        urls = []
        base_url = "http://example.com"
        start_time = time.time()
        query = "SELECT board_id, thread_id, last_updated_at FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        async with db.execute(query) as cursor:
            async for row in cursor:
                bid, tid, ts = row
                # We do fromtimestamp in current code, which causes CPU overhead
                import datetime
                date_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

    async def benchmark_optimized_sqlite():
        urls = []
        base_url = "http://example.com"
        start_time = time.time()
        # We don't fetch last_updated_at since we don't use it!
        query = "SELECT board_id, thread_id FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            for bid, tid in rows:
                urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

    current_time = await benchmark_current_sqlite()
    print(f"Current time: {current_time:.4f}s")
    optimized_time = await benchmark_optimized_sqlite()
    print(f"Optimized time: {optimized_time:.4f}s")

if __name__ == "__main__":
    asyncio.run(main())
