import sqlite3
import json

conn = sqlite3.connect('data/bot_database.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]

if 'posts' in tables:
    cursor.execute('SELECT content FROM posts WHERE author_id=0 ORDER BY post_num DESC LIMIT 5000')
    rows = cursor.fetchall()
    blat_count = 0
    pogovorki = 0
    for row in rows:
        try:
            c = json.loads(row[0])
            text = c.get('text', '') or c.get('caption', '')
            if 'Вечер в хату' in text or 'АУБ' in text or 'Людское' in text or 'Петушиное' in text:
                blat_count += 1
                if 'Там, где' in text or 'Там где' in text or 'отражение своё пугак' in text or 'хуй сосал' in text or 'у зеркала' in text:
                    pogovorki += 1
        except Exception:
            pass
    print(f'Total bot messages analyzed: {len(rows)}')
    print(f'Total blat-like summaries: {blat_count}')
    print(f'Pogovorki used: {pogovorki}')
