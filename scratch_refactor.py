import re
import ast
import os

path = r'C:\Users\danat\Desktop\dvachbot\common\database.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

def refactor_func_to_cursor(code, func_name, db_var='db'):
    pattern = rf'(async def {func_name}\({db_var}\):)(.*?)(?=\nasync def |\ndef |\nclass |\Z)'
    match = re.search(pattern, code, re.DOTALL)
    if not match:
        print(f'Could not find {func_name}')
        return code
    header = match.group(1)
    body = match.group(2)
    
    indented_body_lines = []
    for line in body.splitlines(True):
        if line.strip():
            indented_body_lines.append('    ' + line)
        else:
            indented_body_lines.append(line)
    
    new_body = ''.join(indented_body_lines)
    new_body = new_body.replace(f'await {db_var}.execute(', 'await cursor.execute(')
    new_body = new_body.replace(f'await {db_var}.executemany(', 'await cursor.executemany(')
    
    replacement = f'{header}\n    async with {db_var}.cursor() as cursor:{new_body}'
    return code[:match.start()] + replacement + code[match.end():]

# Refactor schema functions
text = refactor_func_to_cursor(text, '_create_tables', 'db')
text = refactor_func_to_cursor(text, '_apply_migrations', 'db')
text = refactor_func_to_cursor(text, '_create_indices', 'db')
text = refactor_func_to_cursor(text, '_create_triggers', 'db')
text = refactor_func_to_cursor(text, '_insert_initial_data', 'db')

# Add missing high-traffic indices in _create_indices
additional_indices = '''        # High-traffic query filter indices
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON Users(user_id);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_threads_board_id ON Threads(board_id);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON UserAlerts(created_at);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_modqueue_file_id ON ModQueue(file_id);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_mediareposts_file_unique_id ON MediaReposts(file_unique_id);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_sha256 ON FileRegistry(sha256);")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_bannedhashes_hash_value ON BannedHashes(hash_value);")
'''

idx_pos = text.find('async def _create_triggers')
if idx_pos != -1:
    text = text[:idx_pos] + additional_indices + '\n' + text[idx_pos:]

# Refactor register_file_owners_batch
text = text.replace(
    'await conn.executemany(\n                "INSERT OR IGNORE INTO FileOwners (file_id, bot_id) VALUES (?, ?)",\n                owner_pairs\n            )',
    'async with conn.cursor() as cursor:\n                await cursor.executemany(\n                    "INSERT OR IGNORE INTO FileOwners (file_id, bot_id) VALUES (?, ?)",\n                    owner_pairs\n                )'
)

# Refactor DBConnection.__aenter__
old_aenter = '''        try: await self.conn.execute('PRAGMA journal_mode=WAL')
        except: pass
        try: await self.conn.execute('PRAGMA synchronous=NORMAL')
        except: pass
        try: await self.conn.execute('PRAGMA busy_timeout=15000')
        except: pass
        try: await self.conn.execute('PRAGMA wal_autocheckpoint=1000')
        except: pass
        await self.conn.execute("PRAGMA busy_timeout = 60000;")
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous = NORMAL;")
        await self.conn.execute("PRAGMA temp_store = MEMORY;")
        await self.conn.execute("PRAGMA mmap_size = 268435456;")
        await self.conn.execute("PRAGMA cache_size = -60000;")
        await self.conn.execute("PRAGMA foreign_keys = ON;")'''

new_aenter = '''        async with self.conn.cursor() as cursor:
            try: await cursor.execute('PRAGMA journal_mode=WAL')
            except: pass
            try: await cursor.execute('PRAGMA synchronous=NORMAL')
            except: pass
            try: await cursor.execute('PRAGMA busy_timeout=15000')
            except: pass
            try: await cursor.execute('PRAGMA wal_autocheckpoint=1000')
            except: pass
            await cursor.execute("PRAGMA busy_timeout = 60000;")
            await cursor.execute("PRAGMA journal_mode=WAL;")
            await cursor.execute("PRAGMA synchronous = NORMAL;")
            await cursor.execute("PRAGMA temp_store = MEMORY;")
            await cursor.execute("PRAGMA mmap_size = 268435456;")
            await cursor.execute("PRAGMA cache_size = -60000;")
            await cursor.execute("PRAGMA foreign_keys = ON;")'''

text = text.replace(old_aenter, new_aenter)

# Refactor cleanup_old_posts_from_db
old_cleanup = '''    try:
        # isolation_level=None для соответствия архитектуре
        with sqlite3.connect(DB_NAME, timeout=30.0, isolation_level=None) as con:'''

new_cleanup = '''    con = sqlite3.connect(DB_NAME, timeout=30.0, isolation_level=None)
    try:
        with con:'''

text = text.replace(old_cleanup, new_cleanup)

old_cleanup_end = '''            # 7. Очистка карты импорта (удаляем маппинг для завершенных задач)
            _cleanup_import_map(con)

    except Exception as e:
        print(f"⛔ DB Cleanup Critical Error: {e}")'''

new_cleanup_end = '''            # 7. Очистка карты импорта (удаляем маппинг для завершенных задач)
            _cleanup_import_map(con)

    except Exception as e:
        print(f"⛔ DB Cleanup Critical Error: {e}")
    finally:
        con.close()'''

text = text.replace(old_cleanup_end, new_cleanup_end)

# Verify AST
ast.parse(text)
print('AST validation SUCCESSFUL!')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print('common/database.py written successfully!')
