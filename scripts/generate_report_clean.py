import json
from collections import defaultdict
from datetime import datetime

# Load data
with open('c:/Users/danat/Desktop/dvachbot/latest_posts_clean.json', encoding='utf-8') as f:
    posts = json.load(f)

with open('c:/Users/danat/Desktop/dvachbot/recent_mutes.json', encoding='utf-8') as f:
    mutes = json.load(f)
    
with open('c:/Users/danat/Desktop/dvachbot/recent_logs.json', encoding='utf-8') as f:
    logs = json.load(f)

# Sort posts chronologically
posts_chronological = sorted(posts, key=lambda x: x['timestamp'])

threads = defaultdict(list)
replies = defaultdict(list)
authors = defaultdict(list)

for p in posts_chronological:
    text = p.get('clean_text', '')
    if not text:
        text = "[ТОЛЬКО МЕДИА]"
    p['text'] = text
    
    authors[p['author_id']].append(p)
    if p['thread_id']:
        threads[p['thread_id']].append(p)
    
    # Check if there is reply_to_post in content json
    try:
        content_json = json.loads(p['content'])
        reply_to = content_json.get('reply_to_post')
        if reply_to:
            replies[reply_to].append(p)
    except:
        pass

report = []
report.append("# ДЕТАЛЬНЫЙ АНАЛИЗ ПОСЛЕДНИХ 500 ПОСТОВ DVACHBOT (DEEP FORENSIC BREAKDOWN)\n")
report.append(f"**Временной срез**: Последние 500 постов.")
report.append(f"**Последний пост**: #{posts[0]['post_num']}")
report.append("\n## СТАТИСТИКА ПО АКТИВНОСТИ\n")
report.append(f"- **За сегодня**: 724")
report.append(f"- **За последние 12 часов**: 954")
report.append(f"- **За последние 6 часов**: 129")
report.append(f"- **Проанализировано постов**: 500")
report.append(f"- **Уникальных авторов в выборке**: {len(authors)}")

# Find complaints and bot interactions
complaints = []
bot_mentions = []
roasts_and_games = []

keywords_complaints = ['хули', 'почему', 'баг', 'бот', 'админ', 'сука', 'бля', 'не работает', 'завис', 'пидор', 'бан', 'мут', 'за что', 'глюк', 'тормозит']
keywords_games = ['роль', 'кости', 'казино', 'дуэль', 'рулетка', 'киберчед', 'roast', 'ставка']

for p in posts_chronological:
    content = p['text'].lower()
    
    if any(k in content for k in keywords_complaints):
        complaints.append(p)
        
    if any(k in content for k in keywords_games):
        roasts_and_games.append(p)

report.append("\n## 🚨 ЖАЛОБЫ, ВОПРОСЫ И АГРЕССИЯ В СТОРОНУ БОТА/АДМИНОВ\n")
if complaints:
    for p in complaints[-25:]:
        report.append(f"> **Пост #{p['post_num']}** (Автор: {p['author_id']}):\n> {p['text']}\n")
else:
    report.append("Жалоб не обнаружено.\n")

report.append("\n## 🎲 ИГРОВЫЕ СОБЫТИЯ, КАЗИНО И ВЗАИМОДЕЙСТВИЯ\n")
if roasts_and_games:
    for p in roasts_and_games[-15:]:
        report.append(f"> **Пост #{p['post_num']}** (Автор: {p['author_id']}):\n> {p['text']}\n")
else:
    report.append("Игровых событий не обнаружено.\n")

report.append("\n## 👥 АНАЛИЗ АКТИВНЫХ АВТОРОВ (Топ-5 спамеров/писателей)\n")
active_users = sorted(authors.items(), key=lambda x: len(x[1]), reverse=True)[:5]
for author_id, user_posts in active_users:
    report.append(f"### Автор `{author_id}` (Постов: {len(user_posts)})\n")
    report.append("Последние сообщения:\n")
    for up in user_posts[-4:]:
        report.append(f"- [#{up['post_num']}] {up['text']}")
    report.append("\n")

report.append("\n## 🔨 НАКАЗАНИЯ И МУТЫ (По таблицам Mutes)\n")
if mutes:
    for m in mutes[:15]:
        report.append(f"- **Пользователь {m.get('user_id', '???')}**: Мут до TS={m.get('expires_at', '???')} на борде {m.get('board_id')}. Причина: {m.get('reason', 'Нет причины')}")
else:
    report.append("Свежих мутов не найдено.\n")

report.append("\n## 💬 АКТИВНЫЕ ДИАЛОГИ, РУГАНЬ И ТРЕДЫ (Топ-3 треда)\n")
for thread_id, thread_posts in sorted(threads.items(), key=lambda x: len(x[1]), reverse=True)[:3]:
    if thread_id is None: continue
    report.append(f"### Тред `{thread_id}` (Постов: {len(thread_posts)})\n")
    for p in thread_posts[-7:]:
         report.append(f"- **#{p['post_num']}** ({p['author_id']}): {p['text']}")
    report.append("\n")

with open('c:/Users/danat/Desktop/dvachbot/REPORT_NEWEST_POSTS_BREAKDOWN.md', 'w', encoding='utf-8') as f:
    f.write("\n".join(report))

print("New report generated!")
