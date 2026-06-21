import sqlite3

def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        cursor.execute(f"PRAGMA index_list({table});")
        indexes = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        if count > 10000:
            print(f"Table {table}: {count} rows")
            for idx in indexes:
                cursor.execute(f"PRAGMA index_info({idx[1]})")
                cols = [row[2] for row in cursor.fetchall()]
                print(f"  Index: {idx[1]} -> Columns: {cols}")

if __name__ == '__main__':
    check_indexes()
