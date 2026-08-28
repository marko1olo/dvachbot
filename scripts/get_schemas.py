import sqlite3
con = sqlite3.connect('dvach_bot.db', timeout=15.0)
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA busy_timeout=15000;")
print('Posts:')
print(con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Posts'").fetchone()[0])
print('\nPostCopies:')
print(con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='PostCopies'").fetchone()[0])
