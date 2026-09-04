import json
from collections import defaultdict
from datetime import datetime

# Load data
with open('c:/Users/danat/Desktop/dvachbot/latest_posts.json', encoding='utf-8') as f:
    posts = json.load(f)

with open('c:/Users/danat/Desktop/dvachbot/recent_mutes.json', encoding='utf-8') as f:
    mutes = json.load(f)
    
with open('c:/Users/danat/Desktop/dvachbot/recent_logs.json', encoding='utf-8') as f:
    logs = json.load(f)

# Sort posts from oldest to newest for chronological reading
posts_chronological = sorted(posts, key=lambda x: x['timestamp'])

# Build threads / conversations
threads = defaultdict(list)
replies = defaultdict(list)
authors = defaultdict(list)

for p in posts_chronological:
    content = p.get('text_content') or p.get('content') or "[NO TEXT/MEDIA]"
    p['clean_content'] = content
    authors[p['author_id']].append(p)
    if p['thread_id']:
        threads[p['thread_id']].append(p)
    if p['reply_to_post_num']:
        replies[p['reply_to_post_num']].append(p)

report = []
report.append("# ДЕТАЛЬНЫЙ АНАЛИЗ ПОСЛЕДНИХ 500 ПОСТОВ DVACHBOT (DEEP FORENSIC BREAKDOWN)\n")
report.append(f"**Временной срез**: Последние 500 постов.")
report.append(f"**Последний пост**: #{posts[0]['post_num']}")
report.append("\n## СТАТИСТИКА\n")
report.append(f"- **Всего проанализировано постов**: {len(posts)}")
report.append(f"- **Количество уникальных авторов**: {len(authors)}")

# Find complaints and bot interactions
complaints = []
bot_mentions = []
roasts_and_games = []

keywords_complaints = ['хули', 'почему', 'баг', 'бот', 'админ', 'сука', 'бля', 'не работает', 'завис', 'пидор', 'бан', 'мут', 'за что']
keywords_games = ['роль', 'кости', 'казино', 'дуэль', 'рулетка', 'киберчед', 'roast']

for p in posts_chronological:
    content = p['clean_content'].lower()
    
    # Check complaints
    if any(k in content for k in keywords_complaints):
        complaints.append(p)
        
    # Check games/roasts
    if any(k in content for k in keywords_games):
        roasts_and_games.append(p)

report.append("\n## 🚨 ЖАЛОБЫ И АГРЕССИЯ В СТОРОНУ БОТА/АДМИНОВ\n")
if complaints:
    for p in complaints[-20:]: # last 20
        report.append(f"> **Пост #{p['post_num']}** (Автор: {p['author_id']}, Борд: {p['board_id']}):\n> {p['clean_content']}\n")
else:
    report.append("Жалоб не обнаружено.\n")

report.append("\n## 🎲 ИГРОВЫЕ СОБЫТИЯ И ВЗАИМОДЕЙСТВИЯ С БОТОМ\n")
if roasts_and_games:
    for p in roasts_and_games[-15:]:
        report.append(f"> **Пост #{p['post_num']}** (Автор: {p['author_id']}):\n> {p['clean_content']}\n")
else:
    report.append("Игровых событий не обнаружено.\n")

report.append("\n## 👥 АНАЛИЗ АКТИВНЫХ АВТОРОВ (Психологический срез)\n")
# Top 5 most active users
active_users = sorted(authors.items(), key=lambda x: len(x[1]), reverse=True)[:5]
for author_id, user_posts in active_users:
    report.append(f"### Автор `{author_id}` (Постов: {len(user_posts)})\n")
    report.append("Последние сообщения:\n")
    for up in user_posts[-3:]:
        report.append(f"- [#{up['post_num']}] {up['clean_content']}")
    report.append("\n")

report.append("\n## 🔨 НАКАЗАНИЯ И МУТЫ (По таблицам Mutes/Logs)\n")
if mutes:
    for m in mutes[:10]:
        report.append(f"- **Пользователь {m.get('user_id', '???')}**: Мут до {m.get('expires_at', '???')}. Причина: {m.get('reason', 'Нет причины')}")
else:
    report.append("Свежих мутов не найдено.\n")

report.append("\n## 💬 АКТИВНЫЕ ДИАЛОГИ И ТРЕДЫ\n")
for thread_id, thread_posts in sorted(threads.items(), key=lambda x: len(x[1]), reverse=True)[:3]:
    report.append(f"### Тред `{thread_id}` (Постов: {len(thread_posts)})\n")
    for p in thread_posts[-5:]:
         report.append(f"- **#{p['post_num']}** ({p['author_id']}): {p['clean_content']}")
    report.append("\n")

with open('c:/Users/danat/Desktop/dvachbot/REPORT_NEWEST_POSTS_BREAKDOWN.md', 'w', encoding='utf-8') as f:
    f.write("\n".join(report))

print("Report generated successfully.")
