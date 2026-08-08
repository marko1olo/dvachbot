import asyncio
import os
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_clean_init():
    test_db = os.path.join(os.path.dirname(__file__), "test_clean_init_db.db")
    if os.path.exists(test_db):
        os.remove(test_db)

    import common.config
    import common.database
    import common.db_pool

    common.config.DB_NAME = test_db
    common.database.DB_NAME = test_db
    common.db_pool.DB_NAME = test_db

    print(f"Running initialize_database() on clean DB: {test_db}")
    init_failed = False
    error_msg = ""
    try:
        await common.database.initialize_database()
    except SystemExit as e:
        init_failed = True
        error_msg = f"SystemExit: {e}"
    except Exception as e:
        init_failed = True
        error_msg = f"Exception: {e}"

    if os.path.exists(test_db):
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        print("Tables created on clean DB:", sorted(tables))
        print("Is PostFiles in tables?", 'PostFiles' in tables)
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = [r[0] for r in cur.fetchall()]
        print("Indexes created on clean DB count:", len(indexes))
        
        conn.close()
        try:
            os.remove(test_db)
        except Exception:
            pass
    else:
        print("Database file was not created!")

    print(f"Init status: {'FAILED' if init_failed else 'SUCCESS'}")
    if error_msg:
        print("Error details:", error_msg)

if __name__ == "__main__":
    asyncio.run(test_clean_init())
