import sqlite3
import time

conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cursor = conn.cursor()

tag = '1boy'
query_fts = '''
    SELECT file_id, bm25(FileTagsFTS) as score, tags
    FROM FileTagsFTS
    WHERE FileTagsFTS MATCH ?
    ORDER BY score ASC
    LIMIT 60 OFFSET 0
'''

cursor.execute(query_fts, (f'"{tag}"*', ))
res = cursor.fetchall()
file_ids = [r[0] for r in res]

clauses = []
params = []
for fid in file_ids:
    clauses.append('instr(content, ?) > 0')
    params.append(fid)
    
where_clause = ' OR '.join(clauses)
query = f'SELECT count(*) FROM Posts WHERE ({where_clause}) AND IFNULL(is_shadow, 0) = 0'

start = time.time()
cursor.execute(query, params)
c1 = cursor.fetchone()[0]
t1 = time.time() - start
print(f'Old method returned {c1} posts in {t1*1000:.2f}ms')

placeholders = ','.join(['?']*len(file_ids))
params2 = file_ids + file_ids
query2 = f'''
    SELECT count(DISTINCT post_num)
    FROM PostFiles 
    WHERE original_file_id IN ({placeholders})
       OR thumbnail_file_id IN ({placeholders})
'''
start = time.time()
cursor.execute(query2, params2)
c2 = cursor.fetchone()[0]
t2 = time.time() - start
print(f'New method returned {c2} posts in {t2*1000:.2f}ms')
