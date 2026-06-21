import asyncio
import time
import json
import sqlite3
import re

# Mock classes to mimic the real behavior
class MockConn:
    def __init__(self, use_batching):
        self.use_batching = use_batching
        self.update_count = 0
        self.backlink_count = 0

    async def execute(self, query, params=None):
        if "UPDATE" in query:
            self.update_count += 1
        pass

    async def executemany(self, query, params):
        if "UPDATE" in query:
            self.update_count += len(params)
        elif "Backlinks" in query:
            self.backlink_count += len(params)
        pass

    async def commit(self):
        pass

class Importer:
    async def _fix_content_links_and_find_reply(self, text, id_map):
        return text + " fixed", 123

async def benchmark_old(chunk_size, num_posts):
    conn = MockConn(False)
    importer = Importer()
    id_map = {i: i for i in range(num_posts)}
    prepared_posts = [{"old_id": i, "text": f"post {i} >>{max(0, i-1)}", "files": []} for i in range(num_posts)]

    start_time = time.time()

    for i in range(0, len(prepared_posts), chunk_size):
        await conn.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]
        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text: continue
            fixed_text, reply_to_id = await importer._fix_content_links_and_find_reply(original_text, id_map)
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

    end_time = time.time()
    return end_time - start_time, conn

async def benchmark_new(chunk_size, num_posts):
    conn = MockConn(True)
    importer = Importer()
    id_map = {i: i for i in range(num_posts)}
    prepared_posts = [{"old_id": i, "text": f"post {i} >>{max(0, i-1)}", "files": []} for i in range(num_posts)]

    start_time = time.time()

    for i in range(0, len(prepared_posts), chunk_size):
        await conn.execute("BEGIN")
        chunk = prepared_posts[i : i + chunk_size]

        update_params = []
        all_backlink_pairs = []

        for p_data in chunk:
            new_id = id_map[p_data["old_id"]]
            original_text = p_data["text"]
            if not original_text: continue
            fixed_text, reply_to_id = await importer._fix_content_links_and_find_reply(original_text, id_map)
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
            await conn.executemany(
                "UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                update_params
            )
        if all_backlink_pairs:
            await conn.executemany(
                "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                all_backlink_pairs
            )

        await conn.commit()

    end_time = time.time()
    return end_time - start_time, conn

async def main():
    old_time, _ = await benchmark_old(20, 100000)
    new_time, _ = await benchmark_new(20, 100000)

    print(f"Old approach took: {old_time:.4f}s")
    print(f"New approach took: {new_time:.4f}s")
    print(f"Improvement: {(old_time - new_time) / old_time * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
