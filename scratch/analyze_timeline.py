import sqlite3
from datetime import datetime, UTC

def main():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # 1. Total posts count
    cursor.execute("SELECT count(*) FROM Posts")
    total_posts = cursor.fetchone()[0]
    print(f"Total posts in DB: {total_posts}")
    
    # 2. Min/Max post timestamp
    cursor.execute("SELECT min(timestamp), max(timestamp) FROM Posts")
    min_ts, max_ts = cursor.fetchone()
    print(f"First post: {datetime.fromtimestamp(min_ts, tz=UTC) if min_ts else 'N/A'}")
    print(f"Last post: {datetime.fromtimestamp(max_ts, tz=UTC) if max_ts else 'N/A'}")
    
    # 3. Let's see the post count per day for the last 10 days
    cursor.execute("""
        SELECT date(timestamp, 'unixepoch'), count(*) 
        FROM Posts 
        WHERE timestamp >= ?
        GROUP BY date(timestamp, 'unixepoch')
        ORDER BY date(timestamp, 'unixepoch') DESC
    """, (datetime.now().timestamp() - 15 * 86400,))
    print("\n=== POSTS BY DAY ===")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} posts")
        
    # 4. Let's see how many posts are from banned/spammer users (the ones we cleaned up, or in general)
    # Wait, the spammers were 7665861923 and 5264555563.
    # Are there posts left from them, or did we delete all?
    # Let's check if there are any other highly active users in Posts
    cursor.execute("""
        SELECT author_id, count(*) 
        FROM Posts 
        GROUP BY author_id 
        ORDER BY count(*) DESC 
        LIMIT 10
    """)
    print("\n=== TOP AUTHORS BY POST COUNT ===")
    rows = cursor.fetchall()
    if rows:
        author_ids = [row[0] for row in rows]
        placeholders = ','.join('?' for _ in author_ids)
        cursor.execute(f"SELECT user_id, status, board_id FROM Users WHERE user_id IN ({placeholders})", author_ids)
        user_info_map = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

        for row in rows:
            author_id = row[0]
            if author_id in user_info_map:
                status, board_id = user_info_map[author_id]
                status_info = f"{status} on {board_id}"
            else:
                status_info = "not in Users"
            print(f"  Author: {author_id} ({status_info}), Posts: {row[1]}")

    conn.close()

if __name__ == '__main__':
    main()
