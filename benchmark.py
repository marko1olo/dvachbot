import asyncio
import time
import random
import aiosqlite

async def main():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE Users (user_id INTEGER, balance INTEGER)")

        # Insert 1000 users
        users = [(i, 0) for i in range(1000)]
        await db.executemany("INSERT INTO Users (user_id, balance) VALUES (?, ?)", users)
        await db.commit()

        users_to_fix = [i for i in range(1000)]

        # Test 1: Loop
        start = time.time()
        for uid in users_to_fix:
            amount = random.randint(8, 15)
            await db.execute("""
                UPDATE Users SET balance = ?
                WHERE rowid = (SELECT rowid FROM Users WHERE user_id = ? LIMIT 1)
            """, (amount, uid))
        await db.commit()
        time_loop = time.time() - start

        # Test 2: executemany
        start = time.time()
        data = [(random.randint(8, 15), uid) for uid in users_to_fix]
        await db.executemany("""
            UPDATE Users SET balance = ?
            WHERE rowid = (SELECT rowid FROM Users WHERE user_id = ? LIMIT 1)
        """, data)
        await db.commit()
        time_executemany = time.time() - start

        print(f"Loop time: {time_loop:.4f}s")
        print(f"Executemany time: {time_executemany:.4f}s")

asyncio.run(main())
