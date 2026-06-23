import asyncio
import time
import sqlite3
from collections import defaultdict
import aiosqlite
import json

async def setup_db():
    async with aiosqlite.connect("test_benchmark.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS Backlinks (target_post_num INTEGER, source_post_num INTEGER)")
        await db.execute("DELETE FROM Backlinks")

        # Insert test data: 1000 targets, 50 sources each
        data = []
        for i in range(1, 1001):
            for j in range(1, 51):
                data.append((i, i * 1000 + j))

        await db.executemany("INSERT INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)", data)
        await db.commit()

async def benchmark_current(db, target_ids):
    placeholders = ','.join('?' for _ in target_ids)
    query = f"SELECT target_post_num, source_post_num FROM Backlinks WHERE target_post_num IN ({placeholders})"

    start_time = time.perf_counter()
    backlinks_map = defaultdict(list)
    async with db.execute(query, target_ids) as cursor:
        async for row in cursor:
            target, source = row
            backlinks_map[target].append(source)
    end_time = time.perf_counter()
    return end_time - start_time, backlinks_map

async def benchmark_optimized(db, target_ids):
    placeholders = ','.join('?' for _ in target_ids)
    query = f"SELECT target_post_num, json_group_array(source_post_num) FROM Backlinks WHERE target_post_num IN ({placeholders}) GROUP BY target_post_num"

    start_time = time.perf_counter()
    backlinks_map = defaultdict(list)
    async with db.execute(query, target_ids) as cursor:
        async for row in cursor:
            target, sources_json = row
            backlinks_map[target] = json.loads(sources_json)
    end_time = time.perf_counter()
    return end_time - start_time, backlinks_map

async def main():
    await setup_db()
    async with aiosqlite.connect("test_benchmark.db") as db:
        target_ids = list(range(1, 1001))

        # warmup
        await benchmark_current(db, target_ids)
        await benchmark_optimized(db, target_ids)

        # run
        curr_time, _ = await benchmark_current(db, target_ids)
        opt_time, _ = await benchmark_optimized(db, target_ids)

        print(f"Current approach: {curr_time:.5f}s")
        print(f"Optimized approach: {opt_time:.5f}s")
        if curr_time > 0:
            print(f"Improvement: {(curr_time - opt_time) / curr_time * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
