# -*- coding: utf-8 -*-
"""
CyberChad Activation Debouncer & Message Accumulator.
Implements the 15-second debounce window directive:
- When user summons CyberChad (direct call / trigger), does not reply immediately.
- Opens an accumulation window up to 15 seconds.
- If the same user on the same board writes 1-2 additional messages within this window,
  accumulates them into a unified context batch.
- When timer expires (or user went silent for SILENCE_TIMEOUT, or max batch of 3 messages reached),
  flushes the batch and dispatches a single unified CyberChad response.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# User directive constants:
# Wait up to 15 seconds after activation
MAX_DEBOUNCE_SECONDS: float = 15.0
# Silence delay: if user stopped typing for 4.0 seconds, flush early
DEFAULT_SILENCE_SECONDS: float = 4.0
# Maximum messages in batch: 1 initial summon + up to 2 follow-up messages = 3
MAX_BATCH_MESSAGES: int = 3


@dataclass
class CyberchadDebounceItem:
    post_num: int
    text: str
    reply_to_post: Optional[int]
    timestamp: float


@dataclass
class CyberchadDebounceSession:
    board_id: str
    user_id: int
    bot: Any
    stream: str
    created_at: float
    last_message_at: float
    messages: list[CyberchadDebounceItem] = field(default_factory=list)
    initial_reply_to: Optional[int] = None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    timer_task: Optional[asyncio.Task] = None
    flushed: bool = False
    max_wait_seconds: float = MAX_DEBOUNCE_SECONDS
    silence_seconds: float = DEFAULT_SILENCE_SECONDS
    max_messages: int = MAX_BATCH_MESSAGES


# Global registry of active debounce sessions: (board_id, user_id) -> CyberchadDebounceSession
_DEBOUNCE_SESSIONS: dict[tuple[str, int], CyberchadDebounceSession] = {}
_DEBOUNCE_LOCK: asyncio.Lock = asyncio.Lock()


def is_user_debouncing(board_id: str, user_id: int) -> bool:
    """Checks whether an active debounce session exists for (board_id, user_id)."""
    session = _DEBOUNCE_SESSIONS.get((board_id, user_id))
    return bool(session and not session.flushed)


def get_debounce_session(board_id: str, user_id: int) -> Optional[CyberchadDebounceSession]:
    """Returns the active debounce session if present."""
    session = _DEBOUNCE_SESSIONS.get((board_id, user_id))
    if session and not session.flushed:
        return session
    return None


async def add_message_to_debounce(
    board_id: str,
    user_id: int,
    post_num: int,
    text: str,
    reply_to_post: Optional[int] = None,
    now: Optional[float] = None
) -> bool:
    """
    Appends a follow-up message to an active debounce session.
    Returns True if absorbed into the batch, False if no active session.
    """
    now_ts = now if now is not None else time.time()
    async with _DEBOUNCE_LOCK:
        session = _DEBOUNCE_SESSIONS.get((board_id, user_id))
        if not session or session.flushed:
            return False

        # Add message to batch
        item = CyberchadDebounceItem(
            post_num=post_num,
            text=text,
            reply_to_post=reply_to_post,
            timestamp=now_ts
        )
        session.messages.append(item)
        session.last_message_at = now_ts
        if reply_to_post and not session.initial_reply_to:
            session.initial_reply_to = reply_to_post

        logger.info(
            f"📥 [Cyberchad Debounce] Absorbed message #{post_num} from user {user_id} on /{board_id}/ "
            f"(batch size: {len(session.messages)}/{session.max_messages})"
        )

        # Notify the waiting worker task
        session.event.set()
        return True


def format_debounce_batch_text(messages: list[CyberchadDebounceItem]) -> str:
    """
    Formats the accumulated batch of messages into a single unified text.
    If 1 message: returns the text as is.
    If multiple messages: builds a coherent sequence of points from the author.
    """
    if not messages:
        return ""
    if len(messages) == 1:
        return messages[0].text.strip()

    # Multiple messages from same user within the 15s window:
    # Format each post so CyberChad understands the progression of user's arguments
    formatted_parts = []
    for msg in messages:
        clean_txt = msg.text.strip()
        if clean_txt:
            formatted_parts.append(f"• #{msg.post_num}: {clean_txt}")

    return "\n".join(formatted_parts)


async def _debounce_worker(
    session: CyberchadDebounceSession,
    on_flush: Callable[[CyberchadDebounceSession, str, int, Optional[int]], Coroutine[Any, Any, None]]
) -> None:
    """
    Async timer worker:
    Waits up to max_wait_seconds from creation, or silence_seconds after last message.
    Flushes immediately if max_messages reached.
    """
    try:
        while True:
            now = time.time()
            time_from_start = now - session.created_at
            time_from_last = now - session.last_message_at

            remaining_max = session.max_wait_seconds - time_from_start
            remaining_silence = session.silence_seconds - time_from_last

            # 1. Hard maximum window reached (15.0s)
            if remaining_max <= 0:
                logger.info(
                    f"⏰ [Cyberchad Debounce] Max window ({session.max_wait_seconds}s) reached for user {session.user_id} on /{session.board_id}/. Flushing."
                )
                break

            # 2. Maximum accumulated messages reached (1 initial + 2 follow-ups = 3)
            if len(session.messages) >= session.max_messages:
                logger.info(
                    f"🚀 [Cyberchad Debounce] Max messages ({session.max_messages}) reached for user {session.user_id} on /{session.board_id}/. Flushing immediately."
                )
                break

            # 3. User went silent after last message
            if remaining_silence <= 0:
                logger.info(
                    f"🤫 [Cyberchad Debounce] User {session.user_id} went silent ({session.silence_seconds}s inactivity). Flushing batch ({len(session.messages)} msgs)."
                )
                break

            wait_timeout = min(remaining_max, remaining_silence)

            session.event.clear()
            try:
                await asyncio.wait_for(session.event.wait(), timeout=max(0.01, wait_timeout))
            except asyncio.TimeoutError:
                pass

    except asyncio.CancelledError:
        logger.debug(f"[Cyberchad Debounce] Worker cancelled for user {session.user_id} on /{session.board_id}/")
    except Exception as e:
        logger.error(f"❌ [Cyberchad Debounce] Error in debounce worker: {e}", exc_info=True)
    finally:
        await flush_session(session, on_flush)


async def flush_session(
    session: CyberchadDebounceSession,
    on_flush: Callable[[CyberchadDebounceSession, str, int, Optional[int]], Coroutine[Any, Any, None]]
) -> None:
    """
    Flushes the debounce session, removing it from registry and invoking on_flush.
    """
    async with _DEBOUNCE_LOCK:
        if session.flushed:
            return
        session.flushed = True
        key = (session.board_id, session.user_id)
        if _DEBOUNCE_SESSIONS.get(key) is session:
            _DEBOUNCE_SESSIONS.pop(key, None)

    if not session.messages:
        return

    latest_msg = session.messages[-1]
    target_post_num = latest_msg.post_num
    reply_to_post = session.initial_reply_to or next(
        (m.reply_to_post for m in session.messages if m.reply_to_post), None
    )
    combined_text = format_debounce_batch_text(session.messages)

    logger.info(
        f"🔥 [Cyberchad Debounce] Dispatching unified CyberChad intervention for user {session.user_id} "
        f"on /{session.board_id}/ (posts: {[m.post_num for m in session.messages]}, target=#{target_post_num})"
    )

    try:
        await on_flush(session, combined_text, target_post_num, reply_to_post)
    except Exception as err:
        logger.error(f"❌ [Cyberchad Debounce] Error executing on_flush: {err}", exc_info=True)


def start_debounce_session(
    bot: Any,
    board_id: str,
    user_id: int,
    post_num: int,
    text: str,
    reply_to_post: Optional[int] = None,
    stream: str = "ru",
    on_flush: Optional[Callable[[CyberchadDebounceSession, str, int, Optional[int]], Coroutine[Any, Any, None]]] = None,
    max_wait_seconds: float = MAX_DEBOUNCE_SECONDS,
    silence_seconds: float = DEFAULT_SILENCE_SECONDS,
    max_messages: int = MAX_BATCH_MESSAGES,
    now: Optional[float] = None
) -> CyberchadDebounceSession:
    """
    Initializes a new debounce session for (board_id, user_id) and schedules the worker task.
    """
    now_ts = now if now is not None else time.time()
    session = CyberchadDebounceSession(
        board_id=board_id,
        user_id=user_id,
        bot=bot,
        stream=stream,
        created_at=now_ts,
        last_message_at=now_ts,
        initial_reply_to=reply_to_post,
        max_wait_seconds=max_wait_seconds,
        silence_seconds=silence_seconds,
        max_messages=max_messages,
        messages=[CyberchadDebounceItem(
            post_num=post_num,
            text=text,
            reply_to_post=reply_to_post,
            timestamp=now_ts
        )]
    )

    _DEBOUNCE_SESSIONS[(board_id, user_id)] = session

    if on_flush:
        session.timer_task = asyncio.create_task(_debounce_worker(session, on_flush))

    logger.info(
        f"⏳ [Cyberchad Debounce] Started 15s debounce window for user {user_id} on /{board_id}/ "
        f"(initial post #{post_num})"
    )
    return session


def clear_all_debounce_sessions() -> None:
    """Clears all sessions (useful for tests and cleanup)."""
    for session in list(_DEBOUNCE_SESSIONS.values()):
        session.flushed = True
        if session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()
    _DEBOUNCE_SESSIONS.clear()
