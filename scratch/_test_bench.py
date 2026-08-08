import sqlite3
import time

conn = sqlite3.connect('dvach_bot.db')
cur = conn.cursor()

# Ensure separate single-column indexes
cur.execute('CREATE INDEX IF NOT EXISTS idx_postfiles_orig ON PostFiles(original_file_id)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_postfiles_thumb ON PostFiles(thumbnail_file_id)')
conn.commit()

tag = '1boy'
cur.execute('SELECT file_id FROM FileTagsFTS WHERE FileTagsFTS MATCH ? LIMIT 60', (f'"{tag}"*',))
file_ids = [r[0] for r in cur.fetchall()]

placeholders = ','.join(['?'] * len(file_ids))
params = file_ids + file_ids
query = f'''
    SELECT count(DISTINCT post_num)
    FROM PostFiles 
    WHERE original_file_id IN ({placeholders})
       OR thumbnail_file_id IN ({placeholders})
'''

start = time.time()
cur.execute(query, params)
res = cur.fetchone()[0]
t = (time.time() - start) * 1000
print(f'With separate single-column indices: returned {res} posts in {t:.2f}ms')
