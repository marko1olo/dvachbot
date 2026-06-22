import asyncio
import time
import aiosqlite

async def benchmark():
    conn = await aiosqlite.connect(":memory:")

    # Setup
    await conn.execute("CREATE TABLE FileRegistry (sha256 TEXT, tags TEXT)")
    dummy_sha = "testsha"
    dummy_tags = "tag1, tag2"
    await conn.execute("INSERT INTO FileRegistry (sha256, tags) VALUES (?, ?)", (dummy_sha, dummy_tags))
    await conn.commit()

    # Uncached
    start = time.perf_counter()
    for _ in range(10000):
        async with conn.execute("SELECT tags FROM FileRegistry WHERE sha256 = ? AND tags IS NOT NULL AND tags != '' LIMIT 1", (dummy_sha,)) as cursor:
            row = await cursor.fetchone()
            if row:
                tags = row[0]
    uncached_time = time.perf_counter() - start

    # Cached setup
    cache = {dummy_sha: dummy_tags}

    # Cached
    start = time.perf_counter()
    for _ in range(10000):
        tags = cache.get(dummy_sha)
        if not tags:
            async with conn.execute("SELECT tags FROM FileRegistry WHERE sha256 = ? AND tags IS NOT NULL AND tags != '' LIMIT 1", (dummy_sha,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    tags = row[0]
                    cache[dummy_sha] = tags
    cached_time = time.perf_counter() - start

    print(f"Uncached time (10k DB lookups): {uncached_time:.4f}s")
    print(f"Cached time (10k cache lookups): {cached_time:.4f}s")
    print(f"Improvement factor: {uncached_time / cached_time:.2f}x")

asyncio.run(benchmark())
