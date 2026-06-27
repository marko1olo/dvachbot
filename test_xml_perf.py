import sqlite3
import time

def setup_db():
    with sqlite3.connect("test3.db") as db:
        db.execute("CREATE TABLE IF NOT EXISTS Threads (board_id TEXT, thread_id TEXT, last_updated_at INTEGER)")
        db.execute("DELETE FROM Threads")
        rows = [(f"board_{i}", f"thread_{i}", 1700000000 + i) for i in range(15000)]
        db.executemany("INSERT INTO Threads VALUES (?, ?, ?)", rows)
        db.commit()

def test_sqlite_date_and_xml():
    with sqlite3.connect("test3.db") as db:
        start_time = time.time()
        xml_content = []
        base_url = "http://example.com"
        query = "SELECT board_id, thread_id, date(last_updated_at, 'unixepoch') as date_str FROM Threads ORDER BY last_updated_at DESC LIMIT 15000"
        cursor = db.execute(query)
        for row in cursor:
            bid, tid, mod_date = row
            xml_content.append(f'  <url><loc>{base_url}/{bid}/res/{tid}.html</loc><lastmod>{mod_date}</lastmod><changefreq>hourly</changefreq></url>')
        end_time = time.time()
        return end_time - start_time

def test_sqlite_xml_direct():
    with sqlite3.connect("test3.db") as db:
        start_time = time.time()
        xml_content = []
        base_url = "http://example.com"
        query = f"SELECT '  <url><loc>{base_url}/' || board_id || '/res/' || thread_id || '.html</loc><lastmod>' || date(last_updated_at, 'unixepoch') || '</lastmod><changefreq>hourly</changefreq></url>' FROM Threads ORDER BY last_updated_at DESC LIMIT 15000"
        cursor = db.execute(query)
        for row in cursor:
            xml_content.append(row[0])
        end_time = time.time()
        return end_time - start_time

def main():
    setup_db()
    t1 = test_sqlite_date_and_xml()
    t2 = test_sqlite_xml_direct()
    print(f"Fetch date and construct XML in Python: {t1} seconds")
    print(f"Construct XML directly in SQLite: {t2} seconds")

main()
