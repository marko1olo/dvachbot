import asyncio
import aiosqlite

async def main():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE posts (
                post_num INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT
            )
        """)

        params = []
        for i in range(5):
            params.append(f"test_{i}")

        placeholders = ", ".join(["(?)"] * 5)
        cur = await db.execute(
            f"INSERT INTO posts (content) VALUES {placeholders} RETURNING post_num, content",
            params
        )
        rows = await cur.fetchall()
        print(rows)

asyncio.run(main())
