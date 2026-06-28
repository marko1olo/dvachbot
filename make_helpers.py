import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

helpers = """
async def _delete_user_posts_from_db(user_id: int, time_threshold_ts: float, board_id: str) -> tuple[list[int], list, list]:
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        for attempt in range(10):
            try:
                db = await get_pool()
                await db.execute("BEGIN IMMEDIATE")

                query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
                async with db.execute(query_posts, (user_id, board_id, time_threshold_ts)) as cursor:
                    rows = await cursor.fetchall()
                user_posts = [row[0] for row in rows]

                if not user_posts:
                    await db.execute("COMMIT")
                    return [], [], []

                posts_to_delete_set = set(user_posts)
                threads_to_delete = []

                for p_num in user_posts:
                    p_str = str(p_num)
                    async with db.execute("SELECT thread_id FROM Threads WHERE thread_id = ? OR thread_num = ?", (p_str, p_num)) as cursor:
                        t_row = await cursor.fetchone()
                        if t_row:
                            threads_to_delete.append(t_row[0])

                if threads_to_delete:
                    for t_id in threads_to_delete:
                        try: t_id_int = int(t_id)
                        except ValueError: t_id_int = 0
                        async with db.execute("SELECT post_num FROM Posts WHERE thread_id = ? OR thread_id = ?", (t_id, str(t_id_int))) as cursor:
                            p_rows = await cursor.fetchall()
                            for pr in p_rows:
                                posts_to_delete_set.add(pr[0])

                posts_to_delete_nums = list(posts_to_delete_set)
                placeholders = ','.join('?' for _ in posts_to_delete_nums)

                query_copies = f\"\"\"
                    SELECT pc.recipient_id, pc.message_id, p.board_id
                    FROM PostCopies pc
                    JOIN Posts p ON pc.post_num = p.post_num
                    WHERE pc.post_num IN ({placeholders})
                \"\"\"
                async with db.execute(query_copies, posts_to_delete_nums) as cursor:
                    messages_to_delete_from_api = await cursor.fetchall()

                query_channels = f\"\"\"
                    SELECT cc.channel_id, cc.message_id, p.board_id
                    FROM ChannelCopies cc
                    JOIN Posts p ON cc.post_num = p.post_num
                    WHERE cc.post_num IN ({placeholders})
                \"\"\"
                async with db.execute(query_channels, posts_to_delete_nums) as cursor:
                    channel_messages_to_delete = await cursor.fetchall()

                await db.execute(f"DELETE FROM Posts WHERE post_num IN ({placeholders})", posts_to_delete_nums)
                await db.execute(f"DELETE FROM PostCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
                await db.execute(f"DELETE FROM ChannelCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
                await db.execute(f"DELETE FROM UserReplies WHERE post_num IN ({placeholders}) OR parent_num IN ({placeholders})", posts_to_delete_nums + posts_to_delete_nums)

                if threads_to_delete:
                    t_placeholders = ','.join('?' for _ in threads_to_delete)
                    await db.execute(f"DELETE FROM Threads WHERE thread_id IN ({t_placeholders})", threads_to_delete)

                await db.execute("COMMIT")
                return posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete

            except Exception as e:
                import asyncio
                try: await db.execute("ROLLBACK")
                except Exception: pass
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                print(f"⛔ DB Error in delete_user_posts: {e}")
                return [], [], []
    return [], [], []

async def _clean_posts_from_ram(posts_to_delete_nums: list[int], board_id: str):
    async with storage_lock:
        for post_num in posts_to_delete_nums:
            post_data = messages_storage.pop(post_num, None)
            if post_data:
                if board_id in THREAD_BOARDS:
                    thread_id = post_data.get('thread_id')
                    if thread_id:
                        b_data = board_data.get(board_id, {})
                        threads_data = b_data.get('threads_data', {})
                        if thread_id in threads_data:
                            try:
                                if 'posts' in threads_data[thread_id]:
                                    threads_data[thread_id]['posts'].remove(post_num)
                            except (ValueError, KeyError):
                                pass
            message_copies_in_mem = post_to_messages.pop(post_num, {})
            for uid, mid_or_list in message_copies_in_mem.items():
                if isinstance(mid_or_list, list):
                    for mid in mid_or_list:
                        message_to_post.pop((uid, mid), None)
                else:
                    message_to_post.pop((uid, mid_or_list), None)

def _clean_posts_from_caches(posts_to_delete_nums: list[int]):
    from common.database import _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE
    for post_id_int in posts_to_delete_nums:
        post_id_str = str(post_id_int)
        for b in list(_THREAD_CACHE.keys()):
            if post_id_str in _THREAD_CACHE[b]:
                try: _THREAD_CACHE[b].remove(post_id_str)
                except: pass
        for b in list(_VIDEO_CACHE.keys()):
            _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
        for b in list(_IMAGE_CACHE.keys()):
            _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]

async def _delete_posts_from_channels(channel_messages_to_delete: list, bot_instance):
    if not channel_messages_to_delete:
        return
    archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
    for chan_id, msg_id, b_id in channel_messages_to_delete:
        deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(b_id) or bot_instance)
        try:
            await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
        except Exception:
            pass

async def _delete_posts_from_pm_api(messages_to_delete_from_api: list, bot_instance) -> int:
    import asyncio
    CHUNK_SIZE = 47
    DELAY_BETWEEN_CHUNKS = 0.11
    total_deleted_count = 0
    for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
        chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
        tasks = [_delete_message_with_retries(bot_instance, uid, mid, b_id) for uid, mid, b_id in chunk]
        results = await asyncio.gather(*tasks)
        total_deleted_count += sum(1 for res in results if res is True)
        if i + CHUNK_SIZE < len(messages_to_delete_from_api):
            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
    return total_deleted_count
"""

content = content.replace("async def _delete_message_with_retries", helpers + "\nasync def _delete_message_with_retries")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
