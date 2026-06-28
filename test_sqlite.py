import sqlite3
def quote_identifier(s):
    return '"' + s.replace('"', '""') + '"'

conn = sqlite3.connect(':memory:')
conn.execute('CREATE TABLE "my "" table" ("my "" col" TEXT)')
conn.execute('INSERT INTO "my "" table" VALUES ("test")')
print(conn.execute(f"SELECT count(*) FROM {quote_identifier('my \" table')}").fetchone())
print(conn.execute(f"PRAGMA table_info({quote_identifier('my \" table')})").fetchall())
print(conn.execute(f"SELECT {quote_identifier('my \" col')} FROM {quote_identifier('my \" table')}").fetchall())
