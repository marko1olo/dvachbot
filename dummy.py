import sqlite3
import os

conn = sqlite3.connect(":memory:")
cur = conn.cursor()
cur.execute("CREATE TABLE Posts (id INTEGER PRIMARY KEY, title TEXT)")
cur.execute("CREATE INDEX idx_posts_title ON Posts(title)")

def print_indexes(table):
    cur.execute("SELECT * FROM pragma_index_list(?)", (table,))
    indexes = cur.fetchall()
    if not indexes:
        print(f"No indexes for {table}")
        return
    print(f"Indexes for {table}:")
    for idx in indexes:
        idx_name = idx[1]
        cur.execute("SELECT * FROM pragma_index_info(?)", (idx_name,))
        columns = [c[2] for c in cur.fetchall()]
        print(f"  - {idx_name}: {columns}")

print_indexes("Posts")
