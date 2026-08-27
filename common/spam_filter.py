import time
import asyncio
import hashlib
from typing import Dict, List, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta, UTC
from enum import Enum, auto

class SpamResult(Enum):
    CLEAN = auto()
    WARNING = auto()
    BAN_REQUIRED = auto()
    GLOBAL_BAN_REQUIRED = auto()
    BAYAN_MUTE = auto()  # New: bayan-triggered shadowmute

# Volatile State Trackers
user_spam_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
cross_board_spam_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=3))
image_spam_tracker: Dict[str, List[float]] = defaultdict(list)

# The board-level trackers are mapped by board_id then user_id
_spam_trackers: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
_spam_violations: Dict[str, Dict[int, dict]] = defaultdict(dict)
_spam_filter_words: Dict[str, set] = defaultdict(set)
_reaction_banned_users: Dict[str, set] = defaultdict(set)

# --- Bayan Detection ---
# Tracks per-user content fingerprints with timestamps: {user_id: deque of (timestamp, fingerprint)}
_bayan_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
# Tracks how many times a user has been bayan-muted (for exponential escalation)
_bayan_mute_count: Dict[int, int] = defaultdict(int)
# Tracks when the last bayan mute was applied (to reset count after long periods of good behavior)
_bayan_mute_last_ts: Dict[int, float] = defaultdict(float)

BAYAN_WINDOW_SEC = 180       # 3 minutes
BAYAN_THRESHOLD = 3          # 3 duplicate posts in the window
BAYAN_BASE_MUTE_SEC = 1200   # 20 minutes base shadowmute
BAYAN_RESET_SEC = 3600       # Reset escalation counter after 1 hour of no mutes


# --- Configuration ---
SPAM_RULES = {
    'text': {'max_repeats': 5, 'min_length': 4, 'window_sec': 15, 'max_per_window': 10},
    'sticker': {'max_repeats': 5, 'max_per_window': 10, 'window_sec': 20},
    'animation': {'max_repeats': 5, 'max_per_window': 10, 'window_sec': 20},
    'photo': {'max_repeats': 4, 'max_per_window': 8, 'window_sec': 30},
    'video': {'max_repeats': 4, 'max_per_window': 8, 'window_sec': 30},
    'document': {'max_repeats': 4, 'max_per_window': 8, 'window_sec': 30},
    'media': {'max_repeats': 5, 'max_per_window': 10, 'window_sec': 30}
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
    """Checks if a message contains a banned spam filter word."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return False
    except Exception:
        pass
    banned_words = _spam_filter_words.get(board_id)
    if not banned_words:
        return False
    lower_text = str(text or "").lower()
    for wl in ["tgach.top", "t.me/tgchan_archive", "t.me/tgach_archive", "tgchan_archive", "tgach_archive"]:
        lower_text = lower_text.replace(wl, "")
    if any(str(word).strip().lower() in lower_text for word in banned_words if str(word).strip()):
        return True
    return False


def _content_fingerprint(content: str, msg_type: str) -> str:
    """Generate a fingerprint for content deduplication.
    For media (file_id), uses the file_id directly.
    For text, uses a normalized hash.
    """
    if msg_type in ('photo', 'video', 'document', 'sticker', 'animation'):
        # file_id is already unique per media
        return f"media:{content}"
    elif msg_type == 'text' and content:
        # Normalize text: lowercase, strip whitespace, hash
        normalized = content.strip().lower()
        if len(normalized) < 4:
            return ""  # Too short to consider bayan
        h = hashlib.md5(normalized.encode('utf-8', errors='replace')).hexdigest()
        return f"text:{h}"
    return ""


def check_bayan(user_id: int, content: str, msg_type: str) -> Tuple[bool, int]:
    """Check if user is posting duplicate content (bayan).
    
    Returns (is_bayan, bayan_mute_seconds).
    is_bayan=True means threshold exceeded and mute should be applied.
    bayan_mute_seconds is the computed mute duration (with exponential escalation).
    """
    if not content:
        return False, 0
    
    fp = _content_fingerprint(content, msg_type)
    if not fp:
        return False, 0
    
    now = time.time()
    tracker = _bayan_tracker[user_id]
    
    # Prune entries older than the bayan window
    while tracker and now - tracker[0][0] > BAYAN_WINDOW_SEC:
        tracker.popleft()
    
    # Add current fingerprint
    tracker.append((now, fp))
    
    # Count how many times this exact fingerprint appears in the window
    fp_count = sum(1 for ts, f in tracker if f == fp)
    
    if fp_count >= BAYAN_THRESHOLD:
        # Clear the tracker for this user (reset after triggering)
        tracker.clear()
        
        # Compute exponential mute duration
        # Reset escalation if last mute was long ago
        last_mute_ts = _bayan_mute_last_ts[user_id]
        if last_mute_ts and now - last_mute_ts > BAYAN_RESET_SEC:
            _bayan_mute_count[user_id] = 0
        
        escalation = _bayan_mute_count[user_id]
        mute_seconds = BAYAN_BASE_MUTE_SEC * (2 ** escalation)  # 20m, 40m, 80m, 160m, ...
        # Cap at 24 hours
        mute_seconds = min(mute_seconds, 86400)
        
        _bayan_mute_count[user_id] = escalation + 1
        _bayan_mute_last_ts[user_id] = now
        
        return True, mute_seconds
    
    return False, 0


def get_bayan_escalation_level(user_id: int) -> int:
    """Get the current bayan escalation level for a user."""
    return _bayan_mute_count.get(user_id, 0)


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
        
        if len(last_items_deque) >= max_repeats:
            contents = [item[1] for item in last_items_deque]
            
            if len(set(contents)) == 1:
                if msg_type != 'text' or len(contents[0].strip()) >= rules.get('min_length', 4):
                    violations['level'] += 1
                    last_items_deque.clear()
                    return False
            elif msg_type == 'text':
                from difflib import SequenceMatcher
                def _fast_similar(s1: str, s2: str) -> bool:
                    if s1 == s2: return True
                    l1, l2 = len(s1), len(s2)
                    if abs(l1 - l2) / max(l1, l2, 1) > 0.25: return False
                    return SequenceMatcher(None, s1[:400], s2[:400]).ratio() > 0.85
                if all(_fast_similar(contents[0], c) for c in contents[1:]):
                    violations['level'] += 1
                    last_items_deque.clear()
                    return False
    return True

def _check_cross_board_spam(user_id: int, board_id: str, content: str, msg_type: str, raw_content_type: str) -> bool:
    """Check for cross-board spam (echodown detection) returning False if detected."""
    try:
        from bot_helpers import is_admin
        if is_admin(user_id, board_id):
            return True
    except Exception:
        pass
    now_ts = time.time()
    user_cb = cross_board_spam_tracker[user_id]
    if not user_cb or user_cb[-1][1] != board_id:
        user_cb.append((now_ts, board_id, content))
        if len(user_cb) == 3:
            boards = {b for t, b, c in user_cb}
            if len(boards) == 3 and user_cb[-1][0] - user_cb[0][0] <= 30:
                contents = [c for t, b, c in user_cb]
                is_duplicate = False
                if raw_content_type == 'text' or (raw_content_type in ['photo', 'video', 'document'] and msg_type == 'text'):
                    import difflib
                    def _fast_sim(s1, s2):
                        if s1 == s2: return True
                        l1, l2 = len(s1), len(s2)
                        if abs(l1 - l2) / max(l1, l2, 1) > 0.25: return False
                        return difflib.SequenceMatcher(None, s1[:400], s2[:400]).ratio() > 0.85
                    if _fast_sim(contents[0], contents[1]) and _fast_sim(contents[1], contents[2]):
                        is_duplicate = True
                elif contents[0] == contents[1] == contents[2]:
                    is_duplicate = True
                
                if is_duplicate:
                    user_cb.clear()
                    return False
    return True


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


async def analyze_message_for_spam(user_id: int, board_id: str, content: str, msg_type: str, raw_content_type: str, skip_cross_board: bool = False) -> Tuple[SpamResult, int]:
    """
    Decoupled engine for spam analysis.
    Returns a tuple: (SpamResult, current_violation_level).
    Now also checks for bayan (duplicate content) spam.
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

    # --- Bayan check: 3 duplicates in 3 minutes ---
    if content:
        is_bayan, bayan_mute_sec = check_bayan(user_id, content, msg_type or raw_content_type)
        if is_bayan:
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
    }

def acquire_spam_lock(user_id: int):
    return user_spam_locks[user_id]

def get_spam_violation_level(board_id: str, user_id: int) -> int:
    return _spam_violations[board_id].get(user_id, {}).get('level', 0)
