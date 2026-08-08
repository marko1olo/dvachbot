import sqlite3
import time
conn = sqlite3.connect(r'C:\Users\danat\Desktop\dvachbot\dvach_bot.db')
cursor = conn.cursor()
fid = 'BAACAgIAAxkBAAFvspNqasDODXYAAcEVMqrRy7U6fg_lNuoAAr-rAAK6SFBLQd6XoElHgXo9BA'

# replace hyphens with spaces for fts matching if necessary
search_term = fid.replace('-', ' ')

start = time.time()
cursor.execute('SELECT rowid FROM PostsFTS WHERE content MATCH ?', (f'"{search_term}"',))
res = cursor.fetchall()
print(f'Found {len(res)} in {time.time()-start:.4f}s')
print(res)
