with open("site_tgach/importer.py", "r") as f:
    content = f.read()

import re

search = """                for i in range(0, len(prepared_posts), chunk_size):
                    await conn.execute("BEGIN")
                    chunk = prepared_posts[i : i + chunk_size]
                    for p_data in chunk:
                        new_id = id_map[p_data["old_id"]]
                        original_text = p_data["text"]
                        if not original_text:
                            continue
                        fixed_text, reply_to_id = (
                            await self._fix_content_links_and_find_reply(
                                original_text, id_map
                            )
                        )
                        if fixed_text != original_text or reply_to_id is not None:
                            new_content_obj = {
                                "text": fixed_text,
                                "files": p_data["files"],
                                "type": "files" if p_data["files"] else "text",
                            }
                            await conn.execute(
                                "UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                                (json.dumps(new_content_obj), reply_to_id, new_id),
                            )

                            backlink_pairs = []
                            if reply_to_id:
                                backlink_pairs.append((reply_to_id, new_id))

                            refs = set(re.findall(r">>(\d+)", fixed_text))
                            for ref in refs:
                                try:
                                    target_id = int(ref)
                                    if target_id != new_id:
                                        backlink_pairs.append((target_id, new_id))
                                except:
                                    pass

                            if backlink_pairs:
                                await conn.executemany(
                                    "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                                    backlink_pairs,
                                )

                    await conn.commit()"""

replace = """                for i in range(0, len(prepared_posts), chunk_size):
                    await conn.execute("BEGIN")
                    chunk = prepared_posts[i : i + chunk_size]
                    update_queries = []
                    all_backlink_pairs = []
                    for p_data in chunk:
                        new_id = id_map[p_data["old_id"]]
                        original_text = p_data["text"]
                        if not original_text:
                            continue
                        fixed_text, reply_to_id = (
                            await self._fix_content_links_and_find_reply(
                                original_text, id_map
                            )
                        )
                        if fixed_text != original_text or reply_to_id is not None:
                            new_content_obj = {
                                "text": fixed_text,
                                "files": p_data["files"],
                                "type": "files" if p_data["files"] else "text",
                            }
                            update_queries.append(
                                (json.dumps(new_content_obj), reply_to_id, new_id)
                            )

                            if reply_to_id:
                                all_backlink_pairs.append((reply_to_id, new_id))

                            refs = set(re.findall(r">>(\d+)", fixed_text))
                            for ref in refs:
                                try:
                                    target_id = int(ref)
                                    if target_id != new_id:
                                        all_backlink_pairs.append((target_id, new_id))
                                except:
                                    pass

                    if update_queries:
                        await conn.executemany(
                            "UPDATE posts SET content = ?, reply_to_post_num = ? WHERE post_num = ?",
                            update_queries,
                        )
                    if all_backlink_pairs:
                        await conn.executemany(
                            "INSERT OR IGNORE INTO Backlinks (target_post_num, source_post_num) VALUES (?, ?)",
                            all_backlink_pairs,
                        )
                    await conn.commit()"""

if search in content:
    new_content = content.replace(search, replace)
    with open("site_tgach/importer.py", "w") as f:
        f.write(new_content)
    print("PATCH APPLIED SUCCESSFULLY")
else:
    print("FAILED TO FIND TARGET STRING IN ORIGIN/MAIN VERSION")
