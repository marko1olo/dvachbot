import sqlite3
import json

db_path = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'

try:
    conn = sqlite3.connect(db_path, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row['name'] for row in cursor.fetchall()]
    print("Tables:", tables)
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [row['name'] for row in cursor.fetchall()]
        print(f"{table} columns: {columns}")

except Exception as e:
    print("Error:", e)
