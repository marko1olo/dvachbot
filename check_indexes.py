import sqlite3
import os

db_path = "dvach_bot.db"
if not os.path.exists(db_path):
    print("No DB found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

def print_indexes(table):
    cur.execute("SELECT * FROM pragma_index_list(?)", (table,))
    indexes = cur.fetchall()
    if not indexes:
        print(f"No indexes for {table}")
        return
    print(f"Indexes for {table}:")

    cur.execute(f"""
        SELECT m.name, i.name
        FROM pragma_index_list(?) m, pragma_index_info(m.name) i
    """, (table,))

    idx_columns = {idx[1]: [] for idx in indexes}
    for row in cur.fetchall():
        if row[0] in idx_columns:
            idx_columns[row[0]].append(row[1])

    for idx in indexes:
        idx_name = idx[1]
        print(f"  - {idx_name}: {idx_columns[idx_name]}")

print_indexes("Posts")
print_indexes("PostCopies")
print_indexes("ChannelCopies")
print_indexes("FileMirrors")
print_indexes("ImportRefMap")
