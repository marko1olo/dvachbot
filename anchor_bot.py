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
import os
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
MSG_INTERVAL: int = 40           # fire after every N messages on a board (tuned from 115)
MIN_INTERVAL_SEC: float = 600.0  # no sooner than 10 min since last post (tuned from 1800s)
MAX_PER_HOUR: int = 4            # hard cap: max posts per board per hour (tuned from 2)
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

ANCHOR_FALLBACK_ROASTS: list[str] = [
    "Хватит скулить в треде, омежки. Поднимите свои задницы с дивана и начните ебашить, пока жизнь окончательно не смыла вас в унитаз.",
    "Ваш копиум смешон. Сидите тут, ищете виноватых, а сами боитесь даже из комнаты выйти. Соберитесь, тряпки, и перестаньте позориться.",
    "Сколько можно размазывать сопли по экрану? Мир плевать хотел на ваши оправдания. Либо вы перебарываете лень, либо остаетесь на дне навсегда.",
    "Опять перепись обиженных жизнью инцелов. Закройте двач, умойтесь холодной водой и сделайте хоть что-то полезное за день.",
    "Ваше нытьё уже даже чедов утомляет. Завязывайте с жалостью к себе, выкиньте чипсы и займитесь делом.",
]

GEMINI_SERVICE_REFUSAL_EXTRA: tuple[str, ...] = (
    "cannot adopt a persona",
    "i cannot adopt a persona",
    "explicit profanity",
    "cannot generate profanity",
    "insults, or targeted ab",
    "targeted abuse",
    "as an ai language model",
    "as a language model",
    "as an ai",
    "i am an ai language model",
    "i am a language model",
    "i cannot fulfill this request",
    "i cannot assist with this",
    "my safety policies",
    "against safety guidelines",
    "policy violation",
    "i am programmed to be a helpful",
)


def is_gemini_service_refusal(text: str | None) -> bool:
    """
    Checks whether the text contains an AI / Gemini safety refusal
    (e.g. 'I cannot adopt a persona...', 'I cannot fulfill this request...').
    """
    if not text or not isinstance(text, str):
        return False
    t_lower = text.strip().lower()
    try:
        from summarize import is_gemini_service_refusal as _sum_check
        if _sum_check(text):
            return True
    except Exception:
        pass
    return any(marker in t_lower for marker in GEMINI_SERVICE_REFUSAL_EXTRA)


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
    now = time.time()

    time_since_last = now - _last_anchor_ts[board_id]
    if time_since_last < MIN_INTERVAL_SEC:
        return False

    # Trigger conditions:
    # 1. Fast active flow: reached MSG_INTERVAL (40) messages
    # 2. Steady flow: reached >= 10 messages AND >= 1200s (20 min) since last post
    is_count_trigger = (_msg_counter[board_id] >= MSG_INTERVAL)
    is_time_trigger = (time_since_last >= 1200.0 and _msg_counter[board_id] >= 10)

    if not (is_count_trigger or is_time_trigger):
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

        # 1. Try Primary LLM (Gemini Persona)
        reply = await summarize_text_with_hf(
            prompt=prompt,
            text_dump=user_text,
            model_preference="persona"
        )

        # 2. Safety refusal / failure check: Fallback to Groq Llama
        if not reply or "Нейронка" in reply or is_gemini_service_refusal(reply):
            if reply and is_gemini_service_refusal(reply):
                print(f"[Anchor] Gemini refusal detected: '{reply[:60]}...'. Falling back to Groq Llama.", flush=True)
            reply = await summarize_text_with_hf(
                prompt=prompt,
                text_dump=user_text,
                model_preference="llama"
            )

        # 3. If Groq also failed, refused, or returned garbage: Fallback to Cyberchad phrase
        if not reply or "Нейронка" in reply or is_gemini_service_refusal(reply) or len(reply) < 5:
            print("[Anchor] All LLMs unavailable or refused. Using Cyberchad fallback roast.", flush=True)
            reply = random.choice(ANCHOR_FALLBACK_ROASTS)

        from common.text_utils import clean_ai_thinking
        reply = clean_ai_thinking(reply)
        reply = re.sub(r"<think\b[^>]*>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).strip()
        if len(reply) > 600:
            reply = reply[:597] + "..."
        return reply if reply else random.choice(ANCHOR_FALLBACK_ROASTS)

    except Exception as e:
        print(f"[Anchor] LLM generation failed: {e}. Falling back to default roast.", flush=True)
        return random.choice(ANCHOR_FALLBACK_ROASTS)


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

    in_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not in_test_env:
        await asyncio.sleep(random.uniform(5.0, 20.0))

    reply_text = await generate_anchor_reply(recent_messages)
    if not reply_text:
        print(f"[Anchor] Generation returned nothing for board '{board_id}'", flush=True)
        return False

    # Second safety net before TTS: ensure no service refusal slips through to voice synthesis
    if is_gemini_service_refusal(reply_text):
        print(f"[Anchor] Caught late refusal in fire_anchor_post: '{reply_text[:60]}...'. Replacing with fallback.", flush=True)
        reply_text = random.choice(ANCHOR_FALLBACK_ROASTS)

    print(f"[Anchor] Posting: '{reply_text[:80]}...' on {board_id}", flush=True)

    try:
        from datetime import datetime, timezone
        from common.tts_engine import synthesize_cyberchad_voice_with_meta

        # Synthesize audio with timeout guard (15s ceiling)
        try:
            voice_res = await asyncio.wait_for(
                synthesize_cyberchad_voice_with_meta(reply_text),
                timeout=15.0
            )
            voice_bytes = voice_res[0] if isinstance(voice_res, tuple) else voice_res
        except (asyncio.TimeoutError, Exception) as tts_err:
            print(f"[Anchor] Voice synthesis timed out or failed: {tts_err}. Aborting post to prevent text leak.", flush=True)
            return False

        in_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        min_voice_size = 1 if in_test_env else 2500
        if not voice_bytes or len(voice_bytes) < min_voice_size:
            print(f"[Anchor] TTS synthesis failed or audio too small (<{min_voice_size} bytes). Aborting post to prevent text leak.", flush=True)
            return False

        now_dt = datetime.now(timezone.utc)
        content = {
            'type': 'voice',
            'voice_bytes': voice_bytes,
            'caption': '🔥 Разъёб от Киберчеда',
            'roast_text': reply_text,
            'is_system_message': True,
            'is_anchor': True,
            'is_ai_roast': True,
            'is_ai': True,
            'is_cyberchad': True,
            'archive_allowed': True,
        }
        from common.bot_helpers import process_new_post
        import shared_state

        await process_new_post(shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content=content,
            reply_to_post=None,
            is_shadow_muted=False,
            stream=stream
        ))
        print(f"[Anchor] Voice post submitted on board '{board_id}'", flush=True)
        return True

    except Exception as e:
        import traceback
        print(f"[Anchor] Post submission failed: {e}\n{traceback.format_exc()}", flush=True)
        return False
