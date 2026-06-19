import sqlite3
import json
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # 1. Total rows in DeliveryQueue
    cursor.execute("SELECT count(*) FROM DeliveryQueue")
    total_dq = cursor.fetchone()[0]
    print(f"Total rows in DeliveryQueue: {total_dq}")
    
    # 2. Check recipients in DeliveryQueue
    cursor.execute("SELECT id, board_id, post_num, recipients FROM DeliveryQueue LIMIT 10")
    print("\nDeliveryQueue recipients details:")
    for row in cursor.fetchall():
        dq_id, board_id, post_num, recipients_str = row
        try:
            recipients_list = json.loads(recipients_str)
            pos_rec = [uid for uid in recipients_list if uid > 0]
            neg_rec = [uid for uid in recipients_list if uid < 0]
            print(f"  ID: {dq_id}, Board: {board_id}, Post: {post_num}, Total: {len(recipients_list)} (Pos: {len(pos_rec)}, Neg: {len(neg_rec)})")
        except Exception as e:
            print(f"  Failed to parse recipients for ID {dq_id}: {e}")
            
    conn.close()

if __name__ == '__main__':
    main()
