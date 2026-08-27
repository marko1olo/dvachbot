from common.config import *
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
import os
import re
import asyncio
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional
from common.db_pool import LazyLock

RE_REPLY_QUOTE = re.compile(r'(Пост №|Post No\.)(<[^>]+>)*(\s*<[^>]+>)*(\d+)')
RE_REPLY_QUOTE_FORMAT = re.compile(r'(Пост №|Post No\.)(<[^>]+>)*(\s*<[^>]+>)*(\d+)')
RE_MULTI_REPLY = re.compile(r'>>(\d+)')
RE_MULTI_REPLY_LOCAL = re.compile(r'>>(\d+)')


from common.board_config import BOARD_CONFIG
import time
import logging
from datetime import datetime, timezone

def normalize_storage_timestamp(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.timestamp()
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            try:
                dt = datetime.fromisoformat(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                return 0.0
    return 0.0

BOARDS = list(BOARD_CONFIG.keys())
message_queues = {board: asyncio.Queue(maxsize=0) for board in BOARDS}
runtime_logger = logging.getLogger('runtime')

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

BEST_CHANNEL_ID = int(os.getenv("BEST_CHANNEL_ID", -1002827087363))
LIKES_THRESHOLD = 3
AUTHOR_NOTIFY_LIMIT_PER_MINUTE = 4
ENABLE_MULTILANG = False
QUICK_QUOTE_POST_DISTANCE = 330
PRIORITY_DELIVERY_ENABLED = BOT_PRIORITY_DELIVERY
DELIVERY_INITIAL_CHUNK_SIZE = BOT_DELIVERY_INITIAL_CHUNK_SIZE
DELIVERY_MAX_CHUNK_SIZE = BOT_DELIVERY_MAX_CHUNK_SIZE
DELIVERY_MIN_CHUNK_SIZE = BOT_DELIVERY_MIN_CHUNK_SIZE
DELIVERY_PER_RECIPIENT_TIMEOUT_SEC = BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC
DELIVERY_PHASE_GUARD_SEC = BOT_DELIVERY_PHASE_GUARD_SEC
DELIVERY_MAX_RECIPIENT_RETRIES = BOT_DELIVERY_MAX_RECIPIENT_RETRIES
DELIVERY_SLOW_PHASE_SEC = BOT_DELIVERY_SLOW_PHASE_SEC
DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC = float(os.getenv("BOT_DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC", "15.0"))
DURABLE_DELIVERY_QUEUE_ENABLED = BOT_DURABLE_DELIVERY_QUEUE
MAX_COPY_MAP_POSTS_IN_MEMORY = BOT_COPY_CACHE_POST_LIMIT
MAX_MESSAGES_IN_MEMORY = BOT_POST_CACHE_LIMIT
PRIORITY_PHASE_BUDGET_SEC = BOT_PRIORITY_PHASE_BUDGET_SEC
PASSIVE_PHASE_BUDGET_SEC = BOT_PASSIVE_PHASE_BUDGET_SEC

author_reaction_notify_lock = LazyLock()
author_reaction_notify_tracker = defaultdict(list)
pending_edit_lock = LazyLock()
pending_edit_tasks = {}
current_media_groups = {}
media_group_creation_lock = LazyLock()
media_group_timers = {}
sent_media_groups = deque(maxlen=10000)  # deque supports .append() and auto-evicts old entries
_last_persona_dialogue_user_ts = {}
_last_persona_board_ts = {}
_persona_processed_posts: set[int] = set()
last_persona_dialogue_user_ts = _last_persona_dialogue_user_ts
last_persona_board_ts = _last_persona_board_ts
_active_duels = {}
last_messages = deque(maxlen=200)
reaction_ratelimit = defaultdict(float)
current_deliveries = {}
posts_pending_deletion = set()

# Трекинг активных атак для ограничения спама (макс. 2 активных эффекта каждого типа на автора)
_ACTIVE_AUTHOR_ATTACKS: dict[str, dict[int, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
_GLOBAL_COMBAT_COOLDOWNS: dict[int, float] = {}
_TARGET_LAST_ATTACKED_TS: dict[int, float] = {}
_ATTACKER_SERIES_HISTORY: dict[int, list[float]] = defaultdict(list)
_VICTIM_ROB_COOLDOWNS: dict[int, float] = {}

def get_target_grief_protection_remaining(target_id: int) -> int:
    """
    Возвращает оставшееся время (сек) иммунитета цели от повторных атак (окно 5 мин / 300 сек).
    """
    now = time.time()
    last_attack = _TARGET_LAST_ATTACKED_TS.get(target_id, 0.0)
    if now < last_attack:
        return int(last_attack - now)
    return 0

def register_target_attack(target_id: int, duration_seconds: int = 300, attacker_id: int | None = None):
    """
    Регистрирует атаку на цель, включая 5-минутное окно анти-гриферской защиты (diminishing returns).
    Защищает от эксплойта самоатаки: если attacker_id == target_id, иммунитет не дается.
    """
    if attacker_id is not None and attacker_id == target_id:
        return
    _TARGET_LAST_ATTACKED_TS[target_id] = time.time() + duration_seconds

def get_victim_rob_cooldown_remaining(target_id: int) -> int:
    """
    Возвращает оставшееся время (сек) иммунитета жертвы от повторных ограблений (20 минут).
    """
    now = time.time()
    expire_ts = _VICTIM_ROB_COOLDOWNS.get(target_id, 0.0)
    if now < expire_ts:
        return int(expire_ts - now)
    return 0

def set_victim_rob_cooldown(target_id: int, cooldown_seconds: int | None = None):
    """
    Устанавливает кулдаун жертвы от повторных ограблений (рандом 5-15 минут: больничка / мусарня).
    """
    if cooldown_seconds is None:
        cooldown_seconds = random.randint(300, 900)
    _VICTIM_ROB_COOLDOWNS[target_id] = time.time() + cooldown_seconds

def calculate_escalating_combat_cooldown(attacker_id: int, base_seconds: int = 180) -> int:
    """
    Рассчитывает прогрессивный кулдаун для атакующего при частых сериях атак (эскалация спама).
    Если атакующий спамит чаще чем раз в 60 сек, кулдаун прогрессивно увеличивается: x1 -> x2 -> x4.
    """
    now = time.time()
    history = _ATTACKER_SERIES_HISTORY[attacker_id]
    # Очищаем атаки старше 10 минут
    history = [ts for ts in history if now - ts < 600]
    history.append(now)
    _ATTACKER_SERIES_HISTORY[attacker_id] = history
    
    # Считаем атаки за последние 3 минуты
    recent_fast_attacks = sum(1 for ts in history if now - ts < 180)
    if recent_fast_attacks <= 1:
        return base_seconds
    elif recent_fast_attacks == 2:
        return base_seconds * 2
    else:
        return min(base_seconds * 4, 1800) # Максимум 30 мин кулдауна

def get_combat_cooldown_remaining(user_id: int) -> int:
    """
    Возвращает количество секунд оставшегося глобального боевого кулдауна.
    """
    now = time.time()
    last = _GLOBAL_COMBAT_COOLDOWNS.get(user_id, 0)
    if now < last:
        return int(last - now)
    return 0

def set_combat_cooldown(user_id: int, cooldown_seconds: int = 180):
    """
    Устанавливает глобальный боевой кулдаун (с учетом прогрессивной эскалации).
    """
    actual_cooldown = calculate_escalating_combat_cooldown(user_id, cooldown_seconds)
    _GLOBAL_COMBAT_COOLDOWNS[user_id] = time.time() + actual_cooldown

def count_active_attacker_effects(item_type: str, attacker_id: int) -> int:
    """
    Возвращает количество одновременно активных жертв от данного атакующего для item_type.
    Автоматически очищает истекшие эффекты.
    """
    now = time.time()
    victim_map = _ACTIVE_AUTHOR_ATTACKS[item_type].get(attacker_id, {})
    expired = [tgt for tgt, exp in list(victim_map.items()) if exp <= now]
    for tgt in expired:
        victim_map.pop(tgt, None)
    return len(victim_map)

def register_attacker_effect(item_type: str, attacker_id: int, target_id: int, duration_seconds: float):
    """
    Регистрирует активный эффект атакующего на жертву.
    """
    now = time.time()
    _ACTIVE_AUTHOR_ATTACKS[item_type][attacker_id][target_id] = now + duration_seconds

_DAILY_SHOP_PURCHASES: dict[tuple[int, str, str], int] = defaultdict(int)

SHOP_DAILY_LIMITS = {
    "mute": 6,
    "partyvan": 2,
    "knife": 10,
    "shit": 20,
    "laxative": 6,
    "schizopill": 6
}

def get_user_daily_shop_buys(user_id: int, item: str) -> int:
    """Возвращает число покупок данного товара пользователем за текущие сутки UTC."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _DAILY_SHOP_PURCHASES[(user_id, item, today_str)]

def check_shop_purchase_limit(user_id: int, item: str) -> tuple[bool, int, int]:
    """
    Проверяет, не превышен ли суточный лимит покупок.
    Возвращает (is_allowed, current_count, max_limit).
    """
    limit = SHOP_DAILY_LIMITS.get(item)
    if limit is None:
        return True, 0, 0
    current = get_user_daily_shop_buys(user_id, item)
    if current >= limit:
        return False, current, limit
    return True, current, limit

def record_shop_purchase(user_id: int, item: str):
    """Фиксирует покупку товара в суточный счетчик."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _DAILY_SHOP_PURCHASES[(user_id, item, today_str)] += 1

_ATTACK_WINDOW_SEC = 3 * 3600 # 3 hours
_MAX_TARGETS_PER_WINDOW = 2
_ATTACKER_TARGET_HISTORY: dict[int, list[tuple[float, int]]] = {}
_ATTACKER_ABUSE_WARNINGS: dict[int, int] = {}

def check_attack_abuse_limit(attacker_id: int, target_id: int) -> tuple[bool, str, int]:
    """
    Защита от массовых мутов и доносов (максимум 2 уникальные жертвы за 3 часа).
    Возвращает: (is_blocked: bool, outcome: str, fine_amount: int)
      - 'allowed': действие разрешено.
      - 'warning': 1-я попытка превысить порог (предупреждение, действие заблокировано).
      - 'spetsnaz_fine': 2-я+ попытка (штурм спецназа, деанон, штраф 1000₪, мут 1ч, действие заблокировано).
    """
    now = time.time()
    history = _ATTACKER_TARGET_HISTORY.setdefault(attacker_id, [])
    cutoff = now - _ATTACK_WINDOW_SEC
    history = [entry for entry in history if entry[0] > cutoff]
    _ATTACKER_TARGET_HISTORY[attacker_id] = history

    unique_targets = {t_id for _, t_id in history}

    if target_id in unique_targets or len(unique_targets) < _MAX_TARGETS_PER_WINDOW:
        history.append((now, target_id))
        return False, "allowed", 0

    warn_count = _ATTACKER_ABUSE_WARNINGS.get(attacker_id, 0)
    if warn_count == 0:
        _ATTACKER_ABUSE_WARNINGS[attacker_id] = 1
        return True, "warning", 0
    else:
        _ATTACKER_ABUSE_WARNINGS[attacker_id] = warn_count + 1
        return True, "spetsnaz_fine", 1000

def reset_combat_state():
    _GLOBAL_COMBAT_COOLDOWNS.clear()
    _TARGET_LAST_ATTACKED_TS.clear()
    _ACTIVE_AUTHOR_ATTACKS.clear()
    _ATTACKER_SERIES_HISTORY.clear()
    _VICTIM_ROB_COOLDOWNS.clear()
    _ATTACKER_TARGET_HISTORY.clear()
    _ATTACKER_ABUSE_WARNINGS.clear()

# Explicitly export private helpers so 'from shared_state import *' in
# broadcaster.py, delivery_manager.py, post_processor.py, archive_manager.py
# picks them up. Without __all__, Python excludes names starting with '_'.
__all__ = [
    '_GLOBAL_COMBAT_COOLDOWNS',
    '_ACTIVE_AUTHOR_ATTACKS',
    '_TARGET_LAST_ATTACKED_TS',
    '_ATTACKER_SERIES_HISTORY',
    '_ATTACKER_TARGET_HISTORY',
    '_ATTACK_WINDOW_SEC',
    '_ATTACKER_ABUSE_WARNINGS',
    '_PASSPORT_DATA',
    '_stats_cooldown_tracker',
    '_VICTIM_ROB_COOLDOWNS',
    'get_target_grief_protection_remaining',
    'register_target_attack',
    'get_victim_rob_cooldown_remaining',
    'set_victim_rob_cooldown',
    'calculate_escalating_combat_cooldown',
    'get_combat_cooldown_remaining',
    'set_combat_cooldown',
    'count_active_attacker_effects',
    'register_attacker_effect',
    'check_attack_abuse_limit',
    'RE_REPLY_QUOTE',
    'RE_REPLY_QUOTE_FORMAT',
    'RE_MULTI_REPLY',
    'RE_MULTI_REPLY_LOCAL',
    'BOARDS',
    'normalize_storage_timestamp',
    'message_queues',
    'runtime_logger',
    'POSITIVE_REACTIONS',
    'LAUGHING_REACTIONS',
    'NEGATIVE_REACTIONS',
    'CLOWN_REACTION',
    'THINKING_REACTIONS',
    'SHOCK_REACTIONS',
    'SAD_REACTIONS',
    'POLITICAL_REACTIONS',
    'SYMBOLIC_REACTIONS',
    'INSULT_REACTIONS',
    'MAT_WORDS',
    'BEST_CHANNEL_ID',
    'LIKES_THRESHOLD',
    'AUTHOR_NOTIFY_LIMIT_PER_MINUTE',
    'ENABLE_MULTILANG',
    'QUICK_QUOTE_POST_DISTANCE',
    'PRIORITY_DELIVERY_ENABLED',
    'DELIVERY_INITIAL_CHUNK_SIZE',
    'DELIVERY_MIN_CHUNK_SIZE',
    'DELIVERY_PER_RECIPIENT_TIMEOUT_SEC',
    'DELIVERY_PHASE_GUARD_SEC',
    'DELIVERY_MAX_RECIPIENT_RETRIES',
    'DELIVERY_SLOW_PHASE_SEC',
    'DELIVERY_TELEGRAM_REQUEST_TIMEOUT_SEC',
    'DURABLE_DELIVERY_QUEUE_ENABLED',
    'MAX_COPY_MAP_POSTS_IN_MEMORY',
    'MAX_MESSAGES_IN_MEMORY',
    'PRIORITY_PHASE_BUDGET_SEC',
    'PASSIVE_PHASE_BUDGET_SEC',
    'author_reaction_notify_lock',
    'author_reaction_notify_tracker',
    'pending_edit_lock',
    'pending_edit_tasks',
    'current_media_groups',
    'media_group_creation_lock',
    'media_group_timers',
    'sent_media_groups',
    '_last_persona_dialogue_user_ts',
    '_last_persona_board_ts',
    'last_persona_dialogue_user_ts',
    'last_persona_board_ts',
    '_active_duels',
    '_duel_cooldowns',
    '_stats_cache',
    'last_messages',
    'reaction_ratelimit',
    '_media_group_state_key',
    '_iter_message_ids_for_copy',
    '_drop_post_copy_maps_unlocked',
    '_trim_post_copy_maps_unlocked',
    '_trim_messages_storage_unlocked',
    'is_shutting_down',
    'drain_shutdown_requested',
    'durable_delivery_stats',
    'weekly_active_users',
    '_prepare_queue_item',
    'GLOBAL_BOTS',
    'LazyStorageLock',
    'storage_lock',
    'board_data',
    'state',
    'MODE_FLAGS',
    'shadow_fake_post_counters',
    'messages_storage',
    'post_to_messages',
    'message_to_post',
    'BroadcastConfig',
    'THREAD_BOARDS',
    'locally_created_posts',
    'enqueue_board_message',
    'current_deliveries',
    'posts_pending_deletion',
    'market_state',
    'MIRROR_CHANNELS',
    'ARCHIVE_CHANNEL_ID',
    'ARCHIVE_POSTING_BOT_ID',
    'AUTHORIZED_ARCHIVE_BOTS',
    'SPECIAL_NUMERALS_CONFIG',
    'save_executor',
    'ROULETTE_EVENTS',
    '_safe_len',
    '_stats_cooldown_tracker',
    '_PASSPORT_DATA',
    'OP_COMMAND_COOLDOWN',
    'ANIME_CMD_COOLDOWN',
    'anime_cmd_lock',
    'info_cmd_lock',
    'DEANON_COOLDOWN',
    'deanon_lock',
    'roulette_lock',
    'WEEKLY_ACTIVE_DAYS',
    'ANIME_MEDIA_CONCURRENCY',
    'ANIME_URL_FETCH_TIMEOUT_SEC',
    'ANIME_URL_FETCH_TOTAL_SEC',
    'ANIME_URL_FETCH_PARALLEL',
    'ANIME_DOWNLOAD_TIMEOUT_SEC',
    'ANIME_DOWNLOAD_TOTAL_SEC',
    'ANIME_DOWNLOAD_PARALLEL',
    'ANIME_REFILL_ROUNDS',
    'anime_media_gate',
    'ShadowRejectContext',
    'NewPostParams',
    'STOP_WORDS',
    '_DUEL_TIMEOUT'
]

def _media_group_state_key(chat_id: int, media_group_id: str) -> str:
    return f"{chat_id}:{media_group_id}"

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
    if max_posts < 0:
        return 0, 0
    excess = len(post_to_messages) - max_posts
    if excess <= 0:
        return 0, 0
    if max_posts == 0:
        stale_posts = list(post_to_messages)
    else:
        stale_posts = [k for k, _ in zip(post_to_messages, range(excess))]
    removed_reverse = 0
    for post_num in stale_posts:
        removed_reverse += _drop_post_copy_maps_unlocked(post_num)
    return len(stale_posts), removed_reverse

def _trim_messages_storage_unlocked(max_posts: int) -> int:
    if max_posts < 0:
        return 0
    excess = len(messages_storage) - max_posts
    if excess <= 0:
        return 0
    if max_posts == 0:
        stale_posts = list(messages_storage)
    else:
        stale_posts = [k for k, _ in zip(messages_storage, range(excess))]
    removed = 0
    for post_num in stale_posts:
        if messages_storage.pop(post_num, None) is not None:
            removed += 1
    return removed



market_state = {
    'event_text': 'Цены стабильны. Никаких событий.',
    'multipliers': {},
    'last_update': 0
}
is_shutting_down = False
drain_shutdown_requested = False
durable_delivery_stats = {
    'enabled': True,
    'persisted': 0,
    'persist_failed': 0,
    'deleted': 0,
    'restored_items': 0,
    'restored_recipients': 0,
    'restore_deleted_empty': 0,
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

class LazyStorageLock:
    def __init__(self):
        self._lock = None

    @property
    def lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def __aenter__(self):
        await self.lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()

storage_lock = LazyStorageLock()  # Ленивая блокировка для доступа к messages_storage, post_to_messages и т.д.

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
    'rus_mode': False,
    'abu_mode': False,
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
    'user_settings': defaultdict(lambda: {'nsfw': False, 'hide': set(), 'disable_ai_roasts': False, 'hide_ai_slop': False, 'lie_media': False}),
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

MODE_FLAGS = ['anime_mode', 'zaputin_mode', 'slavaukraine_mode', 'suka_blyat_mode', 'polish_mode', 'warhammer_mode', 'imperial_mode', 'gopnik_mode', 'schizo_mode', 'matrix_mode', 'america_mode', 'holiday_mode', 'oldweb_mode', 'jewish_mode', 'rus_mode', 'abu_mode']
shadow_fake_post_counters = {}


messages_storage = {}

post_to_messages = {}

message_to_post = {}

@dataclass
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
# (pending_edit_tasks and pending_edit_lock are defined at top of shared_state.py)


# --- Archive Config ---
def _parse_archive_mirror_channels() -> list[int]:
    raw = os.getenv("ARCHIVE_CHANNELS") or os.getenv("MIRROR_CHANNELS")
    if raw:
        channels = []
        for ch in raw.split(","):
            ch = ch.strip()
            if ch:
                try:
                    cid = int(ch)
                    if cid != 0:
                        channels.append(cid)
                except ValueError:
                    pass
        if channels:
            return channels
    archive_single = os.getenv("ARCHIVE_CHANNEL_ID")
    if archive_single:
        try:
            cid = int(archive_single.strip())
            if cid != 0:
                return [cid]
        except ValueError:
            pass
    return [-1003549106152, -1003651702446, -1003614166511]

MIRROR_CHANNELS = _parse_archive_mirror_channels()

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

ROULETTE_EVENTS = []

def _safe_len(value) -> int:
    try:
        return len(value)
    except Exception:
        return -1

# Globals Extracted
_stats_cache: dict = {}   # board_id -> {ts: float, photos: list[bytes]}
_stats_cooldown_tracker = {}
# _active_duels defined at top of file
_duel_cooldowns: dict = {} # user_id -> timestamp
_PASSPORT_DATA = {
    'ru': {
        'mental': ["Вялотекущая шизофрения", "Педераст", "Газонюх", "Терминальная стадия двачевания", "ПТСР после /po/", "Синдром Туретта", "Одержимость трапами", "Асексуал (насильно)", "Зумер с деменцией", "Свидетель Вайпа", "Жертва психиатрии", "Пиздабол", "Мамкин анархист", "Солевой", "Овощ", "Гигачад (нет)"],
        'inv': ["Справка из дурки", "Трусы с чиркашом", "Банка 'Ягуара'", "Диск с ЦП", "Онахол", "Дакимакура", "Вентилятор", "Флешка с ЦП", "Диплом шараги", "Усы Сталина", "Резиновая вагина (б/у)", "Пакет с пакетами", "Мать (продана)", "Шприц", "Носок (стоячий)", "Тетрадь смерти", "ЕОТ (в мечтах)", "Биткоин (нарисованный)", "15 рублей", "Вейп", "Повестка"],
        'sec': ["Дрочит на фурри", "Любитель лоликона", "Стучит товарищу майору", "Любит унижения", "Мечтает стать модером", "Смотрит цп", "Не мылся год", "Не девственник (врет)", "Боится женщин", "Ест кал", "Хочет в Польшу", "Верит в плоскую землю", "Украл у мамки деньги", "Плачет после секса"]
    },
    'en': {
        'mental': ["Chronic Schizophrenia", "Terminal 4chan addiction", "PTSD after /pol/", "Tourette's", "Trap obsession", "Incel (forced)", "Dementia Zoomer", "Wipe Witness", "Psych ward victim", "Pathological liar", "Basement anarchist", "Meth head", "Vegetable", "Gigachad (not)"],
        'inv': ["Autism certificate", "Stained underwear", "Monster Energy", "Fan (for shit)", "CP Flash drive (fake)", "College debt", "Hitler's moustache", "Used waifu pillow", "Bag of bags", "Sold mom", "Syringe", "Cum sock (stiff)", "Death Note", "GF (imaginary)", "Bitcoin (drawn)", "0.01$", "Vape", "Draft notice"],
        'sec': ["Jerks to furries", "Snitch for FBI", "Loves humiliation", "Wants to be janny", "Watches loli", "Hasn't showered in 2024", "Fake virgin", "Scared of women", "Eats bugs", "Wants to go to Brazil", "Flat earther", "Stole mom's credit card", "Cries while pooping"]
    },
    'jp': {
        'mental': ["統合失調症", "2ch中毒末期", "政治厨PTSD", "トゥレット症候群", "男の娘中毒", "非モテ（強制）", "認知症ズーマー", "祭り目撃者", "精神科の犠牲者", "虚言癖", "ママのアナキスト", "ヤク中", "植物人間", "ギガチャド（嘘）"],
        'inv': ["障害者手帳", "シミ付きパンツ", "ストロングゼロ", "扇風機（クソ用）", "ロリ画像USB", "Fラン大学の学位", "スターリンの髭", "中古オナホ", "レジ袋の山", "売られた母", "注射器", "カチカチの靴下", "デスノート", "脳内彼女", "ビットコイン（絵）", "15ルーブル", "Vape", "赤紙"],
        'sec': ["ケモナー", "警察の犬", "ドM", "削除人になりたい", "ロリコン", "1年風呂入ってない", "童貞（嘘）", "女性恐怖症", "食糞", "異世界に行きたい", "地球平面説信者", "親の金盗んだ", "うんこ中に泣く"]
    }
}
OP_COMMAND_COOLDOWN = 60 # 1 минута кулдауна для команд модерации ОПа в треде

ANIME_CMD_COOLDOWN = 25 # 25 секунд

anime_cmd_lock = LazyLock()

info_cmd_lock = LazyLock() # Кулдаун для команд /stats, /active

DEANON_COOLDOWN = 180  # 3 минуты

deanon_lock = LazyLock()

roulette_lock = LazyLock()

WEEKLY_ACTIVE_DAYS = max(1, BOT_WEEKLY_ACTIVE_DAYS)

ANIME_MEDIA_CONCURRENCY = max(1, BOT_ANIME_MEDIA_CONCURRENCY)

ANIME_URL_FETCH_TIMEOUT_SEC = max(3.0, float(BOT_ANIME_URL_FETCH_TIMEOUT_SEC))

ANIME_URL_FETCH_TOTAL_SEC = max(ANIME_URL_FETCH_TIMEOUT_SEC, float(BOT_ANIME_URL_FETCH_TOTAL_SEC))

ANIME_URL_FETCH_PARALLEL = max(1, int(BOT_ANIME_URL_FETCH_PARALLEL))

ANIME_DOWNLOAD_TIMEOUT_SEC = max(5.0, float(BOT_ANIME_DOWNLOAD_TIMEOUT_SEC))

ANIME_DOWNLOAD_TOTAL_SEC = max(ANIME_DOWNLOAD_TIMEOUT_SEC, float(BOT_ANIME_DOWNLOAD_TOTAL_SEC))

ANIME_DOWNLOAD_PARALLEL = max(1, int(BOT_ANIME_DOWNLOAD_PARALLEL))

ANIME_REFILL_ROUNDS = max(0, int(BOT_ANIME_REFILL_ROUNDS))

anime_media_gate = asyncio.Semaphore(ANIME_MEDIA_CONCURRENCY)

@dataclass
class ShadowRejectContext:
    bot: Bot
    board_id: str
    user_id: int
    content: dict
    reply_to_post: int | None = None
    stream: str = 'ru'

@dataclass
class NewPostParams:
    bot_instance: Bot
    board_id: str
    user_id: int
    content: dict
    reply_to_post: int | None
    is_shadow_muted: bool
    stream: str = 'ru'

STOP_WORDS = set([
    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 
    'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 
    'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 
    'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли', 
    'если', 'уже', 'или', 'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь', 
    'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей', 
    'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя', 
    'их', 'чем', 'была', 'сам', 'чтоб', 'без', 'будто', 'чего', 'раз', 'тоже', 
    'себе', 'под', 'будет', 'ж', 'тогда', 'кто', 'этот', 'того', 'потому', 
    'этого', 'какой', 'совсем', 'ним', 'здесь', 'этом', 'один', 'почти', 'мой', 
    'тем', 'чтобы', 'нее', 'сейчас', 'были', 'куда', 'зачем', 'всех', 'никогда', 
    'можно', 'при', 'наконец', 'два', 'об', 'другой', 'хоть', 'после', 'над', 
    'больше', 'тот', 'через', 'эти', 'нас', 'про', 'всего', 'них', 'какая', 
    'много', 'разве', 'три', 'эту', 'моя', 'впрочем', 'хорошо', 'свою', 'этой', 
    'перед', 'иногда', 'лучше', 'чуть', 'том', 'нельзя', 'такой', 'им', 'более', 
    'всегда', 'конечно', 'всю', 'между', 'это', 'просто', 'блин', 'бля', 'ебать'
])


# --- Extracted from main.py Phase 9 (Helpers) ---
# reaction_ratelimit, author_reaction_notify_tracker, author_reaction_notify_lock initialized at top of file
_DUEL_TIMEOUT = 120       # секунд на принятие
