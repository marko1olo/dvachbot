import sqlite3
import time
import json
conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cursor = conn.cursor()

cursor.execute('CREATE TABLE IF NOT EXISTS PostFiles (id INTEGER PRIMARY KEY AUTOINCREMENT, post_num INTEGER, file_type TEXT, original_file_id TEXT, thumbnail_file_id TEXT, original_url TEXT, thumbnail_url TEXT)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_postfiles_orig ON PostFiles (original_file_id)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_postfiles_thumb ON PostFiles (thumbnail_file_id)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_postfiles_post_num ON PostFiles (post_num)')
cursor.execute('DELETE FROM PostFiles')

start = time.time()
cursor.execute('SELECT post_num, content FROM Posts')
rows = cursor.fetchall()

inserts = []
for post_num, content in rows:
    if not content or ('file_id' not in content and 'original_file_id' not in content and 'original_url' not in content):
        continue
    try:
        obj = json.loads(content)
        m_type = obj.get('type')
        if m_type == 'media_group' and obj.get('media'):
            for m in obj['media']:
                if m.get('file_id') or m.get('original_file_id') or m.get('original_url'):
                    inserts.append((post_num, m.get('type', 'photo'), m.get('file_id') or m.get('original_file_id'), m.get('thumbnail_file_id'), m.get('original_url'), m.get('thumbnail_url')))
        elif obj.get('files'):
            for m in obj['files']:
                if m.get('original_file_id') or m.get('original_url'):
                    inserts.append((post_num, m.get('type', 'photo'), m.get('original_file_id'), m.get('thumbnail_file_id'), m.get('original_url'), m.get('thumbnail_url')))
        elif obj.get('file_id') or obj.get('original_file_id') or obj.get('original_url'):
            inserts.append((post_num, m_type or 'photo', obj.get('file_id') or obj.get('original_file_id'), obj.get('thumbnail_file_id'), obj.get('original_url'), obj.get('thumbnail_url')))
    except:
        pass

cursor.executemany('INSERT INTO PostFiles (post_num, file_type, original_file_id, thumbnail_file_id, original_url, thumbnail_url) VALUES (?, ?, ?, ?, ?, ?)', inserts)
conn.commit()
print(f'Inserted {len(inserts)} files in {time.time()-start:.2f}s')
