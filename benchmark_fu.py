import asyncio
import aiosqlite
import time
import os

DB_NAME = "dvach_bot.db"

async def setup_db():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE MirrorQueue (file_id TEXT)")
        await db.execute("CREATE TABLE PendingHF (file_id TEXT)")

        # Insert 100,000 rows into each table, mix of matching and non-matching
        data = [("AgAC123",), ("BQAC123",), ("CQAC123",), ("Other123",)] * 25000
        await db.executemany("INSERT INTO MirrorQueue (file_id) VALUES (?)", data)
        await db.executemany("INSERT INTO PendingHF (file_id) VALUES (?)", data)
        await db.commit()

async def run_baseline():
    async with aiosqlite.connect(DB_NAME) as db:
        start_time = time.perf_counter()
        patterns = ['AgAC%', 'BQAC%', 'CQAC%']
        for p in patterns:
            await db.execute("DELETE FROM MirrorQueue WHERE file_id LIKE ?", (p,))
            await db.execute("DELETE FROM PendingHF WHERE file_id LIKE ?", (p,))
        await db.commit()
        return time.perf_counter() - start_time

async def run_optimized():
    async with aiosqlite.connect(DB_NAME) as db:
        start_time = time.perf_counter()
        patterns = ['AgAC%', 'BQAC%', 'CQAC%']
        query_mirror = "DELETE FROM MirrorQueue WHERE file_id LIKE ? OR file_id LIKE ? OR file_id LIKE ?"
        await db.execute(query_mirror, patterns)
        query_hf = "DELETE FROM PendingHF WHERE file_id LIKE ? OR file_id LIKE ? OR file_id LIKE ?"
        await db.execute(query_hf, patterns)
        await db.commit()
        return time.perf_counter() - start_time

async def main():
    print("Setting up baseline DB...")
    await setup_db()
    print("Running baseline...")
    baseline_time = await run_baseline()

    print("Setting up optimized DB...")
    await setup_db()
    print("Running optimized...")
    optimized_time = await run_optimized()

    print(f"Baseline: {baseline_time:.4f}s")
    print(f"Optimized: {optimized_time:.4f}s")
    if optimized_time > 0:
        print(f"Improvement: {(baseline_time - optimized_time) / baseline_time * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
