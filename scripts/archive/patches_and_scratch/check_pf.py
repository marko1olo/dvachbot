import sqlite3
import time

conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cursor = conn.cursor()

tag = '1boy'
query_fts = '''
    SELECT file_id
    FROM FileTagsFTS
    WHERE FileTagsFTS MATCH ?
    LIMIT 10
'''
cursor.execute(query_fts, (f'"{tag}"*', ))
file_ids = [r[0] for r in cursor.fetchall()]

for fid in file_ids:
    cursor.execute('SELECT COUNT(*) FROM PostFiles WHERE original_file_id = ? OR thumbnail_file_id = ?', (fid, fid))
    c = cursor.fetchone()[0]
    if c == 0:
        cursor.execute('SELECT COUNT(*) FROM Posts WHERE instr(content, ?) > 0', (fid,))
        c2 = cursor.fetchone()[0]
        print(f'FID {fid}: PostFiles={c}, Posts.content={c2}')
