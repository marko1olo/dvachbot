import sys
import asyncio
import os
import tempfile
import sqlite3

# Reconfigure encoding for Windows console if needed
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

db_path = os.path.join(tempfile.gettempdir(), 'test_fresh_verification.db')
if os.path.exists(db_path):
    os.remove(db_path)

import common.config
common.config.DB_NAME = db_path

from common.database import initialize_database

async def main():
    print("Running initialize_database() on fresh DB...")
    await initialize_database()
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PostFiles'")
    tables = cur.fetchall()
    print("PostFiles Table Found:", tables)
    assert len(tables) == 1, "PostFiles table missing!"
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='PostFiles'")
    indices = cur.fetchall()
    print("PostFiles Indices Found:", indices)
    assert len(indices) >= 3, f"Expected at least 3 indices, found {len(indices)}"
    
    # Check pragma table_info
    cur.execute("PRAGMA table_info(PostFiles)")
    columns = cur.fetchall()
    print("PostFiles Schema Columns:")
    for col in columns:
        print("  ", col)
        
    conn.close()
    print("FRESH DB VERIFICATION PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    asyncio.run(main())
