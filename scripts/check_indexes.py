import sqlite3
import os

db_path = "dvach_bot.db"
if not os.path.exists(db_path):
    print("No DB found")
    exit()

conn = sqlite3.connect(db_path, timeout=15.0)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=15000;")
cur = conn.cursor()

def print_indexes(table):
    cur.execute("SELECT * FROM pragma_index_list(?)", (table,))
    indexes = cur.fetchall()
    if not indexes:
        print(f"No indexes for {table}")
        return
    print(f"Indexes for {table}:")

    cur = conn.cursor()
    cur.execute("""
        SELECT
            name
        FROM sqlite_master
        WHERE type = 'index'
    """)
        WHERE type = 'index'
    """)

    idx_columns = {idx[1]: [] for idx in indexes}
    for row in cur.fetchall():
        if row[0] in idx_columns:
            # mock for row[1] since we only get name
            pass

    for idx in indexes:
        idx_name = idx[1]
        print(f"  - {idx_name}: {idx_columns.get(idx_name, [])}")

print_indexes("Posts")
print_indexes("PostCopies")
print_indexes("ChannelCopies")
print_indexes("FileMirrors")
print_indexes("ImportRefMap")
