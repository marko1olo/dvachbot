"""
Enqueue the latest 10,000 unmirrored post images into MirrorQueue for ImgBB.
Orders by post_num DESC so that the most recent and active posts are mirrored first.
"""

import sys
import os
import sqlite3
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dvach_bot.db')
LIMIT_COUNT = 10000

print(f"Connecting to database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=60000;")
conn.execute("PRAGMA synchronous=NORMAL;")
c = conn.cursor()

query = """
    SELECT DISTINCT pf.original_file_id
    FROM PostFiles pf
    JOIN Posts p ON pf.post_num = p.post_num
    WHERE pf.original_file_id LIKE 'AgAC%'
      AND NOT EXISTS (
          SELECT 1 FROM FileMirrors fm 
          WHERE fm.file_id = pf.original_file_id AND fm.mirror_type = 'imgbb'
      )
      AND NOT EXISTS (
          SELECT 1 FROM MirrorQueue mq 
          WHERE mq.file_id = pf.original_file_id AND mq.mirror_type = 'imgbb'
      )
    ORDER BY p.post_num DESC
    LIMIT ?
"""

print(f"Selecting top {LIMIT_COUNT:,} latest un-mirrored files for ImgBB...")
c.execute(query, (LIMIT_COUNT,))
rows = c.fetchall()
print(f"Found {len(rows):,} candidate files.")

if not rows:
    print("All recent files are already queued or mirrored for ImgBB!")
    conn.close()
    sys.exit(0)

now = time.time()
inserted = 0
for (file_id,) in rows:
    try:
        c.execute(
            "INSERT OR IGNORE INTO MirrorQueue (file_id, mirror_type, attempts, next_run_at) VALUES (?, 'imgbb', 0, ?)",
            (file_id, now)
        )
        if c.rowcount > 0:
            inserted += 1
    except Exception as e:
        print(f"Error inserting {file_id[:15]}: {e}")

conn.commit()
conn.close()

print(f"\n✅ Successfully enqueued {inserted:,} files into MirrorQueue for 'imgbb'!")
print("The background mirror_worker will automatically process them concurrently.")
