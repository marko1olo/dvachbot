from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
import os
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional


from common.board_config import BOARD_CONFIG
import time
import logging

BOARDS = list(BOARD_CONFIG.keys())
message_queues = {board: asyncio.Queue(maxsize=0) for board in BOARDS}
runtime_logger = logging.getLogger('runtime')

is_shutting_down = False
drain_shutdown_requested = False
durable_delivery_stats = {
    'db_loads': 0,
    'failed_queue_upserts': 0,
    'failed_queue_deletes': 0,
    'invalid_recipients': 0,
}
weekly_active_users = {board: set() for board in BOARDS}


def _prepare_queue_item(board_id: str, item: dict) -> dict:
    if isinstance(item, dict):
        item.setdefault('board_id', board_id)
        item.setdefault('enqueued_at', time.time())
    return item

GLOBAL_BOTS = {} # Словарь для хранения всех экземпляров ботов

storage_lock = asyncio.Lock()  # Блокировка для доступа к messages_storage, post_to_messages и т.д.

board_data = defaultdict(lambda: {
    'anime_mode': False,
    'zaputin_mode': False,
    'slavaukraine_mode': False,
    'suka_blyat_mode': False,
    'polish_mode': False,
    'warhammer_mode': False,
    'imperial_mode': False,
    'gopnik_mode': False,
    'schizo_mode': False,
    'matrix_mode': False,
    'america_mode': False,
    'holiday_mode': False,
    'oldweb_mode': False,
    'jewish_mode': False,
    'last_suka_blyat': None,
    'suka_blyat_counter': 0,
    'last_mode_activation': None,
    'active_mode_task': None, # Хранит задачу на отключение текущего режима
    'last_deanon_time': 0, # Время последнего успешного вызова /deanon
    'last_summarize_time': 0, # Время последнего успешного вызова /summarize
    'last_roll_time': defaultdict(float), # Время последнего ролла для кулдауна рулетки
    'last_info_command_time': defaultdict(float), # Кулдаун для /stats, /active
    'last_texts': defaultdict(lambda: deque(maxlen=5)),
    'last_stickers': defaultdict(lambda: deque(maxlen=5)),
    'last_animations': defaultdict(lambda: deque(maxlen=5)),
    'last_audios': defaultdict(lambda: deque(maxlen=5)),
    'spam_violations': defaultdict(dict),
    'spam_tracker': defaultdict(list),
    'spam_filter_words': set(),
    'mutes': {},
    'shadow_mutes': {},
    'reaction_rate_tracker': defaultdict(lambda: deque(maxlen=5)), # Для глобального лимита скорости реакций
    'reaction_banned_users': set(), # Пользователи, которым запрещено ставить реакции
    'reaction_queue': defaultdict(deque), # Очередь post_num для отложенной обработки реакций
    'last_reaction_process_time': defaultdict(float), # Время последней обработки из очереди
    'users': {
        'active': set(),
        'banned': set()
    },
    'single_photo_counter': defaultdict(int), # Трекер для одиночных фото
    'last_photo_group_id': defaultdict(str),  # Чтобы отличать разные группы
    'user_settings': defaultdict(lambda: {'nsfw': False, 'hide': set(), 'lie_media': False}),
    'active_pin': None, 
    'message_counter': defaultdict(int),
    'last_user_msgs': {},
    'last_activity': {},
    'threads_data': {},  # {thread_id: {'op_id', 'title', ...}}
    'user_state': {},    # {user_id: {'location', 'last_seen_main', ...}}
    'thread_locks': defaultdict(asyncio.Lock), #  Словарь для блокировок тредов
    'anime_strict_limits': {5920818088}, # Список ID с жестким ограничением (ID спамера добавлен сразу)
    'anime_daily_tracker': defaultdict(lambda: {'count': 0, 'reset_at': 0.0}), # Суточный счетчик
})

state = {
    'post_counter': 0,
}

messages_storage = {}

post_to_messages = {}

message_to_post = {}

class BroadcastConfig:
    bot_instance: Bot
    board_id: str
    recipients: set
    content: dict
    reply_info: dict | None = None
    keyboard: InlineKeyboardMarkup | None = None
    verbose: bool = False
    queue_enqueued_at: float | None = None
    queue_wait_sec: float | None = None
    delivery_phase: str = "full"
    delivery_original_recipients: int | None = None
    delivery_deferred_recipients: int = 0


# --- Extracted from main.py (Phase 3) ---
THREAD_BOARDS = {'thread', 'test'} # Доски, на которых будет работать система тредов

locally_created_posts = deque(maxlen=500)

async def enqueue_board_message(board_id: str, item: dict) -> bool:
    """
    Кладёт сообщение в очередь доставки доски.

    Возвращает True при успехе. Неизвестная доска раньше давала голый KeyError:
    вызывающий код к этому моменту уже успевал записать пост в БД и
    messages_storage, поэтому пост оставался в базе, но никогда не доставлялся,
    а исключение рвало хендлер. Теперь это громкая запись в лог и False.
    """
    queue = message_queues.get(board_id)
    if queue is None:
        print(f"⛔ enqueue_board_message: неизвестная доска '{board_id}', "
              f"сообщение #{item.get('post_num') if isinstance(item, dict) else '?'} не поставлено в очередь.")
        runtime_logger.error(
            "enqueue_unknown_board board=%s post=%s known=%s",
            board_id,
            item.get("post_num") if isinstance(item, dict) else None,
            ",".join(sorted(message_queues)),
        )
        return False
    await queue.put(_prepare_queue_item(board_id, item))
    return True
current_deliveries = {}
pending_edit_tasks = {}  # Словарь для хранения активных задач редактирования {post_num: asyncio.Task}
pending_edit_lock = asyncio.Lock()
posts_pending_deletion = set()


# --- Archive Config ---
MIRROR_CHANNELS = [
    -1003549106152, 
    -1003651702446,
    -1003614166511, 
]

ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))

ARCHIVE_POSTING_BOT_ID = 'test' 

AUTHORIZED_ARCHIVE_BOTS = {'b', 'a', 'test', 'sex', 'int', 'po', 'vg', 'thread', 'meta', 'trash', 'ai', 'news', 'tech', 'me', 'sci', 'h', 'soc', 'bunker', 'fit', 'fa', 'biz', 'mu', 'tv', 'au', 'vt', 'x'}

SPECIAL_NUMERALS_CONFIG = {
    4: {'label': 'Квадрипл', 'emojis': ('🎯', '🚀', '🔥', '🍀')},
    5: {'label': 'Пентипл', 'emojis': ('🏆', '⭐', '🥇', '💫')},
    6: {'label': 'Секстипл', 'emojis': ('💎', '👑', ' JACKPOT ', '🤩')},
    7: {'label': 'Септипл', 'emojis': ('🤯', '🌌', '🌠', '🪐')},
    8: {'label': 'Октипл', 'emojis': ('🦄', '👽', '💠', '🔱')}
}


# --- Thread Pools ---
save_executor = ThreadPoolExecutor(max_workers=2)
