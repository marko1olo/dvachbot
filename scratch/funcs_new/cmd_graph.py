@dp.message(Command("graph"))
async def cmd_graph(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not GRAPH_LIBS_AVAILABLE:
        if lang == 'en':
            error_text = "Graph generation module is not available (dependencies missing)."
        elif lang == 'jp':
            error_text = "グラフ生成モジュールが利用できません（依存関係が不足しています）。"
        else:
            error_text = "Модуль генерации графиков недоступен (отсутствуют зависимости)."
        try:
            await message.answer(error_text)
            await message.delete()
        except Exception: pass
        return
    INFO_CMD_COOLDOWN = 60
    # storage_lock убран как ложная зависимость: кулдаун в board_data, а лок
    # защищает messages_storage. Исключение уже даёт info_cmd_lock.
    remaining = 0
    async with info_cmd_lock:
        b_data = board_data[board_id]
        current_time = time.time()
        last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
        on_cooldown = current_time - last_usage < INFO_CMD_COOLDOWN
        if on_cooldown:
            remaining = int(INFO_CMD_COOLDOWN - (current_time - last_usage))
        else:
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    if on_cooldown:
        if lang == 'en':
            cooldown_text = f"⏳ You can use this command in {remaining} seconds."
        elif lang == 'jp':
            cooldown_text = f"⏳ このコマンドはあと {remaining} 秒後に使用できます。"
        else:
            cooldown_text = f"⏳ Команду можно использовать через {remaining} сек."
        try:
            sent_msg = await message.answer(cooldown_text)
            spawn_task(delete_message_after_delay(sent_msg, 5))
            await message.delete()
        except Exception: pass
        return
    args = (message.text or message.caption or "").split()
    days = 7  # По умолчанию 7 дней
    if len(args) > 1:
        arg = args[1].lower()
        if arg.endswith('d') and arg[:-1].isdigit():
            try:
                days = int(arg[:-1])
                days = max(1, min(30, days))
            except ValueError:
                import traceback; traceback.print_exc()
    working_msg = None
    try:
        await message.delete()
        if lang == 'en':
            working_text = "🎨 Drawing the graph..."
        elif lang == 'jp':
            working_text = "🎨 グラフを描画中..."
        else:
            working_text = "🎨 Рисую график..."
        working_msg = await message.answer(working_text)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(
            None,
            generate_statistics_graph,
            board_id,
            days
        )
        await working_msg.delete()
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename=f"graph_{board_id}_{days}d.png")
            await message.answer_photo(photo)
        else:
            if lang == 'en':
                no_data_text = "No data available to build a graph for this period."
            elif lang == 'jp':
                no_data_text = "この期間のグラフを作成するためのデータがありません。"
            else:
                no_data_text = "Нет данных для построения графика за этот период."
            await message.answer(no_data_text)
    except Exception as e:
        print(f"⛔ Ошибка в обработчике /graph: {e}")
        try:
            if working_msg:
                await working_msg.delete()
            if lang == 'en':
                error_text = "An error occurred while creating the graph."
            elif lang == 'jp':
                error_text = "グラフの作成中にエラーが発生しました。"
            else:
                error_text = "Произошла ошибка при создании графика."
            await message.answer(error_text)
        except Exception:
            import traceback; traceback.print_exc()