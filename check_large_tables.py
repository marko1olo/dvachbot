import re
import sqlite3
import json


def check_indexes():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()

    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor]

    valid_tables = [t for t in tables if re.match(r"^[a-zA-Z0-9_]+$", t)]

    if not valid_tables:
        return

    # Batch get indexes
    cursor.execute(
        "SELECT j.value, p.* FROM json_each(?) j "
        "CROSS JOIN pragma_index_list(j.value) p",
        (json.dumps(valid_tables),)
    )
    all_indexes_rows = cursor.fetchall()

    table_indexes = {t: [] for t in valid_tables}
    for row in all_indexes_rows:
        table_indexes[row[0]].append(row[1:])

    # Batch get counts
    table_counts = {}
    for i in range(0, len(valid_tables), 100):
        chunk = valid_tables[i:i + 100]
        query = " UNION ALL ".join(
            [f'SELECT "{t}" AS table_name, COUNT(*) AS count FROM "{t}"'
             for t in chunk]
        )
        try:
            cursor.execute(query)
            for row in cursor.fetchall():
                table_counts[row[0]] = row[1]
        except sqlite3.Error:
            for t in chunk:
                cursor.execute(f'SELECT COUNT(*) FROM "{t}"')  # nosec B608
                table_counts[t] = cursor.fetchone()[0]

    for table in valid_tables:
        count = table_counts.get(table, 0)
        indexes = table_indexes.get(table, [])
        if count > 10000:
            print(f"Table {table}: {count} rows")
            if indexes:
                index_names = [idx[1] for idx in indexes]
                cursor.execute(
                    "SELECT j.value, p.name FROM json_each(?) j "
                    "CROSS JOIN pragma_index_info(j.value) p",
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
