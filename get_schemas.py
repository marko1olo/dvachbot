import sqlite3
con = sqlite3.connect('dvach_bot.db')
print('Posts:')
print(con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Posts'").fetchone()[0])
print('\nPostCopies:')
print(con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='PostCopies'").fetchone()[0])
