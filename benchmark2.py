import asyncio
import time
import sqlite3
import aiosqlite
import json

async def setup_db():
    conn = await aiosqlite.connect('test_perf.db')
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS Threads (
            thread_id INTEGER PRIMARY KEY,
            board_id TEXT,
            title TEXT,
            last_updated_at INTEGER,
            is_archived INTEGER
        )
    """)
    await conn.commit()
    # Insert some data
    await conn.execute("DELETE FROM Threads")

    threads = []
    for bid in [f"{i}" for i in range(10)]:
        for j in range(100):
            threads.append((bid, f"Thread {j}", time.time() - j, 0))
    await conn.executemany("INSERT INTO Threads (board_id, title, last_updated_at, is_archived) VALUES (?, ?, ?, ?)", threads)
    await conn.commit()
    return conn

async def run_optimized(db, stats):
    start = time.perf_counter()
    bids = list(stats.keys())
    async with db.execute("""
        SELECT board_id, thread_id, title, last_updated_at
        FROM (
            SELECT board_id, thread_id, title, last_updated_at,
                   ROW_NUMBER() OVER(PARTITION BY board_id ORDER BY last_updated_at DESC) as rn
            FROM Threads
            WHERE is_archived = 0 AND board_id IN (SELECT CAST(value AS TEXT) FROM json_each(?))
        )
        WHERE rn <= 5
    """, (json.dumps(bids),)) as cursor:
        async for row in cursor:
            bid = str(row[0])
            stats[bid]["top_threads"].append(row[1])
    return time.perf_counter() - start

async def main():
    db = await setup_db()
    stats = {f"{i}": {"top_threads": []} for i in range(10)}

    o_time = await run_optimized(db, stats)
    print(f"Optimized: {o_time:.6f}s")
    for k, v in stats.items():
        print(f"Board {k}: {len(v['top_threads'])} threads")

    await db.close()

if __name__ == '__main__':
    asyncio.run(main())
