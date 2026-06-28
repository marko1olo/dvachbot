import asyncio
import aiosqlite
import time

async def main():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE posts (
                post_num INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT,
                thread_id INTEGER,
                content TEXT,
                timestamp INTEGER,
                author_id TEXT,
                reply_to_post_num INTEGER,
                stream TEXT
            )
        """)

        # Method 1: Single inserts in loop
        start = time.time()
        for i in range(1000):
            cur = await db.execute(
                """INSERT INTO posts
                   (board_id, thread_id, content, timestamp, author_id, reply_to_post_num, stream)
                   VALUES (?, ?, ?, ?, ?, NULL, ?) RETURNING post_num""",
                ("b", 1, "test", 1234567890, "author", "en")
            )
            new_id = (await cur.fetchone())[0]
        end = time.time()
        print(f"Loop insert: {end - start:.4f} seconds")

        # Method 2: Batch insert
        start = time.time()
        params = []
        for i in range(1000):
            params.extend(["b", 2, "test", 1234567890, "author", "en"])

        placeholders = ", ".join(["(?, ?, ?, ?, ?, NULL, ?)"] * 1000)
        cur = await db.execute(
            f"""INSERT INTO posts
               (board_id, thread_id, content, timestamp, author_id, reply_to_post_num, stream)
               VALUES {placeholders} RETURNING post_num""",
            params
        )
        new_ids = [row[0] for row in await cur.fetchall()]
        end = time.time()
        print(f"Batch insert: {end - start:.4f} seconds")

asyncio.run(main())
