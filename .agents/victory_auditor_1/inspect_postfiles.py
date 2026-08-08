import sqlite3

conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM PostFiles")
print("Total rows in PostFiles:", cur.fetchone()[0])

cur.execute("SELECT id, post_num, original_file_id, thumbnail_file_id FROM PostFiles LIMIT 10")
rows = cur.fetchall()
print("Sample PostFiles rows:")
for r in rows:
    print(r)

conn.close()
