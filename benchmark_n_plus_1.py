import asyncio
import aiosqlite
import time

async def main():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE Threads (thread_id TEXT, thread_num INTEGER)")
        await db.execute("CREATE TABLE Posts (post_num INTEGER, thread_id TEXT)")

        # Insert 1000 posts, 100 threads
        user_posts = list(range(1, 1001))

        for i in range(100):
            await db.execute("INSERT INTO Threads (thread_id, thread_num) VALUES (?, ?)", (str(i*10), i*10))
            for j in range(10):
                await db.execute("INSERT INTO Posts (post_num, thread_id) VALUES (?, ?)", (i*10 + j, str(i*10)))

        await db.commit()

        # Test N+1
        start = time.time()
        threads_to_delete = []
        for p_num in user_posts:
            p_str = str(p_num)
            async with db.execute("SELECT thread_id FROM Threads WHERE thread_id = ? OR thread_num = ?", (p_str, p_num)) as cursor:
                t_row = await cursor.fetchone()
                if t_row:
                    threads_to_delete.append(t_row[0])

        posts_to_delete_set = set(user_posts)
        if threads_to_delete:
            for t_id in threads_to_delete:
                try: t_id_int = int(t_id)
                except ValueError: t_id_int = 0

                async with db.execute("SELECT post_num FROM Posts WHERE thread_id = ? OR thread_id = ?", (t_id, str(t_id_int))) as cursor:
                    p_rows = await cursor.fetchall()
                    for pr in p_rows:
                        posts_to_delete_set.add(pr[0])
        end = time.time()
        print(f"N+1 approach took: {end - start:.4f} seconds")
        print(f"Found {len(threads_to_delete)} threads to delete, {len(posts_to_delete_set)} total posts to delete")

        # Test Optimized
        start = time.time()
        threads_to_delete2 = []
        if user_posts:
            chunk_size = 400
            for i in range(0, len(user_posts), chunk_size):
                chunk = user_posts[i:i + chunk_size]
                placeholders = ','.join('?' for _ in chunk)
                params = [str(p) for p in chunk] + chunk

                query = f"SELECT thread_id FROM Threads WHERE thread_id IN ({placeholders}) OR thread_num IN ({placeholders})"
                async with db.execute(query, tuple(params)) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        threads_to_delete2.append(row[0])

        posts_to_delete_set2 = set(user_posts)
        if threads_to_delete2:
            chunk_size = 400
            for i in range(0, len(threads_to_delete2), chunk_size):
                chunk = threads_to_delete2[i:i + chunk_size]
                placeholders = ','.join('?' for _ in chunk)
                params = []
                for t_id in chunk:
                    params.append(t_id)
                for t_id in chunk:
                    try: t_id_int = int(t_id)
                    except ValueError: t_id_int = 0
                    params.append(str(t_id_int))

                query = f"SELECT post_num FROM Posts WHERE thread_id IN ({placeholders}) OR thread_id IN ({placeholders})"
                async with db.execute(query, tuple(params)) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        posts_to_delete_set2.add(row[0])
        end = time.time()
        print(f"Optimized approach took: {end - start:.4f} seconds")
        print(f"Found {len(threads_to_delete2)} threads to delete, {len(posts_to_delete_set2)} total posts to delete")

        assert set(threads_to_delete) == set(threads_to_delete2)
        assert posts_to_delete_set == posts_to_delete_set2

asyncio.run(main())
