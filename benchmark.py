import asyncio
import aiosqlite
import time

async def setup_db(db_path):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS Posts (post_num INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT)")
        # Insert 1000 threads, each with 10 posts
        await db.execute("DELETE FROM Posts")
        posts = []
        for t in range(1000):
            for p in range(10):
                posts.append((str(t),))
        await db.executemany("INSERT INTO Posts (thread_id) VALUES (?)", posts)
        await db.commit()

async def benchmark_n_plus_1(db_path, threads_to_delete):
    start_time = time.time()
    posts_to_delete_set = set()
    async with aiosqlite.connect(db_path) as db:
        for t_id in threads_to_delete:
            try: t_id_int = int(t_id)
            except ValueError: t_id_int = 0

            async with db.execute("SELECT post_num FROM Posts WHERE thread_id = ? OR thread_id = ?", (t_id, str(t_id_int))) as cursor:
                p_rows = await cursor.fetchall()
                for pr in p_rows:
                    posts_to_delete_set.add(pr[0])
    return time.time() - start_time

async def benchmark_optimized(db_path, threads_to_delete):
    start_time = time.time()
    posts_to_delete_set = set()
    async with aiosqlite.connect(db_path) as db:
        if threads_to_delete:
            # Flatten to include both t_id and string of int representation to match original logic
            t_ids = []
            for t_id in threads_to_delete:
                t_ids.append(t_id)
                try:
                    t_ids.append(str(int(t_id)))
                except ValueError:
                    t_ids.append(str(0))

            placeholders = ','.join('?' for _ in t_ids)
            query = f"SELECT post_num FROM Posts WHERE thread_id IN ({placeholders})"
            async with db.execute(query, t_ids) as cursor:
                p_rows = await cursor.fetchall()
                for pr in p_rows:
                    posts_to_delete_set.add(pr[0])
    return time.time() - start_time

async def main():
    db_path = "test_benchmark.db"
    await setup_db(db_path)

    threads_to_delete = [str(i) for i in range(1000)]

    time_n_plus_1 = await benchmark_n_plus_1(db_path, threads_to_delete)
    print(f"N+1 approach took: {time_n_plus_1:.4f} seconds")

    time_optimized = await benchmark_optimized(db_path, threads_to_delete)
    print(f"Optimized approach took: {time_optimized:.4f} seconds")

    print(f"Improvement: {time_n_plus_1 / time_optimized:.2f}x faster")

asyncio.run(main())
