import sqlite3
import os

db_path = "dvach_bot.db"
if not os.path.exists(db_path):
    print("No DB found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

def print_indexes(table):
    cur.execute(f"PRAGMA index_list('{table}')")
    indexes = cur.fetchall()
    if not indexes:
        print(f"No indexes for {table}")
        return
    print(f"Indexes for {table}:")
    for idx in indexes:
        idx_name = idx[1]
        cur.execute(f"PRAGMA index_info('{idx_name}')")
        columns = [c[2] for c in cur.fetchall()]
        print(f"  - {idx_name}: {columns}")

print_indexes("Posts")
print_indexes("PostCopies")
print_indexes("ChannelCopies")
print_indexes("FileMirrors")
print_indexes("ImportRefMap")
