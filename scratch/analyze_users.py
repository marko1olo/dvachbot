import sqlite3

def main():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # 1. Total row count in Users
    cursor.execute("SELECT count(*) FROM Users")
    total_users = cursor.fetchone()[0]
    print(f"Total rows in Users: {total_users}")
    
    # 2. Check unique user_ids
    cursor.execute("SELECT count(distinct user_id) FROM Users")
    unique_user_ids = cursor.fetchone()[0]
    print(f"Unique user_ids in Users: {unique_user_ids}")
    
    # 3. Check for negative user_ids or small user_ids
    cursor.execute("SELECT count(*) FROM Users WHERE user_id < 0")
    neg_users = cursor.fetchone()[0]
    print(f"Negative user_ids: {neg_users}")
    
    cursor.execute("SELECT count(*) FROM Users WHERE user_id > 0 AND user_id < 10000")
    small_users = cursor.fetchone()[0]
    print(f"Small positive user_ids (< 10000): {small_users}")
    
    # Let's list some small positive user_ids and negative user_ids
    if neg_users > 0:
        cursor.execute("SELECT user_id, board_id, status FROM Users WHERE user_id < 0 LIMIT 10")
        print("Sample negative user_ids:")
        for row in cursor.fetchall():
            print(f"  {row}")
            
    if small_users > 0:
        cursor.execute("SELECT user_id, board_id, status FROM Users WHERE user_id > 0 AND user_id < 10000 LIMIT 10")
        print("Sample small positive user_ids:")
        for row in cursor.fetchall():
            print(f"  {row}")

    # 4. Check for active Telegram user IDs (usually > 100000)
    cursor.execute("SELECT count(distinct user_id) FROM Users WHERE user_id >= 100000")
    real_tg_users = cursor.fetchone()[0]
    print(f"Unique user_ids >= 100000 (potential real TG users): {real_tg_users}")
    
    # Check subscriptions for these potential real TG users
    cursor.execute("SELECT count(*) FROM Users WHERE user_id >= 100000")
    real_tg_subs = cursor.fetchone()[0]
    print(f"Total subscriptions for users >= 100000: {real_tg_subs}")

    # Group real TG users by board
    cursor.execute("SELECT board_id, count(*) FROM Users WHERE user_id >= 100000 GROUP BY board_id")
    print("Subscriptions by board (for user_id >= 100000):")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # 5. Let's look at ChannelCopies or other tables where site broadcasts might happen
    # Let's check if there are columns or tables referencing "fake" or "site"
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Let's see if there are any settings in SystemSettings
    if 'SystemSettings' in tables:
        cursor.execute("SELECT * FROM SystemSettings")
        print("\n=== SYSTEM SETTINGS ===")
        for row in cursor.fetchall():
            print(row)
            
    conn.close()

if __name__ == '__main__':
    main()
