import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Let's insert the new function before delete_user_posts
new_func = """async def _delete_message_with_retries(bot_instance, uid: int, mid: int, b_id: str = None) -> bool:
    deleter = GLOBAL_BOTS.get(b_id) or bot_instance if b_id else bot_instance
    max_attempts = 6
    delay = 1.5
    for attempt in range(max_attempts):
        try:
            await deleter.delete_message(uid, mid)
            return True
        except (TelegramBadRequest, TelegramForbiddenError):
            if deleter != bot_instance:
                try:
                    await bot_instance.delete_message(uid, mid)
                    return True
                except Exception:
                    pass
            for other_bid, other_bot in GLOBAL_BOTS.items():
                if other_bot != deleter and other_bot != bot_instance:
                    try:
                        await other_bot.delete_message(uid, mid)
                        return True
                    except Exception:
                        pass
            return False
        except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientOSError):
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            else:
                return False
        except Exception:
            return False
    return False

"""

content = content.replace("async def delete_user_posts", new_func + "async def delete_user_posts")

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
