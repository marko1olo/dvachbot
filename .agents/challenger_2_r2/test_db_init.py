import sys
import io
import asyncio
import os
import sqlite3
import tempfile

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure dvachbot root is in sys.path
sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

import common.config
import common.database

async def run_verification():
    # Create temp db file path
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, "clean_test.db")
    print(f"Testing database initialization on clean DB: {test_db_path}")

    # Override DB_NAME
    common.config.DB_NAME = test_db_path
    common.database.DB_NAME = test_db_path

    try:
        # Step 2 & 3: Run initialize_database
        await common.database.initialize_database()
        print("initialize_database() completed successfully.")

        # Verify tables and indices
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()
        
        # Check PostFiles table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='PostFiles';")
        table_res = cursor.fetchone()
        assert table_res is not None, "PostFiles table missing!"
        print("✅ PostFiles table confirmed created.")

        # Check PostFiles indices
        expected_indices = ['idx_postfiles_orig', 'idx_postfiles_thumb', 'idx_postfiles_post_num']
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indices = [row[0] for row in cursor.fetchall()]

        for idx in expected_indices:
            assert idx in indices, f"Index {idx} missing!"
            print(f"✅ Index {idx} confirmed created.")

        conn.close()
        print("ALL DB INIT CHECKS PASSED SUCCESSFULLY.")
    except Exception as e:
        print(f"❌ ERROR DURING DB INIT VERIFICATION: {e}")
        raise e
    finally:
        if os.path.exists(test_db_path):
            try:
                os.remove(test_db_path)
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(run_verification())
