import sqlite3
import json
from datetime import datetime, timedelta, timezone

db_path = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'
conn = sqlite3.connect(db_path, uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get max post_num and timestamp
cursor.execute("SELECT MAX(post_num) as max_num, MAX(timestamp) as max_ts FROM Posts")
max_row = cursor.fetchone()
max_post_num = max_row['max_num']
max_timestamp = max_row['max_ts']

print(f"Max Post Num: {max_post_num}, Max Timestamp: {max_timestamp}")

# Timestamps to filter
# Let's say current time is roughly the max_timestamp or use 2026-09-04 10:58:32
current_time_str = "2026-09-04T10:58:32" # from metadata
try:
    current_time = datetime.strptime(current_time_str, "%Y-%m-%dT%H:%M:%S")
except:
    current_time = datetime.fromisoformat(max_timestamp[:19]) # fallback if max_timestamp is iso

today_start = "2026-09-04 00:00:00"
twelve_hours_ago = "2026-09-03 22:58:32"
six_hours_ago = "2026-09-04 04:58:32"

cursor.execute("SELECT COUNT(*) as c FROM Posts WHERE timestamp >= ?", (today_start,))
count_today = cursor.fetchone()['c']

cursor.execute("SELECT COUNT(*) as c FROM Posts WHERE timestamp >= ?", (twelve_hours_ago,))
count_12h = cursor.fetchone()['c']

cursor.execute("SELECT COUNT(*) as c FROM Posts WHERE timestamp >= ?", (six_hours_ago,))
count_6h = cursor.fetchone()['c']

print(f"Posts today: {count_today}, 12h: {count_12h}, 6h: {count_6h}")

# Get latest 500 posts
query = """
SELECT post_num, board_id, thread_id, author_id, text_content, timestamp, is_shadow, reply_to_post_num
FROM Posts
ORDER BY post_num DESC
LIMIT 500
"""
cursor.execute(query)
posts = [dict(row) for row in cursor.fetchall()]

with open("c:/Users/danat/Desktop/dvachbot/latest_posts.json", "w", encoding="utf-8") as f:
    json.dump(posts, f, ensure_ascii=False, indent=2)

# Get recent Mutes and GlobalLogs for correlation
# We'll just fetch recent mutes and logs (last 500)
cursor.execute("SELECT * FROM Mutes ORDER BY expires_at DESC LIMIT 100")
mutes = [dict(row) for row in cursor.fetchall()]

with open("c:/Users/danat/Desktop/dvachbot/recent_mutes.json", "w", encoding="utf-8") as f:
    json.dump(mutes, f, ensure_ascii=False, indent=2)
    
cursor.execute("SELECT * FROM GlobalLogs ORDER BY id DESC LIMIT 100")
logs = [dict(row) for row in cursor.fetchall()]

with open("c:/Users/danat/Desktop/dvachbot/recent_logs.json", "w", encoding="utf-8") as f:
    json.dump(logs, f, ensure_ascii=False, indent=2)

print("Data dumped to json files.")
