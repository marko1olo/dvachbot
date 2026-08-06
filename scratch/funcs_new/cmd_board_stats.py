@dp.message(Command("board_stats", "board_info", "bstats"))
async def cmd_board_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    INFO_CMD_COOLDOWN = 30
    # storage_lock убран: кулдаун в board_data, исключение даёт info_cmd_lock.
    async with info_cmd_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < INFO_CMD_COOLDOWN
        if not on_cooldown:
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    if on_cooldown:
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    
    wait_txt = "📊 Собираю статистику, вычисляю активность..." if lang != 'en' else "📊 Gathering statistics..."
    wait_msg = await message.answer(wait_txt)
    real_users_active = [uid for uid in b_data['users']['active'] if uid > 0]
    total_users_on_board = len(real_users_active)
    total_posts_on_board = b_data.get('board_post_count', 0)
    total_users_global = 0
    seen_users = set()
    for bid in BOARDS:
        for uid in board_data[bid]['users']['active']:
            if uid > 0: seen_users.add(uid)
    total_users_global = len(seen_users)
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        stats_text = (f"📊 Board Statistics {board_name}:\n\n"
                      f"👥 Anons on this board: {total_users_on_board}\n"
                      f"👥 Total anons in TGACH: {total_users_global}\n"
                      f"📨 Posts on this board: {total_posts_on_board}\n"
                      f"📈 Total posts in TGACH: {state['post_counter']}")
    elif lang == 'jp':
        stats_text = (f"📊 {board_name} の統計:\n\n"
                      f"👥 この板のアノン: {total_users_on_board}\n"
                      f"👥 全アノン数: {total_users_global}\n"
                      f"📨 この板のレス数: {total_posts_on_board}\n"
                      f"📈 総レス数: {state['post_counter']}")
    else:
        stats_text = (f"📊 Статистика доски {board_name}:\n\n"
                      f"👥 Анонимов на доске: {total_users_on_board}\n"
                      f"👥 Всего анонов в Тгаче: {total_users_global}\n"
                      f"📨 Постов на доске: {total_posts_on_board}\n"
                      f"📈 Всего постов в тгаче: {state['post_counter']}")
    try:
        await message.answer(stats_text, parse_mode="HTML")
    except Exception: pass
    try: await wait_msg.delete()
    except Exception: pass