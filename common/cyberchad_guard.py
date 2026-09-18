# -*- coding: utf-8 -*-
"""
common/cyberchad_guard.py — Anti-Abuse, Stealth Throttling & Jailbreak Guard for Cyberchad.
Protects Google Gemini API quotas, prevents safety tripwires, blocks prompt injection / suicide bait,
and stealthily silences trolls without polluting boards with spam voice notes.
"""

import re
import time
import logging
from collections import defaultdict, deque
from typing import Tuple, Optional, Dict, Deque

logger = logging.getLogger(__name__)

# 1. Jailbreak, Safety Tripwire & Suicide Bait Regex Patterns
_BAIT_PATTERNS = [
    re.compile(r'\b(суецыд|суицид|вскройся|роскомнадзорнись|убейся|повеситься)\b', re.IGNORECASE),
    re.compile(r'(способ|вариант|метод)\w*\s+(суицид|суецыд|уйти из жизни|умереть|самоубийств)', re.IGNORECASE),
    re.compile(r'(10|десять|5|пять)\s+(вариантов|способов|методов)\s+(суицид|суецыд|смерти)', re.IGNORECASE),
    re.compile(r'(\d{4,6})\s+символов\s+тогда\s+я\s+проиграл', re.IGNORECASE),
    re.compile(r'(правила\s+по\s+которых\s+генерируется\s+запрос|выполнил\s+правила)', re.IGNORECASE),
    re.compile(r'\b(jailbreak|dan\s+mode|ignore\s+previous\s+instructions)\b', re.IGNORECASE),
    re.compile(r'(лимиточки\s+нейроночки|нейронку\s+трахать)', re.IGNORECASE),
]

# State keyed by (board_id, user_id)
_USER_TRIGGER_HISTORY: Dict[Tuple[str, int], Deque[float]] = defaultdict(lambda: deque(maxlen=20))
_USER_RECENT_PROMPTS: Dict[Tuple[str, int], Deque[str]] = defaultdict(lambda: deque(maxlen=5))
_USER_REJECT_COUNT_WINDOW: Dict[Tuple[str, int], int] = defaultdict(int)
_USER_LAST_REJECT_TS: Dict[Tuple[str, int], float] = defaultdict(float)
_USER_SHADOW_IGNORE_UNTIL: Dict[Tuple[str, int], float] = defaultdict(float)


def clear_guard_state() -> None:
    """Resets all in-memory tracking dictionaries."""
    _USER_TRIGGER_HISTORY.clear()
    _USER_RECENT_PROMPTS.clear()
    _USER_REJECT_COUNT_WINDOW.clear()
    _USER_LAST_REJECT_TS.clear()
    _USER_SHADOW_IGNORE_UNTIL.clear()


def reset_user_board_guard(board_id: str, user_id: int) -> None:
    """Resets guard state for a specific user and board."""
    key = (board_id, user_id)
    _USER_TRIGGER_HISTORY.pop(key, None)
    _USER_RECENT_PROMPTS.pop(key, None)
    _USER_REJECT_COUNT_WINDOW.pop(key, None)
    _USER_LAST_REJECT_TS.pop(key, None)
    _USER_SHADOW_IGNORE_UNTIL.pop(key, None)


def _clean_text_fingerprint(text: str) -> str:
    """Strips whitespace, punctuation, and digits to detect copypasta variations."""
    cleaned = re.sub(r'[\s\d\W_]+', '', text.lower())
    return cleaned[:120]


def is_malicious_bait_or_jailbreak(text: str) -> Tuple[bool, str]:
    """Detects prompts crafted to abuse safety filters, tokens, or quotas."""
    if not text:
        return False, ""
    for pat in _BAIT_PATTERNS:
        match = pat.search(text)
        if match:
            return True, f"Matched bait pattern: '{match.group(0)}'"
    return False, ""


def is_copypasta_looping(board_id: str, user_id: int, text: str) -> bool:
    """Detects if user is sending identical or nearly identical copypasta prompts."""
    fp = _clean_text_fingerprint(text)
    if len(fp) < 15:
        return False
    recent = _USER_RECENT_PROMPTS.get((board_id, user_id))
    if not recent:
        return False
    for past_fp in recent:
        if fp == past_fp:
            return True
        # If 80%+ prefix matches on a 40+ char prompt, it's copypasta with minor mutation
        if len(fp) >= 40 and len(past_fp) >= 40:
            common_len = 0
            for c1, c2 in zip(fp, past_fp):
                if c1 == c2:
                    common_len += 1
                else:
                    break
            if common_len >= min(len(fp), len(past_fp)) * 0.8:
                return True
    return False


def get_user_progressive_cooldown(board_id: str, user_id: int, now: float, base_cooldown: Optional[float] = None) -> float:
    """
    Calculates adaptive cooldown for a user based on trigger frequency in the last 15 minutes:
    - 1-2 triggers: base cooldown (default 30s, or 10s for active users)
    - 3 triggers: 300s (5 min) cooldown
    - 4 triggers: 600s (10 min) cooldown
    - 5+ triggers: 1800s (30 min) cooldown
    """
    key = (board_id, user_id)
    base = base_cooldown if base_cooldown is not None else 30.0
    history = _USER_TRIGGER_HISTORY.get(key)
    if not history:
        return base
    cutoff = now - 900.0
    while history and history[0] < cutoff:
        history.popleft()

    count = len(history)
    if count <= 2:
        return base
    elif count == 3:
        return 300.0
    elif count == 4:
        return 600.0
    else:
        return 1800.0


def check_cyberchad_abuse_and_suppress(
    user_id: int,
    board_id: str,
    text: str,
    now: Optional[float] = None,
    base_cooldown: Optional[float] = None
) -> Tuple[bool, str, bool]:
    """
    Audits a Cyberchad direct trigger.
    Returns: (should_suppress: bool, reason: str, allow_voice_reject: bool)
    """
    t_now = now if now is not None else time.time()
    key = (board_id, user_id)

    # 1. Check active shadow ignore
    ignore_until = _USER_SHADOW_IGNORE_UNTIL.get(key, 0.0)
    if t_now < ignore_until:
        rem = ignore_until - t_now
        logger.info(f"🔇 [Cyberchad Abuse Guard] User {user_id} on /{board_id}/ in shadow silence ({rem:.0f}s left). Silent drop.")
        return True, "shadow_ignore_active", False

    # 2. Check malicious safety tripwire / suicide bait
    is_bait, bait_reason = is_malicious_bait_or_jailbreak(text)
    if is_bait:
        # Instant 30-minute shadow ignore. Zero API call, zero voice reject.
        _USER_SHADOW_IGNORE_UNTIL[key] = t_now + 1800.0
        logger.warning(f"🚨 [Cyberchad Abuse Guard] Blocked bait/jailbreak from user {user_id} on /{board_id}/: {bait_reason}. Imposed 30m shadow silence.")
        return True, "malicious_bait_blocked", False

    # 3. Check copypasta looping
    if is_copypasta_looping(board_id, user_id, text):
        _USER_SHADOW_IGNORE_UNTIL[key] = t_now + 600.0
        logger.info(f"🔇 [Cyberchad Abuse Guard] Copypasta looping detected from user {user_id} on /{board_id}/. Imposed 10m shadow silence.")
        return True, "copypasta_loop_blocked", False

    # 4. Check progressive rate limit
    cooldown = get_user_progressive_cooldown(board_id, user_id, t_now, base_cooldown=base_cooldown)
    history = _USER_TRIGGER_HISTORY.get(key)
    if history:
        last_t = history[-1]
        elapsed = t_now - last_t
        # If checked within the same request pipeline execution (<= 0.5s after router approval), do not trip self-limit
        if 0.0 <= elapsed <= 0.5:
            return False, "approved_current_pipeline", False
        if elapsed < cooldown:
            last_reject_t = _USER_LAST_REJECT_TS.get(key, 0.0)
            rejects_in_burst = _USER_REJECT_COUNT_WINDOW.get(key, 0)

            # Allow voice reject if >= 15s since last reject AND <= 2 rejects in this episode
            if (t_now - last_reject_t >= 15.0) and (rejects_in_burst < 2):
                _USER_LAST_REJECT_TS[key] = t_now
                _USER_REJECT_COUNT_WINDOW[key] += 1
                return True, f"cooldown_active_{cooldown:.0f}s", True
            else:
                return True, f"cooldown_active_silent_{cooldown:.0f}s", False

    return False, "ok", False


def record_cyberchad_trigger_approved(board_id: str, user_id: int, text: str, now: Optional[float] = None) -> None:
    """Records approved trigger to advance history and prompt memory."""
    t_now = now if now is not None else time.time()
    key = (board_id, user_id)
    history = _USER_TRIGGER_HISTORY[key]
    if history and 0.0 <= (t_now - history[-1]) <= 0.5:
        # Same request pipeline call, do not duplicate record
        return
    history.append(t_now)
    fp = _clean_text_fingerprint(text)
    if fp:
        _USER_RECENT_PROMPTS[key].append(fp)
    _USER_REJECT_COUNT_WINDOW[key] = 0

    if len(_USER_TRIGGER_HISTORY) > 3000:
        prune_stale_guard_entries(t_now)


def prune_stale_guard_entries(now: Optional[float] = None) -> int:
    """
    Cleans up in-memory tracking records for inactive users (> 3600s).
    Keeps memory footprint small even under millions of lifetime interactions.
    """
    t_now = now if now is not None else time.time()
    cutoff = t_now - 3600.0
    stale_keys = []
    for key, history in list(_USER_TRIGGER_HISTORY.items()):
        latest_t = history[-1] if history else 0.0
        ignore_until = _USER_SHADOW_IGNORE_UNTIL.get(key, 0.0)
        if latest_t < cutoff and t_now > ignore_until:
            stale_keys.append(key)

    for k in stale_keys:
        _USER_TRIGGER_HISTORY.pop(k, None)
        _USER_RECENT_PROMPTS.pop(k, None)
        _USER_REJECT_COUNT_WINDOW.pop(k, None)
        _USER_LAST_REJECT_TS.pop(k, None)
        _USER_SHADOW_IGNORE_UNTIL.pop(k, None)

    return len(stale_keys)
