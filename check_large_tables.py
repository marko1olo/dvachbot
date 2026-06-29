import re
import sqlite3

def get_table_count(cursor, table, allowed_tables):
    if table not in allowed_tables:
        raise ValueError(f"Invalid table name: {table}")
    safe_table = table.replace('"', '""')
    query = 'SELECT COUNT(*) FROM "' + safe_table + '"'
    cursor.execute(query)
    return cursor.fetchone()[0]

def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    allowed_tables = set(tables)
    
    for table in tables:
        if not re.match(r"^\w+$", table):
            continue
        cursor.execute("SELECT * FROM pragma_index_list(?)", (table,))
        indexes = cursor.fetchall()
        count = get_table_count(cursor, table, allowed_tables)
        if count > 10000:
            print(f"Table {table}: {count} rows")
            for idx in indexes:
                cursor.execute("SELECT * FROM pragma_index_info(?)", (idx[1],))
                cols = [row[2] for row in cursor.fetchall()]
                print(f"  Index: {idx[1]} -> Columns: {cols}")

if __name__ == '__main__':
    check_indexes()
