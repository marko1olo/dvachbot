import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import sqlite3
import tempfile

sys.path.insert(0, r'C:\Users\danat\Desktop\dvachbot')

import common.config
import common.db_pool
import common.database

async def verify_fresh_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        temp_db_path = tmp.name

    print(f"Testing fresh database initialization at {temp_db_path}...", flush=True)

    common.config.DB_NAME = temp_db_path
    common.db_pool.DB_NAME = temp_db_path
    common.database.DB_NAME = temp_db_path

    await common.db_pool.close_pool()
    
    await common.database.initialize_database()
    print("initialize_database() completed successfully.", flush=True)

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = set(r[0] for r in cur.fetchall())
    print(f"Total tables created in fresh DB: {len(tables)}", flush=True)
    print("Tables list:", sorted(list(tables)), flush=True)

    required_tables = {'Posts', 'PostFiles', 'Users', 'Boards', 'FileRegistry', 'FileTagsFTS', 'Threads', 'DeliveryQueue'}
    missing_tables = required_tables - tables
    print(f"Missing required tables: {missing_tables}", flush=True)
    assert not missing_tables, f"Missing tables: {missing_tables}"

    cur.execute("PRAGMA table_info(PostFiles);")
    columns = {r[1]: r[2] for r in cur.fetchall()}
    print("PostFiles columns:", columns, flush=True)
    assert 'post_num' in columns
    assert 'original_file_id' in columns
    assert 'thumbnail_file_id' in columns

    cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indices = set(r[0] for r in cur.fetchall())
    print(f"Total indices created in fresh DB: {len(indices)}", flush=True)
    
    required_indices = {'idx_postfiles_orig', 'idx_postfiles_thumb', 'idx_postfiles_post_num'}
    missing_indices = required_indices - indices
    print(f"Missing required indices: {missing_indices}", flush=True)
    assert not missing_indices, f"Missing indices: {missing_indices}"

    conn.close()
    await common.db_pool.close_pool()

    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
        except:
            pass

    print("✅ FRESH DB SCHEMA VERIFICATION PASSED PERFECTLY!", flush=True)

if __name__ == "__main__":
    asyncio.run(verify_fresh_db())
