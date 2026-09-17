import asyncio
import time
import json
import sqlite3
import aiosqlite

async def setup(db_path):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS Boards (
                board_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                is_approved INTEGER,
                banner_data TEXT
            )
        """)

        data = []
        for i in range(10000):
            data.append((f"board{i}", f"name{i}", f"desc{i}", i % 2, '{"img":"1","link":"2"}'))

        await db.executemany(
            "INSERT OR IGNORE INTO Boards (board_id, name, description, is_approved, banner_data) VALUES (?, ?, ?, ?, ?)",
            data
        )
        await db.commit()

async def baseline(db_path):
    local_config = {"b": {"name": "b", "description": "b"}}

    start = time.perf_counter()
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT board_id, name, description FROM Boards WHERE is_approved = 1"
        ) as cursor:
            async for row in cursor:
                bid, bname, bdesc = row
                if bid not in local_config:
                    local_config[bid] = {"name": bname, "description": bdesc}

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT board_id, banner_data FROM Boards") as cursor:
            async for row in cursor:
                bid, bdata = row
                if bid in local_config and bdata:
                    try:
                        local_config[bid]["banner_data"] = json.loads(bdata)
                    except Exception:
                        pass
    end = time.perf_counter()
    return end - start, local_config

async def optimized(db_path):
    local_config = {"b": {"name": "b", "description": "b"}}

    start = time.perf_counter()
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT board_id, name, description, is_approved, banner_data FROM Boards"
        ) as cursor:
            async for row in cursor:
                bid, bname, bdesc, is_approved, bdata = row
                if is_approved == 1 and bid not in local_config:
                    local_config[bid] = {"name": bname, "description": bdesc}
                if bid in local_config and bdata:
                    try:
                        local_config[bid]["banner_data"] = json.loads(bdata)
                    except Exception:
                        pass
    end = time.perf_counter()
    return end - start, local_config

async def main():
    db_path = "test_boards.db"
    await setup(db_path)

    await baseline(db_path)
    await optimized(db_path)

    t1_sum = 0
    t2_sum = 0
    for _ in range(5):
        t1, c1 = await baseline(db_path)
        t2, c2 = await optimized(db_path)
        t1_sum += t1
        t2_sum += t2
        assert len(c1) == len(c2)

    print(f"Baseline: {t1_sum/5:.4f}s")
    print(f"Optimized: {t2_sum/5:.4f}s")

if __name__ == '__main__':
    asyncio.run(main())
