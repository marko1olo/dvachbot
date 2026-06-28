import sqlite3
import json

def quote_identifier(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'

def main():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # 1. Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print("=== TABLE COUNTS ===")
    for table in tables:
        try:
            cursor.execute(f'SELECT count(*) FROM {quote_identifier(table)}')
            print(f"{table}: {cursor.fetchone()[0]} rows")
        except Exception as e:
            print(f"Error reading {table}: {e}")
            
    # 2. Get user subscription stats if there is a users/subscribers table
    print("\n=== USER STATUS INFO ===")
    for table in ['Users', 'users', 'Subscribers', 'subscribers']:
        if table in tables:
            try:
                cursor.execute(f"SELECT status, count(*) FROM {quote_identifier(table)} GROUP BY status")
                print(f"Status in {table}:")
                for row in cursor.fetchall():
                    print(f"  {row[0]}: {row[1]}")
            except Exception as e:
                pass
            
            try:
                cursor.execute(f"SELECT count(distinct user_id) FROM {quote_identifier(table)}")
                print(f"Unique users in {table}: {cursor.fetchone()[0]}")
            except Exception as e:
                pass

    # 3. Check what boards exist and how many subscribers each has
    print("\n=== BOARD SUBSCRIPTIONS ===")
    # Let's inspect columns of Users/Subscribers
    for table in ['Users', 'users']:
        if table in tables:
            cursor.execute(f"PRAGMA table_info({quote_identifier(table)})")
            cols = [col[1] for col in cursor.fetchall()]
            print(f"{table} columns: {cols}")
            
            # Let's see unique boards in user table if 'board' or 'board_id' exists
            board_col = next((c for c in cols if 'board' in c.lower()), None)
            if board_col:
                cursor.execute(f"SELECT {quote_identifier(board_col)}, count(*) FROM {quote_identifier(table)} GROUP BY {quote_identifier(board_col)}")
                print(f"Subscriptions by {board_col}:")
                for row in cursor.fetchall():
                    print(f"  {row[0]}: {row[1]}")
            else:
                print("No board column in Users")

if __name__ == '__main__':
    main()
