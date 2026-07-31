import asyncio
import time
import sqlite3
import aiosqlite
import os

async def main():
    if os.path.exists("test_bench.db"):
        os.remove("test_bench.db")

    async with aiosqlite.connect("test_bench.db") as conn:
        await conn.execute("CREATE TABLE Users (user_id INTEGER, board_id TEXT, stream TEXT, PRIMARY KEY(user_id, board_id, stream))")
        await conn.commit()

        unique_authors = set(range(1000))
        target_board = "b"
        stream = "ru"

        # Test 1: N+1
        await conn.execute("DELETE FROM Users")
        await conn.commit()

        start = time.time()
        await conn.execute("BEGIN")
        for uid in unique_authors:
            await conn.execute("INSERT OR IGNORE INTO Users (user_id, board_id, stream) VALUES (?, ?, ?)", (uid, target_board, stream))
        await conn.commit()
        end = time.time()
        print(f"N+1 loop time: {end - start:.4f} seconds")

        # Test 2: executemany
        await conn.execute("DELETE FROM Users")
        await conn.commit()

        start = time.time()
        await conn.execute("BEGIN")
        user_params = [(uid, target_board, stream) for uid in unique_authors]
        if user_params:
            await conn.executemany("INSERT OR IGNORE INTO Users (user_id, board_id, stream) VALUES (?, ?, ?)", user_params)
        await conn.commit()
        end = time.time()
        print(f"executemany time: {end - start:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
