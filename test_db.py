import sqlite3

def create_db():
    conn = sqlite3.connect('dvach_bot.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("CREATE INDEX test_idx ON test_table (name)")
    for i in range(10001):
        cursor.execute("INSERT INTO test_table (name) VALUES ('test')")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    create_db()
