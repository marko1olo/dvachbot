import asyncio
import time
import json
import re
import aiosqlite

class MockImporter:
    async def _fix_content_links_and_find_reply(self, original_text, id_map):
        return original_text + " (fixed) >>10", 10

async def setup_db():
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("CREATE TABLE posts (post_num INTEGER PRIMARY KEY, content TEXT, reply_to_post_num INTEGER)")
    await conn.execute("CREATE TABLE Backlinks (target_post_num INTEGER, source_post_num INTEGER, UNIQUE(target_post_num, source_post_num))")

    # Insert some mock data
    for i in range(1, 10001):
        await conn.execute("INSERT INTO posts (post_num, content) VALUES (?, ?)", (i, "old content"))
    await conn.commit()
    return conn

async def run_benchmark():
    num_posts = 5000
    chunk_size = 500
    prepared_posts = [{"old_id": i, "text": f"some text {i}", "files": []} for i in range(1, num_posts + 1)]
    id_map = {i: i for i in range(1, num_posts + 1)}

    # Old approach
    conn1 = await setup_db()
    importer = MockImporter()

    start1 = time.time()
    for i in range(0, len(prepared_posts), chunk_size):
        await conn1.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]
        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text: continue
            fixed_text, reply_to_id = await importer._fix_content_links_and_find_reply(original_text, id_map)
            if fixed_text != original_text or reply_to_id is not None:
                new_content_obj = {"text": fixed_text, "files": p_data["files"], "type": "text"}
                await conn1.execute("UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                                 (json.dumps(new_content_obj), reply_to_id, new_id))

                backlink_pairs = []
                if reply_to_id:
                    backlink_pairs.append((reply_to_id, new_id))

                refs = set(re.findall(r'>>(\d+)', fixed_text))
                for ref in refs:
                    try:
                        target_id = int(ref)
                        if target_id != new_id:
                            backlink_pairs.append((target_id, new_id))
                    except: pass

                if backlink_pairs:
                    await conn1.executemany(
                        "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                        backlink_pairs
                    )
        await conn1.commit()
    time1 = time.time() - start1

    # New approach
    conn2 = await setup_db()
    start2 = time.time()
    for i in range(0, len(prepared_posts), chunk_size):
        await conn2.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]

        update_params = []
        all_backlink_pairs = []

        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text: continue
            fixed_text, reply_to_id = await importer._fix_content_links_and_find_reply(original_text, id_map)
            if fixed_text != original_text or reply_to_id is not None:
                new_content_obj = {"text": fixed_text, "files": p_data["files"], "type": "text"}
                update_params.append((json.dumps(new_content_obj), reply_to_id, new_id))

                if reply_to_id:
                    all_backlink_pairs.append((reply_to_id, new_id))

                refs = set(re.findall(r'>>(\d+)', fixed_text))
                for ref in refs:
                    try:
                        target_id = int(ref)
                        if target_id != new_id:
                            all_backlink_pairs.append((target_id, new_id))
                    except: pass

        if update_params:
            await conn2.executemany("UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?", update_params)

        if all_backlink_pairs:
            await conn2.executemany(
                "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                all_backlink_pairs
            )

        await conn2.commit()
    time2 = time.time() - start2

    print(f"Old Approach: {time1:.4f} seconds")
    print(f"New Approach: {time2:.4f} seconds")
    print(f"Speedup: {time1/time2:.2f}x")

    await conn1.close()
    await conn2.close()

asyncio.run(run_benchmark())
