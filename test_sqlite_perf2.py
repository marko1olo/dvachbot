import sqlite3
import time
from datetime import datetime

def setup_db():
    with sqlite3.connect("test2.db") as db:
        db.execute("CREATE TABLE IF NOT EXISTS Threads (board_id TEXT, thread_id TEXT, last_updated_at INTEGER)")
        db.execute("DELETE FROM Threads")
        rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(10000)]
        db.executemany("INSERT INTO Threads VALUES (?, ?, ?)", rows)
        db.commit()

def test_python_date():
    with sqlite3.connect("test2.db") as db:
        start_time = time.time()
        urls = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id, last_updated_at FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        cursor = db.execute(query)
        for row in cursor:
            bid, tid, ts = row
            date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

def test_sqlite_date():
    with sqlite3.connect("test2.db") as db:
        start_time = time.time()
        urls = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id, date(last_updated_at, 'unixepoch') as date_str FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        cursor = db.execute(query)
        for row in cursor:
            bid, tid, date_str = row
            urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

def test_no_date():
    with sqlite3.connect("test2.db") as db:
        start_time = time.time()
        urls = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id FROM Threads ORDER BY last_updated_at DESC LIMIT 10000"
        cursor = db.execute(query)
        for row in cursor:
            bid, tid = row
            urls.append(f"{base_url}/{bid}/res/{tid}.html")
        end_time = time.time()
        return end_time - start_time

def main():
    setup_db()
    t1 = test_python_date()
    t2 = test_sqlite_date()
    t3 = test_no_date()
    print(f"Python date conversion: {t1} seconds")
    print(f"SQLite date conversion: {t2} seconds")
    print(f"No date conversion: {t3} seconds")

main()
