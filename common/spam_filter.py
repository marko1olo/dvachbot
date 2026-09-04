# -*- coding: utf-8 -*-
import time
import asyncio
import hashlib
import re
import difflib
import logging
from typing import Dict, List, Tuple, Optional
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
URL_WHITELIST = {"tgach.top", "t.me/tgchan_archive", "t.me/tgach_archive", "2ch.hk", "dvach.top"}

# --- Anti-Dox & Phone Leak Patterns ---
DOX_MASK_REPLACEMENT = "[НОМЕР ТЕЛЕФОНА СКРЫТ / ANTI-DOX]"

RE_PHONE_RU_KZ = r'(?:(?:\+7|8)[\s\-\(\)\.\/]*(?:9|7)(?:[\s\-\(\)\.\/]*\d){9})'
RE_PHONE_UA = r'(?:(?:\+?380)(?:[\s\-\(\)\.\/]*\d){9})'
RE_PHONE_BY = r'(?:(?:\+?375)(?:[\s\-\(\)\.\/]*\d){9})'

RE_PHONE_DOX = re.compile(
    rf'(?<![\d+])(?:{RE_PHONE_RU_KZ}|{RE_PHONE_UA}|{RE_PHONE_BY})(?!\d)',
    re.IGNORECASE
)


def contains_phone_number(text: str) -> bool:
    """Returns True if the text contains a leaked mobile phone number."""
    if not text or not isinstance(text, str):
        return False
    return bool(RE_PHONE_DOX.search(text))


def extract_phone_numbers(text: str) -> List[str]:
    """Extracts all matched mobile phone numbers from text."""
    if not text or not isinstance(text, str):
        return []
    return [match.group(0) for match in RE_PHONE_DOX.finditer(text)]


def mask_phone_numbers(text: str, replacement: str = DOX_MASK_REPLACEMENT) -> str:
    """Masks all mobile phone numbers in text with replacement label."""
    if not text or not isinstance(text, str):
        return text
    return RE_PHONE_DOX.sub(replacement, text)


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
    
    # Check phone leak
    if contains_phone_number(text):
        return True

    # Check forbidden link / invite / promo / ad spam
    is_link_spam, _ = check_link_or_ad_spam(user_id, board_id, text)
    if is_link_spam:
        return True

    banned_words = _spam_filter_words.get(board_id)
    if not banned_words:
        return False
    lower_text = str(text or "").lower()
    for wl in ["tgach.top", "t.me/tgchan_archive", "t.me/tgach_archive", "tgchan_archive", "tgach_archive"]:
        lower_text = lower_text.replace(wl, "")
    if any(str(word).strip().lower() in lower_text for word in banned_words if str(word).strip()):
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
            normalized = " ".join(content.strip().lower().split())
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
                normalized = " ".join(str(t).strip().lower().split())
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
    now_ts: float | None = None
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
    for ts, prev_fp, _ in u_tracker:
        if now - ts <= BAYAN_WINDOW_SEC and prev_fp == fp:
            return True, f"Повтор сообщения/медиа (fingerprint: {fp})"

    # 2. Check near-duplicate text similarity (Levenstein/diff >= 85%)
    if fp.startswith("text:") and isinstance(content, str) and len(content.strip()) >= 10:
        norm_cur = content.strip().lower()
        for ts, prev_fp, prev_raw in u_tracker:
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
    now_ts: float | None = None
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

    # Record current message
    tracker.append((now, fp, content if isinstance(content, str) else None))

    # Add to board recent fingerprints
    _board_recent_fingerprints[board_id].append((now, fp))

    # Check total matching bayans in the window
    bayan_count = sum(1 for ts, f, _ in tracker if f == fp)
    
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


def check_flood(user_id: int, board_id: str, now_ts: float | None = None, record_history: bool = True, is_reply: bool = False) -> Tuple[bool, str]:
    """
    Checks if a user is flooding requests (burst and minute limit).
    Returns (is_flooding: bool, reason: str).
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

    # 1. Burst flood: > 4 messages in 4 seconds
    burst_limit = 8 if is_reply else BURST_FLOOD_LIMIT
    burst_window = 10.0 if is_reply else BURST_FLOOD_WINDOW
    burst_count = sum(1 for ts in current_timestamps if now - ts <= burst_window)
    if burst_count > burst_limit:
        if record_history:
            tracker.append(now)
        return True, f"Burst флуд: {burst_count} сообщений за {burst_window}с"

    # 2. Rate flood: > 8 messages in 15 seconds
    rate_count = sum(1 for ts in current_timestamps if now - ts <= RATE_FLOOD_WINDOW)
    if rate_count > RATE_FLOOD_LIMIT:
        if record_history:
            tracker.append(now)
        return True, f"Частый постинг: {rate_count} сообщений за {RATE_FLOOD_WINDOW}с"

    # 3. Minute flood: > 20 messages in 60 seconds
    if len(current_timestamps) > MINUTE_FLOOD_LIMIT:
        if record_history:
            tracker.append(now)
        return True, f"Минутный флуд: {len(current_timestamps)} сообщений за {MINUTE_FLOOD_WINDOW}с"

    if record_history:
        tracker.append(now)

    return False, ""


def check_link_or_ad_spam(user_id: int, board_id: str, text: str, now_ts: float | None = None) -> Tuple[bool, str]:
    """
    Checks for link spam, Telegram invite links, or advertisement/scam keywords.
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

    # 1. Casino / Crypto / Scam keywords
    scam_match = RE_AD_SCAM.search(clean_text)
    if scam_match:
        return True, f"Реклама/скам: '{scam_match.group(0)}'"

    # 2. Phone number / doxing leaks (+79..., 89..., +380..., +375...)
    if contains_phone_number(clean_text):
        phones = extract_phone_numbers(clean_text)
        return True, f"Слив телефонного номера (Anti-Dox): {phones[0]}"

    return False, ""


def _check_repeats(user_id: int, b_data: dict, msg_info: tuple[str, str], rules: dict, violations: dict) -> bool:
    """Check if the user is repeatedly sending the same or highly similar messages."""
    try:
        from site_tgach.admin_config import ADMIN_IDS
        if user_id in ADMIN_IDS:
            return True
    except Exception:
        pass
    content, msg_type = msg_info
    max_repeats = rules.get('max_repeats')
    if not max_repeats or not content:
        return True

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
        consecutive_limit = max_repeats + 1
        if len(last_items_deque) >= consecutive_limit:
            tail = [item[1] for item in list(last_items_deque)[-consecutive_limit:]]
            if len(set(tail)) == 1:
                if msg_type != 'text' or len(str(tail[0]).strip()) >= rules.get('min_length', 4):
                    violations['level'] += 1
                    last_items_deque.clear()
                    return False
        elif len(last_items_deque) >= max_repeats and msg_type == 'text':
            contents = [item[1] for item in list(last_items_deque)[-max_repeats:]]
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


def check_rate_limit(board_id: str, user_id: int, rules: dict) -> bool:
    """Sliding window implementation for rate limits."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return True
    except Exception:
        pass
    now_ts = time.time()
    tracker = _spam_trackers[board_id][user_id]
    
    # Prune old timestamps
    tracker[:] = [t for t in tracker if t > now_ts - rules['window_sec']]
    tracker.append(now_ts)
    
    if len(tracker) >= rules['max_per_window']:
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
    is_reply: bool = False
) -> Tuple[bool, str, float]:
    """
    Comprehensive evaluation of an incoming message for auto-shadowmute:
    1. Check if user is already shadowmuted -> exponential continuation
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
    text_content = content if isinstance(content, str) else (content.get('text') or content.get('caption') if isinstance(content, dict) else None)

    # 1. Flood check
    is_flood, flood_reason = check_flood(user_id, board_id, now_ts=now, is_reply=is_reply)
    if is_flood:
        from common.database import apply_shadow_mute
        expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=FLOOD_BASE_MUTE_SEC, reason=flood_reason, is_exponential=False)
        return True, flood_reason, expires_at

    # 2. Link / Ad / Scam spam check
    if text_content:
        is_link_spam, link_reason = check_link_or_ad_spam(user_id, board_id, text_content, now_ts=now)
        if is_link_spam:
            from common.database import apply_shadow_mute
            expires_at = await apply_shadow_mute(user_id, board_id, duration_seconds=BAYAN_BASE_MUTE_SEC, reason=link_reason, is_exponential=False)
            return True, link_reason, expires_at

    # 3. Cross-board spam check
    if text_content or file_unique_id or file_id:
        payload = text_content or file_unique_id or file_id or ""
        if not _check_cross_board_spam(user_id, board_id, payload, msg_type, raw_content_type):
            cb_reason = f"Кросс-борд веерный спам по доскам"
            from common.database import apply_shadow_mute
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
        now_ts=now
    )
    if is_bayan_trigger:
        reason = f"3+ баяна за 3 минуты"
        from common.database import apply_shadow_mute
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
    skip_bayan: bool = False
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
        is_bayan_hit, bayan_mute_sec = check_bayan(user_id, content, msg_type or raw_content_type, board_id=board_id)
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

    if not check_rate_limit(board_id, user_id, rules):
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
    }

def acquire_spam_lock(user_id: int):
    return user_spam_locks[user_id]

def get_spam_violation_level(board_id: str, user_id: int) -> int:
    return _spam_violations[board_id].get(user_id, {}).get('level', 0)
