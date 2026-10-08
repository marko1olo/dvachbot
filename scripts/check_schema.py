import sqlite3
db_uri = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'
conn = sqlite3.connect(db_uri, uri=True)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for t in tables:
    print('Table:', t[0])
    cursor.execute(f'PRAGMA table_info({t[0]})')
    cols = cursor.fetchall()
    for c in cols:
        print(f'  {c[1]} ({c[2]})')
