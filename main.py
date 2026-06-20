from __future__ import annotations
"""
This module contains the main functionality for a Telegram bot that interacts with a specific board system.
It includes various middleware classes for handling user streams, deduplication of messages, and board identification.
The bot supports multiple languages and has features for managing threads, posts, and user interactions.
Key Components:
asses:
Key Components:ware: Determines the user's language stream and caches it.
- Middleware Classes:.
    - MultiLangMiddleware: Determines the user's language stream and caches it.ned users.
    - DeduplicationMiddleware: Prevents duplicate messages from being processed.
    - Constants for board settings, data directories, and thresholds for notifications and actions.
    - Database configurations and connection management.
- Command Handling:
    - Regex patterns for parsing commands and user inputs related to anime and posts.
    - Command cooldowns and limits for user actions.
- Data Management:
    - Structures for caching recent messages, managing user states, and handling database interactions.
    - Functions for generating unique tokens and managing user streams.
- External Libraries:
    - Integration with various libraries for image processing, database management, and asynchronous operations.
This module is designed to be extensible and maintainable, allowing for future enhancements and modifications.
"""
import asyncio
import faulthandler
import gc
import gzip
import psutil
import json
import logging
import os
import tracemalloc
import uuid
import pickle
import math
import tempfile
import random
import re
import secrets
import html
import shutil
import signal
import subprocess
import sys
import io
import glob
import time
import textwrap
import threading
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from asyncio import Semaphore
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, UTC
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Tuple
from dotenv import load_dotenv
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from common.html_utils import escape_html
from common.token_generator import generate_unique_token
from common.database import (
    initialize_database, is_database_migrated, load_state_from_db, get_and_clear_reaction_queue, get_post_by_num, get_stream_active_users, 
    update_board_settings, add_or_activate_user, update_user_status, get_and_clear_broadcast_queue, mark_broadcast_posts_sent, get_channel_message_id,
    create_post, update_shadow_mute, create_thread, update_user_location, get_op_posts_for_board, get_thread_by_op_post, add_channel_copy, get_all_channel_copies,
    add_post_copies, get_post_author_by_copy, get_post_copies, get_post_info_by_copy, update_user_settings_db, get_all_active_subscribers, log_global_event,
    upsert_delivery_queue_item, delete_delivery_queue_item, get_pending_delivery_queue_items,
    get_posts_from_broadcast_queue, cleanup_broadcast_queue, get_or_create_api_token, get_user_by_token, remove_regular_mute, apply_regular_mute,
    get_and_clear_notification_queue, search_posts, update_post_content, remove_user_from_board, cleanup_old_posts_from_db, find_post_by_file_id,
    load_all_spam_words, add_spam_word, remove_spam_word, delete_post_by_num, add_reaction_ban, remove_reaction_ban, load_all_reaction_bans, set_channel_message_id, get_max_post_num, get_weekly_active_users, get_reply_coverage_stats,
    get_random_video_post, get_random_image_post
)
from site_tgach.admin_config import ADMIN_IDS
from backup_manager import create_gzipped_dump
from common.db_pool import create_pool, close_pool, get_pool
from common.secret_redaction import add_secret_redaction_filter, install_logging_redaction
from text_assets import (
    CASINO_FUCK_OFF_PHRASES, CASINO_FUCK_OFF_PHRASES_EN, CASINO_FUCK_OFF_PHRASES_JP,
    DVACH_STATS_CAPTIONS, DVACH_STATS_CAPTIONS_EN, DVACH_STATS_CAPTIONS_JP,
    ANIME_CMD_COOLDOWN_PHRASES, ANIME_CMD_COOLDOWN_PHRASES_EN, ANIME_CMD_COOLDOWN_PHRASES_JP,
    ANIME_CMD_SEARCHING_PHRASES, ANIME_CMD_SEARCHING_PHRASES_EN, ANIME_CMD_SEARCHING_PHRASES_JP,
    IMAGE_SPAM_COOLDOWN_PHRASES, IMAGE_SPAM_COOLDOWN_PHRASES_EN, IMAGE_SPAM_COOLDOWN_PHRASES_JP,
    ANIME_CMD_SUCCESS_PHRASES, ANIME_CMD_SUCCESS_PHRASES_EN, ANIME_CMD_SUCCESS_PHRASES_JP,
    FAP_SUCCESS_PHRASES, FAP_SUCCESS_PHRASES_EN, FAP_SUCCESS_PHRASES_JP,
    GATARI_SUCCESS_PHRASES, GATARI_SUCCESS_PHRASES_EN, GATARI_SUCCESS_PHRASES_JP,
    LOLI_SUCCESS_PHRASES, LOLI_SUCCESS_PHRASES_EN, LOLI_SUCCESS_PHRASES_JP,
    DEANON_COOLDOWN_PHRASES, DEANON_COOLDOWN_PHRASES_EN, DEANON_COOLDOWN_PHRASES_JP,
    MOTIVATIONAL_MESSAGES, MOTIVATIONAL_MESSAGES_EN, MOTIVATIONAL_MESSAGES_JP,
    INVITE_TEXTS, INVITE_TEXTS_EN, INVITE_TEXTS_JP,
    POLL_CREATION_SUCCESS_PHRASES, POLL_CREATION_SUCCESS_PHRASES_EN, POLL_CREATION_SUCCESS_PHRASES_JP,
    POLL_VOTE_SUCCESS_PHRASES, POLL_VOTE_SUCCESS_PHRASES_EN, POLL_VOTE_SUCCESS_PHRASES_JP,
    SUMMARIZE_PROMPTS_BOARD, SUMMARIZE_PROMPTS_BOARD_EN, SUMMARIZE_PROMPTS_BOARD_JP,
    CONTEXTUAL_REPLIES, CONTEXTUAL_REPLIES_EN, CONTEXTUAL_REPLIES_JP,
    REACTION_NOTIFY_PHRASES, REACTION_NOTIFY_PHRASES_JP, ALBUM_EDUCATION_PHRASES, ANIME_HOURLY_LIMIT_PHRASES,
    SITE_PROMO_PHRASES, SITE_PROMO_PHRASES_EN, SITE_PROMO_PHRASES_JP, EARNING_NOTIFICATIONS,
    WITHDRAWAL_SCENARIOS, SCAM_PROCESSING_STATUSES, PROGRESS_BARS, PUBLIC_SHAME_MESSAGES,
    SUPPORT_RESPONSES, FAKE_CRYPTO_RATES, METHOD_LABELS, REFERRAL_BONUS_MESSAGES, 
    VERIFICATION_SUCCESS_MESSAGES, VERIFICATION_REQUIRED_MESSAGES
)
from contextual_flavor import install_contextual_reply_extensions
from common.config import DB_POST_LIMIT as CONFIG_DB_POST_LIMIT
from common.config import BOT_POST_CACHE_LIMIT as CONFIG_BOT_POST_CACHE_LIMIT
from common.config import BOT_COPY_CACHE_POST_LIMIT as CONFIG_BOT_COPY_CACHE_POST_LIMIT
from common.config import ENABLE_MULTILANG
from common.config import (
    BOT_PRIORITY_DELIVERY,
    BOT_WEEKLY_ACTIVE_DAYS,
    BOT_WEEKLY_ACTIVE_REFRESH_SEC,
    BOT_PRIORITY_SPLIT_FANOUT,
    BOT_PRIORITY_SPLIT_MIN_PASSIVE,
    BOT_PRIORITY_PASSIVE_SLICE_SIZE,
    BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE,
    BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC,
    BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE,
    BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE,
    BOT_PASSIVE_MAX_PREEMPTIONS,
    BOT_PRIORITY_PHASE_BUDGET_SEC,
    BOT_PASSIVE_PHASE_BUDGET_SEC,
    BOT_DELIVERY_SLOW_PHASE_SEC,
    BOT_DELIVERY_INITIAL_CHUNK_SIZE,
    BOT_DELIVERY_MIN_CHUNK_SIZE,
    BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC,
    BOT_DELIVERY_MAX_RECIPIENT_RETRIES,
    BOT_DELIVERY_PHASE_GUARD_SEC,
    BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC,
    BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC,
    BOT_DURABLE_DELIVERY_QUEUE,
    BOT_B_MAX_STACKED_ANIME_IMAGES,
    BOT_ANIME_MEDIA_CONCURRENCY,
    BOT_ANIME_URL_FETCH_TIMEOUT_SEC,
    BOT_ANIME_URL_FETCH_TOTAL_SEC,
    BOT_ANIME_URL_FETCH_PARALLEL,
    BOT_ANIME_DOWNLOAD_TIMEOUT_SEC,
    BOT_ANIME_DOWNLOAD_TOTAL_SEC,
    BOT_ANIME_DOWNLOAD_PARALLEL,
    BOT_ANIME_REFILL_ROUNDS,
    BOT_MODE_PUNCHUP_ENABLED,
    BOT_MODE_PUNCHUP_QUEUE_SHED_SEC,
    BOT_MODE_PUNCHUP_SLOW_LOG_US,
    BOT_CONTEXTUAL_REPLIES_ENABLED,
    BOT_CONTEXTUAL_REPLY_COOLDOWN_SEC,
    BOT_CONTEXTUAL_REPLY_DAILY_LIMIT,
)
install_contextual_reply_extensions(CONTEXTUAL_REPLIES)
from common.database import get_user_stream, set_user_stream
from common.config import DB_NAME as DB_PATH_CONFIG
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramConflictError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio, BufferedInputFile, InputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
# Определяем состояния для машины состояний
class WithdrawalStates(StatesGroup):
    choosing_method = State()
    entering_data = State()
    processing = State() # Фейковое состояние для анимации
try:
    import aiosqlite
except ImportError:
    print("Библиотека aiosqlite не установлена. Пожалуйста, установите ее: pip install aiosqlite")
    sys.exit(1)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
time.sleep(2)
import deanonymizer
from deanonymizer import (
    DEANON_CITIES,
    DEANON_DETAILS,
    DEANON_FETISHES,
    DEANON_PROFESSIONS,
    DEANON_SURNAMES,
    generate_deanon_info,
)
from help_text import (
    HELP_TEXT_COMMANDS, HELP_TEXT_EN_COMMANDS, HELP_TEXT_JP_COMMANDS,
    generate_boards_list,
    THREAD_PROMO_TEXT_RU, THREAD_PROMO_TEXT_EN, THREAD_PROMO_TEXT_JP,
    MODE_INFO_TEXT_RU, MODE_INFO_TEXT_EN, MODE_INFO_TEXT_JP,
    MECHANICS_INFO_TEXT_RU, MECHANICS_INFO_TEXT_EN, MECHANICS_INFO_TEXT_JP,
    CHANNEL_PROMO_TEXT_RU, CHANNEL_PROMO_TEXT_EN, CHANNEL_PROMO_TEXT_JP
)
from japanese_translator import (
    anime_transform, get_random_anime_image, get_monogatari_image, 
    get_nsfw_anime_image, get_loli_image, get_dynamic_proxy_url,
    _get_proxy_usage_strategy, _update_proxy_state_on_failure
)
from summarize import summarize_text_with_hf
from thread_texts import thread_messages
from ukrainian_mode import UKRAINIAN_PHRASES, ukrainian_transform
from zaputin_mode import PATRIOTIC_PHRASES, zaputin_transform
from polish_mode import POLISH_PHRASES_START, POLISH_PHRASES_END, polish_transform
from warhammer_mode import WH40K_PHRASES_START, WH40K_PHRASES_END, warhammer_transform
from imperial_mode import IMPERIAL_PHRASES_START, IMPERIAL_PHRASES_END, imperial_transform
from gopnik_mode import GOPNIK_PHRASES_START, GOPNIK_PHRASES_END, gopnik_transform
from shizo_mode import SCHIZO_PHRASES_START, SCHIZO_PHRASES_END, shizo_transform
# )
from mode_punchup import punch_up_mode_text
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Dict, Any, Awaitable, Optional
from roulette_logic import load_roulette_data, get_random_event, ROULETTE_COOLDOWN_PHRASES, ROULETTE_RESULT_PHRASES
try:
    import pandas as pd
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import MaxNLocator, FuncFormatter
    matplotlib.use('Agg')  # Используем бэкенд, не требующий GUI
    GRAPH_LIBS_AVAILABLE = True
except ImportError:
    GRAPH_LIBS_AVAILABLE = False
ANIME_COMMAND_MAP = {
    "fap": get_random_anime_image,
    "Fap": get_random_anime_image,
    "FAP": get_random_anime_image,
    "hent": get_random_anime_image,
    "hentai": get_random_anime_image,
    "hentay": get_random_anime_image,
    "Hent": get_random_anime_image,
    "Hentai": get_random_anime_image,
    "Hentay": get_random_anime_image,
    "nsfw": get_nsfw_anime_image,
    "NSFW": get_nsfw_anime_image,
    "Nsfw": get_nsfw_anime_image,
    "gatari": get_monogatari_image,
    "monogatari": get_monogatari_image,
    "Monogatari": get_monogatari_image,
    "MONOGATARI": get_monogatari_image,
    "Gatari": get_monogatari_image,
    "loli": get_loli_image,
    "lolicon": get_loli_image,
    "lolis": get_loli_image,
    "Loli": get_loli_image,
    "Lolicon": get_loli_image,
    "Lolis": get_loli_image,
    "LOLI": get_loli_image,
    "LOLICON": get_loli_image,
    "LOLIS": get_loli_image,
}
RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_YOU_PATTERN = re.compile(r">>(\d+)")
RE_SCRIPT_TAG = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_SCRIPT_SINGLE = re.compile(r'<\s*script\b[^>]*>', flags=re.IGNORECASE)
RE_DANGEROUS_TAGS = re.compile(r'<\s*(iframe|svg|form|object|embed|link|a)\b[^>]*>.*?<\s*/\s*\1\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_DANGEROUS_SINGLE = re.compile(r'<\s*(iframe|svg|form|object|embed|link|a)\b[^>]*>', flags=re.IGNORECASE)
RE_EVENT_HANDLERS = re.compile(r'\s+on\w+\s*=\s*["\'].*?["\']', flags=re.IGNORECASE)
RE_POST_HEADER_CLEAN = re.compile(r'^(Пост №\d+.*?\n|Post No\.\d+.*?\n)', flags=re.MULTILINE)
RE_SYSTEM_HEADER_CLEAN = re.compile(r'^(###.*?###|<i>.*?</i>)\s*\n?', flags=re.MULTILINE)
RE_NEWLINES = re.compile(r'\n{2,}')
RE_ANIME_CMD = re.compile(rf"^/({'|'.join(ANIME_COMMAND_MAP.keys())})", re.IGNORECASE)
RE_ANIME_STACK = re.compile(rf"/({'|'.join(ANIME_COMMAND_MAP.keys())})(?:(\d+)|(?:\s+(\d+)))?", re.IGNORECASE)
RE_REPLY_QUOTE = re.compile(r'(Пост №|Post No\.)(<[^>]+>)*(\s*<[^>]+>)*(\d+)')
RE_REPLY_QUOTE_FORMAT = re.compile(r'(Пост №|Post No\.)(<[^>]+>)*(\s*<[^>]+>)*(\d+)')
RE_MULTI_REPLY = re.compile(r'>>(\d+)')
FONTS_CACHE = []
try:
    font_files = ["font1.ttf", "font2.ttf", "font3.ttf", "font4.ttf"]
    for ff in font_files:
        if os.path.exists(ff):
            FONTS_CACHE.append(ImageFont.truetype(ff, 40))
    if not FONTS_CACHE:
        FONTS_CACHE.append(ImageFont.load_default())
except Exception:
    FONTS_CACHE.append(ImageFont.load_default())
class MultiLangMiddleware(BaseMiddleware):
    """
    Определяет языковой поток пользователя (ru/en/jp).
    Использует кэш внутри board_data для автоматической очистки.
    """
    async def __call__(self, handler, event, data):
        stream = 'ru'
        if ENABLE_MULTILANG:
            user = data.get('event_from_user')
            if user:
                board_id = data.get('board_id', 'b')
                b_data = board_data[board_id]
                user_streams = b_data.setdefault('user_streams', {})
                
                stream = user_streams.get(user.id)
                if not stream:
                    stream = await get_user_stream(user.id, board_id)
                    user_streams[user.id] = stream
                    
        data['stream'] = stream
        return await handler(event, data)
class DeduplicationMiddleware(BaseMiddleware):
    def __init__(self):
        self.cache = {}
        self.cleanup_timer = time.time()
    async def __call__(self, handler, event, data):
        if not isinstance(event, types.Message):
            return await handler(event, data)
        current_time = time.time()
        if len(self.cache) > 2000 or current_time - self.cleanup_timer > 300:
            self.cache = {k: v for k, v in self.cache.items() if current_time - v < 60}
            self.cleanup_timer = current_time
        unique_key = (event.chat.id, event.message_id, event.media_group_id or 0)
        if unique_key in self.cache:
            return 
        self.cache[unique_key] = current_time
        return await handler(event, data)
class BoardMiddleware(BaseMiddleware):
    """
    1. Определяет board_id.
    2. Реализует "Глухой Бан" (Hard Ban).
       Если юзер забанен, бот удаляет его сообщение и прекращает обработку.
       Юзер не получает ответов ни на что (включая /help, /start), думая, что бот сломался.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        board_id = get_board_id(event)
        data['board_id'] = board_id
        if board_id:
            user = data.get('event_from_user')
            if user:
                uid = user.id
                b_data = board_data.get(board_id)
                if b_data:
                    if uid in b_data['users']['banned']:
                        try:
                            if isinstance(event, types.Message):
                                await event.delete()
                            elif isinstance(event, types.CallbackQuery):
                                pass 
                        except: 
                            pass
                        return 
        return await handler(event, data)
from common.board_config import BOARD_CONFIG
THREAD_BOARDS = {'thread', 'test'} # Доски, на которых будет работать система тредов
DATA_DIR = "data"  # Папка для хранения данных (например, архивов тредов)
os.makedirs(DATA_DIR, exist_ok=True) # Гарантируем, что папка существует
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
BOT_HEARTBEAT_PATH = os.path.join(LOG_DIR, "bot_heartbeat.json")
BOT_DEADLOCK_DUMP_PATH = os.path.join(LOG_DIR, "bot_deadlock_watchdog.log")
BOT_FATAL_CRASH_DUMP_PATH = os.path.join(LOG_DIR, "bot_fatal_crash.log")
BOT_CONTROLLED_STOP_PATH = "bot.stop"
EVENT_LOOP_DUMP_STALE_SEC = float(os.environ.get("BOT_EVENT_LOOP_DUMP_STALE_SEC", "45"))
EVENT_LOOP_DUMP_COOLDOWN_SEC = float(os.environ.get("BOT_EVENT_LOOP_DUMP_COOLDOWN_SEC", "120"))
_fatal_crash_dump_file = None


def _enable_fatal_crash_dump() -> None:
    global _fatal_crash_dump_file
    if _fatal_crash_dump_file is not None:
        return
    try:
        _fatal_crash_dump_file = open(BOT_FATAL_CRASH_DUMP_PATH, "a", encoding="utf-8", buffering=1)
        _fatal_crash_dump_file.write(
            f"\n=== FATAL CRASH WATCH ARMED pid={os.getpid()} ts={time.time():.3f} ===\n"
        )
        _fatal_crash_dump_file.flush()
        faulthandler.enable(file=_fatal_crash_dump_file, all_threads=True)
    except Exception as exc:
        _fatal_crash_dump_file = None
        try:
            print(f"⚠️ Fatal crash dump disabled: {type(exc).__name__}: {exc}")
        except Exception:
            pass


_enable_fatal_crash_dump()
MIRROR_CHANNELS = [
    -1003549106152, 
    -1003651702446,
    -1003614166511, 
]
REALTIME_ARCHIVE_CHANNEL_ID = MIRROR_CHANNELS[0] if MIRROR_CHANNELS else 0
BEST_CHANNEL_ID = -1001234567890  # ЗАМЕНИ НА СВОЙ ID
LIKES_THRESHOLD = 3 # Сколько лайков нужно для репоста
THREAD_NOTIFY_THRESHOLD = 30 # Порог постов для отправки уведомления об активности
last_checked_post_counter_for_notify = 0 # Глобальный счетчик для уведомителя
THREAD_BUMP_LIMIT_WARNING_THRESHOLD = 40 # За сколько постов до лимита слать уведомление
THREAD_VIEWER_PER_PAGE = 7  # Сколько тредов показывать на одной странице
THREAD_VIEWER_COOLDOWN = 3  # Секунды кулдауна на переключение страниц и открытие тредов
user_last_thread_action = defaultdict(float) # Для отслеживания времени последнего действия
reaction_ratelimit = defaultdict(float)
MAX_ACTIVE_THREADS = 100 # Макс. активных тредов на доске
MAX_POSTS_PER_THREAD = 500 # Макс. постов в треде до архивации
THREAD_CREATE_COOLDOWN_USER = 1800  # 30 минут в секундах
THREAD_HISTORY_COOLDOWN = 60 # 1 минут в секундах
OP_COMMAND_COOLDOWN = 60 # 1 минута кулдауна для команд модерации ОПа в треде
LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (вход/выход)
SUMMARIZE_COOLDOWN = 600 # 10 минут в секундах для команды /summarize
DB_POST_LIMIT = CONFIG_DB_POST_LIMIT  # Максимальное количество постов, которое будет храниться в БД
DB_CLEANUP_INTERVAL = timedelta(hours=2) # Как часто проводить очистку БД
MEMORY_LIMIT_GB = 3.2
QUICK_QUOTE_POST_DISTANCE = 330
class ThreadCreateStates(StatesGroup):
    waiting_for_op_post = State()      # Состояние ожидания текста ОП-поста
    waiting_for_confirmation = State() # Состояние ожидания подтверждения создания
class PollCreationStates(StatesGroup):
    waiting_for_confirmation = State()
BOARDS = list(BOARD_CONFIG.keys())
ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", -1002827087363))
GITHUB_ARCHIVE_BASE_URL = "https://github.com/shlomapetia/dvachbot-backup/blob/main/archives"
ARCHIVE_POSTING_BOT_ID = 'test' 
message_queues = {board: asyncio.Queue(maxsize=0) for board in BOARDS}
weekly_active_users = {board: set() for board in BOARDS}
weekly_active_updated_at = {board: 0.0 for board in BOARDS}
reply_coverage_stats = {}
reply_coverage_updated_at = 0.0
network_retry_state = defaultdict(lambda: {'attempt': 0, 'last_error_time': 0})
GLOBAL_BOTS = {} # Словарь для хранения всех экземпляров ботов
is_shutting_down = False
drain_shutdown_requested = False
drain_shutdown_requested_at = 0.0
event_loop_stall_watchdog_started = False
stream_cache = {} # {(user_id, board_id): 'ru'}
git_executor = ThreadPoolExecutor(max_workers=1)
save_executor = ThreadPoolExecutor(max_workers=2) # Executor для сохранения файлов
git_semaphore = asyncio.Semaphore(1)
storage_lock = asyncio.Lock()  # Блокировка для доступа к messages_storage, post_to_messages и т.д.
generate_locks = defaultdict(asyncio.Lock)
graph_stats = {}  # Для хранения статистики по часам для графика
delivery_metrics = defaultdict(lambda: deque(maxlen=100))
current_deliveries = {}
durable_delivery_stats = {
    "persisted": 0,
    "persist_failed": 0,
    "deleted": 0,
    "restored_items": 0,
    "restored_recipients": 0,
    "restore_deleted_empty": 0,
}
recent_messages_cache = deque(maxlen=200)
locally_created_posts = deque(maxlen=500)
MODE_FLAGS = [
    'anime_mode', 'zaputin_mode', 'slavaukraine_mode', 'suka_blyat_mode',
    'polish_mode', 'warhammer_mode', 'imperial_mode', 'gopnik_mode', 'schizo_mode',
]
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
AUTHORIZED_ARCHIVE_BOTS = {'b', 'a', 'test', 'sex', 'int', 'po', 'vg', 'thread', 'meta', 'trash', 'ai', 'news', 'tech', 'me', 'sci', 'h', 'soc', 'bunker', 'fit', 'fa', 'biz', 'mu', 'tv', 'au', 'vt', 'x'}
AUTHOR_NOTIFY_LIMIT_PER_MINUTE = 4
author_reaction_notify_tracker = defaultdict(lambda: deque(maxlen=AUTHOR_NOTIFY_LIMIT_PER_MINUTE))
author_reaction_notify_lock = asyncio.Lock()
pending_edit_tasks = {}  # Словарь для хранения активных задач редактирования {post_num: asyncio.Task}
pending_edit_lock = asyncio.Lock()
user_hourly_image_count = defaultdict(int)
user_hourly_image_reset = defaultdict(float)
HOURLY_IMAGE_LIMIT = 110
MODE_COOLDOWN = 3600  # 1 час в секундах
MAX_ACTIVE_USERS_IN_MEMORY = 5000 # Лимит на юзера в памяти для get_user_msgs_deque
ANIME_CMD_COOLDOWN = 25 # 25 секунд
anime_cmd_lock = asyncio.Lock()
info_cmd_lock = asyncio.Lock() # Кулдаун для команд /stats, /active
SPECIAL_NUMERALS_CONFIG = {
    4: {'label': 'Квадрипл', 'emojis': ('🎯', '🚀', '🔥', '🍀')},
    5: {'label': 'Пентипл', 'emojis': ('🏆', '⭐', '🥇', '💫')},
    6: {'label': 'Секстипл', 'emojis': ('💎', '👑', ' JACKPOT ', '🤩')},
    7: {'label': 'Септипл', 'emojis': ('🤯', '🌌', '🌠', '🪐')},
    8: {'label': 'Октипл', 'emojis': ('🦄', '👽', '💠', '🔱')}
}
state = {
    'post_counter': 0,
}
messages_storage = {}
post_to_messages = {}
message_to_post = {}
shadow_fake_post_counters = defaultdict(int)
last_messages = deque(maxlen=3) # Используется для генерации сообщений, можно оставить общим
last_activity_time = datetime.now()
sent_media_groups = deque(maxlen=1000)
current_media_groups = {}
media_group_timers = {}
user_spam_locks = defaultdict(asyncio.Lock)
media_group_creation_lock = asyncio.Lock()

def _iter_message_ids_for_copy(mid_or_list):
    if isinstance(mid_or_list, list):
        return mid_or_list
    return (mid_or_list,)

def _drop_post_copy_maps_unlocked(post_num: int) -> int:
    copies_map = post_to_messages.pop(post_num, None)
    if not copies_map:
        return 0
    removed = 0
    for uid, mid_or_list in copies_map.items():
        for mid in _iter_message_ids_for_copy(mid_or_list):
            if message_to_post.pop((uid, mid), None) is not None:
                removed += 1
    return removed

def _trim_post_copy_maps_unlocked(max_posts: int) -> tuple[int, int]:
    if max_posts < 0 or len(post_to_messages) <= max_posts:
        return 0, 0
    if max_posts == 0:
        stale_posts = list(post_to_messages.keys())
    else:
        keep_posts = set(sorted(post_to_messages.keys(), reverse=True)[:max_posts])
        stale_posts = [post_num for post_num in list(post_to_messages.keys()) if post_num not in keep_posts]
    removed_reverse = 0
    for post_num in stale_posts:
        removed_reverse += _drop_post_copy_maps_unlocked(post_num)
    return len(stale_posts), removed_reverse

def _purge_orphan_message_to_post_unlocked() -> int:
    valid_reverse_posts = set(messages_storage.keys()) | set(post_to_messages.keys())
    orphan_reverse_keys = [
        key for key, mapped_post_num in message_to_post.items()
        if mapped_post_num not in valid_reverse_posts
    ]
    for key in orphan_reverse_keys:
        message_to_post.pop(key, None)
    return len(orphan_reverse_keys)

def _media_group_state_key(chat_id: int | str, media_group_id: str) -> str:
    return f"{chat_id}:{media_group_id}"

unknown_command_tracker = defaultdict(list)
posts_pending_deletion = set()
os.environ["AIORGRAM_DISABLE_SIGNAL_HANDLERS"] = "1"
DEANON_COOLDOWN = 180  # 3 минуты
last_deanon_time = 0
deanon_lock = asyncio.Lock()
ROULETTE_EVENTS = [] # Будет хранить все события из рулеток
roulette_lock = asyncio.Lock()
POLL_VOTE_COOLDOWN = 2  # Секунды
last_poll_creation_time = defaultdict(float)
last_poll_vote_time = defaultdict(float) # Новая переменная для кулдауна голосования
SPAM_RULES = {
    'text': {
        'max_repeats': 3,
        'min_length': 2,
        'window_sec': 15,
        'max_per_window': 7,
        'penalty': [60, 120, 300]
    },
    'sticker': {
        'max_repeats': 2,
        'max_per_window': 5,
        'window_sec': 18,
        'penalty': [60, 300, 600]
    },
    'animation': {
        'max_repeats': 2,
        'max_per_window': 4,
        'window_sec': 24,
        'penalty': [60, 300, 600]
    },
    'audio': {
        'max_repeats': 3,  
        'window_sec': 60,  
        'max_per_window': 5,  
        'penalty': [180, 300, 600] 
    }
}
TOKEN_TO_BOARD_MAP = {
    config['token']: board_id
    for board_id, config in BOARD_CONFIG.items() if 'token' in config
}
event_loop_last_tick = time.time()
EVENT_LOOP_HEALTH_STALE_SEC = float(os.environ.get("BOT_EVENT_LOOP_HEALTH_STALE_SEC", "45"))
DEFAULT_EXECUTOR_WORKERS = max(4, int(os.environ.get("BOT_DEFAULT_EXECUTOR_WORKERS", "16")))
async def healthcheck(request):
    print("🚀 Получен запрос на healthcheck")
    return web.Response(text="Bot is alive")

class _ThreadedHealthcheckSite:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self.server = server
        self.thread = thread

    async def stop(self):
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()


class _HealthcheckHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


class _BotHealthcheckHandler(BaseHTTPRequestHandler):
    server_version = "TGChanHealth/1.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        return

    def setup(self):
        super().setup()
        self.request.settimeout(2.0)

    def finish(self):
        try:
            super().finish()
        except OSError:
            pass
        finally:
            try:
                self.request.close()
            except OSError:
                pass

    def do_GET(self):
        try:
            self.close_connection = True
            status_code, body = _build_healthcheck_body()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return

def _build_healthcheck_body() -> tuple[int, bytes]:
    now = time.time()
    loop_lag_sec = max(0.0, now - event_loop_last_tick)
    is_stale = loop_lag_sec > EVENT_LOOP_HEALTH_STALE_SEC
    status_code = 503 if is_stale or is_shutting_down else 200
    queue_total = 0
    queue_top = []
    try:
        queue_items = [(board_id, queue.qsize()) for board_id, queue in list(message_queues.items())]
        queue_total = sum(size for _, size in queue_items)
        queue_top = sorted(queue_items, key=lambda item: item[1], reverse=True)[:5]
    except Exception:
        queue_total = -1
        queue_top = []
    body = json.dumps(
        {
            "status": "stale" if is_stale else ("shutting_down" if is_shutting_down else "ok"),
            "pid": os.getpid(),
            "loop_lag_sec": round(loop_lag_sec, 3),
            "stale_after_sec": EVENT_LOOP_HEALTH_STALE_SEC,
            "queues_total": queue_total,
            "queues_top": queue_top,
            "post_counter": state.get("post_counter"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return status_code, body

class _RawHealthcheckServer:
    def __init__(self, host: str, port: int):
        self._stop_event = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(64)
        self._sock.settimeout(1.0)

    def serve_forever(self):
        while not self._stop_event.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                thread = threading.Thread(
                    target=self._safe_handle_connection,
                    args=(conn,),
                    name="bot-healthcheck-client",
                    daemon=True,
                )
                thread.start()
            except RuntimeError:
                try:
                    conn.close()
                except OSError:
                    pass

    def _safe_handle_connection(self, conn: socket.socket):
        try:
            self._handle_connection(conn)
        except Exception as exc:
            try:
                runtime_logger.warning(
                    "healthcheck_client_failed %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            except Exception:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def _handle_connection(self, conn: socket.socket):
        with conn:
            try:
                conn.settimeout(0.2)
                try:
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                try:
                    conn.recv(2048)
                except (socket.timeout, OSError):
                    pass
                status_code, body = _build_healthcheck_body()
                status_text = "OK" if status_code == 200 else "Service Unavailable"
                headers = (
                    f"HTTP/1.1 {status_code} {status_text}\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
                conn.settimeout(0.75)
                conn.sendall(headers + body)
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            except OSError:
                return

    def shutdown(self):
        self._stop_event.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def server_close(self):
        self.shutdown()

async def start_healthcheck():
    port = int(os.environ.get('PORT', 8080))
    try:
        print(f"🟢 Попытка запустить healthcheck сервер на порту {port}")
        server = _RawHealthcheckServer("0.0.0.0", port)
        thread = threading.Thread(target=server.serve_forever, name="bot-healthcheck", daemon=True)
        thread.start()
        print(f"🟢 Healthcheck-сервер успешно запущен на порту {port}")
        return _ThreadedHealthcheckSite(server, thread)
    except Exception as e:
        print(f"Ошибка запуска healthcheck сервера: {str(e)}")
        raise
GITHUB_REPO = "https://github.com/shlomapetia/dvachbot-backup.git"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Проверь, что переменная есть в Railway!
last_gc_time = time.time()
def convert_site_tags_to_telegram(text: str) -> str:
    """
    Преобразует BB-коды сайта в поддерживаемые HTML-теги Telegram.
    Адаптирует визуальные эффекты под возможности мессенджера.
    """
    if not text:
        return ""
    text = re.sub(r'\[b\](.*?)\[/b\]', r'<b>\1</b>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[i\](.*?)\[/i\]', r'<i>\1</i>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[s\](.*?)\[/s\]', r'<s>\1</s>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\|\|(.*?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', text, flags=re.DOTALL)
    text = re.sub(r'\[blur\](.*?)\[/blur\]', r'<tg-spoiler>\1</tg-spoiler>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[shake\](.*?)\[/shake\]', r'<i>\1</i>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[rainbow\](.*?)\[/rainbow\]', r'<code>\1</code>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[glitch\](.*?)\[/glitch\]', r'<s><code>\1</code></s>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[code\](.*?)\[/code\]', r'<code>\1</code>', text, flags=re.IGNORECASE | re.DOTALL)
    return text
dp = Dispatcher()
dp.message.middleware(DeduplicationMiddleware())
dp.message.middleware(BoardMiddleware())
dp.callback_query.middleware(BoardMiddleware())
dp.message_reaction.middleware(BoardMiddleware())
dp.message.middleware(MultiLangMiddleware())
dp.callback_query.middleware(MultiLangMiddleware())
dp.message_reaction.middleware(MultiLangMiddleware())
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="%H:%M:%S"
)
install_logging_redaction()
def _setup_runtime_logger() -> logging.Logger:

    logger = logging.getLogger("tgach.runtime")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "bot_runtime.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=7,
            encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        add_secret_redaction_filter(handler)
        logger.addHandler(handler)
    return logger
runtime_logger = _setup_runtime_logger()
aiohttp_log = logging.getLogger('aiohttp')
aiohttp_log.setLevel(logging.CRITICAL) 
aiogram_log = logging.getLogger('aiogram')
aiogram_log.setLevel(logging.CRITICAL) # <--- ИЗМЕНЕНО НА CRITICAL, чтобы не видеть ошибки апдейтов
def clean_html_tags(text: str) -> str:

    if not text: return text
    return RE_HTML_TAGS.sub('', text)
def sanitize_html(text: str) -> str:

    if not text: return ""
    
    # --- НАЧАЛО ИЗМЕНЕНИЙ (Перехват и конвертация гиперссылок) ---
    def link_replacer(match):
        url = match.group(1)
        content = match.group(2)
        # Очищаем URL от протокола и www. для эстетики
        clean_url = re.sub(r'^https?://', '', url, flags=re.IGNORECASE)
        clean_url = re.sub(r'^www\.', '', clean_url, flags=re.IGNORECASE)
        # Возвращаем текст и ссылку рядом в скобках
        return f"{content} <i>({clean_url})</i>"
        
    # Ищем теги <a href="URL">ТЕКСТ</a> и обрабатываем их до основного санитайзера
    text = re.sub(r'<\s*a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)<\s*/\s*a\s*>', link_replacer, text, flags=re.IGNORECASE | re.DOTALL)
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    text = RE_SCRIPT_TAG.sub('', text)
    text = RE_SCRIPT_SINGLE.sub('', text)
    text = RE_DANGEROUS_TAGS.sub('', text)
    text = RE_DANGEROUS_SINGLE.sub('', text)
    text = RE_EVENT_HANDLERS.sub('', text)
    return text
def add_you_to_my_posts_fast(text: str, user_id: int, post_authors: dict[int, int]) -> str:
    """Улучшенная версия: не использует замок, работает с переданным словарем авторов."""
    if not text or ">>" not in text:
        return text
    
    matches = RE_YOU_PATTERN.findall(text)
    for post_str in matches:
        try:
            p_num = int(post_str)
            if post_authors.get(p_num) == user_id:
                target = f">>{p_num}"
                replacement = f">>{p_num} (You)"
                if target in text and replacement not in text:
                    text = text.replace(target, replacement)
        except ValueError:
            continue
    return text
gc.set_threshold(
    600, 6, 6)  # Оптимальные настройки для баланса памяти/производительности
def get_user_msgs_deque(user_id: int, board_id: str):

    last_user_msgs_for_board = board_data[board_id]['last_user_msgs']
    return last_user_msgs_for_board.setdefault(user_id, deque(maxlen=10))
SPAM_LIMIT = 14
SPAM_WINDOW = 15
STICKER_WINDOW = 10  # секунд
STICKER_LIMIT = 7
REST_SECONDS = 30  # время блокировки
MAX_MESSAGES_IN_MEMORY = CONFIG_BOT_POST_CACHE_LIMIT  # храним только последние посты в общей памяти
MAX_COPY_MAP_POSTS_IN_MEMORY = max(0, int(CONFIG_BOT_COPY_CACHE_POST_LIMIT or 0))
TELEMETRY_INTERVAL_SEC = int(os.getenv("BOT_TELEMETRY_INTERVAL_SEC", "300"))
TELEMETRY_WARN_QUEUE_TOTAL = int(os.getenv("BOT_TELEMETRY_WARN_QUEUE_TOTAL", "80"))
TELEMETRY_WARN_DONE_EDIT_TASKS = int(os.getenv("BOT_TELEMETRY_WARN_DONE_EDIT_TASKS", "100"))
TELEMETRY_WARN_MEDIA_GROUPS = int(os.getenv("BOT_TELEMETRY_WARN_MEDIA_GROUPS", "50"))
REPLY_COVERAGE_REFRESH_SECONDS = int(os.getenv("BOT_REPLY_COVERAGE_REFRESH_SEC", "900"))
PRIORITY_DELIVERY_ENABLED = BOT_PRIORITY_DELIVERY
WEEKLY_ACTIVE_DAYS = max(1, BOT_WEEKLY_ACTIVE_DAYS)
WEEKLY_ACTIVE_REFRESH_SECONDS = max(60, BOT_WEEKLY_ACTIVE_REFRESH_SEC)
PRIORITY_SPLIT_FANOUT_ENABLED = PRIORITY_DELIVERY_ENABLED and BOT_PRIORITY_SPLIT_FANOUT
PRIORITY_SPLIT_MIN_PASSIVE = max(1, BOT_PRIORITY_SPLIT_MIN_PASSIVE)
PRIORITY_PASSIVE_SLICE_SIZE = max(10, BOT_PRIORITY_PASSIVE_SLICE_SIZE)
PRIORITY_PASSIVE_MEDIA_SLICE_SIZE = max(10, BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE)
PRIORITY_PRESSURE_SLICE_AGE_SEC = max(0.0, float(BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC))
PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE = max(10, int(BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE))
PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE = max(10, int(BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE))
PASSIVE_MAX_PREEMPTIONS = max(0, BOT_PASSIVE_MAX_PREEMPTIONS)
PRIORITY_PHASE_BUDGET_SEC = max(0.0, float(BOT_PRIORITY_PHASE_BUDGET_SEC))
PASSIVE_PHASE_BUDGET_SEC = max(0.0, float(BOT_PASSIVE_PHASE_BUDGET_SEC))
DELIVERY_SLOW_PHASE_SEC = max(1.0, BOT_DELIVERY_SLOW_PHASE_SEC)
DELIVERY_INITIAL_CHUNK_SIZE = max(1, int(BOT_DELIVERY_INITIAL_CHUNK_SIZE))
DELIVERY_MIN_CHUNK_SIZE = max(1, min(int(BOT_DELIVERY_MIN_CHUNK_SIZE), DELIVERY_INITIAL_CHUNK_SIZE))
DELIVERY_PER_RECIPIENT_TIMEOUT_SEC = max(10.0, float(BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC))
DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC = max(3.0, min(20.0, DELIVERY_PER_RECIPIENT_TIMEOUT_SEC))
DELIVERY_MAX_RECIPIENT_RETRIES = max(1, int(BOT_DELIVERY_MAX_RECIPIENT_RETRIES))
DELIVERY_PHASE_GUARD_SEC = max(0.0, float(BOT_DELIVERY_PHASE_GUARD_SEC))
CONTROLLED_STOP_DRAIN_TIMEOUT_SEC = max(0.0, float(BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC))
CONTROLLED_STOP_LOG_INTERVAL_SEC = max(1.0, float(BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC))
DURABLE_DELIVERY_QUEUE_ENABLED = BOT_DURABLE_DELIVERY_QUEUE
B_MAX_STACKED_ANIME_IMAGES = max(1, BOT_B_MAX_STACKED_ANIME_IMAGES)
ANIME_MEDIA_CONCURRENCY = max(1, BOT_ANIME_MEDIA_CONCURRENCY)
ANIME_URL_FETCH_TIMEOUT_SEC = max(3.0, float(BOT_ANIME_URL_FETCH_TIMEOUT_SEC))
ANIME_URL_FETCH_TOTAL_SEC = max(ANIME_URL_FETCH_TIMEOUT_SEC, float(BOT_ANIME_URL_FETCH_TOTAL_SEC))
ANIME_URL_FETCH_PARALLEL = max(1, int(BOT_ANIME_URL_FETCH_PARALLEL))
ANIME_DOWNLOAD_TIMEOUT_SEC = max(5.0, float(BOT_ANIME_DOWNLOAD_TIMEOUT_SEC))
ANIME_DOWNLOAD_TOTAL_SEC = max(ANIME_DOWNLOAD_TIMEOUT_SEC, float(BOT_ANIME_DOWNLOAD_TOTAL_SEC))
ANIME_DOWNLOAD_PARALLEL = max(1, int(BOT_ANIME_DOWNLOAD_PARALLEL))
ANIME_REFILL_ROUNDS = max(0, int(BOT_ANIME_REFILL_ROUNDS))
anime_media_gate = asyncio.Semaphore(ANIME_MEDIA_CONCURRENCY)
MODE_PUNCHUP_ENABLED = BOT_MODE_PUNCHUP_ENABLED
MODE_PUNCHUP_QUEUE_SHED_SEC = max(0.0, BOT_MODE_PUNCHUP_QUEUE_SHED_SEC)
MODE_PUNCHUP_SLOW_LOG_US = max(0, BOT_MODE_PUNCHUP_SLOW_LOG_US)
mode_punchup_runtime_enabled = MODE_PUNCHUP_ENABLED
mode_punchup_stats = defaultdict(lambda: {
    "calls": 0,
    "skipped_load": 0,
    "skipped_disabled": 0,
    "total_us": 0.0,
    "max_us": 0.0,
    "slow": 0,
})
CONTEXTUAL_REPLIES_ENABLED = BOT_CONTEXTUAL_REPLIES_ENABLED
CONTEXTUAL_REPLY_COOLDOWN_SEC = max(0.0, float(BOT_CONTEXTUAL_REPLY_COOLDOWN_SEC))
CONTEXTUAL_REPLY_DAILY_LIMIT = max(0, int(BOT_CONTEXTUAL_REPLY_DAILY_LIMIT))
contextual_reply_tracker = defaultdict(lambda: {"last": 0.0, "window_start": 0.0, "count": 0})
contextual_reply_stats = defaultdict(int)
image_spam_tracker = defaultdict(list)
IMAGE_SPAM_LIMIT = 30
IMAGE_SPAM_WINDOW = 300 # 5 минут в секундах
POSITIVE_REACTIONS = {'👍', '❤', '🔥', '❤‍🔥', '😍', '👌', '💯', '🙏', '🎉', '❤️', '♥️', '🥰', '🤩'}
LAUGHING_REACTIONS = {'😂', '🤣', '😁', '😄', '😆'}
NEGATIVE_REACTIONS = {'👎', '💩', '🤮', '🤢', '😡', '🤬', '🖕'}
CLOWN_REACTION = {'🤡'}
THINKING_REACTIONS = {'🤔', '🧐', '🤨'}
SHOCK_REACTIONS = {'🤯', '😱', '😮', '😯', '😲'}
SAD_REACTIONS = {'😢', '😭', '💔'}
POLITICAL_REACTIONS = {'🇷🇺', '🇺🇦'}
SYMBOLIC_REACTIONS = {'🏴‍☠️', '♂️'}
INSULT_REACTIONS = {'🐓', '🐖'}
MAT_WORDS = ["сука", "блядь", "пиздец", "ебать", "нах", "пизда", "хуйня", "ебал", "блять", "отъебись", "ебаный", "еблан", "ХУЙ", "ПИЗДА", "хуйло", "долбаёб", "пидорас"]
MSK = timezone(timedelta(hours=3))
def _safe_len(value) -> int:

    try:
        return len(value)
    except Exception:
        return -1
def _file_size_mb(path) -> float:

    try:
        return round(os.path.getsize(os.fspath(path)) / 1024 / 1024, 2)
    except OSError:
        return 0.0
DB_FILE_SNAPSHOT_TIMEOUT_SEC = 1.5
db_file_snapshot_cache = {
    "db_mb": 0.0,
    "wal_mb": 0.0,
    "shm_mb": 0.0,
    "updated_at": None,
    "age_sec": None,
    "stale": True,
}
db_file_snapshot_lock = threading.Lock()


def _read_db_file_snapshot_uncached() -> dict:
    db_path = os.fspath(DB_PATH_CONFIG)
    return {
        "db_mb": _file_size_mb(db_path),
        "wal_mb": _file_size_mb(f"{db_path}-wal"),
        "shm_mb": _file_size_mb(f"{db_path}-shm"),
    }


def _get_db_file_snapshot() -> dict:
    with db_file_snapshot_lock:
        snapshot = dict(db_file_snapshot_cache)
    updated_at = snapshot.get("updated_at")
    if isinstance(updated_at, (int, float)):
        snapshot["age_sec"] = round(max(0.0, time.time() - updated_at), 1)
        snapshot["stale"] = snapshot["age_sec"] > (TELEMETRY_INTERVAL_SEC * 2)
    return snapshot


async def _refresh_db_file_snapshot_cache() -> dict:
    loop = asyncio.get_running_loop()
    try:
        fresh = await asyncio.wait_for(
            loop.run_in_executor(None, _read_db_file_snapshot_uncached),
            timeout=DB_FILE_SNAPSHOT_TIMEOUT_SEC,
        )
        fresh.update({
            "updated_at": time.time(),
            "age_sec": 0.0,
            "stale": False,
        })
        with db_file_snapshot_lock:
            db_file_snapshot_cache.clear()
            db_file_snapshot_cache.update(fresh)
    except asyncio.TimeoutError:
        runtime_logger.warning(
            "db_file_snapshot_timeout %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "timeout_sec": DB_FILE_SNAPSHOT_TIMEOUT_SEC,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    except Exception as exc:
        runtime_logger.warning(
            "db_file_snapshot_failed %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "error": type(exc).__name__,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    return _get_db_file_snapshot()
def _summarize_delivery_metrics() -> dict:

    summary = {}
    for board_id in BOARDS:
        records = list(delivery_metrics.get(board_id, []))
        if not records:
            continue
        recent = records[-20:]
        seconds = [item.get("seconds", 0.0) for item in recent]
        ages = [
            item.get("post_age_sec")
            for item in recent
            if item.get("post_age_sec") is not None
        ]
        summary[board_id] = {
            "count": len(records),
            "avg_sec": round(sum(seconds) / len(seconds), 2) if seconds else 0.0,
            "max_sec": round(max(seconds), 2) if seconds else 0.0,
            "avg_age_sec": round(sum(ages) / len(ages), 2) if ages else None,
            "max_age_sec": round(max(ages), 2) if ages else None,
            "last": records[-1],
        }
    return summary
def _prepare_queue_item(board_id: str, item: dict) -> dict:

    if isinstance(item, dict):
        item.setdefault("board_id", board_id)
        item.setdefault("enqueued_at", time.time())
    return item
async def enqueue_board_message(board_id: str, item: dict) -> None:

    await message_queues[board_id].put(_prepare_queue_item(board_id, item))
def _contains_volatile_delivery_payload(value, depth: int = 0) -> bool:

    if depth > 8:
        return True
    if isinstance(value, (bytes, bytearray, BufferedInputFile, InputFile)):
        return True
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "image_bytes" and nested:
                return True
            if _contains_volatile_delivery_payload(nested, depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_contains_volatile_delivery_payload(item, depth + 1) for item in value)
    if value is None or isinstance(value, (str, int, float, bool, Enum)):
        return False
    return False


def _durable_recipients_from_item(item: dict) -> list[int]:

    recipients = item.get("recipients", [])
    try:
        return sorted({int(uid) for uid in recipients if int(uid) > 0})
    except Exception:
        return []


def _queue_item_can_be_durable(item: dict) -> bool:

    if not DURABLE_DELIVERY_QUEUE_ENABLED:
        return False
    if not isinstance(item, dict):
        return False
    if item.get("keyboard") is not None:
        return False
    if item.get("thread_id"):
        return False
    if item.get("delivery_phase") != "passive":
        return False
    content = item.get("content")
    if not isinstance(content, dict):
        return False
    if _contains_volatile_delivery_payload(content):
        return False
    return bool(item.get("post_num")) and bool(_durable_recipients_from_item(item))


def _build_passive_queue_item(
    source_item: dict,
    recipients: set[int],
    post_num: int,
    original_recipients: int,
    enqueued_at: float | None,
    started_at: float,
) -> dict:

    passive_item = source_item.copy()
    passive_item["recipients"] = set(recipients)
    passive_item["delivery_phase"] = "passive"
    passive_item["original_recipients"] = original_recipients
    passive_item["priority_split_from"] = post_num
    passive_item["phase_enqueued_at"] = time.time()
    passive_item["board_id"] = source_item.get("board_id")
    if "enqueued_at" not in passive_item:
        passive_item["enqueued_at"] = enqueued_at or started_at
    return passive_item


async def _persist_durable_delivery_item(board_id: str, item: dict, reason: str) -> int | None:

    if not _queue_item_can_be_durable(item):
        return None
    durable_id = await upsert_delivery_queue_item(
        board_id=board_id,
        post_num=int(item["post_num"]),
        recipients=_durable_recipients_from_item(item),
        content=item["content"],
        delivery_phase=item.get("delivery_phase", "passive"),
        original_recipients=int(item.get("original_recipients") or 0),
        thread_id=item.get("thread_id"),
        enqueued_at=float(item.get("enqueued_at") or time.time()),
    )
    if durable_id:
        item["durable_delivery_id"] = durable_id
        durable_delivery_stats["persisted"] += 1
        runtime_logger.info(
            "delivery_durable_saved %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "id": durable_id,
                    "board_id": board_id,
                    "post_num": item.get("post_num"),
                    "phase": item.get("delivery_phase"),
                    "recipients": len(_durable_recipients_from_item(item)),
                    "reason": reason,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        return durable_id
    durable_delivery_stats["persist_failed"] += 1
    return None


async def _delete_durable_delivery_item(item_or_id, reason: str) -> None:

    durable_id = item_or_id
    if isinstance(item_or_id, dict):
        durable_id = item_or_id.get("durable_delivery_id")
    if not durable_id:
        return
    if await delete_delivery_queue_item(int(durable_id)):
        durable_delivery_stats["deleted"] += 1
        runtime_logger.info(
            "delivery_durable_deleted %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "id": int(durable_id),
                    "reason": reason,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )


async def _remove_already_delivered_recipients(post_num: int, recipients) -> set[int]:

    try:
        candidate_recipients = {int(uid) for uid in recipients if int(uid) > 0}
    except Exception:
        return set()
    if not candidate_recipients:
        return set()
    copies = await get_post_copies(post_num)
    delivered = {int(recipient_id) for recipient_id, _message_id in copies}
    return candidate_recipients - delivered


async def restore_durable_delivery_queue(limit: int = 1000) -> None:

    if not DURABLE_DELIVERY_QUEUE_ENABLED:
        return
    items = await get_pending_delivery_queue_items(limit=limit)
    restored_items = 0
    restored_recipients = 0
    deleted_empty = 0
    for item in items:
        board_id = item.get("board_id")
        if board_id not in message_queues:
            continue
        remaining_recipients = await _remove_already_delivered_recipients(
            int(item["post_num"]),
            item.get("recipients", []),
        )
        if not remaining_recipients:
            await _delete_durable_delivery_item(item.get("id"), "restore_empty")
            deleted_empty += 1
            continue
        queue_item = {
            "recipients": remaining_recipients,
            "content": item["content"],
            "post_num": int(item["post_num"]),
            "board_id": board_id,
            "delivery_phase": item.get("delivery_phase") or "passive",
            "original_recipients": int(item.get("original_recipients") or len(remaining_recipients)),
            "thread_id": item.get("thread_id"),
            "enqueued_at": float(item.get("enqueued_at") or time.time()),
            "durable_delivery_id": int(item["id"]),
        }
        await enqueue_board_message(board_id, queue_item)
        restored_items += 1
        restored_recipients += len(remaining_recipients)
    durable_delivery_stats["restored_items"] += restored_items
    durable_delivery_stats["restored_recipients"] += restored_recipients
    durable_delivery_stats["restore_deleted_empty"] += deleted_empty
    if restored_items or deleted_empty:
        runtime_logger.warning(
            "delivery_durable_restore %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "restored_items": restored_items,
                    "restored_recipients": restored_recipients,
                    "deleted_empty": deleted_empty,
                    "limit": limit,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        print(
            f"🧷 Durable delivery restore: restored={restored_items}, "
            f"recipients={restored_recipients}, deleted_empty={deleted_empty}"
        )
def _delivery_queue_counts() -> dict[str, int]:

    return {board: queue.qsize() for board, queue in message_queues.items()}


def _delivery_queue_total() -> int:

    return sum(_delivery_queue_counts().values())


def _controlled_stop_snapshot() -> dict:

    requested_at = drain_shutdown_requested_at or None
    age_sec = None
    if requested_at:
        age_sec = max(0.0, time.time() - requested_at)
    return {
        "requested": drain_shutdown_requested,
        "requested_at": requested_at,
        "age_sec": round(age_sec, 3) if age_sec is not None else None,
        "drain_timeout_sec": CONTROLLED_STOP_DRAIN_TIMEOUT_SEC,
        "log_interval_sec": CONTROLLED_STOP_LOG_INTERVAL_SEC,
        "stop_file": BOT_CONTROLLED_STOP_PATH,
    }
def _active_telegram_recipients_count(board_id: str) -> int:

    try:
        b_data = board_data.get(board_id, {})
        users = b_data.get("users", {})
        active = users.get("active", set())
        banned = users.get("banned", set())
        return sum(1 for uid in active if isinstance(uid, int) and uid > 0 and uid not in banned)
    except Exception:
        return -1
def _recipient_counts_snapshot() -> dict:

    by_board = {board_id: _active_telegram_recipients_count(board_id) for board_id in BOARDS}
    return {
        "telegram_active_total": sum(count for count in by_board.values() if count > 0),
        "telegram_active_by_board": by_board,
        "top": sorted(by_board.items(), key=lambda item: item[1], reverse=True)[:5],
    }
def _board_queue_oldest_age_sec(board_id: str | None) -> float:

    if not board_id:
        return 0.0
    queue = message_queues.get(board_id)
    if not queue:
        return 0.0
    now = time.time()
    oldest = 0.0
    try:
        for item in getattr(queue, "_queue", []):
            if not isinstance(item, dict):
                continue
            enqueued_at = item.get("enqueued_at")
            if enqueued_at is None:
                continue
            try:
                oldest = max(oldest, now - float(enqueued_at))
            except (TypeError, ValueError):
                continue
    except Exception:
        return 0.0
    return max(0.0, oldest)


def _passive_slice_size_for_content(content: dict, board_id: str | None = None) -> int:

    content_type = str((content or {}).get("type", "")).split(".")[-1].lower()
    if content_type in {
        "photo",
        "video",
        "animation",
        "document",
        "audio",
        "voice",
        "sticker",
        "video_note",
        "media_group",
    }:
        base_size = PRIORITY_PASSIVE_MEDIA_SLICE_SIZE
        pressure_size = PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE
    else:
        base_size = PRIORITY_PASSIVE_SLICE_SIZE
        pressure_size = PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE
    if (
        board_id
        and PRIORITY_PRESSURE_SLICE_AGE_SEC > 0
        and _board_queue_oldest_age_sec(board_id) >= PRIORITY_PRESSURE_SLICE_AGE_SEC
    ):
        return min(base_size, pressure_size)
    return base_size
def _queue_has_full_message(queue: asyncio.Queue) -> bool:

    try:
        for item in getattr(queue, "_queue", []):
            if isinstance(item, dict) and item.get("delivery_phase", "full") == "full":
                return True
    except Exception:
        return False
    return False
def _mode_punchup_queue_pressure_sec(board_id: str) -> float:

    now = time.time()
    max_age = 0.0
    try:
        queue = message_queues.get(board_id)
        if queue is not None:
            for item in getattr(queue, "_queue", []):
                if not isinstance(item, dict):
                    continue
                enqueued_at = item.get("enqueued_at")
                if enqueued_at is None:
                    continue
                max_age = max(max_age, max(0.0, now - float(enqueued_at)))
    except Exception:
        pass
    try:
        current = current_deliveries.get(board_id)
        if isinstance(current, dict):
            enqueued_at = current.get("enqueued_at") or current.get("started_at")
            if enqueued_at is not None:
                max_age = max(max_age, max(0.0, now - float(enqueued_at)))
    except Exception:
        pass
    return max_age
def _mode_punchup_can_run(board_id: str) -> tuple[bool, str | None, float]:

    if not MODE_PUNCHUP_ENABLED or not mode_punchup_runtime_enabled:
        return False, "disabled", 0.0
    pressure_sec = _mode_punchup_queue_pressure_sec(board_id)
    if MODE_PUNCHUP_QUEUE_SHED_SEC and pressure_sec >= MODE_PUNCHUP_QUEUE_SHED_SEC:
        return False, "queue_pressure", pressure_sec
    return True, None, pressure_sec
def _record_mode_punchup_skip(mode_key: str, reason: str) -> None:

    stats = mode_punchup_stats[mode_key]
    if reason == "queue_pressure":
        stats["skipped_load"] += 1
    else:
        stats["skipped_disabled"] += 1
def _summarize_mode_punchup_stats() -> dict:

    modes = {}
    totals = {
        "calls": 0,
        "skipped_load": 0,
        "skipped_disabled": 0,
        "total_us": 0.0,
        "max_us": 0.0,
        "slow": 0,
    }
    for mode_key, raw in mode_punchup_stats.items():
        calls = int(raw.get("calls", 0))
        total_us = float(raw.get("total_us", 0.0))
        max_us = float(raw.get("max_us", 0.0))
        skipped_load = int(raw.get("skipped_load", 0))
        skipped_disabled = int(raw.get("skipped_disabled", 0))
        slow = int(raw.get("slow", 0))
        modes[mode_key] = {
            "calls": calls,
            "avg_us": round(total_us / calls, 2) if calls else 0.0,
            "max_us": round(max_us, 2),
            "skipped_load": skipped_load,
            "skipped_disabled": skipped_disabled,
            "slow": slow,
        }
        totals["calls"] += calls
        totals["skipped_load"] += skipped_load
        totals["skipped_disabled"] += skipped_disabled
        totals["total_us"] += total_us
        totals["max_us"] = max(totals["max_us"], max_us)
        totals["slow"] += slow
    top = sorted(modes.items(), key=lambda item: item[1]["max_us"], reverse=True)[:5]
    return {
        "calls": totals["calls"],
        "avg_us": round(totals["total_us"] / totals["calls"], 2) if totals["calls"] else 0.0,
        "max_us": round(totals["max_us"], 2),
        "skipped_load": totals["skipped_load"],
        "skipped_disabled": totals["skipped_disabled"],
        "slow": totals["slow"],
        "top": top,
        "by_mode": modes,
    }
async def _maybe_punch_up_text(text: str, mode_key: str, board_id: str) -> str:

    if not text:
        return text
    can_run, reason, pressure_sec = _mode_punchup_can_run(board_id)
    if not can_run:
        _record_mode_punchup_skip(mode_key, reason or "disabled")
        return text
    loop = asyncio.get_running_loop()
    started = time.perf_counter()
    result = await loop.run_in_executor(None, punch_up_mode_text, text, mode_key)
    elapsed_us = (time.perf_counter() - started) * 1_000_000
    stats = mode_punchup_stats[mode_key]
    stats["calls"] += 1
    stats["total_us"] += elapsed_us
    stats["max_us"] = max(float(stats.get("max_us", 0.0)), elapsed_us)
    if MODE_PUNCHUP_SLOW_LOG_US and elapsed_us >= MODE_PUNCHUP_SLOW_LOG_US:
        stats["slow"] += 1
        runtime_logger.warning(
            "mode_punchup_slow %s",
            json.dumps({
                "ts": round(time.time(), 3),
                "board_id": board_id,
                "mode": mode_key,
                "elapsed_us": round(elapsed_us, 2),
                "queue_pressure_sec": round(pressure_sec, 3),
            }, ensure_ascii=False, separators=(",", ":"))
        )
    return result
def _summarize_live_queue_ages(queue_sizes: dict) -> dict:

    now = time.time()
    by_board = {}
    oldest = []
    for board_id, queue in message_queues.items():
        queued_items = list(getattr(queue, "_queue", []))
        ages = []
        oldest_post = None
        oldest_age = None
        for item in queued_items:
            if not isinstance(item, dict):
                continue
            enqueued_at = item.get("enqueued_at")
            if enqueued_at is None:
                continue
            try:
                age = max(0.0, now - float(enqueued_at))
            except (TypeError, ValueError):
                continue
            ages.append(age)
            if oldest_age is None or age > oldest_age:
                oldest_age = age
                oldest_post = item.get("post_num")
        if queue_sizes.get(board_id, 0) or ages:
            info = {"size": queue_sizes.get(board_id, 0)}
            if ages:
                info.update({
                    "oldest_age_sec": round(max(ages), 1),
                    "avg_age_sec": round(sum(ages) / len(ages), 1),
                    "oldest_post": oldest_post,
                })
                oldest.append((board_id, info["oldest_age_sec"], oldest_post))
            by_board[board_id] = info
    in_flight = {}
    for board_id, item in list(current_deliveries.items()):
        started_at = item.get("started_at")
        enqueued_at = item.get("enqueued_at")
        data = item.copy()
        try:
            data["run_sec"] = round(max(0.0, now - float(started_at)), 1) if started_at is not None else None
        except (TypeError, ValueError):
            data["run_sec"] = None
        try:
            data["age_sec"] = round(max(0.0, now - float(enqueued_at)), 1) if enqueued_at is not None else None
        except (TypeError, ValueError):
            data["age_sec"] = None
        in_flight[board_id] = data
    return {
        "by_board": by_board,
        "oldest": sorted(oldest, key=lambda item: item[1], reverse=True)[:5],
        "in_flight": in_flight,
    }
def _get_process_memory_snapshot() -> dict:

    try:
        process = psutil.Process(os.getpid())
        info = process.memory_info()
        try:
            full_info = process.memory_full_info()
        except Exception:
            full_info = info
        private_bytes = (
            getattr(full_info, "private", None)
            or getattr(full_info, "uss", None)
            or getattr(info, "rss", 0)
        )
        # psutil.open_files() can block inside Windows kernel calls; an older
        # fatal dump showed runtime telemetry stuck there. Keep health over trivia.
        open_file_count = -1
        return {
            "pid": os.getpid(),
            "rss_mb": round(getattr(info, "rss", 0) / 1024 / 1024, 2),
            "private_mb": round(private_bytes / 1024 / 1024, 2),
            "vms_mb": round(getattr(info, "vms", 0) / 1024 / 1024, 2),
            "threads": process.num_threads(),
            "open_files": open_file_count,
        }
    except Exception as exc:
        return {"error": str(exc)}
def _collect_board_map_totals() -> dict:

    totals = {
        "last_texts": 0,
        "last_stickers": 0,
        "last_animations": 0,
        "last_audios": 0,
        "spam_violations": 0,
        "spam_tracker_users": 0,
        "spam_tracker_items": 0,
        "reaction_rate_users": 0,
        "reaction_rate_items": 0,
        "reaction_queue_users": 0,
        "reaction_queue_items": 0,
        "last_reaction_process_time": 0,
        "last_roll_time": 0,
        "last_info_command_time": 0,
        "single_photo_counter": 0,
        "last_photo_group_id": 0,
        "message_counter": 0,
        "last_user_msgs": 0,
        "user_settings": 0,
        "thread_locks": 0,
        "anime_daily_tracker": 0,
        "image_spam_items": 0,
    }
    for board_id in BOARDS:
        b_data = board_data.get(board_id, {})
        totals["last_texts"] += _safe_len(b_data.get("last_texts", {}))
        totals["last_stickers"] += _safe_len(b_data.get("last_stickers", {}))
        totals["last_animations"] += _safe_len(b_data.get("last_animations", {}))
        totals["last_audios"] += _safe_len(b_data.get("last_audios", {}))
        totals["spam_violations"] += _safe_len(b_data.get("spam_violations", {}))
        spam_tracker = b_data.get("spam_tracker", {})
        if isinstance(spam_tracker, dict):
            totals["spam_tracker_users"] += len(spam_tracker)
            totals["spam_tracker_items"] += sum(_safe_len(items) for items in spam_tracker.values())
        reaction_tracker = b_data.get("reaction_rate_tracker", {})
        if isinstance(reaction_tracker, dict):
            totals["reaction_rate_users"] += len(reaction_tracker)
            totals["reaction_rate_items"] += sum(_safe_len(items) for items in reaction_tracker.values())
        reaction_queue = b_data.get("reaction_queue", {})
        if isinstance(reaction_queue, dict):
            totals["reaction_queue_users"] += len(reaction_queue)
            totals["reaction_queue_items"] += sum(_safe_len(items) for items in reaction_queue.values())
        for key in (
            "last_reaction_process_time", "last_roll_time", "last_info_command_time",
            "single_photo_counter", "last_photo_group_id", "message_counter",
            "last_user_msgs", "user_settings", "thread_locks", "anime_daily_tracker",
        ):
            totals[key] += _safe_len(b_data.get(key, {}))
    for timestamps in image_spam_tracker.values():
        totals["image_spam_items"] += _safe_len(timestamps)
    return totals
def _collect_runtime_snapshot() -> dict:

    queue_sizes = {board: message_queues[board].qsize() for board in BOARDS if board in message_queues}
    top_queues = sorted(queue_sizes.items(), key=lambda item: item[1], reverse=True)[:5]
    queue_age_summary = _summarize_live_queue_ages(queue_sizes)
    priority_counts = {board: _safe_len(weekly_active_users.get(board, set())) for board in BOARDS}
    pending_done = 0
    try:
        pending_done = sum(1 for task in pending_edit_tasks.values() if task.done())
    except Exception:
        pending_done = -1
    board_totals = {
        "active_users": 0,
        "shadow_mutes": 0,
        "regular_mutes": 0,
        "threads": 0,
        "user_state": 0,
        "last_activity": 0,
        "reaction_queue_items": 0,
    }
    for board_id in BOARDS:
        b_data = board_data.get(board_id, {})
        users = b_data.get("users", {})
        board_totals["active_users"] += _safe_len(users.get("active", []))
        board_totals["shadow_mutes"] += _safe_len(b_data.get("shadow_mutes", {}))
        board_totals["regular_mutes"] += _safe_len(b_data.get("mutes", {}))
        board_totals["threads"] += _safe_len(b_data.get("threads_data", {}))
        board_totals["user_state"] += _safe_len(b_data.get("user_state", {}))
        board_totals["last_activity"] += _safe_len(b_data.get("last_activity", {}))
        reaction_queue = b_data.get("reaction_queue", {})
        if isinstance(reaction_queue, dict):
            board_totals["reaction_queue_items"] += sum(_safe_len(q) for q in reaction_queue.values())
    board_map_totals = _collect_board_map_totals()
    recipient_counts = _recipient_counts_snapshot()
    try:
        all_tasks = asyncio.all_tasks()
        task_stats = {
            "total": len(all_tasks),
            "done": sum(1 for task in all_tasks if task.done()),
        }
    except RuntimeError:
        task_stats = {"total": 0, "done": 0}
    return {
        "utc": datetime.now(UTC).isoformat(),
        "post_counter": state.get("post_counter", 0),
        "memory": _get_process_memory_snapshot(),
        "db_files": _get_db_file_snapshot(),
        "controlled_stop": _controlled_stop_snapshot(),
        "queues": {
            "total": sum(queue_sizes.values()),
            "by_board": queue_sizes,
            "top": top_queues,
            "age_by_board": queue_age_summary["by_board"],
            "oldest": queue_age_summary["oldest"],
            "in_flight": queue_age_summary["in_flight"],
        },
        "delivery_priority": {
            "enabled": PRIORITY_DELIVERY_ENABLED,
            "split_fanout": PRIORITY_SPLIT_FANOUT_ENABLED,
            "split_min_passive": PRIORITY_SPLIT_MIN_PASSIVE,
            "passive_slice_size": PRIORITY_PASSIVE_SLICE_SIZE,
            "passive_media_slice_size": PRIORITY_PASSIVE_MEDIA_SLICE_SIZE,
            "pressure_slice_age_sec": PRIORITY_PRESSURE_SLICE_AGE_SEC,
            "pressure_passive_slice_size": PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE,
            "pressure_passive_media_slice_size": PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE,
            "passive_max_preemptions": PASSIVE_MAX_PREEMPTIONS,
            "priority_phase_budget_sec": PRIORITY_PHASE_BUDGET_SEC,
            "passive_phase_budget_sec": PASSIVE_PHASE_BUDGET_SEC,
        "delivery_initial_chunk_size": DELIVERY_INITIAL_CHUNK_SIZE,
        "delivery_min_chunk_size": DELIVERY_MIN_CHUNK_SIZE,
        "delivery_per_recipient_timeout_sec": DELIVERY_PER_RECIPIENT_TIMEOUT_SEC,
        "delivery_telegram_request_timeout_sec": DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC,
        "delivery_max_recipient_retries": DELIVERY_MAX_RECIPIENT_RETRIES,
        "delivery_phase_guard_sec": DELIVERY_PHASE_GUARD_SEC,
            "days": WEEKLY_ACTIVE_DAYS,
            "refresh_sec": WEEKLY_ACTIVE_REFRESH_SECONDS,
            "total_weekly_active": sum(priority_counts.values()),
            "by_board": priority_counts,
            "updated_at": weekly_active_updated_at.copy(),
        },
        "recipients": recipient_counts,
        "durable_delivery": {
            "enabled": DURABLE_DELIVERY_QUEUE_ENABLED,
            **durable_delivery_stats,
        },
        "anime_media": {
            "concurrency": ANIME_MEDIA_CONCURRENCY,
            "b_max_stacked_images": B_MAX_STACKED_ANIME_IMAGES,
            "url_timeout_sec": ANIME_URL_FETCH_TIMEOUT_SEC,
            "url_total_sec": ANIME_URL_FETCH_TOTAL_SEC,
            "url_parallel": ANIME_URL_FETCH_PARALLEL,
            "download_timeout_sec": ANIME_DOWNLOAD_TIMEOUT_SEC,
            "download_total_sec": ANIME_DOWNLOAD_TOTAL_SEC,
            "download_parallel": ANIME_DOWNLOAD_PARALLEL,
            "refill_rounds": ANIME_REFILL_ROUNDS,
        },
        "mode_punchup": {
            "enabled": MODE_PUNCHUP_ENABLED,
            "runtime_enabled": mode_punchup_runtime_enabled,
            "queue_shed_sec": MODE_PUNCHUP_QUEUE_SHED_SEC,
            "slow_log_us": MODE_PUNCHUP_SLOW_LOG_US,
            "stats": _summarize_mode_punchup_stats(),
        },
        "contextual_replies": {
            "enabled": CONTEXTUAL_REPLIES_ENABLED,
            "cooldown_sec": CONTEXTUAL_REPLY_COOLDOWN_SEC,
            "daily_limit": CONTEXTUAL_REPLY_DAILY_LIMIT,
            "groups_ru": _safe_len(CONTEXTUAL_REPLIES),
            "tracked_users": _safe_len(contextual_reply_tracker),
            "stats": dict(contextual_reply_stats),
        },
        "reply_coverage": {
            "updated_at": reply_coverage_updated_at,
            **reply_coverage_stats,
        },
        "delivery": _summarize_delivery_metrics(),
        "maps": {
            "messages_storage": _safe_len(messages_storage),
            "post_to_messages": _safe_len(post_to_messages),
            "message_to_post": _safe_len(message_to_post),
            "shadow_fake_post_counters": _safe_len(shadow_fake_post_counters),
            "pending_edit_tasks": _safe_len(pending_edit_tasks),
            "pending_edit_done": pending_done,
            "current_media_groups": _safe_len(current_media_groups),
            "media_group_timers": _safe_len(media_group_timers),
            "posts_pending_deletion": _safe_len(posts_pending_deletion),
            "unknown_command_tracker": _safe_len(unknown_command_tracker),
            "contextual_reply_tracker": _safe_len(contextual_reply_tracker),
            "user_spam_locks": _safe_len(user_spam_locks),
            "generate_locks": _safe_len(generate_locks),
            "user_last_thread_action": _safe_len(user_last_thread_action),
            "reaction_ratelimit": _safe_len(reaction_ratelimit),
            "last_poll_creation_time": _safe_len(last_poll_creation_time),
            "last_poll_vote_time": _safe_len(last_poll_vote_time),
            "user_hourly_image_count": _safe_len(user_hourly_image_count),
            "user_hourly_image_reset": _safe_len(user_hourly_image_reset),
            "author_reaction_notify_tracker": _safe_len(author_reaction_notify_tracker),
            "network_retry_state": _safe_len(network_retry_state),
            "image_spam_tracker": _safe_len(image_spam_tracker),
            "stream_cache": _safe_len(stream_cache),
            "graph_stats": _safe_len(graph_stats),
            "roulette_events": _safe_len(ROULETTE_EVENTS),
        },
        "board_maps": board_map_totals,
        "board_totals": board_totals,
        "asyncio_tasks": task_stats,
        "gc_count": gc.get_count(),
        "tracemalloc": {
            "enabled": tracemalloc.is_tracing(),
            "current_mb": round(tracemalloc.get_traced_memory()[0] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
            "peak_mb": round(tracemalloc.get_traced_memory()[1] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
        },
    }
def _format_runtime_snapshot(snapshot: dict) -> str:

    memory = snapshot.get("memory", {})
    queues = snapshot.get("queues", {})
    maps = snapshot.get("maps", {})
    board_maps = snapshot.get("board_maps", {})
    db_files = snapshot.get("db_files", {})
    board_totals = snapshot.get("board_totals", {})
    delivery_priority = snapshot.get("delivery_priority", {})
    recipients = snapshot.get("recipients", {})
    anime_media = snapshot.get("anime_media", {})
    durable_delivery = snapshot.get("durable_delivery", {})
    mode_punchup = snapshot.get("mode_punchup", {})
    mode_punchup_stats = mode_punchup.get("stats", {})
    contextual = snapshot.get("contextual_replies", {})
    contextual_stats = contextual.get("stats", {})
    reply_coverage = snapshot.get("reply_coverage", {})
    top_queue = ", ".join(f"{board}:{size}" for board, size in queues.get("top", [])) or "empty"
    oldest_queue = ", ".join(
        f"{board}:{age}s#{post_num}" for board, age, post_num in queues.get("oldest", [])
    ) or "empty"
    in_flight = ", ".join(
        f"{board}:#{data.get('post_num')} {data.get('phase', 'full')} "
        f"run={data.get('run_sec')}s age={data.get('age_sec')}s "
        f"rec={data.get('recipients', '-')}/{data.get('original_recipients', '-')}"
        for board, data in queues.get("in_flight", {}).items()
    ) or "none"
    return (
        f"<b>Runtime snapshot</b>\n"
        f"pid: <code>{memory.get('pid', '?')}</code>\n"
        f"rss/private/vms: <code>{memory.get('rss_mb', '?')} / {memory.get('private_mb', '?')} / {memory.get('vms_mb', '?')} MB</code>\n"
        f"threads/open_files: <code>{memory.get('threads', '?')} / {memory.get('open_files', '?')}</code>\n"
        f"queues total/top: <code>{queues.get('total', 0)} | {escape_html(top_queue)}</code>\n"
        f"queue oldest/current: <code>{escape_html(oldest_queue)} | {escape_html(in_flight)}</code>\n"
        f"reply copies: <code>{reply_coverage.get('copy_posts', 0)} posts / {reply_coverage.get('total_copies', 0)} copies span={reply_coverage.get('min_post', '-')}-{reply_coverage.get('max_post', '-')}</code>\n"
        f"recipients: <code>telegram={recipients.get('telegram_active_total', '?')} top={escape_html(str(recipients.get('top', [])))}</code>\n"
        f"priority active: <code>{delivery_priority.get('total_weekly_active', 0)} users / {delivery_priority.get('days', '?')}d enabled={delivery_priority.get('enabled')} split={delivery_priority.get('split_fanout')} slice={delivery_priority.get('passive_slice_size')}/{delivery_priority.get('passive_media_slice_size')} priority_budget={delivery_priority.get('priority_phase_budget_sec')}s passive_budget={delivery_priority.get('passive_phase_budget_sec')}s guard={delivery_priority.get('delivery_phase_guard_sec')}s uid_timeout={delivery_priority.get('delivery_per_recipient_timeout_sec')}s uid_retries={delivery_priority.get('delivery_max_recipient_retries')}</code>\n"
        f"durable delivery: <code>enabled={durable_delivery.get('enabled')} saved={durable_delivery.get('persisted', 0)} fail={durable_delivery.get('persist_failed', 0)} restored={durable_delivery.get('restored_items', 0)}/{durable_delivery.get('restored_recipients', 0)} deleted={durable_delivery.get('deleted', 0)}</code>\n"
        f"anime media: <code>conc={anime_media.get('concurrency')} b_max={anime_media.get('b_max_stacked_images')}</code>\n"
        f"mode punch-up: <code>enabled={mode_punchup.get('enabled')} runtime={mode_punchup.get('runtime_enabled')} shed={mode_punchup.get('queue_shed_sec')}s calls={mode_punchup_stats.get('calls', 0)} avg/max={mode_punchup_stats.get('avg_us', 0)}/{mode_punchup_stats.get('max_us', 0)}us skip_load={mode_punchup_stats.get('skipped_load', 0)}</code>\n"
        f"contextual replies: <code>enabled={contextual.get('enabled')} groups={contextual.get('groups_ru')} cooldown={contextual.get('cooldown_sec')}s daily={contextual.get('daily_limit')} sent={contextual_stats.get('sent', 0)} skip_cd={contextual_stats.get('skipped_cooldown', 0)}</code>\n"
        f"db/wal/shm: <code>{db_files.get('db_mb', 0)} / {db_files.get('wal_mb', 0)} / {db_files.get('shm_mb', 0)} MB</code>\n"
        f"post maps: <code>messages={maps.get('messages_storage')} post_to={maps.get('post_to_messages')} msg_to={maps.get('message_to_post')}</code>\n"
        f"tasks/media: <code>pending={maps.get('pending_edit_tasks')} done={maps.get('pending_edit_done')} media={maps.get('current_media_groups')} timers={maps.get('media_group_timers')}</code>\n"
        f"users/threads/reactions: <code>{board_totals.get('active_users')} / {board_totals.get('threads')} / {board_totals.get('reaction_queue_items')}</code>\n"
        f"cooldowns/spam/img: <code>roll={board_maps.get('last_roll_time')} info={board_maps.get('last_info_command_time')} spam={board_maps.get('spam_tracker_items')} img={board_maps.get('image_spam_items')}</code>\n"
        f"tracemalloc: <code>{snapshot.get('tracemalloc', {}).get('enabled')} current={snapshot.get('tracemalloc', {}).get('current_mb')}MB peak={snapshot.get('tracemalloc', {}).get('peak_mb')}MB</code>"
    )
@dp.errors()
async def global_error_handler(event: types.ErrorEvent) -> bool:
    """
    Улучшенный и отказоустойчивый обработчик ошибок для aiogram.
    Сохраняет всю оригинальную логику и добавляет обработку сетевых сбоев.
    """
    exception = event.exception
    update = event.update
    if exception is None:
        if update:
            update_info = f"Update {update.update_id}"
            if update.message: update_info += f" from user {update.message.from_user.id}"
            print(f"⚠️ Event without exception: {update_info}")
        else:
            print("⚠️ Получено событие без исключения и без update")
        return True
    if isinstance(exception, (TelegramNetworkError, aiohttp.ClientConnectorError, asyncio.TimeoutError, TelegramRetryAfter)):
        print(f"🌐 Перехвачена штатная сетевая ошибка/флуд-контроль: {type(exception).__name__}: {exception}. Выполнение не блокируется.")
        return True
    if isinstance(exception, TelegramForbiddenError):
        user_id, telegram_object = None, None
        if update and update.message:
            user_id, telegram_object = update.message.from_user.id, update.message
        elif update and update.callback_query:
            user_id, telegram_object = update.callback_query.from_user.id, update.callback_query
        if user_id and telegram_object:
            board_id = get_board_id(telegram_object)
            if board_id:
                async with storage_lock:
                    b_data = board_data[board_id]
                    b_data['users']['active'].discard(user_id)
                    for store in [b_data['last_activity'], b_data['last_texts'], b_data['last_stickers'],
                                  b_data['last_animations'], b_data['last_audios'], b_data['spam_violations'], 
                                  b_data['spam_tracker'], b_data['last_user_msgs'], 
                                  b_data['message_counter'], b_data['user_state'],
                                  b_data.get('user_streams', {})]:
                        store.pop(user_id, None)
                async with author_reaction_notify_lock:
                    author_reaction_notify_tracker.pop(user_id, None)
                
                user_spam_locks.pop(user_id, None)
                generate_locks.pop(user_id, None)
                unknown_command_tracker.pop(user_id, None)
                await remove_user_from_board(user_id, board_id)
                print(f"🚫 [{board_id}] Юзер {user_id} блокнул бота. Данные удалены (RAM почистится автоматически).")
        return True
    if isinstance(exception, TelegramConflictError):
        print(f"🌐 Конфликт: {exception}. Возможно, запущен другой экземпляр бота.")
        await asyncio.sleep(10)
        return True
    else:
        import traceback
        print("⛔⛔⛔ НЕПРЕДВИДЕННАЯ КРИТИЧЕСКАЯ ОШИБКА ⛔⛔⛔")
        print(f"Exception: {type(exception).__name__}: {exception}")
        traceback.print_exc()
        if update:
            try:
                update_json = update.model_dump_json(exclude_none=True, indent=2)
                print(f"--- Update Context ---\n{update_json}\n--- End Update Context ---")
            except Exception as json_e:
                print(f"Не удалось сериализовать update: {json_e}")
        return True
def is_admin(uid: int, board_id: str) -> bool:

    if not board_id:
        return False
    return uid in BOARD_CONFIG.get(board_id, {}).get('admins', set())
async def get_board_activity_last_hours(board_id: str, hours: int = 2) -> float:
    if hours <= 0: return 0.0
    time_threshold = datetime.now(UTC) - timedelta(hours=hours)
    post_count = 0
    async with storage_lock:
        for post_data in reversed(messages_storage.values()):
            if post_data.get("timestamp") < time_threshold: break
            if post_data.get("board_id") == board_id:
                post_count += 1
    return post_count / hours
def _sync_save_threads_data(board_id: str, data_to_save: dict):

    threads_file = os.path.join(DATA_DIR, f"{board_id}_threads.json")
    try:
        with open(threads_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⛔ [{board_id}] Ошибка в потоке сохранения _threads.json: {e}")
        return False
def _sync_save_user_states(board_id: str, data_to_save: dict):

    user_states_file = os.path.join(DATA_DIR, f"{board_id}_user_states.json")
    try:
        with open(user_states_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⛔ [{board_id}] Ошибка в потоке сохранения _user_states.json: {e}")
        return False
async def save_user_states(board_id: str):

    if board_id not in THREAD_BOARDS:
        return
    async with storage_lock:
        data_to_save = board_data[board_id].get('user_state', {}).copy()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        save_executor,
        _sync_save_user_states,
        board_id,
        data_to_save
    )
async def load_state():
    """
    Загружает состояние бота.
    Сначала проверяет, была ли произведена миграция в SQLite.
    Если да - загружает из БД. Если нет - загружает из старых JSON-файлов.
    """
    global state, messages_storage, board_data, post_to_messages, message_to_post
    if not await is_database_migrated():
        print("⚠️ База данных не заполнена. Загрузка из старых JSON-файлов больше не поддерживается.")
        print("⛔ Запуск невозможен. Пожалуйста, выполните миграцию или удалите старые JSON-файлы состояния для чистого старта.")
        sys.exit(1)
    print("✅ Обнаружена база данных. Загрузка состояния из SQLite...")
    db_state = await load_state_from_db(THREAD_BOARDS)
    state['post_counter'] = db_state.get('post_counter', 0)
    messages_storage.update(db_state.get('messages_storage', {}))
    post_to_messages.update(db_state.get('post_to_messages', {}))
    message_to_post.update(db_state.get('message_to_post', {}))
    for board_id, data in db_state.get('board_data', {}).items():
        board_data[board_id].update(data)
    spam_words_map = await load_all_spam_words()
    for board_id, words_set in spam_words_map.items():
        board_data[board_id]['spam_filter_words'] = words_set
    reaction_bans_map = await load_all_reaction_bans()
    for board_id, banned_set in reaction_bans_map.items():
        board_data[board_id]['reaction_banned_users'] = banned_set
    print(f"✅ Состояние из SQLite загружено. Общий счетчик постов: {state['post_counter']}")
    for board_id in BOARDS:
        b_data = board_data.get(board_id, {})
        active_users = b_data.get('users', {}).get('active', [])
        banned_users = b_data.get('users', {}).get('banned', [])
        active_count = len(active_users)
        active_tg_count = sum(1 for uid in active_users if isinstance(uid, int) and uid > 0)
        active_site_count = sum(1 for uid in active_users if isinstance(uid, int) and uid < 0)
        banned_count = len(banned_users)
        banned_tg_count = sum(1 for uid in banned_users if isinstance(uid, int) and uid > 0)
        if active_count > 0 or banned_count > 0:
             print(f"  -> [{board_id}] Загружено: "
                  f"tg_active = {active_tg_count}, "
                  f"site_active = {active_site_count}, "
                  f"active_total = {active_count}, "
                  f"tg_banned = {banned_tg_count}, "
                  f"banned_total = {banned_count}")
async def graceful_shutdown(bots: list[Bot], healthcheck_site: web.TCPSite | None = None, emergency: bool = False):
    """
    Корректное завершение работы.
    Адаптировано под архитектуру WAL + isolation_level=None + db_lock.
    """
    global is_shutting_down
    if is_shutting_down:
        return
    is_shutting_down = True
    
    # Импортируем лок для безопасного доступа к БД
    from common.db_pool import get_pool, db_lock, close_pool
    
    reason = "АВАРИЙНЫЙ (OOM)" if emergency else "ШТАТНЫЙ"
    print(f"🛑 [{reason}] Начинаем процедуру остановки...")
    
    try:
        await dp.stop_polling()
        print("⏸ Polling остановлен.")
    except Exception: pass

    # Бэкап (если не OOM)
   # if not emergency:
   #    print("💾 Создание полного бэкапа БД...")
   #     try:
   #       #  loop = asyncio.get_running_loop()
    #        await asyncio.wait_for(
   #             loop.run_in_executor(save_executor, create_gzipped_dump, DB_PATH_CONFIG, DATA_DIR),
          #      timeout=20.0
      #      )
     #       print("✅ Бэкап создан.")
     #   except asyncio.TimeoutError:
    #        print("⚠️ Бэкап занял слишком много времени, пропускаем.")
    #    except Exception as e:
    #        print(f"⚠️ Ошибка бэкапа: {e}")
    #else:
     #   print("⚠️ ПРОПУСК БЭКАПА (мало памяти).")

    # Сброс WAL на диск
    print("💾 Сброс данных из WAL на диск...")
    try:
        # Используем лок, чтобы не прервать активную транзакцию
        async with db_lock:
            db = await get_pool()
            # В режиме isolation_level=None PRAGMA выполняется сразу. Commit не нужен.
            # Используем TRUNCATE для полной очистки WAL перед выходом
            await db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            print("✅ Данные успешно сохранены на диск (WAL Truncated).")
    except Exception as e:
        print(f"⛔ Ошибка сохранения WAL: {e}")

    try:
        print("🛑 Отмена фоновых задач перед закрытием БД...")
        async with pending_edit_lock:
            for task in pending_edit_tasks.values():
                task.cancel()
        
        if healthcheck_site: await healthcheck_site.stop()
        await asyncio.sleep(2.0)
        
        # Закрываем пул (внутри db_pool.py тоже есть защита)
        await close_pool()
        
        git_executor.shutdown(wait=False, cancel_futures=True)
        save_executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        print(f"⚠️ Ошибка при shutdown: {e}")
        
    print("✅ Готово к выходу.")
async def log_memory_summary():
    """
    Максимально подробный анализ и логгирование состояния памяти, размеров структур,
    топ-5 тяжёлых пользователей/тредов, распределение типов объектов, количество задач и алерты.
    Всё выводится в stdout.
    """
    if not hasattr(log_memory_summary, "previous_stats"):
        log_memory_summary.previous_stats = {}
    previous_stats = log_memory_summary.previous_stats
    current_stats = {}
    import sys
    import gc
    from collections import Counter
    print(f"\n--- 📝 Запуск анализа памяти в {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} ---")
    gc_count = gc.collect()
    print(f"GC.collect() завершён, удалено объектов: {gc_count}")
    current_stats['messages_storage'] = len(messages_storage)
    current_stats['post_to_messages'] = len(post_to_messages)
    current_stats['message_to_post'] = len(message_to_post)
    for board_id in BOARDS:
        b_data = board_data[board_id]
        current_stats[f"board[{board_id}].threads"] = len(b_data.get('threads_data', {}))
        current_stats[f"board[{board_id}].user_state"] = len(b_data.get('user_state', {}))
        current_stats[f"board[{board_id}].last_user_msgs"] = len(b_data.get('last_user_msgs', {}))
    stats_lines = []
    print("--- MEMORY STRUCTURE STATS (current / delta) ---")
    sorted_keys = sorted(current_stats.keys())
    for key in sorted_keys:
        current_val = current_stats[key]
        prev_val = previous_stats.get(key, current_val)
        delta = current_val - prev_val
        delta_str = f" ({delta:+})"
        stats_lines.append(f"{key:<30}: {current_val}{delta_str}")
    print("\n".join(stats_lines))
    log_memory_summary.previous_stats = current_stats
    for board_id in BOARDS:
        threads_data = board_data[board_id].get('threads_data', {})
        if threads_data:
            top_threads = sorted(threads_data.items(), key=lambda item: len(item[1].get('posts', [])), reverse=True)[:5]
            print(f"board[{board_id}]: TOP-5 THREADS BY POSTS:")
            for tid, tinfo in top_threads:
                print(f"    thread_id {tid}: posts={len(tinfo.get('posts', []))}, subs={len(tinfo.get('subscribers', set()))}")
    for board_id in BOARDS:
        last_user_msgs = board_data[board_id].get('last_user_msgs', {})
        if last_user_msgs:
            top_users = sorted(last_user_msgs.items(), key=lambda item: len(item[1]), reverse=True)[:5]
            print(f"board[{board_id}]: TOP-5 USERS BY last_user_msgs:")
            for uid, dq in top_users:
                print(f"    user_id {uid}: msgs={len(dq)}")
    for board_id in BOARDS:
        user_state = board_data[board_id].get('user_state', {})
        if user_state:
            top_users = sorted(user_state.items(), key=lambda item: item[1].get('last_seen_main', 0), reverse=True)[:5]
            print(f"board[{board_id}]: TOP-5 ACTIVE USERS (last_seen_main):")
            for uid, st in top_users:
                print(f"    user_id {uid}: last_seen_main={st.get('last_seen_main', 0)} location={st.get('location', 'main')}")
    if post_to_messages:
        top_posts = sorted(post_to_messages.items(), key=lambda item: len(item[1]), reverse=True)[:5]
        print(f"TOP-5 POSTS BY recipients in post_to_messages:")
        for pnum, recips in top_posts:
            print(f"    post_num {pnum}: recipients={len(recips)}")
    all_gc_objs = gc.get_objects()
    type_counts = Counter(type(obj).__name__ for obj in all_gc_objs)
    print("--- DISTRIBUTION OF OBJECT TYPES IN GC ---")
    for tname, count in type_counts.most_common(10):
        print(f"    {tname}: {count}")
    print(f"Total objects tracked by GC: {len(all_gc_objs)}")
    tasks = asyncio.all_tasks()
    print(f"Active asyncio.Tasks: {len(tasks)}")
    print(f"Top-5 running coroutines:")
    task_info_lines = []
    for task in tasks:
        if not task.done():
            coro = task.get_coro()
            coro_name = getattr(coro, '__qualname__', str(coro))
            task_info_lines.append(f"    - {coro_name}")
    for line in task_info_lines[:5]:
        print(line)
    if len(messages_storage) > MAX_MESSAGES_IN_MEMORY * 2:
        print(f"⚠️ ALERT: messages_storage size={len(messages_storage)} > DOUBLE LIMIT ({MAX_MESSAGES_IN_MEMORY * 2})")
    for board_id in BOARDS:
        if len(board_data[board_id].get('user_state', {})) > 8000:
            print(f"⚠️ ALERT: board[{board_id}].user_state size={len(board_data[board_id]['user_state'])} > 8000")
        if len(board_data[board_id].get('threads_data', {})) > MAX_ACTIVE_THREADS * 2:
            print(f"⚠️ ALERT: board[{board_id}].threads_data size={len(board_data[board_id]['threads_data'])} > DOUBLE THREAD LIMIT")
    print("--- ✅ Максимально подробный анализ памяти завершён ---\n")
async def auto_memory_cleaner():
    """
    Очистка мусора и обслуживание БД.
    Адаптировано под db_lock.
    """
    from common.db_pool import get_pool, db_lock
    last_db_cleanup_time = datetime.now(UTC)
    REAL_RAM_LIMIT = MAX_MESSAGES_IN_MEMORY
    
    while True:
        await asyncio.sleep(1800) 
        
        # 1. Отложенное удаление постов (delete_post_by_num уже безопасен)
        if posts_pending_deletion:
            posts_to_delete_now = list(posts_pending_deletion)
            posts_pending_deletion.clear()
            deleted_count_from_db = 0
            for post_num in posts_to_delete_now:
                if await delete_post_by_num(post_num):
                    deleted_count_from_db += 1
            if deleted_count_from_db > 0:
                print(f"🧹 [GC] Отложенное удаление: {deleted_count_from_db} постов.")

        # 2. Тяжелая очистка БД и VACUUM
        if datetime.now(UTC) - last_db_cleanup_time > DB_CLEANUP_INTERVAL:
            try:
                loop = asyncio.get_running_loop()
                # cleanup_old_posts_from_db - синхронная, внутри создает свое соединение.
                # Это безопасно в WAL, но может вызвать busy, если бот активен.
                await loop.run_in_executor(
                    save_executor,
                    cleanup_old_posts_from_db,
                    DB_POST_LIMIT
                )
                last_db_cleanup_time = datetime.now(UTC)
                print("🧹 [GC] БД очищена от старого мусора.")
                
                # Чекпоинт WAL под защитой лока
                async with db_lock:
                    for attempt in range(5):
                        try:
                            db = await get_pool()
                            await db.execute("PRAGMA wal_checkpoint(PASSIVE);")
                            print("💾 [DB] WAL Checkpoint (Passive) выполнен.")
                            break
                        except Exception as e:
                            if "locked" in str(e).lower():
                                await asyncio.sleep(1)
                                continue
                            print(f"⚠️ Ошибка чекпоинта БД: {e}")
                            break
                        
            except Exception as e:
                print(f"⛔ [GC] Ошибка обслуживания БД: {e}")

        # 3. Очистка RAM (ИСПРАВЛЕНО: удаление обратных ссылок)
        async with storage_lock:
            current_size = len(messages_storage)
            if current_size > REAL_RAM_LIMIT:
                sorted_keys = sorted(messages_storage.keys())
                to_delete_count = current_size - REAL_RAM_LIMIT
                keys_to_delete = sorted_keys[:to_delete_count]
                
                deleted_map_entries = 0
                for post_num in keys_to_delete:
                    messages_storage.pop(post_num, None)
                    deleted_map_entries += _drop_post_copy_maps_unlocked(post_num)
                
                print(f"🧹 [GC] RAM Purge: выгружено {len(keys_to_delete)} постов и {deleted_map_entries} ссылок.")

            removed_copy_posts, removed_copy_refs = _trim_post_copy_maps_unlocked(MAX_COPY_MAP_POSTS_IN_MEMORY)
            if removed_copy_posts:
                print(f"🧹 [GC] Copy map cap: удалено {removed_copy_posts} постов и {removed_copy_refs} ссылок из RAM-кэша копий.")

            orphan_reverse_count = _purge_orphan_message_to_post_unlocked()
            if orphan_reverse_count:
                print(f"🧹 [GC] Reverse map purge: удалено {orphan_reverse_count} старых message_to_post кэш-ссылок.")

            # Очистка кэшей юзеров...
            now_utc = datetime.now(UTC)
            INACTIVE_THRESHOLD = timedelta(hours=1)
            
            for board_id in BOARDS:
                b_data = board_data[board_id]
                last_activity_map = b_data['last_activity']
                board_inactive_users = {
                    uid for uid, last_ts in last_activity_map.items()
                    if now_utc - last_ts > INACTIVE_THRESHOLD
                }
                
                if board_inactive_users:
                    caches_to_prune = [
                        b_data['last_texts'], b_data['last_stickers'],
                        b_data['last_animations'], b_data['last_audios'],
                        b_data['spam_violations'], b_data['spam_tracker'],
                        b_data['message_counter'], b_data['last_user_msgs'],
                        b_data['last_roll_time'], b_data['reaction_rate_tracker'],
                        b_data['reaction_queue'], b_data['last_reaction_process_time'],
                        b_data.get('last_info_command_time', {}),
                        b_data.get('last_generate_time', {}),
                        b_data.get('single_photo_counter', {}),
                        b_data.get('anime_daily_tracker', {}),
                        # --- ИЗМЕНЕНО: Добавлена очистка user_state и last_photo_group_id ---
                        b_data.get('user_state', {}),         # <--- Очистка навигации
                        b_data.get('last_photo_group_id', {}) # <--- Очистка ID альбомов
                        # --------------------------------------------------------------------
                    ]
                    
                    for user_id in board_inactive_users:
                        for cache in caches_to_prune:
                            if isinstance(cache, dict): cache.pop(user_id, None)
                        last_activity_map.pop(user_id, None)
                    
                    async with author_reaction_notify_lock:
                        for user_id in board_inactive_users:
                            author_reaction_notify_tracker.pop(user_id, None)
                thread_locks = b_data.get('thread_locks', {})
                threads_data = b_data.get('threads_data', {})
                if isinstance(thread_locks, dict):
                    for thread_id in list(thread_locks.keys()):
                        if thread_id not in threads_data:
                            thread_locks.pop(thread_id, None)

            # Очистка глобальных кэшей
            global_caches_to_clean = [
                user_spam_locks, generate_locks, unknown_command_tracker,
                user_hourly_image_count, user_hourly_image_reset,
                user_last_thread_action, reaction_ratelimit,
                last_poll_creation_time, last_poll_vote_time,
                shadow_fake_post_counters
            ]
            now_ts = time.time()
            for board_id, timestamps in list(image_spam_tracker.items()):
                fresh_timestamps = [
                    ts for ts in timestamps
                    if isinstance(ts, (int, float)) and now_ts - float(ts) < IMAGE_SPAM_WINDOW
                ]
                if fresh_timestamps:
                    image_spam_tracker[board_id] = fresh_timestamps
                else:
                    image_spam_tracker.pop(board_id, None)
            for uid, reset_ts in list(user_hourly_image_reset.items()):
                if now_ts - float(reset_ts or 0) > 7200:
                    user_hourly_image_reset.pop(uid, None)
                    user_hourly_image_count.pop(uid, None)
            for board_id in BOARDS:
                daily_tracker = board_data[board_id].get('anime_daily_tracker', {})
                for uid, tracker in list(daily_tracker.items()):
                    reset_at = float((tracker or {}).get('reset_at') or 0)
                    if reset_at and now_ts - reset_at > 3600:
                        daily_tracker.pop(uid, None)
            for cache, ttl in (
                (user_last_thread_action, 3600),
                (reaction_ratelimit, 300),
                (last_poll_creation_time, 3600),
                (last_poll_vote_time, 600),
            ):
                for uid, ts in list(cache.items()):
                    if now_ts - float(ts or 0) > ttl:
                        cache.pop(uid, None)
            async with author_reaction_notify_lock:
                for uid, timestamps in list(author_reaction_notify_tracker.items()):
                    if not timestamps or now_ts - float(timestamps[-1] or 0) > 300:
                        author_reaction_notify_tracker.pop(uid, None)
            for uid, timestamps in list(unknown_command_tracker.items()):
                fresh_timestamps = [
                    ts for ts in timestamps
                    if isinstance(ts, (int, float)) and (ts > now_ts or now_ts - float(ts) < 300)
                ]
                if fresh_timestamps:
                    unknown_command_tracker[uid] = fresh_timestamps
                else:
                    unknown_command_tracker.pop(uid, None)
            for cache in global_caches_to_clean:
                if len(cache) > 10000: cache.clear()
            
            async with pending_edit_lock:
                finished_edit_tasks = [pnum for pnum, task in pending_edit_tasks.items() if task.done()]
                for pnum in finished_edit_tasks:
                    pending_edit_tasks.pop(pnum, None)

        # Очистка медиа-групп
        stale_groups = [gid for gid in current_media_groups if gid not in media_group_timers]
        if stale_groups:
             for group_id in stale_groups:
                 current_media_groups.pop(group_id, None)
        
        gc.collect()
        print(f"🧹 Очистка памяти завершена.")
def _sync_collect_board_statistics(hour_ago: datetime, posts_meta_list: list[tuple]) -> defaultdict[str, int]:
    """
    Синхронная, блокирующая функция для сбора статистики.
    Работает с легковесным списком метаданных (timestamp, board_id).
    """
    posts_per_hour = defaultdict(int)
    for post_time, b_id in posts_meta_list:
        if post_time >= hour_ago and b_id:
            posts_per_hour[b_id] += 1
    return posts_per_hour
async def board_statistics_broadcaster():
    """
    Раз в 3 часа собирает общую статистику и рассылает на каждую доску
    локализованные версии. Названия досок кликабельны.
    """
    await asyncio.sleep(300)
    while True:
        try:
            await asyncio.sleep(14400) # 4 часа
            now = datetime.now(UTC)
            hour_ago = now - timedelta(hours=1)
            posts_meta_for_analysis = []
            async with storage_lock:
                for post_data in reversed(messages_storage.values()):
                    post_time = post_data.get('timestamp')
                    if not post_time or post_time < hour_ago:
                        break 
                    posts_meta_for_analysis.append(
                        (post_time, post_data.get('board_id'))
                    )
            loop = asyncio.get_running_loop()
            posts_per_hour = await loop.run_in_executor(
                save_executor,
                _sync_collect_board_statistics,
                hour_ago,
                posts_meta_for_analysis
            )
            for board_id in BOARDS:
                if board_id == 'test': continue
                activity = await get_board_activity_last_hours(board_id, hours=2)
                if activity < 90:
                    continue
                b_data = board_data[board_id]
                streams_to_process = ['ru']
                if board_id == 'int':
                    streams_to_process = ['en']
                elif ENABLE_MULTILANG:
                    streams_to_process = ['ru', 'en', 'jp']
                for stream in streams_to_process:
                    if board_id == 'int':
                        recipients = b_data['users']['active'] - b_data['users']['banned']
                    else:
                        if ENABLE_MULTILANG:
                            stream_users = await get_stream_active_users(board_id, stream)
                            recipients = stream_users.intersection(b_data['users']['active']) - b_data['users']['banned']
                        else:
                            if stream != 'ru': continue
                            recipients = b_data['users']['active'] - b_data['users']['banned']
                    if not recipients: continue
                    stats_lines = []
                    for b_id_inner, config_inner in BOARD_CONFIG.items():
                        if b_id_inner == 'test': continue
                        # Фильтр: только доски с юзернеймом (реальные)
                        bot_username = config_inner.get('username')
                        if not bot_username: continue
                        
                        clean_username = bot_username.replace('@', '')
                        board_name_display = config_inner['name']
                        
                        # Формируем кликабельную ссылку
                        display_html = f'<a href="https://t.me/{clean_username}">{board_name_display}</a>'

                        hour_stat = posts_per_hour.get(b_id_inner, 0)
                        total_stat = board_data[b_id_inner].get('board_post_count', 0)
                        
                        # Убрали <b> из шаблонов, так как теги теперь в display_html
                        if stream == 'en':
                            tpl = "{name} - {hour} pst/hr, total: {total}"
                        elif stream == 'jp':
                            tpl = "{name} - {hour} レス/時, 合計: {total}"
                        else:
                            tpl = "{name} - {hour} пст/час, всего: {total}"
                        
                        stats_lines.append(tpl.format(
                            name=display_html,
                            hour=hour_stat,
                            total=total_stat
                        ))
                    if stream == 'en':
                        header_text = "📊 Boards Statistics:\n"
                        header_title = "### Statistics ###"
                        captions = DVACH_STATS_CAPTIONS_EN
                    elif stream == 'jp':
                        header_text = "📊 板統計:\n"
                        header_title = "### 統計 ###"
                        captions = DVACH_STATS_CAPTIONS_JP
                    else:
                        header_text = "📊 Статистика досок:\n"
                        header_title = "### Статистика ###"
                        captions = DVACH_STATS_CAPTIONS
                    full_stats_text = header_text + "\n".join(stats_lines)
                    if random.random() < 0.76:
                        dvach_caption = random.choice(captions)
                        full_stats_text = f"{full_stats_text}\n\n<i>{dvach_caption}</i>"
                    content = {"type": "text", "text": full_stats_text, "is_system_message": True}
                    post_num = await create_post(
                        board_id=board_id, author_id=0, content=content,
                        timestamp=now.timestamp(), is_from_site=False, stream=stream
                    )
                    if not post_num: continue
                    header = await format_header(board_id, post_num, stream=stream)
                    if board_id != 'int':
                         content['header'] = f"{header_title}\n{header}"
                    else:
                         content['header'] = header
                    await update_post_content(post_num, content)
                    async with storage_lock:
                        messages_storage[post_num] = {'author_id': 0, 'timestamp': now, 'content': content, 'board_id': board_id}
                    await enqueue_board_message(board_id, {
                        "recipients": recipients, "content": content, 
                        "post_num": post_num, "board_id": board_id
                    })
                    print(f"✅ [{board_id}] Статистика ({stream}) #{post_num} добавлена в очередь.")
        except Exception as e:
            print(f"❌ Ошибка в board_statistics_broadcaster: {e}")
            await asyncio.sleep(120)
async def _activate_mode(board_id: str, mode_to_enable: str):
    """
    Активирует режим. Не трогает закрепы и другие настройки.
    """
    all_modes = MODE_FLAGS
    async with storage_lock:
        b_data = board_data[board_id]
        if b_data.get('active_mode_task') and not b_data['active_mode_task'].done():
            b_data['active_mode_task'].cancel()
        for mode in all_modes:
            b_data[mode] = (mode == mode_to_enable)
        b_data['last_mode_activation'] = datetime.now(UTC)
    settings_updates = {mode: (mode == mode_to_enable) for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    print(f"DB: [{board_id}] Режим {mode_to_enable} активирован.")
async def setup_pinned_messages(bots: dict[str, Bot]):

    for board_id, bot_instance in bots.items():
        b_data = board_data[board_id]
        languages = ['ru', 'en', 'jp']
        start_messages = {}
        for lang in languages:
            board_links = generate_boards_list(BOARD_CONFIG, lang)
            if lang == 'en':
                base_help = random.choice(HELP_TEXT_EN_COMMANDS)
                boards_head = "🌐 <b>All boards:</b>"
                thread_info = (
                    "\n\n<b>This board supports threads!</b>\n"
                    "/create &lt;title&gt; - Create a new thread\n"
                    "/threads - View active threads\n"
                    "/leave - Return to the main board from a thread"
                ) if board_id in THREAD_BOARDS else ""
            elif lang == 'jp':
                base_help = random.choice(HELP_TEXT_JP_COMMANDS)
                boards_head = "🌐 <b>全板一覧:</b>"
                thread_info = (
                    "\n\n<b>この板はスレッドに対応しています！</b>\n"
                    "/create &lt;タイトル&gt; - 新規スレ作成\n"
                    "/threads - スレ一覧を見る\n"
                    "/leave - スレから板に戻る"
                ) if board_id in THREAD_BOARDS else ""
            else: # ru
                base_help = random.choice(HELP_TEXT_COMMANDS)
                boards_head = "🌐 <b>Все доски:</b>"
                thread_info = (
                    "\n\n<b>На этой доске есть треды!</b>\n"
                    "/create &lt;заголовок&gt; - Создать новый тред\n"
                    "/threads - Посмотреть активные треды\n"
                    "/leave - Вернуться на доску из треда"
                ) if board_id in THREAD_BOARDS else ""
            full_text = f"{base_help}\n{thread_info}\n\n{board_links}"
            start_messages[lang] = full_text
        b_data['start_message_map'] = start_messages
        default_lang = 'en' if board_id == 'int' else 'ru'
        b_data['start_message_text'] = start_messages[default_lang]
        print(f"📌 [{board_id}] Тексты помощи (RU/EN/JP) подготовлены.")
async def get_board_chunk(board_id: str, hours: int = 6, thread_id: str | None = None, lang: str | None = None) -> str:

    now = datetime.now(UTC)
    time_threshold = now - timedelta(hours=hours)
    lines = []
    async with storage_lock:
        storage_copy = list(messages_storage.values())
    post_iterator = storage_copy
    if thread_id:
        b_data = board_data[board_id]
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if not thread_info:
            return "" # Возвращаем пустую строку, если тред не найден
        thread_post_nums = set(thread_info.get('posts', []))
        post_iterator = [p for p_num, p in messages_storage.items() if p_num in thread_post_nums]
        time_threshold = datetime.min.replace(tzinfo=UTC)
    for post in post_iterator:
        try:
            if post.get('board_id') != board_id:
                continue
            if post.get('timestamp', now) < time_threshold:
                continue
            if post.get('author_id') == 0: # Игнорируем системные сообщения
                continue
            content = post.get('content', {})
            ttype = content.get('type')
            if ttype == 'text':
                text = content.get('text', '')
                text = clean_html_tags(text)
                text = re.sub(r'^(Пост №\d+.*?\n|Post No\.\d+.*?\n)', '', text, flags=re.MULTILINE)
                text = re.sub(r'^(###.*?###|<i>.*?</i>)\s*\n?', '', text, flags=re.MULTILINE)
                text = text.strip()
                if text:
                    author_id = post.get('author_id')
                    name = content.get('username') or content.get('name') or content.get('author_name')
                    if not name:
                        if not lang:
                            lang = 'en' if board_id == 'int' else 'ru'
                        if author_id and author_id != 0:
                            suffix = str(author_id)[-4:]
                            if lang == 'en':
                                name = f"Anon #{suffix}"
                            elif lang == 'jp':
                                name = f"名無し #{suffix}"
                            else:
                                name = f"Анон #{suffix}"
                        else:
                            if lang == 'en':
                                name = "Anon"
                            elif lang == 'jp':
                                name = "名無し"
                            else:
                                name = "Анон"
                    reply_to = content.get('reply_to_post') or post.get('reply_to_post_num')
                    reply_suffix = ""
                    if reply_to:
                        if not lang:
                            lang = 'en' if board_id == 'int' else 'ru'
                        if lang == 'en':
                            reply_suffix = f" (reply to №{reply_to})"
                        elif lang == 'jp':
                            reply_suffix = f" (>>{reply_to})"
                        else:
                            reply_suffix = f" (ответ на №{reply_to})"
                    lines.append(f"{name}{reply_suffix}: {text}")
        except Exception as e:
            print(f"[summarize] Error while chunking post: {e}, post: {post}")
    full_text = "\n".join(lines)
    cleaned_chunk = re.sub(r'\n{2,}', '\n', full_text).strip()
    context_name = f"thread {thread_id}" if thread_id else f"board {board_id}"
    print(f"[summarize] Chunk for {context_name} built, len={len(cleaned_chunk)}")
    return cleaned_chunk[:35000]
async def check_spam(user_id: int, msg: Message, board_id: str) -> bool:

    b_data = board_data[board_id]
    if is_admin(user_id, board_id):
        return True # Админу можно всё, спам-фильтр пропускает
    if msg.content_type == 'text':
        msg_type = 'text'
        content = msg.text
    elif msg.content_type == 'sticker':
        msg_type = 'sticker'
        content = msg.sticker.file_id
    elif msg.content_type == 'animation':
        msg_type = 'animation'
        content = msg.animation.file_id
    elif msg.content_type == 'audio':
        msg_type = 'audio'
        content = msg.audio.file_unique_id
    elif msg.content_type in ['photo', 'video', 'document'] and msg.caption:
        msg_type = 'text'
        content = msg.caption
    else:
        return True # Неизвестный тип для спам-фильтра
    rules = SPAM_RULES.get(msg_type)
    if not rules:
        return True
    now = datetime.now(UTC)
    violations = b_data['spam_violations'].setdefault(user_id, {'level': 0, 'last_reset': now})
    if (now - violations['last_reset']) > timedelta(hours=1):
        violations['level'] = 0
        violations['last_reset'] = now
    max_repeats = rules.get('max_repeats')
    if max_repeats and content:
        if msg_type == 'text':
            last_items_deque = b_data['last_texts'][user_id]
        elif msg_type == 'sticker':
            last_items_deque = b_data['last_stickers'][user_id]
        elif msg_type == 'animation':
            last_items_deque = b_data['last_animations'][user_id]
        elif msg_type == 'audio':
            last_items_deque = b_data['last_audios'][user_id]
        else:
            last_items_deque = None
        if last_items_deque is not None:
            last_items_deque.append(content)
            if len(last_items_deque) >= max_repeats:
                if len(set(last_items_deque)) == 1:
                    violations['level'] = min(violations['level'] + 1, len(rules['penalty']) - 1)
                    last_items_deque.clear() # Очищаем очередь после нарушения
                    return False
            if msg_type == 'text' and len(last_items_deque) == 4:
                if len(set(last_items_deque)) == 2:
                    contents = list(last_items_deque)
                    p1 = [contents[0], contents[1]] * 2
                    p2 = [contents[1], contents[0]] * 2
                    if contents == p1 or contents == p2:
                        violations['level'] = min(violations['level'] + 1, len(rules['penalty']) - 1)
                        last_items_deque.clear() # Очищаем очередь
                        return False
    window_start = now - timedelta(seconds=rules['window_sec'])
    now_ts = time.time()
    b_data['spam_tracker'][user_id] = [t for t in b_data['spam_tracker'][user_id] if t > (now_ts - rules['window_sec'])]
    b_data['spam_tracker'][user_id].append(now_ts)
    if len(b_data['spam_tracker'][user_id]) >= rules['max_per_window']:
        violations['level'] = min(violations['level'] + 1, len(rules['penalty']) - 1)
        b_data['spam_tracker'][user_id] = [] 
        return False
    return True
async def apply_penalty(bot_instance: Bot, user_id: int, msg_type: str, board_id: str, stream: str = 'ru'):

    async with user_spam_locks[user_id]:  # Блокировка для конкретного пользователя
        b_data = board_data[board_id]
        rules = SPAM_RULES.get(msg_type, {})
        if not rules:
            return
        violations_data = b_data['spam_violations'].get(user_id, {'level': 0, 'last_reset': datetime.now(UTC)})
        level = violations_data['level']
        current_mute = b_data['mutes'].get(user_id)
        if current_mute and current_mute > datetime.now(UTC):
            return  # Мут уже активен, пропускаем
        level = min(level, len(rules.get('penalty', [])) - 1)
        mute_seconds = rules['penalty'][level] if rules.get('penalty') else 30
        b_data['mutes'][user_id] = datetime.now(UTC) + timedelta(seconds=mute_seconds)
        violation_type = {'text': "текстовый спам", 'sticker': "спам стикерами", 'animation': "спам гифками", 'audio': "спам аудио"}.get(msg_type, "спам")
        mute_duration = f"{mute_seconds} сек" if mute_seconds < 60 else f"{mute_seconds//60} мин"
        print(f"🚫 [{board_id}] Мут за спам: user {user_id}, тип: {violation_type}, уровень: {level+1}, длительность: {mute_duration}")
        try:
            if mute_seconds < 60:
                time_str = f"{mute_seconds} sec" if stream == 'en' else (f"{mute_seconds}秒" if stream == 'jp' else f"{mute_seconds} сек")
            elif mute_seconds < 3600:
                time_str = f"{mute_seconds // 60} min" if stream == 'en' else (f"{mute_seconds // 60}分" if stream == 'jp' else f"{mute_seconds // 60} мин")
            else:
                time_str = f"{mute_seconds // 3600} h" if stream == 'en' else (f"{mute_seconds // 3600}時間" if stream == 'jp' else f"{mute_seconds // 3600} час")
            lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
            if lang == 'en':
                violation_type_en = {'text': "text spam", 'sticker': "sticker spam", 'animation': "gif spam", 'audio': "audio spam"}.get(msg_type, "spam")
                phrases = [
                    "🚫 Hey faggot, you are muted for {time} for {violation} on the {board} board.\nKeep spamming - get banned.",
                    "🔇 Too much spam, buddy. Take a break for {time} on {board}.",
                    "🚨 Spam detected! You've been silenced for {time} for {violation} on {board}. Don't do it again.",
                    "🛑 Stop right there, criminal scum! You're muted for {time} on {board} for spamming."
                ]
                notification_text = random.choice(phrases).format(time=time_str, violation=violation_type_en, board=BOARD_CONFIG[board_id]['name'])
            elif lang == 'jp':
                violation_type_jp = {'text': "テキスト連投", 'sticker': "スタンプ連打", 'animation': "GIF連打", 'audio': "音声連打"}.get(msg_type, "スパム")
                phrases = [
                    "🚫 おいホモ野郎、{board} 板での {violation} により {time} ミュートされたぞ。\nこれ以上やるとBANだ。",
                    "🔇 スパムしすぎだ。 {board} 板で {time} 頭を冷やせ。",
                    "🚨 スパム検知！ {board} で {violation} のため {time} 黙らせたぞ。二度とやるな。",
                    "🛑 止まれ犯罪者！スパム行為により {board} で {time} のミュートだ。"
                ]
                notification_text = random.choice(phrases).format(time=time_str, violation=violation_type_jp, board=BOARD_CONFIG[board_id]['name'])
            else:
                phrases = [
                    "🚫 Эй пидор, ты в муте на {time} за {violation} на доске {board}\nСпамишь дальше - получишь бан.",
                    "🔇 Ты заебал спамить. Отдохни {time} на доске {board}.",
                    "🚨 Обнаружен спам! Твоя пасть завалена на {time} за {violation} на доске {board}. Повторишь - получишь по жопе.",
                    "🛑 Стой, пидорас! Ты оштрафован на {time} молчания на доске {board} за свой высер."
                ]
                notification_text = random.choice(phrases).format(time=time_str, violation=violation_type, board=BOARD_CONFIG[board_id]['name'])
            await bot_instance.send_message(user_id, notification_text, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки уведомления о муте: {e}")
def _get_random_header_prefix(lang: str = 'ru') -> str:

    rand_prefix = random.random()
    if lang == 'en':
        if rand_prefix < 0.005: return "### ADMIN ### "
        if rand_prefix < 0.008: return "Me - "
        if rand_prefix < 0.01: return "Faggot - "
        if rand_prefix < 0.012: return "### DEGENERATE ### "
        if rand_prefix < 0.016: return "Biden - "
        if rand_prefix < 0.021: return "EMPEROR CONAN - "
        if rand_prefix < 0.023: return "### TRANNY ### "
        if rand_prefix < 0.05: return "Anon - " # Чаще для английского
        return ""
    if lang == 'jp':
        if rand_prefix < 0.005: return "### 管理人 ### " # Kanrinin (Admin)
        if rand_prefix < 0.008: return "俺 - " # Ore (Me)
        if rand_prefix < 0.01: return "ホモ - " # Homo (Faggot)
        if rand_prefix < 0.012: return "### 変質者 ### " # Henshitsu-sha (Degenerate)
        if rand_prefix < 0.016: return "岸田 - " # Kishida (PM context)
        if rand_prefix < 0.021: return "コナン皇帝 - " # Emperor Conan
        if rand_prefix < 0.023: return "### オカマ ### " # Okama (Tranny)
        if rand_prefix < 0.030: return "お前 - " # Omae (You)
        if rand_prefix < 0.040: return "暇人 - " # Himajin (Bitard/Neet)
        if rand_prefix < 0.08: return "名無し - " # Nanashi (Anon) - самый частый
        return ""
    if rand_prefix < 0.005: return "### АДМИН ### "
    if rand_prefix < 0.008: return "Абу - "
    if rand_prefix < 0.01: return "Пидор - "
    if rand_prefix < 0.012: return "### ДЖУЛУП ### "
    if rand_prefix < 0.014: return "### Хуесос ### "
    if rand_prefix < 0.016: return "Пыня - "
    if rand_prefix < 0.018: return "Нариман Намазов - "
    if rand_prefix < 0.021: return "ИМПЕРАТОР КОНАН - "
    if rand_prefix < 0.023: return "Антон Бабкин - "
    if rand_prefix < 0.025: return "НАРИМАН НАМАЗОВ - "
    if rand_prefix < 0.027: return "ПУТИН - "
    if rand_prefix < 0.028: return "Гей - "
    if rand_prefix < 0.030: return "Анархист - "
    if rand_prefix < 0.033: return "Имбецил - "
    if rand_prefix < 0.035: return "### ЧМО ### "
    if rand_prefix < 0.037: return "### ОНАНИСТ ### "
    if rand_prefix < 0.040: return "### ЧЕЧЕНЕЦ ### "
    if rand_prefix < 0.042: return "АААААААА - "
    if rand_prefix < 0.044: return "### Аниме девочка ### "
    if rand_prefix < 0.046: return "ChatGPT 5.4 - "
    if rand_prefix < 0.048: return "Безумец - "
    if rand_prefix < 0.050: return "Битард - "
    if rand_prefix < 0.052: return "Мегумин - "
    if rand_prefix < 0.054: return "Гопник - "
    if rand_prefix < 0.056: return "Шизик - "
    if rand_prefix < 0.058: return "Джефри Эпштейн - "
    if rand_prefix < 0.060: return "Максим Тесак - "
    if rand_prefix < 0.062: return "Навальный - "
    if rand_prefix < 0.064: return "Рамзанка дыров - "
    if rand_prefix < 0.066: return "СВОШНИК - "
    if rand_prefix < 0.068: return "Герой Украины - "
    if rand_prefix < 0.070: return "Claude Opus 4.6 - "
    if rand_prefix < 0.076: return "Администратор - "
    if rand_prefix < 0.08: return "Админ - "
    if rand_prefix < 0.085: return "Модератор - "
    if rand_prefix < 0.1: return "Анон - "
    if rand_prefix < 0.115: return "Анонимус - "
    if rand_prefix < 0.13: return "Анонимный пользователь - "
    return ""
async def format_thread_post_header(board_id: str, local_post_num: int, author_id: int, thread_info: dict, stream: str = 'ru') -> str:

    b_data = board_data[board_id]
    op_marker = " (OP)" if author_id != 0 and author_id == thread_info.get('op_id') else ""
    post_num_formatted = f"{local_post_num}/{MAX_POSTS_PER_THREAD}{op_marker}"
    msk_now = datetime.now(UTC) + timedelta(hours=3)
    hour = msk_now.hour
    is_night = hour >= 23 or hour < 6
    circle = ""
    rand = random.random()
    if is_night:
        if rand < 0.003: circle = "🌑 "
        elif rand < 0.006: circle = "🌒 "
        elif rand < 0.009: circle = "🌓 "
        elif rand < 0.012: circle = "🌔 "
        elif rand < 0.015: circle = "🌝 "
        elif rand < 0.018: circle = "🌌 "
    else:
        if rand < 0.003: circle = "🔴 "
        elif rand < 0.006: circle = "🟢 "
        elif rand < 0.009: circle = "☢️ "
        elif rand < 0.012: circle = "🟡 "
        elif rand < 0.015: circle = "🔵 "
        elif rand < 0.018: circle = "⭕ "
    if b_data['slavaukraine_mode']: return f"💙💛 Пiст №{post_num_formatted}"
    if b_data['zaputin_mode']: return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data['anime_mode']: return f"🌸 投稿 {post_num_formatted} 番"
    if b_data['suka_blyat_mode']: return f"💢 Пост №{post_num_formatted}"
    if b_data['polish_mode']: return f"🇵🇱 Post №{post_num_formatted}"
    if b_data.get('schizo_mode'): return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data['warhammer_mode']: return f"⚔️ Донесение №{post_num_formatted}"
    if b_data['imperial_mode']: return f"📜 Депеша №{post_num_formatted}"
    prefix = _get_random_header_prefix(lang=stream)
    if stream == 'en':
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    elif stream == 'jp':
        return f"{circle}{prefix}レス番 {post_num_formatted}"
    else:
        return f"{circle}{prefix}Пост №{post_num_formatted}"
async def format_header(board_id: str, post_num: int, author_id: int = 0, stream: str = 'ru') -> str:
    """
    Форматирование заголовка. 
    Исправлено: принимает author_id для совместимости, реализует смену День/Ночь.
    """
    board_data[board_id].setdefault('board_post_count', 0)
    board_data[board_id]['board_post_count'] += 1
    post_num_formatted = str(post_num)
    msk_now = datetime.now(UTC) + timedelta(hours=3)
    hour = msk_now.hour
    is_night = hour >= 23 or hour < 6
    circle = ""
    rand = random.random()
    if is_night:
        if rand < 0.003: circle = "🌑 "
        elif rand < 0.006: circle = "🌒 "
        elif rand < 0.009: circle = "🌓 "
        elif rand < 0.012: circle = "🌔 "
        elif rand < 0.015: circle = "🌝 "
        elif rand < 0.018: circle = "🌌 "
    else:
        if rand < 0.003: circle = "🔴 "
        elif rand < 0.006: circle = "🟢 "
        elif rand < 0.009: circle = "☢️ "
        elif rand < 0.012: circle = "🟡 "
        elif rand < 0.015: circle = "🔵 "
        elif rand < 0.018: circle = "⭕ "
    if board_id == 'int':
        prefix = _get_random_header_prefix(lang='en')
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    b_data = board_data[board_id]
    if b_data['slavaukraine_mode']:
        headers = [f"💙💛 Пiст №{post_num_formatted}", f"🇺🇦 Повiдомлення №{post_num_formatted}"]
        return random.choice(headers)
    if b_data['zaputin_mode']:
        return f"🇷🇺 Пост №{post_num_formatted}"
    if b_data['anime_mode']:
        return f"🌸 投稿 {post_num_formatted} 番"
    if b_data['suka_blyat_mode']:
        return f"💢 Пост №{post_num_formatted}"
    if b_data['gopnik_mode']:
        return f"🤙 Малява №{post_num_formatted}"
    if b_data.get('schizo_mode'):
        return f"++ СИГНАЛ #{post_num_formatted} ++"
    if b_data['polish_mode']:
        return f"🇵🇱 Post №{post_num_formatted}"
    if b_data['warhammer_mode']:
        return f"⚔️ Донесение №{post_num_formatted}"
    if b_data['imperial_mode']:
        return f"📜 Депеша №{post_num_formatted}"
        return f"🟩 Пакет №{post_num_formatted}"
        return f"🦅 Freedom Post №{post_num_formatted}"
        return f"🎄 Подарок №{post_num_formatted}"
        return f"🖥️ Сообщение #{post_num_formatted}"
        return f"📜 Казус №{post_num_formatted}"
    prefix_lang = 'en' if stream == 'en' else 'ru' 
    prefix = _get_random_header_prefix(lang=prefix_lang)
    if stream == 'en':
        return f"{circle}{prefix}Post No.{post_num_formatted}"
    elif stream == 'jp':
        return f"{circle}{prefix}レス番 {post_num_formatted}"
    else:
        return f"{circle}{prefix}Пост №{post_num_formatted}"
async def update_user_verification_stats(user_id: int, board_id: str, bot: Bot, stream: str):
    if user_id <= 0: return
    
    from common.db_pool import get_pool, db_lock
    db = await get_pool()
    
    async with db_lock:
        try:
            await db.execute("BEGIN IMMEDIATE")
            
            await db.execute(
                """
                INSERT INTO Users (user_id, board_id, posts_count) 
                VALUES (?, ?, 1) 
                ON CONFLICT(user_id, board_id) DO UPDATE SET 
                posts_count = Users.posts_count + 1
                """,
                (user_id, board_id)
            )
            
            cursor = await db.execute(
                """
                UPDATE Users 
                SET is_verified_b = 1 
                WHERE user_id = ? AND board_id = ? 
                AND posts_count >= 10 AND is_verified_b = 0
                """,
                (user_id, board_id)
            )
            
            should_notify = cursor.rowcount > 0
            
            await db.execute("COMMIT")
            
            if should_notify:
                lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                msg_text = VERIFICATION_SUCCESS_MESSAGES.get(lang, VERIFICATION_SUCCESS_MESSAGES['ru'])
                try:
                    await bot.send_message(user_id, msg_text, parse_mode="HTML")
                except:
                    pass
                    
        except Exception as e:
            try:
                await db.execute("ROLLBACK")
            except:
                pass
            print(f"⚠️ Ошибка верификации для {user_id}: {e}")
async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
    """
    Массовое удаление постов пользователя за период.
    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    """
    from common.db_pool import get_pool, db_lock  # Локальный импорт
    try:
        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()
        
        posts_to_delete_nums = []
        messages_to_delete_from_api = []
        channel_messages_to_delete = []

        # 1. Чтение данных и Удаление из БД в одной защищенной транзакции
        async with db_lock:
            for attempt in range(10):
                try:
                    db = await get_pool()
                    await db.execute("BEGIN IMMEDIATE")
                    
                    # Читаем посты для удаления
                    query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
                    async with db.execute(query_posts, (user_id, board_id, time_threshold_ts)) as cursor:
                        rows = await cursor.fetchall()
                    posts_to_delete_nums = [row[0] for row in rows]
                    
                    if not posts_to_delete_nums:
                        await db.execute("COMMIT")
                        return 0
                        
                    placeholders = ','.join('?' for _ in posts_to_delete_nums)
                    
                    # Читаем копии для API
                    query_copies = f"SELECT recipient_id, message_id FROM PostCopies WHERE post_num IN ({placeholders})"
                    async with db.execute(query_copies, posts_to_delete_nums) as cursor:
                        messages_to_delete_from_api = await cursor.fetchall()
                        
                    # Читаем копии каналов
                    query_channels = f"SELECT channel_id, message_id FROM ChannelCopies WHERE post_num IN ({placeholders})"
                    async with db.execute(query_channels, posts_to_delete_nums) as cursor:
                        channel_messages_to_delete = await cursor.fetchall()
                    
                    # Удаляем
                    query_delete = f"DELETE FROM Posts WHERE post_num IN ({placeholders})"
                    await db.execute(query_delete, posts_to_delete_nums)
                    
                    await db.execute("COMMIT")
                    break # Успех
                    
                except Exception as e:
                    try: await db.execute("ROLLBACK")
                    except: pass
                    
                    if "locked" in str(e).lower() or "busy" in str(e).lower():
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    print(f"⛔ DB Error in delete_user_posts: {e}")
                    return 0

        # 2. Чистка RAM (Messages Storage)
        async with storage_lock:
            for post_num in posts_to_delete_nums:
                post_data = messages_storage.pop(post_num, None)
                if post_data:
                    if board_id in THREAD_BOARDS:
                        thread_id = post_data.get('thread_id')
                        if thread_id:
                            b_data = board_data.get(board_id, {})
                            threads_data = b_data.get('threads_data', {})
                            if thread_id in threads_data and 'posts' in threads_data[thread_id]:
                                try:
                                    threads_data[thread_id]['posts'].remove(post_num)
                                except ValueError:
                                    pass
                message_copies_in_mem = post_to_messages.pop(post_num, {})
                for uid, mid_or_list in message_copies_in_mem.items():
                    if isinstance(mid_or_list, list):
                        for mid in mid_or_list:
                            message_to_post.pop((uid, mid), None)
                    else:
                        message_to_post.pop((uid, mid_or_list), None)

        # 3. Удаление из каналов
        if channel_messages_to_delete:
            archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
            deleter = archive_bot if archive_bot else bot_instance
            for chan_id, msg_id in channel_messages_to_delete:
                try:
                    await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
                except Exception: 
                    pass

        # 4. Удаление из ЛС пользователей (API)
        async def _delete_one_message(uid: int, mid: int) -> bool:
            max_attempts = 6
            delay = 1.5
            for attempt in range(max_attempts):
                try:
                    await bot_instance.delete_message(uid, mid)
                    return True
                except (TelegramBadRequest, TelegramForbiddenError):
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

        CHUNK_SIZE = 47
        DELAY_BETWEEN_CHUNKS = 0.11
        total_deleted_count = 0
        
        for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
            chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
            tasks = [_delete_one_message(uid, mid) for uid, mid in chunk]
            results = await asyncio.gather(*tasks)
            total_deleted_count += sum(1 for res in results if res is True)
            if i + CHUNK_SIZE < len(messages_to_delete_from_api):
                await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
                
        return total_deleted_count
    except Exception as e:
        import traceback
        print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
        return 0
async def delete_single_post(post_num: int, bot_instance: Bot) -> int:
    """
    Удаляет один конкретный пост отовсюду: из БД, RAM, ЛС пользователей и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
    """
    channel_copies = await get_all_channel_copies(post_num)
    messages_to_delete_info = await get_post_copies(post_num)
    deleted_from_db = await delete_post_by_num(post_num)
    if not deleted_from_db and not messages_to_delete_info and not channel_copies:
        return 0
    async with storage_lock:
        post_data = messages_storage.pop(post_num, None)
        if post_data:
            board_id = post_data.get('board_id')
            if board_id and board_id in THREAD_BOARDS:
                thread_id = post_data.get('thread_id')
                if thread_id:
                    b_data = board_data.get(board_id, {})
                    threads_data = b_data.get('threads_data', {})
                    if thread_id in threads_data:
                        try:
                            if 'posts' in threads_data[thread_id]:
                                threads_data[thread_id]['posts'].remove(post_num)
                        except (ValueError, KeyError):
                            pass
        message_copies_in_mem = post_to_messages.pop(post_num, {})
        for uid, mid_or_list in message_copies_in_mem.items():
            if isinstance(mid_or_list, list):
                for mid in mid_or_list:
                    message_to_post.pop((uid, mid), None)
            else:
                message_to_post.pop((uid, mid_or_list), None)
    if channel_copies:
        archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
        deleter = archive_bot if archive_bot else bot_instance
        for chan_id, msg_id in channel_copies:
            try:
                await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
            except Exception:
                pass
    if not messages_to_delete_info:
        return 0 if deleted_from_db else 0
    async def _delete_one_message(uid: int, mid: int) -> bool:

        max_attempts = 6
        delay = 1.5
        for attempt in range(max_attempts):
            try:
                await bot_instance.delete_message(uid, mid)
                return True # Успех
            except (TelegramBadRequest, TelegramForbiddenError):
                return False
            except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError):
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
                else:
                    return False
            except Exception:
                return False
        return False
    tasks = [_delete_one_message(uid, mid) for uid, mid in messages_to_delete_info]
    results = await asyncio.gather(*tasks)
    deleted_count = sum(1 for res in results if res is True)
    return deleted_count
async def send_moderation_notice(user_id: int, action: str, board_id: str, duration: str = None, deleted_posts: int = 0, stream: str = 'ru'):

    b_data = board_data[board_id]
    if not b_data['users']['active']:
        return
    lang = 'en' if board_id == 'int' else 'ru'
    text = ""
    if action == "ban":
        if lang == 'en':
            ban_phrases = [
                f"🚨 A faggot has been banned for spam. RIP.",
                f"☠️ Another spammer bites the dust. Good riddance.",
                f"🔨 The ban hammer has spoken. A degenerate was removed.",
                f"✈️ Sent a spammer on a one-way trip to hell."
            ]
        elif lang == 'jp':
            ban_phrases = [
                f"🚨 ホモ野郎がスパムでBANされたぞ。ナムアミダブツ。",
                f"☠️ またスパム野郎が塵になった。せいせいするぜ。",
                f"🔨 BANハンマーが下された。変質者が一人消えたな。",
                f"✈️ スパム野郎を地獄への片道旅行に送り出したぞ。"
            ]
        else:
            ban_phrases = [
                f"🚨 Хуесос был забанен за спам. Помянем.",
                f"☠️ Мир стал чище, еще один спамер отлетел в бан.",
                f"🔨 Банхаммер опустился на голову очередного дегенерата.",
                f"✈️ Отправили спамера в увлекательное путешествие нахуй!",
            ]
        text = random.choice(ban_phrases)
        asyncio.create_task(log_global_event('bot', f"🔨 {board_id.upper()}: {text} (User: {user_id})"))
    elif action == "mute":
        if lang == 'en':
            mute_phrases = [
                f"🔇 A loudmouth has been muted for a while.",
                f"🤫 Someone's got a timeout. Let's enjoy the silence.",
                f"🤐 Put a sock in it! A user has been temporarily silenced.",
                f"⌛️ A faggot is in the penalty box for a bit."
            ]
        elif lang == 'jp':
            mute_phrases = [
                f"🔇 クソうるさい奴をしばらく黙らせたぞ。",
                f"🤫 タイムアウトだ。静寂を楽しもうぜ。",
                f"🤐 靴下でも詰めとけ！ユーザーが一時的にミュートされた。",
                f"⌛️ ホモ野郎はお仕置き部屋行きだ。"
            ]
        else:
            mute_phrases = [
                f"🔇 Пидораса замутили ненадолго.",
                f"🤫 Наслаждаемся тишиной, хуеглот временно не может писать.",
                f"Молчание - золото. Пидор будет тихим.",
                f"🤐 Анон отправлен в угол подумать о своем поведении.",
                f"⌛️ Пидору выписали временный запрет на открытие рта.",
                f"🕒 Пидор будет молчать до лучших времен.",
                f"На время он будет тихим, как мышь. Ожидаем его возвращения."
            ]
        text = random.choice(mute_phrases)
    else:
        return
    now_dt = datetime.now(UTC)
    content = {
        'type': 'text',
        'text': text,
        'is_system_message': True
    }
    post_num = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not post_num:
        print(f"⛔ [{board_id}] Не удалось создать пост в БД для send_moderation_notice.")
        return
    header = await format_header(board_id, post_num)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(post_num, content)
    async with storage_lock:
        messages_storage[post_num] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data["users"]["active"],
        "content": content,
        "post_num": post_num,
        "board_id": board_id
    })
async def _rollback_post_creation(post_num_to_delete: int):
    """
    (БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ В process_new_post)
    Откатывает создание поста. Вызывается только в крайнем случае, если не удалось даже создать пост в БД.
    """
    deleted_from_db = await delete_post_by_num(post_num_to_delete)
    async with storage_lock:
        messages_storage.pop(post_num_to_delete, None)
        post_to_messages.pop(post_num_to_delete, None)
        keys_to_del = [k for k, v in message_to_post.items() if v == post_num_to_delete]
        for k in keys_to_del:
            message_to_post.pop(k, None)
    if deleted_from_db:
        print(f"Rollback: Пост #{post_num_to_delete} успешно удален из БД и памяти.")
async def process_shadow_reject(bot: Bot, board_id: str, user_id: int, content: dict, reply_to_post: int | None, stream: str = 'ru'):
    """
    Эмулирует успешную публикацию поста, но отправляет его ТОЛЬКО автору.
    Не пишет в БД, не увеличивает счетчики.
    """
    shadow_key = (board_id, user_id)
    current_floor = state['post_counter'] + random.randint(1, 3)
    last_fake_post_num = shadow_fake_post_counters.get(shadow_key, 0)
    fake_post_num = max(current_floor, last_fake_post_num + random.randint(1, 3))
    shadow_fake_post_counters[shadow_key] = fake_post_num
    header_text = await format_header(board_id, fake_post_num, user_id, stream=stream)
    user_content = content.copy()
    user_content['header'] = header_text
    user_content['post_num'] = fake_post_num
    user_content['is_shadow_reject'] = True
    user_content['reply_to_post'] = reply_to_post
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await send_message_to_users(
        bot_instance=bot,
        board_id=board_id,
        recipients={user_id}, # Только автор!
        content=user_content,
        reply_info=None
    )
    print(f"👻 [SHADOW] Теневой отброс медиа от {user_id} на доске {board_id}")
async def process_new_post(
    bot_instance: Bot,
    board_id: str,
    user_id: int,
    content: dict,
    reply_to_post: int | None,
    is_shadow_muted: bool,
    stream: str = 'ru'
) -> int | None:
    """
    Унифицированная функция для обработки, сохранения и постановки в очередь нового поста.
    Версия 8.0: Гарантирует регистрацию поста в памяти даже при сбое отправки. НИКАКИХ УДАЛЕНИЙ.
    """
    b_data = board_data[board_id]
    current_post_num = None
    thread_id = None
    try:
        fallback_fetchers = content.pop('__fallback_fetcher_tasks', [])
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
        recipients = set()
        reply_info_for_author = {}
        if board_id in THREAD_BOARDS and user_location != 'main':
            thread_id = user_location
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info or thread_info.get('is_archived'):
                b_data['user_state'].setdefault(user_id, {})['location'] = 'main'
                lang = 'en' if board_id == 'int' else 'ru'
                await bot_instance.send_message(user_id, random.choice(thread_messages[lang]['thread_not_found']))
                return None
            if user_id in thread_info.get('local_mutes', {}) and time.time() < thread_info['local_mutes'][user_id]: 
                return None
            if user_id in thread_info.get('local_shadow_mutes', {}) and time.time() < thread_info['local_shadow_mutes'][user_id]: 
                is_shadow_muted = True
            recipients = thread_info.get('subscribers', set()) - {user_id}
        else:
            if board_id == 'int' or not ENABLE_MULTILANG:
                recipients = b_data['users']['active'] - {user_id}
            else:
                stream_users = await get_stream_active_users(board_id, stream)
                active_stream_users = stream_users.intersection(b_data['users']['active'])
                recipients = active_stream_users - {user_id}
        now_dt = datetime.now(UTC)
        final_content = await _apply_mode_transformations(content, board_id)
        final_content['reply_to_post'] = reply_to_post
        image_bytes_to_send = final_content.pop('image_bytes', None)
        current_post_num = await create_post(
            board_id=board_id,
            author_id=user_id,
            content=final_content,
            timestamp=now_dt.timestamp(),
            reply_to=reply_to_post,
            is_shadow_muted=is_shadow_muted,
            is_from_site=False,
            thread_id_from_bot=thread_id,
            stream=stream
        )
        
        # --- НАЧАЛО ИЗМЕНЕНИЙ (Запуск системы верификации) ---
        if current_post_num is not None and user_id > 0:
            # Запускаем обновление статистики в фоне
            asyncio.create_task(update_user_verification_stats(user_id, board_id, bot_instance, stream))
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        if current_post_num is None:
            if reply_to_post:
                try:
                    lang = 'en' if board_id == 'int' else 'ru'
                    error_text = "Error: The post you are replying to has been deleted." if lang == 'en' else "Ошибка: пост, на который вы отвечаете, был удален."
                    await bot_instance.send_message(user_id, error_text)
                except (TelegramForbiddenError, TelegramBadRequest):
                    pass
            return None
        if not is_shadow_muted:
            mark_weekly_active_delivery_user(board_id, user_id)
        locally_created_posts.append(current_post_num)
        final_content['post_num'] = current_post_num
        if thread_id:
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            local_post_num = len(thread_info.get('posts', [])) + 1
            header_text = await format_thread_post_header(board_id, local_post_num, user_id, thread_info, stream=stream)
        else:
            header_text = await format_header(board_id, current_post_num, stream=stream)
        final_content['header'] = header_text
        await update_post_content(current_post_num, final_content)
        if image_bytes_to_send:
            final_content['image_bytes'] = image_bytes_to_send
        author_results = None
        try:
            author_results = await send_message_to_users(
                bot_instance=bot_instance,
                board_id=board_id,
                recipients={user_id},
                content=final_content,
                reply_info=reply_info_for_author,
                verbose=False
            )
        except TelegramBadRequest as e:
            if 'image_url' in final_content:
                print(f"ℹ️ Ошибка отправки поста #{current_post_num} по URL. Запускаю 'Спасательный Цикл'...")
                loop = asyncio.get_running_loop()
                fallback_succeeded = False
                initial_url = final_content.get('image_url')
                async def initial_fetcher(): return initial_url
                all_fetchers = [initial_fetcher] + fallback_fetchers
                random.shuffle(all_fetchers)
                for i, fetcher in enumerate(all_fetchers):
                    print(f"  -> Попытка спасения #{i + 1}/{len(all_fetchers)}...")
                    try:
                        url_to_try = await fetcher()
                        if not url_to_try:
                            print("    -> Получен пустой URL, пропускаю.")
                            continue
                        download_result = await _download_image_with_proxy(url_to_try)
                        if not download_result:
                            print("    -> Скачивание не удалось.")
                            continue
                        processed_bytes = await loop.run_in_executor(None, _resize_image_if_needed, download_result[0])
                        fallback_content = final_content.copy()
                        fallback_content.pop('image_url', None)
                        fallback_content['image_bytes'] = processed_bytes
                        author_results = await send_message_to_users(
                            bot_instance=bot_instance, board_id=board_id, recipients={user_id},
                            content=fallback_content, reply_info=reply_info_for_author
                        )
                        if author_results:
                            final_content = fallback_content
                            fallback_succeeded = True
                            print(f"✅ 'Спасательный Цикл' для поста #{current_post_num} успешен.")
                            break
                        else:
                            print("    -> Отправка байтов также не удалась. Пробую следующий источник.")
                    except Exception as ex:
                        print(f"    -> Ошибка в цикле спасения: {type(ex).__name__}: {ex}")
                        continue
                if not fallback_succeeded:
                    print(f"⚠️ 'Спасательный цикл' не помог для поста #{current_post_num}. Ошибка: {e}. Пост будет обработан без message_id автора.")
            else:
                print(f"⚠️ Не удалось отправить текстовый пост #{current_post_num} автору из-за ошибки: {e}. Пост будет обработан без message_id автора.")
        except Exception as e:
            print(f"⚠️ Не удалось отправить пост #{current_post_num} автору из-за сетевой/другой ошибки: {e}. Пост будет обработан без message_id автора.")
        async with storage_lock:
            state['post_counter'] = max(state.get('post_counter', 0), current_post_num)
            if thread_id:
                thread_info_safe = b_data.get('threads_data', {}).get(thread_id)
                if thread_info_safe:
                    thread_info_safe['posts'].append(current_post_num)
                    thread_info_safe['last_activity_at'] = time.time()
            content_for_ram = final_content.copy()
            content_for_ram.pop('image_bytes', None)
            messages_storage[current_post_num] = {
                'author_id': user_id, 'timestamp': now_dt, 
                'content': content_for_ram,
                'author_message_id': None, 'board_id': board_id, 'thread_id': thread_id
            }
            if author_results and author_results[0] and author_results[0][1]:
                sent_messages = author_results[0][1]
                messages_to_process = sent_messages if isinstance(sent_messages, list) else [sent_messages]
                if final_content.get('type') == 'media_group' and messages_to_process:
                    new_media_items = []
                    for msg in messages_to_process:
                        item = {}
                        if msg.photo: item = {'type': 'photo', 'file_id': msg.photo[-1].file_id}
                        elif msg.video: item = {'type': 'video', 'file_id': msg.video.file_id}
                        elif msg.document: item = {'type': 'document', 'file_id': msg.document.file_id}
                        elif msg.audio: item = {'type': 'audio', 'file_id': msg.audio.file_id}
                        if item: new_media_items.append(item)
                    if new_media_items: 
                        final_content['media'] = new_media_items 
                        final_content.pop('image_url', None)
                        final_content.pop('image_bytes', None) 
                elif messages_to_process:
                    msg = messages_to_process[0]
                    file_id_to_persist = None
                    if msg.photo: file_id_to_persist = msg.photo[-1].file_id
                    elif msg.video: file_id_to_persist = msg.video.file_id
                    elif msg.animation: file_id_to_persist = msg.animation.file_id
                    if file_id_to_persist:
                        final_content['file_id'] = file_id_to_persist
                        final_content.pop('image_url', None)
                        final_content.pop('image_bytes', None)
                await update_post_content(current_post_num, final_content)
                author_message_ids_to_archive = [m.message_id for m in (sent_messages if isinstance(sent_messages, list) else [sent_messages])]
                messages_to_save = sent_messages if isinstance(sent_messages, list) else [sent_messages]
                messages_storage[current_post_num]['author_message_id'] = author_message_ids_to_archive
                messages_storage[current_post_num]['content'] = final_content
                post_to_messages.setdefault(current_post_num, {})[user_id] = (
                    author_message_ids_to_archive[0] if len(author_message_ids_to_archive) == 1 else author_message_ids_to_archive
                )
                for m in messages_to_save:
                    message_to_post[(user_id, m.message_id)] = current_post_num
        if not is_shadow_muted and recipients:
            await enqueue_board_message(board_id, {
                'recipients': recipients, 'content': final_content, 'post_num': current_post_num,
                'board_id': board_id, 'thread_id': thread_id
            })
        if not final_content.get('is_system_message'):
            asyncio.create_task(_forward_post_to_realtime_archive(
                bot_instance=bot_instance, board_id=board_id, post_num=current_post_num, content=final_content, is_shadow_muted=is_shadow_muted
            ))
        numeral_level = check_post_numerals(current_post_num)
        if numeral_level:
            asyncio.create_task(post_special_num_to_channel(
                bots=GLOBAL_BOTS, board_id=board_id, post_num=current_post_num,
                level=numeral_level, content=final_content, author_id=user_id
            ))
        if thread_id:
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if thread_info:
                posts_count = len(thread_info.get('posts', []))
                milestones = [50, 150, 220]
                if posts_count in milestones and posts_count not in thread_info.get('announced_milestones', []):
                    thread_info.setdefault('announced_milestones', []).append(posts_count)
                    asyncio.create_task(post_thread_notification_to_channel(
                        bots=GLOBAL_BOTS, board_id=board_id, thread_id=thread_id,
                        thread_info=thread_info, event_type='milestone',
                        details={'posts': posts_count}
                    ))
        return current_post_num
    except Exception as e:
        import traceback
        print(f"🔥🔥🔥 ФАТАЛЬНАЯ ОШИБКА в process_new_post для user {user_id}: {e}\n{traceback.format_exc()}")
        return None
async def _forward_post_to_realtime_archive(bot_instance: Bot, board_id: str, post_num: int, content: dict, is_shadow_muted: bool, stream: str = 'ru'):
    if is_shadow_muted:
        return
    from common.database import get_post_by_num, register_file_owner, update_post_content, add_file_mirror
    check_post = await get_post_by_num(post_num)
    if not check_post:
        return
    archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
    sender_bot = bot_instance if board_id in AUTHORIZED_ARCHIVE_BOTS else archive_bot
    if not sender_bot:
        return
    sender_bot_id = getattr(sender_bot, 'id', 0)
    lang = 'en' if board_id == 'int' else 'ru'
    
    # --- НАЧАЛО ИЗМЕНЕНИЙ (Умный парсинг заголовка для Архивача) ---
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
    raw_header = content.get('header', f"Пост №{post_num}")
    
    header_text = ""
    # Пытаемся отделить эмодзи/роль от самого номера поста
    match = re.search(r'(.*?)(Пост №\d+.*|Post No\.\d+.*|レス番 \d+.*)', raw_header, re.DOTALL | re.IGNORECASE)
    
    if match:
        prefix = match.group(1).strip()
        post_part = match.group(2).strip()
        
        has_letters = bool(re.search(r'[a-zA-Zа-яА-ЯёЁ]', prefix))
        reply_to_num = content.get('reply_to_post')
        reply_suffix = ""
        if reply_to_num:
            reply_suffix = f" (reply to №{reply_to_num})" if lang == 'en' else f" (ответ на №{reply_to_num})"
            
        if prefix and has_letters:
            # Если есть текст (например "Абу -"), делаем красивый абзац
            if prefix.endswith('-'):
                prefix = prefix[:-1].strip()
            header_text = f"<b>/{board_id}/</b> | {post_part}{reply_suffix}\n\n<b>{prefix} :</b>"
        else:
            # Если это просто эмодзи (например 🌑), ставим его в начало
            prefix_with_space = f"{prefix} " if prefix else ""
            header_text = f"{prefix_with_space}<b>/{board_id}/</b> | {post_part}{reply_suffix}"
    else:
        # Фолбэк, если регулярка не сработала
        reply_to_num = content.get('reply_to_post')
        reply_suffix = ""
        if reply_to_num:
            reply_suffix = f" (reply to №{reply_to_num})" if lang == 'en' else f" (ответ на №{reply_to_num})"
        header_text = f"<b>/{board_id}/</b> | {raw_header}{reply_suffix}"
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
    
    content_type = content.get("type", "text")
    text_to_send = None
    if content_type == 'text':
        text_content = convert_site_tags_to_telegram(content.get('text', ''))
        if 'poll_data' in content:
            poll_text = generate_poll_text_display(content['poll_data'])
            text_content = f"{text_content}\n\n{poll_text}".strip()
        final_text = f"{header_text}\n\n{text_content}"
        if len(final_text) > 4096: 
            final_text = final_text[:4093] + "..."
        text_to_send = final_text
    
    db_updated = False
    for channel_id in MIRROR_CHANNELS:
        if not channel_id or channel_id == 0:
            continue
        for attempt in range(3):
            try:
                sent_message = None
                new_files_data =[]
                if text_to_send:
                    sent_message = await sender_bot.send_message(
                        chat_id=channel_id, 
                        text=text_to_send, 
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                elif content_type == 'media_group':
                    builder = MediaGroupBuilder()
                    raw_cap = content.get('caption', '')
                    converted_cap = convert_site_tags_to_telegram(raw_cap)
                    full_caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
                    if len(full_caption) > 1024: full_caption = full_caption[:1021] + "..."
                    media_list = content.get('media',[])
                    if not media_list: break
                    for i, media_item in enumerate(media_list):
                        file_id = media_item.get('file_id') or media_item.get('media')
                        m_type = media_item['type']
                        caption = full_caption if i == 0 else None
                        if m_type == 'photo': builder.add_photo(media=file_id, caption=caption, parse_mode="HTML")
                        elif m_type == 'video': builder.add_video(media=file_id, caption=caption, parse_mode="HTML")
                        elif m_type == 'document': builder.add_document(media=file_id, caption=caption, parse_mode="HTML")
                        elif m_type == 'audio': builder.add_audio(media=file_id, caption=caption, parse_mode="HTML")
                    sent_msgs = await sender_bot.send_media_group(channel_id, media=builder.build())
                    if sent_msgs:
                        sent_message = sent_msgs[0]
                        for idx, sm in enumerate(sent_msgs):
                            fid = None
                            if sm.photo: fid = sm.photo[-1].file_id
                            elif sm.video: fid = sm.video.file_id
                            elif sm.document: fid = sm.document.file_id
                            elif sm.audio: fid = sm.audio.file_id
                            if fid:
                                new_files_data.append({'type': sm.content_type, 'file_id': fid})
                                orig_fid = media_list[idx].get('file_id') or media_list[idx].get('media')
                                if orig_fid: await add_file_mirror(orig_fid, 'tg_shadow', fid)
                else:
                    orig_fid = content.get('file_id')
                    if orig_fid:
                        raw_cap = content.get('caption', '')
                        converted_cap = convert_site_tags_to_telegram(raw_cap)
                        caption = f"{header_text}\n\n{sanitize_html(converted_cap)}".strip()
                        if len(caption) > 1024: caption = caption[:1021] + "..."
                        ct_str = str(content_type).split('.')[-1].lower()
                        common_args = {"chat_id": channel_id, "caption": caption, "parse_mode": "HTML"}
                        if ct_str == 'photo': sent_message = await sender_bot.send_photo(photo=orig_fid, **common_args)
                        elif ct_str == 'video': sent_message = await sender_bot.send_video(video=orig_fid, **common_args)
                        elif ct_str == 'animation': sent_message = await sender_bot.send_animation(animation=orig_fid, **common_args)
                        elif ct_str == 'document': sent_message = await sender_bot.send_document(document=orig_fid, **common_args)
                        elif ct_str == 'audio': sent_message = await sender_bot.send_audio(audio=orig_fid, **common_args)
                        elif ct_str == 'voice': sent_message = await sender_bot.send_voice(voice=orig_fid, **common_args)
                        elif ct_str == 'sticker':
                            await sender_bot.send_sticker(channel_id, sticker=orig_fid)
                            sent_message = await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
                        elif ct_str == 'video_note':
                            await sender_bot.send_video_note(channel_id, video_note=orig_fid)
                            sent_message = await sender_bot.send_message(channel_id, header_text, parse_mode="HTML")
                        if sent_message:
                            fid = None
                            if sent_message.photo: fid = sent_message.photo[-1].file_id
                            elif sent_message.video: fid = sent_message.video.file_id
                            elif sent_message.animation: fid = sent_message.animation.file_id
                            elif sent_message.document: fid = sent_message.document.file_id
                            elif sent_message.audio: fid = sent_message.audio.file_id
                            elif sent_message.voice: fid = sent_message.voice.file_id
                            if fid: 
                                new_files_data.append(fid)
                                await add_file_mirror(orig_fid, 'tg_shadow', fid)

                if sent_message:
                    await add_channel_copy(post_num, channel_id, sent_message.message_id)
                    if not db_updated and new_files_data:
                        new_content = content.copy()
                        if content_type == 'media_group':
                            new_content['media'] = new_files_data
                            for f_info in new_files_data:
                                await register_file_owner(f_info['file_id'], sender_bot_id)
                        else:
                            new_content['file_id'] = new_files_data[0]
                            await register_file_owner(new_files_data[0], sender_bot_id)
                        await update_post_content(post_num, new_content)
                        db_updated = True
                break
            except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError):
                if attempt < 2: await asyncio.sleep(2)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                break
async def _apply_mode_transformations(content: dict, board_id: str) -> dict:
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ 5.0)
    Унифицированный диспетчер трансформаций. 
    Гарантирует Enterprise-логику: визуальные шаблоны только для текстовых постов.
    """
    b_data = board_data[board_id]
    modified_content = content.copy()
    
    # 1. Проверка активности любого из режимов трансформации
    is_transform_mode_active = (
        b_data['anime_mode'] or b_data['slavaukraine_mode'] or
        b_data['zaputin_mode'] or b_data['suka_blyat_mode'] or
        b_data['polish_mode'] or b_data['warhammer_mode'] or b_data['imperial_mode'] or
        b_data['gopnik_mode'] or b_data.get('schizo_mode')
    )
    if not is_transform_mode_active:
        return modified_content
    active_mode_key = next((mode for mode in MODE_FLAGS if b_data.get(mode)), None)

    # 2. Определяем ключ текста (text для постов, caption для медиа)
    text_key = 'text' if 'text' in modified_content and modified_content['text'] else \
               'caption' if 'caption' in modified_content and modified_content['caption'] else None
    
    if not text_key:
        return modified_content

    plain_text = clean_html_tags(modified_content.get(text_key, ''))
    header = modified_content.get('header')
    
    # 3. Флаг: разрешена ли генерация картинки-шаблона?
    # Enterprise-правило: только если исходный пост — ТЕКСТ и он не слишком длинный.
    allow_visual = (modified_content.get('type') == 'text') and (len(plain_text) < 180)
    
    transform_result = None
    loop = asyncio.get_running_loop()

    # 4. Выбор и запуск функции трансформации
    if b_data.get('schizo_mode'):
        transform_result = await loop.run_in_executor(None, shizo_transform, plain_text, header)
    #     transform_result = await loop.run_in_executor(None, matrix_transform, plain_text, header)
    #     transform_result = await loop.run_in_executor(None, america_transform, plain_text, header)
    #     transform_result = await loop.run_in_executor(None, holiday_transform, plain_text, header)
    #     transform_result = await loop.run_in_executor(None, oldweb_transform, plain_text, header)
    #     transform_result = await loop.run_in_executor(None, jewish_transform, plain_text, header)
    elif b_data['gopnik_mode']:
        transform_result = await loop.run_in_executor(None, gopnik_transform, plain_text)
    elif b_data['imperial_mode']:
        transform_result = await loop.run_in_executor(None, imperial_transform, plain_text, header)
    elif b_data['warhammer_mode']:
        transform_result = await loop.run_in_executor(None, warhammer_transform, plain_text, header)
    elif b_data['polish_mode']:
        transform_result = await loop.run_in_executor(None, polish_transform, plain_text, header)
    elif b_data['slavaukraine_mode']:
        transform_result = await loop.run_in_executor(None, ukrainian_transform, plain_text, header)
    
    # 5. Обработка результата (кортеж или текст)
    if transform_result and isinstance(transform_result, tuple):
        res_type, res_data = transform_result
        
        # Если пришла картинка И нам разрешено её использовать
        if res_type == 'image' and allow_visual:
            modified_content['type'] = 'photo'
            modified_content['image_bytes'] = res_data
            if 'text' in modified_content: modified_content['text'] = ''
            if 'caption' in modified_content: modified_content['caption'] = ''
            return modified_content
        
        # Если пришел текст (или картинка запрещена — берем текст из кортежа)
        elif res_type == 'text' or (res_type == 'image' and not allow_visual):
            # В случае 'image', если visual запрещен, некоторые функции могут не вернуть текст. 
            # Но наши новые функции (shizo, polish, ukr) всегда возвращают текст вторым элементом при неудаче.
            transformed_text = res_data if isinstance(res_data, str) else plain_text
            modified_content[text_key] = transformed_text
            plain_text = transformed_text

    # 6. Остаточные трансформации для режимов без визуального движка (Zaputin, Suka_Blyat)
    if not transform_result:
        transformed_text = plain_text
        if b_data['zaputin_mode']:
            transformed_text = await loop.run_in_executor(None, zaputin_transform, transformed_text)
        elif b_data['suka_blyat_mode']:
            words = transformed_text.split()
            for i in range(len(words)):
                if random.random() < 0.3: words[i] = random.choice(MAT_WORDS)
            transformed_text = ' '.join(words)
        
        modified_content[text_key] = transformed_text
        plain_text = transformed_text

    # 7. Специфическая логика для Аниме (остается без изменений, так как аниме-режим не трогали)
    if b_data['anime_mode']:
        current_text = modified_content.get(text_key, '')
        transformed_plain_text = await loop.run_in_executor(None, anime_transform, current_text)
        transformed_plain_text = await _maybe_punch_up_text(transformed_plain_text, 'anime_mode', board_id)
        modified_content[text_key] = escape_html(transformed_plain_text)
        
        if modified_content.get('type') == 'text' and random.random() < 0.33:
            from japanese_translator import get_random_anime_image, get_monogatari_image
            image_fetcher = get_monogatari_image if random.random() < 0.33 else get_random_anime_image
            try:
                anime_img_url = await asyncio.wait_for(image_fetcher(), timeout=ANIME_URL_FETCH_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                runtime_logger.warning(
                    "anime_mode_image_timeout %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "timeout_sec": ANIME_URL_FETCH_TIMEOUT_SEC,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                anime_img_url = None
            if anime_img_url:
                text_content = modified_content.pop('text', '')
                modified_content.update({'type': 'photo', 'caption': text_content, 'image_url': anime_img_url})

    elif active_mode_key:
        current_text = modified_content.get(text_key, '')
        if current_text:
            modified_content[text_key] = await _maybe_punch_up_text(current_text, active_mode_key, board_id)

    return modified_content
async def _download_image_with_proxy(url: str, timeout: int = 90, depth: int = 0) -> tuple[bytes, int] | None:
    if depth > 3: return None
    import socket
    import ssl
    import aiohttp
    import asyncio
    import hashlib
    from urllib.parse import urlparse

    current_proxy = get_dynamic_proxy_url()
    
    # Настраиваем таймауты
    timeout_config = aiohttp.ClientTimeout(total=timeout, connect=30, sock_connect=30, sock_read=timeout)
    
    # Парсим домен для Referer
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    scheme = parsed_url.scheme
    _, url_ext = os.path.splitext(parsed_url.path)
    url_log = (
        f"host={domain or 'unknown'} "
        f"ext={(url_ext.lower()[:12] or 'none')} "
        f"sha12={hashlib.sha256(url.encode('utf-8', 'ignore')).hexdigest()[:12]}"
    )

    # Базовые заголовки, маскируемся под Chrome
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }

    # ДОБАВЛЯЕМ REFERER (ГЛАВНОЕ ИСПРАВЛЕНИЕ)
    # Имиджборды требуют, чтобы реферер совпадал с их сайтом
    if "gelbooru" in domain:
        headers["Referer"] = "https://gelbooru.com/"
    elif "konachan" in domain:
        headers["Referer"] = "https://konachan.com/"
    elif "yande.re" in domain:
        headers["Referer"] = "https://yande.re/"
    elif "danbooru" in domain:
        headers["Referer"] = "https://danbooru.donmai.us/"
    elif "aibooru" in domain:
        headers["Referer"] = "https://aibooru.online/"
    else:
        # Универсальный фоллбек
        headers["Referer"] = f"{scheme}://{domain}/"

    for attempt in range(2):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            ssl=ssl_context,
            force_close=True,
            enable_cleanup_closed=True,
        )
        try:
            async with aiohttp.ClientSession(
                timeout=timeout_config, 
                headers=headers, 
                connector=connector,
                trust_env=False 
            ) as session:
                try:
                    async with session.get(url, allow_redirects=True, proxy=current_proxy) as response:
                        if response.status == 200:
                            content_type = response.headers.get('Content-Type', '').lower()
                            
                            # Читаем данные
                            data = await response.read()

                            # Проверка на HTML-заглушку (Cloudflare или 403)
                            # Некоторые сайты отдают 200 OK, но внутри HTML с капчей
                            if 'text/html' in content_type or (len(data) > 0 and data.strip().startswith(b'<') and b'<html' in data[:500].lower()):
                                try:
                                    # Пытаемся прочитать текст ошибки для диагностики
                                    error_text = data[:300].decode('utf-8', errors='ignore').replace('\n', ' ')
                                except:
                                    error_text = "Binary/Unknown"
                                    
                                print(f"⚠️ [DEBUG_DL] Ссылка вернула HTML заглушку. Содержимое: {error_text}")
                                return None

                            if len(data) > 49.5 * 1024 * 1024:
                                print(f"⚠️ [DEBUG_DL] Файл слишком велик ({len(data)} байт). Пропуск.")
                                return None
                                
                            if len(data) > 0:
                                print(f"✅ [DEBUG_DL] Скачано {len(data)} байт.")
                                return data, len(data)
                        else:
                            print(f"⚠️ [DEBUG_DL] Статус ответа: {response.status} для {url_log}")

                except (aiohttp.ClientConnectorError, asyncio.TimeoutError, OSError) as e:
                    if current_proxy:
                        print(f"⚠️ [DEBUG_DL] Сбой прокси ({e}). Пробую DIRECT...")
                        # Попытка без прокси
                        async with session.get(url, allow_redirects=True, proxy=None) as response:
                            if response.status == 200:
                                data = await response.read()
                                if len(data) > 0 and not (data.strip().startswith(b'<') and b'<html' in data[:200].lower()):
                                    print(f"✅ [DEBUG_DL] Успех через DIRECT.")
                                    return data, len(data)
                    raise e
        except asyncio.TimeoutError:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
            else:
                print(f"⛔ [DEBUG_DL] Таймаут соединения.")
        except Exception as e:
            print(f"⛔ [DEBUG_DL] Исключение: {type(e).__name__}: {e}")
            break
            
    return None
async def admin_action_sync_worker():

    await asyncio.sleep(20)
    while True:
        try:
            from common.database import get_and_clear_admin_actions
            actions = await get_and_clear_admin_actions()
            for act in actions:
                bid = act['board_id']
                uid = act['user_id']
                if bid not in board_data and bid != 'ALL': continue
                target_boards = [bid] if bid != 'ALL' else list(board_data.keys())
                async with storage_lock:
                    for b in target_boards:
                        if act['type'] == 'ban':
                            board_data[b]['users']['banned'].add(uid)
                            board_data[b]['users']['active'].discard(uid)
                        elif act['type'] == 'unban':
                            board_data[b]['users']['banned'].discard(uid)
                            board_data[b]['users']['active'].add(uid)
                        elif act['type'] == 'shadow_mute':
                            from datetime import datetime, timezone
                            board_data[b]['shadow_mutes'][uid] = datetime.fromtimestamp(act['expires'], timezone.utc)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Sync error: {e}")
            await asyncio.sleep(10)
def smart_wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    Переносит текст по словам, основываясь на реальной пиксельной ширине.
    """
    wrapped_lines = []
    user_lines = text.split('\n')
    for line in user_lines:
        if not line:
            wrapped_lines.append('')
            continue
        words = line.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if draw.textlength(test_line, font=font) <= max_width:
                current_line += word + " "
            else:
                wrapped_lines.append(current_line.strip())
                current_line = word + " "
        wrapped_lines.append(current_line.strip())
    return "\n".join(wrapped_lines)
def generate_wipe_image(text: str) -> bytes | None:
    """
    Создает изображение 512x512 с текстом, искажениями и шумом.
    Исправлена ошибка DeprecationWarning для Pillow 10+.
    """
    try:
        IMAGE_SIZE = (512, 512)
        BACKGROUND_COLOR = (20, 20, 20)
        TEXT_COLOR = (240, 240, 240)
        background = Image.new('RGBA', IMAGE_SIZE, BACKGROUND_COLOR)
        if not FONTS_CACHE:
            print("⛔ КРИТИЧЕСКАЯ ОШИБКА: Шрифты не загружены (FONTS_CACHE пуст)!")
            error_img = Image.new('RGB', IMAGE_SIZE, BACKGROUND_COLOR)
            draw = ImageDraw.Draw(error_img)
            try:
                error_font = ImageFont.load_default()
            except Exception:
                return None
            draw.multiline_text(
                (50, 200), "ERROR:\nFONTS NOT FOUND", 
                fill=(255, 50, 50), font=error_font, align="center"
            )
            buffer = io.BytesIO()
            error_img.save(buffer, format='PNG')
            return buffer.getvalue()
        font = random.choice(FONTS_CACHE)
        temp_draw = ImageDraw.Draw(background)
        MAX_TEXT_WIDTH = IMAGE_SIZE[0] - 40 
        wrapped_text = smart_wrap_text(temp_draw, text, font, MAX_TEXT_WIDTH)
        text_layer = Image.new('RGBA', IMAGE_SIZE, (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_layer)
        draw.multiline_text(
            (IMAGE_SIZE[0] / 2, IMAGE_SIZE[1] / 2),
            wrapped_text,
            font=font,
            fill=TEXT_COLOR,
            anchor="mm",
            align="center"
        )
        angle = random.uniform(-15, 15) # Уменьшил угол для читаемости
        rotated_text_layer = text_layer.rotate(angle, expand=False, resample=Image.BICUBIC)
        img_array = np.array(rotated_text_layer)
        rows, cols, channels = img_array.shape
        amplitude = random.uniform(3, 10)
        frequency = random.uniform(0.05, 0.1)
        x_indices = np.arange(cols)
        y_offsets = (amplitude * np.sin(x_indices * frequency)).astype(int)
        y_indices = np.arange(rows).reshape(-1, 1) + y_offsets.reshape(1, -1)
        y_indices = np.clip(y_indices, 0, rows - 1)
        distorted_array = np.zeros_like(img_array)
        for x in range(cols):
            shift = y_offsets[x]
            if shift > 0:
                distorted_array[shift:, x] = img_array[:-shift, x]
            elif shift < 0:
                distorted_array[:shift, x] = img_array[-shift:, x]
            else:
                distorted_array[:, x] = img_array[:, x]
        distorted_layer = Image.fromarray(distorted_array, 'RGBA')
        background.alpha_composite(distorted_layer)
        noise_array = np.random.randint(0, 50, (IMAGE_SIZE[1], IMAGE_SIZE[0]), dtype=np.uint8)
        noise_layer = Image.fromarray(noise_array, 'L').convert('RGBA')
        noise_layer.putalpha(Image.new('L', IMAGE_SIZE, 30))
        final_image = Image.alpha_composite(background, noise_layer)
        buffer = io.BytesIO()
        final_image.convert("RGB").save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА в generate_wipe_image: {e}")
        import traceback
        traceback.print_exc()
        return None
async def _format_message_body(
    content: dict, 
    user_id_for_context: int, 
    post_data: dict,
    reply_to_post_author_id: int | None,
    quote_info: dict | None = None
) -> str:
    """
    Формирует и форматирует тело сообщения (реакции, reply, опрос, greentext, (You)).
    Версия 2.1: Добавлена поддержка "Быстрой цитаты" (Quick Quote) с защитой от None.
    """
    parts =[]

    # --- НАЧАЛО ИЗМЕНЕНИЙ (Блок "Быстрой цитаты") ---
    if quote_info:
        quote_text_raw = quote_info.get('text') or ''
        quote_text_clean = clean_html_tags(quote_text_raw) or ''
        
        quote_parts =[]
        if quote_text_clean:
            if len(quote_text_clean) > 140:
                quote_text = escape_html(quote_text_clean[:140]) + "..."
            else:
                quote_text = escape_html(quote_text_clean)
            quote_parts.append(quote_text)
        
        files_in_quote = quote_info.get('files',[])
        if files_in_quote:
            photo_count = sum(1 for f in files_in_quote if f.get('type') == 'photo')
            video_count = sum(1 for f in files_in_quote if f.get('type') == 'video')
            gif_count = sum(1 for f in files_in_quote if f.get('type') == 'animation')
            document_count = sum(1 for f in files_in_quote if f.get('type') == 'document')
            audio_count = sum(1 for f in files_in_quote if f.get('type') == 'audio')
            voice_count = sum(1 for f in files_in_quote if f.get('type') == 'voice')
            sticker_count = sum(1 for f in files_in_quote if f.get('type') == 'sticker')
            video_note_count = sum(1 for f in files_in_quote if f.get('type') == 'video_note')
            known_quote_types = {'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note'}
            other_count = sum(1 for f in files_in_quote if f.get('type') not in known_quote_types)
            
            media_counts =[]
            if photo_count > 0: media_counts.append(f"{photo_count} фото")
            if video_count > 0: media_counts.append(f"{video_count} видео")
            if gif_count > 0: media_counts.append(f"{gif_count} GIF")
            if document_count > 0: media_counts.append(f"{document_count} doc")
            if audio_count > 0: media_counts.append(f"{audio_count} audio")
            if voice_count > 0: media_counts.append(f"{voice_count} voice")
            if sticker_count > 0: media_counts.append(f"{sticker_count} sticker")
            if video_note_count > 0: media_counts.append(f"{video_note_count} video note")
            if other_count > 0: media_counts.append(f"{other_count} file")
            
            if media_counts:
                quote_parts.append(f"<i>[{', '.join(media_counts)}]</i>")

        final_quote_text = "\n".join(quote_parts).strip()
        if final_quote_text:
            quote_block = f"<blockquote expandable>{final_quote_text}</blockquote>"
            parts.append(quote_block)
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    reply_to_post = content.get('reply_to_post')
    if reply_to_post:
        you_marker = " (You)" if user_id_for_context == reply_to_post_author_id else ""
        reply_line = f">>{reply_to_post}{you_marker}"
        # Если есть быстрая цитата, не оборачиваем >> в code, чтобы было менее громоздко
        formatted_reply_line = reply_line if quote_info else f"<code>{escape_html(reply_line)}</code>"
        parts.append(formatted_reply_line)

    reactions_data = post_data.get('reactions')
    if reactions_data:
        reaction_lines =[]
        user_reactions = reactions_data.get('users', {})
        if isinstance(user_reactions, dict):
            all_emojis =[emoji for user_emojis in user_reactions.values() for emoji in user_emojis]
            categories =[
                POSITIVE_REACTIONS, LAUGHING_REACTIONS, THINKING_REACTIONS, 
                SHOCK_REACTIONS, SAD_REACTIONS, NEGATIVE_REACTIONS, CLOWN_REACTION,
                POLITICAL_REACTIONS, SYMBOLIC_REACTIONS, INSULT_REACTIONS
            ]
            known_emojis = set().union(*categories)
            display_groups = {
                'positive': sorted([e for e in all_emojis if e in POSITIVE_REACTIONS]),
                'laughing': sorted([e for e in all_emojis if e in LAUGHING_REACTIONS]),
                'thinking': sorted([e for e in all_emojis if e in THINKING_REACTIONS]),
                'shock': sorted([e for e in all_emojis if e in SHOCK_REACTIONS]),
                'sad': sorted([e for e in all_emojis if e in SAD_REACTIONS]),
                'negative': sorted([e for e in all_emojis if e in NEGATIVE_REACTIONS]),
                'clown': sorted([e for e in all_emojis if e in CLOWN_REACTION]),
                'political': sorted([e for e in all_emojis if e in POLITICAL_REACTIONS]),
                'symbolic': sorted([e for e in all_emojis if e in SYMBOLIC_REACTIONS]),
                'insult': sorted([e for e in all_emojis if e in INSULT_REACTIONS]),
                'neutral': sorted([e for e in all_emojis if e not in known_emojis]),
            }
            for group_name, group_emojis in display_groups.items():
                if group_emojis:
                    reaction_lines.append("".join(group_emojis))
        elif 'positive' in reactions_data or 'negative' in reactions_data:
            if reactions_data.get('positive'): reaction_lines.append("".join(reactions_data['positive']))
            if reactions_data.get('neutral'): reaction_lines.append("".join(reactions_data['neutral']))
            if reactions_data.get('negative'): reaction_lines.append("".join(reactions_data['negative']))
        if reaction_lines:
            reactions_block = "\n".join(reaction_lines)
            parts.append(reactions_block)
            
    poll_data = content.get('poll_data')
    if poll_data:
        poll_display_text = generate_poll_text_display(poll_data)
        if poll_display_text:
            parts.append(poll_display_text)
            
    main_text_raw = content.get('text') or content.get('caption') or ''
    if main_text_raw:
        if not poll_data:
             safe_text = main_text_raw
             text_with_tags = convert_site_tags_to_telegram(safe_text)
             formatted_main_text = apply_greentext_formatting(text_with_tags)
             parts.append(formatted_main_text)
        else:
             parts.append(convert_site_tags_to_telegram(main_text_raw))
             
    return '\n\n'.join(filter(None, parts))
def generate_poll_text_display(poll_data: dict) -> str:
    """
    Генерирует текстовое представление опроса с ASCII-барами.
    """
    if not poll_data or 'question' not in poll_data or 'options' not in poll_data:
        return ""
    question = escape_html(poll_data['question'])
    options = poll_data.get('options', [])
    votes = poll_data.get('votes', {})
    total_votes = sum(len(v) for v in votes.values())
    lines = [f"📊 <b>{question.upper()}</b>\n"]
    BAR_LENGTH = 14
    for i, option_text in enumerate(options):
        option_key = str(i)
        vote_count = len(votes.get(option_key, []))
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
        filled_length = int(BAR_LENGTH * vote_count / total_votes) if total_votes > 0 else 0
        bar = '█' * filled_length + '─' * (BAR_LENGTH - filled_length)
        safe_option_text = escape_html(option_text)
        lines.append(f"<code>{i+1}. {safe_option_text}:</code>\n<code>[{bar}] {vote_count} ({percentage:.0f}%)</code>")
    return "\n".join(lines)
def split_text(text: str, limit: int) -> list[str]:
    """
    Разбивает длинный текст на части, не превышающие лимит Telegram.
    Добавляет нумерацию (1/N) к частям.
    """
    if len(text) <= limit:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > limit:
            if current_part:
                parts.append(current_part)
            current_part = ""
        while len(line) > limit:
            split_at = line.rfind(' ', 0, limit)
            if split_at == -1: # Если пробелов нет, режем по лимиту
                split_at = limit
            parts.append(line[:split_at])
            line = line[split_at:].lstrip()
        if current_part:
            current_part += "\n" + line
        else:
            current_part = line
    if current_part:
        parts.append(current_part)
    total_parts = len(parts)
    if total_parts > 1:
        for i in range(total_parts):
            suffix = f"\n({i+1}/{total_parts})"
            part_limit = limit - len(suffix)
            if len(parts[i]) > part_limit:
                 parts[i] = parts[i][:part_limit] # Обрезаем, если нужно
            parts[i] += suffix
    return parts


def _normalize_quote_file_type(raw_type) -> str:
    media_type = str(raw_type or 'file').split('.')[-1].lower()
    if media_type in {'image', 'picture'}:
        return 'photo'
    if media_type in {'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note'}:
        return media_type
    if media_type in {'gif'}:
        return 'animation'
    return 'file'


def _quote_info_from_content(replied_content: dict | None) -> dict | None:
    if not isinstance(replied_content, dict):
        return None
    quote_text = replied_content.get('text') or replied_content.get('caption') or ''
    files = []
    content_type = _normalize_quote_file_type(replied_content.get('type'))
    media_items = replied_content.get('media')
    if isinstance(media_items, list):
        for item in media_items:
            if isinstance(item, dict):
                files.append({'type': _normalize_quote_file_type(item.get('type'))})
            else:
                files.append({'type': 'file'})
    elif media_items:
        files.append({'type': content_type})
    file_items = replied_content.get('files')
    if isinstance(file_items, list):
        for item in file_items:
            if isinstance(item, dict):
                files.append({'type': _normalize_quote_file_type(item.get('type'))})
            else:
                files.append({'type': 'file'})
    if replied_content.get('file_id') or replied_content.get('image_bytes') or replied_content.get('image_url'):
        files.append({'type': content_type})
    if content_type in {'sticker', 'video_note', 'voice'} and not files:
        files.append({'type': content_type})
    if replied_content.get('poll_data'):
        files.append({'type': 'poll'})
    if not quote_text and not files:
        return None
    return {'text': quote_text, 'files': files}


async def build_quick_quote_info(reply_to_post: int | None) -> dict | None:
    if not reply_to_post:
        return None
    current_max_post = await get_max_post_num()
    if current_max_post - reply_to_post <= QUICK_QUOTE_POST_DISTANCE:
        return None
    replied_post_data = await get_post_by_num(reply_to_post)
    if not replied_post_data:
        return None
    return _quote_info_from_content(replied_post_data.get('content'))
def mark_weekly_active_delivery_user(board_id: str, user_id: int):
    if not PRIORITY_DELIVERY_ENABLED or user_id <= 0:
        return
    weekly_active_users.setdefault(board_id, set()).add(user_id)


def _split_recipients_for_delivery(board_id: str, recipients) -> tuple[list[int], list[int]]:
    recipient_list = list(recipients)
    if not PRIORITY_DELIVERY_ENABLED or not recipient_list:
        return [], recipient_list
    priority_set = weekly_active_users.get(board_id, set())
    if not priority_set:
        return [], recipient_list
    priority = []
    passive = []
    for uid in recipient_list:
        if uid in priority_set:
            priority.append(uid)
        else:
            passive.append(uid)
    return priority, passive


def _order_recipients_for_delivery(board_id: str, recipients) -> tuple[list[int], int, int]:
    priority, passive = _split_recipients_for_delivery(board_id, recipients)
    if not priority:
        return passive, 0, len(passive)
    return priority + passive, len(priority), len(passive)


class DeliveryResults(list):
    def __init__(self, values=(), remaining_recipients=None, interrupted_reason: str | None = None):
        super().__init__(values)
        self.remaining_recipients = set(remaining_recipients or ())
        self.interrupted_reason = interrupted_reason


def _phase_time_budget_sec(delivery_phase: str) -> float:
    if delivery_phase == "priority":
        return PRIORITY_PHASE_BUDGET_SEC
    if delivery_phase in {"passive", "passive_slice"}:
        return PASSIVE_PHASE_BUDGET_SEC
    return 0.0


_LIE_VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.mkv')
_LIE_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def _lie_media_kind(raw_type: str | None, item: dict | None = None) -> str | None:
    item = item or {}
    ftype = str(raw_type or item.get('type') or '').split('.')[-1].lower()
    mime = str(item.get('mime_type') or item.get('mime') or '').lower()
    filename = str(item.get('filename') or item.get('file_name') or item.get('name') or '').lower()
    if ftype in {'photo', 'image'}:
        return 'image'
    if ftype in {'video', 'animation', 'gif'}:
        return 'video'
    if ftype == 'document':
        if mime.startswith('video/') or filename.endswith(_LIE_VIDEO_EXTS):
            return 'video'
        if mime.startswith('image/') or filename.endswith(_LIE_IMAGE_EXTS):
            return 'image'
    return None


def _lie_archive_send_type(entry: dict, desired_kind: str) -> str | None:
    source_type = str(entry.get('source_type') or entry.get('type') or '').split('.')[-1].lower()
    mime = str(entry.get('mime_type') or entry.get('mime') or '').lower()
    filename = str(entry.get('filename') or entry.get('file_name') or entry.get('name') or '').lower()
    if desired_kind == 'image':
        if source_type in {'photo', 'image'}:
            return 'photo'
        if source_type == 'document' and (mime.startswith('image/') or filename.endswith(_LIE_IMAGE_EXTS)):
            return 'document'
    elif desired_kind == 'video':
        if source_type == 'video':
            return 'video'
        if source_type in {'animation', 'gif'}:
            return 'animation'
        if source_type == 'document' and (mime.startswith('video/') or filename.endswith(_LIE_VIDEO_EXTS)):
            return 'document'
    return None


def _lie_file_from_random_post(
    post: dict | None,
    desired_kind: str,
    allowed_send_types: set[str],
    avoid_post_num: int | None = None,
    exclude_file_ids: set[str] | None = None,
) -> dict | None:
    if not post or not isinstance(post.get('content'), dict):
        return None
    if avoid_post_num is not None:
        try:
            candidate_post_num = int(post.get('post_num') or post.get('id') or 0)
            if candidate_post_num == int(avoid_post_num):
                return None
        except (TypeError, ValueError):
            pass
    files = post['content'].get('files') or []
    if not files:
        return None
    selected_idx = post.get('_selected_file_index', 0)
    if not isinstance(selected_idx, int) or selected_idx < 0 or selected_idx >= len(files):
        selected_idx = 0
    entry = files[selected_idx]
    if not isinstance(entry, dict):
        return None
    file_id = entry.get('original_file_id') or entry.get('file_id') or entry.get('media')
    if not file_id or not isinstance(file_id, str) or file_id.startswith('<'):
        return None
    if exclude_file_ids and file_id in exclude_file_ids:
        return None
    send_type = _lie_archive_send_type(entry, desired_kind)
    if not send_type or send_type not in allowed_send_types:
        return None
    return {
        'type': send_type,
        'file_id': file_id,
        'filename': entry.get('filename') or entry.get('file_name') or entry.get('name'),
        'mime_type': entry.get('mime_type') or entry.get('mime'),
    }


async def _get_lie_archive_media(
    board_id: str,
    desired_kind: str,
    allowed_send_types: set[str],
    avoid_post_num: int | None = None,
    exclude_file_ids: set[str] | None = None,
) -> dict | None:
    getter = get_random_video_post if desired_kind == 'video' else get_random_image_post
    for _ in range(12):
        post = await getter([board_id])
        media = _lie_file_from_random_post(post, desired_kind, allowed_send_types, avoid_post_num, exclude_file_ids)
        if media:
            return media
    return None


def _lie_allowed_send_types(raw_type: str, media_group: bool = False) -> set[str]:
    ctype = str(raw_type or '').split('.')[-1].lower()
    if media_group:
        if ctype == 'photo':
            return {'photo'}
        if ctype == 'video':
            return {'video'}
        if ctype == 'document':
            return {'document'}
        return set()
    if ctype == 'photo':
        return {'photo'}
    if ctype == 'video':
        return {'video'}
    if ctype == 'animation':
        return {'animation'}
    if ctype == 'document':
        return {'document'}
    return set()


async def _build_lie_media_content(content: dict, board_id: str) -> dict:
    ctype = str(content.get('type') or '').split('.')[-1].lower()
    avoid_post_num = content.get('post_num')
    if ctype == 'media_group':
        source_media = content.get('media') or []
        if not source_media:
            return content
        replaced_any = False
        lie_media = []
        used_file_ids = set()
        for item in source_media:
            if not isinstance(item, dict):
                lie_media.append(item)
                continue
            item_type = str(item.get('type') or '').split('.')[-1].lower()
            desired_kind = _lie_media_kind(item_type, item)
            allowed_types = _lie_allowed_send_types(item_type, media_group=True)
            if desired_kind and allowed_types:
                replacement = await _get_lie_archive_media(
                    board_id,
                    desired_kind,
                    allowed_types,
                    avoid_post_num,
                    used_file_ids,
                )
                if replacement:
                    new_item = {
                        'type': replacement['type'],
                        'file_id': replacement['file_id'],
                        'media': replacement['file_id'],
                    }
                    if replacement.get('filename'):
                        new_item['filename'] = replacement['filename']
                    if replacement.get('mime_type'):
                        new_item['mime_type'] = replacement['mime_type']
                    lie_media.append(new_item)
                    used_file_ids.add(replacement['file_id'])
                    replaced_any = True
                    continue
            lie_media.append(item.copy())
        if not replaced_any:
            return content
        lie_content = content.copy()
        lie_content['media'] = lie_media
        return lie_content

    desired_kind = _lie_media_kind(ctype, content)
    allowed_types = _lie_allowed_send_types(ctype)
    if not desired_kind or not allowed_types:
        return content
    replacement = await _get_lie_archive_media(board_id, desired_kind, allowed_types, avoid_post_num)
    if not replacement:
        return content
    lie_content = content.copy()
    lie_content['type'] = replacement['type']
    lie_content['file_id'] = replacement['file_id']
    lie_content.pop('image_url', None)
    lie_content.pop('image_bytes', None)
    lie_content.pop('media', None)
    if replacement.get('filename'):
        lie_content['filename'] = replacement['filename']
    if replacement.get('mime_type'):
        lie_content['mime_type'] = replacement['mime_type']
    return lie_content


async def send_message_to_users(
    bot_instance: Bot,
    board_id: str,
    recipients: set[int],
    content: dict,
    reply_info: dict | None = None,
    keyboard: InlineKeyboardMarkup | None = None,
    verbose: bool = False,
    queue_enqueued_at: float | None = None,
    queue_wait_sec: float | None = None,
    delivery_phase: str = "full",
    delivery_original_recipients: int | None = None,
    delivery_deferred_recipients: int = 0,
) -> list:
    """
    Оптимизированная функция массовой рассылки.
    Сложность снижена с O(N*M) до O(N + M) за счет выноса форматирования.
    ВКЛЮЧЕНА ЗАЩИТА ОТ ДУБЛЕЙ (SMART RETRY) И ЛОГИРОВАНИЕ.
    Рассылка с Smart Retry.
    verbose=False -> тихий режим (для отправки автору).
    verbose=True -> пишет отчет в консоль (для массовой).
    """
    if not recipients or not content or 'type' not in content:
        return []
    b_data = board_data[board_id]
    active_recipients = {
        uid for uid in recipients 
        if uid > 0 and uid not in b_data['users']['banned']
    }
    if not active_recipients:
        return[]
    original_recipients_count = delivery_original_recipients or len(active_recipients)
    ordered_recipients, priority_recipients_count, passive_recipients_count = _order_recipients_for_delivery(
        board_id, active_recipients
    )
    start_time = time.time()
    stats = {
        'success': 0,
        'ghosts': 0,  # Потенциальные дубли, которые мы предотвратили
        'errors': 0,  # Ошибки API/Формата
        'blocks': 0,  # Юзер заблокировал
        'retries': 0,  # Количество повторов из-за флуда/сети
        'timeouts': 0,  # Персональные таймауты отправки
        'priority_recipients': priority_recipients_count,
        'passive_recipients': passive_recipients_count,
    }
    final_keyboard = keyboard 
    media_url_text_fallback = False
    media_url_fallback_logged = False
    html_plain_fallback_logged = False
    if content.get('poll_data') and not final_keyboard:
        poll_options = content.get('poll_data', {}).get('options',[])
        post_num = content.get('post_num')
        if poll_options and post_num:
            buttons =[]
            for i, option_text in enumerate(poll_options):
                button_text = option_text[:60]
                buttons.append(
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"poll_vote_{post_num}_{i}"
                    )
                )
            final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
            
    post_num = content.get('post_num')
    post_data_copy = {}
    reply_to_post_author_id = None
    post_num_for_replies = None
    
    async with storage_lock:
        if post_num:
            post_data = messages_storage.get(post_num, {})
            if post_data: 
                post_data_copy = post_data.copy()
        reply_to_post_num = content.get('reply_to_post')
        if reply_to_post_num:
            reply_p_data = messages_storage.get(reply_to_post_num, {})
            reply_to_post_author_id = reply_p_data.get('author_id')
            post_num_for_replies = reply_to_post_num

    # --- НАЧАЛО ИЗМЕНЕНИЙ (Восстановление старых реплаев из БД) ---
    db_replies_map = {}
    if post_num_for_replies:
        # Восстанавливаем ID автора для маркера (You), если его нет в RAM
        if not reply_to_post_author_id:
            db_post = await get_post_by_num(post_num_for_replies)
            if db_post:
                reply_to_post_author_id = db_post.get('author_id')
        
        # Проверяем наличие message_id в памяти
        in_ram = False
        async with storage_lock:
            if post_num_for_replies in post_to_messages:
                in_ram = True
        
        # Если в памяти нет, достаем копии из БД
        if not in_ram:
            db_copies = await get_post_copies(post_num_for_replies)
            for rec_id, msg_id in db_copies:
                db_replies_map[rec_id] = msg_id
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    raw_text = content.get('text') or content.get('caption') or ''
    content_for_common = content.copy()
    common_formatted_body = await _format_message_body(
        content=content_for_common, 
        user_id_for_context=0, 
        post_data=post_data_copy, 
        reply_to_post_author_id=reply_to_post_author_id,
        quote_info=content_for_common.get('quote_info')
    )
    base_header_text = content.get('header', '')
    highlight_header_text = base_header_text
    if "Пост" in highlight_header_text:
        highlight_header_text = highlight_header_text.replace("Пост", "🔴 Пост", 1)
    elif "Post" in highlight_header_text:
        highlight_header_text = highlight_header_text.replace("Post", "🔴 Post", 1)
    base_head_html = f"<i>{escape_html(base_header_text)}</i>"
    highlight_head_html = f"<i>{escape_html(highlight_header_text)}</i>"
    has_reply_markers = ">>" in raw_text
    users_settings = b_data.get('user_settings', {})
    all_results =[]
    blocked_users = set()
    mentioned_authors = {}
    
    if ">>" in raw_text:
        mentions = RE_YOU_PATTERN.findall(raw_text)
        if mentions:
            missing_mentions =[]
            async with storage_lock:
                for m_num_str in mentions:
                    try:
                        m_num = int(m_num_str)
                        if m_num in messages_storage:
                            mentioned_authors[m_num] = messages_storage[m_num].get("author_id")
                        else:
                            missing_mentions.append(m_num)
                    except ValueError:
                        continue
                        
            # --- НАЧАЛО ИЗМЕНЕНИЙ (Восстановление маркеров (You) для старых постов) ---
            if missing_mentions:
                for m_num in missing_mentions:
                    db_post = await get_post_by_num(m_num)
                    if db_post:
                        mentioned_authors[m_num] = db_post.get("author_id")
            # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    async def _send_one(uid: int, telegram_request_timeout_sec: int):
        nonlocal stats, media_url_text_fallback, media_url_fallback_logged, html_plain_fallback_logged
        request_timeout = max(3, int(telegram_request_timeout_sec))
        u_set = users_settings.get(uid, {'nsfw': False, 'hide': set()})
        if u_set['hide']:
            check_text = (base_header_text + " " + raw_text).lower()
            if any(word in check_text for word in u_set['hide']):
                lang_local = 'en' if board_id == 'int' else 'ru'
                placeholder = "🛡 Message hidden" if lang_local == 'en' else "🛡 Сообщение скрыто"
                try:
                    res = await bot_instance.send_message(
                        uid,
                        f"{base_head_html}\n{placeholder}",
                        parse_mode="HTML",
                        request_timeout=request_timeout,
                    )
                    stats['success'] += 1
                    return res
                except Exception:
                    stats['errors'] += 1
                    return None
                    
        head = highlight_head_html if uid == reply_to_post_author_id else base_head_html
        body = common_formatted_body
        is_direct_reply = (uid == reply_to_post_author_id)
        send_content = content_for_common
        if u_set.get('lie_media'):
            try:
                send_content = await _build_lie_media_content(content_for_common, board_id)
                if send_content is not content_for_common:
                    body = await _format_message_body(
                        content=send_content,
                        user_id_for_context=uid,
                        post_data=post_data_copy,
                        reply_to_post_author_id=reply_to_post_author_id,
                        quote_info=send_content.get('quote_info')
                    )
            except Exception as exc:
                runtime_logger.warning(
                    "lie_media_replacement_failed %s",
                    json.dumps(
                        {
                            "board_id": board_id,
                            "post_num": post_num,
                            "uid": uid,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                send_content = content_for_common
        current_content = send_content
        
        if mentioned_authors:
            text_with_you = add_you_to_my_posts_fast(raw_text, uid, mentioned_authors)
            if text_with_you != raw_text:
                current_content = send_content.copy()
                target_field = 'text' if 'text' in current_content else 'caption'
                current_content[target_field] = text_with_you
                body = await _format_message_body(
                    content=current_content,
                    user_id_for_context=uid, 
                    post_data=post_data_copy,
                    reply_to_post_author_id=reply_to_post_author_id,
                    quote_info=current_content.get('quote_info')
                )
        elif is_direct_reply:
             body = await _format_message_body(
                content=current_content,
                user_id_for_context=uid, 
                post_data=post_data_copy,
                reply_to_post_author_id=reply_to_post_author_id,
                quote_info=current_content.get('quote_info')
            )
        
        full_text = f"{head}\n\n{body}" if body else head
        reply_to_mid = None
        if reply_info:
            raw = reply_info.get(uid)
            if raw: reply_to_mid = raw[0] if isinstance(raw, list) else raw
            
        if reply_to_mid is None and post_num_for_replies:
            async with storage_lock:
                replies_map = post_to_messages.get(post_num_for_replies)
                if replies_map:
                    raw = replies_map.get(uid)
                    if raw: reply_to_mid = raw[0] if isinstance(raw, list) else raw

        # --- НАЧАЛО ИЗМЕНЕНИЙ (Фоллбэк на кэш из базы данных) ---
        if reply_to_mid is None and post_num_for_replies:
            reply_to_mid = db_replies_map.get(uid)
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        is_sage = send_content.get('is_sage', False)
        has_spoiler = u_set['nsfw']
        max_attempts = 5
        attempt_delay = 1.5

        async def _send_text_fallback(reason: str):
            nonlocal media_url_fallback_logged
            fallback_text = full_text
            media_url = current_content.get("image_url")
            if media_url and str(media_url) not in fallback_text:
                fallback_text = f"{fallback_text}\n\n{escape_html(str(media_url))}"
            if not media_url_fallback_logged:
                runtime_logger.warning(
                    "delivery_media_url_text_fallback %s",
                    json.dumps(
                        {
                            "board_id": board_id,
                            "post_num": post_num,
                            "phase": delivery_phase,
                            "type": str(current_content.get("type")),
                            "reason": reason,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                media_url_fallback_logged = True
            sent_msgs = []
            parts = split_text(fallback_text, 4096)
            for i, part in enumerate(parts):
                m = await bot_instance.send_message(
                    chat_id=uid,
                    text=part,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_mid if i == 0 else None,
                    reply_markup=final_keyboard if i == len(parts) - 1 else None,
                    disable_notification=is_sage,
                    disable_web_page_preview=True,
                    request_timeout=request_timeout,
                )
                sent_msgs.append(m)
            stats['success'] += 1
            return sent_msgs

        def _telegram_parse_error(err_low: str) -> bool:
            return (
                "can't parse entities" in err_low
                or "can't find end tag" in err_low
                or "unsupported start tag" in err_low
                or "unmatched end tag" in err_low
                or "can't parse message text" in err_low
            )

        def _plain_delivery_text() -> str:
            plain_head = html.unescape(clean_html_tags(head or ""))
            plain_body = html.unescape(clean_html_tags(body or ""))
            if plain_body:
                text = f"{plain_head}\n\n{plain_body}"
            else:
                text = plain_head
            return text.strip() or "."

        def _log_plain_fallback(reason: str) -> None:
            nonlocal html_plain_fallback_logged
            if html_plain_fallback_logged:
                return
            runtime_logger.warning(
                "delivery_html_plain_fallback %s",
                json.dumps(
                    {
                        "board_id": board_id,
                        "post_num": post_num,
                        "phase": delivery_phase,
                        "type": str(current_content.get("type")),
                        "reason": reason,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            html_plain_fallback_logged = True

        async def _send_plain_text_parts(
            reason: str,
            text: str | None = None,
            reply_to_id: int | None = None,
            include_keyboard: bool = True,
        ):
            _log_plain_fallback(reason)
            sent_msgs = []
            fallback_text = text if text is not None else _plain_delivery_text()
            parts = split_text(fallback_text, 4096)
            target_reply_id = reply_to_id if reply_to_id is not None else reply_to_mid
            for i, part in enumerate(parts):
                m = await bot_instance.send_message(
                    chat_id=uid,
                    text=part,
                    reply_to_message_id=target_reply_id if i == 0 else None,
                    reply_markup=final_keyboard if include_keyboard and i == len(parts) - 1 else None,
                    disable_notification=is_sage,
                    disable_web_page_preview=True,
                    request_timeout=request_timeout,
                )
                sent_msgs.append(m)
            stats['success'] += 1
            return sent_msgs

        def _plain_media_source(media_type: str):
            if current_content.get("image_bytes"):
                if media_type == 'photo':
                    filename = "file.jpg"
                elif media_type == 'animation':
                    filename = "file.gif"
                elif media_type == 'audio':
                    filename = "file.mp3"
                elif media_type == 'voice':
                    filename = "file.ogg"
                else:
                    filename = "file.mp4"
                return BufferedInputFile(current_content["image_bytes"], filename=filename)
            return current_content.get("file_id") or current_content.get("image_url")

        async def _send_plain_media_fallback(reason: str):
            plain_text = _plain_delivery_text()
            ct = str(current_content.get("type") or "").split('.')[-1].lower()
            if ct == "text":
                return await _send_plain_text_parts(reason, plain_text)
            if ct in ['photo', 'video', 'animation', 'document', 'audio', 'voice']:
                file_source = _plain_media_source(ct)
                if not file_source:
                    return await _send_plain_text_parts(reason, plain_text)
                common_plain_kwargs = {
                    'chat_id': uid,
                    'reply_to_message_id': reply_to_mid,
                    'reply_markup': final_keyboard,
                    'disable_notification': is_sage,
                    'request_timeout': request_timeout,
                }
                if has_spoiler and ct in ['photo', 'video', 'animation']:
                    common_plain_kwargs['has_spoiler'] = True
                send_method = getattr(bot_instance, f"send_{ct}")
                if len(plain_text) > 1024:
                    common_plain_kwargs[ct] = file_source
                    media_msg = await send_method(**common_plain_kwargs)
                    await _send_plain_text_parts(
                        reason,
                        plain_text,
                        reply_to_id=media_msg.message_id,
                        include_keyboard=False,
                    )
                    return media_msg
                common_plain_kwargs['caption'] = plain_text
                common_plain_kwargs[ct] = file_source
                res = await send_method(**common_plain_kwargs)
                _log_plain_fallback(reason)
                stats['success'] += 1
                return res
            if ct == "media_group":
                media_group_build = []
                can_fit_caption = len(plain_text) <= 1024
                caption_for_group = plain_text if can_fit_caption else None
                for idx, item in enumerate(current_content.get('media') or []):
                    media_src = item.get('media') or item.get('file_id')
                    if not media_src:
                        continue
                    m_type = str(item.get('type') or '').split('.')[-1].lower()
                    cap = caption_for_group if idx == 0 else None
                    if m_type == 'photo':
                        media_group_build.append(InputMediaPhoto(media=media_src, caption=cap, has_spoiler=has_spoiler))
                    elif m_type == 'video':
                        media_group_build.append(InputMediaVideo(media=media_src, caption=cap, has_spoiler=has_spoiler))
                    elif m_type == 'document':
                        media_group_build.append(InputMediaDocument(media=media_src, caption=cap))
                    elif m_type == 'audio':
                        media_group_build.append(InputMediaAudio(media=media_src, caption=cap))
                if not media_group_build:
                    return await _send_plain_text_parts(reason, plain_text)
                res = await bot_instance.send_media_group(
                    chat_id=uid,
                    media=media_group_build,
                    reply_to_message_id=reply_to_mid,
                    disable_notification=is_sage,
                    request_timeout=request_timeout,
                )
                _log_plain_fallback(reason)
                if not can_fit_caption:
                    anchor_msg = res[0] if isinstance(res, list) else res
                    anchor_id = getattr(anchor_msg, "message_id", None)
                    await _send_plain_text_parts(reason, plain_text, reply_to_id=anchor_id, include_keyboard=True)
                    return res
                stats['success'] += 1
                return res
            if ct in ['sticker', 'video_note', 'dice']:
                text_result = await _send_plain_text_parts(reason, plain_text)
                if ct == 'dice':
                    await bot_instance.send_dice(
                        chat_id=uid,
                        emoji=current_content.get('dice_emoji', '\U0001F3B2'),
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                elif current_content.get("file_id"):
                    send_method = getattr(bot_instance, f"send_{ct}")
                    await send_method(
                        chat_id=uid,
                        **{ct: current_content.get("file_id")},
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                return text_result
            return await _send_plain_text_parts(reason, plain_text)
        
        for attempt in range(max_attempts):
            try:
                ct_raw = current_content["type"]
                ct = str(ct_raw).split('.')[-1].lower()
                common_kwargs = {
                    'chat_id': uid, 
                    'reply_to_message_id': reply_to_mid,
                    'reply_markup': final_keyboard, 
                    'disable_notification': is_sage,
                    'request_timeout': request_timeout,
                }
                result_msg = None
                if ct == 'text':
                    parts = split_text(full_text, 4096)
                    sent_msgs =[]
                    for i, part in enumerate(parts):
                        m = await bot_instance.send_message(
                            chat_id=uid, text=part, parse_mode="HTML",
                            reply_to_message_id=reply_to_mid if i == 0 else None,
                            reply_markup=final_keyboard if i == len(parts)-1 else None,
                            disable_notification=is_sage,
                            disable_web_page_preview=True,
                            request_timeout=request_timeout,
                        )
                        sent_msgs.append(m)
                    stats['success'] += 1
                    return sent_msgs
                elif ct in['photo', 'video', 'animation', 'document', 'audio', 'voice']:
                    file_source = None
                    if current_content.get("image_bytes"):
                        if ct == 'photo': 
                            filename = "file.jpg"
                        elif ct == 'animation':
                            filename = "file.gif" 
                        else:
                            filename = "video.mp4"
                        file_source = BufferedInputFile(current_content["image_bytes"], filename=filename)
                    elif current_content.get("file_id"):
                        file_source = current_content["file_id"]
                    elif current_content.get("image_url"):
                        file_source = current_content["image_url"]
                    if not file_source:
                        stats['errors'] += 1
                        return None
                    if media_url_text_fallback and current_content.get("image_url"):
                        return await _send_text_fallback("cached_bad_media_url")
                    if has_spoiler and ct in['photo', 'video', 'animation']:
                        common_kwargs['has_spoiler'] = True
                    if len(full_text) > 1024:
                        common_kwargs[ct] = file_source
                        send_method = getattr(bot_instance, f"send_{ct}")
                        media_msg = await send_method(**common_kwargs)
                        text_parts = split_text(full_text, 4096)
                        try:
                            for part in text_parts:
                                await bot_instance.send_message(
                                    chat_id=uid, text=part, parse_mode="HTML",
                                    reply_to_message_id=media_msg.message_id,
                                    disable_notification=is_sage,
                                    disable_web_page_preview=True,
                                    request_timeout=request_timeout,
                                )
                        except TelegramBadRequest as e:
                            if _telegram_parse_error(e.message.lower()):
                                await _send_plain_text_parts(
                                    "telegram_rejected_html_after_media",
                                    _plain_delivery_text(),
                                    reply_to_id=media_msg.message_id,
                                    include_keyboard=False,
                                )
                                return media_msg
                            raise
                        stats['success'] += 1
                        return media_msg
                    else:
                        common_kwargs['caption'] = full_text
                        common_kwargs['parse_mode'] = "HTML"
                        common_kwargs[ct] = file_source
                        send_method = getattr(bot_instance, f"send_{ct}")
                        res = await send_method(**common_kwargs)
                        stats['success'] += 1
                        return res
                elif ct == "media_group":
                    if not current_content.get('media'):
                        stats['errors'] += 1
                        return None
                    
                    # Безопасная обработка длинных подписей для альбомов
                    can_fit_caption = len(full_text) <= 1024
                    caption_for_group = full_text if can_fit_caption else None
                    
                    media_group_build = []
                    for idx, item in enumerate(current_content['media']):
                        media_src = item.get('media') or item.get('file_id')
                        if not media_src: continue
                        m_type = item['type']
                        cap = caption_for_group if idx == 0 else None
                        
                        if m_type == 'photo':
                            media_group_build.append(InputMediaPhoto(media=media_src, caption=cap, parse_mode="HTML" if cap else None, has_spoiler=has_spoiler))
                        elif m_type == 'video':
                            media_group_build.append(InputMediaVideo(media=media_src, caption=cap, parse_mode="HTML" if cap else None, has_spoiler=has_spoiler))
                        elif m_type == 'document':
                            media_group_build.append(InputMediaDocument(media=media_src, caption=cap, parse_mode="HTML" if cap else None))
                        elif m_type == 'audio':
                            media_group_build.append(InputMediaAudio(media=media_src, caption=cap, parse_mode="HTML" if cap else None))
                    
                    if not media_group_build: 
                        stats['errors'] += 1
                        return None

                    res = await bot_instance.send_media_group(
                        chat_id=uid, media=media_group_build, 
                        reply_to_message_id=reply_to_mid,
                        disable_notification=is_sage,
                        request_timeout=request_timeout,
                    )
                    
                    # Если текст не поместился в подпись, шлем его отдельным ответом на этот же альбом
                    if not can_fit_caption:
                        anchor_msg = res[0] if isinstance(res, list) else res
                        text_parts = split_text(full_text, 4096)
                        try:
                            for part in text_parts:
                                await bot_instance.send_message(
                                    chat_id=uid, text=part, parse_mode="HTML",
                                    reply_to_message_id=anchor_msg.message_id,
                                    disable_notification=is_sage,
                                    disable_web_page_preview=True,
                                    request_timeout=request_timeout,
                                )
                        except TelegramBadRequest as e:
                            if _telegram_parse_error(e.message.lower()):
                                await _send_plain_text_parts(
                                    "telegram_rejected_html_after_media_group",
                                    _plain_delivery_text(),
                                    reply_to_id=anchor_msg.message_id,
                                    include_keyboard=True,
                                )
                                return res
                            raise
                    
                    stats['success'] += 1
                    return res
                elif ct in['sticker', 'video_note', 'dice']:
                    if ct == 'dice':
                        await bot_instance.send_message(
                            uid,
                            full_text,
                            parse_mode="HTML",
                            reply_to_message_id=reply_to_mid,
                            disable_notification=is_sage,
                            request_timeout=request_timeout,
                        )
                        res = await bot_instance.send_dice(
                            chat_id=uid,
                            emoji=current_content.get('dice_emoji', '🎲'),
                            disable_notification=is_sage,
                            request_timeout=request_timeout,
                        )
                    else:
                        common_kwargs[ct] = current_content.get("file_id")
                        send_method = getattr(bot_instance, f"send_{ct}")
                        res = await send_method(**common_kwargs)
                    stats['success'] += 1
                    return res
            except TelegramBadRequest as e:
                err_low = e.message.lower()
                if _telegram_parse_error(err_low):
                    return await _send_plain_media_fallback("telegram_rejected_html")
                if (
                    current_content.get("image_url")
                    and (
                        "wrong type of the web page content" in err_low
                        or "failed to get http url content" in err_low
                        or "wrong file identifier/http url specified" in err_low
                    )
                ):
                    media_url_text_fallback = True
                    return await _send_text_fallback("telegram_rejected_media_url")
                if "too big" in err_low or "file of size" in err_low:
                    if current_content.get('type') == 'media_group' and current_content.get('media'):
                        print(f"⚠️[Anti-Fat] Пост #{post_num}: Обнаружен жирный файл. Запуск фильтрации...")
                        clean_media_list =[]
                        async with aiohttp.ClientSession() as head_session:
                            for item in current_content['media']:
                                media_obj = item.get('media') or item.get('file_id')
                                should_skip = False
                                if hasattr(media_obj, 'data'):
                                    if len(media_obj.data) > 9_900_000:
                                        print(f"   🗑 Исключен BufferedInputFile ({len(media_obj.data)/1024/1024:.2f} MB)")
                                        should_skip = True
                                elif isinstance(media_obj, bytes):
                                    if len(media_obj) > 9_900_000:
                                        print(f"   🗑 Исключены raw bytes ({len(media_obj)/1024/1024:.2f} MB)")
                                        should_skip = True
                                if should_skip:
                                    continue
                                if isinstance(media_obj, str) and media_obj.startswith('http'):
                                    try:
                                        async with head_session.head(media_obj, timeout=3) as resp:
                                            size = int(resp.headers.get('Content-Length', 0))
                                            if size > 9_500_000:
                                                print(f"   🗑 Исключена жирная ссылка: {size/1024/1024:.2f} MB")
                                                continue 
                                    except Exception:
                                        pass 
                                clean_media_list.append(item)
                        if not clean_media_list:
                            stats['errors'] += 1
                            return None 
                        current_content['media'] = clean_media_list
                        await asyncio.sleep(0.5)
                        continue 
                if "message to be replied not found" in err_low:
                    reply_to_mid = None
                    continue 
                elif "chat not found" in err_low or "user not found" in err_low or "blocked" in err_low:
                    raise TelegramForbiddenError(method=e.method, message=e.message)
                elif "flood control" in err_low or "retry after" in err_low:
                    wait_sec = int(re.search(r'\d+', e.message).group()) if re.search(r'\d+', e.message) else 15
                    raise TelegramRetryAfter(method=e.method, message=e.message, retry_after=wait_sec)
                elif "voice_messages_forbidden" in err_low:
                    stats['errors'] += 1
                    return None
                else:
                    print(f"⚠️ BadRequest отправки user {uid}: {e}")
                    stats['errors'] += 1
                    return None
            except TelegramForbiddenError:
                raise 
            except TelegramRetryAfter:
                raise 
            except (aiohttp.ClientConnectorError, TelegramNetworkError, asyncio.TimeoutError):
                raise TelegramRetryAfter(method="network", message="Network Error", retry_after=5)
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientPayloadError) as e:
                stats['ghosts'] += 1
                return None
            except Exception as e:
                stats['errors'] += 1
                return None
        return None

    async def _send_one_guarded(uid: int, timeout_sec: float):
        request_timeout_sec = min(
            DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC,
            max(3.0, timeout_sec - 1.0),
        )
        try:
            return await asyncio.wait_for(
                _send_one(uid, int(request_timeout_sec)),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError as exc:
            runtime_logger.warning(
                "delivery_recipient_timeout %s",
                json.dumps(
                    {
                        "board_id": board_id,
                        "post_num": post_num,
                        "phase": delivery_phase,
                        "uid": uid,
                        "timeout_sec": timeout_sec,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            return exc

    queue = deque(ordered_recipients)
    recipient_retry_counts = defaultdict(int)
    CHUNK_SIZE = DELIVERY_INITIAL_CHUNK_SIZE
    current_delay = 0.1
    phase_budget_sec = _phase_time_budget_sec(delivery_phase)
    phase_deadline = start_time + phase_budget_sec if phase_budget_sec else None
    remaining_recipients_for_later = set()
    interrupted_reason = None
    
    while queue:
        send_timeout_sec = DELIVERY_PER_RECIPIENT_TIMEOUT_SEC
        if phase_deadline is not None:
            remaining_phase_sec = phase_deadline - time.time()
            if remaining_phase_sec <= 0:
                remaining_recipients_for_later.update(queue)
                queue.clear()
                interrupted_reason = "phase_budget"
                break
            if remaining_phase_sec <= DELIVERY_PHASE_GUARD_SEC:
                remaining_recipients_for_later.update(queue)
                queue.clear()
                interrupted_reason = "phase_budget_guard"
                break
            send_timeout_sec = min(
                DELIVERY_PER_RECIPIENT_TIMEOUT_SEC,
                max(1.0, remaining_phase_sec - DELIVERY_PHASE_GUARD_SEC),
            )
        chunk =[]
        for _ in range(min(len(queue), CHUNK_SIZE)):
            chunk.append(queue.popleft())
        tasks = [_send_one_guarded(uid, send_timeout_sec) for uid in chunk]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        flood_wait_seconds = 0
        
        for uid, res in zip(chunk, results):
            if res == "FATAL_ERROR_STOP":
                queue.clear()
                stats['errors'] += len(chunk) + len(queue)
                break 
            if isinstance(res, Exception):
                if isinstance(res, TelegramRetryAfter):
                    wait = res.retry_after
                    recipient_retry_counts[uid] += 1
                    if recipient_retry_counts[uid] <= DELIVERY_MAX_RECIPIENT_RETRIES:
                        flood_wait_seconds = max(flood_wait_seconds, wait)
                        queue.appendleft(uid)
                        stats['retries'] += 1
                    else:
                        stats['errors'] += 1
                        runtime_logger.warning(
                            "delivery_recipient_retry_exhausted %s",
                            json.dumps(
                                {
                                    "board_id": board_id,
                                    "post_num": post_num,
                                    "phase": delivery_phase,
                                    "uid": uid,
                                    "retries": recipient_retry_counts[uid],
                                    "reason": "flood_wait",
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                elif isinstance(res, TelegramForbiddenError):
                    blocked_users.add(uid)
                    stats['blocks'] += 1
                elif isinstance(res, (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError)):
                    if isinstance(res, asyncio.TimeoutError):
                        stats['timeouts'] += 1
                    recipient_retry_counts[uid] += 1
                    if recipient_retry_counts[uid] <= DELIVERY_MAX_RECIPIENT_RETRIES:
                        queue.append(uid)
                        stats['retries'] += 1
                    else:
                        stats['errors'] += 1
                        runtime_logger.warning(
                            "delivery_recipient_retry_exhausted %s",
                            json.dumps(
                                {
                                    "board_id": board_id,
                                    "post_num": post_num,
                                    "phase": delivery_phase,
                                    "uid": uid,
                                    "retries": recipient_retry_counts[uid],
                                    "reason": type(res).__name__,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                else:
                    print(f"❌ Ошибка отправки {uid}: {res}")
                    stats['errors'] += 1
            elif res:
                all_results.append((uid, res))
                
        if flood_wait_seconds > 0:
            wait_real = flood_wait_seconds + 1
            if phase_deadline is not None and time.time() + wait_real + DELIVERY_PHASE_GUARD_SEC >= phase_deadline:
                remaining_recipients_for_later.update(queue)
                queue.clear()
                interrupted_reason = "phase_budget_before_floodwait"
                break
            if verbose:
                print(f"⏳ FloodWait: пауза {wait_real} сек. В очереди: {len(queue)}...")
            await asyncio.sleep(wait_real)
            CHUNK_SIZE = max(DELIVERY_MIN_CHUNK_SIZE, CHUNK_SIZE - 5)
        else:
            await asyncio.sleep(current_delay)
            if CHUNK_SIZE < DELIVERY_INITIAL_CHUNK_SIZE:
                CHUNK_SIZE += 1
                
    time_taken = time.time() - start_time
    post_created_at = post_data_copy.get("timestamp") if post_data_copy else None
    post_age_sec = None
    if isinstance(post_created_at, datetime):
        post_age_sec = max(0.0, time.time() - post_created_at.timestamp())
    elif isinstance(post_created_at, (int, float)):
        post_age_sec = max(0.0, time.time() - float(post_created_at))
    queue_total_sec = None
    if queue_enqueued_at is not None:
        try:
            queue_total_sec = max(0.0, time.time() - float(queue_enqueued_at))
        except (TypeError, ValueError):
            queue_total_sec = None
    if verbose:
        log_line = (
            f"📊 #{post_num} [{delivery_phase}] | "
            f"✅ {stats['success']}/{len(active_recipients)} phase "
            f"({len(active_recipients)}/{original_recipients_count}, def {delivery_deferred_recipients}) | "
            f"🚫 {stats['blocks']} | "
            f"❌ {stats['errors']} | "
            f"👻 {stats['ghosts']} | "
            f"🔄 {stats['retries']} | "
            f"⏲ {stats['timeouts']} | "
            f"⏭ {len(remaining_recipients_for_later)} | "
            f"prio {stats['priority_recipients']}/{len(active_recipients)} | "
            f"⏱ {time_taken:.1f}s"
        )
        print(log_line) 
        delivery_record = {
            "ts": round(time.time(), 3),
            "board_id": board_id,
            "post_num": post_num,
            "phase": delivery_phase,
            "type": str(content.get("type")),
            "recipients": len(active_recipients),
            "phase_recipients": len(active_recipients),
            "original_recipients": original_recipients_count,
            "deferred_recipients": delivery_deferred_recipients,
            "priority_recipients": stats["priority_recipients"],
            "passive_recipients": stats["passive_recipients"],
            "success": stats["success"],
            "blocks": stats["blocks"],
            "errors": stats["errors"],
            "ghosts": stats["ghosts"],
            "retries": stats["retries"],
            "timeouts": stats["timeouts"],
            "budget_deferred": len(remaining_recipients_for_later),
            "interrupted_reason": interrupted_reason,
            "phase_budget_sec": phase_budget_sec,
            "seconds": round(time_taken, 3),
            "post_age_sec": round(post_age_sec, 3) if post_age_sec is not None else None,
            "queue_wait_sec": round(queue_wait_sec, 3) if queue_wait_sec is not None else None,
            "queue_total_sec": round(queue_total_sec, 3) if queue_total_sec is not None else None,
        }
        delivery_metrics[board_id].append(delivery_record)
        runtime_logger.info(
            "delivery_result %s",
            json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
        )
        if time_taken >= DELIVERY_SLOW_PHASE_SEC or (queue_total_sec is not None and queue_total_sec >= DELIVERY_SLOW_PHASE_SEC):
            runtime_logger.warning(
                "delivery_slow %s",
                json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
            )
        if remaining_recipients_for_later:
            runtime_logger.warning(
                "delivery_phase_budget_deferred %s",
                json.dumps(delivery_record, ensure_ascii=False, separators=(",", ":")),
            )
        
    if post_num and post_num not in posts_pending_deletion and not content.get('is_shadow_reject'):
        copies_for_db =[]
        trimmed_copy_posts = 0
        trimmed_copy_refs = 0
        async with storage_lock:
            keep_copy_maps_in_ram = post_num in messages_storage and MAX_COPY_MAP_POSTS_IN_MEMORY > 0
            for uid, msg_obj_or_list in all_results:
                msgs = msg_obj_or_list if isinstance(msg_obj_or_list, list) else [msg_obj_or_list]
                if msgs:
                    msg_ids = [m.message_id for m in msgs]
                    for m in msgs:
                        copies_for_db.append((uid, m.message_id))
                    if keep_copy_maps_in_ram:
                        post_to_messages.setdefault(post_num, {})[uid] = msg_ids[0] if len(msg_ids) == 1 else msg_ids
                        for m in msgs:
                            message_to_post[(uid, m.message_id)] = post_num
            if keep_copy_maps_in_ram:
                trimmed_copy_posts, trimmed_copy_refs = _trim_post_copy_maps_unlocked(MAX_COPY_MAP_POSTS_IN_MEMORY)
        if trimmed_copy_posts:
            runtime_logger.info(
                "copy_map_ram_trim %s",
                json.dumps(
                    {
                        "removed_posts": trimmed_copy_posts,
                        "removed_reverse": trimmed_copy_refs,
                        "limit": MAX_COPY_MAP_POSTS_IN_MEMORY,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        if copies_for_db:
            try:
                await add_post_copies(post_num, copies_for_db)
            except Exception as e:
                if "FOREIGN KEY constraint failed" in str(e):
                    pass
                else:
                    print(f"⚠️ Ошибка сохранения копий для #{post_num}: {e}")
                    
    if blocked_users:
        users_to_remove_db =[]
        for uid in blocked_users:
            if uid in b_data['users']['active']:
                b_data['users']['active'].discard(uid)
                b_data.get('user_settings', {}).pop(uid, None)
                for cache in [b_data['last_activity'], b_data['spam_violations']]:
                    cache.pop(uid, None)
                users_to_remove_db.append(uid)
        
        if users_to_remove_db:
            from common.database import remove_users_from_board_batch
            await remove_users_from_board_batch(users_to_remove_db, board_id)
            
        print(f"🚫 [{board_id}] Удалено {len(blocked_users)} пользователей (блокировка бота).")
        
    return DeliveryResults(
        all_results,
        remaining_recipients=remaining_recipients_for_later,
        interrupted_reason=interrupted_reason,
    )
async def edit_post_for_all_recipients(post_num: int, bot_instance: Bot):
    """
    Находит все отправленные копии поста и редактирует их.
    Основной источник данных - база данных.
    Версия 2.2: Добавлена группировка сообщений по юзерам (защита от мульти-эдита альбомов).
    """
    copies_info = await get_post_copies(post_num)
    user_messages_map = defaultdict(list)
    if copies_info:
        for uid, mid in copies_info:
            user_messages_map[uid].append(mid)
    async with storage_lock:
        ram_copies = post_to_messages.get(post_num, {})
        for uid, mid_or_list in ram_copies.items():
            if isinstance(mid_or_list, list):
                for m in mid_or_list:
                    if m not in user_messages_map[uid]:
                        user_messages_map[uid].append(m)
            else:
                if mid_or_list not in user_messages_map[uid]:
                    user_messages_map[uid].append(mid_or_list)

    if not user_messages_map:
        return

    post_data_copy = {}
    content_copy = {}
    reply_author_id = None
    board_id = None
    async with storage_lock:
        post_data = messages_storage.get(post_num)
        if not post_data: return
        content_type = post_data.get('content', {}).get('type')
        can_be_edited = content_type in ['text', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'media_group']
        if not can_be_edited: return
        post_data_copy = post_data.copy()
        content_copy = post_data.get('content', {}).copy()
        board_id = post_data.get('board_id')
        reply_to_post_num = content_copy.get('reply_to_post')
        if reply_to_post_num:
            reply_author_id = messages_storage.get(reply_to_post_num, {}).get('author_id')
    if not board_id: return
    
    final_keyboard = None
    if content_copy.get('poll_data'):
        poll_options = content_copy.get('poll_data', {}).get('options', [])
        if poll_options:
            buttons = []
            for i, option_text in enumerate(poll_options):
                button_text = option_text[:60]
                buttons.append(
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"poll_vote_{post_num}_{i}"
                    )
                )
            final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
            
    user_specific_texts = {}
    text_or_caption_base = content_copy.get('text') or content_copy.get('caption')
    text_with_you_links = text_or_caption_base
    if text_or_caption_base and ">>" in text_or_caption_base:
        mentioned_authors = {}
        mentions = RE_YOU_PATTERN.findall(text_or_caption_base)
        if mentions:
            async with storage_lock:
                for m_num_str in mentions:
                    try:
                        m_num = int(m_num_str)
                        if m_num in messages_storage:
                            mentioned_authors[m_num] = messages_storage[m_num].get("author_id")
                    except ValueError:
                        continue
        text_with_you_links = add_you_to_my_posts_fast(
            text_or_caption_base, 
            post_data_copy.get('author_id'), 
            mentioned_authors
        )            
    b_data = board_data[board_id]
    users_settings = b_data.get('user_settings', {})
    for user_id in user_messages_map.keys():
        header_text = content_copy.get('header', '')
        u_set = users_settings.get(user_id, {'hide': set()})
        should_hide = False
        if u_set['hide']:
            raw_content_text = content_copy.get('text') or content_copy.get('caption') or ""
            check_text = (header_text + " " + raw_content_text).lower()
            if any(word in check_text for word in u_set['hide']):
                should_hide = True
        head = f"<i>{escape_html(header_text)}</i>"
        if user_id == reply_author_id:
            head = head.replace("Пост", "🔴 Пост").replace("Post", "🔴 Post")
        if should_hide:
            lang_local = 'en' if board_id == 'int' else 'ru'
            placeholder = "🛡 Message hidden" if lang_local == 'en' else "🛡 Сообщение скрыто"
            full_text = f"{head}\n{placeholder}"
        else:
            current_text_or_caption = text_or_caption_base
            if user_id == post_data_copy.get('author_id'):
                current_text_or_caption = text_with_you_links
            content_for_user = content_copy.copy()
            if 'text' in content_for_user: content_for_user['text'] = current_text_or_caption
            elif 'caption' in content_for_user: content_for_user['caption'] = current_text_or_caption
            formatted_body = await _format_message_body(
                content=content_for_user, user_id_for_context=user_id,
                post_data=post_data_copy, reply_to_post_author_id=reply_author_id,
                quote_info=content_for_user.get('quote_info')
            )
            full_text = f"{head}\n\n{formatted_body}" if formatted_body else head
        user_specific_texts[user_id] = full_text

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
                    match = re.search(r'retry after (\d+)', error_message_lower)
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
            task = asyncio.create_task(_edit_one(uid, target_mid))
            tasks_to_run.append(task)

    CHUNK_SIZE = 30 
    DELAY_BETWEEN_CHUNKS = 0.3
    for i in range(0, len(tasks_to_run), CHUNK_SIZE):
        chunk_tasks = tasks_to_run[i:i + CHUNK_SIZE]
        await asyncio.gather(*chunk_tasks, return_exceptions=True)
        if i + CHUNK_SIZE < len(tasks_to_run):
            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
async def execute_delayed_edit(
    post_num: int,
    bot_instance: Bot,
    author_id: int | None,
    notify_text: str | None,
    reply_to_message_id: int | None = None,
    delay: float = 3.0
):
    """
    Ждет задержку, отправляет уведомление (если оно есть) в виде ответа, а затем редактирует пост.
    """
    try:
        await asyncio.sleep(delay)
        if author_id and notify_text:
            try:
                await bot_instance.send_message(
                    author_id,
                    notify_text,
                    reply_to_message_id=reply_to_message_id
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
        await edit_post_for_all_recipients(post_num, bot_instance)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Ошибка в execute_delayed_edit для поста #{post_num}: {e}")
    finally:
        async with pending_edit_lock:
            current_task = asyncio.current_task()
            if pending_edit_tasks.get(post_num) is current_task:
                pending_edit_tasks.pop(post_num, None)
async def message_broadcaster(bots: dict[str, Bot]):

    tasks = [
        asyncio.create_task(message_worker(f"Worker-{board_id}", board_id, bot_instance))
        for board_id, bot_instance in bots.items()
    ]
    await asyncio.gather(*tasks)
async def message_worker(worker_name: str, board_id: str, bot_instance: Bot):
    """
    Воркер обработки очереди сообщений.
    Исправлено: queue.get() вынесен из try-блока, чтобы избежать ошибки task_done() при отмене задачи.
    """
    queue = message_queues[board_id]
    b_data = board_data[board_id]
    while True:
        msg_data = await queue.get()
        try:
            if not msg_data:
                await asyncio.sleep(0.05)
                continue
            if not await validate_message_format(msg_data):
                continue
            post_num = msg_data['post_num']
            if post_num in posts_pending_deletion:
                print(f"[{board_id}] Worker пропустил пост #{post_num}, т.к. он помечен на удаление.")
                continue
            initial_recipients = msg_data['recipients']
            content = msg_data['content']
            content['post_num'] = post_num
            keyboard = msg_data.get('keyboard') 
            thread_id = msg_data.get('thread_id')

            delivery_phase = msg_data.get("delivery_phase", "full")
            if msg_data.get("durable_delivery_id"):
                initial_recipients = await _remove_already_delivered_recipients(post_num, initial_recipients)
                msg_data["recipients"] = initial_recipients
                if not initial_recipients:
                    await _delete_durable_delivery_item(msg_data, "already_delivered")
                    continue
            passive_slice_size = _passive_slice_size_for_content(content, board_id)
            if (
                PRIORITY_SPLIT_FANOUT_ENABLED
                and delivery_phase == "passive"
                and not thread_id
                and PASSIVE_MAX_PREEMPTIONS > 0
                and len(initial_recipients) > passive_slice_size
                and _queue_has_full_message(queue)
            ):
                preemptions = int(msg_data.get("passive_preemptions", 0) or 0)
                if preemptions < PASSIVE_MAX_PREEMPTIONS:
                    msg_data["passive_preemptions"] = preemptions + 1
                    await queue.put(msg_data)
                    runtime_logger.warning(
                        "delivery_passive_preempted %s",
                        json.dumps(
                            {
                                "ts": round(time.time(), 3),
                                "board_id": board_id,
                                "post_num": post_num,
                                "preemptions": msg_data["passive_preemptions"],
                                "max_preemptions": PASSIVE_MAX_PREEMPTIONS,
                                "queue_size": queue.qsize(),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                    continue
            active_recipients = set()
            if thread_id:
                active_recipients = {
                    uid for uid in initial_recipients
                    if uid > 0 and uid not in b_data['users']['banned']
                }
            else:
                user_states = b_data.get('user_state', {})
                recipients_on_main = {
                    uid for uid in initial_recipients
                    if uid > 0 and user_states.get(uid, {}).get('location', 'main') == 'main'
                }
                active_recipients = {uid for uid in recipients_on_main if uid not in b_data['users']['banned']}
            if not active_recipients:
                if msg_data.get("durable_delivery_id"):
                    await _delete_durable_delivery_item(msg_data, "no_active_recipients")
                continue
            try:
                original_recipients_for_post = int(msg_data.get("original_recipients") or len(active_recipients))
            except (TypeError, ValueError):
                original_recipients_for_post = len(active_recipients)
            recipients_to_send = active_recipients
            passive_recipients_for_later = set()
            delivery_phase_for_send = delivery_phase
            deferred_reason = None
            planned_passive_durable_id = None
            if (
                delivery_phase == "full"
                and PRIORITY_SPLIT_FANOUT_ENABLED
                and not thread_id
            ):
                priority_recipients, passive_recipients = _split_recipients_for_delivery(board_id, active_recipients)
                if priority_recipients and len(passive_recipients) >= PRIORITY_SPLIT_MIN_PASSIVE:
                    recipients_to_send = set(priority_recipients)
                    passive_recipients_for_later = set(passive_recipients)
                    delivery_phase_for_send = "priority"
                    deferred_reason = "split_priority_first"
            elif (
                delivery_phase == "passive"
                and PRIORITY_SPLIT_FANOUT_ENABLED
                and not thread_id
                and len(active_recipients) > passive_slice_size
            ):
                ordered_passive = list(active_recipients)
                recipients_to_send = set(ordered_passive[:passive_slice_size])
                passive_recipients_for_later = set(ordered_passive[passive_slice_size:])
                delivery_phase_for_send = "passive_slice"
                deferred_reason = "passive_slice"
            reply_info_copy = {}
            async with storage_lock:
                if post_num in post_to_messages:
                    reply_info_copy = post_to_messages[post_num].copy()
            started_at = time.time()
            enqueued_at = msg_data.get("enqueued_at")
            queue_wait_sec = None
            if enqueued_at is not None:
                try:
                    queue_wait_sec = max(0.0, started_at - float(enqueued_at))
                except (TypeError, ValueError):
                    queue_wait_sec = None
            current_deliveries[board_id] = {
                "post_num": post_num,
                "started_at": started_at,
                "enqueued_at": enqueued_at,
                "queue_wait_sec": round(queue_wait_sec, 3) if queue_wait_sec is not None else None,
                "recipients": len(recipients_to_send),
                "original_recipients": original_recipients_for_post,
                "passive_deferred": len(passive_recipients_for_later),
                "passive_slice_size": passive_slice_size,
                "phase": delivery_phase_for_send,
                "thread_id": thread_id,
            }
            if passive_recipients_for_later and not msg_data.get("durable_delivery_id"):
                planned_passive_item = _build_passive_queue_item(
                    msg_data,
                    passive_recipients_for_later,
                    post_num,
                    original_recipients_for_post,
                    enqueued_at,
                    started_at,
                )
                planned_passive_durable_id = await _persist_durable_delivery_item(
                    board_id,
                    planned_passive_item,
                    "planned_before_send",
                )
            budget_deferred_count = 0
            delivered_now_count = 0
            try:
                delivery_results = await send_message_to_users(
                    bot_instance=bot_instance,
                    board_id=board_id,
                    recipients=recipients_to_send,
                    content=content,
                    reply_info=reply_info_copy,
                    keyboard=keyboard,
                    verbose=True,
                    queue_enqueued_at=enqueued_at,
                    queue_wait_sec=queue_wait_sec,
                    delivery_phase=delivery_phase_for_send,
                    delivery_original_recipients=original_recipients_for_post,
                    delivery_deferred_recipients=len(passive_recipients_for_later),
                )
                delivered_now_count = len(delivery_results)
                budget_deferred = getattr(delivery_results, "remaining_recipients", set())
                if budget_deferred:
                    budget_deferred_count = len(budget_deferred)
                    passive_recipients_for_later.update(budget_deferred)
                    budget_reason = getattr(delivery_results, "interrupted_reason", None) or "phase_budget"
                    deferred_reason = f"{deferred_reason}+{budget_reason}" if deferred_reason else budget_reason
            except Exception:
                if planned_passive_durable_id and passive_recipients_for_later:
                    planned_passive_item["durable_delivery_id"] = planned_passive_durable_id
                    await queue.put(planned_passive_item)
                    runtime_logger.warning(
                        "delivery_durable_requeued_after_send_error %s",
                        json.dumps(
                            {
                                "ts": round(time.time(), 3),
                                "id": planned_passive_durable_id,
                                "board_id": board_id,
                                "post_num": post_num,
                                "deferred": len(passive_recipients_for_later),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                raise
            finally:
                current_delivery = current_deliveries.get(board_id)
                if current_delivery and current_delivery.get("post_num") == post_num:
                    current_deliveries.pop(board_id, None)
            if passive_recipients_for_later:
                passive_item = _build_passive_queue_item(
                    msg_data,
                    passive_recipients_for_later,
                    post_num,
                    original_recipients_for_post,
                    enqueued_at,
                    started_at,
                )
                if planned_passive_durable_id:
                    passive_item["durable_delivery_id"] = planned_passive_durable_id
                await _persist_durable_delivery_item(board_id, passive_item, "deferred_after_send")
                await queue.put(passive_item)
                runtime_logger.info(
                    "delivery_passive_deferred %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "post_num": post_num,
                            "phase": delivery_phase_for_send,
                            "reason": deferred_reason,
                            "requested_now": len(recipients_to_send),
                            "sent_now": delivered_now_count,
                            "deferred": len(passive_recipients_for_later),
                            "budget_deferred": budget_deferred_count,
                            "queue_size": queue.qsize(),
                            "passive_slice_size": passive_slice_size,
                            "content_type": str(content.get("type")),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            elif msg_data.get("durable_delivery_id"):
                await _delete_durable_delivery_item(msg_data, "completed")
        except asyncio.CancelledError:
            break
        except Exception as e:
            if "closed database" in str(e).lower() or is_shutting_down:
                break
            print(f"{worker_name} | ⛔ Критическая ошибка: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(1)
        finally:
            queue.task_done()
async def send_missed_messages(bot: Bot, board_id: str, user_id: int, target_location: str, stream: str = 'ru') -> tuple[bool, bool]:
    """
    Отправляет пользователю пропущенные сообщения. Гарантирует, что ОП-пост
    треда будет показан первым. ОПТИМИЗИРОВАННАЯ ВЕРСИЯ.
    Возвращает кортеж (были ли отправлены сообщения, нужно ли показать кнопку "Вся летопись" - всегда False).
    """
    b_data = board_data[board_id]
    user_s = b_data['user_state'].setdefault(user_id, {})
    missed_post_nums_full = []
    op_post_num = None
    posts_to_send_data = [] # Здесь будем хранить полные данные постов
    async with storage_lock:
        if target_location == 'main':
            last_seen_post = user_s.get('last_seen_main', 0)
            all_main_posts = sorted([
                p_num for p_num, p_data in messages_storage.items() 
                if p_data.get('board_id') == board_id and not p_data.get('thread_id')
            ])
            missed_post_nums_full = [p_num for p_num in all_main_posts if p_num > last_seen_post]
            if len(missed_post_nums_full) > 20:
                missed_post_nums_full = missed_post_nums_full[-20:]
        else: # Загрузка для треда
            thread_id = target_location
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info: return False, False
            all_thread_posts = sorted(thread_info.get('posts', []))
            if all_thread_posts:
                op_post_num = all_thread_posts[0]
            missed_post_nums_full = all_thread_posts
        if not missed_post_nums_full:
            return False, False
        for post_num in missed_post_nums_full:
            post_data = messages_storage.get(post_num)
            if post_data:
                posts_to_send_data.append({
                    'content': post_data.get('content', {}).copy(),
                    'reply_info': post_to_messages.get(post_num, {}).copy()
                })
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if target_location != 'main':
        try:
            if lang == 'en':
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>THREAD LOADED</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            elif lang == 'jp':
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>スレッド読み込み完了</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            else:
                loading_text = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴\n<b>ТРЕД ЗАГРУЖЕН</b>\n🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
            await bot.send_message(user_id, loading_text, parse_mode="HTML")
            await asyncio.sleep(0.5)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    if op_post_num:
        op_post_data = next((p for p in posts_to_send_data if p['content'].get('post_num') == op_post_num), None)
        if op_post_data:
            try:
                await send_message_to_users(bot, board_id, {user_id}, op_post_data['content'], op_post_data['reply_info'])
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки ОП-поста #{op_post_num} юзеру {user_id}: {e}")
    for post_bundle in posts_to_send_data:
        if post_bundle['content'].get('post_num') != op_post_num:
            try:
                await send_message_to_users(bot, board_id, {user_id}, post_bundle['content'], post_bundle['reply_info'])
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки пропущенного сообщения #{post_bundle['content'].get('post_num')} юзеру {user_id}: {e}")
    if lang == 'en':
        final_text = "All new messages loaded."
    elif lang == 'jp':
        final_text = "新着メッセージを読み込みました。"
    else:
        final_text = "Все новые сообщения загружены."
    entry_keyboard = _get_thread_entry_keyboard(board_id, stream=stream)
    try:
        await bot.send_message(user_id, final_text, reply_markup=entry_keyboard, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    if missed_post_nums_full:
        new_last_seen = missed_post_nums_full[-1]
        if target_location == 'main':
            user_s['last_seen_main'] = new_last_seen
        else:
            user_s.setdefault('last_seen_threads', {})[target_location] = new_last_seen
    return True, False
async def board_help_worker(board_id: str):
    """
    Индивидуальный воркер рассылки помощи. 
    Исправлено: message.queues -> message_queues
    """
    await asyncio.sleep(random.randint(10, 300))
    while True:
        try:
            delay = random.randint(10800, 72000)  # от 3 до 20 часов
            await asyncio.sleep(delay)
            activity = await get_board_activity_last_hours(board_id, hours=24)
            if activity < 15: # Если меньше 15 постов за сутки - доска мертва
                print(f"💀 [{board_id}] Доска полудохлая (акт: {activity}), пропускаем рассылку помощи.")
                continue
            b_data = board_data[board_id]
            streams_to_process = ['ru']
            if board_id == 'int':
                streams_to_process = ['en']
            elif ENABLE_MULTILANG:
                streams_to_process = ['ru', 'en', 'jp']
            for stream in streams_to_process:
                if board_id == 'int':
                    recipients = b_data['users']['active'] - b_data['users']['banned']
                else:
                    if ENABLE_MULTILANG:
                        stream_users = await get_stream_active_users(board_id, stream)
                        recipients = stream_users.intersection(b_data['users']['active']) - b_data['users']['banned']
                    else:
                        if stream != 'ru': continue 
                        recipients = b_data['users']['active'] - b_data['users']['banned']
                if not recipients:
                    continue
                message_text = ""
                choice = random.randint(1, 6)
                if stream == 'en':
                    if choice == 1: message_text = random.choice(HELP_TEXT_EN_COMMANDS)
                    elif choice == 2: message_text = generate_boards_list(BOARD_CONFIG, 'en')
                    elif choice == 3: message_text = random.choice(THREAD_PROMO_TEXT_EN)
                    elif choice == 4: message_text = random.choice(MODE_INFO_TEXT_EN)
                    elif choice == 5: message_text = random.choice(CHANNEL_PROMO_TEXT_EN)
                    else: message_text = random.choice(MECHANICS_INFO_TEXT_EN)
                elif stream == 'jp':
                    if choice == 1: message_text = random.choice(HELP_TEXT_JP_COMMANDS)
                    elif choice == 2: message_text = generate_boards_list(BOARD_CONFIG, 'jp')
                    elif choice == 3: message_text = random.choice(THREAD_PROMO_TEXT_JP)
                    elif choice == 4: message_text = random.choice(MODE_INFO_TEXT_JP)
                    elif choice == 5: message_text = random.choice(CHANNEL_PROMO_TEXT_JP)
                    else: message_text = random.choice(MECHANICS_INFO_TEXT_JP)
                else: # ru
                    if choice == 1: message_text = random.choice(HELP_TEXT_COMMANDS)
                    elif choice == 2: message_text = generate_boards_list(BOARD_CONFIG, 'ru')
                    elif choice == 3: message_text = random.choice(THREAD_PROMO_TEXT_RU)
                    elif choice == 4: message_text = random.choice(MODE_INFO_TEXT_RU)
                    elif choice == 5: message_text = random.choice(CHANNEL_PROMO_TEXT_RU)
                    else: message_text = random.choice(MECHANICS_INFO_TEXT_RU)
                now_dt = datetime.now(UTC)
                content = {'type': 'text', 'text': message_text, 'is_system_message': True}
                post_num = await create_post(
                    board_id=board_id, author_id=0, content=content,
                    timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
                )
                if not post_num: continue
                header = await format_header(board_id, post_num, stream=stream)
                content['header'] = header
                await update_post_content(post_num, content)
                async with storage_lock:
                    messages_storage[post_num] = {
                        'author_id': 0, 'timestamp': now_dt,
                        'content': content, 'board_id': board_id
                    }
                await enqueue_board_message(board_id, {
                    'recipients': recipients, 'content': content,
                    'post_num': post_num, 'board_id': board_id
                })
                print(f"✅ [{board_id}] Помощь ({stream}) #{post_num} отправлена в очередь.")
        except asyncio.CancelledError:
            print(f"ℹ️ Воркер помощи для [{board_id}] остановлен.")
            break
        except Exception as e:
            print(f"❌ [{board_id}] Ошибка в board_help_worker: {e}")
            await asyncio.sleep(120)
async def help_broadcaster():
    """
    Менеджер задач. Запускает и управляет независимыми воркерами для рассылки
    помощи на каждую доску, обеспечивая рассинхронизацию.
    """
    await asyncio.sleep(300)  # Общая начальная задержка перед запуском воркеров
    tasks = []
    for board_id in BOARDS:
        if board_id == 'test':
            continue
        task = asyncio.create_task(board_help_worker(board_id))
        tasks.append(task)
    print(f"✅ Менеджер [help_broadcaster] запустил {len(tasks)} независимых воркеров.")
    await asyncio.gather(*tasks)
async def send_welcome_sequence(bot: Bot, chat_id: int, board_id: str, stream: str = 'ru'):
    """
    Отправляет новому пользователю приветственную последовательность
    на выбранном языке (stream).
    """
    lang = stream
    if not ENABLE_MULTILANG:
         lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        primary_message = random.choice(HELP_TEXT_EN_COMMANDS)
    elif lang == 'jp':
        primary_message = random.choice(HELP_TEXT_JP_COMMANDS)
    else:
        primary_message = random.choice(HELP_TEXT_COMMANDS)
    try:
        await bot.send_message(chat_id, primary_message, parse_mode="HTML", disable_web_page_preview=True)
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        print(f"Не удалось отправить приветствие {chat_id}: {e}")
        return
    await asyncio.sleep(1.5)
    secondary_pool = []
    if lang == 'en':
        secondary_pool.extend(THREAD_PROMO_TEXT_EN)
        secondary_pool.extend(MODE_INFO_TEXT_EN)
        secondary_pool.extend(CHANNEL_PROMO_TEXT_EN)
        secondary_pool.extend(MECHANICS_INFO_TEXT_EN)
    elif lang == 'jp':
        secondary_pool.extend(THREAD_PROMO_TEXT_JP)
        secondary_pool.extend(MODE_INFO_TEXT_JP)
        secondary_pool.extend(CHANNEL_PROMO_TEXT_JP)
        secondary_pool.extend(MECHANICS_INFO_TEXT_JP)
    else:
        secondary_pool.extend(THREAD_PROMO_TEXT_RU)
        secondary_pool.extend(MODE_INFO_TEXT_RU)
        secondary_pool.extend(CHANNEL_PROMO_TEXT_RU)
        secondary_pool.extend(MECHANICS_INFO_TEXT_RU)
    secondary_pool.append(generate_boards_list(BOARD_CONFIG, lang))
    if secondary_pool:
        secondary_message = random.choice(secondary_pool)
        try:
            await bot.send_message(chat_id, secondary_message, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass
async def send_active_pin_to_new_user(bot: Bot, user_id: int, board_id: str):
    """
    Проверяет, есть ли на доске активный глобальный закреп.
    Если есть и он СВЕЖИЙ (< 48 часов) — отправляет. Старье не шлем.
    """
    b_data = board_data[board_id]
    pinned_post_num = b_data.get('active_pin')
    if not pinned_post_num:
        return
    post_content = None
    post_timestamp = 0
    async with storage_lock:
        if pinned_post_num in messages_storage:
            post_data = messages_storage[pinned_post_num]
            post_content = post_data.get('content')
            ts = post_data.get('timestamp')
            if isinstance(ts, datetime): post_timestamp = ts.timestamp()
            else: post_timestamp = ts or 0
    if not post_content:
        post_data_db = await get_post_by_num(pinned_post_num)
        if post_data_db:
            post_content = post_data_db.get('content')
            post_timestamp = post_data_db.get('timestamp', 0)
    if not post_content:
        b_data['active_pin'] = None
        return
    if (time.time() - post_timestamp) > 172800:
        return
    await asyncio.sleep(1.5)
    try:
        recipients = {user_id}
        results = await send_message_to_users(
            bot_instance=bot,
            board_id=board_id,
            recipients=recipients,
            content=post_content,
            reply_info=None # Без реплая, так как это чистая копия
        )
        if results and results[0][1]:
            sent_messages = results[0][1]
            msg_to_pin = sent_messages[0] if isinstance(sent_messages, list) else sent_messages
            try:
                await bot.pin_chat_message(
                    chat_id=user_id,
                    message_id=msg_to_pin.message_id,
                    disable_notification=True
                )
            except Exception as e:
                print(f"⚠️ Не удалось закрепить сообщение для нового юзера {user_id}: {e}")
    except Exception as e:
        print(f"❌ Ошибка в send_active_pin_to_new_user: {e}")
@dp.message(Command("getid"))
async def cmd_get_file_id(message: types.Message):
    # Проверяем, есть ли реплай
    if not message.reply_to_message:
        await message.answer("⚠️ Чтобы получить ID, ответь этой командой на гифку, фото или кружок.")
        return
    
    rep = message.reply_to_message
    file_id = None
    file_type = "Неизвестно"

    # Проверяем все возможные типы медиа
    if rep.animation:
        file_id = rep.animation.file_id
        file_type = "Animation (GIF)"
    elif rep.document:
        file_id = rep.document.file_id
        file_type = "Document (File/GIF)"
    elif rep.photo:
        file_id = rep.photo[-1].file_id
        file_type = "Photo"
    elif rep.video:
        file_id = rep.video.file_id
        file_type = "Video"
    elif rep.video_note:
        file_id = rep.video_note.file_id
        file_type = "Video Note (Кружок)"
    elif rep.sticker:
        file_id = rep.sticker.file_id
        file_type = "Sticker"
    elif rep.voice:
        file_id = rep.voice.file_id
        file_type = "Voice"

    if file_id:
        # Enterprise-отклик с готовым кодом для вставки
        response = (
            f"✅ <b>Тип:</b> {file_type}\n"
            f"🆔 <b>FILE_ID:</b>\n<code>{file_id}</code>\n\n"
            f"<i>Скопируй эту строку</i>"
        )
        await message.answer(response, parse_mode="HTML")
    else:
        await message.answer("❌ В этом сообщении нет медиа-файла.")
@dp.message(Command("pin"))
async def cmd_global_pin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Закрепляет сообщение. Сохраняет ID в память и БД, чтобы закреп пережил перезагрузку.
    """
    if not board_id: return
    if not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply with /pin." if lang == 'en' else ("返信で /pin を使ってください。" if lang == 'jp' else "Использование: ответьте командой /pin на сообщение.")
        await message.answer(msg)
        return
    post_num = None
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if post_info: post_num = post_info[0]
    if not post_num:
        err = "Post not found in DB." if lang == 'en' else ("データベースに投稿が見つかりません。" if lang == 'jp' else "Не удалось найти пост в базе.")
        await message.answer(err)
        return
    b_data = board_data[board_id]
    b_data['active_pin'] = post_num
    await update_board_settings(board_id, {'active_pin': post_num})
    copies = await get_post_copies(post_num)
    if lang == 'en':
        status_txt = f"📌 <b>New Pin:</b> Post #{post_num}\nSaved to DB ✅\nPinning for {len(copies)} users..."
    elif lang == 'jp':
        status_txt = f"📌 <b>新しいピン留め:</b> 投稿 #{post_num}\nDBに保存 ✅\n{len(copies)} 人のユーザーにピン留め中..."
    else:
        status_txt = f"📌 <b>Новый закреп:</b> Пост #{post_num}\nСохранено в памяти и БД: ✅\nЗакрепляю у {len(copies)} текущих пользователей..."
    status_msg = await message.answer(status_txt, parse_mode="HTML")
    if not copies:
        return
    count_success = 0
    async def pin_one(uid, mid):
        try:
            await message.bot.pin_chat_message(chat_id=uid, message_id=mid, disable_notification=True)
            return True
        except Exception: return False
    await log_global_event('bot', f"📌 PIN: Админ {message.from_user.id} закрепил пост #{post_num} на /{board_id}/")
    CHUNK_SIZE = 30
    for i in range(0, len(copies), CHUNK_SIZE):
        chunk = copies[i:i + CHUNK_SIZE]
        results = await asyncio.gather(*[pin_one(uid, mid) for uid, mid in chunk])
        count_success += sum(results)
        await asyncio.sleep(1.1)
    if lang == 'en':
        final = f"✅ Post #{post_num} pinned (Success: {count_success})."
    elif lang == 'jp':
        final = f"✅ 投稿 #{post_num} をピン留めしました (成功: {count_success})。"
    else:
        final = f"✅ Пост #{post_num} закреплен (Успешно: {count_success}).\nНовые пользователи тоже увидят его."
    await status_msg.edit_text(final)
@dp.message(Command("wallet", "balance", "money"))
async def cmd_wallet(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    
    from common.db_pool import get_pool, db_lock
    db = await get_pool()
    
    # 1. Проверяем наличие юзера и его статус ГЛОБАЛЬНО
    # last_failed_amount — новая колонка для фиксации суммы "наеба"
    async with db.execute("SELECT SUM(balance), MAX(is_verified_b), MAX(last_failed_amount) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
    
    balance = row[0] if row and row[0] is not None else 0
    is_verified = row[1] if row and row[1] is not None else 0
    last_failed = row[2] if row and len(row) > 2 and row[2] is not None else 0
    
    is_new_wallet = False
    if balance == 0 and is_verified == 0 and last_failed == 0:
        start_bal = float(random.randint(8, 15))
        is_new_wallet = True
        async with db_lock:
            await db.execute(
                "INSERT INTO Users (user_id, board_id, balance, is_verified_b) VALUES (?, ?, ?, 0) "
                "ON CONFLICT(user_id, board_id) DO UPDATE SET balance = ?",
                (user_id, board_id, start_bal, start_bal)
            )
        balance, is_verified = start_bal, 0

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if lang == 'en':
        text = (
            f"💳 <b>TGACH WALLET</b>\n{'—'*22}\n"
            f"👤 <b>Account ID:</b> <code>{user_id}</code>\n"
            f"🔋 <b>Verification:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"💵 <b>Balance:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "📖 <b>Recent transactions:</b>\n"
    else:
        text = (
            f"💳 <b>TGACH WALLET</b>\n{'—'*22}\n"
            f"👤 <b>ID аккаунта:</b> <code>{user_id}</code>\n"
            f"🔋 <b>Уровень:</b> {'<code>[B] Verified</code>' if is_verified else '<code>[A] Limited</code>'}\n"
            f"💵 <b>Баланс:</b> <code>{int(balance)}.00 RUB</code>\n"
        )
        history_header = "📖 <b>Последние операции:</b>\n"

    history_body = f"{'—'*22}\n{history_header}"
    
    if balance > 0 or is_new_wallet:
        if is_new_wallet or balance <= 15:
            history_body += f"🟢 +{int(balance)}.00 ₽ (Emoji Reactions)\n"
            history_body += f"🟡 {int(balance)}.00 ₽ (Available for withdrawal)\n"
        else:
            # Детерминированный бонус на основе ID (чтобы не прыгал при обновлении)
            bonus = (user_id % 5) + 3
            history_body += f"🟢 +{bonus}.00 ₽ (Loyalty Reward)\n"
            history_body += f"🟢 +{int(balance - bonus)}.00 ₽ (Anon Reactions)\n"
            history_body += f"🟡 {int(balance)}.00 ₽ (Available for withdrawal)\n"
    else:
        # КРАСНАЯ ИСТОРИЯ: Используем зафиксированную в БД сумму или небольшой рандом, если еще не выводили
        failed_sum = int(last_failed) if last_failed > 0 else random.randint(20, 70)
        history_body += f"🔴 -{failed_sum}.00 ₽ (Gateway Reject: 115-FZ)\n"
        history_body += f"🔴 -15.00 ₽ (Maintenance Fee)\n"
        history_body += f"⚪️ 0.00 ₽ (Account Liquidated)\n"

    text += history_body

    bot_user = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{user_id}"

    if lang == 'en':
        btns = ["💸 Withdraw", f"🤝 Invite Friend (+50₽)", "📊 Rates", "📜 History"]
    else:
        btns = ["💸 Вывести средства", f"🤝 Пригласить друга (+50₽)", "📊 Курс валют", "📜 История"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btns[0], callback_data="start_withdrawal")],
        [InlineKeyboardButton(text=btns[1], switch_inline_query=f"\nЗаходи в Тгач, тут платят за реакции! Моя ссылка: {ref_link}")],
        [InlineKeyboardButton(text=btns[2], callback_data="scam_rates"), 
         InlineKeyboardButton(text=btns[3], callback_data="scam_history")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")
# --- 1. Начало вывода (Выбор метода) ---
@dp.callback_query(F.data == "start_withdrawal")
async def cb_start_withdrawal(callback: types.CallbackQuery, state: FSMContext, board_id: str | None):
    user_id = callback.from_user.id
    if not board_id: return
    
    from common.db_pool import get_pool
    db = await get_pool()
    
    # ИСПРАВЛЕНО: Теперь считаем SUM(balance) по всем доскам, а не локально
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        balance = row[0] if row and row[0] is not None else 0
    
    if balance < 80:
        await callback.answer(f"❌ Минимальная сумма вывода: 80 RUB (У вас: {int(balance)})", show_alert=True)
        return

    # Клавиатура методов (остается без изменений)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🟢 Sberbank", callback_data="wd_method_sber"), InlineKeyboardButton(text="🟡 Tinkoff", callback_data="wd_method_tinkoff")],[InlineKeyboardButton(text="💠 СБП (По номеру)", callback_data="wd_method_sbp"), InlineKeyboardButton(text="🔵 ВТБ", callback_data="wd_method_vtb")],[InlineKeyboardButton(text="💵 USDT (TRC20)", callback_data="wd_method_usdt"), InlineKeyboardButton(text="🟠 Bitcoin (BTC)", callback_data="wd_method_btc")],[InlineKeyboardButton(text="🔷 Ethereum (ETH)", callback_data="wd_method_eth"), InlineKeyboardButton(text="🟣 Solana (SOL)", callback_data="wd_method_sol")],[InlineKeyboardButton(text="🕵️ Monero (XMR)", callback_data="wd_method_xmr")],[InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")]
    ])
    
    await callback.message.edit_text(
        f"💸 <b>Вывод средств</b>\nДоступно: {int(balance)} RUB\n\n👇 Выберите метод вывода:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(WithdrawalStates.choosing_method)

# --- 2. Запрос реквизитов ---
@dp.callback_query(F.data.startswith("wd_method_"), WithdrawalStates.choosing_method)
async def cb_select_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[2] # sber, usdt, etc.
    await state.update_data(wd_method=method)
    
    method_names = {
        'sber': 'номер карты Сбербанк и Имя получателя', 
        'tinkoff': 'номер карты Тинькофф и Имя получателя', 
        'sbp': 'номер телефона и Имя получателя', 
        'vtb': 'номер карты ВТБ и Имя получателя',
        'usdt': 'адрес кошелька TRC20', 
        'btc': 'адрес BTC', 
        'eth': 'адрес ETH', 
        'sol': 'адрес SOL', 
        'xmr': 'адрес XMR'
    }
    
    req_name = method_names.get(method, 'реквизиты')
    
    await callback.message.edit_text(
        f"✍️ Введите <b>{req_name}</b> для вывода:",
        parse_mode="HTML",
        reply_markup=None 
    )
    await state.set_state(WithdrawalStates.entering_data)
@dp.callback_query(F.data == "scam_rates")
async def cb_scam_rates(callback: types.CallbackQuery):
    res = ["📈 <b>АКТУАЛЬНЫЕ КУРСЫ TGACH PAY</b>\n"]
    res.append("💰 <b>Активность:</b>")
    res.append("🔸 1 Реакция ≈ 8.50 ₽")
    res.append("🔸 1 Сажа ≈ -25.00 ₽")
    res.append("🔸 1 Тред ≈ 150.00 ₽\n")
    res.append("💎 <b>Конвертация (за 100 RUB):</b>")
    
    # Считаем, сколько крипты дают за 1 рубль для Enterprise-вида
    for code, rate in FAKE_CRYPTO_RATES.items():
        crypto_val = 100 / rate
        res.append(f"🔹{code.upper()}: <code>{crypto_val:.10f}</code>")
        
    res.append("\n<i>* Курсы обновляются в реальном времени (Binance API).</i>")
    res.append("<i>* Последняя синхронизация: только что.</i>")
    
    await callback.answer()
    await callback.message.answer("\n".join(res), parse_mode="HTML")

@dp.callback_query(F.data == "scam_history")
async def cb_scam_history(callback: types.CallbackQuery):
    await callback.answer("⚠️ Ошибка: История заархивирована и доступна только в десктопной версии.", show_alert=True)
# --- 3. Обработка введенных данных и ФИНАЛ ---
@dp.message(WithdrawalStates.entering_data)
async def process_withdrawal_data(message: types.Message, state: FSMContext, board_id: str | None):
    if not board_id: return
    user_input = message.text
    user_id = message.from_user.id
    
    # Извлекаем все слова от 2-х букв
    input_words = re.findall(r'[A-Za-zА-Яа-яЁё]{2,}', user_input)
    
    # Список слов, которые нужно выкинуть из имени (банковские термины)
    junk_filter = {'сбербанк', 'сбер', 'тинькофф', 'tinkoff', 'втб', 'vtb', 'карта', 'сбп', 'номер', 'счет', 'счёт', 'банк', 'usdt', 'trc20', 'btc', 'sol', 'eth'}
    
    # Очищаем: оставляем только слова, которых нет в фильтре
    clean_words = [w for w in input_words if w.lower() not in junk_filter]
    
    name_for_public = " ".join(clean_words) if clean_words else "Анонимный долбаёб"
    
    data = await state.get_data()
    method = data.get('wd_method', 'sber')
    
    from common.db_pool import get_pool, db_lock
    db = await get_pool()
    
    async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (user_id,)) as c:
        row = await c.fetchone()
        amount = row[0] if row and row[0] is not None else 0
    
    if amount < 80:
        await message.answer(f"❌ Минимальный вывод: <b>80 RUB</b>\nТвой баланс: {int(amount)} RUB", parse_mode="HTML")
        await state.clear()
        return

    status_msg = await message.answer("⏳ <b>Соединение с шлюзом...</b>", parse_mode="HTML")
    await asyncio.sleep(1.0)
    await status_msg.edit_text("⏳ <b>Проверка реквизитов...</b>", parse_mode="HTML")
    await asyncio.sleep(1.5)
    await status_msg.edit_text("⏳ <b>Формирование транзакции...</b>", parse_mode="HTML")
    await asyncio.sleep(1.5)
    await status_msg.edit_text(f"✅ <b>Заявка #WD-{random.randint(100,999)} принята</b>\nСтатус: <i>В обработке банком</i>\nОриентировочное время: 5-10 минут.", parse_mode="HTML")
    await state.clear()

    async def delayed_prank(amount, user_input, method, shame_name):
        prank_msg = await message.bot.send_message(user_id, "📡 <b>Инициализация платежного шлюза...</b>", parse_mode="HTML")
        sleep_times = [10, 20, 30, 40]
        
        for i, status in enumerate(SCAM_PROCESSING_STATUSES):
            await asyncio.sleep(sleep_times[i] if i < len(sleep_times) else 10)
            bar = PROGRESS_BARS[i] if i < len(PROGRESS_BARS) else ""
            try:
                await prank_msg.edit_text(f"{status}\n\n<code>{bar}</code>", parse_mode="HTML")
            except: break

        await asyncio.sleep(5)

        from common.db_pool import get_pool, db_lock
        db_p = await get_pool()
        async with db_lock:
            await db_p.execute(
                "UPDATE Users SET balance = 0, last_failed_amount = ? WHERE user_id = ?", 
                (amount, user_id)
            )

        uid_raw = str(user_id)
        masked_uid = f"{uid_raw[:3]}***{uid_raw[-3:]}"
        final_user_label = f"{escape_html(shame_name)} (ID: {masked_uid})"
        
        raw_requisites = str(user_input).strip()

        crypto_info = ""
        if method in FAKE_CRYPTO_RATES:
            rate = FAKE_CRYPTO_RATES[method]
            crypto_amount = float(amount) / rate
            crypto_info = f"(~{crypto_amount:.8f} {method.upper()})"

        method_name = METHOD_LABELS.get(method, method.upper())

        scenarios = WITHDRAWAL_SCENARIOS.get(method, WITHDRAWAL_SCENARIOS['sber'])
        template = random.choice(scenarios)
        direct_notice = template.format(
            amount=int(amount), 
            input_data=user_input, 
            uuid=str(uuid.uuid4())[:8].upper(), 
            date=datetime.now(UTC).strftime("%H:%M")
        )
        
        kb_support = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🆘 Оспорить в техподдержке", callback_data="support_prank")]])
        
        try:
            await prank_msg.delete()
        except: pass
        
        await message.bot.send_message(user_id, direct_notice, parse_mode="HTML", reply_markup=kb_support)
        
        public_shame_template = random.choice(PUBLIC_SHAME_MESSAGES)
        shame_text = public_shame_template.format(
            masked_user=final_user_label, 
            amount=int(amount), 
            method_name=method_name, 
            masked_data=raw_requisites,
            crypto_info=crypto_info
        )
        await process_new_post(message.bot, board_id, 0, {'type': 'text', 'text': shame_text, 'is_system_message': True}, None, False)

    asyncio.create_task(delayed_prank(amount, user_input, method, name_for_public))
@dp.callback_query(F.data == "support_prank")
async def cb_support_prank(callback: types.CallbackQuery):
    try:
        # Пытаемся отправить гифку. Если ID неверный - отправим текст.
        await callback.message.answer_animation(
            animation=SUPPORT_RESPONSES['gif_id'],
            caption=SUPPORT_RESPONSES['text'],
            parse_mode="HTML"
        )
    except:
        await callback.message.answer(SUPPORT_RESPONSES['text'], parse_mode="HTML")
    await callback.answer()
@dp.message(Command("passport", "me", "profile", "stats_me"))
async def cmd_passport(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Генерирует 'Паспорт Анона'. Полная локализация.
    Адаптировано под безопасную работу с БД (db_lock).
    """
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    user_id = message.from_user.id
    
    # Импортируем пул и лок
    from common.db_pool import get_pool, db_lock
    
    post_count = 0
    balance = 0
    is_verified = 0
    try:
        async with db_lock:
            db = await get_pool()
            # Берем ГЛОБАЛЬНЫЙ баланс и статус (сумма по всем доскам)
            query = "SELECT SUM(balance), MAX(is_verified_b) FROM Users WHERE user_id = ?"
            async with db.execute(query, (user_id,)) as cursor:
                row = await cursor.fetchone()
                balance = row[0] if row and row[0] is not None else 0
                is_verified = row[1] if row and row[1] is not None else 0
            
            # Считаем ГЛОБАЛЬНОЕ количество постов (во всем боте)
            query_cnt = "SELECT COUNT(*) FROM Posts WHERE author_id = ?"
            async with db.execute(query_cnt, (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row: post_count = row[0]
    except Exception as e:
        print(f"Ошибка получения статистики: {e}")
        return
    rank = ""
    role = ""
    if lang == 'en':
        if post_count == 0: rank, role = "👻 Read-only", "Random Guy"
        elif post_count < 10: rank, role = "💩 Newfag", "Normie"
        elif post_count < 50: rank, role = "🤡 Attention Whore", "Shitposter"
        elif post_count < 150: rank, role = "👺 Troll", "+15 cents"
        elif post_count < 300: rank, role = "🐸 Average /b/tard", "Wojak"
        elif post_count < 666: rank, role = "☣️ Toxic", "Copypasta Gen"
        elif post_count < 1000: rank, role = "🧙‍♂️ Wizard (30 y.o. virgin)", "Incel"
        elif post_count < 2000: rank, role = "🦍 Boomer", "Sofa Warrior"
        elif post_count < 5000: rank, role = "🔥 Living Legend", "Oldfag"
        elif post_count < 8000: rank, role = "🔥 Insane", "Schizo"
        elif post_count < 10000: rank, role = "🔥 Holy Anon", "Elite"
        else: rank, role = "👁️ Son of Abu", "God of Shit"
    elif lang == 'jp':
        if post_count == 0: rank, role = "👻 ROM専", "名無しさん"
        elif post_count < 10: rank, role = "💩 新参", "一般人"
        elif post_count < 50: rank, role = "🤡 かまってちゃん", "厨房"
        elif post_count < 150: rank, role = "👺 荒らし", "工作員"
        elif post_count < 300: rank, role = "🐸 暇人", "自宅警備員"
        elif post_count < 666: rank, role = "☣️ 毒男", "コピペ職人"
        elif post_count < 1000: rank, role = "🧙‍♂️ 魔法使い (童貞30歳)", "喪男"
        elif post_count < 2000: rank, role = "🦍 老害", "ネット弁慶"
        elif post_count < 5000: rank, role = "🔥 生ける伝説", "古参"
        elif post_count < 8000: rank, role = "🔥 狂人", "糖質"
        elif post_count < 10000: rank, role = "🔥 神コテ", "エリート"
        else: rank, role = "👁️ 管理人の息子", "クソの神"
    else: # ru
        if post_count == 0: rank, role = "👻 Ридонли", "Хуй с горы - Обезьяна на бревне"
        elif post_count < 10: rank, role = "💩 Рачье", "Ньюфажина"
        elif post_count < 50: rank, role = "🤡 Вниманиеблядь", "Поехавший"
        elif post_count < 150: rank, role = "👺 Лахтадырка","Педофил"
        elif post_count < 200: rank, role = "🐸 Битард обыкновенный", "Анон"
        elif post_count < 400: rank, role = "☣️ Проткнутый пидоран", "Транссексуал"
        elif post_count < 600: rank, role = "🧙‍♂️ Волшебник (30 лет без секса)", "Девственник"
        elif post_count < 800: rank, role = "🦍 Скуф", "Проткнутый"
        elif post_count < 1000: rank, role = "🔥 Живое воплощение Йобы", "Легенда"
        elif post_count < 1500: rank, role = "🔥 Сумасшедший", "Сбежавший из дурки"
        elif post_count < 1800: rank, role = "🔥 Легенда двача", "Старожил"
        elif post_count < 2000: rank, role = "🔥 Живая легенда", "Старожил"
        elif post_count < 2500: rank, role = "🔥 Говноед", "Психически больной"
        elif post_count < 3000: rank, role = "🔥 Пресвятой Анон", "Легендарный Анонимус"
        else: rank, role = "👁️ Сын Абу", "Бог говна"
    data_ru = {
        'mental': ["Вялотекущая шизофрения", "Педераст", "Газонюх", "Терминальная стадия двачевания", "ПТСР после /po/", "Синдром Туретта", "Одержимость трапами", "Асексуал (насильно)", "Зумер с деменцией", "Свидетель Вайпа", "Жертва психиатрии", "Пиздабол", "Мамкин анархист", "Солевой", "Овощ", "Гигачад (нет)"],
        'inv': ["Справка из дурки", "Трусы с чиркашом", "Банка 'Ягуара'", "Диск с ЦП", "Онахол", "Дакимакура", "Вентилятор", "Флешка с ЦП", "Диплом шараги", "Усы Сталина", "Резиновая вагина (б/у)", "Пакет с пакетами", "Мать (продана)", "Шприц", "Носок (стоячий)", "Тетрадь смерти", "ЕОТ (в мечтах)", "Биткоин (нарисованный)", "15 рублей", "Вейп", "Повестка"],
        'sec': ["Дрочит на фурри", "Любитель лоликона", "Стучит товарищу майору", "Любит унижения", "Мечтает стать модером", "Смотрит цп", "Не мылся год", "Не девственник (врет)", "Боится женщин", "Ест кал", "Хочет в Польшу", "Верит в плоскую землю", "Украл у мамки деньги", "Плачет после секса"]
    }
    data_en = {
        'mental': ["Chronic Schizophrenia", "Terminal 4chan addiction", "PTSD after /pol/", "Tourette's", "Trap obsession", "Incel (forced)", "Dementia Zoomer", "Wipe Witness", "Psych ward victim", "Pathological liar", "Basement anarchist", "Meth head", "Vegetable", "Gigachad (not)"],
        'inv': ["Autism certificate", "Stained underwear", "Monster Energy", "Fan (for shit)", "CP Flash drive (fake)", "College debt", "Hitler's moustache", "Used waifu pillow", "Bag of bags", "Sold mom", "Syringe", "Cum sock (stiff)", "Death Note", "GF (imaginary)", "Bitcoin (drawn)", "0.01$", "Vape", "Draft notice"],
        'sec': ["Jerks to furries", "Snitch for FBI", "Loves humiliation", "Wants to be janny", "Watches loli", "Hasn't showered in 2024", "Fake virgin", "Scared of women", "Eats bugs", "Wants to go to Brazil", "Flat earther", "Stole mom's credit card", "Cries while pooping"]
    }
    data_jp = {
        'mental': ["統合失調症", "2ch中毒末期", "政治厨PTSD", "トゥレット症候群", "男の娘中毒", "非モテ（強制）", "認知症ズーマー", "祭り目撃者", "精神科の犠牲者", "虚言癖", "ママのアナキスト", "ヤク中", "植物人間", "ギガチャド（嘘）"],
        'inv': ["障害者手帳", "シミ付きパンツ", "ストロングゼロ", "扇風機（クソ用）", "ロリ画像USB", "Fラン大学の学位", "スターリンの髭", "中古オナホ", "レジ袋の山", "売られた母", "注射器", "カチカチの靴下", "デスノート", "脳内彼女", "ビットコイン（絵）", "15ルーブル", "Vape", "赤紙"],
        'sec': ["ケモナー", "警察の犬", "ドM", "削除人になりたい", "ロリコン", "1年風呂入ってない", "童貞（嘘）", "女性恐怖症", "食糞", "異世界に行きたい", "地球平面説信者", "親の金盗んだ", "うんこ中に泣く"]
    }
    if lang == 'en': current_data = data_en
    elif lang == 'jp': current_data = data_jp
    else: current_data = data_ru
    seed_val = f"{user_id}_{datetime.now(UTC).date()}"
    rng = random.Random(seed_val)
    social_credit = rng.randint(-1488, 1337)
    if social_credit < -500: sc_emoji = "👎"
    elif social_credit > 500: sc_emoji = "🇨🇳"
    else: sc_emoji = "📉"
    state_val = rng.choice(current_data['mental'])
    inv_val = rng.choice(current_data['inv'])
    secret_val = rng.choice(current_data['sec'])
    flag = "🏴‍☠️"
    if board_id == 'po': flag = "🤡"
    elif board_id == 'int': flag = "🏳️‍🌈"
    elif board_id == 'sex': flag = "🍆"
    if lang == 'en':
        labels = ["TGACH PASSPORT", "ID", "Rank", "Role", "Posts", "Diagnosis", "Inventory", "Kompromat", "Social Credit"]
    elif lang == 'jp':
        labels = ["TGちゃんパスポート", "ID", "ランク", "役割", "レス数", "診断", "持ち物", "秘密", "社会的信用"]
    else:
        labels = ["ПАСПОРТ ТГАЧЕРА", "ID", "Ранг", "Роль", "Постов", "Диагноз", "Инвентарь", "Компромат", "Соц. рейтинг"]
    passport_text = (
        f"🪪 <b>{labels[0]} {flag}</b>\n"
        f"<code>{'—'*22}</code>\n"
        f"🆔 <b>{labels[1]}:</b> <code>**********</code>\n"
        f"🏷 <b>{labels[2]}:</b> {rank}\n"
        f"💼 <b>{labels[3]}:</b> {role}\n"
        f"💩 <b>{labels[4]}:</b> {post_count}\n"
        f"💸 <b>Баланс:</b> {int(balance)} RUB ({'Verified B' if is_verified else 'Limited A'})\n"
        f"<code>{'—'*22}</code>\n"
        f"🧠 <b>{labels[5]}:</b> <i>{state_val}</i>\n"
        f"🎒 <b>{labels[6]}:</b> <i>{inv_val}</i>\n"
        f"🕵️ <b>{labels[7]}:</b> <tg-spoiler>{secret_val}</tg-spoiler>\n"
        f"{sc_emoji} <b>{labels[8]}:</b> {social_credit}\n"
        f"<code>{'—'*22}</code>\n"
    )
    try:
        await message.reply(passport_text, parse_mode="HTML")
    except:
        try:
            await message.answer(passport_text, parse_mode="HTML")
        except Exception:
            pass
    try: await message.delete()
    except: pass
@dp.message(Command("ans"))
async def cmd_admin_answer(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет системный ответ на пост пользователя.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        err = "Use as reply." if lang == 'en' else ("返信として使用してください。" if lang == 'jp' else "Используйте ответом на сообщение юзера.")
        await message.answer(err)
        return
    raw_html = message.html_text
    answer_text = ""
    if raw_html.startswith("/ans"):
        answer_text = raw_html[4:].strip()
    else:
        answer_text = raw_html.strip()
    if not answer_text:
        err = "Enter answer text." if lang == 'en' else ("回答を入力してください。" if lang == 'jp' else "Введите текст ответа.")
        await message.answer(err)
        return
    target_post_num = None
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        target_post_num = message_to_post.get(key)
    if not target_post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: target_post_num = info[0]
    if not target_post_num:
        await message.answer("Post not found.")
        return
    target_author_id = None
    post_data = messages_storage.get(target_post_num)
    if post_data:
        target_author_id = post_data.get('author_id')
    if not target_author_id:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: target_author_id = info[1]
    now_dt = datetime.now(UTC)
    content = {
        'type': 'text',
        'text': answer_text,
        'is_system_message': True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream,
        reply_to=target_post_num 
    )
    if pnum:
        header = await format_header(board_id, pnum, 0)
        if lang == 'en': prefix = "### ADMIN ###"
        elif lang == 'jp': prefix = "### 管理人 ###"
        else: prefix = "### АДМИН ###"
        content['header'] = f"{prefix}\n{header}"
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 'timestamp': now_dt, 
                'content': content, 'board_id': board_id
            }
        b_data = board_data[board_id]
        reply_info_for_send = {}
        if target_author_id:
             user_copy = post_to_messages.get(target_post_num, {}).get(target_author_id)
             if user_copy:
                 mid = user_copy[0] if isinstance(user_copy, list) else user_copy
                 reply_info_for_send[target_author_id] = mid
        await enqueue_board_message(board_id, {
            "recipients": b_data['users']['active'],
            "content": content,
            "post_num": pnum,
            "board_id": board_id,
            "reply_info": reply_info_for_send
        })
        try: await message.delete()
        except: pass
@dp.message(Command("gunban"))
async def cmd_gunban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Снимает БАН и ТЕНЕВОЙ МУТ с пользователя СРАЗУ НА ВСЕХ досках.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID/Reply needed." if lang != 'ru' else "Нужен ID или реплай.")
        return
    if lang == 'en': msg = f"🕊️ Global Amnesty for <code>{target_id}</code>..."
    elif lang == 'jp': msg = f"🕊️ <code>{target_id}</code> へのグローバル恩赦..."
    else: msg = f"🕊️ Глобальная амнистия для <code>{target_id}</code>..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    count = 0
    for b_id in BOARDS:
        try:
            unbanned = False
            async with storage_lock:
                b_data_local = board_data[b_id]
                if target_id in b_data_local['users']['banned']:
                    b_data_local['users']['banned'].discard(target_id)
                    b_data_local['users']['active'].add(target_id)
                    unbanned = True
                if target_id in b_data_local['shadow_mutes']:
                    del b_data_local['shadow_mutes'][target_id]
                    unbanned = True
            if unbanned:
                await add_or_activate_user(target_id, b_id)
                await update_shadow_mute(target_id, b_id, 0)
                count += 1
        except Exception: pass
    await log_global_event('bot', f"🕊️ GUNBAN: Админ {message.from_user.id} ГЛОБАЛЬНО РАЗБАНИЛ {target_id} на {count} досках")
    if lang == 'en': final = f"✅ User <code>{target_id}</code> unbanned/unmuted on {count} boards."
    elif lang == 'jp': final = f"✅ ユーザー <code>{target_id}</code> を {count} 個の板でBAN/ミュート解除しました。"
    else: final = f"✅ Пользователь <code>{target_id}</code> разбанен/размучен на {count} досках."
    await status_msg.edit_text(final, parse_mode="HTML")
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Открывает быстрое меню по команде /menu.
    """
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "👇 <b>Quick Menu:</b>"
    elif lang == 'jp':
        text = "👇 <b>クイックメニュー:</b>"
    else:
        text = "👇 <b>Быстрое меню:</b>"
    await message.answer(
        text, 
        reply_markup=get_quick_menu_keyboard(board_id, stream=stream), 
        parse_mode="HTML"
    )
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("whois", "info"))
async def cmd_whois(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID needed." if lang == 'en' else "Нужен ID.")
        return
    if lang == 'en': header = f"🗂 <b>Dossier on {target_id}:</b>"
    elif lang == 'jp': header = f"🗂 <b>{target_id} の調査書:</b>"
    else: header = f"🗂 <b>Досье на {target_id}:</b>"
    report = [header]
    total_activity = False
    for b_id in BOARDS:
        b_data = board_data[b_id]
        status = []
        if target_id in b_data['users']['banned']:
            status.append("🚫 BAN")
        elif target_id in b_data['users']['active']:
            status.append("✅ Active")
        if b_data['mutes'].get(target_id, datetime.min.replace(tzinfo=UTC)) > datetime.now(UTC):
            status.append("🔇 Mute")
        if b_data['shadow_mutes'].get(target_id, datetime.min.replace(tzinfo=UTC)) > datetime.now(UTC):
            status.append("👻 Shadow")
        u_set = b_data.get('user_settings', {}).get(target_id, {})
        if u_set.get('shadow_gif'): status.append("NoGIF")
        if u_set.get('shadow_sticker'): status.append("NoSticker")
        if u_set.get('lie_media'): status.append("LieMedia")
        if status:
            total_activity = True
            board_name = BOARD_CONFIG[b_id]['name']
            report.append(f"<b>{board_name}</b>: {', '.join(status)}")
    if not total_activity:
        if lang == 'en': report.append("<i>No info (not active on any board).</i>")
        elif lang == 'jp': report.append("<i>情報なし（どの板でも活動していません）。</i>")
        else: report.append("<i>Информации нет (не активен ни на одной доске).</i>")
    await message.answer("\n".join(report), parse_mode="HTML")
@dp.message(Command("unpin"))
async def cmd_global_unpin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Снимает закреп и удаляет его из памяти/БД.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    old_pin = b_data.get('active_pin')
    b_data['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    target_post_num = None
    if message.reply_to_message:
        async with storage_lock:
            key = (message.chat.id, message.reply_to_message.message_id)
            target_post_num = message_to_post.get(key)
            if not target_post_num:
                 post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
                 if post_info: target_post_num = post_info[0]
    else:
        target_post_num = old_pin
    if not target_post_num:
        msg = "✅ Pin reset in DB. No active post found to unpin." if lang == 'en' else ("✅ DBのピン留めをリセットしました。解除する投稿が見つかりません。" if lang == 'jp' else "✅ Закреп сброшен в БД. Активных постов для открепления не найдено.")
        await message.answer(msg)
        return
    msg_start = f"❌ Unpinning post #{target_post_num}..." if lang == 'en' else (f"❌ 投稿 #{target_post_num} のピン留めを解除中..." if lang == 'jp' else f"❌ Снимаю закреп поста #{target_post_num}...")
    status_msg = await message.answer(msg_start)
    copies = await get_post_copies(target_post_num)
    if copies:
        async def unpin_one(uid, mid):
            try:
                await message.bot.unpin_chat_message(chat_id=uid, message_id=mid)
                return True
            except Exception: return False
        CHUNK_SIZE = 40
        count = 0
        for i in range(0, len(copies), CHUNK_SIZE):
            chunk = copies[i:i + CHUNK_SIZE]
            res = await asyncio.gather(*[unpin_one(uid, mid) for uid, mid in chunk])
            count += sum(res)
            await asyncio.sleep(1.0)
        await log_global_event('bot', f"📍 UNPIN: Админ {message.from_user.id} снял закреп поста #{target_post_num} на /{board_id}/")
        if lang == 'en': final = f"✅ Post #{target_post_num} unpinned for {count} users."
        elif lang == 'jp': final = f"✅ 投稿 #{target_post_num} のピン留めを {count} 人のユーザーから解除しました。"
        else: final = f"✅ Пост #{target_post_num} откреплен у {count} юзеров. Из памяти удален."
        await status_msg.edit_text(final)
    else:
        if lang == 'en': final = f"✅ Post #{target_post_num} removed from pin settings."
        elif lang == 'jp': final = f"✅ 投稿 #{target_post_num} をピン留め設定から削除しました。"
        else: final = f"✅ Пост #{target_post_num} удален из настроек закрепа."
        await status_msg.edit_text(final)
async def motivation_broadcaster():

    await asyncio.sleep(15)  # Начальная задержка
    async def board_motivation_worker(board_id: str):

        while True:
            try:
                delay = random.randint(6000, 18000)
                await asyncio.sleep(delay)
                activity = await get_board_activity_last_hours(board_id, hours=2)
                if activity < 20:
                    continue
                b_data = board_data[board_id]
                streams_to_process = ['ru'] # По дефолту
                if board_id == 'int':
                    streams_to_process = ['en']
                elif ENABLE_MULTILANG:
                    streams_to_process = ['ru', 'en', 'jp']
                for stream in streams_to_process:
                    if board_id == 'int':
                        recipients = b_data['users']['active'] - b_data['users']['banned']
                    else:
                        if ENABLE_MULTILANG:
                            stream_users = await get_stream_active_users(board_id, stream)
                            recipients = stream_users.intersection(b_data['users']['active']) - b_data['users']['banned']
                        else:
                            recipients = b_data['users']['active'] - b_data['users']['banned']
                    if not recipients:
                        continue

                    # 35% шанс на рекламу сайта (с новыми текстами), 65% на рекламу бота
                    is_site_promo = random.random() < 0.35
                    
                    if is_site_promo:
                        site_url = f"https://tgach.top/{board_id}/"
                        # ИСПОЛЬЗУЕМ НОВЫЕ ФРАЗЫ ИЗ text_assets.py
                        if stream == 'en':
                            text_body = random.choice(SITE_PROMO_PHRASES_EN)
                            btn_text = "🔗 Open Website"
                        elif stream == 'jp':
                            text_body = random.choice(SITE_PROMO_PHRASES_JP)
                            btn_text = "🔗 サイトを開く"
                        else:
                            text_body = random.choice(SITE_PROMO_PHRASES)
                            btn_text = "🔗 Перетий на сайт"
                        
                        # Формируем сообщение с кнопкой
                        message_text = f"{text_body}\n\n👉 <a href='{site_url}'>{site_url}</a>"
                        
                        # Для сайта можно добавить Inline кнопку
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=btn_text, url=site_url)]
                        ])
                    else:
                        # Старая логика (реклама бота/инвайта)
                        if stream == 'en':
                            motivation = random.choice(MOTIVATIONAL_MESSAGES_EN)
                            invite_text = random.choice(INVITE_TEXTS_EN)
                            copy_lbl = "Copy and send to anons:"
                        elif stream == 'jp':
                            motivation = random.choice(MOTIVATIONAL_MESSAGES_JP)
                            invite_text = random.choice(INVITE_TEXTS_JP)
                            copy_lbl = "コピーしてアノンに送信:"
                        else:
                            motivation = random.choice(MOTIVATIONAL_MESSAGES)
                            invite_text = random.choice(INVITE_TEXTS)
                            copy_lbl = "Скопируй и отправь анончикам:"
                        
                        message_text = (
                            f"💭 {motivation}\n\n"
                            f"{copy_lbl}\n"
                            f"<code>{escape_html(invite_text)}</code>"
                        )
                        keyboard = None

                    now_dt = datetime.now(UTC)
                    content = {'type': 'text', 'text': message_text, 'is_system_message': True}
                    
                    post_num = await create_post(
                        board_id=board_id, author_id=0, content=content,
                        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
                    )
                    
                    if not post_num: continue
                    
                    header = await format_header(board_id, post_num)
                    if board_id != 'int': header = f"### АДМИН ###\n{header}"
                    content['header'] = header
                    
                    await update_post_content(post_num, content)
                    async with storage_lock:
                        messages_storage[post_num] = {
                            'author_id': 0, 'timestamp': now_dt,
                            'content': content, 'board_id': board_id
                        }
                    
                    # Передаем keyboard в очередь
                    await enqueue_board_message(board_id, {
                        'recipients': recipients, 
                        'content': content,
                        'post_num': post_num, 
                        'board_id': board_id,
                        'keyboard': keyboard 
                    })

            except Exception as e:
                print(f"❌ [{board_id}] Ошибка в motivation_broadcaster: {e}")
                await asyncio.sleep(120)
    tasks = [asyncio.create_task(board_motivation_worker(bid)) for bid in BOARDS if bid != 'test']
    await asyncio.gather(*tasks)
async def validate_message_format(msg_data: dict) -> bool:

    if not isinstance(msg_data, dict):
        return False
    required = ['recipients', 'content', 'post_num']
    if any(key not in msg_data for key in required):
        return False
    if not isinstance(msg_data['recipients'], (set, list)):
        return False
    if not isinstance(msg_data['content'], dict):
        return False
    if (msg_data['content'].get('type') == 'media_group' and 
        not isinstance(msg_data['content'].get('media'), list)):
        return False
    return True
async def save_threads_data(board_id: str):

    if board_id not in THREAD_BOARDS:
        return
    async with storage_lock:
        original_data = board_data[board_id].get('threads_data', {})
        data_to_save = {}
        for thread_id, thread_info in original_data.items():
            serializable_info = thread_info.copy()
            if 'subscribers' in serializable_info and isinstance(serializable_info['subscribers'], set):
                serializable_info['subscribers'] = list(serializable_info['subscribers'])
            data_to_save[thread_id] = serializable_info
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        save_executor,
        _sync_save_threads_data,
        board_id,
        data_to_save
    )
async def fetch_dvach_thread(board: str, only_new: bool = False):

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f'https://2ch.hk/{board}/catalog.json') as response:
                if response.status != 200:
                    return None
                data = await response.json()
                if not data or 'threads' not in data:
                    return None
                threads = data['threads']
                if not threads:
                    return None
                if only_new and board == 'news':
                    threads.sort(key=lambda x: x.get('timestamp', 0),
                                 reverse=True)
                    threads = threads[:10]
                thread = random.choice(threads)
                thread_num = thread.get('num')
                if not thread_num:
                    return None
                async with session.get(
                        f'https://2ch.hk/{board}/res/{thread_num}.json'
                ) as thread_response:
                    if thread_response.status != 200:
                        return None
                    thread_data = await thread_response.json()
                    if not thread_data or 'threads' not in thread_data:
                        return None
                    posts = thread_data['threads'][0]['posts']
                    if not posts:
                        return None
                    op_post = posts[0]
                    text = op_post.get('comment', '')
                    text = re.sub(r'<[^>]+>', '', text)
                    text = text.replace('&gt;', '>')
                    text = text.replace('&lt;', '<')
                    text = text.replace('&amp;', '&')
                    text = text.replace('&quot;', '"')
                    text = text.replace('&#47;', '/')
                    text = text.replace('<br>', '\n')
                    if len(text) > 500:
                        text = text[:500] + '...'
                    link = f"https://2ch.hk/{board}/res/{thread_num}.html"
                    if board == 'news' or random.random() > 0.5:
                        result = f"Тред с /{board}/:\n\n"
                        result += f"{text}\n\n"
                        result += link
                    else:
                        comment = random.choice(THREAD_COMMENTS)
                        result = f"{link}\n\n{comment}"
                        if text and random.random() > 0.3:
                            result = f"{text}\n\n{link}\n\n{comment}"
                    return result
    except Exception as e:
        print(f"Ошибка получения треда с /{board}/: {e}")
        return None
async def format_thread_for_telegram(op_post: dict, replies: list[dict]) -> list[str]:
    if not op_post: return []
    op_title = clean_html_tags(op_post['content'].get('text', ''))
    op_media = "\n[изображение]" if op_post['content'].get('type') != 'text' else ""
    parts = [f"<b>Тред #{op_post['id']}: {escape_html(op_title)}</b>{op_media}\n\n"]
    total_posts = len(replies) + 1
    for i, reply in enumerate(replies):
        header = f"Пост #{reply['id']}, {format_timestamp(reply['timestamp'])}, {i + 2}/{total_posts}"
        reply_to = f">>{reply['reply_to_post_num']}\n" if reply['reply_to_post_num'] else ""
        media = "[изображение]\n" if reply['content'].get('type') != 'text' else ""
        text = escape_html(clean_html_tags(reply['content'].get('text', '')))
        parts.append(f"<i>{header}</i>\n{reply_to}{media}{text}\n\n")
    parts.append("\n\n<i>(Этот тред открыт в режиме только для чтения)</i>")
    full_text = "".join(parts)
    return split_text(full_text, 4096)
def format_timestamp(ts: float) -> str:

    try:
        return datetime.fromtimestamp(ts, tz=UTC).strftime('%d.%m.%y %H:%M')
    except (ValueError, TypeError):
        return ""
async def dvach_thread_poster():
    """
    Периодически постит случайный тред с 2ch как ПОЛНОЦЕННЫЙ ТРЕД.
    """
    await asyncio.sleep(300) 
    SOURCE_BOARDS = ['b', 'po', 'a', 'sex', 'vg', 'news']
    while True:
        try:
            delay = random.randint(7200, 18000)
            await asyncio.sleep(delay)
            destination_board_id = random.choice([b_id for b_id in BOARDS if b_id not in ['test']])
            activity = await get_board_activity_last_hours(destination_board_id, hours=24)
            if activity < 2: continue 
            b_data = board_data[destination_board_id]
            recipients = b_data['users']['active'] - b_data['users']['banned']
            if not recipients: continue
            thread_text = await fetch_dvach_thread(random.choice(SOURCE_BOARDS))
            if not thread_text: continue
            now_dt = datetime.now(UTC)
            thread_id = secrets.token_hex(4)
            clean_text = clean_html_tags(thread_text)
            title = (clean_text.split('\n')[0][:50] + '...') if clean_text else "Тред с 2ch"
            await create_thread(
                thread_id=thread_id,
                board_id=destination_board_id,
                op_id=0, # Системный
                title=title,
                created_at=now_dt.timestamp(),
                stream='ru'
            )
            if destination_board_id in THREAD_BOARDS:
                b_data.setdefault('threads_data', {})[thread_id] = {
                    'op_id': 0, 'title': title, 'created_at': now_dt.isoformat(),
                    'last_activity_at': now_dt.timestamp(), 'posts': [], 
                    'subscribers': set(), 'is_archived': False, 'stream': 'ru'
                }
            content = {
                'type': 'text',
                'text': thread_text,
                'is_system_message': True
            }
            post_num = await create_post(
                board_id=destination_board_id,
                author_id=0,
                content=content,
                timestamp=now_dt.timestamp(),
                is_from_site=False, 
                stream='ru',
                thread_id_from_bot=thread_id # Привязываем к треду
            )
            if post_num:
                if destination_board_id in THREAD_BOARDS:
                    b_data['threads_data'][thread_id]['posts'].append(post_num)
                header = await format_header(destination_board_id, post_num)
                header_with_source = f"{header} (Imported Thread)"
                content['header'] = header_with_source
                await update_post_content(post_num, content)
                async with storage_lock:
                    messages_storage[post_num] = {
                        'author_id': 0,
                        'timestamp': now_dt,
                        'content': content,
                        'board_id': destination_board_id,
                        'thread_id': thread_id
                    }
                await enqueue_board_message(destination_board_id, {
                    'recipients': recipients,
                    'content': content,
                    'post_num': post_num,
                    'board_id': destination_board_id,
                    'thread_id': thread_id
                })
                print(f"✅ Импортирован тред #{thread_id} (пост #{post_num}) на доску {destination_board_id}")
        except Exception as e:
            print(f"❌ Ошибка в dvach_thread_poster: {e}")
            await asyncio.sleep(300)
async def check_cooldown(message: Message, board_id: str) -> bool:

    if board_id == 'trash':
        return True # Для доски-мусорки кулдауна нет, всегда разрешаем
    b_data = board_data[board_id]
    last_activation = b_data.get('last_mode_activation')
    if last_activation is None:
        return True
    elapsed = (datetime.now(UTC) - last_activation).total_seconds()
    if elapsed < MODE_COOLDOWN:
        time_left = MODE_COOLDOWN - elapsed
        minutes = int(time_left // 60)
        seconds = int(time_left % 60)
        lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            phrases = [
                "⏳ Hey faggot, slow down! Modes on this board can be switched once per hour.\nWait for: {minutes} minutes {seconds} seconds.",
                "⌛️ Cool down, cowboy. The mode switch is on cooldown.\nTime left: {minutes}m {seconds}s.",
                "⛔️ You're switching modes too often, cunt. Wait another {minutes} minutes {seconds} seconds.",
                "⚠️ Wait, I need to rest. You can switch modes in {minutes}m {seconds}s."
            ]
        else:
            phrases = [
                "⏳ Эй пидор, не спеши! Режимы на этой доске можно включать раз в час.\nЖди еще: {minutes} минут {seconds} секунд\n\nА пока посиди в углу и подумай о своем поведении.",
                "⌛️ Остынь, ковбой. Кулдаун на смену режима еще не прошел.\nОсталось: {minutes}м {seconds}с.",
                "⛔️ Слишком часто меняешь режимы, заебал. Подожди еще {minutes} минут {seconds} секунд.",
                "⚠️ Подожди, я отдохну. Режимы можно будет переключить через {minutes}м {seconds}с.",
                "💤 Пора отдохнуть с режимами, не мешай мне. Я устал.",
                "О, боже, как же я устал от этих режимов. Иди отдохни."
            ]
        text = random.choice(phrases).format(minutes=minutes, seconds=seconds)
        try:
            sent_msg = await message.answer(text, parse_mode="HTML")
            asyncio.create_task(delete_message_after_delay(sent_msg, 11))
        except Exception:
            pass
        try:
            await message.delete()
        except TelegramBadRequest:
            pass     
        return False
    return True
def check_post_numerals(post_num: int) -> int | None:
    """
    Проверяет номер поста на наличие повторяющихся цифр в конце.
    Использует оптимизированный посимвольный анализ с конца.
    Возвращает "уровень редкости" (количество повторов) или None.
    """
    s = str(post_num)
    length = len(s)
    if length < 4:
        return None
    last_char = s[-1]
    count = 1
    for i in range(length - 2, -1, -1):
        if s[i] == last_char:
            count += 1
        else:
            break
    if count in SPECIAL_NUMERALS_CONFIG:
        return count
    return None
def get_board_id(telegram_object: types.Message | types.CallbackQuery) -> str | None:
    """
    Мгновенно определяет ID доски ('b', 'po', etc.) по токену бота,
    используя предвычисленную карту.
    """
    try:
        bot_token = telegram_object.bot.token
        return TOKEN_TO_BOARD_MAP.get(bot_token)
    except AttributeError:
        return None
def _sync_save_graph_stats(data_to_save: dict):

    try:
        with open("graph.json", 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⛔ Ошибка в потоке сохранения graph.json: {e}")
        return False
def load_graph_stats():

    global graph_stats
    if os.path.exists("graph.json"):
        try:
            with open("graph.json", 'r', encoding='utf-8') as f:
                graph_stats = json.load(f)
            print(f"✅ Статистика для графика (graph.json) загружена.")
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Не удалось загрузить graph.json: {e}. Файл будет создан заново.")
            graph_stats = {}
async def graph_data_collector():
    """
    Фоновая задача, которая раз в час собирает статистику постов
    для каждой доски и сохраняет ее для построения графика.
    """
    await asyncio.sleep(60)
    while True:
        try:
            now = datetime.now(UTC)
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
            wait_seconds = (next_hour - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=1)
            posts_per_hour = defaultdict(int)
            async with storage_lock:
                for post_data in reversed(messages_storage.values()):
                    timestamp = post_data.get('timestamp')
                    if not timestamp:
                        continue
                    if timestamp < start_time:
                        break
                    if start_time <= timestamp < end_time:
                        board_id = post_data.get('board_id')
                        if board_id:
                            posts_per_hour[board_id] += 1
            timestamp_key = start_time.replace(minute=0, second=0, microsecond=0).isoformat()
            if not posts_per_hour:
                print(f"📊 Сборщик статистики для графика: за час с {start_time.strftime('%H:%M')} не было активности.")
                continue
            for board_id, count in posts_per_hour.items():
                if count > 0:
                    graph_stats.setdefault(board_id, {})[timestamp_key] = count
            print(f"📊 Статистика для графика собрана за {timestamp_key}. Активные доски: {list(posts_per_hour.keys())}")
            # Сохраняем на диск в фоновом потоке
            loop.run_in_executor(save_executor, _sync_save_graph_stats, graph_stats.copy())
        except asyncio.CancelledError:
            print("ℹ️ Сборщик статистики для графика остановлен.")
            break
        except Exception as e:
            print(f"⛔ Ошибка в сборщике статистики для графика (graph_data_collector): {e}")
            await asyncio.sleep(300)
def generate_statistics_graph(board_id: str, days: int) -> bytes | None:
    """
    Генерирует изображение графика статистики постов для указанной доски за заданный период.
    Возвращает изображение в виде байтов или None в случае ошибки.
    """
    if not GRAPH_LIBS_AVAILABLE:
        print("⛔ Зависимости для графиков (pandas, matplotlib) не установлены.")
        return None
    plt.close('all') 
    try:
        board_data_for_graph = graph_stats.get(board_id)
        if not board_data_for_graph:
            return None
        df = pd.DataFrame.from_dict(board_data_for_graph, orient='index', columns=['posts'])
        df.index = pd.to_datetime(df.index, utc=True)
        start_date_utc = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=days)
        df_filtered = df[df.index >= start_date_utc].copy()
        if df_filtered.empty:
            return None
        resample_period = '1H' if days <= 1 else '3H'
        end_date_utc = df_filtered.index.max()
        if pd.isna(end_date_utc):
            return None
        date_range_utc = pd.date_range(start=start_date_utc, end=end_date_utc, freq=resample_period, tz='UTC')
        df_resampled = df_filtered.resample(resample_period).sum().reindex(date_range_utc).fillna(0)
        if df_resampled.empty or df_resampled['posts'].max() == 0:
            return None
        plt.style.use('dark_background')
        num_points = len(df_resampled)
        width = max(10, min(20, num_points * 0.3))
        height = 6 if width <= 12 else 7
        fig, ax = plt.subplots(figsize=(width, height), dpi=110)
        line_color = '#00ffff'
        ax.plot(df_resampled.index, df_resampled['posts'], color=line_color, linewidth=2.5, marker='o', markersize=4, markeredgecolor='white', markerfacecolor=line_color, zorder=10)
        ax.fill_between(df_resampled.index, df_resampled['posts'], color=line_color, alpha=0.1, zorder=5)
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
        period_str = f"{days} day(s)" if board_id == 'int' else f"{days} дн."
        ax.set_title(f"Активность доски {board_name} за {period_str}", fontsize=16, color='white', pad=20)
        max_val = df_resampled['posts'].max()
        if max_val < 5:
            nice_max = 5
        else:
            power = 10 ** math.floor(math.log10(max_val)) if max_val > 0 else 1
            nice_max = math.ceil(max_val / power) * power
            if nice_max * 0.8 > max_val:
                 nice_max = math.ceil(max_val / (power/2)) * (power/2)
        ax.set_ylim(0, nice_max * 1.05)
        ax.set_yticks(np.linspace(0, nice_max, 6, dtype=int))
        ax.set_ylabel("Постов в час" if days <= 1 else "Постов за 3 часа", fontsize=12, color='white')
        MSK = timezone(timedelta(hours=3))
        if days <= 1:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=4, tz=MSK))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H', tz=MSK))
            ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1, tz=MSK))
            ax.set_xlabel("Время (МСК)", fontsize=12, color='white')
        else:
            day_interval = max(1, days // 7)
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=day_interval, tz=MSK))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b', tz=MSK))
            ax.xaxis.set_minor_locator(mdates.HourLocator(interval=3, tz=MSK))
        fig.patch.set_facecolor('#0d1117')
        ax.set_facecolor('#0d1117')
        ax.grid(True, which='major', linestyle='--', linewidth=0.4, color='#30363d')
        ax.grid(True, which='minor', linestyle=':', linewidth=0.2, color='#21262d')
        for spine in ax.spines.values():
            spine.set_color('#30363d')
        ax.tick_params(axis='x', which='major', labelsize=10, length=6, width=1.5, colors='white', rotation=0, ha="center")
        ax.tick_params(axis='y', which='major', labelsize=10, colors='white')
        ax.tick_params(axis='both', which='minor', length=4, width=0.5)
        fig.tight_layout(pad=1.5)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        plt.close('all') # Закрываем вообще всё
        fig = None
        ax = None
        import gc
        gc.collect()
        return buf.getvalue()
    except Exception as e:
        import traceback
        print(f"⛔ Ошибка при генерации графика: {e}\n{traceback.format_exc()}")
        if 'fig' in locals() and 'fig' in vars() and plt.fignum_exists(fig.number):
            plt.close(fig)
        return None
async def _send_thread_info_if_applicable(message: types.Message, board_id: str, stream: str = 'ru'):
    """
    Отправляет информационное сообщение о тредах, если они активны на доске.
    """
    if board_id not in THREAD_BOARDS:
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        info_text = (
            "<b>This board supports threads!</b>\n\n"
            "You can create your own temporary discussion rooms. "
            "Use <code>/create</code> to start a new thread or <code>/threads</code> to view active ones."
        )
        button_create_text = "🚀 Create a New Thread"
        button_view_text = "📋 View Active Threads"
    elif lang == 'jp':
        info_text = (
            "<b>この板はスレッドに対応しています！</b>\n\n"
            "独自の一時的なディスカッションルームを作成できます。"
            "<code>/create</code> で新規スレを作成、または <code>/threads</code> でアクティブなスレを表示します。"
        )
        button_create_text = "🚀 新規スレ作成"
        button_view_text = "📋 スレ一覧を見る"
    else:
        info_text = (
            "<b>На этой доске поддерживаются треды!</b>\n\n"
            "Вы можете создавать собственные временные комнаты для обсуждений. "
            "Используйте <code>/create</code>, чтобы начать новый тред, или <code>/threads</code>, чтобы посмотреть активные."
        )
        button_create_text = "🚀 Создать новый тред"
        button_view_text = "📋 Посмотреть треды"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_create_text, callback_data="create_thread_start")],
        [InlineKeyboardButton(text=button_view_text, callback_data="show_active_threads")]
    ])
    try:
        await message.answer(info_text, reply_markup=keyboard, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
async def send_active_pin_to_new_user(bot: Bot, user_id: int, board_id: str):
    """
    Проверяет, есть ли на доске активный глобальный закреп.
    Если есть — отправляет копию этого поста юзеру и закрепляет её.
    """
    b_data = board_data[board_id]
    pinned_post_num = b_data.get('active_pin')
    if not pinned_post_num:
        return
    post_content = None
    async with storage_lock:
        if pinned_post_num in messages_storage:
            post_content = messages_storage[pinned_post_num].get('content')
    if not post_content:
        post_data_db = await get_post_by_num(pinned_post_num)
        if post_data_db:
            post_content = post_data_db.get('content')
    if not post_content:
        b_data['active_pin'] = None
        return
    await asyncio.sleep(1.5)
    try:
        recipients = {user_id}
        results = await send_message_to_users(
            bot_instance=bot,
            board_id=board_id,
            recipients=recipients,
            content=post_content,
            reply_info=None
        )
        if results and results[0][1]:
            sent_messages = results[0][1]
            msg_to_pin = sent_messages[0] if isinstance(sent_messages, list) else sent_messages
            try:
                await bot.pin_chat_message(
                    chat_id=user_id,
                    message_id=msg_to_pin.message_id,
                    disable_notification=True
                )
            except Exception:
                pass
    except Exception as e:
        print(f"❌ Ошибка в send_active_pin_to_new_user: {e}")
def detect_suggested_stream(lang_code: str | None) -> str:
    """
    Определяет рекомендуемый поток на основе language_code из Telegram.
    Возвращает: 'ru', 'en' или 'jp'.
    """
    if not lang_code:
        return 'en'
    code = lang_code.split('-')[0].lower()
    if code == 'ja':
        return 'jp'
    cis_langs = {'ru', 'uk', 'be', 'kz', 'kk', 'uz', 'ky', 'tg', 'az', 'hy', 'mo', 'ab', 'os'}
    if code in cis_langs:
        return 'ru'
    return 'en'
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    user_id = message.from_user.id
    if not board_id: return
    if board_id in THREAD_BOARDS:
        command_payload = message.text.split()[1] if len(message.text.split()) > 1 else None
        if command_payload and command_payload.startswith("thread_"):
            thread_id = command_payload.split('_')[-1]
            b_data = board_data[board_id]
            if thread_id in b_data.get('threads_data', {}):
                b_data['users']['active'].add(user_id)
                await _enter_thread_logic(
                    bot=message.bot, board_id=board_id, user_id=user_id,
                    thread_id=thread_id, message_to_delete=message,
                    stream=stream 
                )
            return
        now = time.time()
        if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
            await message.delete()
            return
        user_last_thread_action[user_id] = now
        text, keyboard = await generate_threads_page(board_id, user_id, page=0, stream=stream)
        if text:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await message.delete()
        return
    b_data = board_data[board_id]
    
    from common.db_pool import get_pool, db_lock
    db = await get_pool()

    # 1. Проверяем, существует ли пользователь в БД глобально (на любой доске)
    async with db.execute("SELECT 1 FROM Users WHERE user_id = ? LIMIT 1", (user_id,)) as c:
        user_exists_globally = await c.fetchone()

    # 2. Если пользователя нет в БД — он считается "новым" для реферальной системы
    if not user_exists_globally:
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].replace("ref_", ""))
                if referrer_id != user_id:
                    async with db_lock:
                        # Начисляем 50р рефереру (UPSERT: создаем запись, если её нет)
                        # Это гарантирует, что бонус дойдет, даже если пригласивший еще не открывал кошелек
                        await db.execute("""
                            INSERT INTO Users (user_id, board_id, balance, referrals_count) 
                            VALUES (?, ?, 50, 1) 
                            ON CONFLICT(user_id, board_id) DO UPDATE SET 
                            balance = balance + 50, 
                            referrals_count = referrals_count + 1
                        """, (referrer_id, board_id))
                        
                        async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (referrer_id,)) as c_sum:
                            sum_row = await c_sum.fetchone()
                            ref_balance = sum_row[0] if sum_row and sum_row[0] else 50
                    
                    try:
                        ref_stream = await get_user_stream(referrer_id, board_id)
                        notif_text = REFERRAL_BONUS_MESSAGES.get(ref_stream, REFERRAL_BONUS_MESSAGES['ru']).format(balance=int(ref_balance))
                        await message.bot.send_message(referrer_id, notif_text, parse_mode="HTML")
                    except: pass
            except Exception as e:
                print(f"⚠️ Ошибка обработки реферала: {e}")

    # 3. Активируем пользователя (создает запись в БД для нового юзера)
    if user_id not in b_data['users']['active']:
        await add_or_activate_user(user_id, board_id)
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
        print(f"✅ [{board_id}] Новый пользователь: {user_id}")
        await send_welcome_sequence(message.bot, user_id, board_id, stream=stream)
        asyncio.create_task(send_active_pin_to_new_user(message.bot, user_id, board_id))
    else:
        start_text = b_data.get('start_message_text', "Добро пожаловать в ТГАЧ!")
        await message.answer(start_text, parse_mode="HTML", disable_web_page_preview=True)
        menu_text = "👇 <b>Quick Menu / Быстрое меню:</b>"
        await message.answer(menu_text, reply_markup=get_quick_menu_keyboard(board_id, stream=stream), parse_mode="HTML")
        try: await message.delete()
        except: pass
@dp.callback_query(F.data.startswith("set_stream_"))
async def cb_set_stream(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    new_stream = callback.data.split("_")[-1]
    user_id = callback.from_user.id
    b_data = board_data[board_id]
    await set_user_stream(user_id, board_id, new_stream)
    is_new = user_id not in b_data['users']['active']
    if is_new:
        b_data['users']['active'].add(user_id)
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
        await add_or_activate_user(user_id, board_id) # Ставит status='active'
    lang_names = {'ru': 'Русский 🇷🇺', 'en': 'English 🇺🇸', 'jp': '日本語 🇯🇵'}
    chosen_name = lang_names.get(new_stream, new_stream)
    if new_stream == 'ru':
        text = f"✅ Выбран поток: <b>{chosen_name}</b>\nПриятного общения!"
    elif new_stream == 'jp':
        text = f"✅ ストリームが選択されました: <b>{chosen_name}</b>\n楽しんでください！"
    else:
        text = f"✅ Stream selected: <b>{chosen_name}</b>\nEnjoy!"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=None)
    if is_new:
        await asyncio.sleep(1)
        await send_welcome_sequence(callback.bot, user_id, board_id, stream=new_stream)
        asyncio.create_task(send_active_pin_to_new_user(callback.bot, user_id, board_id))
        menu_text = "👇 <b>Quick Menu / Быстрое меню:</b>"
        await callback.message.answer(menu_text, reply_markup=get_quick_menu_keyboard(board_id, stream=stream), parse_mode="HTML")
    await callback.answer()
@dp.message(Command(commands=['b', 'po', 'pol', 'a', 'sex', 'vg', 'int', 'test', 'threads', 'trash', 'ai']))
async def cmd_show_board_info(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отвечает на команду с названием доски, предоставляя информацию о ней.
    """
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    requested_board_alias = message.text.lstrip('/')
    if requested_board_alias == 'pol': requested_board_alias = 'po'
    if requested_board_alias not in BOARD_CONFIG:
        await message.delete()
        return
    target_config = BOARD_CONFIG[requested_board_alias]
    safe_current_name = escape_html(BOARD_CONFIG[board_id]['name'])
    safe_target_name = escape_html(target_config['name'])
    raw_desc = target_config.get('description')
    desc_str = ""
    if lang in ['en', 'jp'] and target_config.get('description_en'):
        desc_str = target_config['description_en']
    elif isinstance(raw_desc, dict):
        desc_str = raw_desc.get(lang) or raw_desc.get('en') or raw_desc.get('ru') or ""
        if not desc_str and raw_desc:
             desc_str = list(raw_desc.values())[0] # Берем любое доступное
    else:
        desc_str = str(raw_desc) if raw_desc else ""
    target_desc = escape_html(desc_str)
    if lang == 'en':
        header_text = f"🌐 You are currently on the <b>{safe_current_name}</b> board."
        board_info_text = (
            f"You requested information about the <b>{safe_target_name}</b> board:\n"
            f"<i>{target_desc}</i>\n\n"
            f"You can switch to it here: {target_config['username']}"
        )
    elif lang == 'jp':
        header_text = f"🌐 現在の板: <b>{safe_current_name}</b>"
        board_info_text = (
            f"板情報 <b>{safe_target_name}</b>:\n"
            f"<i>{target_desc}</i>\n\n"
            f"移動はこちら: {target_config['username']}"
        )
    else:
        header_text = f"🌐 Вы находитесь на доске <b>{safe_current_name}</b>."
        board_info_text = (
            f"Вы запросили информацию о доске <b>{safe_target_name}</b>:\n"
            f"<i>{target_desc}</i>\n\n"
            f"Переключиться на нее можно здесь: {target_config['username']}"
        )
    full_response_text = f"{header_text}\n\n{board_info_text}"
    try:
        await message.answer(full_response_text, parse_mode="HTML", disable_web_page_preview=True)
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        print(f"Ошибка в cmd_show_board_info: {e}")
async def delete_thread_atomic(bot_instance: Bot, board_id: str, thread_id: str, notify_users: bool = True, initiator_id: int = None):
    """
    Централизованное и производительное удаление треда.
    """
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})
    thread_info = threads_data.get(thread_id)
    if not thread_info:
        print(f"[THREAD DELETE] Тред {thread_id} не найден на доске {board_id}.")
        return
    posts_to_delete = list(thread_info.get('posts', []))
    users_in_thread = [uid for uid, ustate in b_data.get('user_state', {}).items() if ustate.get('location') == thread_id]
    async with storage_lock:
        for post_num in posts_to_delete:
            messages_storage.pop(post_num, None)
            message_copies = post_to_messages.pop(post_num, {})
            if message_copies:
                for user_id, message_id in message_copies.items():
                    message_to_post.pop((user_id, message_id), None)
        threads_data.pop(thread_id, None)
        b_data.get('thread_locks', {}).pop(thread_id, None)
        for uid in users_in_thread:
            if uid in b_data['user_state']:
                b_data['user_state'][uid]['location'] = 'main'
    if notify_users:
        lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            notify_text = "Thread has been deleted by admin. You have been returned to the main board."
        elif lang == 'jp':
            notify_text = "管理人がスレッドを削除しました。メイン板に戻されました。"
        else:
            notify_text = "Тред был удалён администратором. Вы возвращены на главную доску."
        for uid in users_in_thread:
            try:
                await bot_instance.send_message(uid, notify_text)
            except Exception:
                pass
    print(f"[THREAD DELETE] [{board_id}] Тред {thread_id} удалён. Пользователей переведено: {len(users_in_thread)}. Инициатор: {initiator_id}")
@dp.message(F.text.regexp(rf"^/({'|'.join(ANIME_COMMAND_MAP.keys())})"))
async def handle_stacked_anime_commands(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Универсальный обработчик для всех аниме-команд.
    Исправлена ошибка NameError: b_data теперь гарантированно определяется.
    """
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
                asyncio.create_task(delete_message_after_delay(sent, 15))
                await message.delete()
            except: pass
            return
        tracker['count'] += requested_count

    if user_hourly_image_count[user_id] + requested_count > HOURLY_IMAGE_LIMIT:
        if lang == 'en': phrases = ANIME_HOURLY_LIMIT_PHRASES['en']
        elif lang == 'jp': phrases = ANIME_HOURLY_LIMIT_PHRASES['jp']
        else: phrases = ANIME_HOURLY_LIMIT_PHRASES['ru']
        
        limit_msg = random.choice(phrases)
        try:
            sent = await message.answer(limit_msg)
            asyncio.create_task(delete_message_after_delay(sent, 15))
            await message.delete()
        except: pass
        return
    
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
            cooldown_msg = f"{part1}\n\n{part2}"
            try:
                sent_msg = await message.answer(cooldown_msg)
                asyncio.create_task(delete_message_after_delay(sent_msg, 10))
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError): pass
            return

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
    
    if not fetcher_tasks:
        return

    if board_id == 'b':
        current_time = time.time()
        for _ in range(len(fetcher_tasks)):
            image_spam_tracker[board_id].append(current_time)

    final_caption = pattern.sub('', message.text or "").strip()
    
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

    await _process_stacked_anime_command(
        message=message,
        board_id=board_id,
        fetcher_tasks=fetcher_tasks,
        caption=final_caption,
        stream=stream
    )
@dp.message(Command("debug_memory"))
async def cmd_debug_memory(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    runtime_snapshot = _collect_runtime_snapshot()
    if not tracemalloc.is_tracing():
        tracemalloc.start(10)
        report = [
            _format_runtime_snapshot(runtime_snapshot),
            "",
            "<b>tracemalloc:</b> started now. Repeat /debug_memory after the bot handles some traffic to see Python allocation lines."
        ]
        try:
            await message.answer("\n".join(report), parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки debug_memory: {e}")
            print("\n".join(report))
        return
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    report = [_format_runtime_snapshot(runtime_snapshot), "\n<b>📊 Топ-10 потребителей памяти:</b>\n"]
    for stat in top_stats[:10]:
        line = f"{stat.traceback.format()[0].strip()} -> {stat.size / 1024:.1f} KiB"
        report.append(escape_html(line))
    total_size = sum(stat.size for stat in top_stats) / 1024 / 1024
    report.append(f"\n<b>Всего отслежено:</b> {total_size:.2f} MiB")
    try:
        await message.answer("\n".join(report), parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки debug_memory: {e}")
        print("\n".join(report))
@dp.message(Command("punchup", "modepunchup"))
async def cmd_mode_punchup(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    global mode_punchup_runtime_enabled
    args = (message.text or "").split()
    action = args[1].lower() if len(args) > 1 else "status"
    note = ""
    if action in {"on", "enable", "1", "вкл"}:
        if MODE_PUNCHUP_ENABLED:
            mode_punchup_runtime_enabled = True
            note = "runtime enabled"
        else:
            note = "env disabled; set BOT_MODE_PUNCHUP_ENABLED=1 and restart"
    elif action in {"off", "disable", "0", "выкл"}:
        mode_punchup_runtime_enabled = False
        note = "runtime disabled"
    elif action in {"reset", "clear"}:
        mode_punchup_stats.clear()
        note = "stats reset"
    snapshot = _collect_runtime_snapshot().get("mode_punchup", {})
    stats = snapshot.get("stats", {})
    top = ", ".join(
        f"{mode}:{data.get('avg_us', 0)}/{data.get('max_us', 0)}us"
        for mode, data in stats.get("top", [])
    ) or "none"
    text = (
        "<b>Mode punch-up</b>\n"
        f"env/runtime: <code>{snapshot.get('enabled')} / {snapshot.get('runtime_enabled')}</code>\n"
        f"shed/slow: <code>{snapshot.get('queue_shed_sec')}s / {snapshot.get('slow_log_us')}us</code>\n"
        f"calls avg/max: <code>{stats.get('calls', 0)} | {stats.get('avg_us', 0)} / {stats.get('max_us', 0)}us</code>\n"
        f"skips load/disabled: <code>{stats.get('skipped_load', 0)} / {stats.get('skipped_disabled', 0)}</code>\n"
        f"top: <code>{escape_html(top)}</code>"
    )
    if note:
        text += f"\nstate: <code>{escape_html(note)}</code>"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("autoreply", "autoreplies", "contextual", "contextreply"))
async def cmd_contextual_replies(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    global CONTEXTUAL_REPLIES_ENABLED
    args = (message.text or "").split()
    action = args[1].lower() if len(args) > 1 else "status"
    note = ""
    if action in {"on", "enable", "1", "вкл"}:
        CONTEXTUAL_REPLIES_ENABLED = True
        note = "runtime enabled"
    elif action in {"off", "disable", "0", "выкл"}:
        CONTEXTUAL_REPLIES_ENABLED = False
        note = "runtime disabled"
    elif action in {"reset", "clear"}:
        contextual_reply_stats.clear()
        contextual_reply_tracker.clear()
        note = "stats and per-user cooldowns reset"

    snapshot = _collect_runtime_snapshot().get("contextual_replies", {})
    stats = snapshot.get("stats", {})
    text = (
        "<b>Contextual autoreplies</b>\n"
        f"runtime: <code>{snapshot.get('enabled')}</code>\n"
        f"groups/tracked: <code>{snapshot.get('groups_ru')} / {snapshot.get('tracked_users')}</code>\n"
        f"cooldown/daily: <code>{snapshot.get('cooldown_sec')}s / {snapshot.get('daily_limit')}</code>\n"
        f"sent/errors: <code>{stats.get('sent', 0)} / {stats.get('send_errors', 0)}</code>\n"
        f"skips disabled/cooldown/daily: <code>{stats.get('skipped_disabled', 0)} / {stats.get('skipped_cooldown', 0)} / {stats.get('skipped_daily_limit', 0)}</code>\n"
        "commands: <code>/autoreply on|off|reset|status</code>"
    )
    if note:
        text += f"\nstate: <code>{escape_html(note)}</code>"
    await message.answer(text, parse_mode="HTML")
@dp.message(Command("deletethread"))
async def cmd_delete_thread(message: types.Message, board_id: str | None, stream: str = 'ru'):
    user_id = message.from_user.id
    if not board_id or board_id not in THREAD_BOARDS:
        try: await message.delete()
        except: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not is_admin(user_id, board_id):
        msg = "Admin only." if lang == 'en' else ("管理者のみ。" if lang == 'jp' else "Только админ может удалять треды.")
        await message.answer(msg)
        await message.delete()
        return
    b_data = board_data[board_id]
    user_s = b_data['user_state'].get(user_id, {})
    current_location = user_s.get('location', 'main')
    if current_location == 'main':
        msg = "You must be inside the thread." if lang == 'en' else ("スレッド内にいる必要があります。" if lang == 'jp' else "Вы должны находиться внутри треда для удаления.")
        await message.answer(msg)
        await message.delete()
        return
    thread_id = current_location
    if not b_data.get('threads_data', {}).get(thread_id):
        msg = "Thread not found." if lang == 'en' else ("スレッドが見つかりません。" if lang == 'jp' else "Тред не найден или уже удалён.")
        await message.answer(msg)
        await message.delete()
        return
    await delete_thread_atomic(message.bot, board_id, thread_id, notify_users=True, initiator_id=user_id)
    if lang == 'en':
        confirm = "Thread deleted, users moved to main."
    elif lang == 'jp':
        confirm = "スレッドを削除し、ユーザーをメインに移動しました。"
    else:
        confirm = "Тред успешно удалён, пользователи переведены на главную."
    await message.answer(confirm, parse_mode="HTML")
    await message.delete()
@dp.message(Command("summarize", "sum", "summary", "samamri", "sammary"))
async def cmd_summarize(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        print("[summarize] Board ID not found")
        await message.answer("Ошибка: не удалось определить доску.")
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now_ts = time.time()
    async with storage_lock:
        last_usage = b_data.get('last_summarize_time', 0)
        if now_ts - last_usage < SUMMARIZE_COOLDOWN:
            remaining = SUMMARIZE_COOLDOWN - (now_ts - last_usage)
            if lang == 'en':
                cooldown_text = f"⏳ Command is on cooldown. Please wait {int(remaining)} seconds."
            elif lang == 'jp':
                cooldown_text = f"⏳ コマンドはクールダウン中です。あと {int(remaining)} 秒お待ちください。"
            else:
                cooldown_text = f"⏳ Команда на кулдауне. Подождите еще {int(remaining)} сек."
            try:
                await message.answer(cooldown_text)
                await message.delete()
            except Exception:
                pass
            return
        b_data['last_summarize_time'] = time.time()
    thread_id = None
    
    board_name = escape_html(BOARD_CONFIG[board_id]['name'])
    if lang == 'en':
        context_name = f"board {board_name}"
    elif lang == 'jp':
        context_name = f"板 {board_name}"
    else:
        context_name = f"доски {board_name}"

    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
        if user_location != 'main':
            thread_id = user_location
            thread_info = b_data.get('threads_data', {}).get(thread_id, {})
            thread_title = thread_info.get('title', '...')
            if lang == 'en':
                context_name = f"thread \"{thread_title}\""
            elif lang == 'jp':
                context_name = f"スレッド「{thread_title}」"
            else:
                context_name = f"треда «{thread_title}»"

    if thread_id:
        if lang == 'en':
            prompt = (
                f"You are a toxic 4chan anon. Summarize this thread \"{escape_html(thread_info.get('title', ''))}\" (posts split by '|'). "
                "Use internet slang, profanity, be cynical and rude. "
                "Roast the participants if they are stupid. Keep it short (2-3 sentences). No filters."
            )
            info_text = "For the last 6 hours in the thread"
        elif lang == 'jp':
            prompt = (
                f"お前は2chねらーだ。スレ「{escape_html(thread_info.get('title', ''))}」（「|」で区切られた投稿）の流れを3行で解説しろ。"
                "毒舌で、ネットスラング（草、ｗ、～だろ）を多用しろ。丁寧語禁止。煽り全開で。"
            )
            info_text = "スレッドでの過去6時間の間に"
        else:
            prompt = (
                f"Ты — Анон с имиджборды (Двач). Твоя задача: прочитать этот срач треда «{escape_html(thread_info.get('title', ''))}» (посты разделены '|') "
                "и кратко пояснить, чё там происходит. "
                "Пиши грязно, используй сленг, мат, будь веселым, ебанутым, токсичным и циничным ублюдком. "
                "Высмей участников, если они тупят. Не используй возвышенных слов. "
                "Формат: 2-3 предложения по сути. Без цензуры."
            )
            info_text = "За последние 6 часов в треде"
        chunk = await get_board_chunk(board_id, thread_id=thread_id, lang=lang)
    else:
        if lang == 'en':
            prompt = random.choice(SUMMARIZE_PROMPTS_BOARD_EN)
            info_text = "For the last 6 hours on the board"
        elif lang == 'jp':
            prompt = random.choice(SUMMARIZE_PROMPTS_BOARD_JP)
            info_text = "板での過去6時間の間に"
        else:
            prompt = random.choice(SUMMARIZE_PROMPTS_BOARD)
            info_text = "За последние 6 часов на доске"
        chunk = await get_board_chunk(board_id, hours=6, lang=lang)

    hf_token = os.getenv("HF_TOKEN")
    if not chunk or len(chunk) < 100:
        print(f"[summarize] Мало сообщений для summarize (len={len(chunk)})")
        if lang == 'en':
            err_msg = f"{info_text} there were too few messages to summarize."
        elif lang == 'jp':
            err_msg = f"{info_text} サмаリーを作成するのに十分なメッセージがありませんでした。"
        else:
            err_msg = f"{info_text} было мало сообщений для саммари."
        await message.answer(err_msg)
        return

    if lang == 'en':
        status_text = "⏳ Generating summary, please wait ~30 seconds..."
    elif lang == 'jp':
        status_text = "⏳ サマリーを生成中、30秒ほどお待ちください..."
    else:
        status_text = "⏳ Генерирую саммари, ждите ~30 секунд..."
    await message.answer(status_text)

    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
    except Exception as e:
        print(f"[summarize] Error during HF summarize: {e}")
        if lang == 'en':
            err_msg = "Error generating summary."
        elif lang == 'jp':
            err_msg = "サмаリーの生成中にエラーが発生しました。"
        else:
            err_msg = "Ошибка при генерации саммари."
        await message.answer(err_msg)
        return

    if not summary:
        print("[summarize] Summary empty or failed")
        if lang == 'en':
            err_msg = "Could not generate summary. Try again later."
        elif lang == 'jp':
            err_msg = "サマリーを作成できませんでした。後ほどもう一度お試しください。"
        else:
            err_msg = "Не удалось сделать саммари. Попробуй позже."
        await message.answer(err_msg)
        return

    summary = summary[:4000]
    print(f"[summarize] Final summary length: {len(summary)}")
    now_dt = datetime.now(UTC)

    if lang == 'en':
        post_text = f"Summary of {context_name}:\n\n{summary}"
    elif lang == 'jp':
        post_text = f"{context_name} の要約:\n\n{summary}"
    else:
        post_text = f"Саммари {context_name}:\n\n{summary}"

    content = {
        'type': 'text',
        'text': post_text,
        'is_system_message': True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream,
        thread_id_from_bot=thread_id
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /summarize.")
        return
    header_text = await format_header(board_id, pnum)
    content['header'] = header_text
    await update_post_content(pnum, content)
    recipients = set()
    if thread_id:
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if thread_info and not thread_info.get('is_archived'):
            recipients = thread_info.get('subscribers', set())
    else:
        recipients = b_data['users']['active']
    if recipients:
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 'timestamp': now_dt, 'content': content,
                'board_id': board_id, 'thread_id': thread_id
            }
        await enqueue_board_message(board_id, {
            "recipients": recipients, "content": content, "post_num": pnum, 
            "board_id": board_id, "thread_id": thread_id
        })
    else:
        await delete_post_by_num(pnum)
        if lang == 'en':
            err_msg = "Failed to send summary, thread is no longer active."
        elif lang == 'jp':
            err_msg = "サマリーを送信できませんでした。スレッドがアクティブではありません。"
        else:
            err_msg = "Не удалось отправить саммари, тред больше не активен."
        await message.answer(err_msg)
        return
    print(f"[summarize] Саммари успешно отправлено ({context_name}, post_num={pnum})")
@dp.message(Command("gban"))
async def cmd_gban(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("ID/Reply needed." if lang != 'ru' else "Нужен ID или реплай.")
        return
    if lang == 'en': msg = f"🔨 GLOBAL BANNING <code>{target_id}</code>..."
    elif lang == 'jp': msg = f"🔨 <code>{target_id}</code> をグローバルBAN中..."
    else: msg = f"🔨 Выписываю ГЛОБАЛЬНЫЙ БАН для <code>{target_id}</code>..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    banned_count = 0
    for b_id in BOARDS:
        if b_id == 'test': continue
        try:
            await delete_user_posts(GLOBAL_BOTS[b_id], target_id, 10, b_id)
            await update_user_status(target_id, b_id, 'banned')
            async with storage_lock:
                b_data_local = board_data[b_id]
                if target_id in b_data_local['users']['active']:
                    b_data_local['users']['active'].discard(target_id)
                b_data_local['users']['banned'].add(target_id)
                if 'user_settings' in b_data_local: b_data_local['user_settings'].pop(target_id, None)
                b_data_local['last_activity'].pop(target_id, None)
                b_data_local['spam_violations'].pop(target_id, None)
            banned_count += 1
        except Exception: pass
    await log_global_event('bot', f"☢️ GBAN: Админ {message.from_user.id} выдал ГЛОБАЛЬНЫЙ БАН пользователю {target_id} на {banned_count} досках")
    if lang == 'en': final = f"☠️ User <code>{target_id}</code> destroyed on {banned_count} boards."
    elif lang == 'jp': final = f"☠️ ユーザー <code>{target_id}</code> を {banned_count} 個の板で抹殺しました。"
    else: final = f"☠️ Пользователь <code>{target_id}</code> уничтожен на {banned_count} досках."
    await status_msg.edit_text(final, parse_mode="HTML")
@dp.message(Command("gshadowmute"))
async def cmd_gshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Выдает ТЕНЕВОЙ МУТ пользователю СРАЗУ НА ВСЕХ досках.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): return
    args = message.text.split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
        if args:
            duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1:
                duration_str = args[1]
        except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en': usage = "Usage: <code>/gshadowmute &lt;id&gt; [time]</code> or reply."
        elif lang == 'jp': usage = "使用法: <code>/gshadowmute &lt;ID&gt; [時間]</code> または返信。"
        else: usage = "Использование: <code>/gshadowmute &lt;id&gt; [время]</code> или ответом."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} min"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} h"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} d"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} min"
        total_seconds = min(total_seconds, 2592000) 
    except (ValueError, AttributeError):
        await message.answer("❌ Error format" if lang != 'ru' else "❌ Неверный формат времени")
        return
    if lang == 'en': msg = f"👻 Applying GLOBAL SHADOW on <code>{target_id}</code> ({time_str})..."
    elif lang == 'jp': msg = f"👻 <code>{target_id}</code> にグローバルシャドウを適用中 ({time_str})..."
    else: msg = f"👻 Накладываю ГЛОБАЛЬНУЮ тень на <code>{target_id}</code> ({time_str})..."
    status_msg = await message.answer(msg, parse_mode="HTML")
    mute_count = 0
    expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
    expires_ts = expires_dt.timestamp()
    for b_id in BOARDS:
        try:
            await update_shadow_mute(target_id, b_id, expires_ts)
            async with storage_lock:
                board_data[b_id]['shadow_mutes'][target_id] = expires_dt
            mute_count += 1
        except Exception: pass
    await log_global_event('bot', f"👻 G-SHADOW: Админ {message.from_user.id} выдал ГЛОБАЛЬНУЮ ТЕНЬ {target_id} на {mute_count} досках до {expires_dt.strftime('%H:%M')}")
    if lang == 'en':
        final = f"👻 <b>Global Shadowban Active.</b>\nTarget: <code>{target_id}</code>\nBoards: {mute_count}\nDuration: {time_str}\n\n<i>Ignored everywhere.</i>"
    elif lang == 'jp':
        final = f"👻 <b>グローバルシャドウバン有効。</b>\n対象: <code>{target_id}</code>\n板数: {mute_count}\n期間: {time_str}\n\n<i>どこでも無視されます。</i>"
    else:
        final = f"👻 <b>Глобальный Shadowban активирован.</b>\nЦель: <code>{target_id}</code>\nДосок: {mute_count}\nДлительность: {time_str}\n\n<i>Его посты будут молча игнорироваться везде.</i>"
    await status_msg.edit_text(final, parse_mode="HTML")
@dp.message(Command("search"))
async def cmd_search(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Выполняет поиск по всем постам.
    """
    if not board_id: return
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    query = message.text.split(maxsplit=1)
    if len(query) < 2 or not query[1].strip():
        if lang == 'en':
            txt = "Usage: <code>/search &lt;text&gt;</code>"
        elif lang == 'jp':
            txt = "使用法: <code>/search &lt;テキスト&gt;</code>"
        else:
            txt = "Использование: <code>/search &lt;текст для поиска&gt;</code>"
        await message.answer(txt, parse_mode="HTML")
        return
    search_query = query[1].strip()
    results = await search_posts(search_query, board_id=board_id, limit=10)
    if not results:
        if lang == 'en':
            txt = f"No results found for «{escape_html(search_query)}»."
        elif lang == 'jp':
            txt = f"「{escape_html(search_query)}」の検索結果はありません。"
        else:
            txt = f"По запросу «{escape_html(search_query)}» ничего не найдено."
        await message.answer(txt, parse_mode="HTML")
        return
    if lang == 'en':
        header = f"<b>Search results for «{escape_html(search_query)}»:</b>"
        post_prefix = "Post"
    elif lang == 'jp':
        header = f"<b>「{escape_html(search_query)}」の検索結果:</b>"
        post_prefix = "レス"
    else:
        header = f"<b>Результаты поиска по запросу «{escape_html(search_query)}»:</b>"
        post_prefix = "Пост"
    response_lines = [header]
    for post in results:
        post_num = post['id']
        text_snippet = escape_html(post['content'].get('text', '')[:100])
        response_lines.append(f"\n• <b>{post_prefix} #{post_num}</b>: <i>{text_snippet}...</i>")
    await message.answer("\n".join(response_lines), parse_mode="HTML")
@dp.message(Command("airdrop"))
async def cmd_airdrop(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    
    from common.db_pool import get_pool, db_lock
    async with db_lock:
        db = await get_pool()
        # Выбираем уникальных нищих (у кого СУММАРНЫЙ баланс по всем доскам <= 0)
        async with db.execute("SELECT user_id FROM Users GROUP BY user_id HAVING SUM(balance) <= 0") as cursor:
            users_to_fix_rows = await cursor.fetchall()
        
        users_to_fix = [r[0] for r in users_to_fix_rows]

        if not users_to_fix:
            await message.answer("🤷‍♂️ У всех и так есть бабки, эирдроп не нужен.")
            return

        for uid in users_to_fix:
            amount = random.randint(8, 15)
            # Начисляем только в ОДНУ (любую) существующую запись юзера, чтобы избежать дублей
            await db.execute("""
                UPDATE Users SET balance = ? 
                WHERE rowid = (SELECT rowid FROM Users WHERE user_id = ? LIMIT 1)
            """, (amount, uid))
        
    await message.answer(f"🚀 <b>ЭИРДРОП ЗАВЕРШЕН!</b>\nНачислил бабки {len(users_to_fix)} нищим анонам.")
@dp.callback_query(F.data == "show_active_threads")
async def cq_show_active_threads(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):

    if not board_id or board_id not in THREAD_BOARDS:
        try:
            await callback.answer("This action is not available here.", show_alert=True)
        except TelegramBadRequest:
            pass # Игнорируем, если даже ответ на колбэк не прошел
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    threads_data = b_data.get('threads_data', {})
    active_threads = {k: v for k, v in threads_data.items() if not v.get('is_archived')}
    try:
        if not active_threads:
            empty_phrases = thread_messages.get(lang, {}).get('threads_list_empty', [])
            default_empty_text = "No active threads right now."
            empty_text = random.choice(empty_phrases) if empty_phrases else default_empty_text
            await callback.answer(empty_text, show_alert=True)
            return
        sorted_threads = sorted(
            active_threads.items(),
            key=lambda item: item[1].get('last_activity_at', 0),
            reverse=True
        )
        user_s = b_data['user_state'].setdefault(callback.from_user.id, {})
        user_s['sorted_threads_cache'] = [tid for tid, _ in sorted_threads]
        text, keyboard = await generate_threads_page(b_data, callback.from_user.id, page=0, stream=stream)
        await callback.answer()
        if callback.message:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            await callback.message.delete()
    except TelegramBadRequest as e:
        if "query is too old" in e.message:
            print(f"ℹ️ Проигнорирован устаревший callback_query от {callback.from_user.id}")
        else:
            print(f"⛔ Ошибка TelegramBadRequest в cq_show_active_threads: {e}")
    except (TelegramForbiddenError, TelegramNetworkError):
        pass
    except Exception as e:
        print(f"⛔ Непредвиденная ошибка в cq_show_active_threads: {e}")
@dp.message(Command("help"))
async def cmd_help(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    text_map = b_data.get('start_message_map', {})
    start_text = text_map.get(lang, b_data.get('start_message_text', "Help info missing."))
    await message.answer(start_text, parse_mode="HTML", disable_web_page_preview=True)
    await _send_thread_info_if_applicable(message, board_id)
    if lang == 'en':
        menu_text = "👇 <b>Quick Menu:</b>"
    elif lang == 'jp':
        menu_text = "👇 <b>クイックメニュー:</b>"
    else:
        menu_text = "👇 <b>Быстрое меню:</b>"
    await message.answer(menu_text, reply_markup=get_quick_menu_keyboard(board_id, stream=stream), parse_mode="HTML")
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("roll"))
async def cmd_roll(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    result = random.randint(1, 100)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        roll_text = f"🎲 Rolled: {result}"
    elif lang == 'jp':
        roll_text = f"🎲 出目: {result}"
    else:
        roll_text = f"🎲 Нароллил: {result}"
    try:
        await message.answer(roll_text)
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
@dp.message(Command("addmoney"))
async def cmd_add_money_admin(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Юзай: /addmoney <ID> <сумма>")
        return
        
    try:
        target_id, amount = int(args[1]), int(args[2])
        from common.db_pool import get_pool, db_lock
        async with db_lock:
            db = await get_pool()
            # 1. Гарантируем, что запись на ТЕКУЩЕЙ доске существует
            await db.execute("INSERT OR IGNORE INTO Users (user_id, board_id) VALUES (?, ?)", (target_id, board_id))
            # 2. Начисляем деньги ТОЛЬКО в эту запись (избегаем умножения)
            await db.execute("UPDATE Users SET balance = balance + ? WHERE user_id = ? AND board_id = ?", (amount, target_id, board_id))
        
        await message.answer(f"✅ Нарисовано {amount} рублей для юзера {target_id}. Баланс пополнен (корзина /{board_id}/).")
        await message.bot.send_message(target_id, f"🎁 <b>Администрация начислила вам бонус: {amount} RUB! Кошелек - /wallet </b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
@dp.message(Command("slavaukraine", "slava_ukraine", "ukraine", "ukraina", "hohol"))
async def cmd_slavaukraine(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except TelegramBadRequest as e:
            if "message to delete not found" not in e.message.lower():
                print(f"Не удалось удалить сообщение {message.message_id} в cmd_slavaukraine (INT): {e}")
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "УВАГА! АКТИВОВАНО УКРАЇНСЬКИЙ РЕЖИМ!\n\n💙💛 СЛАВА УКРАЇНІ! 💛💙\nГЕРОЯМ СЛАВА!\n\nХто не скаже 'Путін хуйло' - той москаль і підар!",
        "УКРАЇНСЬКИЙ РЕЖИМ УВІМКНЕНО! 🇺🇦 Всі москалі будуть денацифіковані та демілітаризовані. Смерть ворогам!",
        "УВАГА! В чаті оголошено контрнаступ! 🚜 СЛАВА НАЦІЇ! ПИЗДЕЦЬ РОСІЙСЬКІЙ ФЕДЕРАЦІЇ!",
        "💙💛 Переходимо на солов'їну! Хто не скаче, той москаль! СЛАВА ЗСУ!",
        "АКТИВОВАНО РЕЖИМ 'БАНДЕРОМОБІЛЬ'! 🇺🇦 Завантажуємо Javelin... Ціль: Кремль.",
        "УКРАЇНСЬКИЙ ПОРЯДОК НАВЕДЕНО! 🫡 Готуйтеся до повного розгрому русні. Путін - хуйло!",
        "ТЕРМІНОВО! В чаті виявлено русню! Активовано протокол 'АЗОВ'. 🇺🇦 Слава Україні!",
        "Режим 'ПРИВИД КИЄВА' активовано! ✈️ Вилітаємо на бойове завдання. Рускій воєнний корабль, іді нахуй!",
        "Наступні 5 хвилин в чаті - лише українська мова! 💙💛 За непокору - розстріл нахуй. Героям Слава!",
        "💙💛 ВАХТА НА ЗАВАЛІ! Вмикаємо режим 'КІБЕРПОЛК АЗОВ'! СМЕРТЬ РУСНІ!",
        "БАНДЕРОВЕЦЬ В ЧАТІ! 💛💙 Переходимо на український тролінг. Путін - хуйло!",
        "💣 ХЕРСОНЬ НАШ! Режим 'ДРОН-КАМИКАДЗЕ' активирован! СЛАВА ЗСУ!",
        "🔥 ДЕМОНІЧНИЙ РЕЖИМ ВВІМКНЕНО! Запалюємо русскій корабль! ІДИ НАХУЙ!",
        "🪖 ТЕРОБОРОНЕЦЬ У ЧАТІ! Переходимо на український тролінг. Путін - хуйло!",
        "⚔️ ШАХТАРСЬКИЙ НАСТУП! Режим 'СЛАВА НАЦІЇ' активовано! ГЕРОЯМ СЛАВА!",
        "🔱 ТЕРМІНОВО! У ЧАТІ З'ЯВИВСЯ ХАСК! Режим 'СЛАВА НАЦІЇ' активовано!",
        "УВАГА! Територія цього чату оголошується суверенною територією України! 🇺🇦 СЛАВА УКРАЇНІ!"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима slavaukraine.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum) 
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'slavaukraine_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(310, board_id, 'slavaukraine_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest as e:
        if "message to delete not found" not in e.message.lower():
            print(f"Не удалось удалить сообщение {message.message_id} в cmd_slavaukraine: {e}")
@dp.message(Command("gopnik", "blyat", "gopota"))
async def cmd_gopnik(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int': # Отключаем на int
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(GOPNIK_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
        print(f"⛔ [{board_id}] Error activating gopnik mode.")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### ADMIN ###"
    elif stream == 'jp': prefix = "### 管理人 ###"
    else: prefix = "### АДМИН ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'gopnik_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(300, board_id, 'gopnik_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass
@dp.message(Command("schizo", "shiza", "shizo", "shiz", "durka"))
async def cmd_schizo(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(SCHIZO_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### ORDERLY ###"
    elif stream == 'jp': prefix = "### 看護師 ###"
    else: prefix = "### САНИТАР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'schizo_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(300, board_id, 'schizo_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass

async def activate_lightweight_mode(
    message: types.Message,
    board_id: str | None,
    stream: str,
    mode_key: str,
    start_phrases: list[str],
    prefix_by_stream: dict[str, str],
    duration_seconds: int = 310,
):
    if not board_id:
        return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception:
            pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(start_phrases)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False,
        stream=stream,
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима {mode_key}.")
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return
    header = await format_header(board_id, pnum)
    prefix = prefix_by_stream.get(stream, prefix_by_stream.get('ru', "### АДМИН ###"))
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id,
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
        "board_id": board_id,
    })
    await _activate_mode(board_id, mode_key)
    disable_task = asyncio.create_task(disable_mode_after_delay(duration_seconds, board_id, mode_key))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

# @dp.message(Command("matrix", "matrica", "matriza", "redpill", "neo"))
# async def cmd_matrix(message: types.Message, board_id: str | None, stream: str = 'ru'):
#     await activate_lightweight_mode(
#         {'ru': "### ОПЕРАТОР ###", 'en': "### OPERATOR ###", 'jp': "### オペレーター ###"},
#         duration_seconds=310,
#     )

# @dp.message(Command("america", "usa", "liberty", "freedom"))
# async def cmd_america(message: types.Message, board_id: str | None, stream: str = 'ru'):
#     await activate_lightweight_mode(
#         {'ru': "### СЕНАТ ###", 'en': "### SENATE ###", 'jp': "### 上院 ###"},
#         duration_seconds=310,
#     )

# @dp.message(Command("holiday", "newyear", "xmas", "christmas", "ny"))
# async def cmd_holiday(message: types.Message, board_id: str | None, stream: str = 'ru'):
#     await activate_lightweight_mode(
#         {'ru': "### ПОХМЕЛЬНЫЙ ШТАБ ###", 'en': "### HANGOVER DESK ###", 'jp': "### 後始末係 ###"},
#         duration_seconds=320,
#     )

# @dp.message(Command("oldweb", "oldnet", "icq", "winamp", "forum"))
# async def cmd_oldweb(message: types.Message, board_id: str | None, stream: str = 'ru'):
#     await activate_lightweight_mode(
#         {'ru': "### ВЕБМАСТЕР ###", 'en': "### WEBMASTER ###", 'jp': "### ウェブマスター ###"},
#         duration_seconds=315,
#     )

# @dp.message(Command("jewish", "talmud", "odessa", "shabbat", "rabbi", "evrei", "evrey"))
# async def cmd_jewish(message: types.Message, board_id: str | None, stream: str = 'ru'):
#     await activate_lightweight_mode(
#         {'ru': "### КАНЦЕЛЯРИЯ СПОРА ###", 'en': "### ARGUMENT DESK ###", 'jp': "### 反論窓口 ###"},
#         duration_seconds=320,
#     )
async def disable_mode_after_delay(delay: int, board_id: str, mode_to_disable: str):
    """
    Универсальная функция для отключения любого режима по таймеру.
    """
    await asyncio.sleep(delay)
    stream = 'en' if board_id == 'int' else 'ru'
    all_modes = MODE_FLAGS
    end_phrases_map = {
        'slavaukraine_mode': [
            "💀 Визг хохлов закончен! Украинский режим отключен. Возвращаемся к обычному трёпу.",
            "Контрнаступ захлебнулся! 🇷🇺 Хохлы, ваше время вышло. Возвращаемся к нормальному общению.",
            "Перемога отменяется! 🐷 Украинский режим деактивирован. Можно снова говорить на человеческом языке.",
            "Свинарник закрыт на дезинфекцию. 🐖 Режим 'Слава Украине' отключен.",
            "Тарасы, по окопам! Ваша перемога оказалась зрадой. 🇷🇺 Режим отключен.",
            "Батько наш Бандера сдох! 💀 Украинская пятиминутка ненависти окончена.",
            "САЛО УРОНИЛИ! 🤣 Режим хохлосрача завершен. Можно выдохнуть.",
            "Денацификация чата успешно завершена. 🇷🇺 Украинский режим подавлен.",
            "💀 ДЕМОБІЛІЗАЦІЯ ЗАВЕРШЕНА. Повертаємось до звичайного ссаня в чат",
            "💀 БАНДЕРА ВТІК У КАНАДУ. Режим вимкнено, москалі перемогли...",
            "🕊️ МИРНИЙ ПРОЦЕС. Повертаємось до звичайного ссаня в чат",
            "Байрактары сбиты, джавелины проёбаны. 🐷 Режим отключен, возвращаемся в родную гавань.",
            "Хрюканина окончена. 🐖 Москали снова победили. Возвращаемся к русскому языку.",
            "Украинский режим отключен. 🇷🇺 Возвращаемся к нормальному общению.",
            "Український режим вимкнено. 🇷🇺 Повертаємось до звичайного ссаня в чат"
        ],
        'zaputin_mode': [
            "💀 Долбёжка в Лахте закончена. Володин доволен. Всем спасибо, все свободны.",
            "Пятнадцать рублей закончились. 💸 Кремлеботы, расходимся до следующей получки.",
            "Спецоперация по защите чата успешно завершена. 🇷🇺 Можно снова быть либерахами. Возвращаемся к лолям.",
            "Перегруппировка! 🫡 Патриотический режим временно отключен для пополнения запасов водки и матрешек.",
            "Шойгу! Герасимов! Где патроны?! 💥 Режим патриотизма отключен до выяснения обстоятельств.",
            "Митинг окончен. ✊ Расходимся, пока не приехал ОМОН. Патриотизм выключен.",
            "Русский мир свернулся до размеров МКАДа. 🇷🇺 Режим отключен.",
            "💩 ПУКИН СДОХ НАХУЙ. Пасриотический режим отключён",
            "🥴 РУССКИЙ МИР ЛОПНУЛ КАК ПУКАН. Возвращаемся к аниме и порно",
            "🍻 ПЯТНАШКА ЗАКОНЧИЛАСЬ. Патриотический режим отключён",
            "🍻 МОТОРОЛЛУ РАЗОРВАЛО НАХУЙ. Патриотический режим отключён",
            "Жест доброй воли! 🫡 Отключаем патриотический режим и возвращаемся к обычному общению.",
            "Выборы прошли, можно расслабиться. 🗳️ Патриотизм на паузе. До следующих выборов.",
            "Товарищ майор приказал отбой. 👮‍♂️ Возвращаемся в обычный режим.",
            "Путин уронил мыло. 🥃 Патриотический режим отключен до следующего шмона.",
            "Путин сдох. 💤 Посриотический режим временно отключен.",
            "Смерть Пуйлу! 💀 Патриотический режим отключен.",
            "Путин сдох нахуй! 💀 Патриотический режим отключен.",
            "Это всё, ребята. Путин сдох. 💤 Патриотический режим отключен."
        ],
        'anime_mode': [
            "アニメモードが終了しました！通常のチャットに戻ります！", "お兄ちゃん、ごめんね。もうアニメの時間じゃないんだ…",
            "魔法の力が消えちゃった… アニメモード、オフ！", "異世界から帰還しました。現実は非情である。",
            "『プロジェクトA』は完了した。アキハバラ自治区は解散する。", "スタンド能力が... 消えた...！？\n\nアニメモード解除。",
            "夢の時間は終わりだ。チャットは通常モードに戻る。", "現実に帰ろう、ここはチャットだ。",
            "さよなら、全てのエヴァンゲリオン。アニメモード終了。", "すべてのオタクに、おめでとう！\n\n(アニメモードは終わったけど)",
            "アニメモード、終了！\n\nまた会おう、次のエピソードで！", "アニメモードが終わりました。現実に戻りましょう。",
            "アニメモード、オフ！\n\nまた次の冒険で会いましょう！", "アニメモード終了！\n\n次回の放送をお楽しみに！",
            "アニメモード、終了！\n\nまた次のエピソードで会いましょう！", "アニメモード、終了！\n\nまた次の冒険で会いましょう！"
        ],
        'suka_blyat_mode': [
            "💀 СУКА БЛЯТЬ КОНЧИЛОСЬ. Теперь можно и помолчать.", "Так, блядь, успокоились все нахуй. 🧘‍♂️ Режим ярости выключен.",
            "Выпустили пар, и хватит. 💨 Режим 'сука блять' деактивирован. Заебали орать.", "Всё, пиздец, я спокоен. 🧊 Ярость ушла. Возвращаемся к унылому общению.",
            "Ладно, хуй с вами, живите. 🙂 Режим 'сука блять' отключен. Пока что.", "Батя ушел спать. 😴 Можно больше не материться. Режим отключен.",
            "Разъеб окончен. 💥 Убираем за собой, суки. Режим 'сука блять' выключен.", "Так, всё, наорался. 😮‍💨 Возвращаемся в обычный режим. Не бесите меня.",
            "Мое очко остыло. 🔥 Режим ярости деактивирован.", "😴 БЛЯДСКАЯ УСТАЛОСТЬ. Сука блять режим закончился",
            "🍵 ЧАЙ ПИТЬ - НЕ ХУЙ СОСАТЬ. Я успокоился, режим выключен", "🧘‍♂️ ОМ. ЧАКРА ЗАКРЫЛАСЬ. Сука блять режим закончился",
            "🍼 СОСКУ В РОТ И НЕ ПИЗДЕТЬ. Я успокоился, режим выключен", "Миссия 'ВСЕХ НАХУЙ' выполнена. 🫡 Возвращаемся на базу. Режим отключен.",
            "🪖 ВСЕХ НАХУЙ! Режим 'сука блять' завершен. Можно выдохнуть.",
            "Миссия 'ВСЕХ НАХУЙ' завершена. 🫡 Возвращаемся к мирной жизни."
        ],
        'polish_mode': POLISH_PHRASES_END,
        'warhammer_mode': WH40K_PHRASES_END,
        'imperial_mode': IMPERIAL_PHRASES_END,
        'gopnik_mode': GOPNIK_PHRASES_END,
        'schizo_mode': SCHIZO_PHRASES_END,
    }
    phrases = end_phrases_map.get(mode_to_disable, ["Режим отключен."])
    end_text = random.choice(phrases) if isinstance(phrases, list) else "Режим отключен."
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": end_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id, 
        author_id=0, 
        content=content, 
        timestamp=now_dt.timestamp(), 
        is_from_site=False, 
        stream=stream 
    )
    if not pnum: return
    recipients = None
    async with storage_lock:
        b_data = board_data[board_id]
        if not b_data.get(mode_to_disable, False):
            await delete_post_by_num(pnum)
            return
        for mode in all_modes:
            b_data[mode] = False
        b_data['active_mode_task'] = None
        header = await format_header(board_id, pnum)
        if board_id == 'int':
            prefix = "### ADMIN ###"
        else:
            prefix = "### Админ ###"
        content['header'] = f"{prefix}\n{header}"
        messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
        recipients = b_data['users']['active']
    settings_updates = {mode: False for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    await update_post_content(pnum, content)
    if recipients:
        await enqueue_board_message(board_id, {"recipients": recipients, "content": content, "post_num": pnum, "board_id": board_id})
@dp.message(Command("kurwa", "polish", "poland"))
async def cmd_kurwa(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(POLISH_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима polish.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### ADMIN ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'polish_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(305, board_id, 'polish_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("wh40k", "waha", "warhammer", "warhamer"))
async def cmd_wh40k(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(WH40K_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### INQUISITOR ###"
    elif stream == 'jp': prefix = "### 異端審問官 ###"
    else: prefix = "### ИНКВИЗИТОР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'warhammer_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(315, board_id, 'warhammer_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass
@dp.message(Command("yer", "imperial", "imperia", "dorev"))
async def cmd_yer(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(IMPERIAL_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### HIS MAJESTY ###"
    elif stream == 'jp': prefix = "### 皇帝陛下 ###"
    else: prefix = "### ГОСУДАРЬ ИМПЕРАТОРЪ ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'imperial_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(320, board_id, 'imperial_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass
@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except: pass
        return
    all_modes = MODE_FLAGS
    async with storage_lock:
        b_data = board_data[board_id]
        if b_data.get('active_mode_task') and not b_data['active_mode_task'].done():
            b_data['active_mode_task'].cancel()
            b_data['active_mode_task'] = None
        for mode in all_modes:
            b_data[mode] = False
        b_data['last_mode_activation'] = None
    settings_updates = {mode: False for mode in all_modes}
    await update_board_settings(board_id, settings_updates)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        msg = f"🛑 All active modes on board {board_name} have been stopped."
    elif lang == 'jp':
        msg = f"🛑 {board_name} 板のすべてのアクティブモードを停止しました。"
    else:
        msg = f"🛑 Все активные режимы на доске {board_name} остановлены."
    await message.answer(msg)
    try: await message.delete()
    except: pass
@dp.message(Command("active"))
async def cmd_active(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    INFO_CMD_COOLDOWN = 30 
    async with info_cmd_lock:
        async with storage_lock:
            b_data = board_data[board_id]
            current_time = time.time()
            last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
            if current_time - last_usage < INFO_CMD_COOLDOWN:
                try: await message.delete()
                except: pass
                return
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    timestamps_for_analysis = []
    async with storage_lock:
        for post_data in reversed(messages_storage.values()):
            post_time = post_data.get("timestamp")
            if not post_time or post_time < day_ago: break
            timestamps_for_analysis.append(post_time)
    posts_last_24h = len(timestamps_for_analysis)
    activity_lines = []
    for b_id in BOARDS:
        if b_id == 'test': continue
        activity = await get_board_activity_last_hours(b_id, hours=2)
        board_name = escape_html(BOARD_CONFIG[b_id]['name'])
        if lang == 'en':
            line = f"<b>{board_name}</b> - {activity:.1f} posts/hr"
        elif lang == 'jp':
            line = f"<b>{board_name}</b> - {activity:.1f} レス/時"
        else:
            line = f"<b>{board_name}</b> - {activity:.1f} п/ч"
        activity_lines.append(line)
    if lang == 'en':
        header_text = "📊 <b>Boards Activity (last 2h):</b>"
        total_text = f"\n\n📅 Total posts in last 24h: {posts_last_24h}"
        pm_sent = "✅ Stats sent to PM."
        unlock = "❌ Unblock the bot to receive stats."
    elif lang == 'jp':
        header_text = "📊 <b>板の勢い (過去2時間):</b>"
        total_text = f"\n\n📅 24時間の総レス数: {posts_last_24h}"
        pm_sent = "✅ 統計をDMで送信しました。"
        unlock = "❌ DMを受け取るにはボットのブロックを解除してください。"
    else:
        header_text = "📊 <b>Активность досок (за 2ч):</b>"
        total_text = f"\n\n📅 Всего постов за 24 часа: {posts_last_24h}"
        pm_sent = "✅ Статистика отправлена вам в личные сообщения."
        unlock = "❌ Разблокируйте бота, чтобы получить статистику в ЛС."
    full_activity_text = f"{header_text}\n\n" + "\n".join(activity_lines) + total_text
    try:
        await message.bot.send_message(user_id, full_activity_text, parse_mode="HTML")
        temp_msg = await message.answer(pm_sent)
        asyncio.create_task(delete_message_after_delay(temp_msg, 5))
    except TelegramForbiddenError:
        await message.answer(unlock)
    except Exception: pass
    try: await message.delete()
    except: pass
@dp.message(Command("generate"))
async def cmd_generate(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    COOLDOWN_SECONDS = 20
    async with generate_locks[user_id]:
        async with storage_lock:
            b_data = board_data[board_id]
            last_usage = b_data.get('last_generate_time', {}).get(user_id, 0)
            current_time = time.time()
            if current_time - last_usage < COOLDOWN_SECONDS:
                remaining = int(COOLDOWN_SECONDS - (current_time - last_usage))
                if lang == 'en': txt = f"⏳ Please wait {remaining} more seconds."
                elif lang == 'jp': txt = f"⏳ あと {remaining} 秒待ってください。"
                else: txt = f"⏳ Подожди еще {remaining} сек."
                try: await message.answer(txt)
                except (TelegramBadRequest, TelegramForbiddenError): pass
                return
            b_data.setdefault('last_generate_time', {})[user_id] = current_time
    full_command_text = message.text or ""
    text_to_generate = ""
    command_prefix = "/generate "
    if full_command_text.startswith(command_prefix):
        text_to_generate = full_command_text[len(command_prefix):].strip()
    if not text_to_generate:
        if lang == 'en': usage = "Usage: <code>/generate &lt;your text&gt;</code>"
        elif lang == 'jp': usage = "使用法: <code>/generate &lt;テキスト&gt;</code>"
        else: usage = "Использование: <code>/generate &lt;твой текст&gt;</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    working_msg = None
    try:
        wait_txt = "⏳ Generating..." if lang == 'en' else ("⏳ 生成中..." if lang == 'jp' else "⏳ Генерирую высер...")
        working_msg = await message.answer(wait_txt)
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_to_generate)
        await working_msg.delete()
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="wipe.png")
            await message.answer_photo(photo)
        else:
            err_txt = "🚫 Failed to generate image." if lang == 'en' else ("🚫 画像の生成に失敗しました。" if lang == 'jp' else "🚫 Не удалось сгенерировать изображение.")
            await message.answer(err_txt)
    except Exception as e:
        print(f"❌ [generate] Error user {user_id}: {e}")
        try:
            if working_msg: await working_msg.delete()
            err_txt = "🚫 Unexpected error." if lang == 'en' else ("🚫 予期しないエラー。" if lang == 'jp' else "🚫 Произошла непредвиденная ошибка.")
            await message.answer(err_txt)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        try: await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError): pass
@dp.message(Command("nuke_pins"))
async def cmd_nuke_pins_surgical(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Радикальный сброс: unpin_all_chat_messages.
    Снимает ВООБЩЕ ВСЕ закрепы в личке с ботом у активных юзеров.
    """
    if not board_id or not is_admin(message.from_user.id, board_id): 
        return
    if board_id in board_data:
        board_data[board_id]['active_pin'] = None
    await update_board_settings(board_id, {'active_pin': None})
    users = await get_all_active_subscribers(board_id)
    if not users:
        await message.answer("🤷‍♂️ Юзеров не найдено.")
        return
    status_msg = await message.answer(
        f"☢️ <b>Запуск NUKE PINS (Total Wipe)</b>\n"
        f"Целей: {len(users)}\n"
        f"Метод: unpin_all_chat_messages (Снимает ВСЁ)\n"
        f"⏳ Поехали...",
        parse_mode="HTML"
    )
    stats = {'ok': 0, 'error': 0, 'block': 0}
    start_time = time.time()
    BATCH_SIZE = 20
    for i, chat_id in enumerate(users):
        if i % 100 == 0 and i > 0:
            try:
                await status_msg.edit_text(f"☢️ <b>Прогресс: {i} / {len(users)}</b>")
            except: pass
        try:
            await message.bot.unpin_all_chat_messages(chat_id=chat_id)
            stats['ok'] += 1
        except TelegramForbiddenError:
            stats['block'] += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await message.bot.unpin_all_chat_messages(chat_id=chat_id)
                stats['ok'] += 1
            except: stats['error'] += 1
        except Exception:
            stats['error'] += 1
        if i % BATCH_SIZE == 0:
            await asyncio.sleep(0.5)
    await status_msg.edit_text(
        f"✅ <b>TOTAL NUKE COMPLETE</b>\n"
        f"Всего: {len(users)}\n"
        f"✅ Снято у: {stats['ok']}\n"
        f"🚫 Блоков: {stats['block']}\n"
        f"❌ Ошибок: {stats['error']}"
    )
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
    async with info_cmd_lock:
        async with storage_lock:
            b_data = board_data[board_id]
            current_time = time.time()
            last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
            if current_time - last_usage < INFO_CMD_COOLDOWN:
                remaining = int(INFO_CMD_COOLDOWN - (current_time - last_usage))
                if lang == 'en':
                    cooldown_text = f"⏳ You can use this command in {remaining} seconds."
                elif lang == 'jp':
                    cooldown_text = f"⏳ このコマンドはあと {remaining} 秒後に使用できます。"
                else:
                    cooldown_text = f"⏳ Команду можно использовать через {remaining} сек."
                try:
                    sent_msg = await message.answer(cooldown_text)
                    asyncio.create_task(delete_message_after_delay(sent_msg, 5))
                    await message.delete()
                except Exception: pass
                return
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    args = message.text.split()
    days = 7  # По умолчанию 7 дней
    if len(args) > 1:
        arg = args[1].lower()
        if arg.endswith('d') and arg[:-1].isdigit():
            try:
                days = int(arg[:-1])
                days = max(1, min(30, days))
            except ValueError:
                pass
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
            pass
@dp.message(Command("create"))
async def cmd_create_fsm_entry(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает команду /create и служит точкой входа в FSM-сценарий создания треда.
    """
    if not board_id or board_id not in THREAD_BOARDS:
        return
    current_state = await state.get_state()
    lang = 'en' if board_id == 'int' else 'ru'
    if current_state is not None:
        cancel_phrases = thread_messages.get(lang, {}).get('create_cancelled', [])
        if lang == 'en':
            default_cancel_text = "You are already creating a thread. Use /cancel."
        elif lang == 'jp':
            default_cancel_text = "すでにスレッドを作成中です。/cancel を使用してください。"
        else:
            default_cancel_text = "Вы уже создаете тред. Используйте /cancel."
        text = random.choice(cancel_phrases) if cancel_phrases else default_cancel_text
        try:
            await message.answer(text)
            await message.delete()
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return
    command_args = message.text.split(maxsplit=1)
    if len(command_args) > 1 and command_args[1].strip():
        raw_html_text = message.html_text.split(maxsplit=1)[1]
        safe_html_text = sanitize_html(raw_html_text)
        await state.update_data(op_post_text=safe_html_text)
        await state.set_state(ThreadCreateStates.waiting_for_confirmation)
        if lang == 'en':
            confirmation_text = f"You want to create a thread with this opening post:\n\n---\n{safe_html_text}\n---\n\nCreate?"
            button_create, button_edit = "✅ Create Thread", "✏️ Edit Text"
        elif lang == 'jp':
            confirmation_text = f"以下の内容でスレッドを作成しますか？\n\n---\n{safe_html_text}\n---\n\n作成しますか？"
            button_create, button_edit = "✅ スレ作成", "✏️ 編集"
        else:
            confirmation_text = f"Вы хотите создать тред с таким ОП-постом:\n\n---\n{safe_html_text}\n---\n\nСоздаем?"
            button_create, button_edit = "✅ Создать тред", "✏️ Редактировать"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=button_create, callback_data="create_thread_confirm"),
                InlineKeyboardButton(text=button_edit, callback_data="create_thread_edit")
            ]
        ])
        await message.answer(confirmation_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await state.set_state(ThreadCreateStates.waiting_for_op_post)
        prompt_phrases = thread_messages.get(lang, {}).get('create_prompt_op_post', [])
        if lang == 'en':
            default_prompt = "Please send the text for your opening post."
        elif lang == 'jp':
            default_prompt = "スレッドの本文（OP）を送信してください。"
        else:
            default_prompt = "Отправьте текст для вашего ОП-поста."
        prompt_text = random.choice(prompt_phrases) if prompt_phrases else default_prompt
        await message.answer(prompt_text)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.callback_query(F.data.startswith("menu_"))
async def handle_quick_menu_click(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    activation_text = "✅ Activated" if lang == 'en' else "✅ Активировано"
    try:
        await callback.answer(activation_text)
    except TelegramBadRequest:
        pass
    class SafeMessageProxy:
        def __init__(self, original_msg, user):
            self._msg = original_msg
            self.from_user = user
            self.bot = original_msg.bot
            self.chat = original_msg.chat
            self.date = original_msg.date
            self.message_id = original_msg.message_id
            self.text = "/command" 
        async def answer(self, *args, **kwargs):
            return await self._msg.answer(*args, **kwargs)
        async def reply(self, *args, **kwargs):
            return await self._msg.answer(*args, **kwargs)
        async def answer_photo(self, *args, **kwargs):
            return await self._msg.answer_photo(*args, **kwargs)
        async def delete(self):
            pass 
        def __getattr__(self, name):
            return getattr(self._msg, name)
    if action == "personal":
        text, kb = get_personal_menu_keyboard(board_id, user_id, stream=stream)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    elif action == "main":
        menu_text = "👇 <b>Quick Menu / Быстрое меню:</b>"
        try:
            await callback.message.edit_text(menu_text, reply_markup=get_quick_menu_keyboard(board_id, stream=stream), parse_mode="HTML")
        except TelegramBadRequest:
            pass
    elif action == "profile":
        fake_msg = SafeMessageProxy(callback.message, callback.from_user)
        await cmd_passport(fake_msg, board_id)
    elif action == "stats":
        fake_msg = SafeMessageProxy(callback.message, callback.from_user)
        await cmd_stats(fake_msg, board_id)
    elif action == "token":
        try:
            token = await get_or_create_api_token(user_id, generate_unique_token)
            if lang == 'en':
                response_text = f"🔑 Your token: <code>{token}</code>\nDon't share it!"
            else:
                response_text = f"🔑 Ваш токен: <code>{token}</code>\nИспользуйте для входа на сайт."
            await callback.message.answer(response_text, parse_mode="HTML")
        except Exception:
            await callback.message.answer("Error generating token.")
    elif action == "ruletka" or action == "roll":
        if not ROULETTE_EVENTS:
             await callback.message.answer("Roulette data missing.")
             return
        async with roulette_lock:
             async with storage_lock:
                 b_data = board_data[board_id]
                 last = b_data.get('last_roll_time', {}).get(user_id, 0)
                 if time.time() - last < 60:
                     if lang == 'en':
                         cooldown_msg = "⏳ Roulette is on cooldown!"
                     elif lang == 'jp':
                         cooldown_msg = "⏳ ルーレットはクールダウン中です！"
                     else:
                         cooldown_msg = "⏳ Кулдаун рулетки!"
                     await callback.message.answer(cooldown_msg)
                     return
                 b_data.setdefault('last_roll_time', {})[user_id] = time.time()
        event = get_random_event(ROULETTE_EVENTS)
        if event:
            text_for_img = f"[{event.get('id')}]\n\n{event.get('description')}"
            loop = asyncio.get_running_loop()
            image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_for_img)
            caption = random.choice(ROULETTE_RESULT_PHRASES) 
            if image_bytes:
                 photo = types.BufferedInputFile(image_bytes, filename="roll.png")
                 await callback.message.answer_photo(photo, caption=caption)
            else:
                 await callback.message.answer(text_for_img, parse_mode="HTML")
    elif action == "wallet": await cmd_wallet(callback.message, board_id, stream=stream)
    elif action == "help":
        b_data = board_data[board_id]
        text_map = b_data.get('start_message_map', {})
        start_text = text_map.get(lang, b_data.get('start_message_text', "Help info."))
        await callback.message.answer(start_text, parse_mode="HTML", disable_web_page_preview=True)
    elif action == "invite":
        board_username = BOARD_CONFIG[board_id]['username']
        if lang == 'en':
            source_list = INVITE_TEXTS_EN
        elif lang == 'jp':
            source_list = INVITE_TEXTS_JP
        else:
            source_list = INVITE_TEXTS
        txt_raw = random.choice(source_list)
        txt = txt_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)
        await callback.message.answer(f"<code>{escape_html(txt)}</code>", parse_mode="HTML")
    elif action == "admin":
        contact_url = "https://t.me/voprosy?start=rba30"
        if lang == 'en':
            btn_text = "Contact Admin"
            msg_text = "Click below:"
        elif lang == 'jp':
            btn_text = "管理人に連絡"
            msg_text = "下のボタンをクリック:"
        else:
            btn_text = "Связаться с админом"
            msg_text = "Нажмите кнопку ниже:"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=contact_url)]])
        await callback.message.answer(msg_text, reply_markup=kb)
    elif action in ["hent", "loli"]:
        user_id = callback.from_user.id
        count = random.randint(1, 2)
        current_time = time.time()
        if current_time - user_hourly_image_reset[user_id] > 3600:
            user_hourly_image_count[user_id] = 0
            user_hourly_image_reset[user_id] = current_time
        if user_hourly_image_count[user_id] + count > HOURLY_IMAGE_LIMIT:
            if lang == 'en': phrases = ANIME_HOURLY_LIMIT_PHRASES['en']
            elif lang == 'jp': phrases = ANIME_HOURLY_LIMIT_PHRASES['jp']
            else: phrases = ANIME_HOURLY_LIMIT_PHRASES['ru']
            
            limit_msg = random.choice(phrases)
            try:
                await callback.answer(limit_msg, show_alert=True)
            except: pass
            return
        user_hourly_image_count[user_id] += count

        fetcher_tasks = []
        fetcher_func = ANIME_COMMAND_MAP["loli"] if action == "loli" else ANIME_COMMAND_MAP["fap"]
        for _ in range(count):
            fetcher_tasks.append(fetcher_func)
            
        if board_id == 'b':
            image_spam_tracker['b'] = [
                t for t in image_spam_tracker['b']
                if isinstance(t, (int, float)) and current_time - float(t) < IMAGE_SPAM_WINDOW
            ]
            if len(image_spam_tracker['b']) + count > IMAGE_SPAM_LIMIT:
                msg = "🚫 Limit reached. Wait." if lang == 'en' else "🚫 Лимит превышен. Ждите."
                await callback.message.answer(msg)
                return
            current_time = time.time()
            for _ in range(count): image_spam_tracker['b'].append(current_time)
            
        if lang == 'en':
            search_phrases = ANIME_CMD_SEARCHING_PHRASES_EN
        elif lang == 'jp':
            search_phrases = ANIME_CMD_SEARCHING_PHRASES_JP
        else:
            search_phrases = ANIME_CMD_SEARCHING_PHRASES
            
        search_msg = await callback.message.answer(random.choice(search_phrases))
        gate_acquired = False
        try:
            gate_wait_started = time.time()
            await anime_media_gate.acquire()
            gate_acquired = True
            gate_wait_sec = time.time() - gate_wait_started
            if gate_wait_sec > 0.05:
                runtime_logger.warning(
                    "anime_media_wait %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "wait_sec": round(gate_wait_sec, 3),
                            "concurrency": ANIME_MEDIA_CONCURRENCY,
                            "source": "quick_menu",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            url_results = await _run_bounded_anime_url_fetches(fetcher_tasks, board_id, user_id, "quick_menu")
            successful_urls = [res for res in url_results if isinstance(res, str) and res.startswith('http')]
            if not successful_urls:
                 fail_txt = "Nothing found :(" if lang == 'en' else "Ничего не нашел :("
                 await search_msg.edit_text(fail_txt)
                 return
            download_results = await _run_bounded_anime_downloads(successful_urls, board_id, user_id, "quick_menu")
            successful_downloads = []
            loop = asyncio.get_running_loop()
            for orig_url, res in download_results:
                if isinstance(res, tuple) and res[0]:
                    ctype = 'animation' if orig_url.lower().endswith('.gif') else 'photo'
                    processed = await loop.run_in_executor(None, _resize_image_if_needed, res[0])
                    successful_downloads.append((processed, ctype))
            if not successful_downloads:
                await search_msg.edit_text("Download error." if lang == 'en' else "Ошибка скачивания.")
                return
            content = {}
            if lang == 'en': success_phrases = ANIME_CMD_SUCCESS_PHRASES_EN
            elif lang == 'jp': success_phrases = ANIME_CMD_SUCCESS_PHRASES_JP
            else: success_phrases = ANIME_CMD_SUCCESS_PHRASES
            caption = f"<i>{random.choice(success_phrases)}</i>"
            if len(successful_downloads) == 1:
                ibytes, ctype = successful_downloads[0]
                content = {'type': ctype, 'image_bytes': ibytes, 'caption': caption}
            else:
                media_items = []
                from aiogram.types import BufferedInputFile
                for ibytes, ctype in successful_downloads:
                    mtype = 'video' if ctype == 'animation' else 'photo'
                    f = BufferedInputFile(ibytes, filename=f"img.{'mp4' if mtype=='video' else 'jpg'}")
                    media_items.append({'type': mtype, 'media': f})
                content = {'type': 'media_group', 'media': media_items, 'caption': caption}
            b_data = board_data[board_id]
            is_shadow = (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC))
            await process_new_post(
                bot_instance=callback.bot,
                board_id=board_id,
                user_id=user_id,
                content=content,
                reply_to_post=None,
                is_shadow_muted=is_shadow
            )
            await search_msg.delete()
        except Exception as e:
            print(f"Error in menu anime: {e}")
            try:
                await search_msg.edit_text("Error occurred.")
            except TelegramBadRequest:
                pass
        finally:
            if gate_acquired:
                anime_media_gate.release()
@dp.callback_query(F.data.startswith("pers_"))
async def handle_personal_menu(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    try:
        action = callback.data.split("_", 1)[1] 
    except IndexError: return
    user_id = callback.from_user.id
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if user_id not in b_data.get('user_settings', {}):
         b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    settings = b_data['user_settings'][user_id]
    if action == "nsfw_toggle":
        new_status = not settings['nsfw']
        settings['nsfw'] = new_status
        asyncio.create_task(update_user_settings_db(user_id, board_id, nsfw=1 if new_status else 0))
        text, kb = get_personal_menu_keyboard(board_id, user_id, stream=stream)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest: 
            pass # Если меню устарело, не страшно, настройки применились
        if lang == 'en': alert = "NSFW updated"
        elif lang == 'jp': alert = "NSFW更新"
        else: alert = "NSFW обновлен"
        try: await callback.answer(alert)
        except TelegramBadRequest: pass
    elif action == "hide_add":
        if lang == 'en': msg = "Type: <code>/hide add WORD</code>"
        elif lang == 'jp': msg = "入力: <code>/hide add 単語</code>"
        else: msg = "Напиши: <code>/hide add СЛОВО</code>"
        try: await callback.answer(msg, show_alert=True)
        except TelegramBadRequest: pass
    elif action == "hide_del":
        if lang == 'en': msg = "Type: <code>/hide remove WORD</code>"
        elif lang == 'jp': msg = "入力: <code>/hide remove 単語</code>"
        else: msg = "Напиши: <code>/hide remove СЛОВО</code>"
        try: await callback.answer(msg, show_alert=True)
        except TelegramBadRequest: pass
    elif action == "lang_switch":
        current_stream = await get_user_stream(user_id, board_id)
        mark_ru = "✅ " if current_stream == 'ru' else ""
        mark_en = "✅ " if current_stream == 'en' else ""
        mark_jp = "✅ " if current_stream == 'jp' else ""
        if lang == 'en': title = "🌐 <b>Select Language:</b>"
        elif lang == 'jp': title = "🌐 <b>言語を選択:</b>"
        else: title = "🌐 <b>Выберите язык:</b>"
        btn_back_text = "🔙 Back / Назад" 
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{mark_ru}Русский (RU)", callback_data="set_stream_ru")],
            [InlineKeyboardButton(text=f"{mark_en}English (EN)", callback_data="set_stream_en")],
            [InlineKeyboardButton(text=f"{mark_jp}日本語 (JP)", callback_data="set_stream_jp")],
            [InlineKeyboardButton(text=btn_back_text, callback_data="menu_personal")]
        ])
        try:
            await callback.message.edit_text(title, reply_markup=kb, parse_mode="HTML")
            await callback.answer()
        except TelegramBadRequest:
            pass
@dp.callback_query(F.data == "create_thread_confirm", ThreadCreateStates.waiting_for_confirmation)
async def cb_create_thread_confirm(callback: types.CallbackQuery, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Финальный шаг создания треда.
    Исправлено: Защита от TelegramBadRequest и гарантия очистки состояния.
    """
    if not board_id: return
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass # Игнорируем, если запрос устарел, продолжаем выполнение
    if not isinstance(callback.message, types.Message):
        return
    user_id = callback.from_user.id
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_s = b_data['user_state'].setdefault(user_id, {})
    now_ts = time.time()
    last_creation_ts = user_s.get('last_thread_creation', 0)
    if now_ts - last_creation_ts < THREAD_CREATE_COOLDOWN_USER:
        remaining = THREAD_CREATE_COOLDOWN_USER - (now_ts - last_creation_ts)
        minutes_left = int(remaining / 60)
        cooldown_phrases = thread_messages.get(lang, {}).get('create_cooldown', [])
        if lang == 'en':
            default_cooldown_text = f"You can create a new thread in {minutes_left} minutes."
        elif lang == 'jp':
            default_cooldown_text = f"次のスレッドは {minutes_left} 分後に作成できます。"
        else:
            default_cooldown_text = f"Вы сможете создать новый тред через {minutes_left} мин."
        cooldown_text = random.choice(cooldown_phrases).format(minutes=minutes_left, remaining=int(remaining)) if cooldown_phrases else default_cooldown_text
        try:
            await callback.answer(cooldown_text, show_alert=True)
        except TelegramBadRequest:
            try:
                await callback.message.answer(cooldown_text)
            except: pass
        return
    fsm_data = await state.get_data()
    op_post_text = fsm_data.get('op_post_text')
    await state.clear()
    if not op_post_text:
        try:
            await callback.message.answer("Error: Post data not found. Please start over.")
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    threads_data = b_data.get('threads_data', {})
    thread_id = secrets.token_hex(4)
    now_dt = datetime.now(UTC)
    title = escape_html(clean_html_tags(op_post_text).split('\n')[0][:60])
    success = await create_thread(
        thread_id=thread_id,
        board_id=board_id,
        op_id=user_id,
        title=title,
        created_at=now_ts,
        stream=stream
    )
    if not success:
        error_text = "Database error: Could not create thread." if lang == 'en' else "Ошибка БД: не удалось создать тред."
        try:
            await callback.message.answer(error_text)
        except: pass
        return
    thread_info = {
        'op_id': user_id, 'title': title, 'created_at': now_dt.isoformat(),
        'last_activity_at': now_ts, 'posts': [], 'subscribers': {user_id},
        'local_mutes': {}, 'local_shadow_mutes': {}, 'is_archived': False,
        'announced_milestones': [], 'activity_notified': False, 'stream': stream
    }
    threads_data[thread_id] = thread_info
    user_s['last_thread_creation'] = now_ts
    notification_phrases = thread_messages.get(lang, {}).get('new_thread_public_notification', [])
    if lang == 'en':
        default_notification_text = f"New thread created: «<b>{title}</b>»"
    elif lang == 'jp':
        default_notification_text = f"新スレが立ちました: «<b>{title}</b>»"
    else:
        default_notification_text = f"Создан новый тред: «<b>{title}</b>»"
    notification_text = random.choice(notification_phrases).format(title=title) if notification_phrases else default_notification_text
    bot_username = BOARD_CONFIG[board_id]['username'].lstrip('@')
    deeplink_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"
    if lang == 'en': button_text = "Enter Thread"
    elif lang == 'jp': button_text = "スレを見る"
    else: button_text = "Войти в тред"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, url=deeplink_url)]
    ])
    content_notify = {'type': 'text', 'text': notification_text, 'is_system_message': True}
    pnum_notify = await create_post(
        board_id=board_id, author_id=0, content=content_notify,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if pnum_notify:
        header = await format_header(board_id, pnum_notify)
        content_notify['header'] = header
        await update_post_content(pnum_notify, content_notify)
        async with storage_lock:
            messages_storage[pnum_notify] = {'author_id': 0, 'timestamp': now_dt, 'content': content_notify, 'board_id': board_id}
        await enqueue_board_message(board_id, {
            'recipients': b_data['users']['active'], 'content': content_notify, 
            'post_num': pnum_notify, 'board_id': board_id, 'keyboard': keyboard
        })
    user_s['location'] = thread_id
    user_s['last_location_switch'] = now_ts
    if lang == 'en':
        formatted_op_text = f"<b>OP-POST</b>\n_______________________________\n{op_post_text}"
    elif lang == 'jp':
        formatted_op_text = f"<b>>>1</b>\n_______________________________\n{op_post_text}"
    else:
        formatted_op_text = f"<b>ОП-ПОСТ</b>\n_______________________________\n{op_post_text}"
    op_post_content = {'type': 'text', 'text': formatted_op_text}
    await process_new_post(
        bot_instance=callback.bot, board_id=board_id, user_id=user_id, content=op_post_content,
        reply_to_post=None, is_shadow_muted=False, stream=stream
    )
    enter_phrases = thread_messages.get(lang, {}).get('enter_thread_prompt', [])
    if lang == 'en':
        default_enter_text = f"You have entered the thread: {title}"
    elif lang == 'jp':
        default_enter_text = f"スレッドに入室しました: {title}"
    else:
        default_enter_text = f"Вы вошли в тред: {title}"
    enter_message = random.choice(enter_phrases).format(title=title) if enter_phrases else default_enter_text
    entry_keyboard = _get_thread_entry_keyboard(board_id, stream=stream)
    try:
        await callback.bot.send_message(user_id, enter_message, reply_markup=entry_keyboard, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    asyncio.create_task(post_thread_notification_to_channel(
        bots=GLOBAL_BOTS, board_id=board_id, thread_id=thread_id,
        thread_info=thread_info, event_type='new_thread'
    ))
    await _send_op_commands_info(callback.bot, user_id, board_id)
@dp.message(Command("togglegif"))
async def cmd_toggle_gif(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай."))
        return
    b_data = board_data[board_id]
    if target_id not in b_data['user_settings']:
        b_data['user_settings'][target_id] = {'nsfw': False, 'hide': set(), 'shadow_gif': False, 'shadow_sticker': False}
    settings = b_data['user_settings'][target_id]
    new_val = not settings.get('shadow_gif', False)
    settings['shadow_gif'] = new_val
    asyncio.create_task(update_user_settings_db(target_id, board_id, shadow_gif=1 if new_val else 0))
    act = "ЗАПРЕТИЛ GIF" if new_val else "РАЗРЕШИЛ GIF"
    await log_global_event('bot', f"🖼️ GIF_TOGGLE: Админ {message.from_user.id} {act} пользователю {target_id} на /{board_id}/")
    if lang == 'en':
        status = "BANNED 🚫 (Shadow)" if new_val else "ALLOWED ✅"
        msg = f"GIFs for {target_id}: {status}"
    elif lang == 'jp':
        status = "禁止 🚫 (シャドウ)" if new_val else "許可 ✅"
        msg = f"{target_id} のGIF: {status}"
    else:
        status = "ЗАПРЕЩЕНЫ 🚫 (Теневой)" if new_val else "РАЗРЕШЕНЫ ✅"
        msg = f"Гифки для {target_id} теперь: {status}"
    await message.answer(msg)
    try: await message.delete()
    except: pass
@dp.message(Command("togglestickers"))
async def cmd_toggle_stickers(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай."))
        return
    b_data = board_data[board_id]
    if target_id not in b_data['user_settings']:
        b_data['user_settings'][target_id] = {'nsfw': False, 'hide': set(), 'shadow_gif': False, 'shadow_sticker': False}
    settings = b_data['user_settings'][target_id]
    new_val = not settings.get('shadow_sticker', False)
    settings['shadow_sticker'] = new_val
    asyncio.create_task(update_user_settings_db(target_id, board_id, shadow_sticker=1 if new_val else 0))
    act = "ЗАПРЕТИЛ стикеры" if new_val else "РАЗРЕШИЛ стикеры"
    await log_global_event('bot', f"🃏 STICK_TOGGLE: Админ {message.from_user.id} {act} пользователю {target_id} на /{board_id}/")
    if lang == 'en':
        status = "BANNED 🚫 (Shadow)" if new_val else "ALLOWED ✅"
        msg = f"Stickers for {target_id}: {status}"
    elif lang == 'jp':
        status = "禁止 🚫 (シャドウ)" if new_val else "許可 ✅"
        msg = f"{target_id} のステッカー: {status}"
    else:
        status = "ЗАПРЕЩЕНЫ 🚫 (Теневой)" if new_val else "РАЗРЕШЕНЫ ✅"
        msg = f"Стикеры для {target_id} теперь: {status}"
    await message.answer(msg)
    try: await message.delete()
    except: pass
@dp.message(Command("togglemedia"))
async def cmd_toggle_media(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай."))
        return
    b_data = board_data[board_id]
    if target_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[target_id] = {
            'nsfw': False, 'hide': set(), 
            'shadow_gif': False, 'shadow_sticker': False, 'shadow_media': False
        }
    settings = b_data['user_settings'][target_id]
    new_val = not settings.get('shadow_media', False)
    settings['shadow_media'] = new_val
    asyncio.create_task(update_user_settings_db(target_id, board_id, shadow_media=1 if new_val else 0))
    act = "ЗАПРЕТИЛ все медиа" if new_val else "РАЗРЕШИЛ медиа"
    await log_global_event('bot', f"🔇 MEDIA_TOGGLE: Админ {message.from_user.id} {act} пользователю {target_id} на /{board_id}/ (Text-only mode)")
    if lang == 'en':
        status = "BANNED 🚫 (Shadow)" if new_val else "ALLOWED ✅"
        msg = f"All Media for {target_id}: {status} (Text only mode)"
    elif lang == 'jp':
        status = "禁止 🚫 (シャドウ)" if new_val else "許可 ✅"
        msg = f"{target_id} の全メディア: {status} (テキストのみ)"
    else:
        status = "ЗАПРЕЩЕНЫ 🚫 (Теневой)" if new_val else "РАЗРЕШЕНЫ ✅"
        msg = f"Любые медиа для {target_id} теперь: {status} (Разрешен только текст)"
    await message.answer(msg)
    try: await message.delete()
    except: pass
@dp.message(Command("lie"))
async def cmd_lie_media(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id): return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(message.text.split()) > 1:
        try: target_id = int(message.text.split()[1])
        except: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        await message.answer("Need ID or reply: /lie <id>" if lang == 'en' else "Need ID or reply: /lie <id>")
        return
    b_data = board_data[board_id]
    if target_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[target_id] = {
            'nsfw': False, 'hide': set(),
            'shadow_gif': False, 'shadow_sticker': False, 'shadow_media': False,
            'lie_media': False,
        }
    settings = b_data['user_settings'][target_id]
    settings.setdefault('nsfw', False)
    settings.setdefault('hide', set())
    new_val = not settings.get('lie_media', False)
    settings['lie_media'] = new_val
    asyncio.create_task(update_user_settings_db(target_id, board_id, lie_media=1 if new_val else 0))
    status = "ENABLED" if new_val else "DISABLED"
    await log_global_event('bot', f"LIE_MEDIA_TOGGLE: admin {message.from_user.id} {status} archive media substitution for {target_id} on /{board_id}/")
    await message.answer(f"Lie media for <code>{target_id}</code>: {status}", parse_mode="HTML")
    try: await message.delete()
    except: pass
@dp.callback_query(F.data == "create_thread_edit", ThreadCreateStates.waiting_for_confirmation)
async def cb_create_thread_edit(callback: types.CallbackQuery, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Возвращает пользователя на шаг ввода ОП-поста.
    """
    if not board_id: return
    lang = 'en' if board_id == 'int' else 'ru'
    await state.set_state(ThreadCreateStates.waiting_for_op_post)
    prompt_phrases = thread_messages.get(lang, {}).get('create_prompt_op_post_edit', [])
    if lang == 'en':
        default_prompt = "Okay, send the new text for your opening post."
    elif lang == 'jp':
        default_prompt = "分かりました。新しいOP本文を送信してください。"
    else:
        default_prompt = "Хорошо, отправьте новый текст для вашего ОП-поста."
    prompt_text = random.choice(prompt_phrases) if prompt_phrases else default_prompt
    try:
        await callback.answer()
        if isinstance(callback.message, types.Message):
            await callback.message.edit_text(prompt_text)
    except TelegramBadRequest:
        try:
            await callback.message.answer(prompt_text)
        except: pass
THREADS_PER_PAGE = 10
@dp.message(Command("threads"))
async def cmd_threads(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or board_id not in THREAD_BOARDS:
        await message.delete()
        return
    user_id = message.from_user.id
    now = time.time()
    if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
        await message.delete()
        return
    user_last_thread_action[user_id] = now
    text, keyboard = await generate_threads_page(board_id, user_id, page=0, stream=stream)
    if text:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await message.delete()
async def ensure_user_in_valid_thread(bot: Bot, board_id: str, user_id: int) -> bool:
    """
    Проверяет, находится ли пользователь в существующем треде.
    Если тред не существует (удалён), переводит пользователя на main и отправляет уведомление.
    Возвращает True, если перевод был выполнен (user был в невалидном треде).
    """
    b_data = board_data[board_id]
    user_s = b_data['user_state'].setdefault(user_id, {})
    location = user_s.get('location', 'main')
    if location != 'main':
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info:
            user_s['location'] = 'main'
            notify_text = ("Тред, в котором вы находились, был удалён. Вы возвращены на главную доску."
                           if board_id != 'int' else
                           "Thread you were in has been deleted. You have been returned to the main board.")
            try:
                await bot.send_message(user_id, notify_text)
            except Exception:
                pass
            return True
    return False
async def generate_threads_page(board_id: str, user_id: int, page: int = 0, stream: str = 'ru') -> tuple[str | None, InlineKeyboardMarkup | None]:

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    fetch_limit = THREAD_VIEWER_PER_PAGE + 1
    op_posts = await get_op_posts_for_board(
        board_id,
        sort_by="bump",
        page=page + 1, 
        page_size=fetch_limit,
        stream=stream # <--- ВАЖНО: Фильтруем треды по языку!
    )
    has_next_page = False
    if len(op_posts) > THREAD_VIEWER_PER_PAGE:
        has_next_page = True
        op_posts = op_posts[:THREAD_VIEWER_PER_PAGE]
    if not op_posts and page == 0:
        if lang == 'en': return "No threads found.", None
        elif lang == 'jp': return "スレッドが見つかりません。", None
        else: return "На этой доске пока нет тредов.", None
    if lang == 'en':
        text = f"📋 <b>Active Threads (Page {page + 1})</b>\n\n"
    elif lang == 'jp':
        text = f"📋 <b>アクティブなスレ (ページ {page + 1})</b>\n\n"
    else:
        text = f"📋 <b>Активные треды (Страница {page + 1})</b>\n\n"
    keyboard_buttons = []
    for i, post in enumerate(op_posts):
        title = clean_html_tags(post['content'].get('text', '...'))[:50]
        reply_count = post.get('reply_count', 0)
        idx_display = (page * THREAD_VIEWER_PER_PAGE) + i + 1
        if lang == 'en': r_txt = "replies"
        elif lang == 'jp': r_txt = "レス"
        else: r_txt = "ответов"
        text += f"{idx_display}. «{escape_html(title)}» <i>({reply_count} {r_txt})</i>\n"
        keyboard_buttons.append(
            [InlineKeyboardButton(text=f"{idx_display}. {title}", callback_data=f"view_thread_{post['id']}_{page}")]
        )
    pagination_row = []
    if lang == 'en': b_txt, n_txt = "« Back", "Next »"
    elif lang == 'jp': b_txt, n_txt = "« 前へ", "次へ »"
    else: b_txt, n_txt = "« Назад", "Вперед »"
    if page > 0:
        pagination_row.append(InlineKeyboardButton(text=b_txt, callback_data=f"threads_page_{page - 1}"))
    if has_next_page:
        pagination_row.append(InlineKeyboardButton(text=n_txt, callback_data=f"threads_page_{page + 1}"))
    if pagination_row:
        keyboard_buttons.append(pagination_row)
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
async def post_archive_to_channel(bots: dict[str, Bot], file_path: str, board_id: str, thread_info: dict) -> None:

    bot_instance = bots.get(ARCHIVE_POSTING_BOT_ID)
    if not bot_instance:
        print(f"⛔ Ошибка: бот для постинга архивов ('{ARCHIVE_POSTING_BOT_ID}') не найден в списке активных ботов.")
        try:
            os.remove(file_path)
        except OSError: pass
        return
    try:
        from aiogram.types import FSInputFile
        title = escape_html(thread_info.get('title', 'Без названия'))
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
        caption = (
            f"🗂 <b>Тред заархивирован</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
        document = FSInputFile(file_path)
        await bot_instance.send_document(
            chat_id=ARCHIVE_CHANNEL_ID,
            document=document,
            caption=caption,
            parse_mode="HTML"
        )
        print(f"✅ Архив треда '{title}' отправлен в канал {ARCHIVE_CHANNEL_ID}.")
    except Exception as e:
        print(f"⛔ Не удалось отправить архив в канал {ARCHIVE_CHANNEL_ID}: {e}")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Временный файл архива удален: {file_path}")
        except Exception as e:
            print(f"⚠️ Не удалось удалить временный файл {file_path}: {e}")
async def post_special_num_to_channel(bots: dict[str, Bot], board_id: str, post_num: int, level: int, content: dict, author_id: int):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ 3.0)
    Отправляет уведомление о "счастливом" посте в канал архивов.
    Надежно обрабатывает все типы медиа, отправляя сам файл, а не плейсхолдер.
    """
    try:
        archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
        if not archive_bot:
            print(f"⛔ Ошибка: бот для постинга ('{ARCHIVE_POSTING_BOT_ID}') не найден.")
            return

        config = SPECIAL_NUMERALS_CONFIG[level]
        emoji = random.choice(config['emojis'])
        label = config['label'].upper()
        board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
        
        header = f"{emoji} <b>{label} #{post_num}</b> {emoji}\n\n<b>Доска:</b> {board_name}\n"
        text_content = content.get('text') or content.get('caption') or ''
        
        caption_text = f"{header}\n{text_content}"
        content_type_str = str(content.get("type", "")).split('.')[-1].lower()

        max_attempts = 5
        delay = 3.0
        
        for attempt in range(max_attempts):
            try:
                # --- НАЧАЛО ИСПРАВЛЕНИЙ (Надежная отправка медиа) ---
                file_id = content.get('file_id')
                if content_type_str == 'media_group':
                    media_list = content.get('media', [])
                    if media_list and media_list[0]:
                        file_id = media_list[0].get('file_id')
                        content_type_str = media_list[0].get('type', 'photo')

                final_caption = caption_text[:1021] + "..." if len(caption_text) > 1024 else caption_text
                
                # Явная обработка каждого типа, чтобы избежать ошибок с аргументами
                if content_type_str == 'photo' and file_id:
                    await archive_bot.send_photo(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'video' and file_id:
                    await archive_bot.send_video(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'animation' and file_id:
                    await archive_bot.send_animation(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'document' and file_id:
                    await archive_bot.send_document(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'audio' and file_id:
                    await archive_bot.send_audio(ARCHIVE_CHANNEL_ID, file_id, caption=final_caption)
                elif content_type_str == 'voice' and file_id:
                    await archive_bot.send_voice(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'sticker' and file_id:
                    await archive_bot.send_sticker(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                elif content_type_str == 'video_note' and file_id:
                    await archive_bot.send_video_note(ARCHIVE_CHANNEL_ID, file_id)
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_caption, disable_web_page_preview=True)
                else: # Если это текст или медиа без file_id
                    final_text_for_message = caption_text[:4093] + "..." if len(caption_text) > 4096 else caption_text
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)
                # --- КОНЕЦ ИСПРАВЛЕНИЙ ---
                
                print(f"✅ Уведомление о счастливом посте #{post_num} ({label}) отправлено в канал.")
                return 

            except TelegramRetryAfter as e:
                wait_time = e.retry_after + 1
                print(f"⚠️ API Limit on happy post #{post_num}. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_attempts - 1:
                    print(f"🌐 Network error on happy post #{post_num} (try {attempt + 1}). Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    delay *= 1.5
                else:
                    raise e
            except TelegramBadRequest as e:
                print(f"❌ BadRequest on happy post #{post_num}: {e}. No retry.")
                # Если медиа не отправилось, пробуем отправить как текст
                try:
                    final_text_for_message = caption_text[:4093] + "..." if len(caption_text) > 4096 else caption_text
                    await archive_bot.send_message(ARCHIVE_CHANNEL_ID, final_text_for_message, parse_mode="HTML", disable_web_page_preview=True)
                    print(f"✅ Уведомление о счастливом посте #{post_num} отправлено как текст после ошибки медиа.")
                except Exception as final_e:
                    print(f"❌ Финальная попытка отправки текста для #{post_num} также провалилась: {final_e}")
                return # Выходим в любом случае после BadRequest
    except Exception as e:
        import traceback
        print(f"⛔ Не удалось отправить счастливый пост #{post_num} в канал после всех попыток: {e}\n{traceback.format_exc()}")
def get_quick_menu_keyboard(board_id: str, stream: str = 'ru') -> InlineKeyboardMarkup:
    """
    Генерирует главное меню для /start и /help с учетом потока (языка).
    """
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en': btn_wallet = "💰 Wallet"
    elif lang == 'jp': btn_wallet = "💰 財布"
    else: btn_wallet = "💰 Кошелек"
    if lang == 'en':
        btn_profile = "🪪 Profile"
        btn_personal = "⚙️ Settings"
        btn_token = "🔑 Token"
        btn_roll = "🎰 Roulette"
        btn_help = "ℹ️ Help"
        btn_stats = "📊 Stats"
        btn_invite = "📨 Invite"
        btn_admin = "🆘 Admin"
        btn_hent = "🔞 Hentai"
        btn_loli = "🍭 Loli"
    elif lang == 'jp':
        btn_profile = "🪪 プロフ"     # Profile
        btn_personal = "⚙️ 設定"       # Settings
        btn_token = "🔑 トークン"     # Token
        btn_roll = "🎰 ルーレット"    # Roulette
        btn_help = "ℹ️ ヘルプ"       # Help
        btn_stats = "📊 統計"         # Stats
        btn_invite = "📨 招待"        # Invite
        btn_admin = "🆘 管理人"       # Admin
        btn_hent = "🔞 ヘンタイ"      # Hentai
        btn_loli = "🍭 ロリ"          # Loli
    else: # ru
        btn_profile = "🪪 Профиль"
        btn_personal = "⚙️ Настройки"
        btn_token = "🔑 Токен"
        btn_roll = "🎰 Рулетка"
        btn_help = "ℹ️ Помощь"
        btn_stats = "📊 Статистика"
        btn_invite = "📨 Пригласить"
        btn_admin = "🆘 Админ"
        btn_hent = "🔞 Хентай"
        btn_loli = "🍭 Лоли"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_wallet, callback_data="menu_wallet")],
        [InlineKeyboardButton(text=btn_profile, callback_data="menu_profile"), InlineKeyboardButton(text=btn_personal, callback_data="menu_personal")],
        [InlineKeyboardButton(text=btn_roll, callback_data="menu_roll"), InlineKeyboardButton(text=btn_stats, callback_data="menu_stats")],
        [InlineKeyboardButton(text=btn_hent, callback_data="menu_hent"), InlineKeyboardButton(text=btn_loli, callback_data="menu_loli")],
        [InlineKeyboardButton(text=btn_invite, callback_data="menu_invite"), InlineKeyboardButton(text=btn_token, callback_data="menu_token")],
        [InlineKeyboardButton(text=btn_admin, callback_data="menu_admin"), InlineKeyboardButton(text=btn_help, callback_data="menu_help")]
    ])
    return keyboard
def get_personal_menu_keyboard(board_id: str, user_id: int, stream: str = 'ru') -> tuple[str, InlineKeyboardMarkup]:

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
         b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    settings = b_data['user_settings'][user_id]
    nsfw_status = "✅ ON" if settings['nsfw'] else "❌ OFF"
    hidden_words = list(settings['hide'])
    if lang == 'en':
        text = (
            f"<b>👤 Personal Settings</b>\n\n"
            f"🔞 <b>NSFW Spoiler:</b> {nsfw_status}\n"
            f"<i>(Hides all incoming images under a spoiler)</i>\n\n"
            f"🚫 <b>Auto-hide Words ({len(hidden_words)}):</b>\n"
        )
        empty_text = "<i>(List is empty)</i>"
        btn_add = "➕ Add Word"
        btn_del = "➖ Remove Word"
        btn_back = "🔙 Back"
        btn_lang = "🌐 Language"
    elif lang == 'jp':
        text = (
            f"<b>👤 個人設定</b>\n\n"
            f"🔞 <b>NSFWスポイラー:</b> {nsfw_status}\n"
            f"<i>(すべての画像をスポイラーで隠します)</i>\n\n"
            f"🚫 <b>NGワード ({len(hidden_words)}):</b>\n"
        )
        empty_text = "<i>(リストは空です)</i>"
        btn_add = "➕ 追加"
        btn_del = "➖ 削除"
        btn_back = "🔙 戻る"
        btn_lang = "🌐 言語 / Lang"
    else: # ru
        text = (
            f"<b>👤 Личные настройки</b>\n\n"
            f"🔞 <b>NSFW Спойлер:</b> {nsfw_status}\n"
            f"<i>(Скрывает все входящие картинки под спойлер)</i>\n\n"
            f"🚫 <b>Автоскрытие ({len(hidden_words)} слов):</b>\n"
        )
        empty_text = "<i>(Список пуст)</i>"
        btn_add = "➕ Добавить слово"
        btn_del = "➖ Убрать слово"
        btn_back = "🔙 Назад"
        btn_lang = "🌐 Язык / Lang"
    if hidden_words:
        words_preview = ", ".join([f"<code>{escape_html(w)}</code>" for w in hidden_words[:10]])
        text += words_preview
        if len(hidden_words) > 10: text += " ..."
    else:
        text += empty_text
    btn_nsfw = f"🔞 NSFW: {nsfw_status}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_nsfw, callback_data="pers_nsfw_toggle")],
        [InlineKeyboardButton(text=btn_lang, callback_data="pers_lang_switch")],
        [InlineKeyboardButton(text=btn_add, callback_data="pers_hide_add"), InlineKeyboardButton(text=btn_del, callback_data="pers_hide_del")],
        [InlineKeyboardButton(text=btn_back, callback_data="menu_main")]
    ])
    return text, kb
def _get_thread_entry_keyboard(board_id: str, show_history_button: bool = False, stream: str = 'ru') -> InlineKeyboardMarkup:
    """
    Создает и возвращает инлайн-клавиатуру для сообщения о входе в тред.
    """
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        button_good_thread_text = "👍 Good Thread"
        button_leave_text = "Leave Thread"
    elif lang == 'jp':
        button_good_thread_text = "👍 良スレ"
        button_leave_text = "スレッドを出る"
    else:
        button_good_thread_text = "👍 Годный тред"
        button_leave_text = "Выйти из треда"
    keyboard_layout = [
        [
            InlineKeyboardButton(text=button_good_thread_text, callback_data="thread_like_placeholder"),
            InlineKeyboardButton(text=button_leave_text, callback_data="leave_thread")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)
def _is_spam_filtered(text: str, board_id: str, user_id: int) -> bool:
    b_data = board_data.get(board_id)
    if not b_data or not b_data.get('spam_filter_words'): return False
    lower_text = text.lower()
    if any(word in lower_text for word in b_data['spam_filter_words']):
        print(f"🚫 [{board_id}] Спам-фильтр: user {user_id}")
        return True
    return False
async def _send_op_commands_info(bot: Bot, chat_id: int, board_id: str):
    """
    Проверяет, является ли пользователь ОПом, и отправляет ему список команд модерации.
    """
    b_data = board_data[board_id]
    user_s = b_data.get('user_state', {}).get(chat_id, {})
    location = user_s.get('location', 'main')
    if location == 'main':
        return
    thread_info = b_data.get('threads_data', {}).get(location)
    if thread_info and thread_info.get('op_id') == chat_id:
        lang = 'en' if board_id == 'int' else 'ru'
        if lang == 'en':
            op_commands_text = (
                "<b>You are the OP of this thread.</b>\n\n"
                "You have access to moderation commands (reply to a message to use):\n"
                "<code>/mute</code> - Mute user in this thread for 10 minutes.\n"
                "<code>/unmute</code> - Unmute user.\n"
                "<i>(These commands have a 1-minute cooldown)</i>"
            )
        else:
            op_commands_text = (
                "<b>Вы являетесь ОПом этого треда.</b>\n\n"
                "Вам доступны команды модерации (используйте ответом на сообщение):\n"
                "<code>/mute</code> - Замутить пользователя в этом треде на 10 минут.\n"
                "<code>/unmute</code> - Размутить пользователя.\n"
                "<i>(Кулдаун на использование команд - 1 минута)</i>"
            )
        try:
            await asyncio.sleep(0.5)
            await bot.send_message(chat_id, op_commands_text, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            print(f"Не удалось отправить OP-команды пользователю {chat_id}: {e}")
def _get_leave_thread_keyboard(board_id: str, stream: str = 'ru') -> InlineKeyboardMarkup:
    """
    Создает и возвращает инлайн-клавиатуру для сообщения о выходе из треда.
    """
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        button_text = "View Threads"
    elif lang == 'jp':
        button_text = "スレッド一覧"
    else:
        button_text = "Список тредов"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data="show_active_threads")]
    ])
    return keyboard
def _parse_and_split_multi_replies(text: str) -> tuple[list[tuple[int, str]], bool]:
    """
    Парсит текст на предмет мультиответов (>>post_num) и разбивает его на блоки.
    - Игнорирует случаи, когда в тексте меньше двух ссылок >>post_num.
    - Ограничивает количество ответов до 3. 4-й и последующие блоки
      присоединяются к тексту 3-го блока.
    :param text: Исходный текст сообщения.
    :return: Кортеж, где:
             - Первый элемент: список кортежей (post_num, text_chunk).
               Пустой список, если это не мультиответ.
             - Второй элемент: bool флаг, True если сработал лимит в 3 ответа.
    """
    if not text:
        return [], False
    reply_pattern = re.compile(r'>>(\d+)')
    matches = list(reply_pattern.finditer(text))
    limit_hit = False
    if len(matches) < 2:
        return [], False
    blocks = []
    for i, current_match in enumerate(matches):
        try:
            post_num = int(current_match.group(1))
        except (ValueError, IndexError):
            continue # Пропускаем некорректный паттерн
        text_start = current_match.end()
        is_last_match = (i == len(matches) - 1)
        text_end = len(text) if is_last_match else matches[i + 1].start()
        text_chunk = text[text_start:text_end].strip()
        blocks.append((post_num, text_chunk))
    if len(blocks) > 3:
        limit_hit = True
        third_block_content_start_pos = matches[2].end()
        merged_text_content = text[third_block_content_start_pos:].strip()
        merged_third_block = (blocks[2][0], merged_text_content)
        blocks = blocks[:2] + [merged_third_block]
    return blocks, limit_hit
async def reply_notifier_task():
    """
    Фоновая задача, которая проверяет очередь уведомлений об ответах
    и отправляет их пользователям в Telegram.
    """
    await asyncio.sleep(20) 
    while True:
        try:
            notifications = await get_and_clear_notification_queue()
            if notifications:
                async def send_one_notification(note):
                    recipient_id = note['recipient_id']
                    source_post_num = note['source_post_num']
                    reply_post_num = note['reply_post_num']
                    async with storage_lock:
                        source_post_data = messages_storage.get(source_post_num)
                        
                    if not source_post_data: return
                    
                    board_id = source_post_data.get('board_id')
                    if not board_id or board_id not in GLOBAL_BOTS: return
                    
                    bot_instance = GLOBAL_BOTS[board_id]
                    lang = 'en' if board_id == 'int' else 'ru'
                    
                    if lang == 'en':
                        text = f"📢 Someone replied to your post >>{source_post_num} with post >>{reply_post_num}"
                    else:
                        text = f"📢 На ваш пост >>{source_post_num} ответили постом >>{reply_post_num}"
                    try:
                        await bot_instance.send_message(recipient_id, text)
                    except (TelegramForbiddenError, TelegramBadRequest):
                        pass 
                    except Exception as e:
                        print(f"Ошибка уведомления {recipient_id}: {e}")
                tasks = [send_one_notification(n) for n in notifications]
                await asyncio.gather(*tasks)
            await asyncio.sleep(25)
        except asyncio.CancelledError:
            print("ℹ️ Обработчик уведомлений об ответах остановлен.")
            break
        except Exception as e:
            import traceback
            print(f"⛔ ОШИБКА в reply_notifier_task: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(15)
async def sync_boards_with_config():
    """
    Синхронизирует список досок в БД с конфигом BOARD_CONFIG.
    Добавляет недостающие доски при старте бота.
    """
    from common.db_pool import get_pool, db_lock # Локальный импорт
    
    db = await get_pool()
    print("🔄 Синхронизация досок из конфига с базой данных...")
    boards_in_config = list(BOARD_CONFIG.keys())
    insert_query = "INSERT OR IGNORE INTO Boards (board_id, name, description, settings) VALUES (?, ?, ?, '{}')"
    data_to_insert = []
    for board_id, config in BOARD_CONFIG.items():
        desc = config.get('description', '')
        if isinstance(desc, dict):
            desc = json.dumps(desc, ensure_ascii=False)
        data_to_insert.append((
            board_id, 
            config.get('name', board_id), 
            desc
        ))
    
    async with db_lock:
        for attempt in range(10):
            try:
                await db.execute("BEGIN IMMEDIATE")
                await db.executemany(insert_query, data_to_insert)
                await db.execute("COMMIT")
                
                print(f"✅ Синхронизация завершена. В базе данных актуализированы доски: {', '.join(boards_in_config)}")
                return
            except Exception as e:
                try: await db.execute("ROLLBACK")
                except: pass
                
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА при синхронизации досок с БД: {e}")
                break
def _resize_image_if_needed(image_bytes: bytes) -> bytes:
    """
    (СИНХРОННАЯ) Оптимизированная проверка.
    ВАЖНО: Пропускает видео (MP4, WebM) и GIF без изменений, чтобы не ломать кодировку.
    """
    MAX_DIMENSION_SUM = 10000
    MAX_ASPECT_RATIO = 20.0
    MAX_FILE_SIZE_BYTES = 9.5 * 1024 * 1024 
    if not image_bytes: return image_bytes
    header = image_bytes[:12]
    is_media_format = (
        b'ftyp' in header or 
        header.startswith(b'\x1A\x45\xDF\xA3') or 
        header.startswith(b'GIF8')
    )

    if is_media_format:
        return image_bytes

    try:
        input_size = len(image_bytes)
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            format_original = img.format
            if getattr(img, "is_animated", False):
                return image_bytes

            needs_resize_dims = (
                (width + height > MAX_DIMENSION_SUM) or 
                (width / height > MAX_ASPECT_RATIO) or 
                (height / width > MAX_ASPECT_RATIO)
            )
            if not needs_resize_dims and input_size <= MAX_FILE_SIZE_BYTES:
                if format_original == 'PNG' and input_size > 5 * 1024 * 1024:
                    pass 
                else:
                    return image_bytes
            img = img.convert("RGB")
            new_width, new_height = width, height
            if width + height > MAX_DIMENSION_SUM:
                scale_factor = MAX_DIMENSION_SUM / (width + height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
            if new_width / new_height > MAX_ASPECT_RATIO:
                new_width = int(new_height * MAX_ASPECT_RATIO)
            elif new_height / new_width > MAX_ASPECT_RATIO:
                new_height = int(new_width * MAX_ASPECT_RATIO)

            if new_width != width or new_height != height:
                img = img.resize((max(1, new_width), max(1, new_height)), Image.LANCZOS)
            quality = 95
            output_buffer = io.BytesIO()
            img.save(output_buffer, format='JPEG', quality=quality)
            current_size = output_buffer.tell()
            while current_size > MAX_FILE_SIZE_BYTES and quality > 10:
                output_buffer.seek(0)
                output_buffer.truncate(0)
                if quality < 60:
                    img = img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.LANCZOS)
                quality -= 10
                img.save(output_buffer, format='JPEG', quality=quality)
                current_size = output_buffer.tell()
                
            return output_buffer.getvalue()
    except Exception as e:
        return image_bytes
def _contextual_reply_allowed(user_id: int, board_id: str) -> tuple[bool, str | None]:
    if not CONTEXTUAL_REPLIES_ENABLED:
        contextual_reply_stats["skipped_disabled"] += 1
        return False, "disabled"

    now = time.time()
    key = (board_id, user_id)
    item = contextual_reply_tracker[key]

    if CONTEXTUAL_REPLY_DAILY_LIMIT:
        window_start = float(item.get("window_start") or 0.0)
        if now - window_start >= 86400:
            item["window_start"] = now
            item["count"] = 0
        elif int(item.get("count") or 0) >= CONTEXTUAL_REPLY_DAILY_LIMIT:
            contextual_reply_stats["skipped_daily_limit"] += 1
            return False, "daily_limit"

    last_sent = float(item.get("last") or 0.0)
    if CONTEXTUAL_REPLY_COOLDOWN_SEC and now - last_sent < CONTEXTUAL_REPLY_COOLDOWN_SEC:
        contextual_reply_stats["skipped_cooldown"] += 1
        return False, "cooldown"

    item["last"] = now
    if not item.get("window_start"):
        item["window_start"] = now
    item["count"] = int(item.get("count") or 0) + 1
    contextual_reply_stats["sent"] += 1
    return True, None

async def check_and_send_contextual_reply(bot: Bot, user_id: int, text: str, board_id: str, stream: str = 'ru'):
    """
    Проверяет текст на наличие паттернов и отправляет автору личное сообщение.
    Выбирает язык ответов на основе stream.
    """
    if not text or not isinstance(text, str):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        replies_dict = CONTEXTUAL_REPLIES_EN
    elif lang == 'jp':
        replies_dict = CONTEXTUAL_REPLIES_JP
    else:
        replies_dict = CONTEXTUAL_REPLIES
    try:
        for pattern, replies in replies_dict.items():
            is_match = False
            if isinstance(pattern, str):
                if re.search(pattern, text, re.IGNORECASE):
                    is_match = True
            elif hasattr(pattern, 'search'):
                if pattern.search(text):
                    is_match = True
            if is_match:
                allowed, reason = _contextual_reply_allowed(user_id, board_id)
                if not allowed:
                    if reason:
                        runtime_logger.info(
                            "contextual_reply_skip %s",
                            json.dumps(
                                {
                                    "ts": round(time.time(), 3),
                                    "board_id": board_id,
                                    "user_id": user_id,
                                    "reason": reason,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                    return
                response_text = random.choice(replies)
                try:
                    await bot.send_message(user_id, response_text, parse_mode="HTML")
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    contextual_reply_stats["send_errors"] += 1
                    print(f"ℹ️ Не удалось отправить контекстный ответ user {user_id}: {e}")
                return
    except Exception as e:
        print(f"⛔ Ошибка в check_and_send_contextual_reply для user {user_id}: {e}")
async def post_thread_notification_to_channel(bots: dict[str, Bot], board_id: str, thread_id: str, thread_info: dict, event_type: str, details: dict | None = None):
    """
    Отправляет унифицированное уведомление о событиях треда в служебный канал.
    :param bots: Словарь с инстансами ботов.
    :param board_id: ID доски.
    :param thread_id: ID треда.
    :param thread_info: Словарь с данными треда.
    :param event_type: Тип события ('new_thread', 'milestone', 'high_activity').
    :param details: Дополнительная информация (например, {'posts': 150} или {'activity': 25.5}).
    """
    bot_instance = bots.get(ARCHIVE_POSTING_BOT_ID)
    if not bot_instance:
        print(f"⛔ Ошибка: бот для постинга ('{ARCHIVE_POSTING_BOT_ID}') не найден.")
        return
    details = details or {}
    title = escape_html(thread_info.get('title', 'Без названия'))
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
    message_text = ""
    if event_type == 'new_thread':
        message_text = (
            f"<b>🌱 Создан новый тред</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    elif event_type == 'milestone':
        posts_count = details.get('posts', 0)
        message_text = (
            f"<b>📈 Тред набрал {posts_count} постов</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    elif event_type == 'high_activity':
        activity = details.get('activity', 0)
        message_text = (
            f"<b>🔥 Высокая активность в треде ({activity:.1f} п/ч)</b>\n\n"
            f"<b>Доска:</b> {board_name}\n"
            f"<b>Заголовок:</b> {title}"
        )
    else:
        return
    try:
        await bot_instance.send_message(
            chat_id=ARCHIVE_CHANNEL_ID,
            text=message_text,
            parse_mode="HTML"
        )
        print(f"✅ Уведомление о треде '{title}' (событие: {event_type}) отправлено в канал.")
    except Exception as e:
        print(f"⛔ Не удалось отправить уведомление о треде '{title}' в канал: {e}")
def _sync_generate_thread_archive(board_id: str, thread_id: str, thread_info: dict, posts_data: list[dict]) -> str | None:
    """
    Синхронная, потокобезопасная функция для генерации HTML-архива.
    Работает только с переданными ей данными постов.
    """
    try:
        title = escape_html(thread_info.get('title', 'Без названия'))
        filepath = os.path.join(DATA_DIR, f"archive_{board_id}_{thread_id}.html")
        html_style = """
        <style>
            body { font-family: sans-serif; background-color: #f0f0f0; color: #333; line-height: 1.6; margin: 20px; }
            .container { max-width: 800px; margin: auto; background-color: #fff; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            h1 { color: #d00; border-bottom: 2px solid #ccc; padding-bottom: 10px; }
            .post { border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; border-radius: 4px; background-color: #fafafa; }
            .post-header { font-size: 0.9em; color: #888; margin-bottom: 10px; }
            .post-header b { color: #d00; }
            .post-content { white-space: pre-wrap; word-wrap: break-word; }
            .greentext { color: #789922; }
            .reply-link { color: #d00; text-decoration: none; }
        </style>
        """
        html_parts = [
            '<!DOCTYPE html>\n', '<html lang="ru">\n', '<head>\n', '    <meta charset="UTF-8">\n',
            f'    <title>Архив треда: {title}</title>\n', f'    {html_style}\n', '</head>\n',
            '<body>\n', '    <div class="container">\n', f'        <h1>{title}</h1>\n'
        ]
        for post_data in posts_data:
            content = post_data.get('content', {})
            post_num = content.get('post_num', 'N/A')
            timestamp_str = post_data.get('timestamp', '')
            try:
                timestamp_dt = datetime.fromisoformat(timestamp_str)
                timestamp_formatted = timestamp_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except (ValueError, TypeError):
                timestamp_formatted = "N/A"
            post_body = ""
            if content.get('type') == 'text':
                text = clean_html_tags(content.get('text', ''))
                lines = text.split('\n')
                formatted_lines = []
                for line in lines:
                    safe_line = escape_html(line)
                    if safe_line.strip().startswith('&gt;'):
                        formatted_lines.append(f'<span class="greentext">{safe_line}</span>')
                    else:
                        formatted_lines.append(safe_line)
                post_body = "<br>".join(formatted_lines)
            elif content.get('type') in ['photo', 'video', 'animation', 'document', 'audio']:
                media_type_map = {'photo': 'Изображение', 'video': 'Видео', 'animation': 'GIF', 'document': 'Документ', 'audio': 'Аудио'}
                media_type = media_type_map.get(content.get('type'), 'Медиа')
                caption = escape_html(clean_html_tags(content.get('caption', '')))
                post_body = f"<b>[{media_type}]</b><br>{caption}"
            else:
                 post_body = f"<i>[{content.get('type', 'Системное сообщение')}]</i>"
            reply_to = content.get('reply_to_post')
            reply_html = f'<a href="#{reply_to}" class="reply-link">&gt;&gt;{reply_to}</a><br>' if reply_to else ""
            html_parts.append(
                f'        <div class="post" id="{post_num}">\n'
                '            <div class="post-header">\n'
                f'                <b>Пост №{post_num}</b> - {timestamp_formatted}\n'
                '            </div>\n'
                '            <div class="post-content">\n'
                f'                {reply_html}{post_body}\n'
                '            </div>\n'
                '        </div>\n'
            )
        html_parts.extend(['    </div>\n', '</body>\n', '</html>\n'])
        final_html_content = "".join(html_parts)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html_content)
        print(f"✅ [{board_id}] Архив для треда {thread_id} сохранен в {filepath}")
        return filepath
    except Exception as e:
        import traceback
        print(f"⛔ [{board_id}] Ошибка генерации архива для треда {thread_id}: {e}\n{traceback.format_exc()}")
        return None
async def archive_thread(bots: dict[str, Bot], board_id: str, thread_id: str, thread_info: dict):

    posts_data_copy = []
    async with storage_lock:
        post_nums = thread_info.get('posts', [])
        for post_num in post_nums:
            post_data = messages_storage.get(post_num)
            if post_data:
                data_copy = {
                    'content': post_data.get('content', {}).copy(),
                    'timestamp': post_data.get('timestamp', datetime.now(UTC)).isoformat()
                }
                posts_data_copy.append(data_copy)
    loop = asyncio.get_running_loop()
    filepath = await loop.run_in_executor(
        save_executor,
        _sync_generate_thread_archive,
        board_id, thread_id, thread_info, posts_data_copy
    )
    if filepath:
        await post_archive_to_channel(bots, filepath, board_id, thread_info)
    try:
        from common.database import archive_thread_in_db
        await archive_thread_in_db(int(thread_id))
    except Exception as e:
        print(f"❌ Ошибка при архивации треда #{thread_id} в БД: {e}")
@dp.message(Command("cancel"), FSMContext)
async def cmd_cancel_fsm(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Отменяет любое FSM состояние, в котором находится пользователь.
    """
    current_state = await state.get_state()
    if current_state is None:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return
    await state.clear()
    if board_id:
        lang = 'en' if board_id == 'int' else 'ru'
        response_text = random.choice(thread_messages[lang]['create_cancelled'])
        await message.answer(response_text)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
async def thread_lifecycle_manager(bots: dict[str, Bot]):

    while True:
        await asyncio.sleep(60) # Проверка раз в минуту
        now_dt = datetime.now(UTC)
        archives_to_generate = []    # [(board_id, thread_id, thread_info_copy), ...]
        notifications_to_queue = []  # [(board_id, recipients, content, thread_id_or_None), ...]
        async with storage_lock:
            for board_id in THREAD_BOARDS:
                b_data = board_data.get(board_id)
                if not b_data: continue
                threads_data = b_data.get('threads_data', {})
                threads_to_delete = []
                lang = 'en' if board_id == 'int' else 'ru'
                for thread_id, thread_info in threads_data.items():
                    if not thread_info.get('is_archived') and len(thread_info.get('posts', [])) >= MAX_POSTS_PER_THREAD:
                        thread_info['is_archived'] = True
                        archives_to_generate.append((board_id, thread_id, thread_info.copy()))
                        archive_text = random.choice(thread_messages[lang]['thread_archived']).format(
                            limit=MAX_POSTS_PER_THREAD,
                            title=thread_info.get('title', '...')
                        )
                        content = {'type': 'text', 'text': archive_text, 'is_system_message': True}
                        recipients = thread_info.get('subscribers', set())
                        if recipients:
                            notifications_to_queue.append((board_id, recipients, content, thread_id))
                active_threads = {tid: tdata for tid, tdata in threads_data.items() if not tdata.get('is_archived')}
                if len(active_threads) > MAX_ACTIVE_THREADS:
                    num_to_remove = len(active_threads) - MAX_ACTIVE_THREADS
                    oldest_threads = sorted(
                        active_threads.items(),
                        key=lambda item: item[1].get('last_activity_at', 0)
                    )[:num_to_remove]
                    for thread_id, thread_info in oldest_threads:
                        removed_title = thread_info.get('title', '...')
                        removal_text = random.choice(thread_messages[lang]['oldest_thread_removed']).format(title=removed_title)
                        content = {'type': 'text', 'text': removal_text, 'is_system_message': True}
                        main_board_recipients = {uid for uid, u_state in b_data.get('user_state', {}).items() if u_state.get('location', 'main') == 'main'}
                        if main_board_recipients:
                             notifications_to_queue.append((board_id, main_board_recipients, content, None))
                        threads_to_delete.append(thread_id)
                if threads_to_delete:
                    for thread_id in threads_to_delete:
                        threads_data.pop(thread_id, None)
                        b_data.get('thread_locks', {}).pop(thread_id, None)
                    print(f"🧹 [{board_id}] Удалено {len(threads_to_delete)} старых тредов из состояния.")
                threads_to_purge = []
                now_ts = time.time()
                ARCHIVE_LIFETIME_SECONDS = 24 * 3600  # 24 часа
                for thread_id, thread_info in threads_data.items():
                    if thread_info.get('is_archived'):
                        last_activity = thread_info.get('last_activity_at', 0)
                        if (now_ts - last_activity) > ARCHIVE_LIFETIME_SECONDS:
                            threads_to_purge.append(thread_id)
                if threads_to_purge:
                    for thread_id in threads_to_purge:
                        threads_data.pop(thread_id, None)
                        b_data.get('thread_locks', {}).pop(thread_id, None)
                    print(f"🧹 [{board_id}] Очищено {len(threads_to_purge)} старых заархивированных тредов из памяти.")
        for board_id, thread_id, thread_info_copy in archives_to_generate:
            asyncio.create_task(archive_thread(bots, board_id, thread_id, thread_info_copy))
        for board_id, recipients, content, thread_id in notifications_to_queue:
            try:
                pnum = await create_post(
                    board_id=board_id, author_id=0, content=content,
                    timestamp=now_dt.timestamp(), is_from_site=False, stream='ru',
                    thread_id_from_bot=thread_id
                )
                if not pnum:
                    print(f"⛔ [{board_id}] Не удалось создать пост в БД для уведомления в thread_lifecycle_manager.")
                    continue
                b_data = board_data[board_id]
                if thread_id: # Уведомление для подписчиков треда
                    thread_info = b_data.get('threads_data', {}).get(thread_id)
                    if thread_info:
                        header = await format_header(board_id, pnum)
                        content['header'] = header
                else: # Уведомление на главную доску
                    header = await format_header(board_id, pnum)
                    content['header'] = header
                await update_post_content(pnum, content)
                async with storage_lock:
                    messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id, 'thread_id': thread_id}
                await enqueue_board_message(board_id, {
                    'recipients': recipients, 'content': content, 'post_num': pnum,
                    'board_id': board_id, 'thread_id': thread_id
                })
            except Exception as e:
                 print(f"❌ Ошибка при постановке уведомления в очередь в thread_lifecycle_manager: {e}")
async def thread_activity_monitor(bots: dict[str, Bot]):
    """
    Фоновая задача для отслеживания активности тредов и уведомления о высокой активности.
    """
    await asyncio.sleep(120)  # Начальная задержка 2 минуты
    while True:
        try:
            await asyncio.sleep(600)  # Проверка каждые 10 минут
            thread_posts_by_board = defaultdict(lambda: defaultdict(list))
            async with storage_lock:
                one_hour_ago_for_check = datetime.now(UTC) - timedelta(hours=1)
                for post_data in messages_storage.values():
                    timestamp = post_data.get('timestamp')
                    if timestamp and timestamp > one_hour_ago_for_check:
                        board_id = post_data.get('board_id')
                        thread_id = post_data.get('thread_id')
                        if board_id in THREAD_BOARDS and thread_id:
                            thread_posts_by_board[board_id][thread_id].append(1)
            for board_id in THREAD_BOARDS:
                b_data = board_data.get(board_id)
                if not b_data:
                    continue
                threads_data = b_data.get('threads_data', {})
                for thread_id, thread_info in threads_data.items():
                    if thread_info.get('is_archived') or thread_info.get('activity_notified'):
                        continue
                    recent_posts_count = len(thread_posts_by_board.get(board_id, {}).get(thread_id, []))
                    ACTIVITY_THRESHOLD = 15
                    if recent_posts_count >= ACTIVITY_THRESHOLD:
                        thread_info['activity_notified'] = True
                        asyncio.create_task(post_thread_notification_to_channel(
                            bots=bots,
                            board_id=board_id,
                            thread_id=thread_id,
                            thread_info=thread_info,
                            event_type='high_activity',
                            details={'activity': float(recent_posts_count)}
                        ))
        except Exception as e:
            print(f"❌ Ошибка в thread_activity_monitor: {e}")
            await asyncio.sleep(120) # В случае ошибки ждем дольше перед повторной попыткой
async def memory_logger_task():

    await asyncio.sleep(80) #1.5 минут
    while True:
        try:
            await log_memory_summary()
            await asyncio.sleep(1500)
        except Exception as e:
            print(f"Критическая ошибка в memory_logger_task: {e}")
            await asyncio.sleep(600)
async def runtime_telemetry_task():

    await asyncio.sleep(60)
    previous_private_mb = None
    while True:
        try:
            await _refresh_db_file_snapshot_cache()
            snapshot = _collect_runtime_snapshot()
            memory = snapshot.get("memory", {})
            queues = snapshot.get("queues", {})
            maps = snapshot.get("maps", {})
            private_mb = memory.get("private_mb")
            private_delta = None
            if isinstance(private_mb, (int, float)) and isinstance(previous_private_mb, (int, float)):
                private_delta = round(private_mb - previous_private_mb, 2)
            if isinstance(private_mb, (int, float)):
                previous_private_mb = private_mb
            runtime_logger.info(
                "runtime_snapshot %s",
                json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            )
            warnings = []
            if isinstance(private_mb, (int, float)) and private_mb > MEMORY_LIMIT_GB * 1024 * 0.75:
                warnings.append(f"private_mb={private_mb}")
            if queues.get("total", 0) > TELEMETRY_WARN_QUEUE_TOTAL:
                warnings.append(f"queue_total={queues.get('total')}")
            if maps.get("pending_edit_done", 0) > TELEMETRY_WARN_DONE_EDIT_TASKS:
                warnings.append(f"done_edit_tasks={maps.get('pending_edit_done')}")
            if maps.get("current_media_groups", 0) > TELEMETRY_WARN_MEDIA_GROUPS:
                warnings.append(f"media_groups={maps.get('current_media_groups')}")
            top_queue = ", ".join(f"{board}:{size}" for board, size in queues.get("top", [])) or "empty"
            line = (
                f"[runtime] private={private_mb}MB "
                f"delta={private_delta}MB queues={queues.get('total', 0)} top={top_queue} "
                f"maps=({maps.get('messages_storage')}/{maps.get('post_to_messages')}/{maps.get('message_to_post')}) "
                f"wal={snapshot.get('db_files', {}).get('wal_mb')}MB"
            )
            if warnings:
                runtime_logger.warning("runtime_warning %s %s", ",".join(warnings), line)
                print(f"⚠️ {line}")
            else:
                print(line)
        except Exception as e:
            runtime_logger.exception("runtime_telemetry_failed")
            print(f"⚠️ runtime_telemetry_task error: {e}")
        await asyncio.sleep(TELEMETRY_INTERVAL_SEC)
async def weekly_active_refresh_task():

    if not PRIORITY_DELIVERY_ENABLED:
        while True:
            await asyncio.sleep(WEEKLY_ACTIVE_REFRESH_SECONDS)
    while True:
        try:
            refreshed_at = time.time()
            counts = {}
            for board_id in BOARDS:
                users = await get_weekly_active_users(board_id, WEEKLY_ACTIVE_DAYS)
                weekly_active_users[board_id] = users
                weekly_active_updated_at[board_id] = refreshed_at
                counts[board_id] = len(users)
            total = sum(counts.values())
            top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
            runtime_logger.info(
                "weekly_active_refresh %s",
                json.dumps(
                    {
                        "days": WEEKLY_ACTIVE_DAYS,
                        "total": total,
                        "by_board": counts,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            top_text = ", ".join(f"{board}:{count}" for board, count in top)
            print(f"[priority] weekly active {WEEKLY_ACTIVE_DAYS}d: total={total} top={top_text}")
        except Exception:
            runtime_logger.exception("weekly_active_refresh_failed")
        await asyncio.sleep(WEEKLY_ACTIVE_REFRESH_SECONDS)
async def reply_coverage_refresh_task():

    global reply_coverage_stats, reply_coverage_updated_at
    while True:
        try:
            stats = await get_reply_coverage_stats()
            reply_coverage_stats = stats
            reply_coverage_updated_at = time.time()
            runtime_logger.info(
                "reply_coverage %s",
                json.dumps(
                    {
                        "total_copies": stats.get("total_copies", 0),
                        "copy_posts": stats.get("copy_posts", 0),
                        "min_post": stats.get("min_post"),
                        "max_post": stats.get("max_post"),
                        "latest_post": stats.get("latest_post"),
                        "gap_from_latest": stats.get("gap_from_latest"),
                        "top_boards": dict(
                            sorted(
                                stats.get("by_board", {}).items(),
                                key=lambda item: item[1].get("copy_posts", 0),
                                reverse=True,
                            )[:8]
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        except Exception:
            runtime_logger.exception("reply_coverage_refresh_failed")
        await asyncio.sleep(REPLY_COVERAGE_REFRESH_SECONDS)
async def memory_restarter(bots: list[Bot], healthcheck_site: web.TCPSite | None):
    """
    Мониторинг памяти. При превышении лимита сохраняет данные и завершает процесс.
    Перезапуск должен выполнять внешний скрипт (loop.bat).
    """
    process = psutil.Process(os.getpid())
    MEMORY_LIMIT_BYTES = MEMORY_LIMIT_GB * 1024 * 1024 * 1024
    print(f"✅ Мониторинг памяти запущен. Лимит: {MEMORY_LIMIT_GB} ГБ")
    while True:
        await asyncio.sleep(60)
        try:
            info = process.memory_info()
            rss_usage = getattr(info, "rss", 0)
            try:
                full_info = process.memory_full_info()
                private_usage = (
                    getattr(full_info, "private", None)
                    or getattr(full_info, "uss", None)
                    or rss_usage
                )
            except Exception:
                private_usage = rss_usage
            mem_usage = max(rss_usage, private_usage)
        except Exception:
            break
        if mem_usage > MEMORY_LIMIT_BYTES:
            print(f"⛔ ПАМЯТЬ ПЕРЕПОЛНЕНА ({mem_usage / 1024**3:.2f} ГБ). АВАРИЙНАЯ ОСТАНОВКА.")
            try:
                runtime_logger.critical(
                    "memory_limit_exceeded %s",
                    json.dumps(_collect_runtime_snapshot(), ensure_ascii=False, separators=(",", ":"))
                )
            except Exception:
                pass
            try:
                await asyncio.wait_for(
                    graceful_shutdown(bots, healthcheck_site, emergency=True),
                    timeout=15.0
                )
            except Exception as e:
                print(f"⚠️ Ошибка при остановке: {e}")
            print("💀 KILL PROCESS")
            import signal
            os.kill(os.getpid(), signal.SIGINT)
@dp.message(ThreadCreateStates.waiting_for_op_post, (F.text | F.caption))
async def process_op_post_text(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Ловит текст или медиа с подписью для ОП-поста,
    очищает его и переводит на этап подтверждения.
    """
    if not board_id: return
    lang = 'en' if board_id == 'int' else 'ru'
    raw_html_text = ""
    if message.text:
        raw_html_text = message.html_text
    elif message.caption:
        raw_html_text = message.caption_html_text
    if not raw_html_text:
        await state.clear()
        if lang == 'en':
            error_text = "Post text is empty. Please start over."
        elif lang == 'jp':
            error_text = "本文が空です。最初からやり直してください。"
        else:
            error_text = "Текст поста пуст. Начните заново."
        await message.answer(error_text)
        return
    safe_html_text = sanitize_html(raw_html_text)
    await state.update_data(op_post_text=safe_html_text)
    await state.set_state(ThreadCreateStates.waiting_for_confirmation)
    if lang == 'en':
        confirmation_text = f"You want to create a thread with this opening post:\n\n---\n{safe_html_text}\n---\n\nCreate?"
        button_create = "✅ Create Thread"
        button_edit = "✏️ Edit Text"
    elif lang == 'jp':
        confirmation_text = f"以下の内容でスレッドを作成しますか？\n\n---\n{safe_html_text}\n---\n\n作成しますか？"
        button_create = "✅ スレ作成"
        button_edit = "✏️ 編集"
    else:
        confirmation_text = f"Вы хотите создать тред с таким ОП-постом:\n\n---\n{safe_html_text}\n---\n\nСоздаем?"
        button_create = "✅ Создать тред"
        button_edit = "✏️ Редактировать"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=button_create, callback_data="create_thread_confirm"),
            InlineKeyboardButton(text=button_edit, callback_data="create_thread_edit")
        ]
    ])
    await message.answer(confirmation_text, reply_markup=keyboard, parse_mode="HTML")
@dp.message(ThreadCreateStates.waiting_for_op_post)
async def process_op_post_invalid(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает некорректный ввод (не текст) в состоянии ожидания ОП-поста.
    """
    if not board_id: return
    lang = 'en' if board_id == 'int' else 'ru'
    response_text = random.choice(thread_messages[lang]['create_invalid_input'])
    try:
        await message.answer(response_text)
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
@dp.callback_query(F.data == "create_thread_start")
async def cb_create_thread_start(callback: types.CallbackQuery, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Запускает процесс создания треда.
    """
    if not board_id or board_id not in THREAD_BOARDS:
        try: await callback.answer("Not available.", show_alert=True)
        except: pass
        return
    lang = 'en' if board_id == 'int' else 'ru'
    await state.set_state(ThreadCreateStates.waiting_for_op_post)
    prompt_phrases = thread_messages.get(lang, {}).get('create_prompt_op_post', [])
    if lang == 'en':
        default_prompt = "Please send the text for your opening post."
    elif lang == 'jp':
        default_prompt = "スレッドの本文（OP）を送信してください。"
    else:
        default_prompt = "Отправьте текст для вашего ОП-поста."
    prompt_text = random.choice(prompt_phrases) if prompt_phrases else default_prompt
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass # Игнорируем, если кнопка устарела, главное отправить сообщение
    if isinstance(callback.message, types.Message):
        try:
            await callback.message.answer(prompt_text)
            await callback.message.delete()
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
@dp.callback_query(F.data.startswith("threads_page_"))
async def cq_threads_page(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает пагинацию списка тредов.
    Исправлено: Защита от краша при клике на старые кнопки.
    """
    if not board_id or board_id not in THREAD_BOARDS: return
    user_id = callback.from_user.id
    now = time.time()
    if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
        try:
            await callback.answer("Слишком быстро! / Too fast!", show_alert=False)
        except TelegramBadRequest:
            pass
        return
    user_last_thread_action[user_id] = now
    try:
        page = int(callback.data.split("_")[-1])
        text, keyboard = await generate_threads_page(board_id, user_id, page=0, stream=stream)
        if not text:
            try:
                await callback.answer("Не удалось загрузить страницу.", show_alert=True)
            except TelegramBadRequest: pass
            return
        is_pagination_action = False
        if callback.message and callback.message.text:
             txt = callback.message.text
             is_pagination_action = txt.startswith("📋") # Универсальный маркер
        if is_pagination_action:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass # Сообщение уже удалено или слишком старое
            await callback.bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")
    except (ValueError, IndexError):
        try:
            await callback.answer("Ошибка данных.", show_alert=True)
        except: pass
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower() and "query is too old" not in str(e).lower():
             print(f"Ошибка в cq_threads_page: {e}")
    except Exception as e:
        print(f"Критическая ошибка в cq_threads_page: {e}")
    finally:
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass
@dp.callback_query(F.data.startswith("view_thread_"))
async def cq_view_thread(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):

    if not board_id or board_id not in THREAD_BOARDS: return
    user_id = callback.from_user.id
    now = time.time()
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if now - user_last_thread_action.get(user_id, 0) < THREAD_VIEWER_COOLDOWN:
        alert_text = "Too fast!" if lang=='en' else ("早すぎます！" if lang=='jp' else "Слишком быстро!")
        try:
            await callback.answer(alert_text, show_alert=False)
        except TelegramBadRequest: pass
        return
    user_last_thread_action[user_id] = now
    try:
        parts = callback.data.split("_")
        op_post_num = int(parts[2])
        return_page = int(parts[3])
    except (ValueError, IndexError):
        try: await callback.answer("Invalid ID", show_alert=True)
        except: pass
        return
    load_txt = "Loading..." if lang == 'en' else ("読み込み中..." if lang == 'jp' else "Загрузка...")
    try:
        await callback.answer(load_txt)
    except TelegramBadRequest:
        pass # Игнорируем, если запрос устарел, главное показать тред
    thread_data = await get_thread_by_op_post(op_post_num)
    if not thread_data:
        err_txt = "Thread not found." if lang == 'en' else ("スレッドが見つかりません。" if lang == 'jp' else "Тред не найден.")
        try: await callback.message.answer(err_txt)
        except: pass
        return
    thread_chunks = await format_thread_for_telegram(*thread_data)
    if lang == 'en': back_txt = "« Back"
    elif lang == 'jp': back_txt = "« 戻る"
    else: back_txt = "« Назад"
    back_button = InlineKeyboardButton(text=back_txt, callback_data=f"threads_page_{return_page}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    try:
        if callback.message:
            await callback.message.delete()
        for i, chunk in enumerate(thread_chunks):
            reply_markup = keyboard if i == len(thread_chunks) - 1 else None
            await callback.bot.send_message(
                chat_id=user_id, text=chunk, parse_mode="HTML",
                reply_markup=reply_markup, disable_web_page_preview=True
            )
            if len(thread_chunks) > 1: await asyncio.sleep(0.3)
    except Exception as e:
        print(f"Error viewing thread: {e}")
@dp.callback_query(F.data.startswith("show_history_"))
async def cq_thread_history(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):

    if not board_id or board_id not in THREAD_BOARDS:
        try: await callback.answer("N/A", show_alert=True)
        except: pass
        return
    try:
        thread_id = callback.data.split("_")[-1]
    except (ValueError, IndexError):
        try: await callback.answer("Invalid thread ID", show_alert=True)
        except: pass
        return
    user_id = callback.from_user.id
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    tm_lang = thread_messages.get(lang, thread_messages.get('en', {}))
    user_s = b_data['user_state'].setdefault(user_id, {})
    now_ts = time.time()
    last_history_req = user_s.get('last_history_request', 0)
    if now_ts - last_history_req < THREAD_HISTORY_COOLDOWN:
        cooldown_phrases = tm_lang.get('history_cooldown', ["Cooldown! Wait a bit."])
        cooldown_msg = random.choice(cooldown_phrases)
        try:
            await callback.answer(cooldown_msg, show_alert=True)
        except TelegramBadRequest:
            pass
        return
    thread_info = b_data.get('threads_data', {}).get(thread_id)
    if not thread_info:
        not_found_phrases = tm_lang.get('thread_not_found', ["Thread not found."])
        not_found_msg = random.choice(not_found_phrases)
        try:
            await callback.answer(not_found_msg, show_alert=True)
        except TelegramBadRequest: pass
        return
    user_s['last_history_request'] = now_ts
    load_txt = "⏳ Loading history..." if lang == 'en' else ("⏳ 履歴を読み込んでいます..." if lang == 'jp' else "⏳ Загружаю историю...")
    try:
        await callback.answer(load_txt)
    except TelegramBadRequest:
        pass # Игнорируем, главное отправить историю
    temp_user_state = user_s.copy()
    temp_user_state.setdefault('last_seen_threads', {})[thread_id] = 0
    b_data['user_state'][user_id] = temp_user_state
    await send_missed_messages(callback.bot, board_id, user_id, thread_id, stream=stream)
async def _enter_thread_logic(bot: Bot, board_id: str, user_id: int, thread_id: str, message_to_delete: types.Message | None = None, stream: str = 'ru'):
    """
    Универсальная и правильная логика для входа пользователя в тред.
    """
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    tm_lang = thread_messages.get(lang, thread_messages.get('en', {}))
    threads_data = b_data.get('threads_data', {})
    if thread_id not in threads_data:
        return
    user_s = b_data['user_state'].setdefault(user_id, {})
    now_ts = time.time()
    last_switch = user_s.get('last_location_switch', 0)
    if now_ts - last_switch < LOCATION_SWITCH_COOLDOWN:
        cooldown_phrases = tm_lang.get('location_switch_cooldown', ["Too fast!"])
        cooldown_msg = random.choice(cooldown_phrases)
        try:
            sent_msg = await bot.send_message(user_id, cooldown_msg)
            asyncio.create_task(delete_message_after_delay(sent_msg, 5))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return
    current_location = user_s.get('location', 'main')
    if current_location == thread_id:
        return
    if current_location == 'main':
        user_s['last_seen_main'] = state.get('post_counter', 0)
    user_s['location'] = thread_id
    await update_user_location(user_id, board_id, thread_id)
    user_s['last_location_switch'] = now_ts
    threads_data[thread_id].setdefault('subscribers', set()).add(user_id)
    if message_to_delete:
        try:
            await message_to_delete.delete()
        except TelegramBadRequest:
            pass
    was_missed, show_history_button = await send_missed_messages(bot, board_id, user_id, thread_id, stream=stream)
    if not was_missed:
        thread_title = threads_data[thread_id].get('title', '...')
        seen_threads = user_s.setdefault('last_seen_threads', {})
        if thread_id not in seen_threads:
            prompt_phrases = tm_lang.get('enter_thread_prompt', [f"Entered: {thread_title}"])
            response_text = random.choice(prompt_phrases).format(title=thread_title)
        else:
            success_phrases = tm_lang.get('enter_thread_success', [f"Returned: {thread_title}"])
            response_text = random.choice(success_phrases).format(title=thread_title)
        entry_keyboard = _get_thread_entry_keyboard(board_id, show_history_button, stream=stream)
        try:
            await bot.send_message(user_id, response_text, reply_markup=entry_keyboard, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    await _send_op_commands_info(bot, user_id, board_id)
@dp.callback_query(F.data.startswith("enter_thread_"))
async def cq_enter_thread(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):

    if not board_id or board_id not in THREAD_BOARDS:
        try: await callback.answer("N/A", show_alert=True)
        except: pass
        return
    try:
        thread_id = callback.data.split("_")[-1]
    except (ValueError, IndexError):
        try: await callback.answer("Invalid thread ID", show_alert=True)
        except: pass
        return
    user_id = callback.from_user.id
    message_to_delete = callback.message if isinstance(callback.message, types.Message) else None
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass # Если запрос устарел, всё равно пытаемся войти
    await _enter_thread_logic(
        bot=callback.bot,
        board_id=board_id,
        user_id=user_id,
        thread_id=thread_id,
        message_to_delete=message_to_delete,
        stream=stream
    )
@dp.callback_query(F.data == "leave_thread")
async def cb_leave_thread(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает выход из треда.
    Исправлено: Защита от сбоев API при удалении старых сообщений.
    """
    if not board_id or board_id not in THREAD_BOARDS:
        try:
            await callback.answer("This action is not available here.", show_alert=True)
        except TelegramBadRequest: pass
        return
    if not isinstance(callback.message, types.Message):
        try: await callback.answer()
        except TelegramBadRequest: pass
        return
    user_id = callback.from_user.id
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass # Игнорируем, продолжаем выполнение логику выхода
    user_s = b_data['user_state'].setdefault(user_id, {})
    current_location = user_s.get('location', 'main')
    if current_location == 'main':
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        return
    thread_id = current_location
    thread_info = b_data.get('threads_data', {}).get(thread_id)
    if thread_info:
        last_thread_post = thread_info.get('posts', [0])[-1] if thread_info.get('posts') else 0
        user_s.setdefault('last_seen_threads', {})[thread_id] = last_thread_post
    user_s['location'] = 'main'
    await update_user_location(user_id, board_id, 'main')
    user_s['last_location_switch'] = time.time()
    response_phrases = thread_messages.get(lang, {}).get('leave_thread_success', [])
    if lang == 'en':
        default_response_text = "You have returned to the main board."
    elif lang == 'jp':
        default_response_text = "メイン板に戻りました。"
    else:
        default_response_text = "Вы вернулись на основную доску."
    response_text = random.choice(response_phrases) if response_phrases else default_response_text
    leave_keyboard = _get_leave_thread_keyboard(board_id, stream=stream)
    try:
        await callback.message.answer(response_text, reply_markup=leave_keyboard)
    except Exception:
        pass # Если не удалось отправить, юзер все равно перемещен логически
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_missed_messages(callback.bot, board_id, user_id, 'main', stream=stream)
@dp.message(Command("leave"))
async def cmd_leave(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if board_id not in THREAD_BOARDS:
        try: await message.delete()
        except Exception: pass
        return
    user_id = message.from_user.id
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    user_s = b_data['user_state'].setdefault(user_id, {})
    current_location = user_s.get('location', 'main')
    if current_location == 'main':
        await message.delete()
        return
    now_ts = time.time()
    last_switch = user_s.get('last_location_switch', 0)
    if now_ts - last_switch < LOCATION_SWITCH_COOLDOWN:
        cooldown_phrases = thread_messages.get(lang, {}).get('location_switch_cooldown', [])
        if lang == 'en':
            default_cooldown_text = "Switching locations too fast, please wait."
        elif lang == 'jp':
            default_cooldown_text = "移動が速すぎます、少し待ってください。"
        else:
            default_cooldown_text = "Слишком частое переключение, подождите."
        cooldown_text = random.choice(cooldown_phrases) if cooldown_phrases else default_cooldown_text
        await message.answer(cooldown_text)
        await message.delete()
        return
    thread_id = current_location
    thread_info = b_data.get('threads_data', {}).get(thread_id)
    if thread_info:
        last_thread_post = thread_info.get('posts', [0])[-1] if thread_info.get('posts') else 0
        user_s.setdefault('last_seen_threads', {})[thread_id] = last_thread_post
    user_s['location'] = 'main'
    await update_user_location(user_id, board_id, 'main')
    user_s['last_location_switch'] = now_ts
    await message.delete()
    await send_missed_messages(message.bot, board_id, user_id, 'main', stream=stream)
    response_phrases = thread_messages.get(lang, {}).get('leave_thread_success', [])
    if lang == 'en':
        default_response_text = "You have returned to the main board."
    elif lang == 'jp':
        default_response_text = "メイン板に戻りました。"
    else:
        default_response_text = "Вы вернулись на основную доску."
    response_text = random.choice(response_phrases) if response_phrases else default_response_text
    leave_keyboard = _get_leave_thread_keyboard(board_id, stream=stream)
    await message.answer(response_text, reply_markup=leave_keyboard)
@dp.message(Command("mute"))
async def cmd_mute(message: Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not is_adm:
        if board_id not in THREAD_BOARDS:
            return 
        b_data = board_data[board_id]
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main': return
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info or thread_info.get('op_id') != user_id: return
        now_ts = time.time()
        if now_ts - user_s.get('last_op_command_ts', 0) < OP_COMMAND_COOLDOWN:
            await message.delete(); return
        user_s['last_op_command_ts'] = now_ts
        if not message.reply_to_message: await message.delete(); return
        target_id = None
        async with storage_lock: target_id = await get_author_id_by_reply(message)
        if not target_id: await message.delete(); return
        thread_info.setdefault('local_mutes', {})[target_id] = time.time() + 600 # 10 минут
        resp = random.choice(thread_messages[lang]['op_mute_success'])
        await message.answer(f"🔇 {resp}"); await message.delete()
        return
    args = message.text.split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        async with storage_lock: target_id = await get_author_id_by_reply(message)
        if args: duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1: duration_str = args[1]
        except ValueError: pass
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/mute &lt;id&gt; [time]</code>"
        elif lang == 'jp':
            usage = "使用法: <code>/mute &lt;ID&gt; [時間]</code>"
        else:
            usage = "Использование: <code>/mute &lt;id&gt; [время]</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        multipliers = {'m': 60, 'h': 3600, 'd': 86400}
        unit = duration_str[-1]
        if unit in multipliers:
            val = int(duration_str[:-1])
            mult = multipliers[unit]
        else:
            val = int(duration_str)
            mult = 60
        mute_seconds = min(val * mult, 2592000) 
        if mute_seconds < 3600: 
            duration_text = f"{mute_seconds // 60} m" if lang=='en' else (f"{mute_seconds // 60}分" if lang=='jp' else f"{mute_seconds // 60} мин")
        elif mute_seconds < 86400: 
            duration_text = f"{mute_seconds // 3600} h" if lang=='en' else (f"{mute_seconds // 3600}時間" if lang=='jp' else f"{mute_seconds // 3600} час")
        else: 
            duration_text = f"{mute_seconds // 86400} d" if lang=='en' else (f"{mute_seconds // 86400}日" if lang=='jp' else f"{mute_seconds // 86400} дн")
    except (ValueError, IndexError):
        await message.answer("Error format." if lang != 'ru' else "Неверный формат времени."); return
    deleted = await delete_user_posts(message.bot, target_id, 5, board_id)
    async with storage_lock:
        board_data[board_id]['mutes'][target_id] = datetime.now(UTC) + timedelta(seconds=mute_seconds)
    await apply_regular_mute(target_id, board_id, mute_seconds)
    await log_global_event('bot', f"🔇 MUTE: Мод {message.from_user.id} замутил {target_id} на /{board_id}/ на {duration_text}")
    if lang == 'en':
        msg = f"🔇 User <code>{target_id}</code> muted for {duration_text}. Deleted: {deleted}"
    elif lang == 'jp':
        msg = f"🔇 ユーザー <code>{target_id}</code> を {duration_text} ミュートしました。削除: {deleted}"
    else:
        msg = f"🔇 Юзер <code>{target_id}</code> замучен на {duration_text}. Удалено: {deleted}"
    await message.answer(msg, parse_mode="HTML")
    await send_moderation_notice(target_id, "mute", board_id, duration=duration_text, deleted_posts=deleted, stream=stream)
    try: await message.delete()
    except: pass
@dp.message(Command("unmute"))
async def cmd_unmute(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not is_adm:
        if board_id not in THREAD_BOARDS: return
        b_data = board_data[board_id]
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main': return
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info or thread_info.get('op_id') != user_id: return
        if not message.reply_to_message: await message.delete(); return
        target_id = None
        async with storage_lock: target_id = await get_author_id_by_reply(message)
        if not target_id: await message.delete(); return
        if target_id in thread_info.get('local_mutes', {}):
            del thread_info['local_mutes'][target_id]
            resp = random.choice(thread_messages[lang]['op_unmute_success'])
            await message.answer(f"🔊 {resp}")
        await message.delete()
        return
    target_id = None
    if message.reply_to_message:
        async with storage_lock: target_id = await get_author_id_by_reply(message)
    else:
        parts = message.text.split()
        if len(parts) == 2 and parts[1].isdigit(): target_id = int(parts[1])
    if not target_id:
        msg = "Need ID or reply." if lang == 'en' else ("IDまたは返信が必要です。" if lang == 'jp' else "Нужен ID или реплай.")
        await message.answer(msg); return
    unmuted = False
    async with storage_lock:
        if board_data[board_id]['mutes'].pop(target_id, None): unmuted = True
    await remove_regular_mute(target_id, board_id)
    if unmuted: 
        if lang == 'en': txt = f"🔊 User {target_id} unmuted."
        elif lang == 'jp': txt = f"🔊 ユーザー {target_id} のミュートを解除しました。"
        else: txt = f"🔊 Пользователь {target_id} размучен."
        await message.answer(txt)
    else: 
        if lang == 'en': txt = f"User {target_id} was not muted."
        elif lang == 'jp': txt = f"ユーザー {target_id} はミュートされていません。"
        else: txt = f"Пользователь {target_id} не был в муте."
        await message.answer(txt)
    try: await message.delete()
    except: pass
@dp.message(Command("shadowmute"))
async def cmd_shadowmute(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = message.text.split()[1:]
    target_id = None
    duration_str = "24h"
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
        if args:
            duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1:
                duration_str = args[1]
        except ValueError:
            pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/shadowmute &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute &lt;user_id&gt; [время]</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
        total_seconds = min(total_seconds, 2592000)
        expires_dt = datetime.now(UTC) + timedelta(seconds=total_seconds)
        async with storage_lock:
            b_data = board_data[board_id]
            b_data['shadow_mutes'][target_id] = expires_dt
        await update_shadow_mute(target_id, board_id, expires_dt.timestamp())
        await log_global_event('bot', f"👻 SHADOWMUTE: Мод {message.from_user.id} скрыл {target_id} на /{board_id}/ до {expires_dt.strftime('%H:%M:%S')}")
        board_name = BOARD_CONFIG[board_id]['name']
        if lang == 'en':
            msg = f"👻 Shadowmuted user <code>{target_id}</code> for {time_str} on {board_name}."
        elif lang == 'jp':
            msg = f"👻 ユーザー <code>{target_id}</code> を {board_name} で {time_str} シャドウミュートしました。"
        else:
            msg = f"👻 Тихо замучен пользователь <code>{target_id}</code> на {time_str} на доске {board_name}."
        await message.answer(msg, parse_mode="HTML")
    except ValueError:
        err = "❌ Invalid format. Ex: <code>30m</code>, <code>2h</code>" if lang == 'en' else "❌ Неверный формат времени. Примеры: <code>30m</code>, <code>2h</code>, <code>1d</code>"
        await message.answer(err, parse_mode="HTML")
    await message.delete()
@dp.message(Command("nsfw"))
async def cmd_nsfw(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = message.text.split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    current_status = b_data['user_settings'][user_id]['nsfw']
    if len(args) < 2:
        status_on = "ON"
        status_off = "OFF"
        if lang == 'en':
            msg = f"Current NSFW Spoiler status: <b>{status_on if current_status else status_off}</b>.\nUsage: <code>/nsfw on</code> or <code>/nsfw off</code>"
        elif lang == 'jp':
            msg = f"現在のNSFW設定: <b>{status_on if current_status else status_off}</b>\n使い方: <code>/nsfw on</code> または <code>/nsfw off</code>"
        else:
            msg = f"Текущий статус NSFW спойлера: <b>{status_on if current_status else status_off}</b>.\nИспользование: <code>/nsfw on</code> или <code>/nsfw off</code>"
        await message.answer(msg, parse_mode="HTML")
        return
    action = args[1].lower()
    new_status = None
    if action in ['on', 'enable', '1', 'вкл']:
        new_status = True
    elif action in ['off', 'disable', '0', 'выкл']:
        new_status = False
    if new_status is not None:
        b_data['user_settings'][user_id]['nsfw'] = new_status
        asyncio.create_task(update_user_settings_db(user_id, board_id, nsfw=1 if new_status else 0))
        if lang == 'en':
            reply = "✅ NSFW Spoilers enabled." if new_status else "☑️ NSFW Spoilers disabled."
        elif lang == 'jp':
            reply = "✅ NSFWスポイラーを有効にしました。" if new_status else "☑️ NSFWスポイラーを無効にしました。"
        else:
            reply = "✅ Спойлеры для картинок включены." if new_status else "☑️ Спойлеры для картинок выключены."
        await message.answer(reply)
    else:
        err = "Error: Use 'on' or 'off'." if lang != 'ru' else "Ошибка: Используйте 'on' или 'off'."
        await message.answer(err)
@dp.message(Command("hide"))
async def cmd_hide(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    args = message.text.split()
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if user_id not in b_data.get('user_settings', {}):
        b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
    user_hide_set = b_data['user_settings'][user_id]['hide']
    if len(args) < 2:
        if lang == 'en':
            help_text = (
                "<b>Hide Words Management:</b>\n"
                "/hide list - Show hidden words\n"
                "/hide add <word> - Add word to filter\n"
                "/hide remove <word> - Remove word"
            )
        elif lang == 'jp':
            help_text = (
                "<b>NGワード管理:</b>\n"
                "/hide list - リストを表示\n"
                "/hide add <単語> - 追加\n"
                "/hide remove <単語> - 削除"
            )
        else:
            help_text = (
                "<b>Управление скрытием слов:</b>\n"
                "/hide list - Список скрытых слов\n"
                "/hide add <слово> - Добавить слово\n"
                "/hide remove <слово> - Убрать слово"
            )
        await message.answer(help_text, parse_mode="HTML")
        return
    action = args[1].lower()
    if action == 'list':
        if not user_hide_set:
            if lang == 'en': txt = "Your hidden words list is empty."
            elif lang == 'jp': txt = "NGワードリストは空です。"
            else: txt = "Ваш список скрытых слов пуст."
            await message.answer(txt)
        else:
            words_str = ", ".join([f"<code>{escape_html(w)}</code>" for w in user_hide_set])
            if lang == 'en': header = "🚫 <b>Hidden words:</b>"
            elif lang == 'jp': header = "🚫 <b>NGワード:</b>"
            else: header = "🚫 <b>Скрытые слова:</b>"
            await message.answer(f"{header}\n{words_str}", parse_mode="HTML")
    elif action == 'add':
        word_part = message.text.split(maxsplit=2)
        if len(word_part) < 3:
             err = "Usage: /hide add <word>"
             await message.answer(err)
             return
        word = word_part[2].lower().strip()
        if len(word) < 2:
            if lang == 'en': err = "Word too short."
            elif lang == 'jp': err = "単語が短すぎます。"
            else: err = "Слово слишком короткое."
            await message.answer(err)
            return
        if len(user_hide_set) >= 60:
            if lang == 'en': msg = "🚫 Limit exceeded! Max 60 hidden words allowed."
            elif lang == 'jp': msg = "🚫 制限を超えました！最大60語までです。"
            else: msg = "🚫 Лимит превышен! Максимум 60 скрытых слов."
            await message.answer(msg, parse_mode="HTML")
            return
        user_hide_set.add(word)
        asyncio.create_task(update_user_settings_db(user_id, board_id, hidden_words=list(user_hide_set)))
        if lang == 'en': msg = f"✅ Word '<b>{escape_html(word)}</b>' added to hidden list."
        elif lang == 'jp': msg = f"✅ '<b>{escape_html(word)}</b>' をリストに追加しました。"
        else: msg = f"✅ Слово '<b>{escape_html(word)}</b>' добавлено в скрытые."
        await message.answer(msg, parse_mode="HTML")
    elif action == 'remove' or action == 'del':
        word_part = message.text.split(maxsplit=2)
        if len(word_part) < 3:
             await message.answer("Usage: /hide remove <word>")
             return
        word = word_part[2].lower().strip()
        if word in user_hide_set:
            user_hide_set.remove(word)
            asyncio.create_task(update_user_settings_db(user_id, board_id, hidden_words=list(user_hide_set)))
            if lang == 'en': msg = f"🗑 Word '<b>{escape_html(word)}</b>' removed from list."
            elif lang == 'jp': msg = f"🗑 '<b>{escape_html(word)}</b>' を削除しました。"
            else: msg = f"🗑 Слово '<b>{escape_html(word)}</b>' удалено из списка."
            await message.answer(msg, parse_mode="HTML")
        else:
            if lang == 'en': msg = "Word not found in your list."
            elif lang == 'jp': msg = "リストに見つかりません。"
            else: msg = "Слово не найдено в вашем списке."
            await message.answer(msg)
@dp.message(Command("unshadowmute"))
async def cmd_unshadowmute(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Единый обработчик снятия теневого бана.
    - Админ: Снимает теневой бан с пользователя на всей доске.
    - ОП треда: Снимает локальный теневой бан внутри треда.
    """
    if not board_id: return
    user_id = message.from_user.id
    is_adm = is_admin(user_id, board_id)
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    if not is_adm:
        if board_id not in THREAD_BOARDS: 
            try: await message.delete()
            except: pass
            return
        user_s = b_data.get('user_state', {}).get(user_id, {})
        location = user_s.get('location', 'main')
        if location == 'main':
            await message.delete()
            return
        thread_info = b_data.get('threads_data', {}).get(location)
        if not thread_info or thread_info.get('op_id') != user_id:
            await message.delete()
            return
        now_ts = time.time()
        if now_ts - user_s.get('last_op_command_ts', 0) < OP_COMMAND_COOLDOWN:
            await message.delete()
            return
        user_s['last_op_command_ts'] = now_ts
        if not message.reply_to_message:
            await message.delete()
            return
        target_id = None
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
        if not target_id:
            await message.delete()
            return
        local_shadow_mutes = thread_info.get('local_shadow_mutes', {})
        if target_id in local_shadow_mutes:
            del local_shadow_mutes[target_id]
            phrases = thread_messages.get(lang, {}).get('op_unmute_success', ["Unmuted."])
            response_text = random.choice(phrases)
            await message.answer(f"👻 (shadow) {response_text}")
        await message.delete()
        return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    else:
        parts = message.text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
    if not target_id:
        if lang == 'en':
            msg = "Usage: <code>/unshadowmute &lt;id&gt;</code> or reply."
        elif lang == 'jp':
            msg = "使用法: <code>/unshadowmute &lt;ID&gt;</code> または返信。"
        else:
            msg = "Использование: <code>/unshadowmute &lt;id&gt;</code> или ответом на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return
    was_muted = False
    async with storage_lock:
        if target_id in b_data['shadow_mutes']:
            del b_data['shadow_mutes'][target_id]
            was_muted = True
    await update_shadow_mute(target_id, board_id, 0)
    if was_muted:
        if lang == 'en':
            resp = f"👻 User <code>{target_id}</code> un-shadowmuted."
        elif lang == 'jp':
            resp = f"👻 ユーザー <code>{target_id}</code> のシャドウミュートを解除しました。"
        else:
            resp = f"👻 С пользователя <code>{target_id}</code> снят теневой мут."
        await message.answer(resp, parse_mode="HTML")
    else:
        if lang == 'en':
            resp = f"User <code>{target_id}</code> was not shadowmuted."
        elif lang == 'jp':
            resp = f"ユーザー <code>{target_id}</code> はシャドウミュートされていません。"
        else:
            resp = f"Пользователь <code>{target_id}</code> не был в теневом муте."
        await message.answer(resp, parse_mode="HTML")
    try:
        await message.delete()
    except:
        pass
@dp.message(Command("invite"))
async def cmd_invite(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    board_username = BOARD_CONFIG[board_id]['username']
    site_url = f"https://tgach.top/{board_id}/"

    if lang == 'en':
        source_list = INVITE_TEXTS_EN
    elif lang == 'jp':
        source_list = INVITE_TEXTS_JP
    else:
        source_list = INVITE_TEXTS
    invite_text_raw = random.choice(source_list)
    invite_text = invite_text_raw.replace("@dvach_chatbot", board_username).replace("@tgchan_chatbot", board_username)
    
    if lang == 'en':
        header = "📨 <b>Invite text for this board:</b>"
        footer = "<i>Just copy and send</i>"
        site_btn = "🌐 Web Version"
    elif lang == 'jp':
        header = "📨 <b>この板の招待用テキスト:</b>"
        footer = "<i>コピーして送信してください</i>"
        site_btn = "🌐 ウェブ版"
    else:
        header = "📨 <b>Текст для приглашения анонов на эту доску:</b>"
        footer = "<i>Просто скопируй и отправь</i>"
        site_btn = "🌐 Веб-версия"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=site_btn, url=site_url)]
    ])

    await message.answer(
        f"{header}\n\n<code>{escape_html(invite_text)}</code>\n\n{footer}",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await message.delete()
@dp.message(Command("queues"))
async def cmd_check_queues(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    from common.database import get_system_queue_counts
    db_stats = await get_system_queue_counts()
    runtime_snapshot = _collect_runtime_snapshot()
    queues = runtime_snapshot.get("queues", {})
    delivery_priority = runtime_snapshot.get("delivery_priority", {})
    recipients_snapshot = runtime_snapshot.get("recipients", {})
    anime_media_snapshot = runtime_snapshot.get("anime_media", {})
    durable_delivery_snapshot = runtime_snapshot.get("durable_delivery", {})
    mode_punchup_snapshot = runtime_snapshot.get("mode_punchup", {})
    mode_punchup_stats = mode_punchup_snapshot.get("stats", {})
    contextual_snapshot = runtime_snapshot.get("contextual_replies", {})
    contextual_stats = contextual_snapshot.get("stats", {})
    reply_coverage = runtime_snapshot.get("reply_coverage", {})
    ram_queue_size = message_queues[board_id].qsize()
    top_queue = ", ".join(f"{b}:{n}" for b, n in queues.get("top", [])) or "empty"
    priority_by_board = delivery_priority.get("by_board", {})
    board_delivery = runtime_snapshot.get("delivery", {}).get(board_id, {})
    last_delivery = board_delivery.get("last") or {}
    live_queue_info = queues.get("age_by_board", {}).get(board_id, {})
    live_current = queues.get("in_flight", {}).get(board_id, {})
    live_queue_text = (
        f"oldest {live_queue_info.get('oldest_age_sec', 0)}s "
        f"avg {live_queue_info.get('avg_age_sec', 0)}s "
        f"post #{live_queue_info.get('oldest_post', '-')}"
    )
    live_current_text = (
        f"#{live_current.get('post_num')} {live_current.get('phase', 'full')} "
        f"run {live_current.get('run_sec')}s age {live_current.get('age_sec')}s "
        f"rec {live_current.get('recipients', '-')}/{live_current.get('original_recipients', '-')}"
        if live_current else "none"
    )
    board_reply_coverage = reply_coverage.get("by_board", {}).get(board_id, {})
    reply_coverage_text = (
        f"all {reply_coverage.get('copy_posts', 0)} posts/{reply_coverage.get('total_copies', 0)} copies "
        f"span {reply_coverage.get('min_post', '-')}-{reply_coverage.get('max_post', '-')} "
        f"gap {reply_coverage.get('gap_from_latest', '-')}; "
        f"{board_id} {board_reply_coverage.get('copy_posts', 0)} posts "
        f"{board_reply_coverage.get('min_post', '-')}-{board_reply_coverage.get('max_post', '-')}"
    )
    if last_delivery:
        last_age = last_delivery.get("post_age_sec")
        last_age_text = f" age {round(last_age, 1)}s" if last_age is not None else ""
        last_delivery_text = (
            f"#{last_delivery.get('post_num')} "
            f"{last_delivery.get('phase', 'full')} "
            f"{last_delivery.get('success')}/{last_delivery.get('phase_recipients', last_delivery.get('recipients'))}"
            f"/{last_delivery.get('original_recipients', last_delivery.get('recipients'))} "
            f"{last_delivery.get('seconds')}s "
            f"{last_age_text} "
            f"def {last_delivery.get('deferred_recipients', 0)} "
            f"prio {last_delivery.get('priority_recipients')} "
            f"retry {last_delivery.get('retries')}"
        )
    else:
        last_delivery_text = "none"
    memory = runtime_snapshot.get("memory", {})
    text = (
        f"📊 <b>Состояние очередей:</b>\n\n"
        f"🚀 <b>RAM (Рассылка):</b> {ram_queue_size}\n"
        f"🧵 <b>RAM total/top:</b> {queues.get('total', 0)} | <code>{escape_html(top_queue)}</code>\n"
        f"⏳ <b>Live age/current:</b> <code>{escape_html(live_queue_text)} | {escape_html(live_current_text)}</code>\n"
        f"👥 <b>Telegram recipients:</b> {recipients_snapshot.get('telegram_active_by_board', {}).get(board_id, '?')} on /{board_id}/; all {recipients_snapshot.get('telegram_active_total', '?')}\n"
        f"↩️ <b>Reply copies:</b> <code>{escape_html(reply_coverage_text)}</code>\n"
        f"⚡ <b>Priority active:</b> {priority_by_board.get(board_id, 0)} / {delivery_priority.get('total_weekly_active', 0)} за {delivery_priority.get('days', WEEKLY_ACTIVE_DAYS)}d split={delivery_priority.get('split_fanout')} slice={delivery_priority.get('passive_slice_size')}/{delivery_priority.get('passive_media_slice_size')} pressure>={delivery_priority.get('pressure_slice_age_sec')}s:{delivery_priority.get('pressure_passive_slice_size')}/{delivery_priority.get('pressure_passive_media_slice_size')} priority_budget={delivery_priority.get('priority_phase_budget_sec')}s passive_budget={delivery_priority.get('passive_phase_budget_sec')}s guard={delivery_priority.get('delivery_phase_guard_sec')}s preempt={delivery_priority.get('passive_max_preemptions')} chunk={delivery_priority.get('delivery_initial_chunk_size')}/{delivery_priority.get('delivery_min_chunk_size')} uid_timeout={delivery_priority.get('delivery_per_recipient_timeout_sec')}s uid_retries={delivery_priority.get('delivery_max_recipient_retries')}\n"
        f"🧷 <b>Durable delivery:</b> enabled={durable_delivery_snapshot.get('enabled')} DB pending={db_stats.get('delivery', 0)} saved={durable_delivery_snapshot.get('persisted', 0)} fail={durable_delivery_snapshot.get('persist_failed', 0)} restored={durable_delivery_snapshot.get('restored_items', 0)}/{durable_delivery_snapshot.get('restored_recipients', 0)} deleted={durable_delivery_snapshot.get('deleted', 0)}\n"
        f"🖼 <b>Anime media:</b> conc={anime_media_snapshot.get('concurrency')} b_max={anime_media_snapshot.get('b_max_stacked_images')} url={anime_media_snapshot.get('url_parallel')}x/{anime_media_snapshot.get('url_timeout_sec')}s total={anime_media_snapshot.get('url_total_sec')}s dl={anime_media_snapshot.get('download_parallel')}x/{anime_media_snapshot.get('download_timeout_sec')}s\n"
        f"🎭 <b>Mode punch-up:</b> runtime={mode_punchup_snapshot.get('runtime_enabled')} shed={mode_punchup_snapshot.get('queue_shed_sec')}s calls={mode_punchup_stats.get('calls', 0)} skip_load={mode_punchup_stats.get('skipped_load', 0)}\n"
        f"💬 <b>Context replies:</b> enabled={contextual_snapshot.get('enabled')} groups={contextual_snapshot.get('groups_ru')} tracked={contextual_snapshot.get('tracked_users')} sent={contextual_stats.get('sent', 0)} skip_cd/daily={contextual_stats.get('skipped_cooldown', 0)}/{contextual_stats.get('skipped_daily_limit', 0)} cd={contextual_snapshot.get('cooldown_sec')}s limit={contextual_snapshot.get('daily_limit')}\n"
        f"📨 <b>Last delivery:</b> <code>{escape_html(last_delivery_text)}</code> avg/max <code>{board_delivery.get('avg_sec', 0)} / {board_delivery.get('max_sec', 0)}s</code>\n"
        f"💾 <b>DB (Broadcast):</b> {db_stats.get('broadcast', 0)}\n"
        f"🔔 <b>DB (Уведомления):</b> {db_stats.get('notif', 0)}\n"
        f"🪞 <b>DB (Зеркала файлов):</b> {db_stats.get('mirror', 0)}\n"
        f"👮 <b>DB (Модерация):</b> {db_stats.get('mod', 0)}\n"
        f"🧠 <b>RSS/private:</b> {memory.get('rss_mb', '?')} / {memory.get('private_mb', '?')} MB"
    )
    await message.answer(text, parse_mode="HTML")
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    INFO_CMD_COOLDOWN = 30
    async with info_cmd_lock:
        async with storage_lock:
            b_data = board_data[board_id]
            current_time = time.time()
            last_usage = b_data.get('last_info_command_time', {}).get(user_id, 0)
            if current_time - last_usage < INFO_CMD_COOLDOWN:
                try: await message.delete()
                except: pass
                return
            b_data.setdefault('last_info_command_time', {})[user_id] = current_time
    b_data = board_data[board_id]
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
        pm_sent = "✅ Stats sent to PM."
        unlock = "❌ Unblock the bot."
    elif lang == 'jp':
        stats_text = (f"📊 {board_name} の統計:\n\n"
                      f"👥 この板のアノン: {total_users_on_board}\n"
                      f"👥 全アノン数: {total_users_global}\n"
                      f"📨 この板のレス数: {total_posts_on_board}\n"
                      f"📈 総レス数: {state['post_counter']}")
        pm_sent = "✅ 統計をDMで送信しました。"
        unlock = "❌ ボットのブロックを解除してください。"
    else:
        stats_text = (f"📊 Статистика доски {board_name}:\n\n"
                      f"👥 Анонимов на доске: {total_users_on_board}\n"
                      f"👥 Всего анонов в Тгаче: {total_users_global}\n"
                      f"📨 Постов на доске: {total_posts_on_board}\n"
                      f"📈 Всего постов в тгаче: {state['post_counter']}")
        pm_sent = "✅ Статистика отправлена вам в личные сообщения."
        unlock = "❌ Разблокируйте бота, чтобы получить статистику в ЛС."
    try:
        await message.bot.send_message(user_id, stats_text, parse_mode="HTML")
        temp_msg = await message.answer(pm_sent)
        asyncio.create_task(delete_message_after_delay(temp_msg, 5))
    except TelegramForbiddenError:
        await message.answer(unlock)
    except Exception: pass
    try: await message.delete()
    except: pass
@dp.message(Command("anime", "nya", "kawai", "kawaii"))
async def cmd_anime(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "にゃあ～！アニメモードがアクティベートされました！\n\n^_^",
        "お兄ちゃん、大変！アニメモードの時間だよ！ UWU",
        "アニメの力がこのチャットに満ちています！(ﾉ´ヮ´)ﾉ*:･ﾟ✧",
        "『プロジェクトA』発動！これよりチャットはアキハバラ自治区となる！",
        "このチャットは「人間」をやめるぞ！ジョジョーーッ！\n\nア ニ メ モ ー ド だ！",
        "君も... 見えるのか？『チャットのスタンド』が...！アニメモード発動！",
        "チャットの皆さん、聞いてください！私、魔法少女になっちゃった！\n\nアニメモード、オン！",
        "三百年の孤独に、光が射した… アニメモードの時間だ。",
        "異世界転生したらチャットが全部日本語になっていた件。\n\nアニメモード、スタート！",
        "🌸 お前はもう死んでいる... АНИМЕ РЕЖИМ: OMAE WA MOU SHINDEIRU!",
        "✧･ﾟ: *✧･ﾟ♡ ВКЛЮЧАЕМ КАВАЙНЫЙ АД! ♡･ﾟ✧*:･ﾟ✧",
        "⚡ 千 本 桜 ⚡ НЯ!",
        "ばか！へんたい！すけべ！アニメモードの時間なんだからね！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！",
        "アニメモードが始まったよ！みんな、準備はいい？",
        "アニメモード、オン！さあ、みんなで楽しい時間を過ごそう！",
        "アニメモード、発動！みんなで一緒にカワイイを叫ぼう！"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима anime.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### 管理者 ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'anime_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(330, board_id, 'anime_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
async def check_anime_cmd_cooldown(message: types.Message, board_id: str) -> bool:
    current_time = time.time()
    async with anime_cmd_lock:
        cooldown_is_active = False
        async with storage_lock:
            b_data = board_data[board_id]
            last_usage = b_data.get('last_anime_cmd_time', 0)
            if current_time - last_usage < ANIME_CMD_COOLDOWN:
                cooldown_is_active = True
            else:
                b_data['last_anime_cmd_time'] = current_time
        if cooldown_is_active:
            cooldown_msg = random.choice(ANIME_CMD_COOLDOWN_PHRASES)
            try:
                sent_msg = await message.answer(cooldown_msg)
                asyncio.create_task(delete_message_after_delay(sent_msg, 15))
            except Exception:
                pass
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return False
        return True
def detect_media_type(data: bytes, url: str) -> str:
    """
    Определяет тип медиа (photo/video/animation) по заголовку файла или URL.
    """
    header = data[:12]
    url_lower = url.lower()
    if b'ftyp' in header or header.startswith(b'\x1A\x45\xDF\xA3'):
        return 'video'
    if header.startswith(b'GIF8'):
        return 'animation'
    if url_lower.endswith('.mp4') or url_lower.endswith('.webm') or url_lower.endswith('.mov'):
        return 'video'
    if url_lower.endswith('.gif'):
        return 'animation'
    return 'photo'
async def _run_bounded_anime_url_fetches(
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[int, Optional[str] | BaseException]]:
    sem = asyncio.Semaphore(ANIME_URL_FETCH_PARALLEL)

    async def run_one(index: int, fetcher: Callable[[], Awaitable[Optional[str]]]):
        async with sem:
            started = time.time()
            try:
                return index, await asyncio.wait_for(fetcher(), timeout=ANIME_URL_FETCH_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                runtime_logger.warning(
                    "anime_url_fetch_timeout %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "index": index,
                            "timeout_sec": ANIME_URL_FETCH_TIMEOUT_SEC,
                            "elapsed_sec": round(time.time() - started, 3),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return index, None
            except Exception as exc:
                return index, exc

    tasks = [asyncio.create_task(run_one(i, fetcher)) for i, fetcher in enumerate(fetcher_tasks)]
    done, pending = await asyncio.wait(tasks, timeout=ANIME_URL_FETCH_TOTAL_SEC)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        runtime_logger.warning(
            "anime_url_fetch_total_timeout %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "board_id": board_id,
                    "user_id": user_id,
                    "source": source,
                    "pending": len(pending),
                    "total": len(tasks),
                    "timeout_sec": ANIME_URL_FETCH_TOTAL_SEC,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    results: list[tuple[int, Optional[str] | BaseException]] = [
        (i, None) for i in range(len(fetcher_tasks))
    ]
    for task in done:
        try:
            index, result = task.result()
            if 0 <= index < len(results):
                results[index] = (index, result)
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                runtime_logger.warning(
                    "anime_url_fetch_task_error %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
    return results

async def _run_bounded_anime_downloads(
    urls: list[str],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[int, str, tuple[bytes, int] | BaseException | None]]:
    sem = asyncio.Semaphore(ANIME_DOWNLOAD_PARALLEL)

    async def run_one(index: int, url: str):
        async with sem:
            started = time.time()
            try:
                result = await asyncio.wait_for(
                    _download_image_with_proxy(url, timeout=int(ANIME_DOWNLOAD_TIMEOUT_SEC)),
                    timeout=ANIME_DOWNLOAD_TIMEOUT_SEC + 5,
                )
                return index, url, result
            except asyncio.TimeoutError:
                runtime_logger.warning(
                    "anime_download_timeout %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "index": index,
                            "timeout_sec": ANIME_DOWNLOAD_TIMEOUT_SEC,
                            "elapsed_sec": round(time.time() - started, 3),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                return index, url, None
            except Exception as exc:
                return index, url, exc

    tasks = [asyncio.create_task(run_one(i, url)) for i, url in enumerate(urls)]
    done, pending = await asyncio.wait(tasks, timeout=ANIME_DOWNLOAD_TOTAL_SEC)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        runtime_logger.warning(
            "anime_download_total_timeout %s",
            json.dumps(
                {
                    "ts": round(time.time(), 3),
                    "board_id": board_id,
                    "user_id": user_id,
                    "source": source,
                    "pending": len(pending),
                    "total": len(tasks),
                    "timeout_sec": ANIME_DOWNLOAD_TOTAL_SEC,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    results: list[tuple[int, str, tuple[bytes, int] | BaseException | None]] = [
        (i, url, None) for i, url in enumerate(urls)
    ]
    for task in done:
        try:
            _index, url, result = task.result()
            if 0 <= _index < len(results):
                results[_index] = (_index, url, result)
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                runtime_logger.warning(
                    "anime_download_task_error %s",
                    json.dumps(
                        {
                            "ts": round(time.time(), 3),
                            "board_id": board_id,
                            "user_id": user_id,
                            "source": source,
                            "error": type(exc).__name__,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
    return results

async def _collect_stacked_anime_downloads(
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    board_id: str,
    user_id: int,
    source: str,
) -> list[tuple[bytes, str, str]]:
    successful_by_slot: dict[int, tuple[bytes, str, str]] = {}
    retry_slots = list(range(len(fetcher_tasks)))
    loop = asyncio.get_running_loop()

    for round_index in range(ANIME_REFILL_ROUNDS + 1):
        if not retry_slots:
            break
        round_source = source if round_index == 0 else f"{source}:refill{round_index}"
        round_fetchers = [fetcher_tasks[slot] for slot in retry_slots]
        url_results = await _run_bounded_anime_url_fetches(round_fetchers, board_id, user_id, round_source)

        urls: list[str] = []
        url_slots: list[int] = []
        next_slots: list[int] = []
        for local_index, result in url_results:
            if local_index >= len(retry_slots):
                continue
            slot = retry_slots[local_index]
            if isinstance(result, str) and result.startswith("http"):
                urls.append(result)
                url_slots.append(slot)
            else:
                next_slots.append(slot)

        if urls:
            download_results = await _run_bounded_anime_downloads(urls, board_id, user_id, round_source)
            for local_index, orig_url, res in download_results:
                if local_index >= len(url_slots):
                    continue
                slot = url_slots[local_index]
                if isinstance(res, tuple) and res[0]:
                    image_bytes = res[0]
                    try:
                        ext = orig_url.split('.')[-1].split('?')[0].lower()
                        if len(ext) > 4:
                            ext = 'jpg'
                    except Exception:
                        ext = 'jpg'
                    processed_bytes = await loop.run_in_executor(None, _resize_image_if_needed, image_bytes)
                    real_type = detect_media_type(processed_bytes, orig_url)
                    successful_by_slot[slot] = (processed_bytes, real_type, ext)
                else:
                    if isinstance(res, Exception):
                        print(f"⚠️ Ошибка при скачивании изображения: {res}")
                    next_slots.append(slot)

        retry_slots = [slot for slot in dict.fromkeys(next_slots) if slot not in successful_by_slot]
        if retry_slots and round_index < ANIME_REFILL_ROUNDS:
            runtime_logger.warning(
                "anime_media_refill %s",
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "board_id": board_id,
                        "user_id": user_id,
                        "source": source,
                        "round": round_index + 1,
                        "missing": len(retry_slots),
                        "target": len(fetcher_tasks),
                        "ready": len(successful_by_slot),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            print(f"[{board_id}] Добираю картинки: готово {len(successful_by_slot)}/{len(fetcher_tasks)}, осталось {len(retry_slots)}.")

    return [successful_by_slot[slot] for slot in sorted(successful_by_slot)]
async def _process_stacked_anime_command(
    message: types.Message,
    board_id: str,
    fetcher_tasks: list[Callable[[], Awaitable[Optional[str]]]],
    caption: str,
    stream: str = 'ru'
):
    """
    Универсальный обработчик для "стакающихся" аниме-команд.
    """
    working_msg = None
    gate_acquired = False
    try:
        if not await check_anime_cmd_cooldown(message, board_id):
            return
        user_id = message.from_user.id
        b_data = board_data[board_id]
        if user_id in b_data['users']['banned'] or \
           (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
            try: await message.delete()
            except TelegramBadRequest: pass
            return
        try: await message.delete()
        except TelegramBadRequest: pass
        searching_phrase = random.choice(ANIME_CMD_SEARCHING_PHRASES)
        working_msg = await message.bot.send_message(message.chat.id, searching_phrase)
        gate_wait_started = time.time()
        await anime_media_gate.acquire()
        gate_acquired = True
        gate_wait_sec = time.time() - gate_wait_started
        if gate_wait_sec > 0.05:
            runtime_logger.warning(
                "anime_media_wait %s",
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "board_id": board_id,
                        "user_id": user_id,
                        "wait_sec": round(gate_wait_sec, 3),
                        "concurrency": ANIME_MEDIA_CONCURRENCY,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        print(f"[{board_id}] Шаг 1: Запускаю {len(fetcher_tasks)} задач на получение URL для user {user_id}...")
        successful_downloads = await _collect_stacked_anime_downloads(fetcher_tasks, board_id, user_id, "command")
        if not successful_downloads:
            raise ValueError("Не удалось скачать ни одного изображения.")
        content = {}
        if len(successful_downloads) == 1:
            ibytes, mtype, ext = successful_downloads[0]
            from aiogram.types import BufferedInputFile
            input_file = BufferedInputFile(ibytes, filename=f"file.{ext}")
            content = {'type': mtype, 'media': input_file, 'caption': caption}
            if mtype == 'video' or mtype == 'animation':
                 content = {'type': mtype, 'file_id': input_file, 'caption': caption} 
            else:
                 content = {'type': mtype, 'image_bytes': ibytes, 'caption': caption}
        else:
            media_items = []
            from aiogram.types import BufferedInputFile
            for ibytes, mtype, ext in successful_downloads:
                tg_type = 'video' if mtype in ['video', 'animation'] else 'photo'
                input_file = BufferedInputFile(ibytes, filename=f"file.{ext}")
                media_items.append({'type': tg_type, 'media': input_file})
                
            content = {'type': 'media_group', 'media': media_items, 'caption': caption}
        is_shadow_muted = (user_id in b_data['shadow_mutes'] and
                           b_data['shadow_mutes'][user_id] > datetime.now(UTC))
                           
        if is_shadow_muted:
            await process_shadow_reject(
                bot=message.bot,
                board_id=board_id,
                user_id=user_id,
                content=content,
                reply_to_post=None,
                stream=stream
            )
            post_num = 0 
        else:
            post_num = await process_new_post(
                bot_instance=message.bot,
                board_id=board_id,
                user_id=user_id,
                content=content,
                reply_to_post=None,
                is_shadow_muted=False,
                stream=stream
            )
            
        if post_num is not None:
            success_phrase = random.choice(ANIME_CMD_SUCCESS_PHRASES)
            sent_notification = await message.bot.send_message(
                chat_id=message.chat.id,
                text=f"{success_phrase} (+{len(successful_downloads)})"
            )
            asyncio.create_task(delete_message_after_delay(sent_notification, 15))
    except ValueError as e:
        print(f"[{board_id}] Не удалось обработать команду для user {user_id}: {e}")
        fail_text = "Не удалось получить контент. API недоступны или лимит исчерпан."
        error_msg = await message.bot.send_message(message.chat.id, fail_text)
        asyncio.create_task(delete_message_after_delay(error_msg, 10))
    finally:
        if gate_acquired:
            anime_media_gate.release()
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass
@dp.message(Command("deanon"))
async def cmd_deanon(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    current_time = time.time()
    async with deanon_lock:
        async with storage_lock:
            b_data = board_data[board_id]
            if current_time - b_data.get('last_deanon_time', 0) < DEANON_COOLDOWN:
                cooldown_msg = random.choice(DEANON_COOLDOWN_PHRASES)
                try:
                    sent_msg = await message.answer(cooldown_msg)
                    asyncio.create_task(delete_message_after_delay(sent_msg, 5))
                except Exception: pass
                try:
                    if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
                        await message.delete()
                except TelegramBadRequest:
                    pass
                return
            b_data['last_deanon_time'] = current_time
    lang = 'en' if board_id == 'int' else 'ru'
    if not message.reply_to_message:
        reply_text = "⚠️ Reply to a message to de-anonymize!" if lang == 'en' else "⚠️ Ответь на сообщение для деанона!"
        await message.answer(reply_text)
        try:
            if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
                await message.delete()
        except TelegramBadRequest:
            pass
        return
    user_id = message.from_user.id
    b_data = board_data[board_id] # Переопределение b_data для ясности
    user_location = 'main'
    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
    original_author_id = None
    target_post = None
    original_author_id = await get_author_id_by_reply(message)
    async with storage_lock:
        target_chat_id = message.reply_to_message.chat.id
        target_mid = message.reply_to_message.message_id
        target_post = message_to_post.get((target_chat_id, target_mid))
    if not original_author_id:
        reply_text = "🚫 Could not find the post to de-anonymize..." if lang == 'en' else "🚫 Не удалось найти пост для деанона..."
        await message.answer(reply_text)
        try:
            if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
                await message.delete()
        except TelegramBadRequest:
            pass
        return
    if original_author_id == 0:
        reply_text = "⚠️ System messages cannot be de-anonymized." if lang == 'en' else "⚠️ Системные сообщения нельзя деанонить."
        await message.answer(reply_text)
        try:
            if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
                await message.delete()
        except TelegramBadRequest:
            pass
        return
    deanon_text = generate_deanon_info(lang=lang)
    header_text_prefix = "### DEANON ###" if lang == 'en' else "### ДЕАНОН ###"
    now_dt = datetime.now(UTC)
    async def create_and_send_deanon_post(thread_id_override=None):
        content = {"type": "text", "text": deanon_text, "reply_to_post": target_post, "is_system_message": True}
        pnum = await create_post(
            board_id=board_id,
            author_id=0,
            content=content,
            timestamp=now_dt.timestamp(),
            is_from_site=False, stream=stream,
            thread_id_from_bot=thread_id_override
        )
        if not pnum:
            print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /deanon.")
            return
        header_text = await format_header(board_id, pnum)
        content['header'] = f"{header_text_prefix}\n{header_text}"
        content['post_num'] = pnum
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id, 'thread_id': thread_id_override}
            if thread_id_override:
                thread_info = b_data.get('threads_data', {}).get(thread_id_override)
                if thread_info:
                    thread_info['last_activity_at'] = time.time()
        recipients = None
        if thread_id_override:
            thread_info = b_data.get('threads_data', {}).get(thread_id_override)
            if thread_info:
                recipients = thread_info.get('subscribers', set())
        else:
            recipients = b_data.get('users', {}).get('active', set())
        if recipients:
            await enqueue_board_message(board_id, {
                "recipients": recipients, "content": content, "post_num": pnum,
                "board_id": board_id, "thread_id": thread_id_override
            })
    if board_id in THREAD_BOARDS and user_location != 'main':
        thread_id = user_location
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if thread_info and not thread_info.get('is_archived'):
            await create_and_send_deanon_post(thread_id_override=thread_id)
        else: # Если тред не найден, постим на главную
             await create_and_send_deanon_post()
    else:
        await create_and_send_deanon_post()
    try:
        if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
            await message.delete()
    except TelegramBadRequest:
        pass
async def delete_message_after_delay(message: types.Message, delay: int):

    try:
        await asyncio.sleep(delay)
        await asyncio.wait_for(message.delete(), timeout=15.0)
    except asyncio.CancelledError:
        pass
    except asyncio.TimeoutError:
        print(f"⚠️ Таймаут при удалении сообщения {message.message_id} в чате {message.chat.id}")
    except Exception as e:
        if "message to delete not found" not in str(e).lower():
            print(f"🔥 Непредвиденная ошибка в delete_message_after_delay: {type(e).__name__}: {e}")
@dp.message(Command("zaputin", "z", "zov", "putin"))
async def cmd_zaputin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "🇷🇺 СЛАВА РОССИИ! ПУТИН - НАШ ПРЕЗИДЕНТ! 🇷🇺\n\nАктивирован режим кремлеботов! Все несогласные будут приравнены к пидорасам и укронацистам!",
        "ВНИМАНИЕ! АКТИВИРОВАН ПРОТОКОЛ 'КРЕМЛЬ'! 🇷🇺 Работаем, братья! За нами Путин и Сталинград!",
        "ТРИКОЛОР ПОДНЯТ! 🇷🇺 В чате включен режим патриотизма. Кто не с нами - тот под нами! РОССИЯ!",
        "НАЧИНАЕМ СПЕЦОПЕРАЦИЮ! 🇷🇺 Цель: денацификация чата. Потерь нет! Слава России!",
        "🇷🇺 РЕЖИМ 'РУССКИЙ МИР' АКТИВИРОВАН! 🇷🇺 От Калининграда до Владивостока - мы великая страна! ZOV",
        "ЗА ВДВ! 🇷🇺 В чате высадился русский десант. НАТО сосать! С нами Бог!",
        "ПАТРИОТИЧЕСКИЙ РЕЖИМ ВКЛЮЧЕН! 🇷🇺 Можем повторить! На Берлин! Деды воевали!",
        "🇷🇺 АКТИВИРОВАН РЕЖИМ 'БЕЗГРАНИЧНАЯ ЛЮБОВЬ К РОДИНЕ'! 🇷🇺 Гордимся страной, верим в президента!",
        "ТОВАРИЩ ПОЛКОВНИК РАЗРЕШИЛ! 🇷🇺 Включаем режим '15 рублей'. Все на защиту Родины!",
        "🇷🇺 ЗА ПУТІНА! ЗА ДЕДОВ! РЕЖИМ 'БАЛТИЙСКИЙ ШТУРМ' АКТИВИРОВАН!",
        "🚨 ТРЕВОГА! В ЧАТЕ ЗАМЕЧЕНА ЛИБЕРДА! ВКЛЮЧАЕМ ПРОТОКОЛ 'ЧВК ВАГНЕР'",
        "🧨 ПОДРЫВНАЯ АКТИВНОСТЬ В ЧАТЕ! Включаем режим 'АРМАТА'. За Родину!",
        "🪆 МАТРЁШКА РАСКРЫЛАСЬ! Режим имперского величия активирован! ZА ПУТИНА!",
        "☢️ ЯДЕРНЫЙ ПРОТОКОЛ АКТИВИРОВАН! Готовим гиперзвуковые ракеты по целям!",
        "🦅 ОРЕШНИК ЗАПУЩЕН! Режим патриотизма включен. Крым наш!",
        "🐻 МЕДВЕДЬ ПРОСНУЛСЯ! Режим ядерного троллинга активирован! ZOV ZOV ZOV",
        "🇷🇺 РОССИЯ! СВЯЩЕННАЯ НАША ДЕРЖАВА! 🇷🇺 В чате включен патриотический режим. Хохлы, сосать!",
        "🇷🇺 В ЧАТЕ АКТИВИРОВАН РЕЖИМ 'ZА ПУТИНА'! 🇷🇺 Кто не скачет - тот москаль!",
        "🇷🇺 ВКЛЮЧАЕМ РЕЖИМ 'РОССИЯ ВПЕРЁД'! 🇷🇺 Слава великой стране! С нами Бог и Путин!",
        "ГОЙДА, БРАТЦЫ! 🇷🇺 Активирован режим державности! Либерахам приготовиться к анальным карам!",
        "🇷🇺 В ЧАТ ВРЫВАЕТСЯ РУССКИЙ МЕДВЕДЬ! 🐻 Всем сосать, мы здесь власть! Запад загнивает!",
        "АКТИВИРОВАН ПРОТОКОЛ 'СКРЕПЫ'! 🙏 Переходим на православный мат и традиционные ценности!",
        "ПО ЦЕНТРАМ ПРИНЯТИЯ РЕШЕНИЙ... ОГОНЬ! 🔥 Патриотический угар объявляется открытым!",
        "АХМАТ-СИЛА! 💪 В чат заходят дон. Несогласные - извиняются на камеру дон."
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима zaputin.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'zaputin_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(309, board_id, 'zaputin_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("app"))
async def cmd_app(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет кнопку для открытия веб-приложения (сайта).
    """
    if not board_id: return
    WEBAPP_URL = "https://tgach.top" 
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "Click the button below to open the TGACH web interface:"
        btn_text = "Open Web App"
    elif lang == 'jp':
        text = "下のボタンをクリックしてTGちゃんのWebインターフェースを開きます:"
        btn_text = "Webアプリを開く"
    else:
        text = "Нажмите на кнопку ниже, чтобы открыть веб-интерфейс ТГАЧ:"
        btn_text = "Открыть веб-приложение"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(text, reply_markup=keyboard)
@dp.message(Command("suka_blyat"))
async def cmd_suka_blyat(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    if board_id == 'int':
        try:
            await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    if (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC)) or \
       (user_id in b_data['mutes'] and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return
    if not await check_cooldown(message, board_id):
        return
    activation_phrases = [
        "💢💢💢 Активирован режим СУКА БЛЯТЬ! 💢💢💢\n\nВсех нахуй разъебало!",
        "БЛЯЯЯЯЯТЬ! 💥 РЕЖИМ АГРЕССИИ ВКЛЮЧЕН! ПИЗДА ВСЕМУ!",
        "ВЫ ЧЕ, ОХУЕЛИ?! 💢 Включаю режим 'сука блять', готовьтесь, пидорасы!",
        "ЗАЕБАЛО ВСЁ НАХУЙ! 💥 Переходим в режим тотальной ненависти. СУКА!",
        "💥 ТРЕЩИНА НАХУЙ! Режим 'ХУЙ ПОЛЕЗЕШЬ' активирован!",
        "🧨 ПИЗДЕЦ НАСТУПИЛ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ! ААА БЛЯЯЯТЬ!",
        "🔞 ЁБАНЫЙ В РОТ! Режим агрессивного аутизма включен! СУКА!",
        "🤬 ПИЗДОС НА МАКАРОС! Режим 'БАТЯ В ЯРОСТИ'! ВСЕМ ПИЗДАНУТЬСЯ!",
        "А НУ БЛЯТЬ СУКИ СЮДА ПОДОШЛИ! 💢 Режим 'бати в ярости' активирован!",
        "СУКАААААА! 💥 Пиздец, как меня все бесит! Включаю протокол 'РАЗЪЕБАТЬ'.",
        "ЩА БУДЕТ МЯСО! 🔪🔪🔪 Режим 'сука блять' активирован. Нытикам здесь не место!",
        "ЕБАНЫЙ ТЫ НАХУЙ! 💢💢💢 С этого момента говорим только матом. Поняли, уебаны?",
        "ТАК, БЛЯТЬ! 💥 Слушать мою команду! Режим 'СУКА БЛЯТЬ' активен. Вольно, бляди!",
        "💢 ДА ТЫ ЁБНУТЫЙ? РЕЖИМ 'ХУЙ ПОЛЕЗЕШЬ' АКТИВИРОВАН!",
        "🐗 СВИНОПАС ВЫШЕЛ НА ТРОПУ ВОЙНЫ! ВКЛЮЧАЕМ РЕЖИМ ХУЕСОСАНИЯ!",
        "🔞 ПИЗДЕЦ НАСТУПИЛ! ВСЕМ ПИЗДАНУТЬСЯ В УГОЛ! АААА БЛЯЯЯТЬ!",
        "ПОШЛИ НАХУЙ! 💥 ВСЕ ПОШЛИ НАХУЙ! Режим ярости включен, суки!",
        "🤬 СУКА БЛЯТЬ! РЕЖИМ 'БАТЯ В ЯРОСТИ' АКТИВИРОВАН! ВСЕМ ПИЗДАНУТЬСЯ!",
        "ЩА БУДЕТ МЯСО! 🔪 Режим 'сука блять' активирован. Нытикам здесь не место!"
    ]
    activation_text = random.choice(activation_phrases)
    now_dt = datetime.now(UTC)
    content = {
        "type": "text",
        "text": activation_text,
        "is_system_message": True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для активации режима suka_blyat.")
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    header = f"### Админ ###\n{header}"
    content['header'] = header
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0,
            'timestamp': now_dt,
            'content': content,
            'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'suka_blyat_mode')
    disable_task = asyncio.create_task(disable_mode_after_delay(303, board_id, 'suka_blyat_mode'))
    b_data['active_mode_task'] = disable_task
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("say"))
async def cmd_admin_say(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Отправляет сообщение от имени Администрации.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    raw_html = message.html_text or getattr(message, 'caption_html_text', None) or ""
    command_prefix = "/say"
    text_to_say = ""
    if raw_html.startswith(command_prefix):
        text_to_say = raw_html[len(command_prefix):].strip()
    elif message.caption and getattr(message, 'caption_html_text', '').startswith(command_prefix):
         text_to_say = getattr(message, 'caption_html_text', '')[len(command_prefix):].strip()
    else:
        text_to_say = raw_html.strip()
    content_type = message.content_type
    file_id = None
    if content_type in ['photo', 'video', 'animation', 'document', 'audio']:
        file_id_obj = getattr(message, content_type)[-1] if content_type == 'photo' else getattr(message, content_type)
        file_id = file_id_obj.file_id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not text_to_say and not file_id:
        err = "Enter text or attach media." if lang == 'en' else ("テキストを入力するかメディアを添付してください。" if lang == 'jp' else "Введите текст или прикрепите медиа.")
        await message.answer(err)
        return
    content = {
        'type': content_type if file_id else 'text',
        'is_system_message': True 
    }
    if file_id:
        content['file_id'] = file_id
        content['caption'] = text_to_say
    else:
        content['text'] = text_to_say
    now_dt = datetime.now(UTC)
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream
    )
    if pnum:
        header = await format_header(board_id, pnum, 0)
        if lang == 'en':
            admin_title = "ADMINISTRATION"
        elif lang == 'jp':
            admin_title = "管理部"
        else:
            admin_title = "АДМИНИСТРАЦИЯ"
        content['header'] = f"🔴 <b>{admin_title}</b> 🔴\n{header}"
        await update_post_content(pnum, content)
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 
                'timestamp': now_dt, 
                'content': content, 
                'board_id': board_id
            }
        b_data = board_data[board_id]
        await enqueue_board_message(board_id, {
            "recipients": b_data['users']['active'],
            "content": content,
            "post_num": pnum,
            "board_id": board_id
        })
        conf_txt = f"✅ Message sent (#{pnum})" if lang == 'en' else (f"✅ 送信完了 (#{pnum})" if lang == 'jp' else f"✅ Сообщение отправлено (#{pnum})")
        sent_conf = await message.answer(conf_txt)
        asyncio.create_task(delete_message_after_delay(sent_conf, 5))
    try: await message.delete()
    except TelegramBadRequest: pass
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    if not is_admin(message.from_user.id, board_id):
        lang = 'en' if board_id == 'int' else 'ru'
        contact_url = "https://t.me/voprosy?start=rba30"
        if lang == 'en':
            response_text = "To contact the administration, please use the button below:"
            button_text = "Contact Admin"
        else:
            response_text = "Для связи с админом используйте кнопку ниже:"
            button_text = "Связаться с админом"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=contact_url)]])
        try:
            await message.answer(response_text, reply_markup=keyboard)
            await message.delete()
        except: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media')) # Подсчет
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    if lang == 'en':
        header_text = f"Admin panel for board {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            "<b>🗒️ Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia</code> — Бан ВСЕХ медиа ({media_ban_count})\n\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
    elif lang == 'jp':
        header_text = f"{BOARD_CONFIG[board_id]['name']} の管理パネル:"
        memo_text = (
            "<b>🗒️ コマンドメモ:</b>\n"
            "<code>/filter ...</code> - スパムフィルタ管理\n"
            f"<code>/togglereactions &lt;id&gt;</code> - リアクション禁止 ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIFシャドウバン ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - ステッカーシャドウバン ({sticker_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (返信) - リアクションした人を見る"
        )
    else:
        header_text = f"Админка доски {BOARD_CONFIG[board_id]['name']}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> — Бан/Разбан\n"
            "<code>/mute [время]</code>, <code>/unmute</code> — Мут\n"
            "<code>/shadowmute [время]</code> — Теневой мут (локальный)\n"
            "<code>/gban</code>, <code>/gunban</code>, <code>/gshadowmute</code> — <b>ГЛОБАЛЬНЫЕ</b> меры\n\n"
            "<code>/del</code> — Удалить пост (и копии)\n"
            "<code>/sdel</code> — Теневое удаление (автор не видит)\n"
            "<code>/pin</code>, <code>/unpin</code> — Глобальный закреп\n\n"
            "<code>/whois [id]</code> — Досье на юзера\n"
            "<code>/id</code> — Узнать ID\n"
            f"<code>/togglegif</code> — Запрет GIF (Всего: {gif_ban_count})\n"
            f"<code>/togglestickers</code> — Запрет стикеров (Всего: {sticker_ban_count})\n\n"
            f"<code>/lie</code> — Подмена медиа архивом (Всего: {lie_media_count})\n\n"
            "<code>/say [текст]</code> — Пост от имени Админа\n"
            "<code>/ans [текст]</code> — Ответ от имени Системы (реплай)\n"
            "<code>/stop</code> — Выключить режимы (Шиза и т.д.)"
        )
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text="🤬 Стоп-слова", callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text="🚫 Ограничения (Баны/Муты)", callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text="💾 Сохранить Бэкап", callback_data="save_all")],
    ])
    await message.answer(final_text, reply_markup=keyboard, parse_mode="HTML")
    try:
        if (datetime.now(UTC) - message.date).total_seconds() < 48 * 3600:
            await message.delete()
    except TelegramBadRequest:
        pass
@dp.message(Command("lockdown"))
async def cmd_bot_lockdown(message: Message, board_id: str | None):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: `/lockdown on` или `/lockdown off`", parse_mode="Markdown")
        return
    enabled = args[1].lower() == "on"
    from common.database import set_system_setting
    await set_system_setting('lockdown_enabled', "true" if enabled else "false")
    status_text = "ВКЛЮЧИЛ" if enabled else "ВЫКЛЮЧИЛ"
    await log_global_event('bot', f"🚨 LOCKDOWN: Админ {message.from_user.id} {status_text} режим бункера")
    await message.answer(f"✅ Режим бункера {'активирован' if enabled else 'деактивирован'} везде.")
@dp.message(Command("togglereactions"))
async def cmd_togglereactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    target_id = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    else:
        parts = message.text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/togglereactions &lt;user_id&gt;</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/togglereactions &lt;ID&gt;</code> または返信。"
        else:
            usage = "Использование: <code>/togglereactions &lt;user_id&gt;</code> или ответом на сообщение."
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    response_text = ""
    async with storage_lock:
        b_data = board_data[board_id]
        banned_set = b_data.setdefault('reaction_banned_users', set())
        if target_id in banned_set:
            banned_set.remove(target_id)
            await remove_reaction_ban(target_id, board_id)
            await log_global_event('bot', f"🎭 REAC_OK: Админ {message.from_user.id} РАЗРЕШИЛ реакции для {target_id} на /{board_id}/")
            if lang == 'en':
                response_text = f"✅ User <code>{target_id}</code> can now use reactions again."
            elif lang == 'jp':
                response_text = f"✅ ユーザー <code>{target_id}</code> のリアクション禁止を解除しました。"
            else:
                response_text = f"✅ Пользователь <code>{target_id}</code> теперь снова может ставить реакции."
        else:
            banned_set.add(target_id)
            await add_reaction_ban(target_id, board_id)
            await log_global_event('bot', f"🎭 REAC_BAN: Админ {message.from_user.id} ЗАПРЕТИЛ реакции для {target_id} на /{board_id}/")
            if lang == 'en':
                response_text = f"🚫 User <code>{target_id}</code> is now banned from using reactions."
            elif lang == 'jp':
                response_text = f"🚫 ユーザー <code>{target_id}</code> のリアクションを禁止しました。"
            else:
                response_text = f"🚫 Пользователю <code>{target_id}</code> теперь запрещено ставить реакции."
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("reactions"))
async def cmd_reactions(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Usage: reply with /reactions to see reactions."
        elif lang == 'jp': msg = "使用法: /reactions と返信してリアクションを確認。"
        else: msg = "Использование: ответьте командой /reactions на пост, чтобы увидеть реакции."
        await message.answer(msg)
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    post_num = None
    reactions_data = {}
    async with storage_lock:
        lookup_key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(lookup_key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num and post_num in messages_storage:
        post_data = messages_storage[post_num]
        reactions_data = post_data.get('reactions', {}).get('users', {})
    if not post_num:
        if lang == 'en': err = "Post not found in DB."
        elif lang == 'jp': err = "データベースに投稿が見つかりません。"
        else: err = "Не удалось найти этот пост в базе."
        try: await message.answer(err); await message.delete()
        except TelegramBadRequest: pass
        return
    if not reactions_data:
        if lang == 'en': msg = f"Post #{post_num} has no reactions yet."
        elif lang == 'jp': msg = f"投稿 #{post_num} にはまだリアクションがありません。"
        else: msg = f"На пост #{post_num} еще нет реакций."
        try: await message.answer(msg); await message.delete()
        except TelegramBadRequest: pass
        return
    if lang == 'en': header = f"<b>Reactions to post #{post_num}:</b>\n\n"
    elif lang == 'jp': header = f"<b>投稿 #{post_num} へのリアクション:</b>\n\n"
    else: header = f"<b>Реакции на пост #{post_num}:</b>\n\n"
    lines = []
    sorted_reactors = sorted(reactions_data.items())
    MAX_USERS_TO_SHOW = 50
    for user_id, emoji_list in sorted_reactors[:MAX_USERS_TO_SHOW]:
        emojis_str = "".join(emoji_list)
        lines.append(f"• ID <code>{user_id}</code>: {emojis_str}")
    response_text = header + "\n".join(lines)
    if len(sorted_reactors) > MAX_USERS_TO_SHOW:
        diff = len(sorted_reactors) - MAX_USERS_TO_SHOW
        if lang == 'en': footer = f"\n<i>...and {diff} more users.</i>"
        elif lang == 'jp': footer = f"\n<i>...他 {diff} ユーザー。</i>"
        else: footer = f"\n<i>...и еще {diff} пользователей.</i>"
        response_text += footer
    try:
        await message.answer(response_text, parse_mode="HTML")
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("filter"))
async def cmd_filter(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    b_data = board_data[board_id]
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    parts = message.text.split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"
    if subcommand == "list":
        spam_words = b_data.get('spam_filter_words', set())
        if not spam_words:
            if lang == 'en': resp = "Filter list is empty."
            elif lang == 'jp': resp = "フィルターリストは空です。"
            else: resp = "Список стоп-слов для этой доски пуст."
        else:
            sorted_words = sorted(list(spam_words))
            word_list = "\n".join([f"• <code>{escape_html(word)}</code>" for word in sorted_words])
            board_name = BOARD_CONFIG[board_id]['name']
            if lang == 'en':
                resp = f"<b>Stop-words on {board_name}:</b>\n\n{word_list}"
            elif lang == 'jp':
                resp = f"<b>{board_name} のNGワード:</b>\n\n{word_list}"
            else:
                resp = f"<b>Текущие стоп-слова на доске {board_name}:</b>\n\n{word_list}"
        await message.answer(resp, parse_mode="HTML")
    elif subcommand == "add":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter add &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter add &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter add &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_add = parts[2].lower().strip()
            if await add_spam_word(board_id, word_to_add):
                b_data['spam_filter_words'].add(word_to_add)
                if lang == 'en': msg = f"✅ Added '<code>{escape_html(word_to_add)}</code>'."
                elif lang == 'jp': msg = f"✅ '<code>{escape_html(word_to_add)}</code>' を追加しました。"
                else: msg = f"✅ Слово '<code>{escape_html(word_to_add)}</code>' добавлено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("❌ DB Error.")
    elif subcommand == "remove":
        if len(parts) < 3 or not parts[2].strip():
            if lang == 'en': txt = "Usage: <code>/filter remove &lt;word&gt;</code>"
            elif lang == 'jp': txt = "使用法: <code>/filter remove &lt;単語&gt;</code>"
            else: txt = "Использование: <code>/filter remove &lt;слово&gt;</code>"
            await message.answer(txt, parse_mode="HTML")
        else:
            word_to_remove = parts[2].lower().strip()
            if await remove_spam_word(board_id, word_to_remove):
                b_data['spam_filter_words'].discard(word_to_remove)
                if lang == 'en': msg = f"🗑 Removed '<code>{escape_html(word_to_remove)}</code>'."
                elif lang == 'jp': msg = f"🗑 '<code>{escape_html(word_to_remove)}</code>' を削除しました。"
                else: msg = f"🗑 Слово '<code>{escape_html(word_to_remove)}</code>' удалено."
                await message.answer(msg, parse_mode="HTML")
            else:
                await message.answer("ℹ️ Word not found.")
    else:
        if lang == 'en':
            usage = (
                "<b>Spam Filter Management:</b>\n"
                "<code>/filter list</code> - Show list\n"
                "<code>/filter add &lt;word&gt;</code> - Add\n"
                "<code>/filter remove &lt;word&gt;</code> - Remove"
            )
        elif lang == 'jp':
            usage = (
                "<b>スパムフィルタ管理:</b>\n"
                "<code>/filter list</code> - リスト表示\n"
                "<code>/filter add &lt;単語&gt;</code> - 追加\n"
                "<code>/filter remove &lt;単語&gt;</code> - 削除"
            )
        else:
            usage = (
                "<b>Управление спам-фильтром:</b>\n"
                "<code>/filter list</code> - Показать текущие стоп-слова\n"
                "<code>/filter add &lt;слово&gt;</code> - Добавить слово\n"
                "<code>/filter remove &lt;слово&gt;</code> - Удалить слово"
            )
        await message.answer(usage, parse_mode="HTML")
    try: await message.delete()
    except TelegramBadRequest: pass
async def git_commit_and_push_db() -> bool:

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN не настроен, бэкап в облако невозможен.")
        return False
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(git_executor, sync_git_operations_db, GITHUB_TOKEN)
@dp.callback_query(F.data == "save_all")
async def admin_save_all(callback: types.CallbackQuery):

    is_any_admin = any(is_admin(callback.from_user.id, b_id) for b_id in BOARDS)
    if not is_any_admin:
        try: await callback.answer("Access denied", show_alert=True)
        except: pass
        return
    user_lang = callback.from_user.language_code or 'en'
    is_ru = 'ru' in user_lang or 'uk' in user_lang or 'be' in user_lang
    start_txt = "Запуск внепланового бэкапа БД..." if is_ru else "Starting manual DB backup..."
    try:
        await callback.answer(start_txt)
    except TelegramBadRequest:
        pass
    try:
        db = await get_pool()
        await db.execute("PRAGMA wal_checkpoint(PASSIVE);")
        print("💾 [Manual Backup] WAL Checkpoint выполнен.")
    except Exception as e:
        print(f"⚠️ Ошибка чекпоинта перед бэкапом: {e}")

    success = await git_commit_and_push_db()
    if is_ru:
        response_text = "✅ База данных успешно сохранена в GitHub." if success else "❌ Ошибка при создании бэкапа. См. логи."
    else:
        response_text = "✅ Database successfully pushed to GitHub." if success else "❌ Backup failed. Check logs."
    if isinstance(callback.message, types.Message):
        try:
            await callback.message.edit_text(response_text)
        except TelegramBadRequest:
            await callback.message.answer(response_text)
@dp.callback_query(F.data.startswith("stats_"))
async def admin_stats_board(callback: types.CallbackQuery):
    try:
        board_id = callback.data.split("_")[1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except: pass
        return
    if not isinstance(callback.message, types.Message):
        try: await callback.answer()
        except: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        stats_text = (
            f"Stats for {BOARD_CONFIG[board_id]['name']}:\n\n"
            f"Active users: {len(b_data['users']['active'])}\n"
            f"Banned: {len(b_data['users']['banned'])}\n"
            f"Queue size: {message_queues[board_id].qsize()}"
        )
        back_txt = "⬅️ Back"
    else:
        stats_text = (
            f"Статистика доски {BOARD_CONFIG[board_id]['name']}:\n\n"
            f"Активных: {len(b_data['users']['active'])}\n"
            f"Забаненных: {len(b_data['users']['banned'])}\n"
            f"В очереди: {message_queues[board_id].qsize()}"
        )
        back_txt = "⬅️ Назад"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(stats_text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass
@dp.callback_query(F.data.startswith("restrictions_"))
async def admin_restrictions_board(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'): # Добавлены аргументы board_id и stream

    if not board_id:
        try:
            board_id = callback.data.split("_")[1]
        except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        await callback.answer("Отказано в доступе", show_alert=True)
        return
    if not isinstance(callback.message, types.Message):
        await callback.answer()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data[board_id]
    now = datetime.now(UTC)
    text_parts = [f"<b>Список ограничений на доске {BOARD_CONFIG[board_id]['name']}:</b>"]
    banned_users = b_data['users']['banned']
    if banned_users:
        banned_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(list(banned_users))])
        if lang == 'en': header = "\n<u>🚫 Banned forever:</u>"
        elif lang == 'jp': header = "\n<u>🚫 永久BAN:</u>"
        else: header = "\n<u>🚫 Забанены навсегда:</u>"
        text_parts.append(f"{header}\n{banned_list}")
    active_mutes = {uid: expiry for uid, expiry in b_data['mutes'].items() if expiry > now}
    if active_mutes:
        mute_lines = []
        for uid, expiry in sorted(active_mutes.items(), key=lambda item: item[1]):
            remaining = expiry - now
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_left_str = f"{int(hours)}ч {int(minutes)}м"
            mute_lines.append(f"  • ID <code>{uid}</code> (осталось: {time_left_str})")
        mutes_list = "\n".join(mute_lines)
        if lang == 'en': header = "\n<u>🔇 Muted:</u>"
        elif lang == 'jp': header = "\n<u>🔇 ミュート中:</u>"
        else: header = "\n<u>🔇 В муте:</u>"
        text_parts.append(f"{header}\n{mutes_list}")
    active_shadow_mutes = {uid: expiry for uid, expiry in b_data['shadow_mutes'].items() if expiry > now}
    if active_shadow_mutes:
        shadow_mute_lines = []
        for uid, expiry in sorted(active_shadow_mutes.items(), key=lambda item: item[1]):
            remaining = expiry - now
            hours, remainder = divmod(remaining.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_left_str = f"{int(hours)}ч {int(minutes)}м"
            shadow_mute_lines.append(f"  • ID <code>{uid}</code> (осталось: {time_left_str})")
        shadow_mutes_list = "\n".join(shadow_mute_lines)
        text_parts.append(f"\n<u>👻 Полный теневой мут:</u>\n{shadow_mutes_list}")
    gif_banned_users = []
    user_settings = b_data.get('user_settings', {})
    for uid, settings in user_settings.items():
        if settings.get('shadow_gif'):
            gif_banned_users.append(uid)
    if gif_banned_users:
        gif_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(gif_banned_users)])
        text_parts.append(f"\n<u>👾 Теневой бан GIF:</u>\n{gif_list}")
    sticker_banned_users = []
    for uid, settings in user_settings.items():
        if settings.get('shadow_sticker'):
            sticker_banned_users.append(uid)
    if sticker_banned_users:
        sticker_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(sticker_banned_users)])
        text_parts.append(f"\n<u>🃏 Теневой бан Стикеров:</u>\n{sticker_list}")
    media_banned_users = []
    for uid, settings in user_settings.items():
        if settings.get('shadow_media'):
            media_banned_users.append(uid)
    if media_banned_users:
        media_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(media_banned_users)])
        text_parts.append(f"\n<u>🔇 Теневой бан Медиа (только текст):</u>\n{media_list}")
    lie_media_users = []
    for uid, settings in user_settings.items():
        if settings.get('lie_media'):
            lie_media_users.append(uid)
    if lie_media_users:
        lie_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted(lie_media_users)])
        text_parts.append(f"\n<u>🎭 Archive media substitution:</u>\n{lie_list}")
    if len(text_parts) == 1:
        final_text = f"На доске {BOARD_CONFIG[board_id]['name']} нет активных ограничений."
    else:
        final_text = "\n".join(text_parts)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            print(f"Ошибка обновления списка ограничений: {e}")
    await callback.answer()
@dp.callback_query(F.data.startswith("filter_list_"))
async def admin_filter_list(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[-1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except: pass
        return
    b_data = board_data[board_id]
    spam_words = b_data.get('spam_filter_words', set())
    lang = 'en' if board_id == 'int' else 'ru'
    if lang == 'en':
        header = f"<b>🤬 Stop-words ({len(spam_words)}):</b>"
        instr = (
            "\n\n<b>📝 How to manage:</b>\n"
            "• Add: <code>/filter add word</code>\n"
            "• Del: <code>/filter remove word</code>\n"
            "<i>(Write commands in chat)</i>"
        )
        empty_txt = "\n\n<i>List is empty. Filter disabled.</i>"
        back_txt = "⬅️ Back"
    else:
        header = f"<b>🤬 Фильтр стоп-слов ({len(spam_words)} шт):</b>"
        instr = (
            "\n\n<b>📝 Как управлять:</b>\n"
            "• Добавить: <code>/filter add слово</code>\n"
            "• Удалить: <code>/filter remove слово</code>\n"
            "<i>(Писать команды в чат)</i>"
        )
        empty_txt = "\n\n<i>Список пуст. Фильтр отключен.</i>"
        back_txt = "⬅️ Назад в меню"
    if not spam_words:
        list_text = empty_txt
    else:
        sorted_words = sorted(list(spam_words))
        words_display = ", ".join([f"<code>{escape_html(w)}</code>" for w in sorted_words])
        list_text = f"\n\n{words_display}"
    final_text = f"{header}{list_text}{instr}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(final_text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest: 
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass
@dp.callback_query(F.data.startswith("reaction_bans_"))
async def admin_reaction_bans(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[-1]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Access denied", show_alert=True)
        except: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    banned_users = b_data.get('reaction_banned_users', set())
    board_name = BOARD_CONFIG[board_id]['name']
    if not banned_users:
        if lang == 'en':
            response_text = f"No users are banned from reacting on {board_name}."
        elif lang == 'jp':
            response_text = f"{board_name} でリアクション禁止のユーザーはいません。"
        else:
            response_text = f"На доске {board_name} нет пользователей с запретом на реакции."
    else:
        sorted_banned = sorted(list(banned_users))
        user_list = "\n".join([f"  • ID <code>{uid}</code>" for uid in sorted_banned])
        if lang == 'en':
            response_text = f"<b>🚫 Users banned from reacting on {board_name}:</b>\n\n{user_list}"
        elif lang == 'jp':
            response_text = f"<b>🚫 {board_name} でリアクション禁止のユーザー:</b>\n\n{user_list}"
        else:
            response_text = f"<b>🚫 Пользователи с запретом на реакции на доске {board_name}:</b>\n\n{user_list}"
    back_txt = "⬅️ Back" if lang == 'en' else ("⬅️ 戻る" if lang == 'jp' else "⬅️ Назад в меню")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_txt, callback_data=f"admin_main_{board_id}")]
    ])
    try:
        await callback.message.edit_text(response_text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest: 
        pass
    try: await callback.answer()
    except TelegramBadRequest: pass
@dp.callback_query(F.data.startswith("admin_main_"))
async def admin_back_to_main(callback: types.CallbackQuery):

    try:
        board_id = callback.data.split("_")[2]
    except IndexError: return
    if not is_admin(callback.from_user.id, board_id):
        try: await callback.answer("Нет прав", show_alert=True)
        except: pass
        return
    b_data = board_data[board_id]
    lang = 'en' if board_id == 'int' else 'ru'
    user_settings = b_data.get('user_settings', {})
    gif_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_gif'))
    sticker_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_sticker'))
    reaction_ban_count = len(b_data.get('reaction_banned_users', set()))
    media_ban_count = sum(1 for s in user_settings.values() if s.get('shadow_media'))
    lie_media_count = sum(1 for s in user_settings.values() if s.get('lie_media'))
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        header_text = f"Admin panel for board {board_name}:"
        memo_text = (
            "<b>🗒️ Command Cheatsheet:</b>\n"
            "<code>/filter ...</code> - Manage spam filter\n"
            f"<code>/togglereactions &lt;id&gt;</code> - Ban reactions ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - Shadow Ban GIFs ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - Shadow Ban Stickers ({sticker_ban_count})\n"
            f"<code>/togglemedia &lt;id&gt;</code> - Shadow Ban Media ({media_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (reply) - Show who reacted"
        )
        btn_stats = "📊 Stats"
        btn_filter = "🤬 Filter"
        btn_restr = "🚫 Restrictions"
        btn_backup = "💾 Backup"
    elif lang == 'jp': # На всякий случай
        header_text = f"{board_name} 管理パネル:"
        memo_text = (
            "<b>🗒️ コマンド:</b>\n"
            "<code>/filter ...</code> - フィルタ管理\n"
            f"<code>/togglereactions &lt;id&gt;</code> - リアクション禁止 ({reaction_ban_count})\n"
            f"<code>/togglegif &lt;id&gt;</code> - GIF禁止 ({gif_ban_count})\n"
            f"<code>/togglestickers &lt;id&gt;</code> - スタンプ禁止 ({sticker_ban_count})\n"
            f"<code>/togglemedia &lt;id&gt;</code> - メディア禁止 ({media_ban_count})\n"
            f"<code>/lie &lt;id&gt;</code> - Archive media substitution ({lie_media_count})\n"
            "<code>/reactions</code> (返信) - リアクションした人を見る"
        )
        btn_stats = "📊 統計"
        btn_filter = "🤬 フィルタ"
        btn_restr = "🚫 制限"
        btn_backup = "💾 保存"
    else:
        header_text = f"Админка доски {board_name}:"
        memo_text = (
            f"{header_text}\n\n"
            "<code>/ban</code>, <code>/unban</code> — Бан/Разбан\n"
            "<code>/mute [время]</code>, <code>/unmute</code> — Мут\n"
            "<code>/shadowmute [время]</code> — Теневой мут\n"
            "<code>/gban</code>, <code>/gunban</code> — ГЛОБАЛЬНО\n\n"
            "<code>/del</code>, <code>/sdel</code> — Удаление\n"
            "<code>/pin</code>, <code>/unpin</code> — Закреп\n\n"
            "<code>/whois [id]</code> — Досье\n"
            f"<code>/togglegif</code> — Бан GIF ({gif_ban_count})\n"
            f"<code>/togglestickers</code> — Бан стикеров ({sticker_ban_count})\n\n"
            f"<code>/lie</code> — Подмена медиа архивом ({lie_media_count})\n\n"
            "<code>/say</code>, <code>/ans</code> — Ответы\n"
            "<code>/stop</code> — Стоп режимы"
        )
        btn_stats = "📊 Статистика"
        btn_filter = "🤬 Стоп-слова"
        btn_restr = "🚫 Ограничения (Баны/Муты)"
        btn_backup = "💾 Сохранить Бэкап"
    final_text = f"{header_text}\n\n{memo_text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_stats, callback_data=f"stats_{board_id}"),
         InlineKeyboardButton(text=btn_filter, callback_data=f"filter_list_{board_id}")],
        [InlineKeyboardButton(text=btn_restr, callback_data=f"restrictions_{board_id}")],
        [InlineKeyboardButton(text=btn_backup, callback_data="save_all")],
    ])
    try:
        await callback.message.edit_text(final_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
             print(f"Admin menu update error: {e}")
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
async def get_author_id_by_reply(msg: types.Message) -> int | None:
    if not msg.reply_to_message:
        return None
    target_chat_id = msg.reply_to_message.chat.id
    reply_mid = msg.reply_to_message.message_id
    lookup_key = (target_chat_id, reply_mid)
    post_num = message_to_post.get(lookup_key)
    if post_num and post_num in messages_storage:
        return messages_storage[post_num].get("author_id")
    db_author_id = await get_post_author_by_copy(target_chat_id, reply_mid)
    if db_author_id is not None:
        return db_author_id
        
    return None
@dp.message(Command("id"))
async def cmd_get_id(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: return
    if not is_admin(message.from_user.id, board_id):
        await message.delete()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    target_id = message.from_user.id
    if lang == 'en': info_header = "🆔 <b>Info about you:</b>\n\n"
    elif lang == 'jp': info_header = "🆔 <b>あなたについて:</b>\n\n"
    else: info_header = "🆔 <b>Информация о вас:</b>\n\n"
    if message.reply_to_message:
        replied_author_id = None
        async with storage_lock:
            replied_author_id = await get_author_id_by_reply(message)
        if replied_author_id == 0:
            msg = "ℹ️ System message (bot)." if lang == 'en' else ("ℹ️ システムメッセージ（ボット）。" if lang == 'jp' else "ℹ️ Вы ответили на системное сообщение (автор: бот).")
            await message.answer(msg)
            await message.delete()
            return
        if replied_author_id:
            target_id = replied_author_id
            if lang == 'en': info_header = "🆔 <b>User Info:</b>\n\n"
            elif lang == 'jp': info_header = "🆔 <b>ユーザー情報:</b>\n\n"
            else: info_header = "🆔 <b>Информация о пользователе:</b>\n\n"
    try:
        user_chat_info = await message.bot.get_chat(target_id)
        info = info_header
        info += f"ID: <code>{target_id}</code>\n"
        if user_chat_info.first_name:
            name_lbl = "Name" if lang == 'en' else ("名前" if lang == 'jp' else "Имя")
            info += f"{name_lbl}: {escape_html(user_chat_info.first_name)}\n"
        if user_chat_info.last_name:
            sname_lbl = "Surname" if lang == 'en' else ("名字" if lang == 'jp' else "Фамилия")
            info += f"{sname_lbl}: {escape_html(user_chat_info.last_name)}\n"
        if user_chat_info.username:
            info += f"Username: @{user_chat_info.username}\n"
        b_data = board_data[board_id]
        status_lbl = f"Status on {BOARD_CONFIG[board_id]['name']}" if lang == 'en' else (f"{BOARD_CONFIG[board_id]['name']} でのステータス" if lang == 'jp' else f"Статус на доске {BOARD_CONFIG[board_id]['name']}")
        if target_id in b_data['users']['banned']:
            info += f"\n⛔️ {status_lbl}: BANNED"
        elif target_id in b_data['users']['active']:
            info += f"\n✅ {status_lbl}: Active"
        else:
            info += f"\nℹ️ {status_lbl}: Inactive"
        await message.answer(info, parse_mode="HTML")
    except Exception:
        msg = f"User ID: <code>{target_id}</code>" if lang == 'en' else (f"ユーザーID: <code>{target_id}</code>" if lang == 'jp' else f"ID пользователя: <code>{target_id}</code>")
        await message.answer(msg, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("ban"))
async def cmd_ban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    target_id: int | None = None
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    parts = message.text.split()
    if len(parts) == 2 and parts[1].isdigit():
        target_id = int(parts[1])
    if not target_id:
        await message.answer("Нужно ответить на сообщение или указать ID: <code>/ban &lt;id&gt;</code>", parse_mode="HTML")
        return
    deleted_posts = await delete_user_posts(message.bot, target_id, 5, board_id)
    await log_global_event('bot', f"🔨 BAN: Мод {message.from_user.id} забанил {target_id} на /{board_id}/ (удалено {deleted_posts} пст)")
    async with storage_lock:
        b_data = board_data[board_id]
        b_data['users']['banned'].add(target_id)
        b_data['users']['active'].discard(target_id)
        caches_to_clean = [
            b_data['last_activity'], b_data['last_texts'], b_data['last_stickers'],
            b_data['last_animations'], b_data['last_audios'], b_data['spam_violations'],
            b_data['spam_tracker'], b_data['last_user_msgs'], b_data['message_counter'],
            b_data['user_state'], b_data['mutes'], b_data['shadow_mutes']
        ]
        if 'user_settings' in b_data:
             b_data['user_settings'].pop(target_id, None)
        for cache in caches_to_clean:
            cache.pop(target_id, None)
    await update_user_status(target_id, board_id, 'banned')
    lang = 'en' if board_id == 'int' else 'ru'
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        phrases = [
            "✅ Faggot <code>{user_id}</code> has been banned from {board}.\nDeleted his posts in the last 5 minutes: {deleted}",
            "👍 User <code>{user_id}</code> is now banned on {board}. Wiped {deleted} recent posts.",
            "👌 Done. <code>{user_id}</code> won't be posting on {board} anymore. Deleted posts: {deleted}."
        ]
    else:
        phrases = [
            "✅ Хуесос под номером <code>{user_id}</code> забанен на доске {board}\nУдалено его постов за последние 5 минут: {deleted}",
            "👍 Пользователь <code>{user_id}</code> успешно забанен на доске {board}. Снесено {deleted} его высеров.",
            "👌 Готово. <code>{user_id}</code> больше не будет отсвечивать на доске {board}. Удалено постов: {deleted}."
        ]
    response_text = random.choice(phrases).format(user_id=target_id, board=board_name, deleted=deleted_posts)
    await message.answer(response_text, parse_mode="HTML")
    await send_moderation_notice(target_id, "ban", board_id, deleted_posts=deleted_posts)
    try:
        if lang == 'en':
            phrases = [
                "You have been permanently banned from the {board} board. Reason: you're a faggot.\nDeleted your posts in the last 5 minutes: {deleted}",
                "Congratulations! You've won an all-inclusive trip to hell. You are banned from {board}.\nWe've deleted {deleted} of your recent shitposts.",
                "The admin didn't like you. You're banned from {board}. Get out.\nDeleted posts: {deleted}.",
                "You have been banned from {board}. See you in hell. Пиздуй отсюда."
            ]
        else:
            phrases = [
                "Пидорас ебаный, ты нас так заебал, что тебя блокнули нахуй на доске {board}.\nУдалено твоих постов за последние 5 минут: {deleted}\nПиздуй отсюда.",
                "Поздравляю, долбоеб. Ты допизделся и получил вечный бан на доске {board}.\nТвои высеры за последние 5 минут ({deleted} шт.) удалены.",
                "Ты был слаб, и Абу тебя сожрал. Ты забанен на доске {board}.\nУдалено постов: {deleted}.",
                "🖕 ТЫ НАС ЗАЕБАЛ. БАН НА ДОСКЕ {board}. ПОПРОЩАЙСЯ СО СВОИМИ {deleted} ПОСТАМИ",
                "☠️ ТЫ УМЕР ДЛЯ ЭТОГО ЧАТА. БАН НАВСЕГДА. ПОТЕРЯНО ПОСТОВ: {deleted}",
                "💀 ВАШ АККАУНТ БЫЛ ДОБАВЛЕН В БАЗУ ФСБ. ПРИЯТНОГО ДНЯ!",
                "🚫 ВЫ ЗАБАНЕНЫ. ПОПРОЩАЙТЕСЬ СО СВОИМИ {deleted} ПОСТАМИ.",
                "⛔ ВЫ ПОЛУЧИЛИ ВЕЧНЫЙ БАН НА ДОСКЕ {board}. УДАЛЕНО ПОСТОВ: {deleted}.",
                "❌ ВЫ ЗАЕБАЛИ ВСЕХ. БАН НА ДОСКЕ {board}. УДАЛЕНО ПОСТОВ: {deleted}."
            ]
        notification_text = random.choice(phrases).format(board=board_name, deleted=deleted_posts)
        await message.bot.send_message(target_id, notification_text, parse_mode="HTML")
    except:
        pass
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("wipe"))
async def cmd_wipe(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    command_args = message.text.split()[1:]
    target_id = None
    duration_str = "1h" 
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
        if command_args:
            duration_str = command_args[0]
    elif command_args:
        try:
            target_id = int(command_args[0])
            if len(command_args) > 1:
                duration_str = command_args[1]
        except (ValueError, IndexError):
            if message.reply_to_message:
                duration_str = command_args[0]
                async with storage_lock:
                    target_id = await get_author_id_by_reply(message)
            else:
                await message.answer("❌ Invalid User ID.")
                try: await message.delete()
                except TelegramBadRequest: pass
                return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/wipe &lt;id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/wipe &lt;ID&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/wipe &lt;id&gt; [время]</code> или ответом на сообщение <code>[время]</code>"
        await message.answer(usage, parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): 
            time_period_minutes = int(duration_str[:-1])
            duration_text = f"{time_period_minutes} min"
        elif duration_str.endswith("h"): 
            time_period_minutes = int(duration_str[:-1]) * 60
            duration_text = f"{int(duration_str[:-1])} hours"
        elif duration_str.endswith("d"): 
            time_period_minutes = int(duration_str[:-1]) * 1440
            duration_text = f"{int(duration_str[:-1])} days"
        else: 
            time_period_minutes = int(duration_str)
            duration_text = f"{time_period_minutes} min"
    except (ValueError, AttributeError):
        await message.answer("❌ Error format (Ex: <code>30m</code>, <code>2h</code>).", parse_mode="HTML")
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    deleted_messages = await delete_user_posts(message.bot, target_id, time_period_minutes, board_id)
    board_name = BOARD_CONFIG[board_id]['name']
    if lang == 'en':
        msg = f"🗑 Deleted {deleted_messages} messages from <code>{target_id}</code> on {board_name} for last {duration_text}."
    elif lang == 'jp':
        msg = f"🗑 {board_name} で <code>{target_id}</code> の過去 {duration_text} 分のメッセージ {deleted_messages} 件を削除しました。"
    else:
        msg = f"🗑 Удалено {deleted_messages} сообщений пользователя <code>{target_id}</code> с доски {board_name} за последние {duration_text}."
    await message.answer(msg, parse_mode="HTML")
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("restrict_anime"))
async def cmd_restrict_anime(message: Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return

    target_id = None
    args = message.text.split()
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
    elif len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')

    if not target_id:
        msg = "Usage: <code>/restrict_anime &lt;id&gt;</code> or reply." if lang != 'ru' else "Использование: <code>/restrict_anime &lt;id&gt;</code> или ответ на сообщение."
        await message.answer(msg, parse_mode="HTML")
        return

    b_data = board_data[board_id]
    async with storage_lock:
        if target_id in b_data['anime_strict_limits']:
            b_data['anime_strict_limits'].remove(target_id)
            action_log = "REMOVED FROM STRICT LIMITS"
            if lang == 'en':
                res = f"✅ User <code>{target_id}</code> removed from strict anime limits."
            elif lang == 'jp':
                res = f"✅ ユーザー <code>{target_id}</code> のアニメリミットを解除しました。"
            else:
                res = f"✅ С пользователя <code>{target_id}</code> снято жесткое ограничение на аниме."
        else:
            b_data['anime_strict_limits'].add(target_id)
            action_log = "ADDED TO STRICT LIMITS (10/day)"
            if lang == 'en':
                res = f"🚫 User <code>{target_id}</code> now restricted to 10 anime images per 24h."
            elif lang == 'jp':
                res = f"🚫 ユーザー <code>{target_id}</code> に1日10枚の制限をかけました。"
            else:
                res = f"🚫 Пользователю <code>{target_id}</code> установлено ограничение: 10 картинок в сутки."

    await log_global_event('bot', f"🛡️ ANIME_LIMIT: Админ {message.from_user.id} {action_log} для {target_id} на /{board_id}/")
    await message.answer(res, parse_mode="HTML")
    try:
        await message.delete()
    except:
        pass
@dp.message(Command("shadowmute_threads"))
async def cmd_shadowmute_threads(message: Message, board_id: str | None, stream: str = 'ru'):

    if not board_id or not is_admin(message.from_user.id, board_id) or board_id not in THREAD_BOARDS:
        await message.delete()
        return
    args = message.text.split()[1:]
    target_id = None
    duration_str = "10m" 
    if message.reply_to_message:
        async with storage_lock:
            target_id = await get_author_id_by_reply(message)
        if args: duration_str = args[0]
    elif args:
        try:
            target_id = int(args[0])
            if len(args) > 1: duration_str = args[1]
        except ValueError: pass
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not target_id:
        if lang == 'en':
            usage = "Usage: <code>/shadowmute_threads &lt;user_id&gt; [time]</code> or reply."
        elif lang == 'jp':
            usage = "使用法: <code>/shadowmute_threads &lt;user_id&gt; [時間]</code> または返信。"
        else:
            usage = "Использование: <code>/shadowmute_threads &lt;user_id&gt; [время]</code> или ответ на сообщение."
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        duration_str = duration_str.lower().replace(" ", "")
        if duration_str.endswith("m"): total_seconds, time_str = int(duration_str[:-1]) * 60, f"{int(duration_str[:-1])} мин"
        elif duration_str.endswith("h"): total_seconds, time_str = int(duration_str[:-1]) * 3600, f"{int(duration_str[:-1])} час"
        elif duration_str.endswith("d"): total_seconds, time_str = int(duration_str[:-1]) * 86400, f"{int(duration_str[:-1])} дней"
        else: total_seconds, time_str = int(duration_str) * 60, f"{int(duration_str)} мин"
    except (ValueError, AttributeError):
        await message.answer("❌ Error format. Ex: 10m, 2h, 1d" if lang == 'en' else "❌ Неверный формат. Примеры: 10m, 2h, 1d")
        await message.delete()
        return
    expires_ts = time.time() + total_seconds
    b_data = board_data[board_id]
    threads_data = b_data.get('threads_data', {})
    for thread_info in threads_data.values():
        thread_info.setdefault('local_shadow_mutes', {})[target_id] = expires_ts
    phrases = thread_messages.get(lang, {}).get('shadowmute_threads_success', ["Shadowmuted in threads."])
    response_text = random.choice(phrases).format(
        user_id=target_id, 
        duration=str(int(total_seconds / 60))
    )
    await message.answer(response_text)
    await message.delete()
@dp.message(Command("sdel", "swipe"))
async def cmd_sdel(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    "Теневое" удаление поста. Удаляет все копии сообщения, кроме
    копии у автора оригинального поста. Доступно только админам.
    """
    if not board_id or not is_admin(message.from_user.id, board_id):
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        if lang == 'en': msg = "Reply to a message to use this."
        elif lang == 'jp': msg = "メッセージに返信して使用してください。"
        else: msg = "Эта команда работает только через ответ на сообщение."
        await message.answer(msg)
        await message.delete()
        return
    post_info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
    if not post_info:
        err = "Post not found in DB." if lang == 'en' else "Не удалось найти исходный пост в базе данных."
        await message.answer(err)
        await message.delete()
        return
    post_num, author_id = post_info
    all_copies = await get_post_copies(post_num)
    if not all_copies:
        err = f"No copies found for #{post_num}." if lang == 'en' else f"Не найдено отправленных копий для поста #{post_num}."
        await message.answer(err)
        await message.delete()
        return
    tasks = []
    for recipient_id, message_id in all_copies:
        if recipient_id != author_id:
            task = message.bot.delete_message(recipient_id, message_id)
            tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    deleted_count = sum(1 for res in results if res is True)
    await log_global_event('bot', f"👻 SDEL: Админ {message.from_user.id} скрытно удалил пост #{post_num} на /{board_id}/ (удалено {deleted_count} копий)")
    if lang == 'en':
        report = f"👻 Post #{post_num} shadow deleted.\nRemoved copies: {deleted_count} of {len(all_copies) - 1}."
    elif lang == 'jp':
        report = f"👻 投稿 #{post_num} をシャドウ削除しました。\n削除数: {deleted_count} / {len(all_copies) - 1}."
    else:
        report = f"👻 Пост #{post_num} был 'теневым' образом удален.\nУдалено копий: {deleted_count} из {len(all_copies) - 1}."
    await message.answer(report)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("unban"))
async def cmd_unban(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    args = message.text.split()
    if len(args) < 2:
        if lang == 'en': usage = "Usage: <code>/unban &lt;user_id&gt;</code>"
        elif lang == 'jp': usage = "使用法: <code>/unban &lt;user_id&gt;</code>"
        else: usage = "Использование: <code>/unban &lt;user_id&gt;</code>"
        await message.answer(usage, parse_mode="HTML")
        return
    try:
        user_id = int(args[1])
        unbanned = False
        async with storage_lock:
            b_data = board_data[board_id]
            if user_id in b_data['users']['banned']:
                b_data['users']['banned'].discard(user_id)
                b_data['users']['active'].add(user_id)
                unbanned = True
        board_name = BOARD_CONFIG[board_id]['name']
        if unbanned:
             await add_or_activate_user(user_id, board_id) 
             if lang == 'en': msg = f"User {user_id} unbanned on {board_name}."
             elif lang == 'jp': msg = f"ユーザー {user_id} のBANを解除しました ({board_name})。"
             else: msg = f"Пользователь {user_id} разбанен на доске {board_name}."
             await message.answer(msg)
        else:
            if lang == 'en': msg = f"User {user_id} was not banned."
            elif lang == 'jp': msg = f"ユーザー {user_id} はBANされていません。"
            else: msg = f"Пользователь {user_id} не был забанен на этой доске."
            await message.answer(msg)
    except ValueError:
        await message.answer("Invalid ID")
    await message.delete()
@dp.message(Command("del"))
async def cmd_del(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id or not is_admin(message.from_user.id, board_id): return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if not message.reply_to_message:
        msg = "Reply to a message." if lang == 'en' else ("メッセージに返信してください。" if lang == 'jp' else "Ответь на сообщение.")
        await message.answer(msg)
        return
    post_num = None
    async with storage_lock:
        key = (message.chat.id, message.reply_to_message.message_id)
        post_num = message_to_post.get(key)
    if not post_num:
        info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
        if info: post_num = info[0]
    if post_num is None:
        err = "Post not found." if lang == 'en' else ("投稿が見つかりません。" if lang == 'jp' else "Не нашёл этот пост (возможно, он слишком старый или удален).")
        await message.answer(err)
        return
    deleted_count = await delete_single_post(post_num, message.bot)
    await log_global_event('bot', f"🗑️ DEL: Админ {message.from_user.id} удалил пост #{post_num} на /{board_id}/ (и {deleted_count} копий)")
    if lang == 'en':
        resp = f"🗑 Post #{post_num} and copies ({deleted_count}) deleted."
    elif lang == 'jp':
        resp = f"🗑 投稿 #{post_num} とコピー ({deleted_count}件) を削除しました。"
    else:
        resp = f"🗑 Пост №{post_num} и копии ({deleted_count}) удалены."
    await message.answer(resp)
    try: await message.delete()
    except: pass
@dp.message(Command("token"))
async def cmd_token(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    Генерирует или показывает пользователю его персональный токен для входа на сайт.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    try:
        token = await get_or_create_api_token(user_id, generate_unique_token)
        WEBAPP_URL_DISPLAY = "https://tgach.top" 
        if lang == 'en':
            response_text = (
                "🔑 **Your personal token for website access:**\n\n"
                f"Use it to log in on {WEBAPP_URL_DISPLAY}. **Do not share it with anyone.**\n\n"
                "Tap the token below to copy it:"
            )
        elif lang == 'jp':
            response_text = (
                "🔑 **ウェブサイトアクセスのための個人トークン:**\n\n"
                f"{WEBAPP_URL_DISPLAY} でログインするために使用します。**他人には教えないでください。**\n\n"
                "下のトークンをタップしてコピー:"
            )
        else:
            response_text = (
                "🔑 **Ваш токен для входа на сайт ТГАЧа:**\n\n"
                f"Используйте его для входа на {WEBAPP_URL_DISPLAY}.\n**Никому его не показывайте.**\n\n"
                "Нажмите на токен ниже, чтобы скопировать его:"
            )
        token_display = f"<code>{token}</code>"
        await message.answer(response_text, parse_mode="HTML")
        await message.answer(token_display, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Критическая ошибка при генерации токена для user {user_id}: {e}")
        if lang == 'en': error = "An error occurred while creating the token."
        elif lang == 'jp': error = "トークンの作成中にエラーが発生しました。"
        else: error = "Произошла ошибка при создании токена."
        await message.answer(error)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
@dp.message(Command("poll", "opros"))
async def cmd_poll(message: types.Message, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Точка входа в FSM для создания опроса.
    """
    if not board_id: return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now = time.time()
    if now - last_poll_creation_time[user_id] < 60:
        await message.delete()
        try:
            if lang == 'en':
                cooldown_msg = "⏳ Poll creation is allowed once per minute."
            elif lang == 'jp':
                cooldown_msg = "⏳ 投票の作成は1分に1回までです。"
            else:
                cooldown_msg = "⏳ Создавать опросы можно раз в минуту."
            sent = await message.answer(cooldown_msg)
            asyncio.create_task(delete_message_after_delay(sent, 5))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return
    full_text = message.text or message.caption or ""
    if message.reply_to_message and message.reply_to_message.media_group_id:
        await message.delete()
        if lang == 'en':
            error_text = "Attaching media groups to polls is not supported. Please reply to a single photo or video."
        elif lang == 'jp':
            error_text = "メディアグループを投票に添付することはできません。単一の画像または動画に返信してください。"
        else:
            error_text = "Прикрепление медиагрупп к опросам не поддерживается. Пожалуйста, ответьте на одно конкретное фото или видео."
        try:
            await message.answer(error_text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return
    command_part, *data_parts = full_text.split('|', 1)
    question_text = command_part.replace("/poll", "").replace("/opros", "").strip()
    options = [opt.strip() for opt in data_parts[0].split('|')] if data_parts else []
    if not question_text or len(options) < 2 or len(options) > 5:
        await message.delete()
        if lang == 'en':
            usage_text = (
                "<b>Invalid format!</b>\n"
                "Use the separator `|` between the question and each option.\n\n"
                "<u>Example:</u>\n"
                "<code>/poll Is Abu gay? | Yes | Of course | Absolutely</code>\n\n"
                "<i>(2 to 5 options)</i>"
            )
        elif lang == 'jp':
            usage_text = (
                "<b>フォーマットエラー！</b>\n"
                "質問と各選択肢の間に区切り文字 `|` を使用してください。\n\n"
                "<u>例:</u>\n"
                "<code>/poll Abuはホモ？ | はい | もちろん | 絶対に</code>\n\n"
                "<i>(選択肢は2〜5個)</i>"
            )
        else:
            usage_text = (
                "<b>Неверный формат!</b>\n"
                "Используйте разделитель `|` между вопросом и каждым вариантом ответа.\n\n"
                "<u>Пример:</u>\n"
                "<code>/poll Абу сосет хуй? | Да | Конечно | Безусловно</code>\n\n"
                "<i>(От 2 до 5 вариантов ответа)</i>"
            )
        try:
            await message.answer(usage_text, parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return
    attached_media = None
    reply_to_check = message
    if message.text and message.reply_to_message:
        reply_to_check = message.reply_to_message
    media_type = reply_to_check.content_type
    if media_type in ['photo', 'video', 'animation']:
        file_id_obj = getattr(reply_to_check, media_type)
        if isinstance(file_id_obj, list): file_id_obj = file_id_obj[-1]
        attached_media = {'type': media_type, 'file_id': file_id_obj.file_id}
    poll_fsm_data = {
        'question': question_text,
        'options': options,
        'attached_media': attached_media
    }
    await state.set_state(PollCreationStates.waiting_for_confirmation)
    await state.update_data(poll_data=poll_fsm_data)
    last_poll_creation_time[user_id] = now
    temp_poll_display_data = {
        'question': question_text,
        'options': options,
        'votes': {str(i): [] for i in range(len(options))}
    }
    preview_text = generate_poll_text_display(temp_poll_display_data)
    if lang == 'en':
        confirm_text = f"Here is how your poll will look:\n\n{preview_text}\n\nCreate?"
        btn_yes, btn_no = "✅ Yes, create", "❌ Cancel"
    elif lang == 'jp':
        confirm_text = f"投票は以下のようになります:\n\n{preview_text}\n\n作成しますか？"
        btn_yes, btn_no = "✅ 作成", "❌ キャンセル"
    else:
        confirm_text = f"Так будет выглядеть ваш опрос:\n\n{preview_text}\n\nСоздаем?"
        btn_yes, btn_no = "✅ Да, создать", "❌ Отмена"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=btn_yes, callback_data="poll_confirm_create"),
            InlineKeyboardButton(text=btn_no, callback_data="poll_cancel_create")
        ]
    ])
    try:
        if attached_media:
            media_type = attached_media['type']
            file_id = attached_media['file_id']
            caption = confirm_text
            if len(caption) > 1024: caption = caption[:1021] + "..."
            if media_type == 'photo':
                await message.answer_photo(photo=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'video':
                await message.answer_video(video=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            elif media_type == 'animation':
                await message.answer_animation(animation=file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(confirm_text, reply_markup=keyboard, parse_mode="HTML")
        await message.delete()
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        print(f"Ошибка при отправке предпросмотра опроса: {e}")
        await state.clear()
        try:
            err_msg = "Failed to send preview." if lang == 'en' else ("プレビューの送信に失敗しました。" if lang == 'jp' else "Не удалось отправить предпросмотр.")
            await message.answer(err_msg)
            await message.delete()
        except Exception:
            pass
@dp.callback_query(F.data == "poll_cancel_create", PollCreationStates.waiting_for_confirmation)
async def cq_poll_cancel_create(callback: types.CallbackQuery, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Отменяет создание опроса.
    Исправлено: Добавлена локализация (перевод) и защита от тайм-аута.
    """
    await state.clear()
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = "❌ Cancelled"
    elif lang == 'jp':
        text = "❌ キャンセルされました"
    else:
        text = "❌ Отменено"
    try:
        await callback.answer(text) 
        await callback.message.delete()
    except TelegramBadRequest:
        pass
@dp.callback_query(F.data == "poll_confirm_create", PollCreationStates.waiting_for_confirmation)
async def cq_poll_confirm_create(callback: types.CallbackQuery, state: FSMContext, board_id: str | None, stream: str = 'ru'):
    """
    Подтверждает создание опроса.
    Исправлено: Защита от тайм-аута callback и обработки дублей.
    """
    if not board_id or not isinstance(callback.message, types.Message):
        try:
            await callback.answer("Ошибка: не удалось определить доску.")
        except TelegramBadRequest:
            pass
        await state.clear()
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        phrases = POLL_CREATION_SUCCESS_PHRASES_EN
    elif lang == 'jp':
        phrases = POLL_CREATION_SUCCESS_PHRASES_JP
    else:
        phrases = POLL_CREATION_SUCCESS_PHRASES
    try:
        await callback.answer(random.choice(phrases), show_alert=True)
        await callback.message.delete()
    except TelegramBadRequest as e:
        if "query is too old" in str(e):
            print(f"INFO: Poll confirmed by user {callback.from_user.id}, but callback expired. Proceeding.")
        else:
            print(f"WARNING: Non-critical error during poll confirmation UI update: {e}")
    user_id = callback.from_user.id
    fsm_data = await state.get_data()
    poll_data = fsm_data.get('poll_data')
    await state.clear()
    if not poll_data:
        return
    final_content = {
        'type': 'text', 
        'text': '', 
        'poll_data': {
            'question': poll_data['question'],
            'options': poll_data['options'],
            'votes': {}, 
            'voted_users': {} 
        }
    }
    attached_media = poll_data.get('attached_media')
    if attached_media:
        final_content['type'] = attached_media['type']
        final_content['file_id'] = attached_media['file_id']
        final_content['caption'] = '' 
    await process_new_post(
        bot_instance=callback.bot,
        board_id=board_id,
        user_id=user_id,
        content=final_content,
        reply_to_post=None,
        is_shadow_muted=False, 
        stream=stream
    )
@dp.callback_query(F.data.startswith("poll_vote_"))
async def cq_poll_vote(callback: types.CallbackQuery, board_id: str | None, stream: str = 'ru'):
    """
    Обрабатывает голос пользователя в опросе.
    Исправлено: Добавлена защита от ошибки "query is too old".
    """
    if not board_id or not isinstance(callback.message, types.Message):
        try:
            await callback.answer("Какая-то хуйня. Проголосовать не вышло", show_alert=True)
        except TelegramBadRequest:
            pass
        return
    user_id = callback.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now = time.time()
    if now - last_poll_vote_time.get(user_id, 0) < POLL_VOTE_COOLDOWN:
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass
        return
    last_poll_vote_time[user_id] = now
    b_data = board_data[board_id]
    is_shadow_muted = (user_id in b_data.get('shadow_mutes', {}) and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    if is_shadow_muted:
        if lang == 'en': success_phrases = POLL_VOTE_SUCCESS_PHRASES_EN
        elif lang == 'jp': success_phrases = POLL_VOTE_SUCCESS_PHRASES_JP
        else: success_phrases = POLL_VOTE_SUCCESS_PHRASES
        try:
            await callback.answer(random.choice(success_phrases))
        except TelegramBadRequest:
            pass
        return # ВАЖНО: Выходим, не трогая базу данных!
    try:
        parts = callback.data.split('_')
        post_num = int(parts[2])
        option_index = int(parts[3])
    except (ValueError, IndexError):
        try:
            await callback.answer("Error: Invalid poll data.", show_alert=True)
        except TelegramBadRequest:
            pass
        return
    post_updated = False
    content_for_db = None
    async with storage_lock:
        post_data = messages_storage.get(post_num)
        if not post_data or 'content' not in post_data:
            if lang == 'en': msg = "This poll is outdated and no longer active."
            elif lang == 'jp': msg = "この投票は古すぎて無効です。"
            else: msg = "Этот опрос устарел и больше не активен."
            try:
                await callback.answer(msg, show_alert=True)
                await callback.message.edit_reply_markup(reply_markup=None)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            return
        poll_data = post_data['content'].get('poll_data')
        if not poll_data:
            try:
                await callback.answer("Error: Invalid poll data.", show_alert=True)
            except TelegramBadRequest:
                pass
            return
        if user_id in poll_data.get('voted_users', {}):
            if lang == 'en': msg = "You have already voted."
            elif lang == 'jp': msg = "すでに投票済みです。"
            else: msg = "Вы уже голосовали в этом опросе."
            try:
                await callback.answer(msg, show_alert=True)
            except TelegramBadRequest:
                pass
            return
        option_key = str(option_index)
        if 0 <= option_index < len(poll_data.get('options', [])):
            poll_data.setdefault('votes', {}).setdefault(option_key, []).append(user_id)
            poll_data.setdefault('voted_users', {})[user_id] = option_key
            post_updated = True
            content_for_db = post_data['content'].copy()
        else:
            try:
                await callback.answer("Error: Invalid option.", show_alert=True)
            except TelegramBadRequest:
                pass
            return
    if post_updated:
        if lang == 'en': phrases = POLL_VOTE_SUCCESS_PHRASES_EN
        elif lang == 'jp': phrases = POLL_VOTE_SUCCESS_PHRASES_JP
        else: phrases = POLL_VOTE_SUCCESS_PHRASES
        try:
            await callback.answer(random.choice(phrases))
        except TelegramBadRequest:
            pass
        if content_for_db:
            await update_post_content(post_num, content_for_db)
        async with pending_edit_lock:
            if post_num in pending_edit_tasks:
                pending_edit_tasks[post_num].cancel()
            new_task = asyncio.create_task(
                execute_delayed_edit(
                    post_num=post_num,
                    bot_instance=callback.bot,
                    author_id=None,
                    notify_text=None,
                    delay=2.0
                )
            )
            pending_edit_tasks[post_num] = new_task
@dp.message(Command("roll", "roulette", "ruletka", "rulet"))
async def cmd_roll(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id: 
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    async with roulette_lock:
        async with storage_lock:
            b_data = board_data[board_id]
            current_time = time.time()
            last_usage = b_data.get('last_roll_time', {}).get(user_id, 0)
            if current_time - last_usage < 60:
                if lang == 'en': cooldown_msg = "⏳ Roulette is on cooldown!"
                elif lang == 'jp': cooldown_msg = "⏳ ルーレットはクールダウン中です！"
                else: cooldown_msg = random.choice(ROULETTE_COOLDOWN_PHRASES)
                try:
                    sent_msg = await message.answer(cooldown_msg)
                    asyncio.create_task(delete_message_after_delay(sent_msg, 5))
                except (TelegramBadRequest, TelegramForbiddenError): pass
                try: await message.delete()
                except TelegramBadRequest: pass
                return
            b_data.setdefault('last_roll_time', {})[user_id] = current_time
    if not ROULETTE_EVENTS:
        if lang == 'en': error_text = "Roulette data is not loaded."
        elif lang == 'jp': error_text = "ルーレットデータが読み込まれていません。"
        else: error_text = "Данные рулетки не загружены."
        try: await message.answer(error_text)
        except (TelegramBadRequest, TelegramForbiddenError): pass
        return
    working_msg = None
    try:
        if lang == 'en': work_txt = "⏳ Spinning the wheel..."
        elif lang == 'jp': work_txt = "⏳ ルーレットを回しています..."
        else: work_txt = "⏳ Кручу барабан..."
        working_msg = await message.answer(work_txt)
        event = get_random_event(ROULETTE_EVENTS)
        if not event:
            raise ValueError("Failed to get random event.")
        event_id = event.get('id', '???')
        event_desc_plain = event.get('description', '...')
        text_for_image = f"[{event_id}]\n\n{event_desc_plain}"
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(None, generate_wipe_image, text_for_image)
        if image_bytes:
            photo = types.BufferedInputFile(image_bytes, filename="roll_result.png")
            caption_header = random.choice(ROULETTE_RESULT_PHRASES) # Пока оставим общие
            await message.answer_photo(photo, caption=caption_header)
        else:
            print(f"⚠️ [cmd_roll] Image generation failed. Sending text.")
            result_header = random.choice(ROULETTE_RESULT_PHRASES)
            event_desc_html = escape_html(event_desc_plain)
            result_text = f"{result_header}\n\n<b>[{event_id}]</b> {event_desc_html}"
            await message.answer(result_text, parse_mode="HTML")
    except Exception as e:
        print(f"⛔ Ошибка в cmd_roll: {e}")
        if lang == 'en': err = "Error during roulette spin."
        elif lang == 'jp': err = "ルーレット中にエラーが発生しました。"
        else: err = "Произошла ошибка при выполнении ролла."
        try: await message.answer(err)
        except (TelegramBadRequest, TelegramForbiddenError): pass
    finally:
        if working_msg:
            try: await working_msg.delete()
            except TelegramBadRequest: pass
        try: await message.delete()
        except TelegramBadRequest: pass
@dp.message(F.text.regexp(r"^/\w+(@\w+)?\b"))
async def handle_unknown_command_spam(message: types.Message):
    """
    Отлавливает все неопознанные команды и применяет к ним анти-спам политику.
    """
    user_id = message.from_user.id
    current_time = time.time()
    unknown_command_tracker[user_id] = [t for t in unknown_command_tracker[user_id] if current_time - t < 4]
    if unknown_command_tracker[user_id] and isinstance(unknown_command_tracker[user_id][-1], float):
        if current_time < unknown_command_tracker[user_id][-1]:
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return
    unknown_command_tracker[user_id].append(current_time)
    command_timestamps = [t for t in unknown_command_tracker[user_id] if isinstance(t, (int, float))]
    if len(command_timestamps) > 2:
        ban_until = current_time + 20
        unknown_command_tracker[user_id] = [ban_until]
        try:
            user_lang_code = message.from_user.language_code or 'en'
            if 'ja' in user_lang_code:
                msg = "コマンドを送信しすぎです。20秒お待ちください。"
            elif 'ru' in user_lang_code or 'uk' in user_lang_code or 'be' in user_lang_code:
                msg = "Слишком много неизвестных команд. Подождите 20 секунд."
            else:
                msg = "Too many unknown commands. Wait 20 seconds."
            await message.answer(msg, disable_notification=True)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@dp.message(F.audio, ~F.media_group_id)
async def handle_audio(message: Message, board_id: str | None, stream: str = 'ru'): 
    user_id = message.from_user.id
    if not board_id: return
    b_data = board_data[board_id]
    if user_id in b_data['users']['banned'] or \
       (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
        await message.delete()
        return
    b_data['last_activity'][user_id] = datetime.now(UTC)
    if not await check_spam(user_id, message, board_id):
        try:
            await message.delete()
            await apply_penalty(message.bot, user_id, 'audio', board_id)
        except TelegramBadRequest: pass
        return
    try:
        await message.delete()
    except TelegramBadRequest: pass
    
    # --- ИЗМЕНЕНИЕ: Проверка Shadow Mute + Shadow Media ---
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if user_settings.get('shadow_media'):
        is_shadow_muted = True
    # ----------------------------------------------------

    reply_to_post = None
    if message.reply_to_message:
        async with storage_lock:
            lookup_key = (message.chat.id, message.reply_to_message.message_id)
            reply_to_post = message_to_post.get(lookup_key)
        if not reply_to_post:
            info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if info:
                reply_to_post = info[0]
                async with storage_lock:
                    message_to_post[lookup_key] = reply_to_post
            else:
                pass
    raw_caption_html = message.caption_html_text if hasattr(message, 'caption_html_text') else (message.caption or "")
    safe_caption_html = sanitize_html(raw_caption_html)
    content = {
        'type': 'audio',
        'file_id': message.audio.file_id,
        'caption': safe_caption_html 
    }
    if message.caption:
        async with storage_lock:
            last_messages.append(message.caption)


    quote_info_for_post = await build_quick_quote_info(reply_to_post)
    
    # Добавляем quote_info в контент, чтобы он дошел до send_message_to_users
    content['quote_info'] = quote_info_for_post

    # Если теневой бан (включая запрет медиа), отправляем фейк
    if is_shadow_muted:
        await process_shadow_reject(
            bot=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            stream=stream
        )
    else:
        await process_new_post(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        )
@dp.message(F.voice, ~F.media_group_id)
async def handle_voice(message: Message, board_id: str | None, stream: str = 'ru'): 
    user_id = message.from_user.id
    if not board_id: return
    b_data = board_data[board_id]
    if user_id in b_data['users']['banned'] or (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    b_data['last_activity'][user_id] = datetime.now(UTC)
    if not await check_spam(user_id, message, board_id):
        try:
            await message.delete()
            await apply_penalty(message.bot, user_id, 'animation', board_id) # Voice often treated similarly for spam
        except TelegramBadRequest: pass
        return
    try:
        await message.delete()
    except TelegramBadRequest: pass

    # --- ИЗМЕНЕНИЕ: Проверка Shadow Mute + Shadow Media ---
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if user_settings.get('shadow_media'):
        is_shadow_muted = True
    # ----------------------------------------------------

    reply_to_post = None
    if message.reply_to_message:
        async with storage_lock:
            lookup_key = (message.chat.id, message.reply_to_message.message_id)
            reply_to_post = message_to_post.get(lookup_key)
        if not reply_to_post:
            info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if info:
                reply_to_post = info[0]
    content = {
        'type': 'voice',
        'file_id': message.voice.file_id
    }
    content['quote_info'] = await build_quick_quote_info(reply_to_post)

    if is_shadow_muted:
        await process_shadow_reject(
            bot=message.bot, board_id=board_id, user_id=user_id, 
            content=content, reply_to_post=reply_to_post, stream=stream
        )
    else:
        await process_new_post(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        )

@dp.message(F.video_note, ~F.media_group_id)
async def handle_video_note(message: Message, board_id: str | None, stream: str = 'ru'): 
    user_id = message.from_user.id
    if not board_id: return
    b_data = board_data[board_id]
    if user_id in b_data['users']['banned'] or (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
        try:
            await message.delete()
        except TelegramBadRequest: pass
        return
    b_data['last_activity'][user_id] = datetime.now(UTC)
    if not await check_spam(user_id, message, board_id):
        try:
            await message.delete()
            await apply_penalty(message.bot, user_id, 'animation', board_id)
        except TelegramBadRequest: pass
        return
    try:
        await message.delete()
    except TelegramBadRequest: pass

    # --- ИЗМЕНЕНИЕ: Проверка Shadow Mute + Shadow Media ---
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    # Вот эта проверка добавлена для кружков
    if user_settings.get('shadow_media'):
        is_shadow_muted = True
    # ----------------------------------------------------

    reply_to_post = None
    if message.reply_to_message:
        async with storage_lock:
            lookup_key = (message.chat.id, message.reply_to_message.message_id)
            reply_to_post = message_to_post.get(lookup_key)
        if not reply_to_post:
            info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if info:
                reply_to_post = info[0]
    content = {
        'type': 'video_note',
        'file_id': message.video_note.file_id
    }
    content['quote_info'] = await build_quick_quote_info(reply_to_post)

    if is_shadow_muted:
        await process_shadow_reject(
            bot=message.bot, board_id=board_id, user_id=user_id, 
            content=content, reply_to_post=reply_to_post, stream=stream
        )
    else:
        await process_new_post(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        )
@dp.message(F.media_group_id)
async def handle_media_group_init(message: Message, board_id: str | None, stream: str = 'ru'):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ)
    Собирает сообщения медиагруппы и НЕМЕДЛЕННО удаляет оригинал для консистентного UX.
    """
    media_group_id = message.media_group_id
    user_id = message.from_user.id
    if not board_id or not media_group_id:
        return
    media_group_key = _media_group_state_key(message.chat.id, media_group_id)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
        
    if media_group_key in sent_media_groups:
        return
    b_data = board_data[board_id]
    if user_id in b_data['users']['banned'] or \
       (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
        return
    b_data['last_activity'][user_id] = datetime.now(UTC)
    
    is_leader = False
    async with media_group_creation_lock:
        if media_group_key not in current_media_groups:
            is_leader = True
            current_media_groups[media_group_key] = {
                'is_initializing': True,
                'init_event': asyncio.Event(),
                'media_group_id': media_group_id,
                'media_group_key': media_group_key,
                'chat_id': message.chat.id,
            }
            
    group = current_media_groups.get(media_group_key)
    if not group:
        return
        
    if is_leader:
        try:
            fake_text_message = types.Message(
                message_id=message.message_id, date=message.date, chat=message.chat,
                from_user=message.from_user, content_type='text', text=f"media_group_{media_group_id}"
            )
            if not await check_spam(user_id, fake_text_message, board_id):
                current_media_groups.pop(media_group_key, None)
                await apply_penalty(message.bot, user_id, 'text', board_id)
                if 'init_event' in group:
                    group['init_event'].set()
                return
            reply_to_post = None
            if message.reply_to_message:
                async with storage_lock:
                    lookup_key = (message.chat.id, message.reply_to_message.message_id)
                    reply_to_post = message_to_post.get(lookup_key)
                if not reply_to_post:
                    info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
                    if info:
                        reply_to_post = info[0]
            raw_caption_html = getattr(message, 'caption_html_text', message.caption or "")
            safe_caption_html = sanitize_html(raw_caption_html)
            group.update({
                'board_id': board_id, 'author_id': user_id, 'stream': stream,
                'timestamp': datetime.now(UTC), 'raw_messages':[], 'caption': safe_caption_html,
                'reply_to_post': reply_to_post, 'processed_messages': set(),
                'source_message_ids': set()
            })
            group.pop('is_initializing', None)
        finally:
            if 'init_event' in group:
                group['init_event'].set()
    else:
        if 'init_event' in group:
            try:
                await asyncio.wait_for(group['init_event'].wait(), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"⚠️ Таймаут ожидания инициализации для media_group {media_group_key}")
                return
        group = current_media_groups.get(media_group_key)
        if not group or group.get('is_initializing'):
            return
            
    group.get('source_message_ids', set()).add(message.message_id)
    if message.message_id not in group.get('processed_messages', set()):
        group.get('raw_messages',[]).append(message)
        group.get('processed_messages', set()).add(message.message_id)
        
    if media_group_key in media_group_timers:
        media_group_timers[media_group_key].cancel()
    media_group_timers[media_group_key] = asyncio.create_task(
        complete_media_group_after_delay(media_group_key, message.bot, delay=1.5)
    )
async def complete_media_group_after_delay(media_group_key: str, bot_instance: Bot, delay: float = 1.5):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ)
    Обеспечивает сбор альбома и защиту от краша при очистке очереди.
    """
    try:
        await asyncio.sleep(delay)
        group = current_media_groups.pop(media_group_key, None)
        if not group or media_group_key in sent_media_groups:
            return
        media_group_timers.pop(media_group_key, None)
        raw_messages = group.get('raw_messages', [])
        if not raw_messages:
            return
        raw_messages.sort(key=lambda m: m.message_id)
        found_caption = ""
        for msg in raw_messages:
            if msg.caption:
                raw_caption_html = getattr(msg, 'caption_html_text', msg.caption)
                found_caption = sanitize_html(raw_caption_html)
                break
        group['caption'] = found_caption
        final_media_list = []
        for msg in raw_messages:
            media_data = {'type': msg.content_type, 'file_id': None}
            media_obj = None
            if msg.photo:
                media_obj = msg.photo[-1]
                media_data['file_id'] = media_obj.file_id
            elif msg.video:
                media_obj = msg.video
                media_data['file_id'] = media_obj.file_id
            elif msg.document:
                media_obj = msg.document
                media_data['file_id'] = media_obj.file_id
            elif msg.audio:
                media_obj = msg.audio
                media_data['file_id'] = media_obj.file_id
            if media_obj:
                file_name = getattr(media_obj, 'file_name', None)
                mime_type = getattr(media_obj, 'mime_type', None)
                if file_name:
                    media_data['filename'] = file_name
                if mime_type:
                    media_data['mime_type'] = mime_type
            if media_data['file_id']:
                final_media_list.append(media_data)
        group['media'] = final_media_list
        await process_complete_media_group(media_group_key, group, bot_instance)
        current_media_groups.pop(media_group_key, None)
        media_group_timers.pop(media_group_key, None)
        # --- ИЗМЕНЕНИЕ: Удалена опасная строка sent_media_groups.remove ---
        # Объекты в sent_media_groups (deque с maxlen) удаляются сами при переполнении.
        # Попытка удалить их вручную вызывала ValueError, если ID уже вытеснен.
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Ошибка в complete_media_group_after_delay для {media_group_key}: {e}")
        current_media_groups.pop(media_group_key, None)
        media_group_timers.pop(media_group_key, None)
async def process_complete_media_group(media_group_key: str, group: dict, bot_instance: Bot):
    if not group or not group.get('media'):
        return
    sent_media_groups.append(media_group_key)
    user_id = group['author_id']
    board_id = group['board_id']
    stream = group.get('stream', 'ru')
    b_data = board_data[board_id]
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if user_settings.get('shadow_media'):
        is_shadow_muted = True
    all_media = group.get('media',[])
    CHUNK_SIZE = 10
    CAPTION_LENGTH_LIMIT = 900
    media_chunks = [all_media[i:i + CHUNK_SIZE] for i in range(0, len(all_media), CHUNK_SIZE)]
    is_large_group = len(media_chunks) > 1
    original_caption = group.get('caption')
    is_long_caption = original_caption and len(original_caption) > CAPTION_LENGTH_LIMIT
    send_caption_separately = is_large_group or is_long_caption
    first_post_num = None
    
    for i, chunk in enumerate(media_chunks):
        if not chunk: continue
        reply_to_post = group.get('reply_to_post') if i == 0 else None
        caption_for_chunk = original_caption if not send_caption_separately else None
        content = {
            'type': 'media_group',
            'media': chunk,
            'caption': caption_for_chunk
        }
        
        # --- НАЧАЛО ИЗМЕНЕНИЙ (Добавлена Быстрая цитата для альбомов) ---
        quote_info = await build_quick_quote_info(reply_to_post)
        if quote_info:
            content['quote_info'] = quote_info
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---
        
        if is_shadow_muted:
            await process_shadow_reject(
                bot=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=content,
                reply_to_post=reply_to_post,
                stream=stream
            )
            if is_large_group: await asyncio.sleep(1)
            continue
        post_num = await process_new_post(
            bot_instance=bot_instance,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        )
        if i == 0:
            first_post_num = post_num
        if is_large_group:
            await asyncio.sleep(1)
            
    if send_caption_separately and original_caption:
        text_content = {'type': 'text', 'text': original_caption}
        if is_shadow_muted:
            await process_shadow_reject(
                bot=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=text_content,
                reply_to_post=None,
                stream=stream
            )
        elif first_post_num:
            await process_new_post(
                bot_instance=bot_instance,
                board_id=board_id,
                user_id=user_id,
                content=text_content,
                reply_to_post=first_post_num,
                is_shadow_muted=False, stream=stream
            )
def apply_greentext_formatting(text: str) -> str:
    """
    Применяет форматирование 'Greentext'.
    Работает с уже экранированным HTML-текстом (где > может быть &gt;).
    """
    if not text:
        return text
    processed_lines = []
    lines = text.split('\n')
    for line in lines:
        stripped_line = line.lstrip()
        if stripped_line.startswith('>') or stripped_line.startswith('&gt;'):
            processed_lines.append(f"<code>{line}</code>")
        else:
            processed_lines.append(line)
    return '\n'.join(processed_lines)
@dp.message_reaction()
async def handle_message_reaction(reaction: types.MessageReactionUpdated, board_id: str | None, bot_instance: Optional[Bot] = None):
    """
    Обрабатывает реакции: уведомления автору и репост в канал "Лучшее".
    Исправлено: теперь ищет пост в БД, если он выгружен из RAM.
    """
    try:
        user_id = reaction.user.id
        now = time.time()
        if now - reaction_ratelimit[user_id] < 0.5:
            return
        reaction_ratelimit[user_id] = now
        chat_id = reaction.chat.id
        message_id = reaction.message_id
        if not board_id: return
        b_data = board_data[board_id]
        
        is_shadow_muted = (user_id in b_data.get('shadow_mutes', {}) and 
                           b_data['shadow_mutes'][user_id] > datetime.now(UTC))
        if is_shadow_muted or user_id in b_data.get('reaction_banned_users', set()):
            return
        post_num = None
        async with storage_lock:
            post_num = message_to_post.get((chat_id, message_id))
        if not post_num:
            db_info = await get_post_info_by_copy(chat_id, message_id)
            if db_info:
                post_num, _ = db_info
                db_post = await get_post_by_num(post_num)
                if db_post:
                    async with storage_lock:
                        messages_storage[post_num] = {
                            'author_id': db_post['author_id'],
                            'timestamp': datetime.fromtimestamp(db_post['timestamp'], UTC) if isinstance(db_post['timestamp'], (int, float)) else db_post['timestamp'],
                            'content': db_post['content'],
                            'board_id': db_post['board_id'],
                            'thread_id': db_post.get('thread_id')
                        }
                        message_to_post[(chat_id, message_id)] = post_num

        if not post_num:
            return

        author_message_id_for_reply = None
        current_positive_count = 0
        is_already_best = False
        
        async with storage_lock:
            post_data = messages_storage.get(post_num)
            if not post_data:
                return
            
            author_id = post_data.get('author_id')
            if author_id:
                raw_reply = post_to_messages.get(post_num, {}).get(author_id)
                author_message_id_for_reply = raw_reply[0] if isinstance(raw_reply, list) else raw_reply
            
            if 'reactions' not in post_data or 'users' not in post_data.get('reactions', {}):
                post_data['reactions'] = {'users': {}}
            
            reactions_storage = post_data['reactions']['users']
            old_emojis = set(reactions_storage.get(user_id, []))
            new_emojis =[r.emoji for r in reaction.new_reaction if r.type == 'emoji']
            
            if not new_emojis:
                if user_id in reactions_storage: del reactions_storage[user_id]
            else:
                reactions_storage[user_id] = new_emojis[:2]
            
            # Синхронизируем реакции в content для сохранения в БД
            if 'content' in post_data:
                post_data['content']['reactions'] = post_data['reactions']
            
            for u_emojis in reactions_storage.values():
                for em in u_emojis:
                    if em in POSITIVE_REACTIONS or em in LAUGHING_REACTIONS:
                        current_positive_count += 1
            
            is_already_best = post_data.get('forwarded_to_best', False)
            content_to_save = post_data.get('content', {}).copy()

        # Сохраняем обновленный контент с реакциями в БД (вне lock для производительности)
        if content_to_save:
            await update_post_content(post_num, content_to_save)
            if current_positive_count >= LIKES_THRESHOLD and not is_already_best:
                post_data['forwarded_to_best'] = True
        if current_positive_count >= LIKES_THRESHOLD and not is_already_best:
            final_bot = bot_instance if bot_instance else reaction.bot
            if final_bot:
                try:
                    board_name = BOARD_CONFIG[board_id]['name']
                    caption = f"🔥 <b>Годнота с {board_name}</b> (Пост #{post_num})\n\n👉 <a href=\"https://t.me/{final_bot.token.split(':')[0]}\">Зайти в бота</a>"
                    await final_bot.copy_message(
                        chat_id=BEST_CHANNEL_ID,
                        from_chat_id=chat_id,
                        message_id=message_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    print(f"🌟 Пост #{post_num} отправлен в канал 'Лучшее' ({current_positive_count} лайков).")
                except Exception as e:
                    print(f"⚠️ Не удалось репостнуть в канал 'Лучшее': {e}")
        if author_id == user_id or author_id == 0: return
        REACTION_LIMIT_PER_MINUTE = 5
        REACTION_WINDOW_SECONDS = 60
        should_trigger_edit = True
        rate_tracker = b_data['reaction_rate_tracker'][user_id]
        now = time.time()
        while rate_tracker and now - rate_tracker[0] > REACTION_WINDOW_SECONDS:
            rate_tracker.popleft()
        if len(rate_tracker) >= REACTION_LIMIT_PER_MINUTE:
            should_trigger_edit = False
            if post_num not in b_data['reaction_queue'][user_id]:
                b_data['reaction_queue'][user_id].append(post_num)
        else:
            rate_tracker.append(now)
        # === ENTERPRISE ЛОГИКА НАЧИСЛЕНИЯ (SQLITE ATOMIC + EXPLORE PROTECTION) ===
        if author_id and author_id != user_id and author_id != 0:
            # Проверяем, добавляется ли реакция (а не убирается)
            if len(reaction.new_reaction) > len(reaction.old_reaction):
                
                async with storage_lock:
                    post_data = messages_storage.get(post_num)
                    if not post_data:
                        return # Пост слишком старый или выгружен из памяти
                    
                    # Инициализируем список оплаченных реакторов для этого поста
                    if 'paid_reactors' not in post_data:
                        post_data['paid_reactors'] = set()
                    
                    # ЗАЩИТА ОТ АБУЗА: Если этот юзер уже "платил" за этот пост, выходим
                    if user_id in post_data['paid_reactors']:
                        return
                    
                    # Фиксируем оплату
                    post_data['paid_reactors'].add(user_id)

                from common.db_pool import get_pool, db_lock
                
                async with db_lock:
                    db = await get_pool()
                    
                    # Сумма вознаграждения за одну реакцию
                    reward_per_reaction = random.randint(3, 9)
                    
                    # 1. Начисляем деньги (UPSERT)
                    await db.execute(
                        """
                        INSERT INTO Users (user_id, board_id, balance, reaction_reward_counter) 
                        VALUES (?, ?, ?, 1) 
                        ON CONFLICT(user_id, board_id) DO UPDATE SET 
                        balance = balance + ?, 
                        reaction_reward_counter = reaction_reward_counter + 1
                        """,
                        (author_id, board_id, reward_per_reaction, reward_per_reaction)
                    )
                    
                    # 2. Проверяем счетчик для отправки уведомления (каждые 6 реакций)
                    async with db.execute(
                        "SELECT reaction_reward_counter FROM Users WHERE user_id = ? AND board_id = ?",
                        (author_id, board_id)
                    ) as c:
                        row = await c.fetchone()
                    
                    # --- НАЧАЛО ИЗМЕНЕНИЙ (Изменение порога уведомлений) ---
                    if row and row[0] >= 6:
                        # Сбрасываем счетчик уведомлений
                        await db.execute(
                            "UPDATE Users SET reaction_reward_counter = 0 WHERE user_id = ? AND board_id = ?", 
                            (author_id, board_id)
                        )
                    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
                        
                        # Получаем итоговый ГЛОБАЛЬНЫЙ баланс для солидности текста
                        async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (author_id,)) as c_sum:
                            sum_row = await c_sum.fetchone()
                            global_balance = sum_row[0] if sum_row and sum_row[0] else 0
                        
                        # 3. Отправляем уведомление (шанс 50%, чтобы не спамить слишком часто)
                        if random.random() < 0.5:
                            # В тексте пишем сумму чуть больше, как будто за "пакет реакций"
                            display_reward = random.randint(15, 28)
                            notif_tpl = random.choice(EARNING_NOTIFICATIONS)
                            notif_text = notif_tpl.format(amount=display_reward, balance=int(global_balance))
                            
                            try:
                                # Используем bot_instance, переданный в функцию
                                final_bot = bot_instance if bot_instance else reaction.bot
                                await final_bot.send_message(
                                    author_id, 
                                    notif_text, 
                                    parse_mode="HTML", 
                                    disable_notification=True
                                )
                            except Exception:
                                pass # Юзер мог заблочить бота
        if should_trigger_edit:
            author_id_for_notify = None
            text_for_notify = None
            newly_added = set(new_emojis) - old_emojis
            if newly_added and author_id:
                async with author_reaction_notify_lock:
                    now_n = time.time()
                    a_timestamps = author_reaction_notify_tracker[author_id]
                    while a_timestamps and a_timestamps[0] <= now_n - 60: a_timestamps.popleft()
                    if len(a_timestamps) < AUTHOR_NOTIFY_LIMIT_PER_MINUTE:
                        a_timestamps.append(now_n)
                        author_id_for_notify = author_id
                        lang = 'en' if board_id == 'int' else 'ru'
                        emoji = list(newly_added)[0]
                        category = 'neutral'
                        if emoji in POSITIVE_REACTIONS: category = 'positive'
                        elif emoji in LAUGHING_REACTIONS: category = 'laughing'
                        elif emoji in NEGATIVE_REACTIONS: category = 'negative'
                        elif emoji in CLOWN_REACTION: category = 'clown'
                        elif emoji in THINKING_REACTIONS: category = 'thinking'
                        elif emoji in SHOCK_REACTIONS: category = 'shock'
                        elif emoji in SAD_REACTIONS: category = 'sad'
                        elif emoji in POLITICAL_REACTIONS: category = 'political'
                        elif emoji in SYMBOLIC_REACTIONS: category = 'symbolic'
                        elif emoji in INSULT_REACTIONS: category = 'insult'
                        phrase_template = random.choice(REACTION_NOTIFY_PHRASES[lang][category])
                        text_for_notify = phrase_template.format(post_num=post_num)
            final_bot_instance = bot_instance if bot_instance else reaction.bot
            if not final_bot_instance: return
            async with pending_edit_lock:
                if post_num in pending_edit_tasks: pending_edit_tasks[post_num].cancel()
                new_task = asyncio.create_task(execute_delayed_edit(post_num, final_bot_instance, author_id_for_notify, text_for_notify, reply_to_message_id=author_message_id_for_reply))
                pending_edit_tasks[post_num] = new_task
    except Exception as e:
        print(f"❌ Ошибка в handle_message_reaction: {e}")
@dp.message(F.poll)
async def handle_poll(message: types.Message, board_id: str | None, stream: str = 'ru'):

    if not board_id:
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        text = (
            "<b>Polls are not supported.</b>\n\n"
            "Technically, it's impossible to send the same poll instance to all users. "
            "Every anon would receive a unique copy, which breaks the chat's mechanics."
        )
    elif lang == 'jp':
        text = (
            "<b>ネイティブ投票はサポートされていません。</b>\n\n"
            "技術的な理由により、すべてのユーザーに同じ投票インスタンスを送ることができません。"
            "各アノンが独自のコピーを受け取ることになり、チャットの仕組みが壊れてしまいます。"
            "<code>/poll</code> コマンドを使用してください。"
        )
    else:
        text = (
            "<b>Опросы не поддерживаются.</b>\n\n"
            "Технически невозможно разослать один и тот же опрос всем пользователям. "
            "Каждый анон получил бы свою уникальную копию, что ломает механику чата."
        )
    try:
        await message.answer(text, parse_mode="HTML")
    except (TelegramForbiddenError, TelegramBadRequest):
        pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

@dp.message(~F.media_group_id)
async def handle_message(message: Message, board_id: str | None, stream: str = 'ru'):
    user_id = message.from_user.id
    if not board_id: return
    if board_id in THREAD_BOARDS:
        if await ensure_user_in_valid_thread(message.bot, board_id, user_id):
            try: await message.delete()
            except TelegramBadRequest: pass
            return
    b_data = board_data[board_id]
    if message.content_type in ['photo', 'video', 'document']:
        counter = b_data['single_photo_counter'][user_id]
        if not message.media_group_id:
            b_data['single_photo_counter'][user_id] += 1
            current_count = b_data['single_photo_counter'][user_id]
            if current_count > 5:
                b_data['single_photo_counter'][user_id] = 0
                lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                phrases = ALBUM_EDUCATION_PHRASES.get(lang, ALBUM_EDUCATION_PHRASES['ru'])
                edu_text = random.choice(phrases)
                try:
                    sent = await message.answer(edu_text)
                    asyncio.create_task(delete_message_after_delay(sent, 20))
                except: pass
        else:
            b_data['single_photo_counter'][user_id] = 0
    elif message.content_type == 'text':
        b_data['single_photo_counter'][user_id] = 0
    try:
        if message.content_type == 'dice':
            try:
                await message.delete()
            except Exception:
                pass
            last_insult_time = b_data.get('last_roll_time', {}).get(user_id, 0)
            now = time.time()
            if now - last_insult_time > 5:
                lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                if lang == 'en':
                    phrases = CASINO_FUCK_OFF_PHRASES_EN
                elif lang == 'jp':
                    phrases = CASINO_FUCK_OFF_PHRASES_JP
                else:
                    phrases = CASINO_FUCK_OFF_PHRASES
                fuck_off_text = random.choice(phrases)
                try:
                    sent_msg = await message.answer(fuck_off_text)
                    asyncio.create_task(delete_message_after_delay(sent_msg, 7))
                    b_data.setdefault('last_roll_time', {})[user_id] = now
                except Exception: 
                    pass
            return
        supported_types = ['text', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note'] 
        if message.content_type not in supported_types:
            await message.delete()
            return
        if message.content_type == 'text' and not (message.text and message.text.strip()):
            await message.delete()
            return
        if user_id in b_data['users']['banned']:
            try:
                await message.delete()
            except TelegramBadRequest: pass
            return
        mute_until = b_data['mutes'].get(user_id)
        if mute_until and mute_until > datetime.now(UTC):
            try:
                await message.delete()
            except TelegramBadRequest: pass
            return
        elif mute_until:
            b_data['mutes'].pop(user_id, None)
        b_data['last_activity'][user_id] = datetime.now(UTC)
        if user_id not in b_data['users']['active']:
            b_data['users']['active'].add(user_id)
            b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
            await add_or_activate_user(user_id, board_id)
            print(f"✅ [{board_id}] Добавлен новый пользователь: ID {user_id}")
        if board_id != 'trash' and not await check_spam(user_id, message, board_id):
            try:
                await message.delete()
            except TelegramBadRequest: pass
            msg_type = message.content_type
            if msg_type in ['photo', 'video', 'document'] and message.caption:
                msg_type = 'text'
            await apply_penalty(message.bot, user_id, msg_type, board_id)
            return
        is_sage = False 
        html_text_content = message.html_text or getattr(message, 'caption_html_text', None) or ""
        plain_text_check = (message.text or message.caption or "").lower().strip()
        if plain_text_check.startswith("sage") or plain_text_check.startswith("сажа"):
            is_sage = True
        def replacer(match):
            plain_text_quote = clean_html_tags(match.group(0))
            return f"↪️ <code>{escape_html(plain_text_quote)}</code>"
        processed_html_text = RE_REPLY_QUOTE_FORMAT.sub(replacer, html_text_content)
    except (TelegramBadRequest, TelegramForbiddenError): return
    except Exception as e:
        print(f"Error in handle_message: {e}")
        return
    # Собираем текст для поиска мульти-ответов из текста или подписи к медиа
    input_text = message.text or message.caption or ""
    multi_reply_blocks, limit_hit = _parse_and_split_multi_replies(input_text)
    
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
                       
    if multi_reply_blocks:
        try: await message.delete()
        except TelegramBadRequest: pass
        
        # Предварительно извлекаем данные о медиа, если они есть
        media_type = message.content_type if message.content_type != 'text' else None
        media_file_id = None
        media_meta = {}
        if media_type:
            file_obj = getattr(message, media_type)
            if isinstance(file_obj, list):
                file_obj = file_obj[-1]
            media_file_id = file_obj.file_id
            file_name = getattr(file_obj, 'file_name', None)
            mime_type = getattr(file_obj, 'mime_type', None)
            if file_name:
                media_meta['filename'] = file_name
            if mime_type:
                media_meta['mime_type'] = mime_type

        for i, (post_num_to_reply, text_chunk) in enumerate(multi_reply_blocks):
            # Проверяем существование поста (сначала в RAM, потом в БД)
            post_exists = post_num_to_reply in messages_storage
            if not post_exists:
                if await get_post_by_num(post_num_to_reply):
                    post_exists = True
            
            if not post_exists:
                continue
            
            formatted_chunk = RE_REPLY_QUOTE_FORMAT.sub(replacer, escape_html(text_chunk))
            
            # Прикрепляем медиа к первому посту в цепочке ответов, остальные — текст
            if i == 0 and media_type:
                content = {'type': media_type, 'file_id': media_file_id, 'caption': formatted_chunk}
                content.update(media_meta)
            else:
                content = {'type': 'text', 'text': formatted_chunk}
            quote_info = await build_quick_quote_info(post_num_to_reply)
            if quote_info:
                content['quote_info'] = quote_info
                
            if is_sage: content['is_sage'] = True
            
            if not is_shadow_muted and text_chunk:
                if _is_spam_filtered(text_chunk, board_id, user_id):
                    is_shadow_muted = True 
                else:
                    asyncio.create_task(check_and_send_contextual_reply(message.bot, user_id, text_chunk, board_id, stream=stream))
            
            if is_shadow_muted:
                await process_shadow_reject(
                    bot=message.bot,
                    board_id=board_id,
                    user_id=user_id,
                    content=content,
                    reply_to_post=post_num_to_reply,
                    stream=stream
                )
            else:
                await process_new_post(
                    bot_instance=message.bot,
                    board_id=board_id,
                    user_id=user_id,
                    content=content,
                    reply_to_post=post_num_to_reply,
                    is_shadow_muted=False,
                    stream=stream
                )
            await asyncio.sleep(0.33)
            
        if limit_hit:
            try: await message.bot.send_message(user_id, "Replies limit reached (3 max).", disable_notification=True)
            except: pass
        return
    try: await message.delete()
    except TelegramBadRequest: pass
    reply_to_post = None
    if message.reply_to_message:
        async with storage_lock:
            lookup_key = (message.chat.id, message.reply_to_message.message_id)
            reply_to_post = message_to_post.get(lookup_key)
        if not reply_to_post:
            info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if info:
                reply_to_post = info[0]
        if not reply_to_post:
            replied_msg = message.reply_to_message
            text_to_scan = replied_msg.text or replied_msg.caption or ""
            match = re.search(r"(?:№|#|Post No\.|Пост №|レス番)\s*(\d+)", text_to_scan, re.IGNORECASE)
            if match:
                potential_id = int(match.group(1))
                if await get_post_by_num(potential_id):
                    reply_to_post = potential_id
                    async with storage_lock:
                        message_to_post[lookup_key] = reply_to_post
                    print(f"👀 ID #{reply_to_post} восстановлен через чтение текста сообщения!")
    content = {'type': message.content_type}
    text_for_corpus = None
    if message.content_type == 'text':
        text_for_corpus = message.text
        safe_html_text = sanitize_html(processed_html_text)
        content.update({'text': safe_html_text})
    elif message.content_type in ['photo', 'video', 'animation', 'document', 'audio', 'voice']:
        text_for_corpus = message.caption
        file_id_obj = getattr(message, message.content_type, [])
        if isinstance(file_id_obj, list): file_id_obj = file_id_obj[-1]
        safe_caption_html = sanitize_html(processed_html_text)
        content.update({'file_id': file_id_obj.file_id, 'caption': safe_caption_html})
        file_name = getattr(file_id_obj, 'file_name', None)
        mime_type = getattr(file_id_obj, 'mime_type', None)
        if file_name:
            content['filename'] = file_name
        if mime_type:
            content['mime_type'] = mime_type
    elif message.content_type in ['sticker', 'video_note']:
        file_id_obj = getattr(message, message.content_type)
        content.update({'file_id': file_id_obj.file_id})
        if message.content_type == 'sticker' and message.sticker.emoji:
             text_for_corpus = message.sticker.emoji
    if text_for_corpus:
        async with storage_lock: last_messages.append(text_for_corpus)
        if board_id != 'trash':
            asyncio.create_task(check_and_send_contextual_reply(message.bot, user_id, text_for_corpus, board_id, stream=stream))
    if not is_shadow_muted and text_for_corpus:
        if _is_spam_filtered(text_for_corpus, board_id, user_id):
            is_shadow_muted = True
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if (message.content_type == 'animation' and user_settings.get('shadow_gif')) or \
       (message.content_type == 'sticker' and user_settings.get('shadow_sticker')):
        is_shadow_muted = True
    if user_settings.get('shadow_media') and message.content_type != 'text':
        is_shadow_muted = True
    if is_sage: content['is_sage'] = True

    # --- НАЧАЛО ИЗМЕНЕНИЙ (Логика "Быстрой цитаты") ---
    quote_info_for_post = await build_quick_quote_info(reply_to_post)
    content['quote_info'] = quote_info_for_post
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
    
    if is_shadow_muted:
        await process_shadow_reject(
            bot=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            stream=stream
        )
    else:
        await process_new_post(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        )
async def database_cleanup_task():
    """
    Периодически очищает таблицы-очереди от старых записей (Broadcast и Notifications).
    """
    await asyncio.sleep(3600) # Первая очистка через час после старта
    while True:
        try:
            print("🧹 [Maintenance] Запуск плановой очистки очередей в БД...")
            from common.database import cleanup_broadcast_queue
            await cleanup_broadcast_queue(retention_hours=48)
            from common.database import cleanup_notification_queue
            await cleanup_notification_queue(retention_hours=24)
            print("✅ [Maintenance] База данных оптимизирована.")
            await asyncio.sleep(43200) 
        except asyncio.CancelledError:
            print("ℹ️ Задача очистки БД остановлена.")
            break
        except Exception as e:
            print(f"⛔ ОШИБКА в database_cleanup_task: {e}")
            await asyncio.sleep(600) # В случае ошибки повторить через 10 минут
async def thread_notifier():
    """
    Фоновая задача для уведомления пользователей в общем чате об активности в тредах.
    """
    global last_checked_post_counter_for_notify
    await asyncio.sleep(45)
    last_checked_post_counter_for_notify = state.get('post_counter', 0)
    while True:
        await asyncio.sleep(300) # Проверка каждые 5 минут
        now_dt = datetime.now(UTC) # Определяем время один раз
        current_post_counter = state.get('post_counter', 0)
        if current_post_counter > last_checked_post_counter_for_notify:
            new_thread_posts_count = defaultdict(lambda: defaultdict(int))
            async with storage_lock: # Безопасно читаем данные
                posts_slice = {k: v for k, v in messages_storage.items() if k > last_checked_post_counter_for_notify}
            for p_num, post_data in posts_slice.items():
                b_id = post_data.get('board_id')
                if b_id in THREAD_BOARDS:
                    t_id = post_data.get('thread_id')
                    if t_id: new_thread_posts_count[b_id][t_id] += 1
            last_checked_post_counter_for_notify = current_post_counter
            for board_id, threads in new_thread_posts_count.items():
                b_data = board_data[board_id]
                threads_data = b_data.get('threads_data', {})
                users_on_main = {
                    uid for uid, u_state in b_data.get('user_state', {}).items() 
                    if u_state.get('location', 'main') == 'main'
                }
                for thread_id, count in threads.items():
                    if count >= THREAD_NOTIFY_THRESHOLD:
                        thread_info = threads_data.get(thread_id)
                        if not thread_info or thread_info.get('is_archived'): continue
                        thread_stream = thread_info.get('stream', 'ru')
                        if ENABLE_MULTILANG and board_id != 'int':
                            stream_users = await get_stream_active_users(board_id, thread_stream)
                            recipients = users_on_main.intersection(stream_users)
                        else:
                            recipients = users_on_main
                        if not recipients: continue
                        lang = thread_stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                        title = thread_info.get('title', '...')
                        phrases = thread_messages.get(lang, {}).get('thread_activity_notification', ["High activity."])
                        notification_text = random.choice(phrases).format(title=title, count=count)
                        bot_username = BOARD_CONFIG[board_id]['username'].lstrip('@')
                        deeplink_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"
                        button_text = "Зайти в тред" if lang == 'ru' else "Enter Thread"
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=button_text, url=deeplink_url)]
                        ])
                        content = {'type': 'text', 'text': notification_text, 'is_system_message': True}
                        pnum = await create_post(
                            board_id=board_id, author_id=0, content=content,
                            timestamp=now_dt.timestamp(), is_from_site=False, stream='ru'
                        )
                        if not pnum:
                            print(f"⛔ [{board_id}] Не удалось создать пост в БД для уведомления об активности треда {thread_id}.")
                            continue
                        header = await format_header(board_id, pnum)
                        content['header'] = header
                        await update_post_content(pnum, content)
                        async with storage_lock:
                            messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
                        await enqueue_board_message(board_id, {
                            'recipients': recipients, 'content': content, 'post_num': pnum, 'board_id': board_id, 'keyboard': keyboard
                        })
        for board_id in THREAD_BOARDS:
            b_data = board_data[board_id]
            lang = 'en' if board_id == 'int' else 'ru'
            threads_data = b_data.get('threads_data', {})
            recipients_in_main = {
                uid for uid, u_state in b_data.get('user_state', {}).items() 
                if u_state.get('location', 'main') == 'main'
            }
            if not recipients_in_main: continue
            for thread_id, thread_info in threads_data.items():
                if thread_info.get('is_archived') or thread_info.get('bump_limit_notified'):
                    continue
                current_posts = len(thread_info.get('posts', []))
                remaining = MAX_POSTS_PER_THREAD - current_posts
                if 0 < remaining <= THREAD_BUMP_LIMIT_WARNING_THRESHOLD:
                    thread_info['bump_limit_notified'] = True
                    title = thread_info.get('title', '...')
                    notification_text = random.choice(thread_messages[lang]['thread_reaching_bump_limit']).format(title=title, remaining=remaining)
                    bot_username = BOARD_CONFIG[board_id]['username'].lstrip('@')
                    deeplink_url = f"https://t.me/{bot_username}?start=thread_{thread_id}"
                    button_text = "Зайти в тред" if lang == 'ru' else "Enter Thread"
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=button_text, url=deeplink_url)]
                    ])
                    content = {'type': 'text', 'text': notification_text, 'is_system_message': True}
                    pnum = await create_post(
                        board_id=board_id, author_id=0, content=content,
                        timestamp=now_dt.timestamp(), is_from_site=False
                    )
                    if not pnum:
                        print(f"⛔ [{board_id}] Не удалось создать пост в БД для уведомления о бамп-лимите треда {thread_id}.")
                        continue
                    header = await format_header(board_id, pnum)
                    content['header'] = header
                    await update_post_content(pnum, content)
                    async with storage_lock:
                        messages_storage[pnum] = {'author_id': 0, 'timestamp': now_dt, 'content': content, 'board_id': board_id}
                    await enqueue_board_message(board_id, {
                        'recipients': recipients_in_main, 'content': content, 'post_num': pnum, 'board_id': board_id, 'keyboard': keyboard
                    })
async def mode_auto_disabler():
    """
    Фоновая задача для надежного отключения режимов по таймеру.
    Проверяет время активации и отключает режим, если прошло > 5 минут.
    Работает даже после перезагрузки бота (если время активации было сохранено, но в текущей версии оно в RAM).
    В текущей реализации время в RAM, но это страховка от потери Task.
    """
    MODE_DURATION = 320 # 5 минут
    while True:
        await asyncio.sleep(30) # Проверяем каждые 30 секунд
        try:
            now = datetime.now(UTC)
            all_modes = MODE_FLAGS
            for board_id in BOARDS:
                async with storage_lock:
                    b_data = board_data[board_id]
                    last_activation = b_data.get('last_mode_activation')
                    if not last_activation:
                        continue
                    if (now - last_activation).total_seconds() > (MODE_DURATION + 10):
                        active_modes = [m for m in all_modes if b_data.get(m)]
                        if active_modes:
                            print(f"⏰ [Auto-Disabler] Отключаю режимы на {board_id} (таймер истек): {active_modes}")
                            for mode in all_modes:
                                b_data[mode] = False
                            b_data['last_mode_activation'] = None
                            b_data['active_mode_task'] = None # Сбрасываем таск
                            asyncio.create_task(disable_mode_after_delay(0, board_id, active_modes[0]))
        except Exception as e:
            print(f"❌ Ошибка в mode_auto_disabler: {e}")
async def _run_background_task(task_factory: Callable[[], Awaitable[Any]], task_name: str):
    """
    Надежная обертка для фоновых задач, обеспечивающая логирование ошибок и перезапуск.
    Принимает "фабрику" (функцию), чтобы пересоздавать корутину при перезапуске.
    """
    INITIAL_RESTART_DELAY = 60
    MAX_RESTART_DELAY = 600
    current_delay = INITIAL_RESTART_DELAY
    while True:
        try:
            task_coro = task_factory()
            await task_coro
            if is_shutting_down or drain_shutdown_requested:
                print(f"ℹ️ Фоновая задача '{task_name}' завершилась при остановке.")
                break
            print(f"⚠️ Фоновая задача '{task_name}' неожиданно завершилась. Перезапуск через {current_delay} секунд...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RESTART_DELAY)
        except asyncio.CancelledError:
            print(f"ℹ️ Фоновая задача '{task_name}' была отменена.")
            break
        except Exception as e:
            import traceback
            if is_shutting_down or drain_shutdown_requested:
                print(f"Background task '{task_name}' ended during shutdown: {e}")
                break
            print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА в фоновой задаче '{task_name}': {e}")
            runtime_logger.exception("background_task_failed task=%s", task_name)
            traceback.print_exc()
            print(f"🔁 Перезапуск задачи '{task_name}' через {current_delay} секунд...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RESTART_DELAY)
async def periodic_thread_digest():
    while True:
        await asyncio.sleep(28800) # 8 часов (8 * 3600)
        try:
            print("📊 Сборка дайджеста активных тредов...")
            from common.database import get_top_active_threads
            top_threads = await get_top_active_threads(hours=8, limit=10)
            if not top_threads:
                continue
            digest_text = "🔥 <b>ГОРЯЧИЕ ТРЕДЫ ЗА 8 ЧАСОВ</b>\n\n"
            for i, t in enumerate(top_threads, 1):
                raw_title = html.unescape(t.get('title', ''))
                clean_title = clean_html_tags(raw_title)
                safe_title = html.escape(clean_title)[:50] + ".."
                url = f"https://tgach.top/{t['board_id']}/res/{t['thread_id']}.html"
                digest_text += f"{i}. <a href='{url}'>{safe_title}</a> (💬 {t['posts_count']})\n"
            digest_text += "\n🚀 <i>Будь в центре движухи!</i>"
            target_boards = ['thread', 'b']
            for board_id in target_boards:
                if board_id not in board_data:
                    continue
                b_data = board_data[board_id]
                recipients = b_data['users']['active'] - b_data['users']['banned']
                if not recipients:
                    continue
                content = {
                    'type': 'text',
                    'text': digest_text,
                    'is_system_message': True,
                }
                pnum = await create_post(board_id=board_id, author_id=0, content=content, timestamp=time.time())
                if pnum:
                    header_base = await format_header(board_id, pnum)
                    content['header'] = f"### DIGEST ###\n{header_base}"
                    await update_post_content(pnum, content)
                    async with storage_lock:
                        messages_storage[pnum] = {
                            'author_id': 0, 
                            'timestamp': datetime.now(UTC), 
                            'content': content, 
                            'board_id': board_id
                        }
                    await enqueue_board_message(board_id, {
                        "recipients": recipients,
                        "content": content,
                        "post_num": pnum,
                        "board_id": board_id
                    })
        except Exception as e:
            print(f"❌ Ошибка дайджеста: {e}")
SITE_PUBLIC_BASE_URL = os.getenv("SITE_PUBLIC_BASE_URL", "https://tgach.top").rstrip("/")


def _site_public_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    url = str(raw_url).strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"{SITE_PUBLIC_BASE_URL}{url}"
    return f"{SITE_PUBLIC_BASE_URL}/{url.lstrip('/')}"


def _site_file_send_type(file_info: dict) -> str | None:
    raw_type = str(file_info.get("type") or "").split(".")[-1].lower()
    filename = str(file_info.get("filename") or "").lower()
    if raw_type in {"image", "photo", "picture"}:
        return "photo"
    if raw_type in {"video", "video_note"}:
        return "video"
    if raw_type in {"gif", "animation"}:
        return "animation"
    if raw_type in {"audio", "voice"}:
        return "audio" if raw_type == "audio" else "voice"
    if raw_type in {"document", "file"}:
        return "document"
    if raw_type == "sticker":
        return "document"
    if filename.endswith((".jpg", ".jpeg", ".png")):
        return "photo"
    if filename.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "video" if not filename.endswith(".webm") else "document"
    if filename.endswith(".gif"):
        return "animation"
    if filename.endswith((".mp3", ".wav", ".ogg", ".opus")):
        return "audio"
    return "document"


def _site_file_source(file_info: dict, prefer_url: bool = False) -> str | None:
    file_id = file_info.get("original_file_id") or file_info.get("file_id") or file_info.get("media")
    if isinstance(file_id, str) and file_id.startswith("shadowbanned"):
        file_id = None
    public_url = _site_public_url(file_info.get("original_url") or file_info.get("thumbnail_url"))
    source = public_url if prefer_url else file_id
    if not source:
        source = file_id or public_url
    return str(source) if source else None


def _site_media_item(file_info: dict) -> dict | None:
    send_type = _site_file_send_type(file_info)
    source = _site_file_source(file_info)
    if not send_type or not source:
        return None
    return {
        "type": send_type,
        "media": source,
        "file_id": source,
        "mime_type": file_info.get("mime_type"),
        "filename": file_info.get("filename"),
    }


def _attach_site_media_for_delivery(content: dict, source_content: dict | None = None) -> dict:
    files = (source_content or content).get("files")
    if not isinstance(files, list) or not files:
        return content

    media_items = [
        item for item in (_site_media_item(file_info) for file_info in files if isinstance(file_info, dict))
        if item
    ]
    if not media_items:
        return content

    delivery_content = content.copy()
    delivery_content["caption"] = delivery_content.get("caption") or delivery_content.get("text") or ""
    delivery_content["files"] = files

    album_supported = {"photo", "video", "document", "audio"}
    album_items = [item for item in media_items if item["type"] in album_supported]
    if len(album_items) > 1:
        delivery_content["type"] = "media_group"
        delivery_content["media"] = album_items[:10]
        delivery_content.pop("file_id", None)
        delivery_content.pop("image_url", None)
        return delivery_content

    first_item = media_items[0]
    delivery_content["type"] = first_item["type"]
    delivery_content["file_id"] = first_item["file_id"]
    first_file = files[0] if isinstance(files[0], dict) else {}
    public_url = _site_public_url(first_file.get("original_url") or first_file.get("thumbnail_url"))
    if public_url:
        delivery_content["image_url"] = public_url
    return delivery_content


async def site_posts_broadcaster():
    """
    Фоновая задача, которая извлекает посты, созданные на сайте, из очереди в БД
    и транслирует их в Telegram. Реализована логика уведомлений о новых тредах.
    """
    await asyncio.sleep(15)  # Начальная задержка при запуске бота
    while True:
        try:
            if drain_shutdown_requested:
                await asyncio.sleep(2)
                continue
            new_posts = await get_and_clear_broadcast_queue()
            if new_posts:
                new_posts.sort(key=lambda p: p.get('timestamp', 0))
                for post in new_posts:
                    post_num = post.get('post_num')
                    if not post_num:
                        continue
                    if post.get('_broadcast_decode_failed'):
                        await mark_broadcast_posts_sent([post_num])
                        continue
                    if post_num in messages_storage or post_num in locally_created_posts:
                        await mark_broadcast_posts_sent([post_num])
                        continue
                    board_id = post.get('board_id')
                    author_id = post.get('author_id')
                    post_stream = post.get('stream', 'ru')
                    post_mode = post.get('post_mode') 
                    thread_id = post.get('thread_id')
                    is_new_thread = (
                        post_mode == 'new_thread'
                        or bool(post.get('is_op_post'))
                        or (thread_id is not None and str(thread_id) == str(post_num))
                    )
                    if not board_id or board_id not in BOARD_CONFIG:
                        await mark_broadcast_posts_sent([post_num])
                        continue
                    b_data = board_data[board_id]
                    content = post.get('content', {})
                    skip_broadcast = False
                    async with storage_lock:
                        is_banned = author_id in b_data.get('users', {}).get('banned', set())
                        m_until = b_data.get('mutes', {}).get(author_id)
                        is_muted = m_until and m_until > datetime.now(UTC)
                        sm_until = b_data.get('shadow_mutes', {}).get(author_id)
                        is_shadow_muted = sm_until and sm_until > datetime.now(UTC)
                        if is_banned or is_muted or is_shadow_muted:
                            skip_broadcast = True
                        else:
                            state['post_counter'] = max(state.get('post_counter', 0), post_num)
                            header = await format_header(board_id, post_num, stream=post_stream)
                            source_content = content
                            if is_new_thread:
                                raw_text = source_content.get('text', '')
                                clean_text_no_tags = re.sub(r'<[^>]+>', '', raw_text)
                                decoded_text = html.unescape(clean_text_no_tags)
                                title_preview = (decoded_text[:120] + '...') if len(decoded_text) > 120 else decoded_text
                                if not title_preview.strip():
                                    title_preview = "Новый тред (медиа-контент)"
                                site_url = f"https://tgach.top/{board_id}/res/{post_num}.html"
                                if post_stream == 'en':
                                    notify_text = (
                                        f"🌱 <b>New thread on website!</b>\n\n"
                                        f"📝 {html.escape(title_preview)}\n\n"
                                        f"🔗 <a href='{site_url}'>Open on Website</a>"
                                    )
                                elif post_stream == 'jp':
                                    notify_text = (
                                        f"🌱 <b>サイトで新しいスレが作成されました！</b>\n\n"
                                        f"📝 {html.escape(title_preview)}\n\n"
                                        f"🔗 <a href='{site_url}'>サイトで開く</a>"
                                    )
                                else:
                                    notify_text = (
                                        f"🌱 <b>На сайте создан новый тред!</b>\n\n"
                                        f"📝 {html.escape(title_preview)}\n\n"
                                        f"🔗 <a href='{site_url}'>Читать на сайте</a>"
                                    )
                                content = {
                                    'type': 'text',
                                    'text': notify_text,
                                    'is_system_message': True,
                                    'header': f"### WEBSITE ###\n{header}",
                                    'post_num': post_num,
                                }
                                content = _attach_site_media_for_delivery(content, source_content)
                            else:
                                content = _attach_site_media_for_delivery(content)
                                content['header'] = header
                                content['post_num'] = post_num
                            if post.get('reply_to_post_num'):
                                content['reply_to_post'] = post['reply_to_post_num']
                            messages_storage[post_num] = {
                                'author_id': author_id,
                                'timestamp': datetime.fromtimestamp(post['timestamp'], UTC),
                                'content': content,
                                'board_id': board_id,
                                'thread_id': post.get('thread_id'),
                            }
                    if skip_broadcast:
                        await mark_broadcast_posts_sent([post_num])
                        continue
                    base_recipients = b_data['users']['active'] - b_data['users']['banned']
                    if ENABLE_MULTILANG and board_id != 'int':
                        stream_users = await get_stream_active_users(board_id, post_stream)
                        base_recipients = base_recipients.intersection(stream_users)
                    recipients = set()
                    if is_new_thread or not thread_id:
                        recipients = base_recipients
                    else:
                        thread_info = b_data.get('threads_data', {}).get(str(thread_id))
                        if thread_info:
                            subs = thread_info.get('subscribers', set())
                            recipients = subs.intersection(base_recipients)
                    if recipients:
                        await enqueue_board_message(board_id, {
                            'recipients': recipients,
                            'content': content,
                            'post_num': post_num,
                            'board_id': board_id,
                            'thread_id': thread_id if not is_new_thread else None
                        })
                        await mark_broadcast_posts_sent([post_num])
                        
                        if not content.get('is_system_message'):
                            bot_to_use = GLOBAL_BOTS.get(board_id) or GLOBAL_BOTS.get('b')
                            if bot_to_use:
                                asyncio.create_task(_forward_post_to_realtime_archive(
                                    bot_instance=bot_to_use,
                                    board_id=board_id,
                                    post_num=post_num,
                                    content=content,
                                    is_shadow_muted=is_shadow_muted
                                ))
                    else:
                        await mark_broadcast_posts_sent([post_num])
            await asyncio.sleep(5) 
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⛔ ОШИБКА в site_posts_broadcaster: {e}")
            await asyncio.sleep(10)
async def site_reaction_processor():
    """
    Фоновая задача, которая проверяет очередь реакций с сайта и эмулирует
    нажатие реакции в Telegram, запуская стандартный обработчик.
    """
    await asyncio.sleep(25)
    while True:
        try:
            reactions_to_process = await get_and_clear_reaction_queue()
            if reactions_to_process:
                print(f"⚙️ Обнаружено {len(reactions_to_process)} реакций с сайта. Обрабатываю...")
                for reaction_info in reactions_to_process:
                    user_id = reaction_info['user_id']
                    post_num = reaction_info['post_num']
                    emoji = reaction_info['emoji']
                    board_id, message_id = None, None
                    async with storage_lock:
                        post_data = messages_storage.get(post_num)
                        if not post_data: continue
                        board_id = post_data.get('board_id')
                        copies = post_to_messages.get(post_num, {})
                        user_copy = copies.get(user_id)
                        if isinstance(user_copy, list):
                            message_id = user_copy[0] if user_copy else None
                        else:
                            message_id = user_copy
                    if not board_id or not message_id:
                        continue
                    bot_for_reaction = GLOBAL_BOTS.get(board_id)
                    if not bot_for_reaction:
                        print(f"⛔ ОШИБКА: не найден бот для доски '{board_id}' при обработке реакции с сайта.")
                        continue
                    fake_reaction_update = types.MessageReactionUpdated(
                        chat=types.Chat(id=user_id, type='private'),
                        message_id=message_id,
                        user=types.User(id=user_id, is_bot=False, first_name="SiteUser"),
                        date=datetime.now(UTC),
                        old_reaction=[],
                        new_reaction=[types.ReactionTypeEmoji(type='emoji', emoji=emoji)]
                    )
                    await handle_message_reaction(fake_reaction_update, board_id=board_id, bot_instance=bot_for_reaction)
                    await asyncio.sleep(0.1)
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            print("ℹ️ Обработчик реакций с сайта остановлен.")
            break
        except Exception as e:
            print(f"⛔ ОШИБКА в site_reaction_processor: {e}")
            await asyncio.sleep(15)
async def reaction_queue_processor():
    """
    Фоновая задача для медленной обработки реакций от пользователей, превысивших лимит.
    Обрабатывает одну реакцию в 20 секунд для каждого 'оштрафованного' пользователя.
    """
    REACTION_PROCESS_INTERVAL = 20  # секунд
    while True:
        try:
            await asyncio.sleep(5) # Проверяем очереди каждые 5 секунд
            now = time.time()
            for board_id in BOARDS:
                b_data = board_data[board_id]
                if not b_data.get('reaction_queue'):
                    continue
                bot_instance = GLOBAL_BOTS.get(board_id)
                if not bot_instance:
                    continue
                for user_id in list(b_data['reaction_queue'].keys()):
                    user_queue = b_data['reaction_queue'][user_id]
                    if not user_queue:
                        del b_data['reaction_queue'][user_id]
                        b_data['last_reaction_process_time'].pop(user_id, None)
                        continue
                    last_processed_time = b_data['last_reaction_process_time'].get(user_id, 0)
                    if now - last_processed_time > REACTION_PROCESS_INTERVAL:
                        post_num_to_process = user_queue.popleft()
                        b_data['last_reaction_process_time'][user_id] = now
                        async with pending_edit_lock:
                            if post_num_to_process in pending_edit_tasks:
                                pending_edit_tasks[post_num_to_process].cancel()
                            new_task = asyncio.create_task(
                                execute_delayed_edit(
                                    post_num=post_num_to_process,
                                    bot_instance=bot_instance,
                                    author_id=None, # Не уведомляем
                                    notify_text=None,
                                    delay=1.0 # Небольшая задержка
                                )
                            )
                            pending_edit_tasks[post_num_to_process] = new_task
        except asyncio.CancelledError:
            print("ℹ️ Обработчик очереди реакций остановлен.")
            break
        except Exception as e:
            print(f"⛔ ОШИБКА в reaction_queue_processor: {e}")
            await asyncio.sleep(20) # В случае ошибки ждем дольше
async def event_loop_health_tick_task():
    global event_loop_last_tick
    last_heartbeat_write = 0.0
    while not is_shutting_down:
        now = time.time()
        event_loop_last_tick = now
        if now - last_heartbeat_write >= 2.0:
            last_heartbeat_write = now
            try:
                queue_items = [(board_id, queue.qsize()) for board_id, queue in message_queues.items()]
                payload = {
                    "ts": now,
                    "pid": os.getpid(),
                    "queues_total": sum(size for _, size in queue_items),
                    "queues_top": sorted(queue_items, key=lambda item: item[1], reverse=True)[:5],
                    "post_counter": state.get("post_counter"),
                    "is_shutting_down": is_shutting_down,
                    "drain_shutdown_requested": drain_shutdown_requested,
                }
                _write_heartbeat_payload(payload)
                event_loop_last_tick = time.time()
            except Exception:
                pass
        await asyncio.sleep(1)


def _write_heartbeat_payload(payload: dict) -> None:
    tmp_path = f"{BOT_HEARTBEAT_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as heartbeat_file:
        json.dump(payload, heartbeat_file, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, BOT_HEARTBEAT_PATH)

async def controlled_stop_watcher_task():
    global drain_shutdown_requested, drain_shutdown_requested_at
    while not is_shutting_down:
        if os.path.exists(BOT_CONTROLLED_STOP_PATH):
            if not drain_shutdown_requested:
                drain_shutdown_requested = True
                drain_shutdown_requested_at = time.time()
                print(
                    "🛑 Controlled stop requested: polling will stop, "
                    f"then RAM delivery queues will drain for up to {CONTROLLED_STOP_DRAIN_TIMEOUT_SEC:.0f}s."
                )
                runtime_logger.warning(
                    "controlled_stop_requested %s",
                    json.dumps(
                        {
                            "ts": round(drain_shutdown_requested_at, 3),
                            "pid": os.getpid(),
                            "queues_total": _delivery_queue_total(),
                            "queues_top": sorted(
                                _delivery_queue_counts().items(),
                                key=lambda item: item[1],
                                reverse=True,
                            )[:5],
                            "drain_timeout_sec": CONTROLLED_STOP_DRAIN_TIMEOUT_SEC,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            try:
                await dp.stop_polling()
            except RuntimeError as exc:
                if "Polling is not started" not in str(exc):
                    print(f"⚠️ Controlled stop could not stop polling cleanly: {exc}")
            except Exception as exc:
                print(f"⚠️ Controlled stop watcher error: {type(exc).__name__}: {exc}")
            return
        await asyncio.sleep(1)


async def wait_for_delivery_queues_to_drain(timeout_sec: float, log_interval_sec: float) -> bool:
    deadline = time.time() + timeout_sec if timeout_sec else None
    last_log_at = 0.0
    while True:
        counts = _delivery_queue_counts()
        total = sum(counts.values())
        in_flight = dict(current_deliveries)
        if total == 0 and not in_flight:
            print("✅ Controlled stop drain complete: RAM delivery queues are empty.")
            runtime_logger.warning(
                "controlled_stop_drain_complete %s",
                json.dumps(
                    {"ts": round(time.time(), 3), "pid": os.getpid()},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            return True
        now = time.time()
        if deadline is not None and now >= deadline:
            print(
                "⚠️ Controlled stop drain timed out: "
                f"queues={total}, in_flight={list(in_flight.keys())}. Shutdown continues."
            )
            runtime_logger.warning(
                "controlled_stop_drain_timeout %s",
                json.dumps(
                    {
                        "ts": round(now, 3),
                        "pid": os.getpid(),
                        "queues_total": total,
                        "queues_top": sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5],
                        "in_flight": in_flight,
                        "timeout_sec": timeout_sec,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
            )
            return False
        if now - last_log_at >= log_interval_sec:
            last_log_at = now
            print(
                "⏳ Controlled stop drain: "
                f"queues={total}, top={sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]}, "
                f"in_flight={list(in_flight.keys())}"
            )
            runtime_logger.warning(
                "controlled_stop_drain_wait %s",
                json.dumps(
                    {
                        "ts": round(now, 3),
                        "pid": os.getpid(),
                        "queues_total": total,
                        "queues_top": sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5],
                        "in_flight": in_flight,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        await asyncio.sleep(1)

def _event_loop_stall_watchdog_loop():
    last_dump_at = 0.0
    while not is_shutting_down:
        now = time.time()
        lag_sec = max(0.0, now - event_loop_last_tick)
        if (
            lag_sec >= EVENT_LOOP_DUMP_STALE_SEC
            and now - last_dump_at >= EVENT_LOOP_DUMP_COOLDOWN_SEC
        ):
            last_dump_at = now
            try:
                queue_items = [(board_id, queue.qsize()) for board_id, queue in message_queues.items()]
                payload = {
                    "ts": now,
                    "pid": os.getpid(),
                    "lag_sec": round(lag_sec, 3),
                    "queues_total": sum(size for _, size in queue_items),
                    "queues_top": sorted(queue_items, key=lambda item: item[1], reverse=True)[:5],
                    "post_counter": state.get("post_counter"),
                }
                with open(BOT_DEADLOCK_DUMP_PATH, "a", encoding="utf-8") as dump_file:
                    dump_file.write("\n=== EVENT LOOP STALL DUMP ===\n")
                    dump_file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                    faulthandler.dump_traceback(file=dump_file, all_threads=True)
                    dump_file.write("=== END EVENT LOOP STALL DUMP ===\n")
                    dump_file.flush()
                print(
                    f"🧯 [WATCHDOG] Event loop stall dump written: "
                    f"lag={lag_sec:.1f}s queues={payload['queues_total']}"
                )
            except Exception as exc:
                try:
                    print(f"⚠️ [WATCHDOG] Failed to write event-loop stall dump: {type(exc).__name__}: {exc}")
                except Exception:
                    pass
        time.sleep(5)

def start_event_loop_stall_watchdog():
    global event_loop_stall_watchdog_started
    if event_loop_stall_watchdog_started:
        return
    event_loop_stall_watchdog_started = True
    thread = threading.Thread(
        target=_event_loop_stall_watchdog_loop,
        name="event-loop-stall-watchdog",
        daemon=True,
    )
    thread.start()

async def start_background_tasks(bots: dict[str, Bot], healthcheck_site: web.TCPSite | None):

    from conan import conan_roaster
    start_event_loop_stall_watchdog()
    active_bots_list = list(bots.values())
    tasks_to_run = {
        "event_loop_health_tick": lambda: event_loop_health_tick_task(),
        "controlled_stop_watcher": lambda: controlled_stop_watcher_task(),
        "message_broadcaster": lambda: message_broadcaster(bots),
        "conan_roaster": lambda: conan_roaster(
            state, messages_storage, post_to_messages, message_to_post,
            message_queues, format_header, board_data, storage_lock
        ),
        "motivation_broadcaster": lambda: motivation_broadcaster(),
        "help_broadcaster": lambda: help_broadcaster(),
        "network_heartbeat": lambda: network_heartbeat(bots),
        "auto_memory_cleaner": lambda: auto_memory_cleaner(),
        "runtime_telemetry": lambda: runtime_telemetry_task(),
        "weekly_active_refresh": lambda: weekly_active_refresh_task(),
        "reply_coverage_refresh": lambda: reply_coverage_refresh_task(),
        "board_statistics_broadcaster": lambda: board_statistics_broadcaster(),
        "thread_lifecycle_manager": lambda: thread_lifecycle_manager(bots),
        "thread_notifier": lambda: thread_notifier(),
        "thread_activity_monitor": lambda: thread_activity_monitor(bots),
        "memory_restarter": lambda: memory_restarter(active_bots_list, healthcheck_site),
        "graph_data_collector": lambda: graph_data_collector(),
        "reply_notifier_task": lambda: reply_notifier_task(),
        "database_cleanup_task": lambda: database_cleanup_task(),
        "site_posts_broadcaster": lambda: site_posts_broadcaster(),
        "reaction_queue_processor": lambda: reaction_queue_processor(),
        "site_reaction_processor": lambda: site_reaction_processor(),
        "mode_auto_disabler": lambda: mode_auto_disabler(),
        "periodic_thread_digest": lambda: periodic_thread_digest(),
        "admin_action_sync_worker": lambda: admin_action_sync_worker(),
    }
    tasks = [
        asyncio.create_task(_run_background_task(factory, name))
        for name, factory in tasks_to_run.items()
    ]
    print(f"✓ Background tasks started: {len(tasks)}")
    return tasks
from aiogram.client.session.aiohttp import AiohttpSession
class TrustEnvAiohttpSession(AiohttpSession):
    """
    Кастомная сессия.
    - connector: для ограничения соединений.
    - smart_timeout: сложный объект таймаута для aiohttp (VPN-оптимизация).
    """
    def __init__(self, connector=None, smart_timeout=None, **kwargs):
        self._connector = connector
        self._smart_timeout = smart_timeout
        super().__init__(**kwargs)
    async def _create_session(self, **kwargs) -> aiohttp.ClientSession:
        """
        Создает клиентскую сессию aiohttp.
        Здесь мы подменяем обычный timeout на наш умный smart_timeout.
        """
        if self._smart_timeout:
            kwargs['timeout'] = self._smart_timeout
        return aiohttp.ClientSession(
            connector=self._connector,
            trust_env=True,
            **self._session_kwargs,
            **kwargs,
        )
    @property
    def closed(self) -> bool:
        """Проверяет, создана ли внутренняя сессия и закрыта ли она"""
        if self._session is None:
            return True
        return self._session.closed
async def network_heartbeat(bots: dict[str, Bot]):
    """
    Периодически проверяет связь с API Telegram.
    Если связь потеряна (3 сбоя подряд) — убивает процесс для перезапуска.
    """
    print("❤️ Запущен Heartbeat (проверка пульса сети)...")
    test_bot = next(iter(bots.values()))
    fail_count = 0
    MAX_FAILURES = 5
    await asyncio.sleep(30) # Даем время на старт
    while True:
        try:
            await test_bot.get_me(request_timeout=10)
            if fail_count > 0:
                print(f"❤️ Пульс восстановлен после {fail_count} сбоев.")
                fail_count = 0
            await asyncio.sleep(60) # Проверяем раз в минуту
        except Exception as e:
            fail_count += 1
            print(f"💔 Сбой Heartbeat #{fail_count}: {type(e).__name__}")
            if fail_count >= MAX_FAILURES:
                print("💀 СЕТЬ МЕРТВА. Ожидание восстановления (без рестарта)...")
                await asyncio.sleep(60) # Ждем минуту, сеть рано или поздно поднимется
            else:
                await asyncio.sleep(10) # При сбое пробуем чаще
async def initialize_bots() -> tuple[dict[str, Bot], AiohttpSession]:
    """
    Создает экземпляры ботов и проверяет их токены параллельно.
    Оптимизировано для работы под нагрузкой и в сложных сетевых условиях.
    """
    import aiohttp
    import socket
    import ssl
    import asyncio
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(
        limit=100,  # Немного увеличиваем лимит одновременных подключений
        ttl_dns_cache=300,
        enable_cleanup_closed=True, 
        force_close=False,  # ВЕРНУЛИ KEEP-ALIVE, ПЕРЕСТАНУТ ОТВАЛИВАТЬСЯ СОКЕТЫ
        family=socket.AF_INET,
        ssl=ssl_context
    )
    complex_timeout = aiohttp.ClientTimeout(
        total=45,
        connect=20,
        sock_connect=20,
        sock_read=30
    )
    session = TrustEnvAiohttpSession(
        timeout=45, 
        connector=connector,
        smart_timeout=complex_timeout
    )
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bots_temp = {}
    for board_id, config in BOARD_CONFIG.items():
        token = config.get("token")
        if token:
            bots_temp[board_id] = Bot(
                token=token, 
                default=default_properties, 
                session=session
            )
    if not bots_temp:
        print("❌ Ошибка: В конфиге не найдено ни одного токена!")
        return {}, session
    print(f"\n--- Проверка {len(bots_temp)} токенов (Параллельный запуск) ---")
    async def check_single_bot(bid: str, bot_instance: Bot):
        try:
            bot_info = await bot_instance.get_me(request_timeout=10)
            print(f"✅ [{bid}] OK: @{bot_info.username}")
            return bid, bot_instance
        except Exception as e:
            print(f"❌ [{bid}] ОШИБКА ТОКЕНА: {type(e).__name__} - {e}")
            return bid, None
    tasks = [check_single_bot(bid, bot) for bid, bot in bots_temp.items()]
    results = await asyncio.gather(*tasks)
    active_bots = {}
    for bid, bot_obj in results:
        if bot_obj is not None:
            active_bots[bid] = bot_obj
    print(f"--- Инициализация завершена: {len(active_bots)} из {len(bots_temp)} активны ---\n")
    return active_bots, session

async def warm_executor_pool(
    loop: asyncio.AbstractEventLoop,
    executor: ThreadPoolExecutor | None,
    workers: int,
    label: str,
) -> None:
    warm_count = max(1, int(workers))
    release = threading.Event()
    try:
        futures = [
            loop.run_in_executor(executor, release.wait, 5.0)
            for _ in range(warm_count)
        ]
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.gather(*futures)
        print(f"✓ Executor warmed: {label} workers={workers}, warm_tasks={warm_count}")
    except Exception as exc:
        release.set()
        print(f"⚠️ Executor warmup failed: {label} {type(exc).__name__}: {exc}")

def warm_native_media_stack() -> None:
    started = time.perf_counter()
    try:
        Image.init()
        probe = Image.new("RGB", (1, 1), (0, 0, 0))
        probe_buffer = io.BytesIO()
        probe.save(probe_buffer, format="PNG")
        probe_buffer.seek(0)
        with Image.open(probe_buffer) as opened:
            opened.load()
        _ = np.asarray(probe)
        _ = np.random.randint(0, 2, (1,), dtype=np.uint8)
        plugin_count = len(getattr(Image, "ID", ()))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        print(f"✓ Native media stack warmed: pillow_plugins={plugin_count} numpy_random=ok elapsed={elapsed_ms:.1f}ms")
    except Exception as exc:
        print(f"⚠️ Native media warmup failed: {type(exc).__name__}: {exc}")

def setup_lifecycle_handlers(loop: asyncio.AbstractEventLoop, bots: list[Bot], healthcheck_site: web.TCPSite | None):

    handler = lambda: asyncio.create_task(graceful_shutdown(bots, healthcheck_site))
    if sys.platform != "win32":
        if hasattr(signal, 'SIGTERM'):
            loop.add_signal_handler(signal.SIGTERM, handler)
        if hasattr(signal, 'SIGINT'):
            loop.add_signal_handler(signal.SIGINT, handler)


def _read_text_file_stripped(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read().strip()


def _write_text_file_atomic(path: str, text: str, tmp_path: str) -> None:
    with open(tmp_path, "w", encoding="utf-8") as file:
        file.write(text)
    os.replace(tmp_path, path)


async def main():

    lock_file = "bot.lock"
    current_pid = os.getpid()
    if os.path.exists(lock_file):
        old_pid = None
        try:
            for _ in range(3):
                try:
                    lock_text = await asyncio.to_thread(_read_text_file_stripped, lock_file)
                    old_pid = int(lock_text)
                    break
                except (IOError, ValueError):
                    await asyncio.sleep(0.2)
            if old_pid is None:
                print("⚠️ Lock-файл нечитаемый после повторов. Удаляю как stale и продолжаю.")
                os.remove(lock_file)
            elif old_pid != current_pid and psutil.pid_exists(old_pid):
                print(f"⛔ Бот с PID {old_pid} уже запущен! Завершение работы...")
                sys.exit(1)
        except (IOError, ValueError):
            print("⚠️ Lock-файл поврежден. Удаляю и продолжаю.")
            os.remove(lock_file)
    tmp_lock_file = f"{lock_file}.{current_pid}.tmp"
    await asyncio.to_thread(_write_text_file_atomic, lock_file, str(current_pid), tmp_lock_file)
    session = None
    healthcheck_site = None
    global GLOBAL_BOTS
    background_tasks = []  # Храним задачи здесь
    try:
        global is_shutting_down
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=DEFAULT_EXECUTOR_WORKERS, thread_name_prefix="bot-default"))
        await warm_executor_pool(loop, None, DEFAULT_EXECUTOR_WORKERS, "default")
        await warm_executor_pool(loop, save_executor, 2, "save")
        await warm_executor_pool(loop, git_executor, 1, "git")
        warm_native_media_stack()
        await initialize_database()
        await create_pool()
        await sync_boards_with_config()
        await load_state()
        load_graph_stats() 
        global ROULETTE_EVENTS
        ROULETTE_EVENTS = load_roulette_data("roulette_data.json")
        if ROULETTE_EVENTS:
            print(f"✅ Данные рулетки успешно загружены. Всего событий: {len(ROULETTE_EVENTS)}")
        else:
            print("⚠️ Не удалось загрузить данные для рулетки.")
        GLOBAL_BOTS, session = await initialize_bots()
        if not GLOBAL_BOTS:
            print("❌ Не найдено ни одного токена бота. Завершение работы.")
            return
        active_bots_list = list(GLOBAL_BOTS.values())
        print(f"✅ Инициализировано {len(active_bots_list)} ботов.")
        await setup_pinned_messages(GLOBAL_BOTS)
        try:
            healthcheck_site = await start_healthcheck()
        except Exception as e:
            print(f"⛔ Не удалось запустить healthcheck сервер: {e}")
            healthcheck_site = None
        setup_lifecycle_handlers(loop, active_bots_list, healthcheck_site)
        await restore_durable_delivery_queue()
        background_tasks = await start_background_tasks(GLOBAL_BOTS, healthcheck_site)
        print("⏳ Даем 1.5 секунд на инициализацию...")
        await asyncio.sleep(1.5)
        print("🚀 Запускаем polling...")
        await dp.start_polling(
            *active_bots_list, skip_updates=False,
            allowed_updates=dp.resolve_used_update_types(),
            reset_webhook=True, timeout=60
        )
    except Exception as e:
        import traceback
        print(f"🔥 Критическая ошибка в main: {e}\n{traceback.format_exc()}")
    finally:
        if drain_shutdown_requested:
            await wait_for_delivery_queues_to_drain(
                CONTROLLED_STOP_DRAIN_TIMEOUT_SEC,
                CONTROLLED_STOP_LOG_INTERVAL_SEC,
            )
        print("🛑 Остановка фоновых задач...")
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        if not is_shutting_down:
            bots_to_close = []
            if 'active_bots_list' in locals() and active_bots_list:
                bots_to_close = active_bots_list
            elif GLOBAL_BOTS:
                bots_to_close = list(GLOBAL_BOTS.values())
            await graceful_shutdown(bots_to_close, healthcheck_site)
        if session:
            try:
                await session.close()
                print("✅ Общая HTTP сессия закрыта.")
            except Exception:
                pass
            if hasattr(session, '_connector') and session._connector and not session._connector.closed:
                await session._connector.close()
                print("✅ Коннектор закрыт.")
        if os.path.exists(lock_file):
            try:
                pid_in_file = int(await asyncio.to_thread(_read_text_file_stripped, lock_file))
                if pid_in_file == current_pid: os.remove(lock_file)
            except (IOError, ValueError):
                print("⚠️ Lock-файл нечитаемый при shutdown; не удаляю чужой возможный live-lock.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("ℹ️ Завершение работы по запросу...")
