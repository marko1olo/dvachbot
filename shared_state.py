from common.config import *
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
import os
import re
import asyncio
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

BEST_CHANNEL_ID = -1001234567890
LIKES_THRESHOLD = 3
AUTHOR_NOTIFY_LIMIT_PER_MINUTE = 4
ENABLE_MULTILANG = False
QUICK_QUOTE_POST_DISTANCE = 330
PRIORITY_DELIVERY_ENABLED = BOT_PRIORITY_DELIVERY
DELIVERY_INITIAL_CHUNK_SIZE = BOT_DELIVERY_INITIAL_CHUNK_SIZE
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

# Explicitly export private helpers so 'from shared_state import *' in
# broadcaster.py, delivery_manager.py, post_processor.py, archive_manager.py
# picks them up. Without __all__, Python excludes names starting with '_'.
__all__ = [
    'RE_REPLY_QUOTE',
    'RE_REPLY_QUOTE_FORMAT',
    'RE_MULTI_REPLY',
    'RE_MULTI_REPLY_LOCAL',
    'BOARDS',
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
    if max_posts < 0 or len(post_to_messages) <= max_posts:
        return 0, 0
    if max_posts == 0:
        stale_posts = list(post_to_messages)
    else:
        keep_posts = set(sorted(post_to_messages.keys(), reverse=True)[:max_posts])
        stale_posts = [post_num for post_num in post_to_messages if post_num not in keep_posts]
    removed_reverse = 0
    for post_num in stale_posts:
        removed_reverse += _drop_post_copy_maps_unlocked(post_num)
    return len(stale_posts), removed_reverse

def _trim_messages_storage_unlocked(max_posts: int) -> int:
    if max_posts < 0 or len(messages_storage) <= max_posts:
        return 0
    if max_posts == 0:
        stale_posts = list(messages_storage)
    else:
        keep_posts = set(sorted(messages_storage.keys(), reverse=True)[:max_posts])
        stale_posts = [post_num for post_num in messages_storage if post_num not in keep_posts]
    removed = 0
    for post_num in stale_posts:
        if messages_storage.pop(post_num, None) is not None:
            removed += 1
    return removed


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

MODE_FLAGS = ['anime_mode', 'zaputin_mode', 'slavaukraine_mode', 'suka_blyat_mode', 'polish_mode', 'warhammer_mode', 'imperial_mode', 'gopnik_mode', 'schizo_mode', 'matrix_mode', 'america_mode', 'holiday_mode', 'oldweb_mode', 'jewish_mode']
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
