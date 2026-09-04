import sqlite3
import re
import json

db_uri = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'

keywords = {
    'Bugs': [r'баг', r'лаг', r'ошибк', r'глюк', r'завис', r'не работает', r'не пришло', r'пропал', r'вылетел', r'сбросил', r'не засчитал'],
    'Moderation': [r'мут', r'бан', r'теневой', r'шэдоу', r'спам', r'за что', r'размуть', r'удалил', r'почини'],
    'Mechanics': [r'заточк', r'грабеж', r'спиздил', r'баланс', r'перцовк', r'пативэн', r'дуэль', r'кости', r'скам', r'нечестн'],
    'Suggestions': [r'предлагаю', r'сделай', r'добавь', r'верни', r'лучше бы', r'надо сдела', r'идея']
}

conn = sqlite3.connect(db_uri, uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get posts from last 48h
# Ensure table columns exist, if not, handle it. Let's do a quick pragma check if this fails.
cursor.execute("SELECT * FROM Posts WHERE timestamp >= 1788329880")
posts = cursor.fetchall()

findings = {'Bugs': [], 'Moderation': [], 'Mechanics': [], 'Suggestions': []}

for post in posts:
    comment = post['comment'] if 'comment' in post.keys() else post.get('text', '')
    author_id = post['author_id'] if 'author_id' in post.keys() else post.get('user_id', '')
    post_num = post['post_num'] if 'post_num' in post.keys() else post.get('id', '')
    timestamp = post['timestamp'] if 'timestamp' in post.keys() else post.get('created_at', 0)
    
    if not comment: continue
    comment_lower = comment.lower()
    
    matched_categories = []
    for cat, patterns in keywords.items():
        if any(re.search(p, comment_lower) for p in patterns):
            matched_categories.append(cat)
            
    for cat in matched_categories:
        findings[cat].append({
            'post_num': post_num,
            'author_id': author_id,
            'comment': comment,
            'timestamp': timestamp
        })

# Let's cross-reference and augment with transactions/mutes
for cat in findings:
    for item in findings[cat]:
        author_id = item['author_id']
        
        # Get recent transactions
        try:
            cursor.execute("SELECT amount, reason, timestamp FROM UserTransactions WHERE user_id = ? AND timestamp >= 1788329880", (author_id,))
            txs = [dict(r) for r in cursor.fetchall()]
        except:
            txs = []
        item['transactions'] = txs
        
        # Get recent mutes
        try:
            cursor.execute("SELECT reason, expires_at FROM Mutes WHERE user_id = ?", (author_id,))
            mutes = [dict(r) for r in cursor.fetchall()]
        except:
            mutes = []
        item['mutes'] = mutes

with open('c:/Users/danat/Desktop/dvachbot/feedback_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(findings, f, ensure_ascii=False, indent=2)

print("Analysis saved to feedback_analysis.json")
