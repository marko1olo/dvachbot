import asyncio
import time
import json
import re
import aiosqlite

async def mock_fix(text, id_map):
    return text + " fixed", 123

async def run_baseline(conn, chunk, id_map):
    await conn.execute("BEGIN")
    for p_data in chunk:
        new_id = id_map[p_data["old_id"]]
        original_text = p_data["text"]
        if not original_text: continue
        fixed_text, reply_to_id = await mock_fix(original_text, id_map)
        if fixed_text != original_text or reply_to_id is not None:
            new_content_obj = {"text": fixed_text, "files": p_data["files"], "type": "files" if p_data["files"] else "text"}
            await conn.execute("UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
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
                await conn.executemany(
                    "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                    backlink_pairs
                )
    await conn.commit()

async def run_optimized(conn, chunk, id_map):
    await conn.execute("BEGIN")
    update_params = []
    all_backlink_pairs = []
    for p_data in chunk:
        new_id = id_map[p_data["old_id"]]
        original_text = p_data["text"]
        if not original_text: continue
        fixed_text, reply_to_id = await mock_fix(original_text, id_map)
        if fixed_text != original_text or reply_to_id is not None:
            new_content_obj = {"text": fixed_text, "files": p_data["files"], "type": "files" if p_data["files"] else "text"}
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
        await conn.executemany("UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?", update_params)
    if all_backlink_pairs:
        await conn.executemany("INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)", all_backlink_pairs)
    await conn.commit()

async def main():
    async with aiosqlite.connect(':memory:') as conn:
        await conn.execute("CREATE TABLE posts (post_num INTEGER PRIMARY KEY, content TEXT, reply_to_post_num INTEGER)")
        await conn.execute("CREATE TABLE Backlinks (target_post_num INTEGER, source_post_num INTEGER, UNIQUE(target_post_num, source_post_num))")
        await conn.commit()

        N = 5000
        chunk = []
        id_map = {}
        for i in range(N):
            chunk.append({"old_id": i, "text": f"hello world >>{i-1} >>{i-2}", "files": []})
            id_map[i] = i
            await conn.execute("INSERT INTO posts (post_num, content, reply_to_post_num) VALUES (?, ?, ?)", (i, "{}", None))
        await conn.commit()

        start = time.perf_counter()
        await run_baseline(conn, chunk, id_map)
        t_baseline = time.perf_counter() - start

        # Reset
        await conn.execute("DELETE FROM posts")
        await conn.execute("DELETE FROM Backlinks")
        for i in range(N):
            await conn.execute("INSERT INTO posts (post_num, content, reply_to_post_num) VALUES (?, ?, ?)", (i, "{}", None))
        await conn.commit()

        start = time.perf_counter()
        await run_optimized(conn, chunk, id_map)
        t_optimized = time.perf_counter() - start

        print(f"Baseline: {t_baseline:.4f}s")
        print(f"Optimized: {t_optimized:.4f}s")
        print(f"Speedup: {t_baseline / t_optimized:.2f}x")

asyncio.run(main())
