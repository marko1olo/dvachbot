import sqlite3

def quote_identifier(s: str) -> str:
    """Safely quote SQL identifiers (table names, column names)."""
    return '"' + s.replace('"', '""') + '"'

def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        safe_table = quote_identifier(table)
        cursor.execute(f"PRAGMA index_list({safe_table});")  # nosec B608
        indexes = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) FROM {safe_table}")  # nosec B608
        count = cursor.fetchone()[0]
        if count > 10000:
            print(f"Table {table}: {count} rows")
            for idx in indexes:
                safe_idx = quote_identifier(idx[1])
                cursor.execute(f"PRAGMA index_info({safe_idx})")  # nosec B608
                cols = [row[2] for row in cursor.fetchall()]
                print(f"  Index: {idx[1]} -> Columns: {cols}")

if __name__ == '__main__':
    check_indexes()
