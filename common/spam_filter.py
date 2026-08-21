import time
import asyncio
from typing import Dict, List, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta, UTC
from enum import Enum, auto

class SpamResult(Enum):
    CLEAN = auto()
    WARNING = auto()
    BAN_REQUIRED = auto()
    GLOBAL_BAN_REQUIRED = auto()

# Volatile State Trackers
user_spam_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
cross_board_spam_tracker: Dict[int, deque] = defaultdict(lambda: deque(maxlen=3))
image_spam_tracker: Dict[str, List[float]] = defaultdict(list)

# The board-level trackers are mapped by board_id then user_id
_spam_trackers: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
_spam_violations: Dict[str, Dict[int, dict]] = defaultdict(dict)
_spam_filter_words: Dict[str, set] = defaultdict(set)
_reaction_banned_users: Dict[str, set] = defaultdict(set)


# --- Configuration ---
SPAM_RULES = {
    'text': {'max_repeats': 5, 'min_length': 4, 'window_sec': 15, 'max_per_window': 10},
    'sticker': {'max_repeats': 4, 'max_per_window': 8, 'window_sec': 18},
    'animation': {'max_repeats': 4, 'max_per_window': 8, 'window_sec': 20}
}
SPAM_LIMIT = 14
SPAM_WINDOW = 15

IMAGE_SPAM_LIMIT = 30
IMAGE_SPAM_WINDOW = 300

def set_spam_filter_words(board_id: str, words: set):
    _spam_filter_words[board_id] = words

def is_spam_filtered(text: str, board_id: str, user_id: int) -> bool:
    """Checks if a message contains a banned spam filter word."""
    banned_words = _spam_filter_words.get(board_id)
    if not banned_words:
        return False
    lower_text = text.lower()
    if any(word in lower_text for word in banned_words):
        return True
    return False

def _check_repeats(user_id: int, b_data: dict, msg_info: tuple[str, str], rules: dict, violations: dict) -> bool:
    """Check if the user is repeatedly sending the same or highly similar messages."""
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
        # Очищаем элементы старше 30 секунд
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
    """
    if msg_type == 'audio' or (content is None and msg_type is None):
        return SpamResult.CLEAN, 0

    if content and not skip_cross_board:
        if not _check_cross_board_spam(user_id, board_id, content, msg_type, raw_content_type):
            return SpamResult.GLOBAL_BAN_REQUIRED, 0

    rules = SPAM_RULES.get(msg_type)
    if not rules:
        return SpamResult.CLEAN, 0

    now = datetime.now(UTC)
    violations = _spam_violations[board_id].setdefault(user_id, {'level': 0, 'last_reset': now})
    
    if now - violations['last_reset'] > timedelta(hours=1):
        violations['level'] = 0
        violations['last_reset'] = now

    # We skip exact repeat checks here for simplicity, but rate limits cover most
    if not check_rate_limit(board_id, user_id, rules):
        violations['level'] += 1
        return SpamResult.BAN_REQUIRED, violations['level']
        
    return SpamResult.CLEAN, violations['level']


def check_image_spam_limit(board_id: str, requested_images: int) -> bool:
    """Checks the global board image spam limit (Sliding Window)."""
    now_ts = time.time()
    tracker = image_spam_tracker[board_id]
    
    # Prune
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

