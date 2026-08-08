import sqlite3
import os
import time

db_path = r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db'
if not os.path.exists(db_path):
    # check fallback paths
    for p in ['bot_database.db', 'data/bot_database.db', 'database.db']:
        full_p = os.path.join(r'C:\Users\danat\Desktop\dvachbot', p)
        if os.path.exists(full_p):
            db_path = full_p
            break

print(f"Connecting to database: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. List all tables and indexes
cursor.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY tbl_name, type")
schema_items = cursor.fetchall()
print("\n--- TABLES & INDEXES ---")
for ttype, name, tbl_name, sql in schema_items:
    if ttype == 'index' and tbl_name in ('Posts', 'PostFiles', 'Users', 'DeliveryQueue', 'FileRegistry', 'FileTagsFTS'):
        print(f"Index: {name} on {tbl_name} -> {sql}")

# 2. Inspect PostFiles table structure and indexes specifically
cursor.execute("PRAGMA table_info(PostFiles)")
cols = cursor.fetchall()
print("\n--- PostFiles columns ---")
for c in cols:
    print(c)

cursor.execute("PRAGMA index_list(PostFiles)")
idxs = cursor.fetchall()
print("\n--- PostFiles indexes ---")
for idx in idxs:
    print(idx)
    cursor.execute(f"PRAGMA index_info({idx[1]})")
    print("  Columns:", cursor.fetchall())

# 3. Explain Query Plan for tag search (PostFiles query in bench_tags.py)
file_ids_sample = ['test1', 'test2', 'test3']
placeholders = ','.join(['?']*len(file_ids_sample))
params = file_ids_sample + file_ids_sample
tag_query = f'''
    EXPLAIN QUERY PLAN
    SELECT count(DISTINCT post_num)
    FROM PostFiles 
    WHERE original_file_id IN ({placeholders})
       OR thumbnail_file_id IN ({placeholders})
'''
cursor.execute(tag_query, params)
print("\n--- EXPLAIN QUERY PLAN: PostFiles tag query ---")
for row in cursor.fetchall():
    print(row)

# 4. Explain Query Plan for DeliveryQueue queries
delivery_query = '''
    EXPLAIN QUERY PLAN
    SELECT id FROM DeliveryQueue
    WHERE status = 'pending' AND board_id = ? AND post_num = ? AND delivery_phase = ?
    ORDER BY id LIMIT 1
'''
cursor.execute(delivery_query, ('b', 12345, 'passive'))
print("\n--- EXPLAIN QUERY PLAN: DeliveryQueue lookup query ---")
for row in cursor.fetchall():
    print(row)

# 5. Explain Query Plan for get_posts_by_file_ids
get_posts_query = f'''
    EXPLAIN QUERY PLAN
    SELECT * FROM Posts 
    WHERE post_num IN (
        SELECT post_num FROM PostFiles 
        WHERE original_file_id IN ({placeholders}) 
           OR thumbnail_file_id IN ({placeholders})
    ) AND IFNULL(is_shadow, 0) = 0
'''
cursor.execute(get_posts_query, params)
print("\n--- EXPLAIN QUERY PLAN: get_posts_by_file_ids ---")
for row in cursor.fetchall():
    print(row)

conn.close()
