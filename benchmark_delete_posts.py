import asyncio
import json
import time
import aiosqlite

async def benchmark_current():
    db = await aiosqlite.connect(":memory:")
    await db.execute("CREATE TABLE Posts (post_num INTEGER, thread_id TEXT)")

    data = []
    for i in range(50000):
        data.append((i, str(i % 5000)))
    await db.executemany("INSERT INTO Posts VALUES (?, ?)", data)

    t_ids = [str(i) for i in range(5000)]

    start = time.perf_counter()
    posts_to_delete_set = set()
    chunk_size = 400
    for i in range(0, len(t_ids), chunk_size):
        chunk = t_ids[i:i+chunk_size]
        placeholders_threads = ','.join(['?'] * len(chunk))
        query = f"SELECT post_num FROM Posts WHERE thread_id IN ({placeholders_threads})"
        async with db.execute(query, chunk) as cursor:
            p_rows = await cursor.fetchall()
            for pr in p_rows:
                posts_to_delete_set.add(pr[0])

    end = time.perf_counter()
    print(f"Current: {end - start:.5f}s, found {len(posts_to_delete_set)}")

    start = time.perf_counter()
    posts_to_delete_set2 = set()
    t_ids_json = json.dumps(t_ids)
    query = "SELECT post_num FROM Posts WHERE thread_id IN (SELECT value FROM json_each(?))"
    async with db.execute(query, (t_ids_json,)) as cursor:
        p_rows = await cursor.fetchall()
        for pr in p_rows:
            posts_to_delete_set2.add(pr[0])

    end = time.perf_counter()
    print(f"Optimized: {end - start:.5f}s, found {len(posts_to_delete_set2)}")

    await db.close()

asyncio.run(benchmark_current())
