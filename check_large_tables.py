import re
import sqlite3
import json


def check_indexes():
    conn = sqlite3.connect("dvach_bot.db")
    cursor = conn.cursor()

    # Analyze table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor]
    valid_tables = [t for t in tables if re.fullmatch(r"[a-zA-Z0-9_]+", t)]

    query_indexes = (
        "SELECT j.value, p.seq, p.name, p.[unique], p.origin, p.partial "
        "FROM json_each(?) j CROSS JOIN pragma_index_list(j.value) p"
    )
    cursor.execute(query_indexes, (json.dumps(valid_tables),))
    table_indexes = {t: [] for t in valid_tables}
    for row in cursor.fetchall():
        table_indexes[row[0]].append(row[1:])

    counts = {}
    chunk_size = 100
    for i in range(0, len(valid_tables), chunk_size):
        chunk = valid_tables[i : i + chunk_size]
        q = " UNION ALL ".join(
            [f"SELECT '{t}', COUNT(*) FROM \"{t}\"" for t in chunk]  # nosec B608
        )
        try:
            cursor.execute(q)
            for row in cursor.fetchall():
                counts[row[0]] = row[1]
        except sqlite3.Error:
            for t in chunk:
                if not re.fullmatch(r"[a-zA-Z0-9_]+", t):
                    continue
                cursor.execute(f'SELECT COUNT(*) FROM "{t}"')  # nosec B608
                counts[t] = cursor.fetchone()[0]

    for table in valid_tables:
        count = counts.get(table, 0)
        if count > 10000:
            indexes = table_indexes.get(table, [])
            print(f"Table {table}: {count} rows")
            if indexes:
                index_names = [idx[1] for idx in indexes]
                query_info = (
                    "SELECT j.value, p.name FROM json_each(?) j "
                    "CROSS JOIN pragma_index_info(j.value) p"
                )
                cursor.execute(query_info, (json.dumps(index_names),))
                index_cols = {name: [] for name in index_names}
                for row in cursor.fetchall():
                    if row[1] is not None:
                        index_cols[row[0]].append(row[1])
                for idx in indexes:
                    cols = index_cols.get(idx[1], [])
                    print(f"  Index: {idx[1]} -> Columns: {cols}")


if __name__ == "__main__":
    check_indexes()
