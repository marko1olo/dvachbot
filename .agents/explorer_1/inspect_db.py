import sqlite3
import os

db_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT type, name, sql FROM sqlite_master WHERE name LIKE '%PostFile%' OR name LIKE '%Post%'")
    for r in c.fetchall():
        print(r)
