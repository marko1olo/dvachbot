import asyncio
import time
from datetime import datetime

async def test_sitemap_loop():
    start_time = time.time()
    urls = []
    base_url = "http://example.com"
    # Mocking rows directly
    rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(10000)]

    for row in rows:
        bid, tid, ts = row
        date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        urls.append(f"{base_url}/{bid}/res/{tid}.html")

    end_time = time.time()
    print(f"Loop execution time for 10000 iterations: {end_time - start_time} seconds")

    start_time2 = time.time()
    urls2 = []

    # Simulating what happens when we avoid datetime.fromtimestamp inside the loop
    # In SQLite, we can use datetime(last_updated_at, 'unixepoch') to get date directly.
    # But wait, date is not even used in Dubsite_tgach/main.py:1331 urls.append(f"{base_url}/{bid}/res/{tid}.html")
    # Yes, it is assigned but never used!

    for row in rows:
        bid, tid, ts = row
        urls2.append(f"{base_url}/{bid}/res/{tid}.html")

    end_time2 = time.time()
    print(f"Loop execution time without datetime.fromtimestamp: {end_time2 - start_time2} seconds")

asyncio.run(test_sitemap_loop())
