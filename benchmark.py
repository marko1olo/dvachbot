import asyncio
import time
import json
import sqlite3
import aiosqlite

async def setup_db():
    conn = await aiosqlite.connect(':memory:')
    await conn.execute("""
        CREATE TABLE posts (
            post_num INTEGER PRIMARY KEY,
            content TEXT,
            reply_to_post_num INTEGER
        )
    """)
    await conn.execute("""
        CREATE TABLE Backlinks (
            target_post_num INTEGER,
            source_post_num INTEGER,
            UNIQUE(target_post_num, source_post_num)
        )
    """)
    await conn.commit()
    return conn

class MockImporter:
    async def _fix_content_links_and_find_reply(self, text, id_map):
        return text + " fixed", 1

async def run_benchmark():
    conn = await setup_db()

    # Prepare dummy data
    num_posts = 1000
    chunk_size = 20

    prepared_posts = []
    id_map = {}
    for i in range(num_posts):
        old_id = str(i)
        new_id = i + 1
        id_map[old_id] = new_id
        prepared_posts.append({
            "old_id": old_id,
            "text": f"Some text {i} >>{i-1}",
            "files": []
        })
        await conn.execute("INSERT INTO posts (post_num, content, reply_to_post_num) VALUES (?, ?, ?)", (new_id, "{}", None))
    await conn.commit()

    importer = MockImporter()

    print("Running baseline...")
    start_time = time.time()

    import re
    # Unoptimized
    for i in range(0, len(prepared_posts), chunk_size):
        await conn.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]
        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text:
                continue
            fixed_text, reply_to_id = (
                await importer._fix_content_links_and_find_reply(
                    original_text, id_map
                )
            )
            if fixed_text != original_text or reply_to_id is not None:
                new_content_obj = {
                    "text": fixed_text,
                    "files": p_data["files"],
                    "type": "files" if p_data["files"] else "text",
                }
                await conn.execute(
                    "UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                    (json.dumps(new_content_obj), reply_to_id, new_id),
                )

                backlink_pairs = []
                if reply_to_id:
                    backlink_pairs.append((reply_to_id, new_id))

                refs = set(re.findall(r">>(\d+)", fixed_text))
                for ref in refs:
                    try:
                        target_id = int(ref)
                        if target_id != new_id:
                            backlink_pairs.append((target_id, new_id))
                    except:
                        pass

                if backlink_pairs:
                    await conn.executemany(
                        "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                        backlink_pairs,
                    )

        await conn.commit()

    baseline_duration = time.time() - start_time
    print(f"Baseline took: {baseline_duration:.4f}s")

    # Optimized
    print("Running optimized...")
    start_time = time.time()
    for i in range(0, len(prepared_posts), chunk_size):
        await conn.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]

        update_params = []
        all_backlink_pairs = []

        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text:
                continue
            fixed_text, reply_to_id = (
                await importer._fix_content_links_and_find_reply(
                    original_text, id_map
                )
            )
            if fixed_text != original_text or reply_to_id is not None:
                new_content_obj = {
                    "text": fixed_text,
                    "files": p_data["files"],
                    "type": "files" if p_data["files"] else "text",
                }
                update_params.append((json.dumps(new_content_obj), reply_to_id, new_id))

                if reply_to_id:
                    all_backlink_pairs.append((reply_to_id, new_id))

                refs = set(re.findall(r">>(\d+)", fixed_text))
                for ref in refs:
                    try:
                        target_id = int(ref)
                        if target_id != new_id:
                            all_backlink_pairs.append((target_id, new_id))
                    except:
                        pass

        if update_params:
            await conn.executemany(
                "UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                update_params,
            )

        if all_backlink_pairs:
            await conn.executemany(
                "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                all_backlink_pairs,
            )

        await conn.commit()

    optimized_duration = time.time() - start_time
    print(f"Optimized took: {optimized_duration:.4f}s")
    print(f"Improvement: {baseline_duration / optimized_duration:.2f}x")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(run_benchmark())
