import asyncio
import time
import aiosqlite

async def run_benchmark():
    async with aiosqlite.connect(':memory:') as conn:
        await conn.execute('CREATE TABLE ChannelCopies (post_num INTEGER, channel_id TEXT, message_id INTEGER, PRIMARY KEY (post_num, channel_id, message_id))')

        prepared_posts = []
        id_map = {}
        for i in range(1000):
            p_data = {
                "old_id": str(i),
                "files": [
                    {"channel_message_id": i},
                    {"channel_message_id": i + 10000}
                ]
            }
            prepared_posts.append(p_data)
            id_map[str(i)] = i

        current_channel = "test_channel"

        # Current implementation (Individual executes)
        start_time = time.time()
        channel_copies_params = []
        for p_data in prepared_posts:
            p_num = id_map.get(p_data["old_id"])
            if not p_num:
                continue
            for f in p_data["files"]:
                if f.get("channel_message_id"):
                    channel_copies_params.append((p_num, current_channel, f["channel_message_id"]))

        if channel_copies_params:
            await conn.executemany(
                "INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)",
                channel_copies_params
            )
        await conn.commit()
        time_individual = time.time() - start_time
        print(f"Individual executes took {time_individual:.4f} seconds")

        await conn.execute('DELETE FROM ChannelCopies')
        await conn.commit()

        # Proposed implementation (executemany)
        start_time = time.time()

        channel_copies_params = []
        for p_data in prepared_posts:
            p_num = id_map.get(p_data["old_id"])
            if not p_num:
                continue
            for f in p_data["files"]:
                if f.get("channel_message_id"):
                    channel_copies_params.append((p_num, current_channel, f["channel_message_id"]))

        if channel_copies_params:
            await conn.executemany(
                "INSERT OR IGNORE INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)",
                channel_copies_params
            )
        await conn.commit()
        time_executemany = time.time() - start_time
        print(f"executemany took {time_executemany:.4f} seconds")
        print(f"Improvement: {time_individual / time_executemany:.2f}x faster")

asyncio.run(run_benchmark())
