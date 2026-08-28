import sqlite3

def dump_schema():
    conn = sqlite3.connect('C:/Users/danat/Desktop/dvachbot/dvach_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    with open('schema_dump.sql', 'w', encoding='utf-8') as f:
        for name, sql in tables:
            if sql:
                f.write(f"{sql};\n\n")

if __name__ == '__main__':
    dump_schema()
