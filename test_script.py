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

asyncio.run(test_sitemap_loop())
