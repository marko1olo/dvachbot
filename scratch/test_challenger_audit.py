import asyncio
import importlib
import glob
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def run_import_audit():
    print("=" * 60)
    print("TEST 1: Module Import Dry-Run Audit")
    print("=" * 60)
    
    # List all top-level and common/handlers python files
    py_files = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip venv, .git, .agents, __pycache__
        if any(ignored in root for ignored in ['venv', '.git', '.agents', '__pycache__', '.mypy_cache', '.pytest_cache']):
            continue
        for file in files:
            if file.endswith('.py') and not file.startswith('test_') and not file.startswith('bench_'):
                rel_path = os.path.relpath(os.path.join(root, file), PROJECT_ROOT)
                py_files.append(rel_path)

    print(f"Found {len(py_files)} Python files to check.")
    passed = 0
    failed = []

    for rel_path in py_files:
        # Convert path to module name
        mod_name = rel_path.replace(os.sep, '.').rstrip('.py')
        if mod_name.endswith('.__init__'):
            mod_name = mod_name[:-9]
        
        # Skip scratch or test scripts that expect CLI args
        if mod_name.startswith('scratch.') or mod_name in ['create_new_db', 'fix_db']:
            continue
            
        try:
            importlib.import_module(mod_name)
            passed += 1
        except Exception as e:
            failed.append((rel_path, str(e)))

    print(f"Import Audit Result: {passed} passed, {len(failed)} failed.")
    for path, err in failed:
        print(f"  ❌ {path}: {err}")
    return len(failed) == 0, failed

async def run_clean_db_init_audit():
    print("\n" + "=" * 60)
    print("TEST 2: Clean Database Initialization & Migration Audit")
    print("=" * 60)
    
    test_db = os.path.join(PROJECT_ROOT, "scratch", "test_audit_clean_db.db")
    if os.path.exists(test_db):
        try: os.remove(test_db)
        except Exception: pass

    import common.config
    import common.database
    import common.db_pool

    common.config.DB_NAME = test_db
    common.database.DB_NAME = test_db
    common.db_pool.DB_NAME = test_db

    init_success = False
    init_error = None
    try:
        # Wrap initialize_database call
        await common.database.initialize_database()
        init_success = True
    except SystemExit as e:
        init_error = f"SystemExit({e})"
    except Exception as e:
        init_error = str(e)

    postfiles_exists = False
    tables_count = 0
    indexes_count = 0

    if os.path.exists(test_db):
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        tables_count = len(tables)
        postfiles_exists = 'PostFiles' in tables
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = [r[0] for r in cur.fetchall()]
        indexes_count = len(indexes)
        conn.close()
        
        try: os.remove(test_db)
        except Exception: pass

    print(f"Initialization Succeeded: {init_success}")
    if init_error:
        print(f"Initialization Error: {init_error}")
    print(f"Total Tables Created: {tables_count}")
    print(f"PostFiles Table Exists: {postfiles_exists}")
    print(f"Total Indexes Created: {indexes_count}")

    passed = init_success and postfiles_exists
    return passed, {
        "init_success": init_success,
        "init_error": init_error,
        "postfiles_exists": postfiles_exists,
        "tables_count": tables_count,
        "indexes_count": indexes_count
    }

def run_existing_db_indexes_audit():
    print("\n" + "=" * 60)
    print("TEST 3: Existing Database (dvach_bot.db) Indexes & PostFiles Audit")
    print("=" * 60)
    
    db_path = os.path.join(PROJECT_ROOT, "dvach_bot.db")
    if not os.path.exists(db_path):
        print(f"❌ {db_path} does not exist!")
        return False, "File missing"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = [r[0] for r in cur.fetchall()]

    required_tables = ['Posts', 'Users', 'PostFiles', 'DeliveryQueue', 'BroadcastQueue', 'FileRegistry', 'FileTagsFTS']
    missing_tables = [t for t in required_tables if t not in tables]

    required_indexes = [
        'idx_postfiles_orig',
        'idx_postfiles_thumb',
        'idx_postfiles_post_num',
        'idx_deliveryqueue_status_board',
        'idx_broadcastqueue_pending'
    ]
    missing_indexes = [idx for idx in required_indexes if idx not in indexes]

    print(f"Existing DB Tables count: {len(tables)}")
    print(f"Missing required tables: {missing_tables}")
    print(f"Existing DB Indexes count: {len(indexes)}")
    print(f"Missing required indexes: {missing_indexes}")

    conn.close()
    passed = len(missing_tables) == 0 and len(missing_indexes) == 0
    return passed, {"missing_tables": missing_tables, "missing_indexes": missing_indexes}

async def run_all_audits():
    t_start = time.time()
    
    import_ok, import_details = run_import_audit()
    clean_init_ok, clean_init_details = await run_clean_db_init_audit()
    exist_idx_ok, exist_idx_details = run_existing_db_indexes_audit()

    print("\n" + "=" * 60)
    print("AUDIT SUMMARY REPORT")
    print("=" * 60)
    print(f"1. Module Imports Audit: {'PASSED' if import_ok else 'FAILED'}")
    print(f"2. Clean DB Initialization Audit: {'PASSED' if clean_init_ok else 'FAILED'}")
    print(f"3. Existing DB Index Audit: {'PASSED' if exist_idx_ok else 'FAILED'}")
    print(f"Total time elapsed: {time.time() - t_start:.2f}s")
    
    return {
        "import_ok": import_ok,
        "clean_init_ok": clean_init_ok,
        "exist_idx_ok": exist_idx_ok
    }

if __name__ == "__main__":
    asyncio.run(run_all_audits())
