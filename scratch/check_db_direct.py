import sqlite3
import sys

db_name = None
with open('common/database.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('DB_NAME = '):
            db_name = line.split('=')[1].strip().strip('\'\"')
            break

if not db_name:
    print('Could not find DB_NAME')
    sys.exit(1)

print('DB_NAME:', db_name)
db = sqlite3.connect(db_name)
cur = db.cursor()
cur.execute('PRAGMA integrity_check;')
print('Integrity:', cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM Posts;')
print('Posts count:', cur.fetchone()[0])

try:
    cur.execute('SELECT COUNT(*) FROM PostFiles;')
    print('PostFiles count:', cur.fetchone()[0])
    
    cur.execute('PRAGMA index_list(PostFiles);')
    print('PostFiles Indices:', cur.fetchall())
except Exception as e:
    print('PostFiles error:', e)
