import sqlite3
import json
from collections import defaultdict
from datetime import datetime, timezone

db_path = 'file:c:/Users/danat/Desktop/dvachbot/dvach_bot.db?mode=ro'
conn = sqlite3.connect(db_path, uri=True)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Get max timestamp
c.execute("SELECT MAX(timestamp), MAX(post_num) FROM Posts")
max_ts, max_post_num = c.fetchone()
print(f"Max TS: {max_ts} = {datetime.fromtimestamp(max_ts, tz=timezone.utc)}")

# Get stats for 12h and 6h and today (based on max_ts)
today_start_ts = datetime.fromtimestamp(max_ts).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
c.execute("SELECT COUNT(*) FROM Posts WHERE timestamp >= ?", (today_start_ts,))
count_today = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM Posts WHERE timestamp >= ?", (max_ts - 12*3600,))
count_12h = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM Posts WHERE timestamp >= ?", (max_ts - 6*3600,))
count_6h = c.fetchone()[0]

print(f"Today: {count_today}, 12h: {count_12h}, 6h: {count_6h}")

# Get 500 latest posts
c.execute("SELECT * FROM Posts ORDER BY post_num DESC LIMIT 500")
posts = [dict(r) for r in c.fetchall()]

# Extract clean text from JSON content
for p in posts:
    clean_text = ""
    try:
        if p['content']:
            content_dict = json.loads(p['content'])
            text = content_dict.get('text') or content_dict.get('caption') or ""
            clean_text = text
    except:
        pass
    p['clean_text'] = clean_text

# Write to json for report builder
with open('c:/Users/danat/Desktop/dvachbot/latest_posts_clean.json', 'w', encoding='utf-8') as f:
    json.dump(posts, f, ensure_ascii=False, indent=2)

print("Data extracted cleanly.")
