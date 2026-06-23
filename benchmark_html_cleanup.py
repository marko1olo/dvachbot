import asyncio
import time
import json
import sqlite3
from bs4 import BeautifulSoup
import aiosqlite

async def setup_db(db_path, num_rows):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS Posts (
            post_num INTEGER PRIMARY KEY,
            content TEXT
        )
        """)
        await conn.execute("DELETE FROM Posts")

        rows = []
        for i in range(num_rows):
            content = json.dumps({"text": f"some text with <img src='test.jpg'> tag {i}"})
            rows.append((i, content))

        await conn.executemany("INSERT INTO Posts (post_num, content) VALUES (?, ?)", rows)
        await conn.commit()

async def run_original(db_path):
    count = 0
    async with aiosqlite.connect(db_path) as conn:
        query = "SELECT post_num, content FROM Posts WHERE content LIKE '%<img%'"
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()

        await conn.execute("BEGIN IMMEDIATE")
        start = time.time()
        for row in rows:
            post_num, raw_content = row
            try:
                content = json.loads(raw_content)
                text = content.get('text', '')

                if '<img' in text or '<IMG' in text:
                    soup = BeautifulSoup(text, "html.parser")
                    images = soup.find_all('img')

                    if images:
                        for img in images:
                            img.decompose()

                        content['text'] = str(soup)
                        new_json = json.dumps(content)

                        await conn.execute(
                            "UPDATE Posts SET content = ? WHERE post_num = ?",
                            (new_json, post_num)
                        )
                        count += 1
            except Exception:
                continue
        await conn.execute("COMMIT")
        end = time.time()
    return end - start, count

async def run_optimized(db_path):
    count = 0
    async with aiosqlite.connect(db_path) as conn:
        query = "SELECT post_num, content FROM Posts WHERE content LIKE '%<img%'"
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()

        await conn.execute("BEGIN IMMEDIATE")
        start = time.time()
        updates = []
        for row in rows:
            post_num, raw_content = row
            try:
                content = json.loads(raw_content)
                text = content.get('text', '')

                if '<img' in text or '<IMG' in text:
                    soup = BeautifulSoup(text, "html.parser")
                    images = soup.find_all('img')

                    if images:
                        for img in images:
                            img.decompose()

                        content['text'] = str(soup)
                        new_json = json.dumps(content)

                        updates.append((new_json, post_num))
                        count += 1
            except Exception:
                continue

        if updates:
            await conn.executemany(
                "UPDATE Posts SET content = ? WHERE post_num = ?",
                updates
            )
        await conn.execute("COMMIT")
        end = time.time()
    return end - start, count

async def main():
    db_path = "test_perf.db"
    num_rows = 1000

    print(f"Setting up DB with {num_rows} rows...")
    await setup_db(db_path, num_rows)
    print("Running original...")
    t_orig, c_orig = await run_original(db_path)
    print(f"Original took {t_orig:.4f}s for {c_orig} updates")

    await setup_db(db_path, num_rows)
    print("Running optimized...")
    t_opt, c_opt = await run_optimized(db_path)
    print(f"Optimized took {t_opt:.4f}s for {c_opt} updates")

    if t_opt < t_orig:
        print(f"Improvement: {(t_orig - t_opt) / t_orig * 100:.2f}% faster")
    else:
        print(f"No improvement.")

if __name__ == '__main__':
    asyncio.run(main())
