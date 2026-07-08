import random
from help_text import (
    generate_boards_list,
    HELP_TEXT_EN_COMMANDS,
    HELP_TEXT_JP_COMMANDS,
    HELP_TEXT_COMMANDS
)

async def setup_pinned_messages(bots: dict, board_data: dict, board_config: dict, thread_boards: list):
    for board_id, bot_instance in bots.items():
        b_data = board_data.get(board_id, {})
        languages = ['ru', 'en', 'jp']
        start_messages = {}
        for lang in languages:
            board_links = generate_boards_list(board_config, lang)
            if lang == 'en':
                base_help = random.choice(HELP_TEXT_EN_COMMANDS)
                boards_head = "🌐 <b>All boards:</b>"
                thread_info = (
                    "\n\n<b>This board supports threads!</b>\n"
                    "/create &lt;title&gt; - Create a new thread\n"
                    "/threads - View active threads\n"
                    "/leave - Return to the main board from a thread"
                ) if board_id in thread_boards else ""
            elif lang == 'jp':
                base_help = random.choice(HELP_TEXT_JP_COMMANDS)
                boards_head = "🌐 <b>全板一覧:</b>"
                thread_info = (
                    "\n\n<b>この板はスレッドに対応しています！</b>\n"
                    "/create &lt;タイトル&gt; - 新規スレ作成\n"
                    "/threads - スレ一覧を見る\n"
                    "/leave - スレから板に戻る"
                ) if board_id in thread_boards else ""
            else: # ru
                base_help = random.choice(HELP_TEXT_COMMANDS)
                boards_head = "🌐 <b>Все доски:</b>"
                thread_info = (
                    "\n\n<b>На этой доске есть треды!</b>\n"
                    "/create &lt;заголовок&gt; - Создать новый тред\n"
                    "/threads - Посмотреть активные треды\n"
                    "/leave - Вернуться на доску из треда"
                ) if board_id in thread_boards else ""
            full_text = f"{base_help}\n{thread_info}\n\n{board_links}"
            start_messages[lang] = full_text
        b_data['start_message_map'] = start_messages
        default_lang = 'en' if board_id == 'int' else 'ru'
        b_data['start_message_text'] = start_messages[default_lang]
        board_data[board_id] = b_data
        print(f"📌 [{board_id}] Тексты помощи (RU/EN/JP) подготовлены.")
