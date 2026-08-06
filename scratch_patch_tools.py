import ast
import os

def patch_file(path, old_str, new_str):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        c = f.read()
    if old_str in c:
        if 'import contextlib' not in c:
            c = 'import contextlib\n' + c
        c = c.replace(old_str, new_str)
        try:
            ast.parse(c)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(c)
            print(f'Patched {path}')
        except Exception as e:
            print(f'Error patching {path}: {e}')
    else:
        print(f'Pattern not found in {path}')

patch_file(r'C:\Users\danat\Desktop\dvachbot\check_db.py', "conn = sqlite3.connect('data/bot_database.db')", "with contextlib.closing(sqlite3.connect('data/bot_database.db')) as conn:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\check_indexes.py', "conn = sqlite3.connect(db_path)", "with contextlib.closing(sqlite3.connect(db_path)) as conn:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\check_large_tables.py', "conn = sqlite3.connect('dvach_bot.db')", "with contextlib.closing(sqlite3.connect('dvach_bot.db')) as conn:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\dbchecker.py', "conn = sqlite3.connect(db_path, timeout=15.0)", "with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\fast_cleanup_orphans.py', "conn = sqlite3.connect('dvach_bot.db')", "with contextlib.closing(sqlite3.connect('dvach_bot.db')) as conn:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\get_schemas.py', "con = sqlite3.connect('dvach_bot.db')", "with contextlib.closing(sqlite3.connect('dvach_bot.db')) as con:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\tools\selfcheck.py', "con = sqlite3.connect(dbp)", "with contextlib.closing(sqlite3.connect(dbp)) as con:")
patch_file(r'C:\Users\danat\Desktop\dvachbot\tools\smoketest.py', "con = sqlite3.connect(D.DB_NAME)", "with contextlib.closing(sqlite3.connect(D.DB_NAME)) as con:")
