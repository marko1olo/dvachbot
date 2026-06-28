import re

def main():
    with open('main.py', 'r') as f:
        content = f.read()

    func_match = re.search(
        r'@dp\.message\(F\.text\.regexp\(rf"\^/\({\'\|\'\.join\(ANIME_COMMAND_MAP\.keys\(\)\)}\)"\)\)\nasync def handle_stacked_anime_commands\(message: types\.Message, board_id: str \| None, stream: str = \'ru\'\):(.*?)\n    await _process_stacked_anime_command\(\n        message=message,\n        board_id=board_id,\n        fetcher_tasks=fetcher_tasks,\n        caption=final_caption,\n        stream=stream\n    \)\n',
        content,
        re.DOTALL
    )

    if not func_match:
        print("Function not found!")
        return

    original_code = func_match.group(0)
    print("Found original code, length:", len(original_code))

    new_code = """async def _check_anime_limits(
    user_id: int, board_id: str, b_data: dict, requested_count: int,
    matches: list, max_images_for_board: int, lang: str,
    current_time: float, message: types.Message
) -> bool:
    # Проверка жесткого лимита (10 картинок в 24ч) для особых спамеров
    if user_id in b_data.get('anime_strict_limits', set()):
        tracker = b_data['anime_daily_tracker'][user_id]
        if current_time > tracker['reset_at']:
            tracker['count'] = 0
            tracker['reset_at'] = current_time + 86400

        if tracker['count'] + requested_count > 10:
            if lang == 'en':
                msg = "🛑 Strict limit! You are allowed only 10 images per 24h. Contact admin."
            elif lang == 'jp':
                msg = "🛑 制限中！24時間に10枚までです。管理人に連絡してください。"
            else:
                msg = "🛑 У вас жесткое ограничение: 10 картинок в сутки. Заебал спамить! По всем вопросам к админу."
            try:
                sent = await message.answer(msg)
                spawn_task(delete_message_after_delay(sent, 15))
                await message.delete()
            except Exception: pass
            return True
        tracker['count'] += requested_count

    if user_hourly_image_count[user_id] + requested_count > HOURLY_IMAGE_LIMIT:
        if lang == 'en': phrases = ANIME_HOURLY_LIMIT_PHRASES['en']
        elif lang == 'jp': phrases = ANIME_HOURLY_LIMIT_PHRASES['jp']
        else: phrases = ANIME_HOURLY_LIMIT_PHRASES['ru']

        limit_msg = random.choice(phrases)
        try:
            sent = await message.answer(limit_msg)
            spawn_task(delete_message_after_delay(sent, 15))
            await message.delete()
        except Exception: pass
        return True

    user_hourly_image_count[user_id] += requested_count

    if board_id == 'b':
        image_spam_tracker[board_id] = [t for t in image_spam_tracker[board_id] if current_time - t < IMAGE_SPAM_WINDOW]
        total_requested_images = 0
        for _, num_no_space, num_with_space in matches:
            count = 1
            number_str = num_no_space or num_with_space
            if number_str and number_str.strip().isdigit():
                count = int(number_str.strip())
            total_requested_images += count
        total_requested_images = min(total_requested_images, max_images_for_board)

        if len(image_spam_tracker[board_id]) + total_requested_images > IMAGE_SPAM_LIMIT:
            if lang == 'en':
                phrases_cd = ANIME_CMD_COOLDOWN_PHRASES_EN
                phrases_spam = IMAGE_SPAM_COOLDOWN_PHRASES_EN
            elif lang == 'jp':
                phrases_cd = ANIME_CMD_COOLDOWN_PHRASES_JP
                phrases_spam = IMAGE_SPAM_COOLDOWN_PHRASES_JP
            else:
                phrases_cd = ANIME_CMD_COOLDOWN_PHRASES
                phrases_spam = IMAGE_SPAM_COOLDOWN_PHRASES
            part1 = random.choice(phrases_cd)
            part2 = random.choice(phrases_spam).format(
                limit=IMAGE_SPAM_LIMIT,
                minutes=IMAGE_SPAM_WINDOW // 60
            )
            cooldown_msg = f"{part1}\\n\\n{part2}"
            try:
                sent_msg = await message.answer(cooldown_msg)
                spawn_task(delete_message_after_delay(sent_msg, 10))
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError): pass
            return True

    return False

def _prepare_fetcher_tasks(matches: list, max_images_for_board: int) -> tuple[list, dict]:
    fetcher_tasks = []
    command_counts = defaultdict(int)

    canonical_map = {
        **{k: 'fap' for k in ["fap", "hent", "hentai", "hentay", "nsfw", "FAP", "HENT", "HENTAI", "HENTAY", "NSFW"]},
        **{k: 'gatari' for k in ["gatari", "monogatari", "GATARI"]},
        **{k: 'loli' for k in ["loli", "lolicon", "lolis", "LOLI", "LOLICON", "LOLIS"]},
    }

    for command, num_no_space, num_with_space in matches:
        count = 1
        number_str = num_no_space or num_with_space
        if number_str and number_str.strip().isdigit():
            count = int(number_str.strip())

        command_lower = command.lower()
        cmd_func = ANIME_COMMAND_MAP.get(command_lower)
        if not cmd_func: continue

        for _ in range(count):
            if len(fetcher_tasks) < max_images_for_board:
                fetcher_tasks.append(cmd_func)
                canonical_name = canonical_map.get(command_lower.split('@')[0])
                if canonical_name:
                    command_counts[canonical_name] += 1
            else:
                break
        if len(fetcher_tasks) >= max_images_for_board:
            break

    return fetcher_tasks, command_counts

def _generate_anime_caption(final_caption: str, command_counts: dict, lang: str) -> str:
    if not final_caption and random.random() < 0.30 and command_counts:
        population = list(command_counts.keys())
        weights = list(command_counts.values())
        chosen_category = random.choices(population, weights=weights, k=1)[0]

        # Выбор фраз с учетом языка
        phrase_list = []
        if chosen_category == 'fap':
            if lang == 'en': phrase_list = FAP_SUCCESS_PHRASES_EN
            elif lang == 'jp': phrase_list = FAP_SUCCESS_PHRASES_JP
            else: phrase_list = FAP_SUCCESS_PHRASES
        elif chosen_category == 'gatari':
            if lang == 'en': phrase_list = GATARI_SUCCESS_PHRASES_EN
            elif lang == 'jp': phrase_list = GATARI_SUCCESS_PHRASES_JP
            else: phrase_list = GATARI_SUCCESS_PHRASES
        elif chosen_category == 'loli':
            if lang == 'en': phrase_list = LOLI_SUCCESS_PHRASES_EN
            elif lang == 'jp': phrase_list = LOLI_SUCCESS_PHRASES_JP
            else: phrase_list = LOLI_SUCCESS_PHRASES

        if phrase_list:
            random_phrase = random.choice(phrase_list)
            final_caption = f"<i>{escape_html(random_phrase)}</i>"
    return final_caption

@dp.message(F.text.regexp(rf"^/({'|'.join(ANIME_COMMAND_MAP.keys())})"))
async def handle_stacked_anime_commands(message: types.Message, board_id: str | None, stream: str = 'ru'):
    \"\"\"
    Универсальный обработчик для всех аниме-команд.
    Исправлена ошибка NameError: b_data теперь гарантированно определяется.
    \"\"\"
    if not board_id:
        return

    # ЯВНОЕ ОПРЕДЕЛЕНИЕ b_data (Исправление ошибки)
    b_data = board_data[board_id]

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    MAX_IMAGES = 10
    max_images_for_board = B_MAX_STACKED_ANIME_IMAGES if board_id == 'b' else MAX_IMAGES
    command_keys = '|'.join(ANIME_COMMAND_MAP.keys())
    pattern = re.compile(rf"/({command_keys})(?:(\d+)|(?:\s+(\d+)))?", re.IGNORECASE)
    matches = pattern.findall(message.text or "")
    if not matches: return

    user_id = message.from_user.id
    current_time = time.time()

    if current_time - user_hourly_image_reset[user_id] > 3600:
        user_hourly_image_count[user_id] = 0
        user_hourly_image_reset[user_id] = current_time

    raw_requested_count = 0
    for _, num_no_space, num_with_space in matches:
        count = 1
        number_str = num_no_space or num_with_space
        if number_str and number_str.strip().isdigit():
            count = int(number_str.strip())
        raw_requested_count += count
    requested_count = min(raw_requested_count, max_images_for_board)
    if raw_requested_count > max_images_for_board:
        runtime_logger.warning(
            "anime_request_capped %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "board_id": board_id,
                    "user_id": user_id,
                    "requested": raw_requested_count,
                    "accepted": requested_count,
                    "cap": max_images_for_board,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    if await _check_anime_limits(user_id, board_id, b_data, requested_count, matches, max_images_for_board, lang, current_time, message):
        return

    fetcher_tasks, command_counts = _prepare_fetcher_tasks(matches, max_images_for_board)

    if not fetcher_tasks:
        return

    if board_id == 'b':
        current_time = time.time()
        for _ in range(len(fetcher_tasks)):
            image_spam_tracker[board_id].append(current_time)

    final_caption = pattern.sub('', message.text or "").strip()
    final_caption = _generate_anime_caption(final_caption, command_counts, lang)

    await _process_stacked_anime_command(
        message=message,
        board_id=board_id,
        fetcher_tasks=fetcher_tasks,
        caption=final_caption,
        stream=stream
    )
"""
    new_content = content.replace(original_code, new_code)
    with open('main.py', 'w') as f:
        f.write(new_content)
    print("Replaced successfully!")

if __name__ == '__main__':
    main()
