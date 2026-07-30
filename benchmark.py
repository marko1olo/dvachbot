import sqlite3
import json
import time

def setup_db():
    conn = sqlite3.connect('bench.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, c0 TEXT)")

    # Create 100 columns
    for i in range(1, 100):
        try:
            cursor.execute(f"ALTER TABLE test_table ADD COLUMN c{i} TEXT")
        except:
            pass

    # Create 100 indexes
    for i in range(100):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{i} ON test_table (c{i})")

    for i in range(10001):
        pass # Not actually needed to measure pragma, just needs 10000 rows for the check_indexes script
    conn.commit()
    conn.close()

def bench_n_plus_1():
    conn = sqlite3.connect('bench.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pragma_index_list('test_table')")
    indexes = cursor.fetchall()

    start = time.time()
    for _ in range(100): # Run multiple times
        for idx in indexes:
            cursor.execute("SELECT * FROM pragma_index_info(?)", (idx[1],))
            cols = [row[2] for row in cursor]
            # print(f"  Index: {idx[1]} -> Columns: {cols}")
    end = time.time()
    print(f"N+1 time: {end-start:.4f}s")

def bench_batched():
    conn = sqlite3.connect('bench.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pragma_index_list('test_table')")
    indexes = cursor.fetchall()

    start = time.time()
    for _ in range(100): # Run multiple times
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
    end = time.time()
    print(f"Batched time: {end-start:.4f}s")

if __name__ == '__main__':
    setup_db()
    bench_n_plus_1()
    bench_batched()
