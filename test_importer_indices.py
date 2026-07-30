import sqlite3

conn = sqlite3.connect(':memory:')
conn.execute("""
    CREATE TABLE ImportQueue (
        id INTEGER PRIMARY KEY,
        task_id TEXT,
        board_id TEXT,
        original_post_num INTEGER,
        reply_to_original INTEGER,
        content TEXT,
        author_id TEXT,
        stream TEXT,
        is_op BOOLEAN,
        thread_title TEXT,
        publish_at INTEGER
    )
""")

cur = conn.execute("""
    SELECT id, task_id, board_id, original_post_num, reply_to_original,
           content, author_id, stream, is_op, thread_title
    FROM ImportQueue
""")

description = cur.description
print("Indices in query:")
for i, col in enumerate(description):
    print(f"{i}: {col[0]}")
