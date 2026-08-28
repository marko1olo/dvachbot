import sqlite3
import time

conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cursor = conn.cursor()
tag = '1boy'
query_fts = '''
    SELECT file_id
    FROM FileTagsFTS
    WHERE FileTagsFTS MATCH ?
    LIMIT 60
'''
cursor.execute(query_fts, (f'"{tag}"*', ))
file_ids = [r[0] for r in cursor.fetchall()]
placeholders = ','.join(['?']*len(file_ids))

# new json approach
query_json = f'''
SELECT post_num 
FROM Posts, json_each(
    CASE 
        WHEN json_extract(content, '$.type') = 'media_group' THEN json_extract(content, '$.media')
        WHEN json_extract(content, '$.file_id') IS NOT NULL THEN json_array(json_extract(content, '$'))
        WHEN json_extract(content, '$.original_file_id') IS NOT NULL THEN json_array(json_extract(content, '$'))
        WHEN json_extract(content, '$.files') IS NOT NULL THEN json_extract(content, '$.files')
        ELSE json_array()
    END
) as media
WHERE json_extract(media.value, '$.file_id') IN ({placeholders}) 
   OR json_extract(media.value, '$.original_file_id') IN ({placeholders})
'''
start = time.time()
cursor.execute(query_json, file_ids + file_ids)
res = cursor.fetchall()
t = time.time() - start
print(f'JSON EACH returned {len(res)} in {t*1000:.2f}ms')
