import asyncio
import sqlite3
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from common.database import (
    find_post_by_file_id,
    apply_auto_censure,
    get_posts_by_file_ids,
)
from common.db_pool import create_pool, get_pool

async def run_audit():
    print("--- 1. Testing Schema and Index Existence ---")
    conn = sqlite3.connect('dvach_bot.db')
    cur = conn.cursor()
    cur.execute("PRAGMA index_list('PostFiles')")
    indexes = [row[1] for row in cur.fetchall()]
    print("PostFiles indexes:", indexes)
    assert "idx_postfiles_orig" in indexes, "idx_postfiles_orig missing!"
    assert "idx_postfiles_thumb" in indexes, "idx_postfiles_thumb missing!"
    
    print("\n--- 2. Checking Query Plan for PostFiles lookup ---")
    cur.execute("""
        EXPLAIN QUERY PLAN
        SELECT post_num FROM PostFiles 
        WHERE original_file_id = ? OR thumbnail_file_id = ?
    """, ("test_id", "test_id"))
    plan = cur.fetchall()
    print("Query Plan:")
    for p in plan:
        print("  ", p)
    # Confirm MULTI-INDEX OR or INDEX usage
    plan_str = " ".join([str(p) for p in plan])
    assert "USING INDEX" in plan_str, f"Query plan does not use index: {plan_str}"

    print("\n--- 3. Testing Real Database Query Results ---")
    cur.execute("SELECT original_file_id, post_num FROM PostFiles WHERE original_file_id IS NOT NULL AND original_file_id != '' LIMIT 1")
    row = cur.fetchone()
    sample_fid, expected_post_num = row
    print(f"Sample FID: {sample_fid}, Expected Post Num: {expected_post_num}")

    await create_pool()

    # Test find_post_by_file_id
    post = await find_post_by_file_id(sample_fid)
    print("find_post_by_file_id result:", post)
    assert post is not None, "find_post_by_file_id returned None!"
    assert post['post_num'] == expected_post_num, f"Expected post {expected_post_num}, got {post['post_num']}"

    # Test get_posts_by_file_ids
    posts = await get_posts_by_file_ids([sample_fid])
    print(f"get_posts_by_file_ids returned {len(posts)} posts")
    assert len(posts) > 0, "get_posts_by_file_ids returned empty!"
    assert any(p['post_num'] == expected_post_num for p in posts), "Expected post num not found in get_posts_by_file_ids output"

    print("\n--- 4. Checking dry-run core modules import ---")
    import main, delivery_manager, broadcaster, user_manager
    print("All core modules imported successfully.")

    print("\n--- AUDIT VERIFICATION PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    asyncio.run(run_audit())
