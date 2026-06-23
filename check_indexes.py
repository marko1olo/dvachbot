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

    query = f"""
        SELECT il.name, ii.name
        FROM pragma_index_list('{table}') il
        JOIN pragma_index_info(il.name) ii
        ORDER BY il.seq, ii.seqno;
    """
    cur.execute(query)
    results = cur.fetchall()

    index_columns = {}
    for idx_name, col_name in results:
        index_columns.setdefault(idx_name, []).append(col_name)

    for idx in indexes:
        idx_name = idx[1]
        columns = index_columns.get(idx_name, [])
        print(f"  - {idx_name}: {columns}")

print_indexes("Posts")
print_indexes("PostCopies")
print_indexes("ChannelCopies")
print_indexes("FileMirrors")
print_indexes("ImportRefMap")
