import asyncio
import time
import json
from common.database import get_db_connection, initialize_database
from common.db_pool import create_pool

BOARD_CONFIG = {"b": {"name": "b", "description": "b"}}

async def setup():
    await create_pool()
    await initialize_database()
    async with get_db_connection() as conn:
        # Insert 10,000 dummy boards
        data = []
        for i in range(10000):
            data.append((f"board{i}", f"name{i}", f"desc{i}", i % 2, '{"img":"1","link":"2"}'))

        await conn.executemany(
            "INSERT OR IGNORE INTO Boards (board_id, name, description, is_approved, banner_data) VALUES (?, ?, ?, ?, ?)",
            data
        )
        await conn.commit()

async def baseline():
    import copy
    global BOARD_CONFIG
    local_config = copy.deepcopy(BOARD_CONFIG)

    start = time.perf_counter()
    async with get_db_connection() as conn:
        async with conn.execute(
            "SELECT board_id, name, description FROM Boards WHERE is_approved = 1"
        ) as cursor:
            async for row in cursor:
                bid, bname, bdesc = row
                if bid not in local_config:
                    local_config[bid] = {"name": bname, "description": bdesc}

    async with get_db_connection() as conn:
        async with conn.execute("SELECT board_id, banner_data FROM Boards") as cursor:
            async for row in cursor:
                bid, bdata = row
                if bid in local_config and bdata:
                    try:
                        local_config[bid]["banner_data"] = json.loads(bdata)
                    except Exception:
                        pass
    end = time.perf_counter()
    return end - start, local_config

async def optimized():
    import copy
    global BOARD_CONFIG
    local_config = copy.deepcopy(BOARD_CONFIG)

    start = time.perf_counter()
    async with get_db_connection() as conn:
        async with conn.execute(
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
    await setup()

    # Warmup
    await baseline()
    await optimized()

    t1_sum = 0
    t2_sum = 0
    for _ in range(5):
        t1, c1 = await baseline()
        t2, c2 = await optimized()
        t1_sum += t1
        t2_sum += t2
        assert len(c1) == len(c2)

    print(f"Baseline: {t1_sum/5:.4f}s")
    print(f"Optimized: {t2_sum/5:.4f}s")

if __name__ == '__main__':
    asyncio.run(main())
