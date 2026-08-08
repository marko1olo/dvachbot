import sqlite3
import json
import logging
from common.config import DB_NAME

logging.basicConfig(level=logging.INFO)

db_name = DB_NAME
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

cursor.execute("SELECT MAX(post_num) FROM Posts WHERE post_num < 100000000")
last_valid = cursor.fetchone()[0]
print(f"Last valid post_num: {last_valid}")

cursor.execute("SELECT post_num, content FROM Posts WHERE post_num >= 100000000 ORDER BY post_num ASC")
corrupted = cursor.fetchall()

if corrupted:
    new_start = last_valid + 1
    mapping = {}
    for i, (old_num, content) in enumerate(corrupted):
        new_num = new_start + i
        mapping[old_num] = new_num
    
    print(f"Mapping: {mapping}")
    
    for old_num, new_num in mapping.items():
        cursor.execute("UPDATE Posts SET post_num = ? WHERE post_num = ?", (new_num, old_num))
        cursor.execute("SELECT content FROM Posts WHERE post_num = ?", (new_num,))
        content_str = cursor.fetchone()[0]
        if content_str:
            try:
                data = json.loads(content_str)
                changed = False
                if data.get('post_num') == old_num:
                    data['post_num'] = new_num
                    changed = True
                if data.get('reply_to_post') in mapping:
                    data['reply_to_post'] = mapping[data['reply_to_post']]
                    changed = True
                
                # update header
                header = data.get('header', '')
                if str(old_num) in header:
                    data['header'] = header.replace(str(old_num), str(new_num))
                    changed = True

                if changed:
                    cursor.execute("UPDATE Posts SET content = ? WHERE post_num = ?", (json.dumps(data, ensure_ascii=False), new_num))
            except:
                pass

        cursor.execute("UPDATE PostCopies SET post_num = ? WHERE post_num = ?", (new_num, old_num))
        cursor.execute("UPDATE UserReplies SET post_num = ? WHERE post_num = ?", (new_num, old_num))
        cursor.execute("UPDATE UserReplies SET parent_num = ? WHERE parent_num = ?", (new_num, old_num))
        cursor.execute("UPDATE PostsFTS SET rowid = ? WHERE rowid = ?", (new_num, old_num))
        cursor.execute("UPDATE ChannelCopies SET post_num = ? WHERE post_num = ?", (new_num, old_num))
        cursor.execute("UPDATE Posts SET reply_to_post_num = ? WHERE reply_to_post_num = ?", (new_num, old_num))

    max_new_num = new_start + len(corrupted) - 1
    cursor.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'Posts'", (max_new_num,))
    
    conn.commit()
    print(f"Fixed! Next post will be {max_new_num + 1}")
else:
    print("No corrupted posts found.")
