# -*- coding: utf-8 -*-
import time
import asyncio
import hashlib
import re
import difflib
import unicodedata
import logging
from typing import Dict, List, Tuple, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta, UTC
from enum import Enum, auto

logger = logging.getLogger("spam_filter")

class SpamResult(Enum):
    CLEAN = auto()
    WARNING = auto()
    BAN_REQUIRED = auto()
    GLOBAL_BAN_REQUIRED = auto()
    BAYAN_MUTE = auto()
    SHADOW_MUTE_REQUIRED = auto()
    REPOST_BLOCKED = auto()

# --- Volatile State Trackers ---
user_spam_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
cross_board_spam_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=5))
image_spam_tracker: Dict[str, List[float]] = defaultdict(list)

# Board-level trackers mapped by board_id then user_id
_spam_trackers: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
_spam_violations: Dict[str, Dict[int, dict]] = defaultdict(dict)
_spam_filter_words: Dict[str, set] = defaultdict(set)
_reaction_banned_users: Dict[str, set] = defaultdict(set)

# --- Bayan Detection Trackers ---
# {user_id: deque of (timestamp, fingerprint, content_snippet)}
_bayan_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=100))
# Board-level recent content fingerprints: {board_id: deque of (timestamp, fingerprint)}
_board_recent_fingerprints: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
# Tracks how many times a user has been bayan-muted / escalated: {user_id: int}
_bayan_mute_count: Dict[int, int] = defaultdict(int)
# Tracks when the last bayan mute was applied: {user_id: float}
_bayan_mute_last_ts: Dict[int, float] = defaultdict(float)

# --- Flood Trackers ---
# {user_id: deque of timestamps}
_user_request_timestamps: Dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
# {user_id: deque of (timestamp, text_snippet)}
_user_link_timestamps: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
# {user_id: deque of timestamps for public channel/chat reposts}
_user_repost_timestamps: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
# {user_id: {media_group_id: {'first_ts': float, 'blocked': bool, 'response': str}}}
_seen_repost_media_groups: Dict[int, Dict[str, dict]] = defaultdict(dict)
# {user_id: deque of timestamps}
_short_gibberish_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=30))
_last_auto_cleanup_ts: float = 0.0

# --- In-Memory Shadow Mutes Fast Cache (DOS & Flood Shield) ---
# {user_id or (user_id, board_id): expires_at_timestamp}
_in_memory_shadow_muted_users: Dict[Any, float] = {}

def set_in_memory_shadow_mute(
    user_id: int,
    board_id: Any = 'ALL',
    expires_at: float | None = None,
    duration_seconds: float | None = None
) -> float:
    """Sets shadow mute expiration in memory for instant O(1) checks without DB queries."""
    now = time.time()
    if expires_at is None:
        dur = float(duration_seconds or 1200.0)
        exp_ts = now + dur
    else:
        exp_ts = float(expires_at)

    _in_memory_shadow_muted_users[user_id] = exp_ts
    if board_id == 'ALL' or board_id is None:
        _in_memory_shadow_muted_users[(user_id, 'ALL')] = exp_ts
        try:
            from shared_state import BOARDS
            for b in BOARDS:
                _in_memory_shadow_muted_users[(user_id, str(b))] = exp_ts
        except Exception:
            pass
    elif isinstance(board_id, (list, set, tuple)):
        for b in board_id:
            _in_memory_shadow_muted_users[(user_id, str(b))] = exp_ts
    else:
        _in_memory_shadow_muted_users[(user_id, str(board_id))] = exp_ts

    return exp_ts

def is_user_in_memory_shadow_muted(user_id: int, board_id: str | None = None, now_ts: float | None = None) -> bool:
    """
    Checks if a user is shadow-muted using strictly in-memory data (< 0.1ms).
    Zero database queries, zero db_lock acquisitions.
    """
    if not user_id:
        return False

    now = float(now_ts) if now_ts is not None else time.time()

    # 1. Global / direct user check
    exp = _in_memory_shadow_muted_users.get(user_id)
    if exp is not None:
        if exp > now:
            return True
        else:
            _in_memory_shadow_muted_users.pop(user_id, None)

    # 2. Board-specific checks
    if board_id:
        b_str = str(board_id)
        exp_b = _in_memory_shadow_muted_users.get((user_id, b_str))
        if exp_b is not None:
            if exp_b > now:
                return True
            else:
                _in_memory_shadow_muted_users.pop((user_id, b_str), None)

        exp_all = _in_memory_shadow_muted_users.get((user_id, 'ALL'))
        if exp_all is not None:
            if exp_all > now:
                return True
            else:
                _in_memory_shadow_muted_users.pop((user_id, 'ALL'), None)

    return False

def clear_in_memory_shadow_mutes(user_id: int | None = None) -> None:
    """Clears in-memory shadow mutes for a user (or globally)."""
    if user_id is not None:
        _in_memory_shadow_muted_users.pop(user_id, None)
        for k in list(_in_memory_shadow_muted_users.keys()):
            if isinstance(k, tuple) and k[0] == user_id:
                _in_memory_shadow_muted_users.pop(k, None)
    else:
        _in_memory_shadow_muted_users.clear()

def load_active_shadow_mutes_from_db(db_path: str | None = None) -> int:
    """
    Loads active shadow mutes from SQLite into _in_memory_shadow_muted_users.
    Uses read-only URI mode to prevent any WAL write lock contention.
    Returns count of loaded records.
    """
    try:
        import os, sqlite3
        if not db_path:
            try:
                from common.config import DB_NAME
                db_path = DB_NAME
            except Exception:
                db_path = r"C:\dev\dvachbot\dvach_bot.db"

        if not db_path or not os.path.exists(str(db_path)):
            return 0

        clean_path = str(db_path).replace("\\", "/")
        now_ts = time.time()
        conn = sqlite3.connect(f"file:{clean_path}?mode=ro", uri=True, timeout=1.0)
        loaded = 0
        try:
            cur = conn.execute(
                "SELECT user_id, board_id, expires_at FROM Mutes WHERE mute_type = 'shadow' AND expires_at > ?",
                (now_ts,)
            )
            for uid, bid, exp in cur.fetchall():
                if exp and exp > now_ts:
                    set_in_memory_shadow_mute(int(uid), str(bid), float(exp))
                    loaded += 1
        finally:
            conn.close()
        return loaded
    except Exception as e:
        logger.debug(f"Failed to load shadow mutes from DB: {e}")
        return 0

# --- Wall-of-Text & Sybil Raid Tracker ---
# deque of (timestamp, user_id, board_id, norm_text, raw_snippet)
_board_recent_wall_of_texts: deque = deque(maxlen=500)
WALL_OF_TEXT_MIN_LEN = 100
SYBIL_RAID_WINDOW_SEC = 1800.0   # 30 minutes window for detecting bot networks posting same copypasta
CROSS_BOARD_FAST_SEC = 300.0     # 5 minutes window for cross-board copy blast
TEXT_BAYAN_MIN_LEN = 80          # Short texts (< 80 chars) are casual banter and immune from bayan bans

# --- Constants & Thresholds ---
BAYAN_WINDOW_SEC = 180          # 3 minutes sliding window (180s matches '3+ баяна за 3 минуты')
BAYAN_THRESHOLD = 3             # 3 bayans in 3 minutes -> 20 min shadowmute
BAYAN_STICKER_THRESHOLD = 5     # 5 sticker repeats in 180s (increased from 3 to 5)
BAYAN_MEDIA_THRESHOLD = 5       # 5 sticker/media repeats in 180s
BAYAN_BASE_MUTE_SEC = 1200      # 20 minutes base shadowmute (1200 seconds)
BAYAN_STICKER_BASE_MUTE_SEC = 120  # 120 seconds base shadowmute for sticker repeats (reduced from 1200s / 20m)
BAYAN_RESET_SEC = 3600          # Reset escalation counter after 1 hour without infractions
MAX_BAYAN_MUTE_SEC = 1800       # 30 minutes max shadow mute for bayan
MAX_SHADOW_MUTE_SEC = 1800      # 30 minutes hard cap

# Flood limits
BURST_FLOOD_LIMIT = 8           # > 8 messages in 4 seconds
BURST_FLOOD_WINDOW = 4.0
RATE_FLOOD_LIMIT = 15           # > 15 messages in 15 seconds
RATE_FLOOD_WINDOW = 15.0
MINUTE_FLOOD_LIMIT = 30         # > 30 messages in 60 seconds
MINUTE_FLOOD_WINDOW = 60.0
FLOOD_BASE_MUTE_SEC = 300.0     # 5 minutes base shadowmute for fast flood (not 20m!)

# Short Gibberish & Keysmash Flood
SHORT_GIBBERISH_MAX_LEN = 25
SHORT_GIBBERISH_FAST_WINDOW = 5.0
SHORT_GIBBERISH_FAST_LIMIT = 3
SHORT_GIBBERISH_SLOW_WINDOW = 10.0
SHORT_GIBBERISH_SLOW_LIMIT = 4
SHORT_GIBBERISH_VETERAN_MUTE = 600
SHORT_GIBBERISH_DEFAULT_MUTE = 1800

# Repost / Forward from public channels limits & responses
REPOST_LIMIT_PER_MINUTE = 6
REPOST_WINDOW_SEC = 60.0
REPOST_FLOOD_MUTE_SEC = 120.0  # 2 minutes shadowmute for news repost spammers (was 1200s / 20m)

REPOST_FLOOD_RESPONSES: List[str] = [
    "Уймись, ковбой, тут не личка твоей блядины, чтобы твоё говно репощенное читать!",
    "Тормози, шлюхопересыльщик. Тут борда, а не помойка для репостов из твоих ссаных пабликов.",
    "Завали ебало с репостами. Тут борда, а не твой сраный Твиттер для бесконечных форвардов.",
    "Хватит форвардить этот кал, шизоид. Своими словами пиши или пиздуй отсюда.",
    "Репостоблядь detected. Уйми пальцы, тут никто твой пересланный мусор читать не нанимался.",
]

# Доски с разрешенным репост-контентом (например /sex/, куда аноны постят контент из каналов)
REPOST_EXEMPT_BOARDS: set[str] = {"sex"}

# User Tiers and Flood Limits (Послабления и скидки для ветеранов)
USER_TIERS = {
    'newbie': {
        'name': 'Новичок',
        'min_posts': 0,
        'burst_limit': 8,
        'burst_window': 4.0,
        'rate_limit': 15,
        'minute_limit': 30,
        'repeat_bonus': 0,
        'flood_base_mute_sec': 300.0,
        'multiplier': 1.0,
        'repost_limit': 4,
        'can_repost_mute': True,
    },
    'anon': {
        'name': 'Анон',
        'min_posts': 20,
        'burst_limit': 10,
        'burst_window': 3.8,
        'rate_limit': 18,
        'minute_limit': 37,
        'repeat_bonus': 0,
        'flood_base_mute_sec': 240.0,
        'multiplier': 1.25,
        'repost_limit': 6,
        'can_repost_mute': True,
    },
    'veteran': {
        'name': 'Ветеран',
        'min_posts': 100,
        'burst_limit': 12,
        'burst_window': 3.5,
        'rate_limit': 22,
        'minute_limit': 45,
        'repeat_bonus': 1,
        'flood_base_mute_sec': 120.0,
        'multiplier': 1.5,
        'repost_limit': 8,
        'can_repost_mute': True,
    },
    'oldfag': {
        'name': 'Олдфаг',
        'min_posts': 500,
        'burst_limit': 14,
        'burst_window': 3.3,
        'rate_limit': 26,
        'minute_limit': 52,
        'repeat_bonus': 2,
        'flood_base_mute_sec': 90.0,
        'multiplier': 1.75,
        'repost_limit': 10,
        'can_repost_mute': False,  # Total immunity from shadowmutes for reposts
    },
    'ancient': {
        'name': 'Древний Олдфаг',
        'min_posts': 2000,
        'burst_limit': 16,
        'burst_window': 3.0,
        'rate_limit': 30,
        'minute_limit': 60,
        'repeat_bonus': 2,
        'flood_base_mute_sec': 60.0,
        'multiplier': 2.0,
        'repost_limit': 12,
        'can_repost_mute': False,  # Total immunity from shadowmutes for reposts
    },
}

MEDIA_BURST_BONUS = 6
MEDIA_RATE_BONUS = 10
MEDIA_MINUTE_BONUS = 15

# Media Burst & Album Buffering
MEDIA_BURST_GAP = 3.5          # Max gap between images in rapid series/album
MEDIA_BURST_MAX_ITEMS = 10     # Max images in standard album buffer
MEDIA_GROUP_WINDOW = 30.0      # Sliding window for Telegram media_group_id
MAX_MEDIA_GROUP_ITEMS = 15     # Upper bound to prevent abusive infinite media_group loops

# Seen media groups to treat whole album as 1 post: {user_id: {media_group_id: {'first_ts': float, 'count': int}}}
_seen_media_groups: Dict[int, Dict[str, dict]] = defaultdict(dict)

# Rapid media burst buffer: {user_id: {'count': int, 'first_ts': float, 'last_ts': float}}
_user_media_burst_tracker: Dict[int, dict] = defaultdict(lambda: {'count': 0, 'first_ts': 0.0, 'last_ts': 0.0})

# Mute grace period tracker: {user_id: applied_ts}
_shadow_mute_applied_ts: Dict[int, float] = defaultdict(float)
MUTE_GRACE_PERIOD_SEC = 4.0

def record_shadow_mute_applied(user_id: int, now_ts: float | None = None):
    """Records the timestamp when shadow mute was applied to provide grace period for in-flight packets."""
    _shadow_mute_applied_ts[user_id] = float(now_ts) if now_ts is not None else time.time()

def is_in_mute_grace_period(user_id: int, now_ts: float | None = None) -> bool:
    """Returns True if message arrived during grace period of initial mute (preventing compounding)."""
    applied_ts = _shadow_mute_applied_ts.get(user_id, 0.0)
    if not applied_ts:
        return False
    now = float(now_ts) if now_ts is not None else time.time()
    return 0.0 <= (now - applied_ts) < MUTE_GRACE_PERIOD_SEC

def get_user_tier(posts_count: int = 0) -> dict:
    """Returns the tier configuration based on user's post count."""
    try:
        count = max(0, int(posts_count or 0))
    except (ValueError, TypeError):
        count = 0
    if count >= 2000:
        return USER_TIERS['ancient']
    if count >= 500:
        return USER_TIERS['oldfag']
    if count >= 100:
        return USER_TIERS['veteran']
    if count >= 20:
        return USER_TIERS['anon']
    return USER_TIERS['newbie']

def get_veteran_flood_multiplier(posts_count: int = 0, account_age_days: float = 0.0) -> float:
    """Calculates dynamic flood tolerance multiplier based on user's posts_count and longevity."""
    tier = get_user_tier(posts_count)
    mult = tier.get('multiplier', 1.0)
    if posts_count >= 100 and account_age_days >= 30.0:
        mult = min(2.0, mult + 0.1)
    return mult

def reset_media_burst_tracker(user_id: int | None = None):
    """Resets media burst tracking (for testing or shadowmute recovery)."""
    if user_id is not None:
        _user_media_burst_tracker.pop(user_id, None)
        _seen_media_groups.pop(user_id, None)
    else:
        _user_media_burst_tracker.clear()
        _seen_media_groups.clear()

def reset_short_gibberish_tracker(user_id: int | None = None):
    """Resets short gibberish flood tracker for a user or globally."""
    if user_id is not None:
        _short_gibberish_tracker.pop(user_id, None)
    else:
        _short_gibberish_tracker.clear()

def register_media_group(user_id: int, media_group_id: str, now_ts: float | None = None):
    """Explicitly registers an incoming media group for a user."""
    now = float(now_ts) if now_ts is not None else time.time()
    _seen_media_groups[user_id][str(media_group_id)] = {'first_ts': now, 'count': 1}

# Fast cache for user posts count: {user_id: (cached_at_ts, posts_count)}
_user_posts_count_cache: Dict[int, Tuple[float, int]] = {}
USER_POSTS_CACHE_TTL = 60.0

def set_cached_user_posts(user_id: int, posts_count: int):
    # Enforce upper bound on cache to prevent memory leaks from 50,000+ transient IDs
    if len(_user_posts_count_cache) > 5000:
        sorted_keys = sorted(_user_posts_count_cache.keys(), key=lambda k: _user_posts_count_cache[k][0])
        for k in sorted_keys[:1000]:
            _user_posts_count_cache.pop(k, None)
    _user_posts_count_cache[user_id] = (time.time(), int(posts_count or 0))

def get_cached_user_posts(user_id: int) -> int:
    now = time.time()
    cached = _user_posts_count_cache.get(user_id)
    if cached:
        ts, count = cached
        if now - ts < USER_POSTS_CACHE_TTL:
            return count
    # Fast read-only query on Users table if DB exists
    try:
        import os
        from common.config import DB_NAME
        if DB_NAME:
            db_path = str(DB_NAME)
            if os.path.exists(db_path):
                import sqlite3
                clean_path = db_path.replace("\\", "/")
                conn = sqlite3.connect(f"file:{clean_path}?mode=ro", uri=True, timeout=0.2)
                try:
                    cur = conn.execute("SELECT COALESCE(MAX(posts_count), 0) FROM Users WHERE user_id = ?", (user_id,))
                    row = cur.fetchone()
                    count = int(row[0]) if row and row[0] is not None else 0
                    _user_posts_count_cache[user_id] = (now, count)
                    return count
                finally:
                    conn.close()
    except Exception:
        pass
    return 0

async def get_user_total_posts(user_id: int) -> int:
    now = time.time()
    cached = _user_posts_count_cache.get(user_id)
    if cached and (now - cached[0] < USER_POSTS_CACHE_TTL):
        return cached[1]
    try:
        from common.db_pool import get_pool
        db = await get_pool()
        async with db.execute("SELECT COALESCE(MAX(posts_count), 0) FROM Users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            count = int(row[0]) if row and row[0] is not None else 0
            if count == 0:
                async with db.execute("SELECT COALESCE(SUM(posts_count), 0) FROM Users WHERE user_id = ?", (user_id,)) as cur2:
                    r2 = await cur2.fetchone()
                    count = int(r2[0]) if r2 and r2[0] is not None else 0
            _user_posts_count_cache[user_id] = (now, count)
            return count
    except Exception:
        return get_cached_user_posts(user_id)


# Fast cache for user account age: {user_id: (cached_at_ts, age_days)}
_user_account_age_cache: Dict[int, Tuple[float, float]] = {}
USER_ACCOUNT_AGE_CACHE_TTL = 300.0

def get_cached_user_account_age_days(user_id: int) -> float:
    """Returns user's account age in days based on Users.created_at or Posts.timestamp."""
    now = time.time()
    cached = _user_account_age_cache.get(user_id)
    if cached and (now - cached[0] < USER_ACCOUNT_AGE_CACHE_TTL):
        return cached[1]

    try:
        import os
        from common.config import DB_NAME
        if DB_NAME:
            db_path = str(DB_NAME)
            if os.path.exists(db_path):
                import sqlite3
                clean_path = db_path.replace("\\", "/")
                conn = sqlite3.connect(f"file:{clean_path}?mode=ro", uri=True, timeout=0.2)
                try:
                    cur = conn.execute("SELECT MIN(created_at) FROM Users WHERE user_id = ? AND created_at > 0", (user_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        created_at = float(row[0])
                        age_days = max(0.0, (now - created_at) / 86400.0)
                        _user_account_age_cache[user_id] = (now, age_days)
                        return age_days

                    cur = conn.execute("SELECT MIN(timestamp) FROM Posts WHERE author_id = ? AND timestamp > 0", (user_id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        first_post_ts = float(row[0])
                        age_days = max(0.0, (now - first_post_ts) / 86400.0)
                        _user_account_age_cache[user_id] = (now, age_days)
                        return age_days
                finally:
                    conn.close()
    except Exception:
        pass
    return 0.0


# Cross-board limit
CROSS_BOARD_WINDOW = 60.0       # 60 seconds

# Link & Ad Regex Patterns
RE_TG_INVITE = re.compile(r'(?:t\.me|telegram\.me)/(?:\+|joinchat/)[a-zA-Z0-9_\-]+', re.IGNORECASE)
RE_TG_PROMO = re.compile(r'(?<![a-zA-Z0-9])(?:t\.me|telegram\.me)/(?!(?:tgchan_archive|tgach_archive|c/\d+))[a-zA-Z0-9_]{5,}', re.IGNORECASE)

# Explicit scam brands (forbidden unconditionally, with strict word boundaries)
# Casino keywords (казино, casino, вулкан, вавада, 1win и т.д.) are strictly excluded
# per owner directive since the bot has its own integrated casino and games.
RE_EXPLICIT_SCAM_BRANDS = re.compile(
    r'(?<![a-zA-Zа-яА-ЯёЁ0-9\-_])(?:'
    r'1xbet'
    r')(?![a-zA-Zа-яА-ЯёЁ0-9\-_])',
    re.IGNORECASE | re.UNICODE
)

# Contextual ad/scam phrases that require promo hooks or untrusted account status to prevent false positives
# Casino mentions are allowed as regular conversation / bot gameplay.
RE_CONTEXTUAL_AD_PHRASES = re.compile(
    r'(?:'
    r'ставки\s*на\s*спорт|crypto\s*airdrop|раздача\s*крипт|'
    r'слив\s*онлифанс|вип\s*канал|подпишись\s*на\s*канал|легкий\s*заработок|интим\s*знакомства'
    r')',
    re.IGNORECASE | re.UNICODE
)

# Promo call-to-action hooks (links, channels, promo codes, referral terms)
RE_PROMO_HOOK = re.compile(
    r'(?:'
    r'https?://|t\.me/|@\w{4,}|промокод|бонус|фрибет|вывод|'
    r'переходи|подпишись|в\s+шапке|в\s+закрепе|по\s+ссылке|ссылка\s+в|реф(?:ка|ералка)?'
    r')',
    re.IGNORECASE | re.UNICODE
)

# Reply and quote header prefix cleaner (to prevent cascade mute infection on replies)
RE_REPLY_QUOTE_PREFIX = re.compile(
    r'(?:[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]*Пост\s*№?\d+[\s\S]*?\n\n|'
    r'^\s*(?:>|&gt;|>>\d+).*$\n?)',
    re.UNICODE | re.MULTILINE
)

# Backward compatibility alias
RE_AD_SCAM = re.compile(
    rf'(?:{RE_EXPLICIT_SCAM_BRANDS.pattern}|{RE_CONTEXTUAL_AD_PHRASES.pattern})',
    re.IGNORECASE | re.UNICODE
)
RE_URL = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+', re.IGNORECASE)
URL_WHITELIST = {
    "tgchan_archive",
    "tgach_archive",
    "t.me/tgchan_archive",
    "t.me/tgach_archive",
    "telegram.me/tgchan_archive",
    "telegram.me/tgach_archive",
    "https://t.me/tgchan_archive",
    "https://t.me/tgach_archive",
    "http://t.me/tgchan_archive",
    "http://t.me/tgach_archive",
    "@tgchan_archive",
    "@tgach_archive",
    "tgach.top",
    "https://tgach.top",
    "http://tgach.top",
    "2ch.hk",
    "https://2ch.hk",
    "http://2ch.hk",
    "2ch.life",
    "dvach.top",
    "https://dvach.top",
    "http://dvach.top",
}

# --- Anti-Dox & Phone Leak Patterns ---
DOX_MASK_REPLACEMENT = "[НОМЕР ТЕЛЕФОНА СКРЫТ / ANTI-DOX]"

RE_PHONE_RU_KZ = r'(?:(?:\+7|8)[\s\-\(\)\.\/]*(?:9|7)(?:[\s\-\(\)\.\/]*\d){9})'
RE_PHONE_UA = r'(?:(?:\+?380)(?:[\s\-\(\)\.\/]*\d){9})'
RE_PHONE_BY = r'(?:(?:\+?375)(?:[\s\-\(\)\.\/]*\d){9})'

RE_PHONE_DOX = re.compile(
    rf'(?<![\d+])(?:{RE_PHONE_RU_KZ}|{RE_PHONE_UA}|{RE_PHONE_BY})(?!\d)',
    re.IGNORECASE
)


RE_ZERO_WIDTH = re.compile(
    r'[\u200b-\u200f'  # Zero-width spaces, marks
    r'\u2028-\u202f'  # Line/paragraph separators, directional overrides (LRE, RLE, RLO, etc.)
    r'\u2060-\u206f'  # Word joiner, invisible operators
    r'\ufeff'          # Byte Order Mark (ZWNBSP)
    r'\u00ad'          # Soft hyphen
    r'\u034f'          # Combining grapheme joiner
    r'\u180e'          # Mongolian vowel separator
    r']+',
    re.UNICODE
)

HOMOGLYPH_LATIN_TO_CYRILLIC = str.maketrans({
    'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
    'A': 'а', 'B': 'в', 'C': 'с', 'E': 'е', 'H': 'н', 'K': 'к', 'M': 'м',
    'O': 'о', 'P': 'р', 'T': 'т', 'X': 'х', 'Y': 'у'
})

HOMOGLYPH_CYRILLIC_TO_LATIN = str.maketrans({
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x', 'у': 'y',
    'в': 'b', 'н': 'h', 'к': 'k', 'м': 'm', 'т': 't',
    'А': 'a', 'С': 'c', 'Е': 'e', 'О': 'o', 'Р': 'p', 'Х': 'x', 'У': 'y',
    'В': 'b', 'Н': 'h', 'К': 'k', 'М': 'm', 'Т': 't'
})

def canonicalize_spam_text(text: str, map_homoglyphs: bool = False) -> str:
    """
    Нормализует Unicode (NFKC), удаляет zero-width и RTL-override символы,
    предотвращая обход спам-фильтра и Anti-Dox детектора.
    """
    if not text or not isinstance(text, str):
        return ""
    norm = unicodedata.normalize('NFKC', text)
    norm = RE_ZERO_WIDTH.sub('', norm)
    norm = norm.lower()
    if map_homoglyphs:
        norm = norm.translate(HOMOGLYPH_LATIN_TO_CYRILLIC)
    return norm


def contains_phone_number(text: str) -> bool:
    """Returns True if the text contains a leaked mobile phone number."""
    if not text or not isinstance(text, str):
        return False
    if bool(RE_PHONE_DOX.search(text)):
        return True
    cleaned = canonicalize_spam_text(text)
    return bool(RE_PHONE_DOX.search(cleaned))


def extract_phone_numbers(text: str) -> List[str]:
    """Extracts all matched mobile phone numbers from text."""
    if not text or not isinstance(text, str):
        return []
    res = [match.group(0) for match in RE_PHONE_DOX.finditer(text)]
    if not res:
        cleaned = canonicalize_spam_text(text)
        res = [match.group(0) for match in RE_PHONE_DOX.finditer(cleaned)]
    return res


def mask_phone_numbers(text: str, replacement: str = DOX_MASK_REPLACEMENT) -> str:
    """Masks all mobile phone numbers in text with replacement label."""
    if not text or not isinstance(text, str):
        return text
    res = RE_PHONE_DOX.sub(replacement, text)
    cleaned = canonicalize_spam_text(text)
    if RE_PHONE_DOX.search(cleaned):
        for match in RE_PHONE_DOX.finditer(cleaned):
            leaked_raw = match.group(0)
            escaped_chars = [re.escape(c) for c in leaked_raw]
            loose_pattern = r'[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff\u00ad]*'.join(escaped_chars)
            try:
                res = re.sub(loose_pattern, replacement, res, flags=re.IGNORECASE)
            except Exception:
                pass
    return res


def check_dox_content(
    text: str,
    user_id: int = 0,
    board_id: str = "b",
    mask: bool = True
) -> Tuple[bool, str, List[str]]:
    """
    Checks text for doxing/phone number leaks.
    Returns: (is_dox_detected: bool, masked_or_original_text: str, list_of_phone_numbers: List[str]).
    """
    if not text or not isinstance(text, str):
        return False, text or "", []

    try:
        from bot_helpers import is_admin
        if user_id and is_admin(user_id, board_id):
            return False, text, []
    except Exception:
        pass

    phones = extract_phone_numbers(text)
    if not phones:
        return False, text, []

    masked_text = mask_phone_numbers(text) if mask else text
    logger.warning(
        f"🛡️ ANTI-DOX: Leaked mobile phone number detected from user {user_id} on /{board_id}/: {phones}"
    )
    return True, masked_text, phones


def check_phone_dox(user_id: int, board_id: str, text: str) -> Tuple[bool, str, str]:
    """
    Validation helper returning (is_dox: bool, masked_text: str, reason: str).
    """
    is_dox, masked, phones = check_dox_content(text, user_id=user_id, board_id=board_id, mask=True)
    if is_dox:
        reason = f"Слив мобильного номера деанона (Anti-Dox: {phones[0]})"
        return True, masked, reason
    return False, text, ""


# Legacy spam rules preserved for compatibility
SPAM_RULES = {
    # text: 18/15s — активная дискуссия в тредах норма, 10/15s было слишком жёстко
    # media_group fake_text обходится отдельной проверкой в handle_media_group_init
    'text': {'max_repeats': 5, 'min_length': 4, 'window_sec': 15, 'max_per_window': 18},
    'sticker': {'max_repeats': 3, 'max_per_window': 10, 'window_sec': 20},
    'animation': {'max_repeats': 3, 'max_per_window': 10, 'window_sec': 20},
    'photo': {'max_repeats': 4, 'max_per_window': 15, 'window_sec': 30},
    'video': {'max_repeats': 4, 'max_per_window': 15, 'window_sec': 30},
    'document': {'max_repeats': 4, 'max_per_window': 15, 'window_sec': 30},
    'media': {'max_repeats': 5, 'max_per_window': 10, 'window_sec': 30},
    # pseudo-type для медиагрупп — только flood-check, без rate-limit text-счётчика
    'media_group': {'max_repeats': 3, 'max_per_window': 6, 'window_sec': 30},
}
SPAM_LIMIT = 20
SPAM_WINDOW = 15

IMAGE_SPAM_LIMIT = 40
IMAGE_SPAM_WINDOW = 300


def set_spam_filter_words(board_id: str, words: set):
    if words:
        _spam_filter_words[board_id] = {str(w).strip().lower() for w in words if str(w).strip()}
    else:
        _spam_filter_words[board_id] = set()


def is_spam_filtered(text: str, board_id: str, user_id: int) -> bool:
    """Checks if a message contains a banned spam filter word, forbidden link/ad, or dox phone leak."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False
    except Exception:
        pass

    clean_canonical = canonicalize_spam_text(text)

    # Check phone leak
    if contains_phone_number(clean_canonical):
        return True

    # Check forbidden link / invite / promo / ad spam
    is_link_spam, _ = check_link_or_ad_spam(user_id, board_id, clean_canonical)
    if is_link_spam:
        return True

    banned_words = set(_spam_filter_words.get(board_id) or set())
    if 'ALL' in _spam_filter_words:
        banned_words.update(_spam_filter_words['ALL'])
    if not banned_words:
        return False

    for wl in sorted(URL_WHITELIST, key=len, reverse=True):
        clean_canonical = clean_canonical.replace(wl, "")

    clean_with_cyrillic = clean_canonical.translate(HOMOGLYPH_LATIN_TO_CYRILLIC)
    clean_with_latin = clean_canonical.translate(HOMOGLYPH_CYRILLIC_TO_LATIN)

    for word in banned_words:
        w = canonicalize_spam_text(str(word)).strip()
        if not w:
            continue
        w_cyr = w.translate(HOMOGLYPH_LATIN_TO_CYRILLIC)
        w_lat = w.translate(HOMOGLYPH_CYRILLIC_TO_LATIN)
        if (w in clean_canonical or w in clean_with_cyrillic or w in clean_with_latin or
            w_cyr in clean_with_cyrillic or w_lat in clean_with_latin):
            return True
    return False


def _content_fingerprint(
    content: str | None = None,
    msg_type: str = 'text',
    file_unique_id: str | None = None,
    file_id: str | None = None,
    media_hash: str | None = None
) -> str:
    """
    Generate a fingerprint for content deduplication and bayan detection.
    - file_unique_id: Telegram's globally persistent media identifier
    - media_hash: sha256 / phash of the media
    - file_id: fallback media identifier
    - text: normalized text hash (lowercase, whitespace collapsed)
    """
    if file_unique_id:
        return f"fuid:{file_unique_id}"
    if media_hash:
        return f"mhash:{media_hash}"
    if msg_type in ('photo', 'video', 'document', 'sticker', 'animation', 'audio', 'voice'):
        if file_id:
            return f"media:{file_id}"
        if isinstance(content, str) and content.strip():
            return f"media:{content.strip()}"
    if content:
        if isinstance(content, str):
            cleaned = canonicalize_spam_text(content)
            normalized = " ".join(cleaned.split())
            if len(normalized) < TEXT_BAYAN_MIN_LEN:
                return ""  # Ignore short trivial text & casual banter (immune to bayan bans)
            h = hashlib.sha256(normalized.encode('utf-8', errors='replace')).hexdigest()[:16]
            return f"text:{h}"
        elif isinstance(content, dict):
            f_uid = content.get('file_unique_id')
            if f_uid: return f"fuid:{f_uid}"
            f_id = content.get('file_id')
            if f_id: return f"media:{f_id}"
            t = content.get('text') or content.get('caption')
            if t:
                cleaned = canonicalize_spam_text(str(t))
                normalized = " ".join(cleaned.split())
                if len(normalized) >= TEXT_BAYAN_MIN_LEN:
                    h = hashlib.sha256(normalized.encode('utf-8', errors='replace')).hexdigest()[:16]
                    return f"text:{h}"
    return ""


def is_bayan(
    user_id: int,
    board_id: str,
    content: str | dict | None = None,
    msg_type: str = 'text',
    file_unique_id: str | None = None,
    file_id: str | None = None,
    media_hash: str | None = None,
    now_ts: float | None = None,
    media_group_id: str | None = None
) -> Tuple[bool, str]:
    """
    Checks whether the current message is a bayan (duplicate text, repeat media, hash match).
    Returns (is_bayan: bool, reason: str).
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, ""
    except Exception:
        pass

    now = now_ts or time.time()
    fp = _content_fingerprint(content, msg_type, file_unique_id, file_id, media_hash)
    if not fp:
        return False, ""

    # 1. Check if user recently posted this exact fingerprint
    u_tracker = _bayan_tracker.get(user_id)
    if u_tracker:
        for item in u_tracker:
            ts = item[0]
            prev_fp = item[1]
            prev_mg = item[3] if len(item) > 3 else None
            if media_group_id and prev_mg and prev_mg == str(media_group_id):
                continue
            if now - ts <= BAYAN_WINDOW_SEC and prev_fp == fp:
                return True, f"Повтор сообщения/медиа (fingerprint: {fp})"

        # 2. Check near-duplicate text similarity (Levenstein/diff >= 85%)
        if fp.startswith("text:") and isinstance(content, str) and len(content.strip()) >= 10:
            norm_cur = content.strip().lower()
            for item in u_tracker:
                ts = item[0]
                prev_fp = item[1]
                prev_raw = item[2] if len(item) > 2 else None
                if now - ts <= BAYAN_WINDOW_SEC and prev_fp.startswith("text:") and prev_raw:
                    norm_prev = str(prev_raw).strip().lower()
                    l1, l2 = len(norm_cur), len(norm_prev)
                    if max(l1, l2) > 0 and abs(l1 - l2) / max(l1, l2) <= 0.25:
                        if difflib.SequenceMatcher(None, norm_cur[:300], norm_prev[:300]).ratio() >= 0.85:
                            return True, "Схожий дубликат текста (схожесть >= 85%)"

    # 3. Check if media was already seen on board in recent history
    if fp.startswith(("fuid:", "mhash:", "media:", "fid:")):
        b_tracker = _board_recent_fingerprints[board_id]
        for ts, prev_fp in b_tracker:
            if now - ts <= 3600.0 and prev_fp == fp:
                return True, f"Медиа-баян на доске {board_id} (fingerprint: {fp})"

    return False, ""


def check_bayan(
    user_id: int,
    content: str | None = None,
    msg_type: str = 'text',
    file_unique_id: str | None = None,
    file_id: str | None = None,
    media_hash: str | None = None,
    board_id: str = 'b',
    now_ts: float | None = None,
    media_group_id: str | None = None
) -> Tuple[bool, int]:
    """
    Checks if a user is posting duplicate content (bayan).
    If >= 3 bayans occur within 3 minutes (180s), triggers auto-shadowmute.
    Returns (is_mute_triggered: bool, mute_duration_seconds: int).
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, 0
    except Exception:
        pass

    now = now_ts or time.time()
    fp = _content_fingerprint(content, msg_type, file_unique_id, file_id, media_hash)
    if not fp:
        return False, 0

    tracker = _bayan_tracker[user_id]

    # Prune old entries
    while tracker and now - tracker[0][0] > BAYAN_WINDOW_SEC:
        tracker.popleft()

    if len(_bayan_tracker) > 5000:
        for k in list(_bayan_tracker.keys())[:1000]:
            _bayan_tracker.pop(k, None)

    # Record current message: (timestamp, fingerprint, content, media_group_id)
    tracker.append((now, fp, content if isinstance(content, str) else None, str(media_group_id) if media_group_id else None))

    # Add to board recent fingerprints
    _board_recent_fingerprints[board_id].append((now, fp))

    # Check total matching bayans in the window (excluding items within same media group)
    bayan_count = sum(
        1 for item in tracker
        if item[1] == fp and not (media_group_id and len(item) > 3 and item[3] == str(media_group_id))
    )

    is_sticker = (msg_type == 'sticker')
    effective_threshold = BAYAN_STICKER_THRESHOLD if is_sticker else BAYAN_THRESHOLD
    effective_base_mute = BAYAN_STICKER_BASE_MUTE_SEC if is_sticker else BAYAN_BASE_MUTE_SEC

    if bayan_count >= effective_threshold:
        last_mute = _bayan_mute_last_ts[user_id]
        if last_mute and now - last_mute > BAYAN_RESET_SEC:
            _bayan_mute_count[user_id] = 0

        escalation = _bayan_mute_count[user_id]
        mute_seconds = int(min(MAX_BAYAN_MUTE_SEC, effective_base_mute * (2 ** escalation)))

        _bayan_mute_count[user_id] = escalation + 1
        _bayan_mute_last_ts[user_id] = now
        _bayan_tracker.pop(user_id, None)
        return True, mute_seconds

    return False, 0


def get_bayan_escalation_level(user_id: int) -> int:
    """Get the current bayan escalation level for a user."""
    return _bayan_mute_count.get(user_id, 0)


def check_flood(
    user_id: int,
    board_id: str,
    now_ts: float | None = None,
    record_history: bool = True,
    is_reply: bool = False,
    posts_count: int | None = None,
    is_media: bool = False,
    media_group_id: str | None = None
) -> Tuple[bool, str]:
    """
    Checks if a user is flooding requests (burst and minute limit).
    Supports veteran tier limits (posts_count discounts), media bonuses,
    media burst buffering, and deduplication for media groups/albums.
    Returns (is_flooding: bool, reason: str).
    Ghost / shadow posts (record_history=False) evaluate flood thresholds without appending to history.
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, ""
    except Exception:
        pass

    try:
        now = float(now_ts) if now_ts is not None else time.time()
    except Exception:
        now = time.time()

    # Periodic sanitation check (every 60s)
    global _last_auto_cleanup_ts
    if now - _last_auto_cleanup_ts > 60.0:
        _last_auto_cleanup_ts = now
        prune_stale_spam_filter_state(now_ts=now)

    # 1. Handle media groups (albums): subsequent files of the same album within window are NOT new flood messages
    if media_group_id:
        mg_str = str(media_group_id)
        mg_map = _seen_media_groups[user_id]
        # Prune expired entries
        expired = [
            mg for mg, entry in list(mg_map.items())
            if now - (entry['first_ts'] if isinstance(entry, dict) else (entry if isinstance(entry, (int, float)) else 0.0)) > MEDIA_GROUP_WINDOW
        ]
        for mg in expired:
            mg_map.pop(mg, None)

        mg_entry = mg_map.get(mg_str)
        if isinstance(mg_entry, dict):
            if mg_entry.get('count', 0) < MAX_MEDIA_GROUP_ITEMS:
                mg_entry['count'] += 1
                # Subsequent message in legitimate media group album -> bypass flood count cleanly!
                return False, ""
        elif isinstance(mg_entry, (int, float)):
            mg_map[mg_str] = {'first_ts': float(mg_entry), 'count': 2}
            return False, ""
        else:
            # First item in this media group
            _seen_media_groups[user_id][mg_str] = {'first_ts': now, 'count': 1}

    # 2. Media burst buffering: protects rapid image series / albums without media_group_id
    if is_media:
        burst = _user_media_burst_tracker[user_id]
        if burst['last_ts'] > 0.0 and (now - burst['last_ts'] <= MEDIA_BURST_GAP):
            burst['count'] += 1
            burst['last_ts'] = now
            # Resolve user tier for allowed burst size
            if posts_count is None:
                posts_count = get_cached_user_posts(user_id)
            tier = get_user_tier(posts_count)
            mult = tier.get('multiplier', 1.0)
            max_media_allowed = int(MEDIA_BURST_MAX_ITEMS * (1.8 if mult >= 1.75 else (1.2 if mult > 1.0 else 1.0)))
            if burst['count'] <= max_media_allowed:
                # Absorbed into media burst buffer!
                return False, ""
        else:
            burst['count'] = 1
            burst['first_ts'] = now
            burst['last_ts'] = now

    tracker = _user_request_timestamps[user_id]

    # Prune older than 60s
    while tracker:
        try:
            if now - float(tracker[0]) > MINUTE_FLOOD_WINDOW:
                tracker.popleft()
            else:
                break
        except Exception:
            tracker.popleft()

    # In case updates are queued/delayed from network recovery, ensure monotonic timestamps
    if tracker:
        try:
            if now < float(tracker[-1]):
                now = float(tracker[-1])
        except Exception:
            pass

    current_timestamps = [float(ts) for ts in tracker if isinstance(ts, (int, float))]
    current_timestamps.append(now)

    # Resolve tier & limits
    if posts_count is None:
        posts_count = get_cached_user_posts(user_id)
    tier = get_user_tier(posts_count)

    tier_burst = tier['burst_limit']
    tier_rate = tier['rate_limit']
    tier_minute = tier['minute_limit']

    # Apply media bonuses for media messages so albums/batches do not falsely trip flood
    if is_media:
        tier_burst += MEDIA_BURST_BONUS
        tier_rate += MEDIA_RATE_BONUS
        tier_minute += MEDIA_MINUTE_BONUS

    # 1. Burst flood: > burst_limit in burst_window
    if not is_media and not media_group_id:
        # Trust fair tier_burst directly without artificial min(tier_burst, 5) clamping
        burst_limit = tier_burst if not is_reply else max(tier_burst, 8)
        burst_window = tier.get('burst_window', 4.0 if not is_reply else 5.0)
    else:
        mult = tier.get('multiplier', 1.0)
        burst_limit = int(max(tier_burst, 8 * mult)) if is_reply else tier_burst
        burst_window = 10.0 if is_reply else tier.get('burst_window', BURST_FLOOD_WINDOW)
    burst_count = sum(1 for ts in current_timestamps if now - ts <= burst_window)
    if burst_count > burst_limit:
        if record_history:
            tracker.append(now)
        return True, f"Burst флуд: {burst_count} сообщений за {burst_window}с"

    # 2. Rate flood: > tier_rate in RATE_FLOOD_WINDOW
    rate_count = sum(1 for ts in current_timestamps if now - ts <= RATE_FLOOD_WINDOW)
    if rate_count > tier_rate:
        if record_history:
            tracker.append(now)
        return True, f"Частый постинг: {rate_count} сообщений за {RATE_FLOOD_WINDOW}с"

    # 3. Minute flood: > tier_minute in MINUTE_FLOOD_WINDOW
    if len(current_timestamps) > tier_minute:
        if record_history:
            tracker.append(now)
        return True, f"Минутный флуд: {len(current_timestamps)} сообщений за {MINUTE_FLOOD_WINDOW}с"

    if record_history:
        tracker.append(now)

    return False, ""


_top_active_users_cache: set[int] = set()
_top_active_users_cache_ts: float = 0.0

def get_top_active_monthly_users(ttl: float = 3600.0) -> set[int]:
    """
    Returns the user IDs of the top 15 most active users for the last 30 days.
    These users receive an indulgence against emergency anti-dox TG link filters.
    Uses read-only URI mode to prevent lock contention with WAL mode.
    """
    global _top_active_users_cache, _top_active_users_cache_ts
    now = time.time()
    if _top_active_users_cache and (now - _top_active_users_cache_ts) < ttl:
        return _top_active_users_cache
    try:
        from common.config import DB_NAME
        import sqlite3
        db_path = str(DB_NAME).replace("\\", "/")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
        c = conn.cursor()
        month_ago = now - (30 * 86400)
        c.execute("""
            SELECT author_id
            FROM Posts
            WHERE timestamp > ?
              AND author_id > 0
              AND is_shadow = 0
            GROUP BY author_id
            ORDER BY count(*) DESC
            LIMIT 15
        """, (month_ago,))
        _top_active_users_cache = {row[0] for row in c.fetchall()}
        _top_active_users_cache_ts = now
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching top active monthly users: {e}")
        if not _top_active_users_cache:
            _top_active_users_cache = set()
    return _top_active_users_cache


def check_link_or_ad_spam(user_id: int, board_id: str, text: str, now_ts: float | None = None, posts_count: int | None = None, account_age_days: float | None = None) -> Tuple[bool, str]:
    """
    Checks for link spam or doxing phone number leaks (Anti-Dox).
    Casino keywords are not flagged per owner directive (regular chat mentions must not cause bans).
    Returns (is_spam: bool, reason: str).
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, ""
    except Exception:
        pass

    if not text or not isinstance(text, str):
        return False, ""

    now = now_ts or time.time()
    clean_text = text

    # Remove whitelisted domains before evaluation (longest match first)
    for wl in sorted(URL_WHITELIST, key=len, reverse=True):
        clean_text = clean_text.replace(wl, "")

    # Phone number / doxing leaks (+79..., 89..., +380..., +375...)
    if contains_phone_number(clean_text):
        phones = extract_phone_numbers(clean_text)
        return True, f"Слив телефонного номера (Anti-Dox): {phones[0]}"

    # Permanent invite, promo, and ad/scam filter
    # URL_WHITELIST (tgchan_archive, tgach_archive, 2ch.hk, tgach.top, etc.) is strictly preserved
    p_count = posts_count if posts_count is not None else get_cached_user_posts(user_id)
    norm_text = canonicalize_spam_text(clean_text)
    cyr_homo = str.maketrans('тасеорхі', 'taceopxi')
    trans_text = norm_text.translate(cyr_homo)

    # Strip quote lines and Telegram reply headers for ad evaluations to prevent false-positives on replying to posts
    non_quote_text = RE_REPLY_QUOTE_PREFIX.sub('', clean_text).strip()
    non_quote_norm = canonicalize_spam_text(non_quote_text) if non_quote_text else ""
    non_quote_trans = non_quote_norm.translate(cyr_homo) if non_quote_norm else ""

    # 1. Telegram invite links (t.me/+..., joinchat, etc.) - forbidden for all users (no posts >= 50 immunity)
    target_texts = (clean_text, norm_text, trans_text)
    target_texts_inv = (non_quote_text, non_quote_norm, non_quote_trans) if non_quote_text else target_texts
    if any(RE_TG_INVITE.search(t) for t in target_texts_inv):
        return True, "Запрещенная инвайт-ссылка Telegram"

    # 2. Ad / Casino / Crypto / Scam keywords
    # 2a. Explicit casino / gambling / scam brands: unconditionally forbidden
    target_texts = (clean_text, norm_text, trans_text)
    if non_quote_text:
        target_texts_scam = (non_quote_text, non_quote_norm, non_quote_trans)
    else:
        target_texts_scam = target_texts

    if any(RE_EXPLICIT_SCAM_BRANDS.search(t) for t in target_texts_scam):
        return True, "Рекламный или скам-текст"

    # 2b. Contextual ad/scam phrases: require promo hook (link, @channel, promo code)
    # or untrusted brand new account status to prevent false positives in conversation/critique
    if any(RE_CONTEXTUAL_AD_PHRASES.search(t) for t in target_texts_scam):
        has_promo_hook = any(RE_PROMO_HOOK.search(t) for t in target_texts)
        if has_promo_hook:
            return True, "Рекламный или скам-текст"

        user_age = account_age_days if account_age_days is not None else get_cached_user_account_age_days(user_id)
        if p_count < 10 and user_age < 3.0 and len(clean_text.strip()) < 80:
            return True, "Рекламный или скам-текст"

    # 3. Telegram public/promo links (excluding whitelisted archives)
    # Requires confirmed veteran status (posts_count >= 50 or account older than 30 days)
    if RE_TG_PROMO.search(clean_text) or RE_TG_PROMO.search(norm_text) or RE_TG_PROMO.search(trans_text):
        is_veteran = (p_count >= 50)
        if not is_veteran:
            if account_age_days is not None:
                is_veteran = (account_age_days >= 30.0)
            else:
                db_age = get_cached_user_account_age_days(user_id)
                if db_age > 0.0:
                    is_veteran = (db_age >= 30.0)

        if not is_veteran:
            return True, "Реклама/промо Telegram-канала (требуется ветеранский статус)"

    return False, ""


# --- Repost / Channel Forward Anti-Spam ---

def is_repost_from_public(message: Any, bot_instance: Any = None) -> bool:
    """
    Detects if a Telegram message is a forward/repost from an external public channel or group/chat.
    Distinguishes public reposts from regular user forwards (forward_from / MessageOriginUser).
    Excludes messages forwarded from our own bot or archive channels.
    Supports aiogram 2.x, 3.x, and dictionary representations.
    """
    if message is None:
        return False

    try:
        from common.forward_utils import is_forwarded_from_bot
        if is_forwarded_from_bot(message, bot_instance):
            return False
    except Exception:
        pass

    # 1. Check forward_origin (aiogram 3.x / Telegram Bot API 7.0+)
    origin = getattr(message, 'forward_origin', None)
    if origin is None and isinstance(message, dict):
        origin = message.get('forward_origin')

    if origin is not None:
        origin_type = getattr(origin, 'type', None)
        if origin_type is None and isinstance(origin, dict):
            origin_type = origin.get('type')

        if origin_type in ('channel', 'chat'):
            return True
        if origin_type in ('user', 'hidden_user'):
            return False

        cls_name = type(origin).__name__
        if cls_name in ('MessageOriginChannel', 'MessageOriginChat'):
            return True
        if cls_name in ('MessageOriginUser', 'MessageOriginHiddenUser'):
            return False

        if getattr(origin, 'chat', None) or getattr(origin, 'sender_chat', None):
            return True
        if isinstance(origin, dict) and (origin.get('chat') or origin.get('sender_chat')):
            return True

    # 2. Check forward_from_chat (legacy / aiogram 2.x & 3.x)
    # In Telegram Bot API, forward_from_chat is present ONLY for channels or anonymous chat forwards
    f_chat = getattr(message, 'forward_from_chat', None)
    if f_chat is None and isinstance(message, dict):
        f_chat = message.get('forward_from_chat')

    if f_chat is not None:
        chat_type = getattr(f_chat, 'type', None)
        if chat_type is None and isinstance(f_chat, dict):
            chat_type = f_chat.get('type')
        if chat_type:
            if chat_type in ('channel', 'supergroup', 'group', 'chat'):
                return True
        else:
            return True

    return False


def get_repost_flood_response(index: int | None = None) -> str:
    """Returns a toxic Dvach response for exceeding the repost limit."""
    import random
    if index is not None and 0 <= index < len(REPOST_FLOOD_RESPONSES):
        return REPOST_FLOOD_RESPONSES[index]
    return random.choice(REPOST_FLOOD_RESPONSES)


def reset_repost_tracker(user_id: int | None = None, board_id: str | None = None) -> None:
    """Resets repost flood tracker for a user (optionally on specific board) or globally."""
    if user_id is not None:
        if board_id is not None:
            _user_repost_timestamps.pop((user_id, str(board_id)), None)
            _user_repost_timestamps.pop(user_id, None)
            _seen_repost_media_groups.pop((user_id, str(board_id)), None)
            _seen_repost_media_groups.pop(user_id, None)
        else:
            for k in list(_user_repost_timestamps.keys()):
                if k == user_id or (isinstance(k, tuple) and k[0] == user_id):
                    _user_repost_timestamps.pop(k, None)
            for k in list(_seen_repost_media_groups.keys()):
                if k == user_id or (isinstance(k, tuple) and k[0] == user_id):
                    _seen_repost_media_groups.pop(k, None)
    else:
        _user_repost_timestamps.clear()
        _seen_repost_media_groups.clear()


def check_repost_spam(
    user_id: int | Any,
    message: Any = None,
    board_id: str = "b",
    now_ts: float | None = None,
    record_history: bool = True,
    is_repost: bool | None = None,
    auto_apply_mute: bool = True,
    mute_duration_sec: float | None = None,
    media_group_id: str | None = None,
    bot_instance: Any = None,
    posts_count: int | None = None,
) -> Tuple[bool, str]:
    """
    Checks if an incoming message is a repost from a public channel/chat and enforces
    sliding 60 seconds repost limits tailored to user tier (from 4 for newbies up to 12 for ancients).
    Per-board tracking prevents cross-board rate-limit collisions.
    Supports media_group_id deduplication so 1 album counts as 1 repost.

    If limit is exceeded:
    1. Returns (True, toxic_repost_response).
    2. Spawns shadowmute only for aggressive/persistent spam or spambots.
       Oldfags/ancients have total immunity from shadowmutes.
       First minor infractions for anons are dropped with warning without shadowmutes.

    If within limit or message is not a repost:
    Returns (False, "").
    """
    # Defensive unwrapping if message passed as first argument
    if not isinstance(user_id, int):
        if message is None:
            message = user_id
            user_id = getattr(getattr(message, 'from_user', None), 'id', None)
            if user_id is None and isinstance(message, dict):
                user_id = (message.get('from') or {}).get('id') or message.get('user_id')
            if not isinstance(user_id, int):
                user_id = 0

    if media_group_id is None and message is not None:
        media_group_id = getattr(message, 'media_group_id', None)
        if media_group_id is None and isinstance(message, dict):
            media_group_id = message.get('media_group_id')

    if is_repost is None:
        is_repost = is_repost_from_public(message, bot_instance=bot_instance) if message is not None else False

    if not is_repost:
        return False, ""

    if str(board_id).lower() in REPOST_EXEMPT_BOARDS:
        return False, ""

    try:
        from bot_helpers import is_admin
        if user_id and is_admin(user_id, board_id):
            return False, ""
    except Exception:
        pass

    now = float(now_ts) if now_ts is not None else time.time()
    tracker_key = (user_id, str(board_id)) if (user_id and board_id) else user_id

    # Media group deduplication: subsequent items of the same album do not re-count
    if media_group_id:
        mg_str = str(media_group_id)
        user_mg_map = _seen_repost_media_groups[tracker_key]
        # Prune expired albums older than 60s
        expired = [k for k, v in list(user_mg_map.items()) if now - (v.get('first_ts', 0) if isinstance(v, dict) else 0) > REPOST_WINDOW_SEC]
        for k in expired:
            user_mg_map.pop(k, None)

        if mg_str in user_mg_map:
            entry = user_mg_map[mg_str]
            return entry.get('blocked', False), entry.get('response', "")

    tracker = _user_repost_timestamps[tracker_key]

    # Prune timestamps older than sliding window
    while tracker and (now - float(tracker[0]) > REPOST_WINDOW_SEC):
        tracker.popleft()

    # Monotonic safety
    if tracker and now < float(tracker[-1]):
        now = float(tracker[-1])

    # Resolve user tier for repost limits
    if posts_count is None and isinstance(user_id, int) and user_id > 0:
        posts_count = get_cached_user_posts(user_id)
    tier = get_user_tier(posts_count if posts_count is not None else 0)
    repost_limit = tier.get('repost_limit', REPOST_LIMIT_PER_MINUTE)
    can_mute = tier.get('can_repost_mute', True)

    if len(tracker) >= repost_limit:
        response = get_repost_flood_response()
        logger.warning(
            f"🚫 REPOST SPAM: User {user_id} exceeded repost limit ({len(tracker)}/{repost_limit} in {REPOST_WINDOW_SEC}s) on /{board_id}/"
        )
        if media_group_id:
            _seen_repost_media_groups[tracker_key][str(media_group_id)] = {
                'first_ts': now, 'blocked': True, 'response': response
            }

        # Record blocked attempts in tracker so persistent flood can be detected
        if record_history:
            tracker.append(now)

        # Mute policy:
        # - Oldfags/Ancients: total immunity from shadowmutes.
        # - Newbies (< 20 posts): auto-mute applies immediately (neutralizes spambots).
        # - Anons / Veterans: 1st and 2nd excess reposts are dropped + warned only;
        #   shadowmute applies only if user aggressively keeps spamming (>= repost_limit + 3 attempts).
        is_persistent = (len(tracker) >= repost_limit + 3) or (posts_count is not None and posts_count < 20)
        should_shadow_mute = auto_apply_mute and can_mute and is_persistent

        if should_shadow_mute and user_id:
            try:
                loop = asyncio.get_running_loop()
                from common.task_manager import spawn_task
                eff_mute_dur = mute_duration_sec if mute_duration_sec is not None else REPOST_FLOOD_MUTE_SEC
                spawn_task(
                    apply_shadow_mute(
                        user_id=user_id,
                        board_id=board_id,
                        duration_seconds=eff_mute_dur,
                        reason=f"Спам репостами из пабликов (>{repost_limit}/мин): {response}",
                        is_exponential=False
                    )
                )
            except RuntimeError:
                pass  # No running event loop (e.g. sync test)
            except Exception as e:
                logger.warning(f"Failed to spawn shadow mute task for repost spam (user {user_id}): {e}")
        return True, response

    if media_group_id:
        _seen_repost_media_groups[tracker_key][str(media_group_id)] = {
            'first_ts': now, 'blocked': False, 'response': ""
        }

    if record_history:
        tracker.append(now)

    return False, ""


async def check_repost_spam_async(
    user_id: int | Any,
    message: Any = None,
    board_id: str = "b",
    now_ts: float | None = None,
    record_history: bool = True,
    is_repost: bool | None = None,
    auto_apply_mute: bool = True,
    mute_duration_sec: float | None = None,
    media_group_id: str | None = None,
    bot_instance: Any = None,
    posts_count: int | None = None,
) -> Tuple[bool, str, float]:
    """
    Async version of check_repost_spam.
    If limit is exceeded and mute criteria met, applies shadowmute directly and awaits it.
    Returns: (is_blocked: bool, toxic_response: str, expires_at: float)
    """
    if str(board_id).lower() in REPOST_EXEMPT_BOARDS:
        return False, "", 0.0

    if posts_count is None and isinstance(user_id, int) and user_id > 0:
        posts_count = get_cached_user_posts(user_id)
    tier = get_user_tier(posts_count if posts_count is not None else 0)
    repost_limit = tier.get('repost_limit', REPOST_LIMIT_PER_MINUTE)
    can_mute = tier.get('can_repost_mute', True)

    tracker_key = (user_id, str(board_id)) if (user_id and board_id) else user_id
    tracker = _user_repost_timestamps[tracker_key]

    is_blocked, response = check_repost_spam(
        user_id=user_id,
        message=message,
        board_id=board_id,
        now_ts=now_ts,
        record_history=record_history,
        is_repost=is_repost,
        auto_apply_mute=False,  # Explicitly awaited below
        mute_duration_sec=mute_duration_sec,
        media_group_id=media_group_id,
        bot_instance=bot_instance,
        posts_count=posts_count,
    )
    expires_at = 0.0
    is_persistent = (len(tracker) >= repost_limit + 3) or (posts_count is not None and posts_count < 20)
    should_shadow_mute = is_blocked and auto_apply_mute and can_mute and is_persistent and isinstance(user_id, int) and user_id

    if should_shadow_mute:
        eff_mute_dur = mute_duration_sec if mute_duration_sec is not None else REPOST_FLOOD_MUTE_SEC
        try:
            expires_at = await apply_shadow_mute(
                user_id=user_id,
                board_id=board_id,
                duration_seconds=eff_mute_dur,
                reason=f"Спам репостами из пабликов (>{repost_limit}/мин): {response}",
                is_exponential=False
            )
        except Exception as e:
            logger.warning(f"Error applying shadow mute for repost spam (user {user_id}): {e}")
    return is_blocked, response, expires_at


def _check_repeats(
    user_id: int,
    b_data: dict,
    msg_info: tuple[str, str],
    rules: dict,
    violations: dict,
    posts_count: int | None = None,
    media_group_id: str | None = None
) -> bool:
    """Check if the user is repeatedly sending the same or highly similar messages."""
    try:
        from site_tgach.admin_config import ADMIN_IDS
        if user_id in ADMIN_IDS:
            return True
    except Exception:
        pass

    # Media group albums and media bursts are protected from repeat penalties
    if media_group_id:
        return True

    content, msg_type = msg_info
    if msg_type in ('photo', 'video', 'document', 'media', 'media_group'):
        burst = _user_media_burst_tracker.get(user_id)
        if burst and burst.get('count', 0) > 1:
            return True

    max_repeats = rules.get('max_repeats')
    if not max_repeats or not content:
        return True

    # Scale repeat tolerance for board veterans based on posts_count
    if posts_count is None:
        posts_count = get_cached_user_posts(user_id)
    tier = get_user_tier(posts_count)
    repeat_bonus = tier.get('repeat_bonus', 0)
    effective_max_repeats = max_repeats + repeat_bonus

    last_items_deque = None
    if msg_type == 'text':
        last_items_deque = b_data.setdefault('last_texts', defaultdict(deque))[user_id]
    elif msg_type == 'sticker':
        last_items_deque = b_data.setdefault('last_stickers', defaultdict(deque))[user_id]
    elif msg_type == 'animation':
        last_items_deque = b_data.setdefault('last_animations', defaultdict(deque))[user_id]
    elif msg_type == 'audio':
        last_items_deque = b_data.setdefault('last_audios', defaultdict(deque))[user_id]

    if last_items_deque is not None:
        now = time.time()
        while last_items_deque and (not isinstance(last_items_deque[0], tuple) or now - last_items_deque[0][0] > 30):
            if not isinstance(last_items_deque[0], tuple):
                last_items_deque.popleft()
            elif now - last_items_deque[0][0] > 30:
                last_items_deque.popleft()
            else:
                break

        last_items_deque.append((now, content))

        # Consecutive identical items check:
        # e.g., max_repeats = 3 allows up to 3 identical stickers/animations in a row; 4th is blocked.
        consecutive_limit = effective_max_repeats + 1
        if len(last_items_deque) >= consecutive_limit:
            tail = [item[1] for item in list(last_items_deque)[-consecutive_limit:]]
            if len(set(tail)) == 1:
                if msg_type != 'text' or len(str(tail[0]).strip()) >= rules.get('min_length', 4):
                    violations['level'] += 1
                    last_items_deque.clear()
                    return False
        elif len(last_items_deque) >= effective_max_repeats and msg_type == 'text':
            contents = [item[1] for item in list(last_items_deque)[-effective_max_repeats:]]
            def _fast_similar(s1: str, s2: str) -> bool:
                if s1 == s2: return True
                l1, l2 = len(s1), len(s2)
                if abs(l1 - l2) / max(l1, l2, 1) > 0.25: return False
                return difflib.SequenceMatcher(None, str(s1)[:400], str(s2)[:400]).ratio() > 0.85
            if all(_fast_similar(contents[0], c) for c in contents[1:]):
                violations['level'] += 1
                last_items_deque.clear()
                return False
    return True


def _check_cross_board_spam(
    user_id: int,
    board_id: str,
    content: str,
    msg_type: str,
    raw_content_type: str,
    now_ts: float | None = None,
    record_history: bool = True
) -> bool:
    """Check for cross-board spam returning False if detected."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return True
    except Exception:
        pass

    # Игнорировать короткие сообщения (< 15 символов, либо 1 слово/смайлики)
    if raw_content_type == 'text' or msg_type == 'text' or (isinstance(content, str) and not content.startswith(('AQAD', 'BAAC', 'AgAC', 'fuid:', 'media:', 'fid:'))):
        if isinstance(content, str):
            clean_text = content.strip()
            if len(clean_text) < 15 or len(clean_text.split()) <= 1:
                return True

    now = now_ts or time.time()
    user_cb = cross_board_spam_tracker[user_id]

    # Prune older than CROSS_BOARD_WINDOW
    while user_cb and now - user_cb[0][0] > CROSS_BOARD_WINDOW:
        user_cb.popleft()

    candidate_cb = list(user_cb)
    if not candidate_cb or candidate_cb[-1][1] != board_id:
        candidate_cb.append((now, board_id, content))
        if len(candidate_cb) >= 3:
            # Check the 3 most recent entries across boards (prevent bypass from older benign posts)
            recent_3 = candidate_cb[-3:]
            boards = {b for t, b, c in recent_3}
            if len(boards) >= 2 and recent_3[-1][0] - recent_3[0][0] <= CROSS_BOARD_WINDOW:
                contents = [c for t, b, c in recent_3]
                is_duplicate = False
                if raw_content_type == 'text' or (raw_content_type in ['photo', 'video', 'document'] and msg_type == 'text'):
                    def _fast_sim(s1, s2):
                        if not s1 or not s2: return False
                        if s1 == s2: return True
                        l1, l2 = len(s1), len(s2)
                        if abs(l1 - l2) / max(l1, l2, 1) > 0.25: return False
                        return difflib.SequenceMatcher(None, str(s1)[:400], str(s2)[:400]).ratio() > 0.85
                    if _fast_sim(contents[0], contents[1]) and _fast_sim(contents[1], contents[2]):
                        is_duplicate = True
                elif contents[0] == contents[1] == contents[2]:
                    is_duplicate = True

                if is_duplicate:
                    if record_history:
                        user_cb.clear()
                    return False

    if record_history and (not user_cb or user_cb[-1][1] != board_id):
        user_cb.append((now, board_id, content))

    return True

check_cross_board_spam = _check_cross_board_spam


def check_rate_limit(
    board_id: str,
    user_id: int,
    rules: dict,
    posts_count: int | None = None,
    media_group_id: str | None = None
) -> bool:
    """Sliding window implementation for rate limits with veteran scaling and media group protection."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return True
    except Exception:
        pass

    # Media group albums parts (after the first) do not exhaust rate limit
    if media_group_id:
        user_mg = _seen_media_groups.get(user_id, {})
        mg_entry = user_mg.get(str(media_group_id))
        if isinstance(mg_entry, dict) and mg_entry.get('count', 0) > 1:
            return True

    now_ts = time.time()
    tracker = _spam_trackers[board_id][user_id]

    # Prune old timestamps
    tracker[:] = [t for t in tracker if t > now_ts - rules['window_sec']]
    tracker.append(now_ts)

    if posts_count is None:
        posts_count = get_cached_user_posts(user_id)
    tier = get_user_tier(posts_count)
    mult = tier.get('multiplier', 1.0)
    effective_max = int(rules['max_per_window'] * mult)

    if len(tracker) >= effective_max:
        tracker.clear()
        return False
    return True


async def handle_shadow_mute_continuation(
    user_id: int,
    board_id: str,
    reason: str = "Постинг в шедоумуте",
    now_ts: float | None = None
) -> Tuple[bool, float]:
    """
    If user is already in shadow mute and continues posting,
    maintains the existing shadow mute without exponential doubling.
    Returns (is_muted: bool, expires_at: float).
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, 0.0
    except Exception:
        pass

    now = float(now_ts) if now_ts is not None else time.time()
    if is_user_in_memory_shadow_muted(user_id, board_id, now_ts=now):
        exp_ts = _in_memory_shadow_muted_users.get(user_id) or _in_memory_shadow_muted_users.get((user_id, board_id)) or (now + 1200.0)
        return True, exp_ts

    from common.database import get_shadow_mute_info
    info = await get_shadow_mute_info(user_id, board_id)
    if info['is_muted']:
        exp = info['expires_at'] or (now + 1200.0)
        set_in_memory_shadow_mute(user_id, board_id, exp)
        return True, exp
    return False, 0.0


async def apply_shadow_mute_multi_boards(
    user_id: int,
    board_ids: list[str] | set[str] | tuple[str, ...],
    duration_seconds: float = 1200.0,
    reason: str = ""
) -> float:
    """
    Applies shadow mute across multiple boards in a SINGLE batched executemany transaction.
    Eliminates database lock contention caused by looping individual queries across 28 boards.
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, 'ALL'):
            return 0.0
    except Exception:
        pass

    now_ts = time.time()

    # If already in memory with active mute: skip repeated DB writes
    if is_user_in_memory_shadow_muted(user_id, now_ts=now_ts):
        existing_exp = _in_memory_shadow_muted_users.get(user_id) or _in_memory_shadow_muted_users.get((user_id, 'ALL'))
        if existing_exp and existing_exp > now_ts:
            return existing_exp

    new_duration = float(duration_seconds or 1200.0)
    new_expires_at = now_ts + new_duration

    # 1. Update in-memory cache and volatile trackers immediately
    set_in_memory_shadow_mute(user_id, board_ids, new_expires_at)
    record_shadow_mute_applied(user_id, now_ts=now_ts)
    _user_media_burst_tracker.pop(user_id, None)
    _seen_media_groups.pop(user_id, None)
    reset_repost_tracker(user_id)
    reset_short_gibberish_tracker(user_id)
    cross_board_spam_tracker.pop(user_id, None)
    _user_request_timestamps.pop(user_id, None)

    # 2. Sync RAM board_data
    try:
        from shared_state import board_data
        exp_dt = datetime.fromtimestamp(new_expires_at, UTC)
        for b in board_ids:
            if b in board_data:
                board_data[b].setdefault('shadow_mutes', {})[user_id] = exp_dt
        board_data.setdefault('ALL', {}).setdefault('shadow_mutes', {})[user_id] = exp_dt
    except Exception:
        pass

    # 3. Single batched executemany in a single transaction
    target_boards = list(board_ids)
    if 'ALL' not in target_boards:
        target_boards.append('ALL')

    records = [
        (user_id, b, 'shadow', new_expires_at, reason or 'auto_spam')
        for b in target_boards
    ]

    try:
        from common.db_pool import get_pool, db_transaction
        db = await get_pool()
        async with db_transaction(db):
            try:
                await db.executemany(
                    """
                    INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at, thread_id, reason)
                    VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    records
                )
            except Exception as col_err:
                if "no column named reason" in str(col_err).lower():
                    try:
                        await db.execute("ALTER TABLE Mutes ADD COLUMN reason TEXT")
                        await db.executemany(
                            """
                            INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at, thread_id, reason)
                            VALUES (?, ?, ?, ?, NULL, ?)
                            """,
                            records
                        )
                    except Exception:
                        await db.executemany(
                            """
                            INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at, thread_id)
                            VALUES (?, ?, ?, ?, NULL)
                            """,
                            [(r[0], r[1], r[2], r[3]) for r in records]
                        )
                else:
                    raise col_err
    except Exception as e:
        logger.warning(f"Error in batched multi-board mute for user {user_id}: {e}")

    return new_expires_at

async def apply_shadow_mute(
    user_id: int,
    board_id: str | list[str] | set[str] | tuple[str, ...],
    duration_seconds: float = 1200.0,
    reason: str = "",
    is_exponential: bool = False
) -> float:
    """
    Applies shadow mute, clears user volatile trackers, and caches mute in memory.
    Supports batched multi-board writes (board_id='ALL' or list/set of boards) via a single executemany query.
    If user is already in memory shadow muted, drops without repeating DB writes.
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id if isinstance(board_id, str) else 'ALL'):
            return 0.0
    except Exception:
        pass

    now_ts = time.time()

    # Fast check: If user is already in-memory shadow muted, avoid repeating DB writes!
    b_str = board_id if isinstance(board_id, str) else None
    if is_user_in_memory_shadow_muted(user_id, b_str, now_ts=now_ts):
        existing_exp = _in_memory_shadow_muted_users.get(user_id) or (
            _in_memory_shadow_muted_users.get((user_id, b_str)) if b_str else None
        )
        if existing_exp and existing_exp > now_ts:
            return existing_exp

    # Check multi-board mute
    if board_id == 'ALL' or isinstance(board_id, (list, set, tuple)):
        try:
            from shared_state import BOARDS
            target_boards = list(BOARDS) if board_id == 'ALL' else list(board_id)
        except Exception:
            target_boards = list(board_id) if isinstance(board_id, (list, set, tuple)) else ['ALL']
        return await apply_shadow_mute_multi_boards(
            user_id=user_id,
            board_ids=target_boards,
            duration_seconds=duration_seconds,
            reason=reason
        )

    # Single board mute:
    record_shadow_mute_applied(user_id, now_ts=now_ts)
    _user_media_burst_tracker.pop(user_id, None)
    _seen_media_groups.pop(user_id, None)
    reset_repost_tracker(user_id, board_id)
    reset_short_gibberish_tracker(user_id)
    cross_board_spam_tracker.pop(user_id, None)
    if board_id in _spam_trackers:
        _spam_trackers[board_id].pop(user_id, None)
    try:
        _user_request_timestamps.pop(user_id, None)
        _user_request_timestamps.pop((user_id, board_id), None)
    except Exception:
        pass

    set_in_memory_shadow_mute(user_id, board_id, duration_seconds=duration_seconds)

    # Ensure ghost / shadow posts do not trigger exponential flood mute escalation
    if is_exponential:
        from common.database import get_shadow_mute_info
        info = await get_shadow_mute_info(user_id, board_id)
        if info.get('is_muted'):
            return info.get('expires_at') or (now_ts + duration_seconds)

    is_flood_reason = any(w in (reason or "").lower() for w in ("флуд", "flood", "burst", "постинг"))
    if is_exponential and is_flood_reason:
        is_exponential = False

    if is_exponential and is_in_mute_grace_period(user_id, now_ts=now_ts):
        is_exponential = False

    orig_fn = _orig_db_apply_shadow_mute or getattr(common.database, "apply_shadow_mute", None)
    if orig_fn and orig_fn is not apply_shadow_mute:
        exp_res = await orig_fn(
            user_id, board_id, duration_seconds=duration_seconds, reason=reason, is_exponential=is_exponential
        )
        if exp_res:
            set_in_memory_shadow_mute(user_id, board_id, exp_res)
        return exp_res
    return now_ts + duration_seconds


# Hook common.database.apply_shadow_mute
try:
    import common.database
    _orig_db_apply_shadow_mute = getattr(common.database, "apply_shadow_mute", None)
    if _orig_db_apply_shadow_mute:
        common.database.apply_shadow_mute = apply_shadow_mute
except Exception:
    _orig_db_apply_shadow_mute = None




def normalize_wall_text(text: str) -> str:
    """Normalizes text for Sybil & wall-of-text matching (NFKC, zero-width stripped, non-alphanumeric removed)."""
    if not text:
        return ""
    norm = unicodedata.normalize('NFKC', text)
    norm = RE_ZERO_WIDTH.sub('', norm).lower()
    return re.sub(r'[\W_]+', '', norm)


RE_BEGGAR_PHRASES = re.compile(
    r'(?:(?:нужна|прошу|ищу|помогите|сбор|скиньте|подайте|задонатьте)\s+.{1,100}?(?:на\s+еду|с\s+едой|на\s+хлеб|денег|рублей|рубл|копеечк|на\s+проживание|выжить|покушать|на\s+проезд)|'
    r'(?:помощь\s+с\s+едой|сбор\s+средств|непростой\s+период|тяжелый\s+период|буду\s+искренне\s+благодарен\s+любой\s+поддержк)|'
    r'(?:(?:nuzhna|proshu|pomogite|sbor|skinte|podate)\s+.{1,100}?(?:s\s+edoy|na\s+edu|na\s+khleb|deneg|rubley|vyzhit|pokushat))|'
    r'(?:pomoshch\s+s\s+edoy|sbor\s+sredstv|neprostoy\s+period|tyazhelyy\s+period|budu\s+iskrenne\s+blagodaren))'
)

RE_BEGGAR_DEST = re.compile(
    r'(?:@[a-zA-Z0-9_]{3,}|t\.me\/[a-zA-Z0-9_]{3,}|\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b|\b(?:0x[a-fA-F0-9]{40}|T[A-Za-z1-9]{33})\b)'
)


def check_beggar_phishing_spam(text: str) -> Tuple[bool, str]:
    """
    Детектор спам-попрошаек и финансового скама (@Waouty, просьбы денег/еды, криптокошельки).
    Устойчив к математическим курсивным шрифтам Unicode и транслиту.
    Не срабатывает на обычные просьбы о помощи в коде/музыке.
    """
    if not text or len(text.strip()) < 20:
        return False, ""

    norm = unicodedata.normalize('NFKC', text)
    norm = RE_ZERO_WIDTH.sub('', norm).lower()

    # Short-circuit check using precompiled regex
    if not RE_BEGGAR_PHRASES.search(norm):
        return False, ""

    # Financial destination / contact in beg context
    if RE_BEGGAR_DEST.search(norm):
        return True, "Спам-шаблон попрошайки / финансового сбора с контактом"

    return False, ""


def check_text_copro_flood(text: str) -> Tuple[bool, str]:
    """
    Детектор текстового копро-вайпа (5+ фекальных корней, либо 3+ корней капсом/повторами в одном посте).
    Обычное бытовое ругательство и обсуждение плохих игр/фильмов (1-3 разных слова в обычном регистре) не блокирует.
    """
    if not text or len(text.strip()) < 10:
        return False, ""
    norm = unicodedata.normalize('NFKC', text)
    norm = RE_ZERO_WIDTH.sub('', norm).lower()

    SAFE_NON_FECAL_PREFIXES = (
        'калори', 'календар', 'калибр', 'кальци', 'калий', 'кальмар',
        'калитк', 'калейдоскоп', 'кальян', 'каллиграф', 'кальк', 'калек',
        'калин', 'калорифер', 'каламбур', 'калош', 'калач', 'калган',
        'кальсон', 'калым', 'кальвадос', 'ккал', 'мегакал'
    )
    fecal_roots = ['понос', 'кал', 'калл', 'говн', 'гавн', 'дрист', 'срак', 'говнон', 'гавнон']
    pattern = r'\b(?:' + '|'.join(fecal_roots) + r')[а-яё]*\b'
    raw_matches = re.findall(pattern, norm)
    matches = [m for m in raw_matches if not any(m.startswith(safe) for safe in SAFE_NON_FECAL_PREFIXES)]

    # 1. 5+ фекальных корней в посте = безусловный копро-вайп
    if len(matches) >= 5:
        return True, f"Текстовый копро-вайп ({len(matches)} фекальных корней в посте)"

    # 2. 5+ корней требуют подтверждения агрессивного вайпа: повторы одного корня или КАПС
    if len(matches) >= 5:
        unique_matches = set(matches)
        if len(unique_matches) <= 1:
            return True, f"Текстовый копро-вайп (повторы фекальных корней: {len(matches)})"

        upper_matches = [
            m.group(0) for m in re.finditer(pattern, text, re.IGNORECASE)
            if m.group(0).isupper() and not any(m.group(0).lower().startswith(safe) for safe in SAFE_NON_FECAL_PREFIXES)
        ]
        if len(upper_matches) >= 5:
            return True, f"Текстовый копро-вайп (капс-вайп фекальными корнями: {len(upper_matches)})"

    return False, ""


def check_sybil_and_wall_of_text_raid(
    user_id: int,
    board_id: str,
    text: str,
    now_ts: float | None = None
) -> Tuple[bool, str, int]:
    """
    Детектор скоординированных сеток ботов (Sybil Raid) и веерного спама длинными пастами.
    - Короткие реплики (< 100 символов) полностью освобождены от проверки.
    - Сетевой дубль клиента (double-tap <= 3.0с) отбрасывается без наказания (0 секунд).
    - Дубль длинного текста от другого аккаунта за 30 минут = 24 часа мут (Sybil Raid).
    - Дубль на другую доску за 5 минут = 1 час мут (Cross-board blast).
    - 3-й повтор пасты одним юзером за 15 минут = 30 минут мут.
    """
    if not text or len(text.strip()) < WALL_OF_TEXT_MIN_LEN:
        return False, "", 0

    now = now_ts or time.time()
    norm_cur = normalize_wall_text(text)
    if len(norm_cur) < 70:
        return False, "", 0

    # Prune expired entries (> 30 mins)
    while _board_recent_wall_of_texts and (now - _board_recent_wall_of_texts[0][0] > SYBIL_RAID_WINDOW_SEC):
        _board_recent_wall_of_texts.popleft()

    user_repeat_count = 0
    for prev_ts, prev_uid, prev_bid, prev_norm, prev_raw in _board_recent_wall_of_texts:
        is_match = False
        if prev_norm == norm_cur:
            is_match = True
        elif abs(len(prev_norm) - len(norm_cur)) / max(len(prev_norm), len(norm_cur)) <= 0.15:
            if difflib.SequenceMatcher(None, norm_cur[:250], prev_norm[:250]).ratio() >= 0.85:
                is_match = True

        if is_match:
            # 1. Double-tap protection (same user, <= 3 seconds apart)
            if prev_uid == user_id and now - prev_ts <= 3.0:
                return True, "double_tap_drop", 0

            # 2. Sybil Raid (different user, same wall of text within 30 min)
            if prev_uid != user_id and now - prev_ts <= SYBIL_RAID_WINDOW_SEC:
                _board_recent_wall_of_texts.append((now, user_id, board_id, norm_cur, text[:60]))
                return True, f"Сетка ботов / Sybil Raid: дубль длинного текста от пользователя {prev_uid}", 86400

            # 3. Cross-board fast blast (same user, different board within 5 min)
            if prev_uid == user_id and prev_bid != board_id and now - prev_ts <= CROSS_BOARD_FAST_SEC:
                _board_recent_wall_of_texts.append((now, user_id, board_id, norm_cur, text[:60]))
                return True, f"Веерный спам длинной пастой по доскам (/{prev_bid}/ -> /{board_id}/)", 3600

            if prev_uid == user_id and now - prev_ts <= 900.0:
                user_repeat_count += 1

    if user_repeat_count >= 2:
        _board_recent_wall_of_texts.append((now, user_id, board_id, norm_cur, text[:60]))
        return True, "Повторный спам длинной пастой (3+ за 15 мин)", 1800

    _board_recent_wall_of_texts.append((now, user_id, board_id, norm_cur, text[:60]))
    return False, "", 0

def calculate_dynamic_spam_mute_duration(
    text: str,
    count: int,
    window: float,
    posts_count: int | None = None,
    user_id: int | None = None
) -> int:
    """
    Calculates dynamic shadow mute duration based on text length, message frequency, and user tier:
    - length_factor:
        <= 10 chars: 3.0 (ultra-short keysmash)
        11..25 chars: 2.0
        26..60 chars: 1.2
        > 60 chars: 1.0
    - frequency_factor:
        velocity = count / max(window, 0.5)
        >= 2.0 msg/s: 2.5 (macro/script)
        >= 1.0 msg/s: 1.8
        < 1.0 msg/s: 1.0
    - base_sec:
        600s for veterans/oldfags (posts_count >= 100)
        1200s for newbies/anons
    - duration = int(base_sec * length_factor * frequency_factor), capped at 86400s (24h).
    """
    cleaned = canonicalize_spam_text(text).strip() if text and isinstance(text, str) else ""
    text_len = len(cleaned)
    if text_len <= 10:
        length_factor = 3.0
    elif text_len <= 25:
        length_factor = 2.0
    elif text_len <= 60:
        length_factor = 1.2
    else:
        length_factor = 1.0

    eff_window = max(float(window or 0.0), 0.5)
    velocity = float(count) / eff_window
    if velocity >= 2.0:
        frequency_factor = 2.5
    elif velocity >= 1.0:
        frequency_factor = 1.8
    else:
        frequency_factor = 1.0

    if posts_count is None and user_id is not None:
        posts_count = get_cached_user_posts(user_id)
    base_sec = 600.0 if (posts_count or 0) >= 100 else 1200.0

    duration = int(base_sec * length_factor * frequency_factor)
    return min(duration, 86400)


VOWELS = set("аеёиоуыэюяaeiouy")
CONSONANTS = set("бвгджзйклмнпрстфхцчшщbcdfghjklmnpqrstvwxz")

ALLOWED_NO_VOWEL_WORDS = {
    "спс", "ппц", "спб", "мск", "чзх", "нз", "кст", "крч", "пнх", "дтп",
    "смс", "чп", "ввп", "кгб", "фсб", "мвд", "блять", "хз", "мб", "ок",
    "в", "с", "к", "о", "у", "я", "и", "а", "не", "но", "он", "оч", "до",
    "из", "за", "по", "со", "ко", "во", "же", "ли", "бы", "то", "ну",
    "мда", "хд", "xd", "втф",
    "brb", "btw", "thx", "pls", "wtf", "idk", "tbh", "ngl"
}

VALID_CONSONANT_CLUSTERS = {
    "встр", "вспл", "взгл", "вскр", "нстр", "рств", "нтств", "ндств", "пльс"
}

LAUGHTER_WORDS = {
    "ха", "хах", "хаха", "хахах", "хахаха", "хахахах", "хахахаха",
    "аха", "ахах", "ахаха", "ахахах", "ахахаха",
    "хе", "хех", "хехе", "хехех", "хы", "хых", "хыхы", "кек", "лол",
    "пха", "пхах", "пхаха", "пхахах", "пхахаха",
    "бгг", "бггг", "бгггг"
}

KEYBOARD_WALKS = [
    "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "йцукенгшщзхъ", "фывапролджэ", "фывпр", "фывпрлджэ",
    "ячсмитьбю", "qazwsxedc", "poiuytrewq", "lkjhgfdsa", "mnbvcxz",
    "ъхзщшгнекуцй", "эждлорпавыф", "юбьтимсчя"
]

_VOWELS_RE_PATTERN = r'[аеёиоуыэюяaeiouy]'
# Disjoint deterministic non-backtracking laughter regex: zero ReDoS risk (< 0.05ms)
RE_LAUGH_DET = re.compile(
    rf'^[пpbбgг]?{_VOWELS_RE_PATTERN}*(?:[хxh]+{_VOWELS_RE_PATTERN}+)*[хxh]*$',
    re.IGNORECASE
)

def is_laughter_or_slang_token(token: str) -> bool:
    """Recognizes laughter patterns, elongated laughs, and valid slang."""
    t = token.lower()
    if t in LAUGHTER_WORDS or t in ALLOWED_NO_VOWEL_WORDS:
        return True
    # Laugh patterns with repetition: 'хддд', 'xd', 'xddd'
    if re.fullmatch(r'^[хx]+[дd]+$', t):
        return True
    # Elongated laughs: 'лоооол', 'лооооол'
    if re.fullmatch(r'^л+[оo]+л+$', t):
        return True
    # Elongated 'кеееек'
    if re.fullmatch(r'^к+[еe]+к+$', t):
        return True
    # Russian chuckle 'ыыы', 'ыыыы', 'ыыыыы'
    if re.fullmatch(r'^ы+$', t):
        return True
    # Elongated 'роофл'
    if re.fullmatch(r'^р+[оo]+ф+л+$', t):
        return True
    # Russian chuckle 'бгг', 'бггг'
    if re.fullmatch(r'^б+[гg]+$', t):
        return True
    # Laugh expressions with 'х'/'x'/'h' and vowels: 'ахахах', 'пхаха', 'хахахааа', 'хехехе', 'хыхыхы'
    # Deterministic O(N) evaluation with disjoint transitions (< 0.05ms, zero backtracking / ReDoS)
    if len(t) >= 2 and ('х' in t or 'x' in t or 'h' in t) and len(t) <= 1000:
        if RE_LAUGH_DET.fullmatch(t):
            return True
    # Humming / contemplation: 'ммм', 'мммм', 'ммммм', 'mmm', 'mmmm'
    if re.fullmatch(r'^[мm]+$', t):
        return True
    # Howling / sorrow / amazement: 'ууу', 'уууу', 'ууууу', 'uuu', 'uuuu'
    if re.fullmatch(r'^[уu]+$', t):
        return True
    # Wonder / ooh: 'ооо', 'оооо', 'ооооо', 'ooo', 'oooo'
    if re.fullmatch(r'^[оo]+$', t):
        return True
    # Dots / ellipsis: '....', '.....'
    if re.fullmatch(r'^\.+$|', t):
        return True
    # De-elongate repeated vowels: e.g. 'даааа' -> 'да', 'неееет' -> 'нет', 'мдааа' -> 'мда'
    collapsed = re.sub(r'([аеёиоуыэюяaeiouyмm])\1{2,}', r'\1', t)
    if collapsed in ALLOWED_NO_VOWEL_WORDS or collapsed in LAUGHTER_WORDS:
        return True
    if collapsed in {"да", "нет", "мда", "ура", "плиз", "спасибо", "привет", "ладно", "жиза", "база", "кринж"}:
        return True
    return False

def is_actual_keysmash_or_gibberish(text: str, posts_count: int | None = None) -> bool:
    """
    Detects true keysmash, home-row smashes, or consonant gibberish.
    Returns False for legitimate human conversation, common slang, laughing, or valid words.
    Users with posts_count >= 100 are exempt from hard keysmash detection.
    """
    if posts_count is not None and posts_count >= 100:
        return False

    if not text or not isinstance(text, str):
        return False

    cleaned = text.strip()
    if not cleaned:
        return False

    cleaned_lower = cleaned.lower()
    if re.fullmatch(r'^\.+$|^\.{2,}$', cleaned_lower):
        return False

    # If it's standard laughter or recognized slang across the entire input
    if is_laughter_or_slang_token(cleaned_lower):
        return False

    # Extract alphanumeric tokens
    tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9]+', cleaned_lower)

    # If all tokens are laughter or slang, it's NOT keysmash
    if tokens and all(is_laughter_or_slang_token(tok) for tok in tokens):
        return False

    # 1. Check for single character repeated >= 4 times (e.g. 'aaaa', 'фффф', '))))', '1111')
    if re.search(r'(.)\1{3,}', cleaned_lower):
        # Allow laughter / elongated tokens (e.g. 'лоооол', 'ыыыы', 'даааа', 'неееет', 'хддд')
        if not tokens:
            return True
        # If any token is pure single-character repeat (like 'aaaa', 'фффф', '1111') and not laughter
        has_abusive_repeat = False
        for tok in tokens:
            if is_laughter_or_slang_token(tok):
                continue
            if re.search(r'(.)\1{3,}', tok):
                has_abusive_repeat = True
                break
        if has_abusive_repeat:
            return True

    # If non-alphanumeric only, e.g. repeated symbols like '=-=-=-'
    if not tokens:
        if len(cleaned_lower) >= 4 and len(set(cleaned_lower)) <= 2:
            return True
        return False

    for token in tokens:
        if is_laughter_or_slang_token(token):
            continue
        # Pure numeric tokens (years, post numbers, counters, e.g. 123, 2026, 12345) are never keysmash
        if token.isdigit():
            continue

        token_len = len(token)

        # Check full repetition: 'asdasd', 'fghfgh', 'ываыва', 'qwerqwer'
        # Whitelist conversational affirmations and short words ('да', 'нет', 'ой', 'ай', 'ну', 'то')
        match_rep = re.match(r'^(.{2,5})\1+$', token)
        if match_rep:
            unit = match_rep.group(1)
            if unit not in ("ха", "хе", "хы", "ах", "ох", "хо", "да", "нет", "ой", "ай", "ну", "па", "то"):
                return True

        # Check keyboard walks (e.g. 'asdfgh', 'фывпр', 'йцукен', 'zxcvb')
        if token_len >= 4:
            for walk in KEYBOARD_WALKS:
                if len(walk) >= 4:
                    for i in range(len(walk) - 3):
                        sub = walk[i:i+4]
                        if sub in token:
                            return True

        token_vowels = [c for c in token if c in VOWELS]
        token_consonants = [c for c in token if c in CONSONANTS]

        # Consonant keysmash rules apply ONLY when the token actually contains letters/consonants
        if token_consonants:
            # Rule: If token has consonants, length > 3 and has NO vowels -> KEYSMASH!
            if token_len > 3 and not token_vowels:
                return True

            # Rule: If token length is 3 and has NO vowels and not in allowed abbreviations -> KEYSMASH!
            if token_len == 3 and not token_vowels and token not in ALLOWED_NO_VOWEL_WORDS:
                return True

        # Rule: Check clusters of >= 4 consonants in a row without vowels
        consec_consonants = re.findall(r'[бвгджзйклмнпрстфхцчшщbcdfghjklmnpqrstvwxz]{4,}', token)
        for cluster in consec_consonants:
            if len(cluster) >= 5 and cluster not in VALID_CONSONANT_CLUSTERS:
                return True
            if len(cluster) == 4:
                if cluster not in VALID_CONSONANT_CLUSTERS:
                    return True
                if not token_vowels:
                    return True

    # Check overall phrase vowel ratio for phrases with >= 2 words
    all_letters = [c for c in cleaned_lower if c.isalpha()]
    if len(all_letters) >= 5:
        all_vowels = [c for c in all_letters if c in VOWELS]
        ratio = len(all_vowels) / len(all_letters)
        if ratio < 0.15 and len(tokens) >= 2:
            return True

    return False


STOP_WORDS_WINDOW = 180.0
STOP_WORDS_TRIGGER_COUNT = 3  # > 2 messages with stop-words in sliding window
STOP_WORDS_MUTE_DURATION = 3600.0  # 1 hour (3600s)

_stop_words_violation_tracker: Dict[int, deque] = defaultdict(deque)

def reset_stop_words_tracker(user_id: int | None = None) -> None:
    """Resets stop-words violation tracker for a user or globally."""
    if user_id is not None:
        _stop_words_violation_tracker.pop(user_id, None)
    else:
        _stop_words_violation_tracker.clear()

def check_stop_words_violation(
    user_id: int,
    board_id: str,
    text: str,
    now_ts: float | None = None
) -> Tuple[bool, str, int]:
    """
    Tracks messages containing stop words from _spam_filter_words.
    If a user sends > 2 messages containing stop words within a sliding 180s window,
    triggers a 1-hour (3600s) shadowmute.
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, "", 0
    except Exception:
        pass

    if not is_spam_filtered(text, board_id, user_id):
        return False, "", 0

    now = float(now_ts) if now_ts is not None else time.time()
    tracker = _stop_words_violation_tracker[user_id]
    while tracker and (now - tracker[0] > STOP_WORDS_WINDOW):
        tracker.popleft()

    tracker.append(now)
    if len(tracker) >= STOP_WORDS_TRIGGER_COUNT:
        reason = f"Спам запрещенными словами из стоп-листа ({len(tracker)} сообщений за {int(STOP_WORDS_WINDOW)}с)"
        tracker.clear()
        return True, reason, int(STOP_WORDS_MUTE_DURATION)

    return False, "", 0


def check_short_gibberish_flood(
    user_id: int,
    text: str,
    now_ts: float | None = None,
    posts_count: int | None = None
) -> Tuple[bool, str, int]:
    """
    Detects macro flood with short random gibberish / keysmash in sliding windows:
    - Text length after canonicalization <= 25 chars.
    - If text is NOT actual keysmash / gibberish, returns False immediately!
    - Dynamic post trust scaling:
      * oldfags (posts_count >= 10000): fast limit raised to 12 msgs / 5s
      * regular / veteran / oldfag (posts_count >= 500): fast limit raised to 8 msgs / 5s
      * newbies / unverified: fast limit remains 3 msgs / 5s
    - Shadowmute duration dynamically scaled via calculate_dynamic_spam_mute_duration.
    Returns (is_flood: bool, reason: str, mute_duration_seconds: int).
    """
    if not user_id or not text or not isinstance(text, str):
        return False, "", 0

    try:
        from site_tgach.admin_config import ADMIN_IDS
        if user_id in ADMIN_IDS:
            return False, "", 0
    except Exception:
        pass

    cleaned = canonicalize_spam_text(text).strip()
    if not cleaned or len(cleaned) > SHORT_GIBBERISH_MAX_LEN:
        return False, "", 0

    # Resolve post count trust scaling
    if posts_count is None and user_id is not None:
        posts_count = get_cached_user_posts(user_id)
    p_count = posts_count or 0

    # Veterans with >= 100 posts are exempt from hard keysmash checks
    if p_count >= 100:
        return False, "", 0

    # REAL KEYSMASH / GIBBERISH CHECK: If normal text, do NOT trigger!
    if not is_actual_keysmash_or_gibberish(cleaned, posts_count=p_count):
        return False, "", 0

    now = float(now_ts) if now_ts is not None else time.time()
    tracker = _short_gibberish_tracker[user_id]

    if p_count >= 10000:
        fast_limit = 12
        slow_limit = 16
        fast_window = 5.0
        slow_window = 10.0
    elif p_count >= 500:
        fast_limit = 8
        slow_limit = 12
        fast_window = 5.0
        slow_window = 10.0
    else:
        fast_limit = SHORT_GIBBERISH_FAST_LIMIT
        slow_limit = SHORT_GIBBERISH_SLOW_LIMIT
        fast_window = SHORT_GIBBERISH_FAST_WINDOW
        slow_window = SHORT_GIBBERISH_SLOW_WINDOW

    # Prune timestamps older than slow_window
    while tracker and (now - tracker[0] > slow_window):
        tracker.popleft()

    if len(_short_gibberish_tracker) > 5000:
        for k in list(_short_gibberish_tracker.keys())[:1000]:
            _short_gibberish_tracker.pop(k, None)

    tracker.append(now)

    matching_fast = [ts for ts in tracker if now - ts <= fast_window]
    matching_slow = list(tracker)

    count_fast = len(matching_fast)
    count_slow = len(matching_slow)

    if count_fast >= fast_limit:
        time_span = now - matching_fast[0] if len(matching_fast) > 1 else fast_window
        mute_sec = calculate_dynamic_spam_mute_duration(
            text=cleaned,
            count=count_fast,
            window=time_span,
            posts_count=posts_count,
            user_id=user_id
        )
        reason = f"Спам-флуд короткой рандомной херней/keysmash ({count_fast} за {fast_window}с)"
        _short_gibberish_tracker.pop(user_id, None)
        return True, reason, mute_sec
    elif count_slow >= slow_limit:
        time_span = now - matching_slow[0] if len(matching_slow) > 1 else slow_window
        mute_sec = calculate_dynamic_spam_mute_duration(
            text=cleaned,
            count=count_slow,
            window=time_span,
            posts_count=posts_count,
            user_id=user_id
        )
        reason = f"Спам-флуд короткой рандомной херней/keysmash ({count_slow} за {slow_window}с)"
        _short_gibberish_tracker.pop(user_id, None)
        return True, reason, mute_sec

    return False, "", 0


async def evaluate_message_for_autoshadowmute(
    user_id: int,
    board_id: str,
    content: str | dict | None,
    msg_type: str,
    raw_content_type: str,
    file_unique_id: str | None = None,
    file_id: str | None = None,
    media_hash: str | None = None,
    now_ts: float | None = None,
    is_reply: bool = False,
    posts_count: int | None = None,
    media_group_id: str | None = None,
) -> Tuple[bool, str, float]:
    """
    Comprehensive evaluation of an incoming message for auto-shadowmute:
    1. Check if user is already shadowmuted -> maintain existing mute (no compounding)
    2. Check for Flood (burst / minute)
    3. Check for Link / Ad / Scam spam
    4. Check for Cross-board spam
    5. Check for Bayans (>= 3 duplicates in 3 minutes)
    Returns: (should_mute: bool, reason: str, mute_duration_seconds: float)
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False, "", 0.0
    except Exception:
        pass

    now = now_ts or time.time()

    # Fast in-memory check FIRST (< 0.1ms, zero DB, zero locks)
    if is_user_in_memory_shadow_muted(user_id, board_id, now_ts=now):
        exp_ts = _in_memory_shadow_muted_users.get(user_id) or _in_memory_shadow_muted_users.get((user_id, board_id)) or (now + 1200.0)
        return True, "Уже в теневом муте", exp_ts

    # If user is already shadow-muted, maintain existing mute without extending duration
    from common.database import is_shadow_muted, get_shadow_mute_info
    if await is_shadow_muted(user_id, board_id):
        info = await get_shadow_mute_info(user_id, board_id)
        exp_ts = info.get('expires_at') or (now + 1200.0)
        set_in_memory_shadow_mute(user_id, board_id, exp_ts)
        return True, "Уже в теневом муте", exp_ts
    text_content = content if isinstance(content, str) else (content.get('text') or content.get('caption') if isinstance(content, dict) else None)

    if not media_group_id and isinstance(content, dict):
        media_group_id = content.get('media_group_id')

    if posts_count is None:
        posts_count = await get_user_total_posts(user_id)
    is_media = (
        raw_content_type in ('photo', 'video', 'animation', 'document', 'audio', 'voice', 'video_note')
        or msg_type in ('photo', 'video', 'animation', 'document', 'audio', 'voice', 'video_note')
        or bool(file_unique_id)
        or bool(file_id)
        or bool(media_hash)
        or bool(media_group_id)
    )

    # 1. Flood check
    is_flood, flood_reason = check_flood(
        user_id, board_id, now_ts=now, is_reply=is_reply,
        posts_count=posts_count, is_media=is_media, media_group_id=media_group_id
    )
    if is_flood:
        from common.database import apply_shadow_mute
        tier = get_user_tier(posts_count or 0)
        base_mute = tier.get('flood_base_mute_sec', FLOOD_BASE_MUTE_SEC)
        if not is_media and not media_group_id and text_content and "burst" in flood_reason.lower():
            m_burst = re.search(r'Burst флуд:\s*(\d+)\s*сообщений\s*за\s*([\d\.]+)с', flood_reason)
            b_cnt = int(m_burst.group(1)) if m_burst else 6
            b_win = float(m_burst.group(2)) if m_burst else 4.0
            base_mute = float(calculate_dynamic_spam_mute_duration(
                text=text_content, count=b_cnt, window=b_win, posts_count=posts_count, user_id=user_id
            ))
        logger.warning(
            f"🚫 [SPAM_FILTER_TRIGGER: FLOOD] user={user_id} board={board_id} posts={posts_count} "
            f"tier={tier.get('name')} reason='{flood_reason}' duration={base_mute}s"
        )
        expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=base_mute, reason=flood_reason, is_exponential=False)
        return True, flood_reason, expires_at

    # 1.1. Short gibberish / keysmash macro flood check
    if text_content and not is_media and not media_group_id:
        is_gib, gib_reason, gib_mute_sec = check_short_gibberish_flood(
            user_id=user_id, text=text_content, now_ts=now, posts_count=posts_count
        )
        if is_gib:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: SHORT_GIBBERISH_FLOOD] user={user_id} board={board_id} posts={posts_count} "
                f"reason='{gib_reason}' duration={gib_mute_sec}s"
            )
            expires_at = await apply_shadow_mute(
                user_id, board_id, duration_seconds=float(gib_mute_sec), reason=gib_reason, is_exponential=False
            )
            return True, gib_reason, expires_at

    # 2. Link / Ad / Scam spam check
    if text_content:
        is_link_spam, link_reason = check_link_or_ad_spam(user_id, board_id, text_content, now_ts=now, posts_count=posts_count)
        if is_link_spam:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: LINK_OR_AD] user={user_id} board={board_id} reason='{link_reason}' duration={BAYAN_BASE_MUTE_SEC}s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=BAYAN_BASE_MUTE_SEC, reason=link_reason, is_exponential=False)
            return True, link_reason, expires_at

    # 2.1. Beggar & Phishing Scam Template Check
    if text_content:
        is_beggar, beggar_reason = check_beggar_phishing_spam(text_content)
        if is_beggar:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: BEGGAR_SCAM] user={user_id} board={board_id} reason='{beggar_reason}' duration=86400s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=86400.0, reason=beggar_reason, is_exponential=False)
            return True, beggar_reason, expires_at

    # 2.2. Stop-words consecutive spam check (>2 messages with stop words in 180s -> 1h shadowmute)
    if text_content:
        is_sw_flood, sw_reason, sw_mute_sec = check_stop_words_violation(
            user_id=user_id, board_id=board_id, text=text_content, now_ts=now
        )
        if is_sw_flood:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: STOP_WORDS_FLOOD] user={user_id} board={board_id} posts={posts_count} "
                f"reason='{sw_reason}' duration={sw_mute_sec}s"
            )
            expires_at = await apply_shadow_mute(
                user_id, board_id, duration_seconds=float(sw_mute_sec), reason=sw_reason, is_exponential=False
            )
            return True, sw_reason, expires_at

    # 2.2. Text Copro-Wipe Check (3+ fecal roots in one message)
    if text_content:
        is_copro_text, copro_reason = check_text_copro_flood(text_content)
        if is_copro_text:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: COPRO_TEXT] user={user_id} board={board_id} reason='{copro_reason}' duration={BAYAN_BASE_MUTE_SEC}s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=BAYAN_BASE_MUTE_SEC, reason=copro_reason, is_exponential=False)
            return True, copro_reason, expires_at

    # 2.3. Sybil Raid & Wall-of-Text Check (long text >= 100 chars across users/boards)
    if text_content:
        is_raid, raid_reason, raid_mute_sec = check_sybil_and_wall_of_text_raid(user_id, board_id, text_content, now_ts=now)
        if is_raid:
            if raid_reason == "double_tap_drop":
                logger.info(f"👻 [SPAM_FILTER: DOUBLE_TAP_DROP] user={user_id} board={board_id}")
                return True, "Сетевой дубль сообщения (лаг Telegram)", 0.0
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: SYBIL_WALL_OF_TEXT] user={user_id} board={board_id} reason='{raid_reason}' duration={raid_mute_sec}s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=float(raid_mute_sec), reason=raid_reason, is_exponential=False)
            return True, raid_reason, expires_at

    # 3. Cross-board spam check
    if text_content or file_unique_id or file_id:
        payload = text_content or file_unique_id or file_id or ""
        if not _check_cross_board_spam(user_id, board_id, payload, msg_type, raw_content_type):
            cb_reason = "Кросс-борд веерный спам по доскам"
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: CROSS_BOARD] user={user_id} board=ALL duration={BAYAN_BASE_MUTE_SEC}s"
            )
            expires_at = await apply_shadow_mute(user_id, 'ALL', duration_seconds=BAYAN_BASE_MUTE_SEC, reason=cb_reason, is_exponential=False)
            return True, cb_reason, expires_at

    # 4. Bayan check (>= 3 bayans in 3 minutes)
    is_bayan_trigger, bayan_mute_sec = check_bayan(
        user_id=user_id,
        content=text_content,
        msg_type=msg_type or raw_content_type,
        file_unique_id=file_unique_id,
        file_id=file_id,
        media_hash=media_hash,
        board_id=board_id,
        now_ts=now,
        media_group_id=media_group_id
    )
    if is_bayan_trigger:
        reason = "3+ баяна за 3 минуты"
        from common.database import apply_shadow_mute
        logger.warning(
            f"🚫 [SPAM_FILTER_TRIGGER: BAYAN] user={user_id} board={board_id} duration={bayan_mute_sec}s"
        )
        expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=float(bayan_mute_sec), reason=reason, is_exponential=False)
        return True, reason, expires_at

    return False, "", 0.0


async def analyze_message_for_spam(
    user_id: int,
    board_id: str,
    content: str,
    msg_type: str,
    raw_content_type: str,
    skip_cross_board: bool = False,
    skip_bayan: bool = False,
    posts_count: int | None = None,
    media_group_id: str | None = None
) -> Tuple[SpamResult, int]:
    """
    Decoupled engine for spam analysis.
    Returns a tuple: (SpamResult, current_violation_level).
    """
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return SpamResult.CLEAN, 0
    except Exception:
        pass
    if msg_type == 'audio' or (content is None and msg_type is None):
        return SpamResult.CLEAN, 0

    if content and not skip_cross_board:
        if not _check_cross_board_spam(user_id, board_id, content, msg_type, raw_content_type):
            return SpamResult.GLOBAL_BAN_REQUIRED, 0

    # Bayan check: 3 duplicates in 3 minutes (skipped if already checked in evaluate_message_for_autoshadowmute)
    if content and not skip_bayan:
        is_bayan_hit, bayan_mute_sec = check_bayan(user_id, content, msg_type or raw_content_type, board_id=board_id, media_group_id=media_group_id)
        if is_bayan_hit:
            return SpamResult.BAYAN_MUTE, bayan_mute_sec

    rules = SPAM_RULES.get(msg_type) or SPAM_RULES.get(raw_content_type)
    if not rules:
        if raw_content_type in ['photo', 'video', 'document', 'audio', 'voice']:
            rules = SPAM_RULES.get('media')
    if not rules:
        return SpamResult.CLEAN, 0

    now = datetime.now(UTC)
    violations = _spam_violations[board_id].setdefault(user_id, {'level': 0, 'last_reset': now})

    if now - violations['last_reset'] > timedelta(minutes=5):
        violations['level'] = 0
        violations['last_reset'] = now

    if posts_count is None:
        posts_count = await get_user_total_posts(user_id)

    if not check_rate_limit(board_id, user_id, rules, posts_count=posts_count, media_group_id=media_group_id):
        violations['level'] += 1
        return SpamResult.BAN_REQUIRED, violations['level']

    return SpamResult.CLEAN, violations['level']


def check_image_spam_limit(board_id: str, requested_images: int) -> bool:
    """Checks the global board image spam limit (Sliding Window)."""
    now_ts = time.time()
    tracker = image_spam_tracker[board_id]

    tracker[:] = [t for t in tracker if now_ts - t < IMAGE_SPAM_WINDOW]

    if len(tracker) + requested_images > IMAGE_SPAM_LIMIT:
        return False
    return True

def update_image_spam_tracker(board_id: str, requested_images: int):
    """Adds timestamps for successfully generated images."""
    now_ts = time.time()
    for _ in range(requested_images):
        image_spam_tracker[board_id].append(now_ts)

def get_board_spam_stats(board_id: str) -> dict:
    return {
        "spam_violations": len(_spam_violations[board_id]),
        "spam_tracker_users": len(_spam_trackers[board_id]),
        "spam_tracker_items": sum(len(items) for items in list(_spam_trackers[board_id].values())),
        "image_spam_items": len(image_spam_tracker[board_id]),
        "bayan_tracked_users": len(_bayan_tracker),
        "media_burst_tracked_users": len(_user_media_burst_tracker),
        "active_media_groups": sum(len(g) for g in list(_seen_media_groups.values())),
        "repost_tracked_users": len(_user_repost_timestamps),
        "short_gibberish_tracked_users": len(_short_gibberish_tracker),
    }

def prune_idle_user_spam_locks(max_keep: int = 1500) -> int:
    """Removes idle locks from user_spam_locks where lock is not acquired and has no waiters."""
    if len(user_spam_locks) <= max_keep:
        return 0
    stale = []
    for uid, lock in list(user_spam_locks.items()):
        try:
            if not lock.locked() and not getattr(lock, "_waiters", None):
                stale.append(uid)
                if len(user_spam_locks) - len(stale) <= max_keep:
                    break
        except Exception:
            continue
    for uid in stale:
        user_spam_locks.pop(uid, None)
    return len(stale)


def prune_stale_spam_filter_state(now_ts: float | None = None) -> dict[str, int]:
    """
    Sanitizes all in-memory spam filter trackers (TTL and LRU cleanup).
    Prevents memory leaks when 50,000+ users interact with the bot.
    Each cleanup stage is wrapped in try/except to prevent partial failures from aborting the prune cycle.
    Returns dictionary with counts of pruned entries.
    """
    now = float(now_ts) if now_ts is not None else time.time()
    pruned: dict[str, int] = {}

    # 1. user_spam_locks
    try:
        pruned["user_spam_locks"] = prune_idle_user_spam_locks(max_keep=1000)
    except Exception as e:
        logger.debug(f"Stage 1 prune_idle_user_spam_locks error: {e}")
        pruned["user_spam_locks"] = 0

    # 2. _seen_media_groups: {user_id: {mg_id: {'first_ts': float, ...}}}
    try:
        stale_mg_users = []
        for uid, mg_map in list(_seen_media_groups.items()):
            if not mg_map:
                stale_mg_users.append(uid)
                continue
            expired = [
                mg for mg, entry in list(mg_map.items())
                if now - (entry['first_ts'] if isinstance(entry, dict) else (entry if isinstance(entry, (int, float)) else 0.0)) > MEDIA_GROUP_WINDOW
            ]
            for mg in expired:
                mg_map.pop(mg, None)
            if not mg_map:
                stale_mg_users.append(uid)
        for uid in stale_mg_users:
            _seen_media_groups.pop(uid, None)
        pruned["_seen_media_groups"] = len(stale_mg_users)
    except Exception as e:
        logger.debug(f"Stage 2 _seen_media_groups error: {e}")
        pruned["_seen_media_groups"] = 0

    # 3. _seen_repost_media_groups: {user_id: {mg_id: {'first_ts': float, ...}}}
    try:
        stale_rmg_users = []
        for uid, rmg_map in list(_seen_repost_media_groups.items()):
            if not rmg_map:
                stale_rmg_users.append(uid)
                continue
            expired = [
                k for k, v in list(rmg_map.items())
                if now - (v.get('first_ts', 0.0) if isinstance(v, dict) else 0.0) > REPOST_WINDOW_SEC
            ]
            for k in expired:
                rmg_map.pop(k, None)
            if not rmg_map:
                stale_rmg_users.append(uid)
        for uid in stale_rmg_users:
            _seen_repost_media_groups.pop(uid, None)
        pruned["_seen_repost_media_groups"] = len(stale_rmg_users)
    except Exception as e:
        logger.debug(f"Stage 3 _seen_repost_media_groups error: {e}")
        pruned["_seen_repost_media_groups"] = 0

    # 4. _user_request_timestamps: {user_id: deque}
    try:
        stale_req_users = []
        for uid, tracker in list(_user_request_timestamps.items()):
            while tracker and (now - float(tracker[0]) > MINUTE_FLOOD_WINDOW):
                tracker.popleft()
            if not tracker:
                stale_req_users.append(uid)
        for uid in stale_req_users:
            _user_request_timestamps.pop(uid, None)
        pruned["_user_request_timestamps"] = len(stale_req_users)
    except Exception as e:
        logger.debug(f"Stage 4 _user_request_timestamps error: {e}")
        pruned["_user_request_timestamps"] = 0

    # 5. _bayan_tracker: {user_id: deque}
    try:
        stale_bayan_users = []
        for uid, tracker in list(_bayan_tracker.items()):
            while tracker and (now - tracker[0][0] > BAYAN_WINDOW_SEC):
                tracker.popleft()
            if not tracker:
                stale_bayan_users.append(uid)
        for uid in stale_bayan_users:
            _bayan_tracker.pop(uid, None)
        pruned["_bayan_tracker"] = len(stale_bayan_users)
    except Exception as e:
        logger.debug(f"Stage 5 _bayan_tracker error: {e}")
        pruned["_bayan_tracker"] = 0

    # 6. _bayan_mute_count & _bayan_mute_last_ts
    try:
        stale_bayan_mutes = []
        for uid, last_ts in list(_bayan_mute_last_ts.items()):
            if now - last_ts > BAYAN_RESET_SEC:
                stale_bayan_mutes.append(uid)
        for uid in stale_bayan_mutes:
            _bayan_mute_last_ts.pop(uid, None)
            _bayan_mute_count.pop(uid, None)
        # Also clean orphaned entries in _bayan_mute_count
        orphans = [uid for uid, cnt in list(_bayan_mute_count.items()) if cnt <= 0 or uid not in _bayan_mute_last_ts]
        for uid in orphans:
            _bayan_mute_count.pop(uid, None)
        pruned["_bayan_mute_counters"] = len(stale_bayan_mutes) + len(orphans)
    except Exception as e:
        logger.debug(f"Stage 6 _bayan_mute_counters error: {e}")
        pruned["_bayan_mute_counters"] = 0

    # 7. _user_link_timestamps & _user_repost_timestamps
    try:
        stale_links = []
        for uid, tracker in list(_user_link_timestamps.items()):
            while tracker and (now - float(tracker[0][0] if isinstance(tracker[0], tuple) else tracker[0]) > 60.0):
                tracker.popleft()
            if not tracker:
                stale_links.append(uid)
        for uid in stale_links:
            _user_link_timestamps.pop(uid, None)
        pruned["_user_link_timestamps"] = len(stale_links)
    except Exception as e:
        logger.debug(f"Stage 7a _user_link_timestamps error: {e}")
        pruned["_user_link_timestamps"] = 0

    try:
        stale_reposts = []
        for uid, tracker in list(_user_repost_timestamps.items()):
            while tracker and (now - float(tracker[0]) > REPOST_WINDOW_SEC):
                tracker.popleft()
            if not tracker:
                stale_reposts.append(uid)
        for uid in stale_reposts:
            _user_repost_timestamps.pop(uid, None)
        pruned["_user_repost_timestamps"] = len(stale_reposts)
    except Exception as e:
        logger.debug(f"Stage 7b _user_repost_timestamps error: {e}")
        pruned["_user_repost_timestamps"] = 0

    # 8. _user_media_burst_tracker: {user_id: dict}
    try:
        stale_bursts = []
        for uid, burst in list(_user_media_burst_tracker.items()):
            if burst.get('last_ts', 0.0) == 0.0 or (now - burst.get('last_ts', 0.0) > MEDIA_BURST_GAP * 3):
                stale_bursts.append(uid)
        for uid in stale_bursts:
            _user_media_burst_tracker.pop(uid, None)
        pruned["_user_media_burst_tracker"] = len(stale_bursts)
    except Exception as e:
        logger.debug(f"Stage 8 _user_media_burst_tracker error: {e}")
        pruned["_user_media_burst_tracker"] = 0

    # 9. _shadow_mute_applied_ts: {user_id: float}
    try:
        stale_mute_grace = []
        for uid, applied_ts in list(_shadow_mute_applied_ts.items()):
            if now - applied_ts > MUTE_GRACE_PERIOD_SEC * 10:
                stale_mute_grace.append(uid)
        for uid in stale_mute_grace:
            _shadow_mute_applied_ts.pop(uid, None)
        pruned["_shadow_mute_applied_ts"] = len(stale_mute_grace)
    except Exception as e:
        logger.debug(f"Stage 9 _shadow_mute_applied_ts error: {e}")
        pruned["_shadow_mute_applied_ts"] = 0

    # 10. _user_posts_count_cache: {user_id: (ts, count)}
    try:
        stale_cache = []
        for uid, val in list(_user_posts_count_cache.items()):
            if isinstance(val, tuple) and len(val) >= 1:
                if now - val[0] > USER_POSTS_CACHE_TTL:
                    stale_cache.append(uid)
            else:
                stale_cache.append(uid)
        for uid in stale_cache:
            _user_posts_count_cache.pop(uid, None)
        pruned["_user_posts_count_cache"] = len(stale_cache)
    except Exception as e:
        logger.debug(f"Stage 10 _user_posts_count_cache error: {e}")
        pruned["_user_posts_count_cache"] = 0

    # 11. _spam_violations: {board_id: {user_id: {'level': int, 'last_reset': datetime}}}
    try:
        now_dt = datetime.now(UTC)
        clean_v_count = 0
        for b_id, v_map in list(_spam_violations.items()):
            stale_v_users = []
            for uid, v in list(v_map.items()):
                lr = v.get('last_reset')
                if lr is not None:
                    age_sec = (now - lr) if isinstance(lr, (int, float)) else ((now_dt - (lr if getattr(lr, 'tzinfo', None) else lr.replace(tzinfo=UTC))).total_seconds() if hasattr(lr, 'tzinfo') else 0.0)
                    # Level 0 pruned after 5m (300s); violations of any level expired after 24h (86400s)
                    if (v.get('level', 0) == 0 and age_sec > 300) or age_sec > 86400:
                        stale_v_users.append(uid)
            for uid in stale_v_users:
                v_map.pop(uid, None)
            clean_v_count += len(stale_v_users)
        pruned["_spam_violations"] = clean_v_count
    except Exception as e:
        logger.debug(f"Stage 11 _spam_violations error: {e}")
        pruned["_spam_violations"] = 0

    # 12. _spam_trackers: {board_id: {user_id: [timestamps]}}
    try:
        clean_st_count = 0
        for b_id, u_map in list(_spam_trackers.items()):
            stale_st_users = []
            for uid, timestamps in list(u_map.items()):
                u_map[uid] = [t for t in timestamps if now - t <= 60.0]
                if not u_map[uid]:
                    stale_st_users.append(uid)
            for uid in stale_st_users:
                u_map.pop(uid, None)
            clean_st_count += len(stale_st_users)
        pruned["_spam_trackers"] = clean_st_count
    except Exception as e:
        logger.debug(f"Stage 12 _spam_trackers error: {e}")
        pruned["_spam_trackers"] = 0

    # 13. cross_board_spam_tracker: {user_id: deque}
    try:
        stale_cb_users = []
        for uid, tracker in list(cross_board_spam_tracker.items()):
            while tracker and (now - tracker[0][0] > CROSS_BOARD_WINDOW):
                tracker.popleft()
            if not tracker:
                stale_cb_users.append(uid)
        for uid in stale_cb_users:
            cross_board_spam_tracker.pop(uid, None)
        pruned["cross_board_spam_tracker"] = len(stale_cb_users)
    except Exception as e:
        logger.debug(f"Stage 13 cross_board_spam_tracker error: {e}")
        pruned["cross_board_spam_tracker"] = 0

    # 14. _short_gibberish_tracker: {user_id: deque}
    try:
        stale_gib_users = []
        for uid, tracker in list(_short_gibberish_tracker.items()):
            while tracker and (now - tracker[0] > SHORT_GIBBERISH_SLOW_WINDOW):
                tracker.popleft()
            if not tracker:
                stale_gib_users.append(uid)
        for uid in stale_gib_users:
            _short_gibberish_tracker.pop(uid, None)
        pruned["_short_gibberish_tracker"] = len(stale_gib_users)
    except Exception as e:
        logger.debug(f"Stage 14 _short_gibberish_tracker error: {e}")
        pruned["_short_gibberish_tracker"] = 0

    # 14. _stop_words_violation_tracker
    try:
        stale_sw = []
        for uid, tr in list(_stop_words_violation_tracker.items()):
            while tr and (now - tr[0] > STOP_WORDS_WINDOW):
                tr.popleft()
            if not tr:
                stale_sw.append(uid)
        for uid in stale_sw:
            _stop_words_violation_tracker.pop(uid, None)
        pruned["_stop_words_violation_tracker"] = len(stale_sw)
    except Exception as e:
        logger.debug(f"Stage 14 _stop_words_violation_tracker error: {e}")
        pruned["_stop_words_violation_tracker"] = 0

    # 15. _in_memory_shadow_muted_users
    try:
        stale_sm = []
        for k, exp in list(_in_memory_shadow_muted_users.items()):
            if exp <= now:
                stale_sm.append(k)
        for k in stale_sm:
            _in_memory_shadow_muted_users.pop(k, None)
        pruned["_in_memory_shadow_muted_users"] = len(stale_sm)
    except Exception as e:
        logger.debug(f"Stage 15 _in_memory_shadow_muted_users error: {e}")
        pruned["_in_memory_shadow_muted_users"] = 0

    # 16. board_data shadow_mutes stale entries cleanup
    try:
        from shared_state import board_data
        clean_bd_sm = 0
        for b_id, b_dict in list(board_data.items()):
            sm_map = b_dict.get('shadow_mutes', {})
            stale_bd = []
            for uid, exp in list(sm_map.items()):
                exp_sec = exp.timestamp() if isinstance(exp, datetime) else float(exp)
                if exp_sec <= now:
                    stale_bd.append(uid)
            for uid in stale_bd:
                sm_map.pop(uid, None)
            clean_bd_sm += len(stale_bd)
        pruned["board_data_shadow_mutes"] = clean_bd_sm
    except Exception as e:
        logger.debug(f"Stage 16 board_data_shadow_mutes error: {e}")
        pruned["board_data_shadow_mutes"] = 0

    return pruned


def acquire_spam_lock(user_id: int):
    if len(user_spam_locks) > 3000:
        prune_idle_user_spam_locks(max_keep=1500)
    return user_spam_locks[user_id]


def get_spam_violation_level(board_id: str, user_id: int) -> int:
    return _spam_violations[board_id].get(user_id, {}).get('level', 0)

# Preload existing active shadow mutes on startup
try:
    load_active_shadow_mutes_from_db()
except Exception:
    pass
