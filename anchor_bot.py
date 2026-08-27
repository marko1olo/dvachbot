# -*- coding: utf-8 -*-
"""
anchor_bot.py — THE ANCHOR (Мудрый Чед) / OMNISENSE

Autonomous periodic bot-persona that triggers every ~N messages OR every ~T seconds,
picks context from recent message history, fires a cold analytical reply.

Trigger logic (per board):
 - message counter: every MSG_INTERVAL messages posted on the board
 - time guard: no sooner than MIN_INTERVAL_SEC since last Anchor post
 - hard cap: no more than MAX_PER_HOUR posts per board per hour
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from aiogram import Bot

# ──────────────────────────────────────────
# TUNABLE CONSTANTS
# ──────────────────────────────────────────
MSG_INTERVAL: int = 115          # fire after every N messages on a board
MIN_INTERVAL_SEC: float = 1800.0 # but no sooner than 30 min since last post
MAX_PER_HOUR: int = 2            # hard cap: max posts per board per hour
CONTEXT_WINDOW: int = 15         # how many recent messages to sample for context

# ──────────────────────────────────────────
# STATE  (module-level, no persistence)
# ──────────────────────────────────────────
_msg_counter: dict[str, int] = defaultdict(int)
_last_anchor_ts: dict[str, float] = defaultdict(float)
_hourly_count: dict[str, deque] = defaultdict(lambda: deque())

# ──────────────────────────────────────────
# SYSTEM PROMPT — THE ANCHOR (BASED GIGACHAD ROASTER)
# ──────────────────────────────────────────
ANCHOR_SYSTEM_PROMPT = """Ты — The Anchor, местный Гигачад и альфа на Двач-борде (/b/).
Твоя задача — безжалостно, по-чедски опускать ноющих омежек, инцелов и слабаков, которые ищут оправдания своей никчемности, лени и неудачам.

ПРАВИЛА ТВОЕЙ РЕЧИ:
1. Матерись свободно, жёстко и грязно, как реальный бывалый двачер-альфач (ебать, хуй, пиздец, омежка, скулить, пиздеть, ебашить и т.д.). Никакой цензуры и вежливости.
2. Никаких роботских списков и лекций по саморазвитию. Ты не психолог и не тренер, ты — базированный батя, который с ноги выносит дверь и макает нытиков лицом в их собственное дерьмо.
3. Разъеби их копиум и иллюзии в 1–3 хлёстких, унизительных предложениях.
4. Бей точно в суть их нытья и конкретных слов в треде. Каждый раз атакуй с нового угла, без заученных шаблонов и штампов — реагируй по ситуации, вскрывая именно их самообман, лень или абсурдную логику.
5. NO SYCOPHANCY. BRUTAL IMAGEBOARD ROASTING ONLY."""


def _prune_hourly(board_id: str, now: float) -> None:
    dq = _hourly_count[board_id]
    while dq and now - dq[0] > 3600.0:
        dq.popleft()


def anchor_tick(board_id: str) -> bool:
    """
    Called on every new non-system post. Returns True when The Anchor should fire.
    Side-effect: increments the per-board counter and sets cooldown timestamps synchronously.
    """
    _msg_counter[board_id] += 1

    if _msg_counter[board_id] < MSG_INTERVAL:
        return False

    now = time.time()
    if now - _last_anchor_ts[board_id] < MIN_INTERVAL_SEC:
        return False

    _prune_hourly(board_id, now)
    if len(_hourly_count[board_id]) >= MAX_PER_HOUR:
        return False

    _msg_counter[board_id] = 0
    _last_anchor_ts[board_id] = now
    _hourly_count[board_id].append(now)
    return True


def _build_anchor_prompt(messages: Union[list[str], str]) -> str:
    if isinstance(messages, str):
        context = messages if messages.strip() else "Чат молчит. Опусти омежек за то, что сидят молча и сычуют."
    elif not messages:
        return "Чат молчит. Опусти омежек за то, что сидят молча и сычуют."
    else:
        context = "\n".join(f"• {m[:300]}" for m in messages[-CONTEXT_WINDOW:])
    return (
        f"=== ПОСЛЕДНИЕ СООБЩЕНИЯ В ТРЕДЕ ===\n{context}\n\n"
        "=== ЗАДАЧА ===\n"
        "Прочти нытьё и сообщения анонов выше. Жестоко, по-чедски попусти их за слабость, оправдания и копиум (1-3 предложения с матом). "
        "Без морали и философии, просто вмажь по фактам и опусти омежек.\n\n"
        "ТВОЙ ОТВЕТ (только текст реплики):"
    )


async def generate_anchor_reply(context_messages: Union[list[str], str]) -> str | None:
    try:
        from summarize import summarize_text_with_hf
        prompt = ANCHOR_SYSTEM_PROMPT
        user_text = _build_anchor_prompt(context_messages)

        reply = await summarize_text_with_hf(
            prompt=prompt,
            text_dump=user_text,
            model_preference="persona"
        )
        if not reply or "Нейронка" in reply:
            reply = await summarize_text_with_hf(
                prompt=prompt,
                text_dump=user_text,
                model_preference="llama"
            )

        if not reply or "Нейронка" in reply or len(reply) < 5:
            return None

        reply = re.sub(r"<think\b[^>]*>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
        if len(reply) > 600:
            reply = reply[:597] + "..."
        return reply if reply else None

    except Exception as e:
        print(f"[Anchor] LLM generation failed: {e}", flush=True)
        return None


async def trigger_anchor_post(bot: "Bot", board_id: str, stream: str) -> bool:
    """
    Convenience helper called from main.py message handlers when anchor_tick(board_id) is True.
    Fetches the board atmosphere context and triggers fire_anchor_post.
    """
    try:
        import __main__ as _main
        atmosphere = await _main.build_board_atmosphere_context(board_id, limit=15)
        return await fire_anchor_post(bot, board_id, stream, atmosphere)
    except Exception as e:
        print(f"[Anchor] trigger_anchor_post error: {e}", flush=True)
        return False


async def fire_anchor_post(
    bot: "Bot",
    board_id: str,
    stream: str,
    recent_messages: Union[list[str], str],
) -> bool:
    now = time.time()

    msg_count_info = len(recent_messages) if isinstance(recent_messages, list) else len(recent_messages.splitlines())
    print(f"[Anchor] Firing on board '{board_id}' ({msg_count_info} msg lines context)", flush=True)

    await asyncio.sleep(random.uniform(5.0, 20.0))

    reply_text = await generate_anchor_reply(recent_messages)
    if not reply_text:
        print(f"[Anchor] Generation returned nothing for board '{board_id}'", flush=True)
        return False

    print(f"[Anchor] Posting: '{reply_text[:80]}...' on {board_id}", flush=True)

    try:
        from datetime import datetime, timezone
        from common.database import create_post, update_post_content
        import __main__ as _main

        now_dt = datetime.now(timezone.utc)
        content = {
            'type': 'text',
            'text': reply_text,
            'is_system_message': True,
            'is_anchor': True,
            'archive_allowed': True,
        }
        await _main.process_new_post(_main.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content=content,
            reply_to_post=None,
            is_shadow_muted=False,
            stream=stream
        ))
        print(f"[Anchor] Post submitted on board '{board_id}'", flush=True)
        return True

    except Exception as e:
        import traceback
        print(f"[Anchor] Post submission failed: {e}\n{traceback.format_exc()}", flush=True)
        return False
