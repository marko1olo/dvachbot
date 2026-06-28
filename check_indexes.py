import sqlite3
import os

db_path = "dvach_bot.db"
if not os.path.exists(db_path):
    print("No DB found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

def print_indexes(table):
    cur.execute("""
        SELECT il.name, ii.name
        FROM pragma_index_list(?) il, pragma_index_info(il.name) ii
    """, (table,))
    rows = cur.fetchall()
    if not rows:
        print(f"No indexes for {table}")
        return

    print(f"Indexes for {table}:")
    indexes = {}
    for idx_name, col_name in rows:
        if idx_name not in indexes:
            indexes[idx_name] = []
        indexes[idx_name].append(col_name)

    for idx_name, columns in indexes.items():
        print(f"  - {idx_name}: {columns}")

print_indexes("Posts")
print_indexes("PostCopies")
print_indexes("ChannelCopies")
print_indexes("FileMirrors")
print_indexes("ImportRefMap")
