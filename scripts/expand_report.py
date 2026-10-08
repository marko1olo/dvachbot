import sqlite3
import json

db_path = "c:/Users/danat/Desktop/dvachbot/dvach_bot.db"
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = """
SELECT post_num, author_id, content, timestamp
FROM Posts
WHERE timestamp >= 1788329880
ORDER BY timestamp ASC
"""
cursor.execute(query)
posts = cursor.fetchall()

keywords = [
    'киберчед', 'бот', 'хуета', 'заебал', 'рулетка', 'дуэль', 'мут', 
    'одни и те же', 'пидор', 'хуй', 'пизд', 'ебат', 'бля', 'сука', 
    'тупой', 'несправедлив', 'говн', 'мраз', 'уебан', 'пидорас', 'параша', 'кал', 'бесит'
]

negativity = []

for p in posts:
    if not p['content']: continue
    try:
        c_json = json.loads(p['content'])
        text = str(c_json.get('text', c_json.get('caption', '')))
    except:
        continue
        
    text_lower = text.lower()
    
    # Filter out bot's own standard messages to only get user outbursts
    # if it's the bot itself, author_id is usually 0
    if p['author_id'] == 0:
        continue
        
    if any(k in text_lower for k in keywords):
        negativity.append({
            'post_num': p['post_num'],
            'author_id': p['author_id'],
            'text': text
        })

# Now format this into a massive markdown string
md_content = """# РАСШИРЕННЫЙ РЕЕСТР НЕГАТИВА И ФРУСТРАЦИИ (ПОСЛЕДНИЕ 48 ЧАСОВ)

Ниже приведена исчерпывающая база всех эмоциональных всплесков, мата, претензий к боту, играм и модерации от пользователей за последние 48 часов.

"""

for idx, item in enumerate(negativity, 1):
    md_content += f"### Инцидент {idx}\n"
    md_content += f"- **Post Num:** {item['post_num']}\n"
    md_content += f"- **Author ID:** {item['author_id']}\n"
    md_content += f"- **Цитата:**\n> {item['text'].replace(chr(10), chr(10)+'> ')}\n\n"

# Append this to the existing report
existing_report = open("c:/Users/danat/Desktop/dvachbot/REPORT_USER_SENTIMENT_LAST_48H.md", "r", encoding="utf-8").read()

final_report = existing_report + "\n\n---\n\n" + md_content

with open("c:/Users/danat/Desktop/dvachbot/REPORT_USER_SENTIMENT_LAST_48H.md", "w", encoding="utf-8") as f:
    f.write(final_report)

print(f"Added {len(negativity)} negative outbursts to the report.")
