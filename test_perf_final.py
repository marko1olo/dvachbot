import asyncio
import time
from datetime import datetime

async def test_baseline():
    start_time = time.time()
    urls = []
    base_url = "http://example.com"
    rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(10000)]

    for row in rows:
        bid, tid, ts = row
        date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        urls.append(f"{base_url}/{bid}/res/{tid}.html")

    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        xml_content.append(f'  <url><loc>{url}</loc></url>')
    xml_content.append('</urlset>')

    end_time = time.time()
    return end_time - start_time

async def test_optimized():
    start_time = time.time()
    base_url = "http://example.com"
    rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(10000)]

    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for row in rows:
        bid, tid, ts = row
        xml_content.append(f'  <url><loc>{base_url}/{bid}/res/{tid}.html</loc></url>')

    xml_content.append('</urlset>')

    end_time = time.time()
    return end_time - start_time

async def main():
    t1 = await test_baseline()
    t2 = await test_optimized()
    print(f"Baseline: {t1} seconds")
    print(f"Optimized: {t2} seconds")
    print(f"Improvement: {t1 / t2:.2f}x faster")

asyncio.run(main())
