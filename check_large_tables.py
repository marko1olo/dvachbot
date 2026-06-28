import sqlite3

def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        return

    large_tables = {}
    chunk_size = 500
    for i in range(0, len(tables), chunk_size):
        chunk = tables[i:i + chunk_size]
        query = " UNION ALL ".join([f"SELECT ?, COUNT(*) FROM \"{t}\"" for t in chunk])
        cursor.execute(query, chunk)
        for t, c in cursor.fetchall():
            if c > 10000:
                large_tables[t] = c

    for table in tables:
        if table in large_tables:
            count = large_tables[table]
            print(f"Table {table}: {count} rows")
            cursor.execute("SELECT * FROM pragma_index_list(?)", (table,))
            indexes = cursor.fetchall()
            for idx in indexes:
                cursor.execute("SELECT * FROM pragma_index_info(?)", (idx[1],))
                cols = [row[2] for row in cursor.fetchall()]
                print(f"  Index: {idx[1]} -> Columns: {cols}")

if __name__ == '__main__':
    check_indexes()
