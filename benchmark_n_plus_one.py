import asyncio
import time
import sqlite3
import random
import sys

# Create a mock database implementation for benchmarking

async def setup_db():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE Threads (thread_id TEXT, thread_num INTEGER)")

    # Insert dummy data
    for i in range(1000):
        # some match string ID, some match integer NUM
        conn.execute("INSERT INTO Threads VALUES (?, ?)", (str(i), i))

    conn.commit()
    return conn

class MockCursor:
    def __init__(self, conn, query, params=None):
        self.cursor = conn.cursor()
        self.cursor.execute(query, params or ())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.cursor.close()

    async def fetchone(self):
        return self.cursor.fetchone()

    async def fetchall(self):
        return self.cursor.fetchall()

class MockDB:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        return MockCursor(self.conn, query, params)

async def test_n_plus_1(db, user_posts):
    threads_to_delete = []
    start = time.time()

    for p_num in user_posts:
        p_str = str(p_num)
        async with db.execute("SELECT thread_id FROM Threads WHERE thread_id = ? OR thread_num = ?", (p_str, p_num)) as cursor:
            t_row = await cursor.fetchone()
            if t_row:
                threads_to_delete.append(t_row[0])

    end = time.time()
    return end - start, threads_to_delete

async def test_optimized(db, user_posts):
    threads_to_delete = []
    start = time.time()

    if user_posts:
        placeholders = ','.join('?' for _ in user_posts)
        # We need both strings and ints for the query
        str_posts = [str(p) for p in user_posts]
        params = tuple(str_posts + list(user_posts))

        async with db.execute(f"SELECT thread_id FROM Threads WHERE thread_id IN ({placeholders}) OR thread_num IN ({placeholders})", params) as cursor:
            rows = await cursor.fetchall()
            threads_to_delete = [r[0] for r in rows]

    end = time.time()
    return end - start, threads_to_delete

async def main():
    conn = await setup_db()
    db = MockDB(conn)

    # Test with varying sizes
    for size in [10, 50, 100, 500]:
        user_posts = random.sample(range(2000), size) # Some hit, some miss

        t1, r1 = await test_n_plus_1(db, user_posts)
        t2, r2 = await test_optimized(db, user_posts)

        # Verify correctness
        assert set(r1) == set(r2), f"Mismatch: {set(r1)} != {set(r2)}"

        print(f"Size: {size}")
        print(f"N+1 time: {t1:.6f}s")
        print(f"Opt time: {t2:.6f}s")
        print(f"Speedup: {t1/t2:.2f}x\n")

if __name__ == "__main__":
    asyncio.run(main())
