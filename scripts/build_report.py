import sqlite3
import re
import json
from collections import defaultdict

db_uri = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'
conn = sqlite3.connect(db_uri, uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

time_start = 1788329880

keywords = {
    'Bugs': [r'баг', r'лаг', r'ошибк', r'глюк', r'завис', r'не работа', r'не пришл', r'пропал', r'вылетел', r'сбросил', r'не засчитал', r'почини'],
    'Moderation': [r'мут\b', r'бан\b', r'теневой', r'шэдоу', r'спам', r'за что', r'размуть', r'удалил', r'несправедлив'],
    'Mechanics': [r'заточк', r'грабеж', r'спиздил', r'баланс', r'перцовк', r'пативэн', r'дуэль', r'кости', r'скам', r'нечестн'],
    'Suggestions': [r'предлагаю', r'сделай', r'добавь', r'верни', r'лучше бы', r'надо сдела', r'идея']
}

cursor.execute('SELECT post_num, author_id, content, timestamp FROM Posts WHERE timestamp >= ? AND author_id != 0', (time_start,))
posts = cursor.fetchall()

complaints = defaultdict(list)

for post_row in posts:
    post = dict(post_row)
    content_raw = post.get('content', '')
    
    text = ''
    try:
        data = json.loads(content_raw)
        if isinstance(data, dict):
            text = data.get('text', '')
        elif isinstance(data, list):
            text = ' '.join(item.get('text', '') for item in data if isinstance(item, dict) and item.get('type') == 'text')
    except:
        text = str(content_raw)
        
    text_lower = text.lower()
    if len(text) < 10: 
        continue # Ignore too short messages
        
    matched_cats = set()
    for cat, patterns in keywords.items():
        if any(re.search(p, text_lower) for p in patterns):
            matched_cats.add(cat)
            
    if matched_cats:
        complaints[post['author_id']].append({
            'post_num': post['post_num'],
            'text': text,
            'timestamp': post['timestamp'],
            'categories': list(matched_cats)
        })

report_md = "# Investigation Report: User Feedback & Bugs (Last 48h)\n\n"

for author_id, user_complaints in complaints.items():
    # Only process if there's substantial text, maybe skip if it's just general chat
    # To reduce noise, we check if they talk to 'админ' or use exclamation
    is_valid = False
    for c in user_complaints:
        t = c['text'].lower()
        if 'админ' in t or 'бот' in t or 'размуть' in t or 'почини' in t or 'баг' in t or 'ошибк' in t or 'пропал' in t or 'грабеж' in t or 'скам' in t or 'предлагаю' in t or 'верни' in t:
            is_valid = True
            break
            
    # if not is_valid: continue

    report_md += f"## User ID: {author_id}\n\n"
    report_md += "### Complaints / Posts:\n"
    for c in user_complaints:
        report_md += f"- **Post {c['post_num']}** ({', '.join(c['categories'])}): `{c['text']}`\n"
        
    cursor.execute('SELECT reason, expires_at FROM Mutes WHERE user_id = ?', (author_id,))
    mutes = cursor.fetchall()
    if mutes:
        report_md += "### Mutes found:\n"
        for m in mutes:
            report_md += f"- Reason: {m['reason']}, Expires at: {m['expires_at']}\n"
            
    cursor.execute('SELECT amount, category, description, timestamp FROM UserTransactions WHERE user_id = ? AND timestamp >= ?', (author_id, time_start))
    txs = cursor.fetchall()
    if txs:
        report_md += "### Recent Transactions:\n"
        for t in txs:
            report_md += f"- [{t['timestamp']}] {t['amount']} (Cat: {t['category']}): {t['description']}\n"
            
    report_md += "---\n\n"

with open('c:/Users/danat/Desktop/dvachbot/draft_report.md', 'w', encoding='utf-8') as f:
    f.write(report_md)
