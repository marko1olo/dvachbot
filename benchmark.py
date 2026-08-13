import asyncio
import time
import ujson as json
import random
import os
import re
import aiosqlite

async def setup_and_benchmark():
    if os.path.exists("test_bot.db"):
        os.remove("test_bot.db")

    async with aiosqlite.connect("test_bot.db") as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS ImportQueue (id INTEGER PRIMARY KEY, task_id TEXT, board_id TEXT, original_post_num TEXT, reply_to_original TEXT, content TEXT, author_id INTEGER, stream INTEGER, is_op INTEGER, thread_title TEXT, publish_at REAL)")
        await conn.execute("CREATE TABLE IF NOT EXISTS ImportRefMap (task_id TEXT, original_post_num TEXT, real_post_num TEXT)")

        now = time.time()

        queue_rows = []
        refmap_rows = []
        for i in range(500):
            task_id = f"task_{i // 50}"
            refs = [str(random.randint(1, 500)) for _ in range(5)]
            content = {"text": f"Some text " + " ".join([f">>{r}" for r in refs])}
            queue_rows.append((task_id, "test_board", str(i), str(0), json.dumps(content), 1, 0, 0, "Test", now))
            refmap_rows.append((task_id, str(i), str(i + 10000)))

        await conn.executemany("INSERT INTO ImportQueue (task_id, board_id, original_post_num, reply_to_original, content, author_id, stream, is_op, thread_title, publish_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", queue_rows)
        await conn.executemany("INSERT INTO ImportRefMap (task_id, original_post_num, real_post_num) VALUES (?, ?, ?)", refmap_rows)
        await conn.commit()

        async with conn.execute("SELECT id, task_id, board_id, original_post_num, reply_to_original, content, author_id, stream, is_op, thread_title FROM ImportQueue ORDER BY publish_at ASC, original_post_num ASC") as cursor:
            rows = await cursor.fetchall()

        # 1. Current Benchmark
        start_time = time.time()
        for row in rows:
            (q_id, task_id, board_id, orig_num, reply_to_orig, content_str, author_id, stream, is_op, title) = row
            content = json.loads(content_str)
            text = content.get("text", "")
            refs = re.findall(r"(?:>>|&gt;&gt;)(\d+)", text)
            replacements = {}
            if refs:
                placeholders = ",".join(["?"] * len(refs))
                q_map = f"SELECT original_post_num, real_post_num FROM ImportRefMap WHERE task_id = ? AND original_post_num IN ({placeholders})"
                async with conn.execute(q_map, [task_id] + refs) as map_cur:
                    async for m_row in map_cur:
                        replacements[m_row[0]] = m_row[1]
        end_time = time.time()
        print(f"Current approach (N+1 Query IN clause): {end_time - start_time:.4f} seconds")

        # 2. Benchmark json_each
        start_time = time.time()
        for row in rows:
            (q_id, task_id, board_id, orig_num, reply_to_orig, content_str, author_id, stream, is_op, title) = row
            content = json.loads(content_str)
            text = content.get("text", "")
            refs = re.findall(r"(?:>>|&gt;&gt;)(\d+)", text)
            replacements = {}
            if refs:
                refs_json = json.dumps(refs)
                q_map = "SELECT original_post_num, real_post_num FROM ImportRefMap, json_each(?) WHERE task_id = ? AND original_post_num = json_each.value"
                async with conn.execute(q_map, [refs_json, task_id]) as map_cur:
                    async for m_row in map_cur:
                        replacements[str(m_row[0])] = m_row[1]
        end_time = time.time()
        print(f"json_each inside loop: {end_time - start_time:.4f} seconds")

        # 3. Batched benchmark
        start_time = time.time()
        for i in range(0, len(rows), 10):
            batch = rows[i:i+10]
            task_refs = {}
            parsed_batch = []
            for row in batch:
                (q_id, task_id, board_id, orig_num, reply_to_orig, content_str, author_id, stream, is_op, title) = row
                content = json.loads(content_str)
                text = content.get("text", "")
                refs = re.findall(r"(?:>>|&gt;&gt;)(\d+)", text)
                if refs:
                    if task_id not in task_refs:
                        task_refs[task_id] = set()
                    task_refs[task_id].update(refs)
                parsed_batch.append({"row": row, "content": content, "refs": refs, "task_id": task_id})

            all_replacements = {}
            if task_refs:
                for task_id, refs in task_refs.items():
                    refs_json = json.dumps(list(refs))
                    q_map = "SELECT original_post_num, real_post_num FROM ImportRefMap, json_each(?) WHERE task_id = ? AND original_post_num = json_each.value"
                    async with conn.execute(q_map, [refs_json, task_id]) as map_cur:
                        async for m_row in map_cur:
                            all_replacements[(task_id, str(m_row[0]))] = m_row[1]

            for item in parsed_batch:
                replacements = {}
                for ref in item["refs"]:
                    key = (item["task_id"], ref)
                    if key in all_replacements:
                        replacements[ref] = all_replacements[key]
        end_time = time.time()
        print(f"Batched json_each: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(setup_and_benchmark())
