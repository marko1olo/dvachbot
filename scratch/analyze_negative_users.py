import sqlite3

def main():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Let's count negative users by board and stream
    cursor.execute("""
        SELECT board_id, stream, count(*), count(distinct user_id)
        FROM Users 
        WHERE user_id < 0 
        GROUP BY board_id, stream
    """)
    print("=== NEGATIVE USERS BY BOARD & STREAM ===")
    for row in cursor.fetchall():
        print(f"Board: {row[0]}, Stream: {row[1]}, Rows: {row[2]}, Unique: {row[3]}")
        
    # Let's see some details of negative users
    cursor.execute("""
        SELECT user_id, board_id, status, location, role, stream, created_at, lie_media
        FROM Users 
        WHERE user_id < 0 
        LIMIT 15
    """)
    print("\n=== SAMPLE NEGATIVE USERS ===")
    for row in cursor.fetchall():
        print(row)
        
    # Let's check how many total users are active (not banned/deleted) with user_id >= 100000
    cursor.execute("""
        SELECT board_id, count(*) 
        FROM Users 
        WHERE user_id >= 100000 AND status = 'active'
        GROUP BY board_id
    """)
    print("\n=== ACTIVE TG USERS (>= 100000) BY BOARD ===")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
        
    # Let's see if there are any active negative users
    cursor.execute("""
        SELECT count(*) 
        FROM Users 
        WHERE user_id < 0 AND status = 'active'
    """)
    print(f"\nActive negative user rows: {cursor.fetchone()[0]}")

    conn.close()

if __name__ == '__main__':
    main()
