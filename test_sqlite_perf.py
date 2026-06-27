import asyncio
import time
import sqlite3
import aiosqlite
from datetime import datetime

async def setup_db():
    async with aiosqlite.connect("test.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS Threads (board_id TEXT, thread_id TEXT, last_updated_at INTEGER)")
        await db.execute("DELETE FROM Threads")
        rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(10000)]
        await db.executemany("INSERT INTO Threads VALUES (?, ?, ?)", rows)
        await db.commit()

async def test_python_date():
    async with aiosqlite.connect("test.db") as db:
        start_time = time.time()
        urls = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id, last_updated_at FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        async with db.execute(query) as cursor:
            async for row in cursor:
                bid, tid, ts = row
                date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

async def test_sqlite_date():
    async with aiosqlite.connect("test.db") as db:
        start_time = time.time()
        urls = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id, date(last_updated_at, 'unixepoch') FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        async with db.execute(query) as cursor:
            async for row in cursor:
                bid, tid, date_str = row
                urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

async def main():
    await setup_db()
    t1 = await test_python_date()
    t2 = await test_sqlite_date()
    print(f"Python date conversion: {t1} seconds")
    print(f"SQLite date conversion: {t2} seconds")

asyncio.run(main())
