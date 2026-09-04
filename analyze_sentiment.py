import sqlite3
import json
import collections

db_path = "c:/Users/danat/Desktop/dvachbot/dvach_bot.db"
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get posts from last 48 hours
query = """
SELECT post_num, board_id, thread_id, author_id, text_content, timestamp, is_shadow
FROM Posts
WHERE timestamp >= 1788329880
ORDER BY timestamp ASC
"""
cursor.execute(query)
posts = cursor.fetchall()

bot_keywords = ['бот', 'bot', 'cyberchad', 'киберчед', 'войс', 'гс', 'голос']
game_keywords = ['/duel', 'дуэль', '/dice', 'кости', 'ролл', 'рулетк', '/roulette']
toxic_keywords = ['хуй', 'пизд', 'ебат', 'бля', 'сука', 'тупой', 'несправедлив', 'заебал', 'говн', 'пидор', 'мраз', 'хуйня', 'уебан', 'пидорас']

results = {
    "total_posts": len(posts),
    "bot_feedback": [],
    "game_feedback": [],
    "toxic_incidents": [],
    "threads_summary": []
}

threads = collections.defaultdict(list)
for p in posts:
    threads[p['thread_id']].append(dict(p))

for t_id, t_posts in threads.items():
    results["threads_summary"].append({
        "thread_id": t_id,
        "post_count": len(t_posts)
    })

for p in posts:
    text = str(p['text_content'] or '').lower()
    
    is_bot = any(k in text for k in bot_keywords)
    is_game = any(k in text for k in game_keywords)
    is_toxic = any(k in text for k in toxic_keywords)
    
    post_data = {
        'post_num': p['post_num'],
        'author_id': p['author_id'],
        'thread_id': p['thread_id'],
        'text': p['text_content'],
        'timestamp': p['timestamp']
    }
    
    if is_bot and len(results["bot_feedback"]) < 200:
        results["bot_feedback"].append(post_data)
    if is_game and len(results["game_feedback"]) < 200:
        results["game_feedback"].append(post_data)
    if is_toxic and len(results["toxic_incidents"]) < 200:
        results["toxic_incidents"].append(post_data)

results["threads_summary"] = sorted(results["threads_summary"], key=lambda x: x["post_count"], reverse=True)[:10]

with open("c:/Users/danat/Desktop/dvachbot/analysis_out.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Analyzed {len(posts)} posts. Wrote to analysis_out.json")
