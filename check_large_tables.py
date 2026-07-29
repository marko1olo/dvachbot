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

    chunk_size = 100
    counts = {}
    indexes_by_table = {t: [] for t in valid_tables}

    for i in range(0, len(valid_tables), chunk_size):
        chunk = valid_tables[i:i+chunk_size]
        queries = [
            f'SELECT "{t}" AS table_name, COUNT(*) AS cnt FROM "{t}"'
            for t in chunk
        ]
        query = " UNION ALL ".join(queries)
        try:
            cursor.execute(query)
            for row in cursor.fetchall():
                counts[row[0]] = row[1]
        except Exception:
            for t in chunk:
                cursor.execute(f'SELECT COUNT(*) FROM "{t}"')  # nosec B608
                counts[t] = cursor.fetchone()[0]

        cursor.execute(
            "SELECT j.value, p.* FROM json_each(?) j "
            "CROSS JOIN pragma_index_list(j.value) p",
            (json.dumps(chunk),)
        )
        for row in cursor.fetchall():
            indexes_by_table[row[0]].append(row[1:])

    for table in valid_tables:
        count = counts.get(table, 0)
        indexes = indexes_by_table.get(table, [])
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
            for idx in indexes:
                cursor.execute("SELECT * FROM pragma_index_info(?)", (idx[1],))
                cols = [row[2] for row in cursor]
                print(f"  Index: {idx[1]} -> Columns: {cols}")


if __name__ == "__main__":
    check_indexes()
