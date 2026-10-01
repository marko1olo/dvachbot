# -*- coding: utf-8 -*-
import time
import asyncio
import hashlib
import re
import difflib
import unicodedata
import logging
from typing import Dict, List, Tuple, Optional, Any
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

# --- Constants & Thresholds ---
BAYAN_WINDOW_SEC = 180          # 3 minutes sliding window
BAYAN_THRESHOLD = 3             # 3 bayans in 3 minutes -> 20 min shadowmute
BAYAN_BASE_MUTE_SEC = 1200      # 20 minutes base shadowmute (1200 seconds)
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

# Repost / Forward from public channels limits & responses
REPOST_LIMIT_PER_MINUTE = 4
REPOST_WINDOW_SEC = 60.0
REPOST_FLOOD_MUTE_SEC = 1200.0  # Standard 20 minutes shadowmute for news repost spammers

REPOST_FLOOD_RESPONSES: List[str] = [
    "Уймись, ковбой, тут не личка твоей блядины, чтобы твоё говно репощенное читать!",
    "Тормози, шлюхопересыльщик. Тут борда, а не помойка для репостов из твоих ссаных пабликов.",
    "Завали ебало с репостами. 4 штуки в минуту — твой потолок, дальше иди в свой Твиттер сри.",
    "Хватит форвардить этот кал, шизоид. Своими словами пиши или пиздуй отсюда.",
    "Репостоблядь detected. Уйми пальцы, тут никто твой пересланный мусор читать не нанимался.",
]

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

def register_media_group(user_id: int, media_group_id: str, now_ts: float | None = None):
    """Explicitly registers an incoming media group for a user."""
    now = float(now_ts) if now_ts is not None else time.time()
    _seen_media_groups[user_id][str(media_group_id)] = {'first_ts': now, 'count': 1}

# Fast cache for user posts count: {user_id: (cached_at_ts, posts_count)}
_user_posts_count_cache: Dict[int, Tuple[float, int]] = {}
USER_POSTS_CACHE_TTL = 60.0

def set_cached_user_posts(user_id: int, posts_count: int):
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
        if DB_NAME and isinstance(DB_NAME, str) and os.path.exists(DB_NAME):
            import sqlite3
            conn = sqlite3.connect(f"file:{DB_NAME}?mode=ro", uri=True, timeout=0.2)
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


# Cross-board limit
CROSS_BOARD_WINDOW = 60.0       # 60 seconds

# Link & Ad Regex Patterns
RE_TG_INVITE = re.compile(r'(?:t\.me|telegram\.me)/(?:\+|joinchat/)[a-zA-Z0-9_\-]+', re.IGNORECASE)
RE_TG_PROMO = re.compile(r'(?:t\.me|telegram\.me)/(?!(?:tgchan_archive|tgach_archive|c/\d+))[a-zA-Z0-9_]{5,}', re.IGNORECASE)
RE_AD_SCAM = re.compile(
    r'(?:'
    r'1win|1xbet|vavada|вавад[аы]|up-?x|dragon\s*money|драгон\s*мани|pin-?up|пин-?ап|казино\s*вулкан|клуб\s*вулкан|онлайн[\s\-]казино|зеркал[оа][\s\-]+казино|'
    r'crypto\s*airdrop|раздача\s*крипт|слив\s*онлифанс|вип\s*канал|подпишись\s*на\s*канал|ставки\s*на\s*спорт|'
    r'легкий\s*заработок|интим\s*знакомства|промокод\s+на\s+(?:депозит|фриспин)'
    r')',
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

    banned_words = _spam_filter_words.get(board_id)
    if not banned_words:
        return False

    for wl in URL_WHITELIST:
        clean_canonical = clean_canonical.replace(wl, "")

    clean_with_homoglyphs = clean_canonical.translate(HOMOGLYPH_LATIN_TO_CYRILLIC)

    for word in banned_words:
        w = canonicalize_spam_text(str(word)).strip()
        if not w:
            continue
        if w in clean_canonical or w in clean_with_homoglyphs:
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
            if len(normalized) < 4:
                return ""  # Ignore short trivial text
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
                if len(normalized) >= 4:
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
    u_tracker = _bayan_tracker[user_id]
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

    # Record current message: (timestamp, fingerprint, content, media_group_id)
    tracker.append((now, fp, content if isinstance(content, str) else None, str(media_group_id) if media_group_id else None))

    # Add to board recent fingerprints
    _board_recent_fingerprints[board_id].append((now, fp))

    # Check total matching bayans in the window (excluding items within same media group)
    bayan_count = sum(
        1 for item in tracker
        if item[1] == fp and not (media_group_id and len(item) > 3 and item[3] == str(media_group_id))
    )
    
    if bayan_count >= BAYAN_THRESHOLD:
        last_mute = _bayan_mute_last_ts[user_id]
        if last_mute and now - last_mute > BAYAN_RESET_SEC:
            _bayan_mute_count[user_id] = 0

        escalation = _bayan_mute_count[user_id]
        mute_seconds = int(min(MAX_BAYAN_MUTE_SEC, BAYAN_BASE_MUTE_SEC * (2 ** escalation)))
        
        _bayan_mute_count[user_id] = escalation + 1
        _bayan_mute_last_ts[user_id] = now
        tracker.clear()
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

    # 1. Handle media groups (albums): subsequent files of the same album within window are NOT new flood messages
    if media_group_id:
        mg_str = str(media_group_id)
        mg_map = _seen_media_groups[user_id]
        # Prune expired
        expired = [mg for mg, entry in list(mg_map.items()) if now - (entry['first_ts'] if isinstance(entry, dict) else entry) > MEDIA_GROUP_WINDOW]
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
            mg_map[mg_str] = {'first_ts': now, 'count': 1}

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


def check_link_or_ad_spam(user_id: int, board_id: str, text: str, now_ts: float | None = None) -> Tuple[bool, str]:
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

    # Remove whitelisted domains before evaluation
    for wl in URL_WHITELIST:
        clean_text = clean_text.replace(wl, "")

    # Phone number / doxing leaks (+79..., 89..., +380..., +375...)
    if contains_phone_number(clean_text):
        phones = extract_phone_numbers(clean_text)
        return True, f"Слив телефонного номера (Anti-Dox): {phones[0]}"

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


def reset_repost_tracker(user_id: int | None = None) -> None:
    """Resets repost flood tracker for a user or globally."""
    if user_id is not None:
        _user_repost_timestamps.pop(user_id, None)
        _seen_repost_media_groups.pop(user_id, None)
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
    mute_duration_sec: float = REPOST_FLOOD_MUTE_SEC,
    media_group_id: str | None = None,
    bot_instance: Any = None,
) -> Tuple[bool, str]:
    """
    Checks if an incoming message is a repost from a public channel/chat and enforces
    the limit of at most 4 reposts per sliding 60 seconds from a single user on a board/bot.
    Supports media_group_id deduplication so 1 album counts as 1 repost.

    If limit is exceeded (5th and subsequent reposts within 60 seconds):
    1. Returns (True, toxic_repost_response).
    2. Spawns standard shadowmute task if auto_apply_mute is True and loop is running.

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

    try:
        from bot_helpers import is_admin
        if user_id and is_admin(user_id, board_id):
            return False, ""
    except Exception:
        pass

    now = float(now_ts) if now_ts is not None else time.time()

    # Media group deduplication: subsequent items of the same album do not re-count
    if media_group_id:
        mg_str = str(media_group_id)
        user_mg_map = _seen_repost_media_groups[user_id]
        # Prune expired albums older than 60s
        expired = [k for k, v in list(user_mg_map.items()) if now - v.get('first_ts', 0) > REPOST_WINDOW_SEC]
        for k in expired:
            user_mg_map.pop(k, None)

        if mg_str in user_mg_map:
            entry = user_mg_map[mg_str]
            return entry.get('blocked', False), entry.get('response', "")

    tracker = _user_repost_timestamps[user_id]

    # Prune timestamps older than sliding window
    while tracker and (now - float(tracker[0]) > REPOST_WINDOW_SEC):
        tracker.popleft()

    # Monotonic safety
    if tracker and now < float(tracker[-1]):
        now = float(tracker[-1])

    if len(tracker) >= REPOST_LIMIT_PER_MINUTE:
        response = get_repost_flood_response()
        logger.warning(
            f"🚫 REPOST SPAM: User {user_id} exceeded repost limit ({len(tracker)} reposts in {REPOST_WINDOW_SEC}s) on /{board_id}/"
        )
        if media_group_id:
            _seen_repost_media_groups[user_id][str(media_group_id)] = {
                'first_ts': now, 'blocked': True, 'response': response
            }
        if auto_apply_mute and user_id:
            try:
                loop = asyncio.get_running_loop()
                from common.task_manager import spawn_task
                spawn_task(
                    apply_shadow_mute(
                        user_id=user_id,
                        board_id=board_id,
                        duration_seconds=mute_duration_sec,
                        reason=f"Спам репостами из пабликов (>4/мин): {response}",
                        is_exponential=False
                    )
                )
            except RuntimeError:
                pass  # No running event loop (e.g. sync test)
            except Exception as e:
                logger.warning(f"Failed to spawn shadow mute task for repost spam (user {user_id}): {e}")
        return True, response

    if media_group_id:
        _seen_repost_media_groups[user_id][str(media_group_id)] = {
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
    mute_duration_sec: float = REPOST_FLOOD_MUTE_SEC,
    media_group_id: str | None = None,
    bot_instance: Any = None,
) -> Tuple[bool, str, float]:
    """
    Async version of check_repost_spam.
    If limit is exceeded, applies shadowmute directly and awaits it.
    Returns: (is_blocked: bool, toxic_response: str, expires_at: float)
    """
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
    )
    expires_at = 0.0
    if is_blocked and auto_apply_mute and isinstance(user_id, int) and user_id:
        try:
            expires_at = await apply_shadow_mute(
                user_id=user_id,
                board_id=board_id,
                duration_seconds=mute_duration_sec,
                reason=f"Спам репостами из пабликов (>4/мин): {response}",
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
        last_items_deque = b_data['last_texts'][user_id]
    elif msg_type == 'sticker':
        last_items_deque = b_data['last_stickers'][user_id]
    elif msg_type == 'animation':
        last_items_deque = b_data['last_animations'][user_id]
    elif msg_type == 'audio':
        last_items_deque = b_data['last_audios'][user_id]

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
            boards = {b for t, b, c in candidate_cb}
            if len(boards) >= 2 and candidate_cb[-1][0] - candidate_cb[0][0] <= CROSS_BOARD_WINDOW:
                contents = [c for t, b, c in candidate_cb]
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

    from common.database import get_shadow_mute_info
    info = await get_shadow_mute_info(user_id, board_id)
    if info['is_muted']:
        return True, info['expires_at'] or 0.0
    return False, 0.0


async def apply_shadow_mute(
    user_id: int,
    board_id: str,
    duration_seconds: float = 1200.0,
    reason: str = "",
    is_exponential: bool = False
) -> float:
    """
    Applies shadow mute, clears the user's timestamp deques _user_request_timestamps[(user_id, board_id)].clear()
    and _user_request_timestamps[user_id].clear() so queued/in-flight messages from the same packet burst
    do not immediately re-trigger flood detection, and ensures ghost/shadow posts do not trigger exponential flood mute escalation.
    """
    record_shadow_mute_applied(user_id)
    _user_media_burst_tracker.pop(user_id, None)
    _seen_media_groups.pop(user_id, None)
    _user_repost_timestamps.pop(user_id, None)
    _seen_repost_media_groups.pop(user_id, None)
    try:
        _user_request_timestamps.pop(user_id, None)
        _user_request_timestamps.pop((user_id, board_id), None)
    except Exception:
        pass

    # Ensure ghost / shadow posts do not trigger exponential flood mute escalation
    if is_exponential:
        from common.database import get_shadow_mute_info
        info = await get_shadow_mute_info(user_id, board_id)
        if info.get('is_muted'):
            return info.get('expires_at') or 0.0

    is_flood_reason = any(w in (reason or "").lower() for w in ("флуд", "flood", "burst", "постинг"))
    if is_exponential and is_flood_reason:
        is_exponential = False

    if is_exponential and is_in_mute_grace_period(user_id):
        is_exponential = False

    orig_fn = _orig_db_apply_shadow_mute or getattr(common.database, "apply_shadow_mute", None)
    if orig_fn and orig_fn is not apply_shadow_mute:
        return await orig_fn(
            user_id, board_id, duration_seconds=duration_seconds, reason=reason, is_exponential=is_exponential
        )
    return 0.0


# Hook common.database.apply_shadow_mute
try:
    import common.database
    _orig_db_apply_shadow_mute = getattr(common.database, "apply_shadow_mute", None)
    if _orig_db_apply_shadow_mute:
        common.database.apply_shadow_mute = apply_shadow_mute
except Exception:
    _orig_db_apply_shadow_mute = None


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

    # If user is already shadow-muted, maintain existing mute without extending duration
    from common.database import is_shadow_muted, get_shadow_mute_info
    if await is_shadow_muted(user_id, board_id):
        info = await get_shadow_mute_info(user_id, board_id)
        return True, "Уже в теневом муте", info.get('expires_at') or 0.0

    now = now_ts or time.time()
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
        logger.warning(
            f"🚫 [SPAM_FILTER_TRIGGER: FLOOD] user={user_id} board={board_id} posts={posts_count} "
            f"tier={tier.get('name')} reason='{flood_reason}' duration={base_mute}s"
        )
        expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=base_mute, reason=flood_reason, is_exponential=False)
        return True, flood_reason, expires_at

    # 2. Link / Ad / Scam spam check
    if text_content:
        is_link_spam, link_reason = check_link_or_ad_spam(user_id, board_id, text_content, now_ts=now)
        if is_link_spam:
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: LINK_OR_AD] user={user_id} board={board_id} reason='{link_reason}' duration={BAYAN_BASE_MUTE_SEC}s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=BAYAN_BASE_MUTE_SEC, reason=link_reason, is_exponential=False)
            return True, link_reason, expires_at

    # 3. Cross-board spam check
    if text_content or file_unique_id or file_id:
        payload = text_content or file_unique_id or file_id or ""
        if not _check_cross_board_spam(user_id, board_id, payload, msg_type, raw_content_type):
            cb_reason = f"Кросс-борд веерный спам по доскам"
            from common.database import apply_shadow_mute
            logger.warning(
                f"🚫 [SPAM_FILTER_TRIGGER: CROSS_BOARD] user={user_id} board={board_id} duration={BAYAN_BASE_MUTE_SEC}s"
            )
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=BAYAN_BASE_MUTE_SEC, reason=cb_reason, is_exponential=False)
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
        reason = f"3+ баяна за 3 минуты"
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
        "spam_tracker_items": sum(len(items) for items in _spam_trackers[board_id].values()),
        "image_spam_items": len(image_spam_tracker[board_id]),
        "bayan_tracked_users": len(_bayan_tracker),
        "media_burst_tracked_users": len(_user_media_burst_tracker),
        "active_media_groups": sum(len(g) for g in _seen_media_groups.values()),
        "repost_tracked_users": len(_user_repost_timestamps),
    }

def acquire_spam_lock(user_id: int):
    return user_spam_locks[user_id]

def get_spam_violation_level(board_id: str, user_id: int) -> int:
    return _spam_violations[board_id].get(user_id, {}).get('level', 0)
