import re

with open('main.py', 'r') as f:
    content = f.read()

# We need to replace the body of edit_post_for_all_recipients.
new_function = """async def edit_post_for_all_recipients(post_num: int, bot_instance: Bot):
    \"\"\"
    Находит все отправленные копии поста и редактирует их.
    Основной источник данных - база данных.
    Версия 2.2: Добавлена группировка сообщений по юзерам (защита от мульти-эдита альбомов).
    \"\"\"
    user_messages_map = await _get_user_messages_map_for_edit(post_num)
    if not user_messages_map:
        return

    post_data_copy, content_copy, reply_author_id, board_id = await _get_post_data_for_edit(post_num)
    if not board_id:
        return

    final_keyboard = _build_edit_keyboard(content_copy, post_num)
    user_specific_texts = await _build_user_specific_texts(user_messages_map, content_copy, post_data_copy, board_id, reply_author_id)

    async def _edit_one(user_id: int, message_id: int):
        max_attempts = 6
        delay = 1.5
        for attempt in range(max_attempts):
            try:
                full_text = user_specific_texts.get(user_id, "")
                content_type = content_copy.get('type')
                if content_type == 'text':
                    if len(full_text) > 4096: full_text = full_text[:4093] + "..."
                    await bot_instance.edit_message_text(text=full_text, chat_id=user_id, message_id=message_id, parse_mode="HTML", reply_markup=final_keyboard)
                else:
                    if len(full_text) > 1024: full_text = full_text[:1021] + "..."
                    await bot_instance.edit_message_caption(caption=full_text, chat_id=user_id, message_id=message_id, parse_mode="HTML", reply_markup=final_keyboard)
                return
            except TelegramRetryAfter as e:
                wait_sec = e.retry_after + 1
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_sec)
                    continue
                else:
                    return
            except TelegramBadRequest as e:
                error_message_lower = e.message.lower()
                ignored_errors = ("message is not modified", "message to edit not found", "chat not found")
                if any(err in error_message_lower for err in ignored_errors):
                    return
                if "flood control" in error_message_lower or "retry after" in error_message_lower:
                    wait_sec = 3
                    match = re.search(r'retry after (\\d+)', error_message_lower)
                    if match:
                        wait_sec = int(match.group(1)) + 1
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(wait_sec)
                        continue
                    else:
                        return
                return
            except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 10)
                    continue
                else:
                    return
            except Exception as e:
                print(f"⚠️ Непредвиденная ошибка в _edit_one: {e}")
                return

    tasks_to_run = []
    for uid, msgs in user_messages_map.items():
        if msgs:
            target_mid = sorted(msgs)[0]
            task = spawn_task(_edit_one(uid, target_mid))
            tasks_to_run.append(task)

    CHUNK_SIZE = 30
    DELAY_BETWEEN_CHUNKS = 0.3
    for i in range(0, len(tasks_to_run), CHUNK_SIZE):
        chunk_tasks = tasks_to_run[i:i + CHUNK_SIZE]
        await asyncio.gather(*chunk_tasks, return_exceptions=True)
        if i + CHUNK_SIZE < len(tasks_to_run):
            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)"""

# regex replacement
start_str = r"async def edit_post_for_all_recipients\(post_num: int, bot_instance: Bot\):"
end_str = r"async def execute_delayed_edit"

match_start = re.search(start_str, content)
match_end = re.search(end_str, content)

if match_start and match_end:
    new_content = content[:match_start.start()] + new_function + "\n" + content[match_end.start():]
    with open('main.py', 'w') as f:
        f.write(new_content)
else:
    print("Failed to match")
