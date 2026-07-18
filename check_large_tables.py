import re
import sqlite3
import json

def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    
    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        if not re.match(r"^\w+$", table):
            continue
        cursor.execute("SELECT * FROM pragma_index_list(?)", (table,))
        indexes = cursor.fetchall()
        safe_table = table.replace('"', '""')
        cursor.execute(f'SELECT COUNT(*) FROM "{safe_table}"')  # nosec B608
        count = cursor.fetchone()[0]
        if count > 10000:
            print(f"Table {table}: {count} rows")
            if indexes:
                index_names = [idx[1] for idx in indexes]
                cursor.execute(
                    "SELECT j.value, p.name FROM json_each(?) j CROSS JOIN pragma_index_info(j.value) p",
                    (json.dumps(index_names),)
                )
                index_cols = {name: [] for name in index_names}
                for row in cursor.fetchall():
                    if row[1] is not None:
                        index_cols[row[0]].append(row[1])
                for idx in indexes:
                    cols = index_cols.get(idx[1], [])
                    print(f"  Index: {idx[1]} -> Columns: {cols}")

if __name__ == '__main__':
    check_indexes()
