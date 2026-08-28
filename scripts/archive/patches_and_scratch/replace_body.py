import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

old_body_regex = r'async def delete_user_posts\(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str\) -> int:.*?(?=async def delete_single_post)'
new_body = """async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
    \"\"\"
    Массовое удаление постов пользователя за период.
    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
    \"\"\"
    try:
        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()

        posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete = await _delete_user_posts_from_db(
            user_id, time_threshold_ts, board_id
        )

        if not posts_to_delete_nums:
            return 0

        await _clean_posts_from_ram(posts_to_delete_nums, board_id)
        _clean_posts_from_caches(posts_to_delete_nums)
        await _delete_posts_from_channels(channel_messages_to_delete, bot_instance)
        total_deleted_count = await _delete_posts_from_pm_api(messages_to_delete_from_api, bot_instance)

        return total_deleted_count
    except Exception as e:
        import traceback
        print(f"Критическая ошибка в delete_user_posts: {e}\\n{traceback.format_exc()}")
        return 0
"""
content = re.sub(old_body_regex, new_body, content, flags=re.DOTALL)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
