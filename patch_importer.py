import re

with open('Dubsite_tgach/importer.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''                unique_authors = set(p["author_id"] for p in prepared_posts)
                for uid in unique_authors:
                    await conn.execute("INSERT OR IGNORE INTO Users (user_id, board_id, stream) VALUES (?, ?, ?)", (uid, target_board, stream))'''

repl1 = '''                unique_authors = set(p["author_id"] for p in prepared_posts)
                users_data = [(uid, target_board, stream) for uid in unique_authors]
                if users_data:
                    await conn.executemany("INSERT OR IGNORE INTO Users (user_id, board_id, stream) VALUES (?, ?, ?)", users_data)'''

target2 = '''                for p_data in prepared_posts:
                    p_num = id_map.get(p_data["old_id"])
                    if not p_num: continue
                    for f in p_data["files"]:
                        if f.get('channel_message_id'):
                            await conn.execute("INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)", 
                                             (p_num, current_channel, f['channel_message_id']))'''

repl2 = '''                channel_copies_params = []
                for p_data in prepared_posts:
                    p_num = id_map.get(p_data["old_id"])
                    if not p_num: continue
                    for f in p_data["files"]:
                        if f.get('channel_message_id'):
                            channel_copies_params.append((p_num, current_channel, f['channel_message_id']))
                if channel_copies_params:
                    await conn.executemany("INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)", channel_copies_params)'''

if target1 in content:
    content = content.replace(target1, repl1)
    print("Patched target1")
if target2 in content:
    content = content.replace(target2, repl2)
    print("Patched target2")

with open('Dubsite_tgach/importer.py', 'w', encoding='utf-8') as f:
    f.write(content)
