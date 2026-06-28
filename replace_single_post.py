import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# First, remove the _delete_one_message inline func and the subsequent tasks gathering block inside delete_single_post

old_body = r'''    async def _delete_one_message\(uid: int, mid: int\) -> bool:.*?return deleted_count'''

new_body = r'''    tasks = [_delete_message_with_retries(bot_instance, uid, mid, board_id) for uid, mid in messages_to_delete_info]
    results = await asyncio.gather(*tasks)
    deleted_count = sum(1 for res in results if res is True)
    return deleted_count'''

content = re.sub(old_body, new_body, content, flags=re.DOTALL)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
