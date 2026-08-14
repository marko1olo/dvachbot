from shared_state import *
from shared_state import _persona_processed_posts
from aiogram import types
from aiogram.types import Message

import os
import time
import random
import logging
from datetime import datetime, timezone
UTC = timezone.utc
from aiogram import Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
import httpx

from common.html_utils import escape_html
from common.text_utils import clean_html_for_tg

import json
from datetime import timedelta
from common.database import get_post_by_num, get_pool, delete_post_by_num
from common.text_utils import clean_html_tags
from bot_helpers import delete_message_after_delay, check_cooldown, _activate_mode, disable_mode_after_delay
from common.task_manager import spawn_task
from post_helpers import create_post, _format_post_text, _get_author_name, _get_reply_suffix, update_post_content, format_header
from delivery_manager import enqueue_board_message

import re
import asyncio
from summarize import summarize_text_with_hf, create_telegraph_page_async
from post_processor import NewPostProcessor, NewPostContext
from text_assets import (
    CONTEXTUAL_REPLIES, CONTEXTUAL_REPLIES_EN, CONTEXTUAL_REPLIES_JP,
    ROAST_PROMPTS, ROAST_PROMPTS_EN, ROAST_PROMPTS_JP,
    SUMMARIZE_PROMPTS_BOARD, SUMMARIZE_PROMPTS_BOARD_EN, SUMMARIZE_PROMPTS_BOARD_JP,
    SUMMARIZE_PROMPTS_BOARD_SHORT, SUMMARIZE_PROMPTS_BOARD_LONG,
    SUMMARIZE_PROMPTS_BOARD_SHORT_EN, SUMMARIZE_PROMPTS_BOARD_LONG_EN
)
from shizo_mode import SCHIZO_PHRASES_START
from warhammer_mode import WH40K_PHRASES_START

import __main__ as main
ROAST_COOLDOWN = getattr(main, 'ROAST_COOLDOWN', 300)
SUMMARIZE_COOLDOWN = getattr(main, 'SUMMARIZE_COOLDOWN', 600)
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from collections import defaultdict

logger = logging.getLogger(__name__)
router = Router()

CONTEXTUAL_REPLIES_ENABLED = True
CONTEXTUAL_REPLY_COOLDOWN_SEC = 300.0
CONTEXTUAL_REPLY_DAILY_LIMIT = 5
contextual_reply_tracker = defaultdict(lambda: {"last": 0.0, "window_start": 0.0, "count": 0})
contextual_reply_stats = defaultdict(int)

def _contextual_reply_allowed(user_id: int, board_id: str) -> tuple[bool, str | None]:
    if not CONTEXTUAL_REPLIES_ENABLED:
        contextual_reply_stats["skipped_disabled"] += 1
        return False, "disabled"

    now = time.time()
    key = (board_id, user_id)
    item = contextual_reply_tracker[key]

    if CONTEXTUAL_REPLY_DAILY_LIMIT:
        window_start = float(item.get("window_start") or 0.0)
        if now - window_start >= 86400:
            item["window_start"] = now
            item["count"] = 0
        elif int(item.get("count") or 0) >= CONTEXTUAL_REPLY_DAILY_LIMIT:
            contextual_reply_stats["skipped_daily_limit"] += 1
            return False, "daily_limit"

    last_sent = float(item.get("last") or 0.0)
    if CONTEXTUAL_REPLY_COOLDOWN_SEC and now - last_sent < CONTEXTUAL_REPLY_COOLDOWN_SEC:
        contextual_reply_stats["skipped_cooldown"] += 1
        return False, "cooldown"

    item["last"] = now
    if not item.get("window_start"):
        item["window_start"] = now
    item["count"] = int(item.get("count") or 0) + 1
    contextual_reply_stats["sent"] += 1
    return True, None

async def check_and_send_contextual_reply(bot, user_id: int, text: str, board_id: str, stream: str = 'ru'):
    """
    Проверяет текст на наличие паттернов и отправляет автору личное сообщение.
    Выбирает язык ответов на основе stream.
    """
    if not text or not isinstance(text, str):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        replies_dict = CONTEXTUAL_REPLIES_EN
    elif lang == 'jp':
        replies_dict = CONTEXTUAL_REPLIES_JP
    else:
        replies_dict = CONTEXTUAL_REPLIES
    try:
        for pattern, replies in replies_dict.items():
            is_match = False
            if isinstance(pattern, str):
                if re.search(pattern, text, re.IGNORECASE):
                    is_match = True
            elif hasattr(pattern, 'search'):
                if pattern.search(text):
                    is_match = True
            if is_match:
                allowed, reason = _contextual_reply_allowed(user_id, board_id)
                if not allowed:
                    if reason:
                        runtime_logger.info(
                            "contextual_reply_skip %s",
                            json.dumps(
                                {
                                    "ts": round(time.time(), 3),
                                    "board_id": board_id,
                                    "user_id": user_id,
                                    "reason": reason,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                    return
                response_text = random.choice(replies)
                try:
                    await bot.send_message(user_id, response_text, parse_mode="HTML")
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    contextual_reply_stats["send_errors"] += 1
                    print(f"ℹ️ Не удалось отправить контекстный ответ user {user_id}: {e}")
                return
    except Exception as e:
        print(f"⛔ Ошибка в check_and_send_contextual_reply для user {user_id}: {e}")

async def transcribe_and_roast_voice_note(bot, message: Message, board_id: str = 'b', stream: str = 'ru'):
    """
    Автоматическая транскрипция ГС и кружочков (Whisper/Groq STT)
    с красивым ответом-расшифровкой в чат и уничтожающим 2ch-роастом.
    """
    if not message:
        return
    try:
        content_type = message.content_type
        if content_type not in ('voice', 'video_note'):
            return

        is_video_note = (content_type == 'video_note')
        media_obj = getattr(message, content_type, None)
        if not media_obj:
            return

        duration = getattr(media_obj, 'duration', 0)
        file_id = getattr(media_obj, 'file_id', None)

        transcript = None

        # 1. Попытка скачивания аудио и распознавания речи через Groq Whisper STT
        if file_id and bot:
            try:
                from common.token_pool import groq_pool
                file_info = await bot.get_file(file_id)
                file_bytes_io = await bot.download_file(file_info.file_path)
                audio_bytes = file_bytes_io.read() if hasattr(file_bytes_io, 'read') else file_bytes_io.getvalue()

                token = groq_pool.get_token() or os.getenv("GROQ_API_KEY")
                if token and audio_bytes:
                    ext = ".mp4" if is_video_note else ".ogg"
                    filename = f"speech{ext}"
                    headers = {"Authorization": f"Bearer {token}"}
                    files = {"file": (filename, audio_bytes, "application/octet-stream")}
                    data = {"model": "whisper-large-v3-turbo", "response_format": "json"}
                    
                    async with httpx.AsyncClient(timeout=25.0) as client:
                        resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                        if resp.status_code == 200:
                            transcript = resp.json().get("text", "").strip()
            except Exception as stt_err:
                logger.warning(f"⚠️ Ошибка STT транскрипции ГС/кружочка: {stt_err}")

        # Если STT не отработал — молча выходим, не подделываем транскрипт
        if not transcript:
            return

        # 2. Генерация уничтожающего двачевского роаста
        roast = None
        if transcript:
            try:
                prompt = (
                    "Ты — агрессивный, циничный, мизантропичный анон из /b/ Двача. "
                    "Твоя задача — жестко, уничтожающе и с ядовитым 2ch-юмором разнести автора за его сообщение (голосовуху или кружочек), "
                    "высмеяв его слова, логику, суждения и бессмысленность сказанного.\n\n"
                    "СТРОГИЕ ПРАВИЛА И ЗАПРЕТЫ:\n"
                    "1. Запрещены любые вступления, преамбулы и приветствия (например: 'Вот твоя прожарка:', 'Привет', 'Ну слушай', 'Держи').\n"
                    "2. Запрещены оговорки, морализаторство, оправдания и вежливые вводные фразы.\n"
                    "3. Запрещены кавычки вокруг ответа.\n"
                    "4. Пиши СТРОГО 1-2 емких, ядовитых, смешных предложения — сразу суть и жесткий вердикт.\n"
                    "5. Используй сочный двачерский сленг и мат по делу.\n\n"
                    f"Слова автора: «{transcript}»"
                )
                from common.token_pool import groq_pool
                token = groq_pool.get_token() or os.getenv("GROQ_API_KEY")
                if token:
                    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                    data = {
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 150,
                        "temperature": 0.8
                    }
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
                        if resp.status_code == 200:
                            raw_roast = resp.json()["choices"][0]["message"]["content"]
                            if raw_roast and len(raw_roast.strip()) > 5:
                                roast = raw_roast.strip()
            except Exception as roast_err:
                logger.warning(f"⚠️ Ошибка генерации роаста: {roast_err}")

        if not roast:
            roasts = CONTEXTUAL_REPLIES.get(r'\b(голосов[ауи]|кружоч[еик]|гс|записал|послушай|аудио)\b', [
                "засунь свое ГС себе в жопу и напиши текстом, шепелявый"
            ])
            roast = random.choice(roasts)

        icon = "📹" if is_video_note else "🎙"
        title = "Кружочек" if is_video_note else "Голосовое сообщение"

        formatted_response = (
            f"<b>{icon} {title}</b> (<i>{duration} сек</i>)\n"
            f"📝 <b>Транскрипция:</b> <i>«{escape_html(transcript)}»</i>\n\n"
            f"🔥 <b>Вердикт /b/ AI:</b>\n"
            f"{escape_html(roast)}"
        )

        try:
            await message.reply(formatted_response, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message to be replied not found" in str(e).lower() or "message to reply not found" in str(e).lower():
                await message.answer(formatted_response, parse_mode="HTML")
            else:
                raise
    except Exception as e:
        logger.error(f"❌ Ошибка в transcribe_and_roast_voice_note: {e}", exc_info=True)


def _summarize_delivery_metrics() -> dict:

    summary = {}
    for board_id in BOARDS:
        records = list(delivery_metrics.get(board_id, []))
        if not records:
            continue
        recent = records[-20:]
        seconds = [item.get("seconds", 0.0) for item in recent]
        ages = [
            item.get("post_age_sec")
            for item in recent
            if item.get("post_age_sec") is not None
        ]
        summary[board_id] = {
            "count": len(records),
            "avg_sec": round(sum(seconds) / len(seconds), 2) if seconds else 0.0,
            "max_sec": round(max(seconds), 2) if seconds else 0.0,
            "avg_age_sec": round(sum(ages) / len(ages), 2) if ages else None,
            "max_age_sec": round(max(ages), 2) if ages else None,
            "last": records[-1],
        }
    return summary

def _summarize_mode_punchup_stats() -> dict:

    modes = {}
    totals = {
        "calls": 0,
        "skipped_load": 0,
        "skipped_disabled": 0,
        "total_us": 0.0,
        "max_us": 0.0,
        "slow": 0,
    }
    for mode_key, raw in mode_punchup_stats.items():
        calls = int(raw.get("calls", 0))
        total_us = float(raw.get("total_us", 0.0))
        max_us = float(raw.get("max_us", 0.0))
        skipped_load = int(raw.get("skipped_load", 0))
        skipped_disabled = int(raw.get("skipped_disabled", 0))
        slow = int(raw.get("slow", 0))
        modes[mode_key] = {
            "calls": calls,
            "avg_us": round(total_us / calls, 2) if calls else 0.0,
            "max_us": round(max_us, 2),
            "skipped_load": skipped_load,
            "skipped_disabled": skipped_disabled,
            "slow": slow,
        }
        totals["calls"] += calls
        totals["skipped_load"] += skipped_load
        totals["skipped_disabled"] += skipped_disabled
        totals["total_us"] += total_us
        totals["max_us"] = max(totals["max_us"], max_us)
        totals["slow"] += slow
    top = sorted(modes.items(), key=lambda item: item[1]["max_us"], reverse=True)[:5]
    return {
        "calls": totals["calls"],
        "avg_us": round(totals["total_us"] / totals["calls"], 2) if totals["calls"] else 0.0,
        "max_us": round(totals["max_us"], 2),
        "skipped_load": totals["skipped_load"],
        "skipped_disabled": totals["skipped_disabled"],
        "slow": totals["slow"],
        "top": top,
        "by_mode": modes,
    }

def _summarize_live_queue_ages(queue_sizes: dict) -> dict:

    now = time.time()
    by_board = {}
    oldest = []
    for board_id, queue in message_queues.items():
        ages, oldest_age, oldest_post = _process_board_queue(queue, now)
        if queue_sizes.get(board_id, 0) or ages:
            info = {"size": queue_sizes.get(board_id, 0)}
            if ages:
                info.update({
                    "oldest_age_sec": round(max(ages), 1),
                    "avg_age_sec": round(sum(ages) / len(ages), 1),
                    "oldest_post": oldest_post,
                })
                oldest.append((board_id, info["oldest_age_sec"], oldest_post))
            by_board[board_id] = info

    in_flight = _process_in_flight_deliveries(now)

    return {
        "by_board": by_board,
        "oldest": sorted(oldest, key=lambda item: item[1], reverse=True)[:5],
        "in_flight": in_flight,
    }

async def build_reply_chain_context(target_post_num: int, max_depth: int = 25) -> str:
    """
    Строит цепочку ответов от предков к целевому посту (до 25 уровней вглубь).
    Возвращает отформатированный хронологический контекст для LLM.
    """
    if not target_post_num:
        return ""
        
    chain = []
    current_num = target_post_num
    visited = set()
    
    while current_num and current_num not in visited and len(chain) < max_depth:
        visited.add(current_num)
        post_data = None
        async with storage_lock:
            post_data = messages_storage.get(current_num)
        if not post_data:
            post_data = await get_post_by_num(current_num)
            
        if not post_data:
            break
            
        content = post_data.get('content', {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                content = {'text': content}
                
        raw_text = content.get('text') or content.get('caption') or ""
        clean_text = clean_html_tags(raw_text).replace('\n', ' ').strip()
        if not clean_text and content.get('type'):
            clean_text = f"[{content.get('type')}]"
            
        author_id = post_data.get('author_id', -1)
        is_bot = (author_id == 0 or author_id == 1488148800)
        
        reply_to = post_data.get('reply_to_post_num') or post_data.get('reply_to') or content.get('reply_to_post')
        
        chain.append({
            'post_num': current_num,
            'is_bot': is_bot,
            'author_id': author_id,
            'text': clean_text,
            'reply_to': reply_to
        })
        
        current_num = reply_to

    if not chain:
        return ""

    chain.reverse()
    
    lines = []
    for item in chain:
        if item['is_bot']:
            sender = "ТЫ (Персона)"
        else:
            anon_hash = str(abs(hash(str(item.get('author_id', 'anon')))))[:4]
            sender = f"Анон #{anon_hash}"
        reply_prefix = f" (в ответ на #{item['reply_to']})" if item['reply_to'] else ""
        lines.append(f"• #{item['post_num']} [{sender}]{reply_prefix}: {item['text'][:300]}")
        
    return "\n".join(lines)

async def schedule_persona_reply(bot, board_id: str, target_post_num: int, context_text: str, stream: str, is_admin_trigger: bool = False, photo_file_id: str = None, is_dialogue: bool = False):
    try:
        from site_tgach.persona_bot import generate_anon_reply, is_valid_for_persona

        if target_post_num and target_post_num in _persona_processed_posts:
            print(f"ℹ️ [Persona Debounce] Reply for post #{target_post_num} already processed, skipping duplicate trigger.")
            return
        if target_post_num:
            _persona_processed_posts.add(target_post_num)
            if len(_persona_processed_posts) > 3000:
                _persona_processed_posts.clear()

        now_ts = time.time()

        attach_file_id = None
        attach_media_type = None

        if not photo_file_id and target_post_num and target_post_num in messages_storage:
            p_data = messages_storage[target_post_num]
            c = p_data.get('content', {})
            m_type = c.get('type')
            if m_type == 'image': m_type = 'photo'
            if m_type in {'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document'}:
                photo_file_id = c.get('thumbnail_file_id') or c.get('file_id')
                attach_file_id = c.get('file_id')
                attach_media_type = m_type
            elif m_type == 'media_group' and c.get('media'):
                for m in c.get('media', []):
                    if m.get('file_id'):
                        photo_file_id = m.get('thumbnail_file_id') or m.get('file_id')
                        attach_file_id = m.get('file_id')
                        sub_type = m.get('type') or 'photo'
                        attach_media_type = 'photo' if sub_type == 'image' else sub_type
                        break
            # Если в самом посте нет картинки, проверим родительский пост, на который отвечают
            if not photo_file_id:
                reply_to_num = p_data.get('reply_to_post_num') or p_data.get('reply_to')
                if reply_to_num and reply_to_num in messages_storage:
                    parent_c = messages_storage[reply_to_num].get('content', {})
                    pm_type = parent_c.get('type')
                    if pm_type == 'image': pm_type = 'photo'
                    if pm_type in {'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document'}:
                        photo_file_id = parent_c.get('thumbnail_file_id') or parent_c.get('file_id')
                        attach_file_id = parent_c.get('file_id')
                        attach_media_type = pm_type
                    elif pm_type == 'media_group' and parent_c.get('media'):
                        for m in parent_c.get('media', []):
                            if m.get('file_id'):
                                photo_file_id = m.get('thumbnail_file_id') or m.get('file_id')
                                attach_file_id = m.get('file_id')
                                sub_type = m.get('type') or 'photo'
                                attach_media_type = 'photo' if sub_type == 'image' else sub_type
                                break

        vision_desc = None
        if photo_file_id and not (context_text and "[ИЗОБРАЖЕНИЕ:" in context_text):
            vision_desc = await analyze_telegram_photo(bot, photo_file_id, caption=context_text)
            if vision_desc:
                img_tag = f"\n[ИЗОБРАЖЕНИЕ: {vision_desc}]"
                context_text = (context_text or "") + img_tag

        if not is_admin_trigger and not is_valid_for_persona(context_text):
            return
            
        await asyncio.sleep(random.uniform(12.0, 35.0) if not is_admin_trigger else 0)
        
        print(f"🤖 [Persona] Requesting reply generation for post {target_post_num} on {board_id} (is_dialogue={is_dialogue})...")
        
        # Строим общую атмосферу доски (25 последних постов)
        atmosphere_context = await build_board_atmosphere_context(board_id, exclude_post_num=target_post_num, limit=25)
        
        # Строим контекст всей цепочки ответов (до 25 уровней)
        chain_context = await build_reply_chain_context(target_post_num, max_depth=25)
        if not chain_context:
            chain_context = context_text
        elif photo_file_id and vision_desc and "[ИЗОБРАЖЕНИЕ:" not in chain_context:
            chain_context += f"\n[ИЗОБРАЖЕНИЕ: {vision_desc}]"

        replies = await generate_anon_reply(
            context_text=chain_context,
            target_post=context_text,
            is_dialogue=is_dialogue,
            atmosphere_text=atmosphere_context
        )
        
        # Гарантия от "замалчивания": если юзер вел диалог с ботом, но генератор сбросился — даем аноновский фаллбэк-ответ
        if not replies and is_dialogue:
            print(f"⚠️ [Persona] Dialogue fallback for post {target_post_num} (preventing silence).")
            fallback_options = [
                "Понял тебя, анон.",
                "Ладно, проехали.",
                "Хз даже чё сказать на это, анон.",
                "Ну допустим.",
                "Ладно, забей.",
                "Останемся при своих, анон."
            ]
            replies = [random.choice(fallback_options)]

        if not replies:
            print(f"⚠️ [Persona] Generation failed or returned empty for post {target_post_num}.")
            return
            
        print(f"✅ [Persona] Successfully generated {len(replies)} replies for post {target_post_num}.")
            
        for i, text in enumerate(replies):
            now_dt = datetime.now(UTC)
            # Прикрепляем картинку только в 30% случаев чтобы не спамить медиа
            attach_media = attach_file_id and attach_media_type in {'photo', 'video', 'animation', 'gif'} and i == 0 and random.random() < 0.30
            content = {
                'type': attach_media_type if attach_media else 'text',
                'is_system_message': True,
                'archive_allowed': True
            }
            if attach_media:
                content['caption'] = text
                content['file_id'] = attach_file_id
            else:
                content['text'] = text
                
            pnum = await create_post(
                board_id=board_id,
                author_id=0,
                content=content,
                timestamp=now_dt.timestamp(),
                is_from_site=False, stream=stream,
                reply_to=target_post_num if target_post_num else None
            )
            if pnum:
                header = await format_header(board_id, pnum, 0)
                content['header'] = f"### АНОН ###\n{header}" if stream == 'ru' else f"### ANON ###\n{header}"
                await update_post_content(pnum, content)
                async with storage_lock:
                    messages_storage[pnum] = {
                        'author_id': 0, 'timestamp': now_dt, 
                        'content': content, 'board_id': board_id,
                        'reply_to_post_num': target_post_num if target_post_num else None
                    }
                await NewPostProcessor(NewPostContext(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content=content,
                    reply_to_post=target_post_num if target_post_num else None,
                    is_shadow_muted=False,
                    stream=stream
                )).execute()
            if len(replies) > 1:
                await asyncio.sleep(random.uniform(1.0, 3.0))
    except Exception as e:
        print(f"Error in schedule_persona_reply: {e}")

@router.message(Command("schizo", "shiza", "shizo", "shiz", "durka"))
async def cmd_schizo(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int':
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(SCHIZO_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### ORDERLY ###"
    elif stream == 'jp': prefix = "### 看護師 ###"
    else: prefix = "### САНИТАР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'schizo_mode')
    disable_task = spawn_task(disable_mode_after_delay(300, board_id, 'schizo_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass

@router.message(Command("wh40k", "waha", "warhammer", "warhamer"))
async def cmd_wh40k(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(WH40K_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### INQUISITOR ###"
    elif stream == 'jp': prefix = "### 異端審問官 ###"
    else: prefix = "### ИНКВИЗИТОР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'warhammer_mode')
    disable_task = spawn_task(disable_mode_after_delay(315, board_id, 'warhammer_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass

def _tg_safe_truncate(text: str, max_utf16: int = 4000) -> str:
    """Truncate text to fit Telegram's UTF-16 code unit limit.
    
    Telegram counts message length in UTF-16 code units:
    - ASCII chars: 1 unit each
    - Cyrillic/CJK/most Unicode > U+FFFF: 2 units each
    - Emoji/surrogate pairs: 2 units each
    max_utf16=4000 gives ~96 unit headroom under Telegram's 4096 hard limit.
    """
    units = 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        units += 2 if cp > 0xFFFF or 0x0400 <= cp <= 0x04FF or 0x4E00 <= cp <= 0x9FFF else 1
        if units > max_utf16:
            return text[:i] + "…"
    return text

async def get_board_chunk(board_id: str, hours: int = 6, thread_id: str | None = None, lang: str | None = None) -> str:

    now = datetime.now(UTC)
    time_threshold = now - timedelta(hours=hours)
    lines = []
    
    async with storage_lock:
        if thread_id:
            b_data = board_data[board_id]
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info:
                return ""
            thread_post_nums = set(thread_info.get('posts', []))
            post_iterator = [p for p_num, p in messages_storage.items() if p_num in thread_post_nums]
            time_threshold = datetime.min.replace(tzinfo=UTC)
            # Сортируем сообщения треда по времени
            post_iterator.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
        else:
            board_posts = [p for p in messages_storage.values() if p.get('board_id') == board_id and p.get('author_id') != 0]
            board_posts.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
            
            posts_in_last_6h = [p for p in board_posts if p.get('timestamp', now) >= time_threshold]
            count_6h = len(posts_in_last_6h)
            
            # 150-200 последних сообщений либо 6 часов (выбираем оптимальный диапазон)
            if count_6h < 150:
                target_posts = board_posts[-150:]
            elif count_6h > 200:
                target_posts = board_posts[-200:]
            else:
                target_posts = posts_in_last_6h
            post_iterator = target_posts
            time_threshold = datetime.min.replace(tzinfo=UTC)
    for post in post_iterator:
        try:
            if post.get('board_id') != board_id:
                continue
            if post.get('timestamp', now) < time_threshold:
                continue
            if post.get('author_id') == 0: # Игнорируем системные сообщения
                continue
            content = post.get('content', {})
            msg_type = content.get('type', 'text')
            
            text = _format_post_text(content, msg_type)
            if text:
                name = _get_author_name(post, content, board_id, lang)
                reply_suffix = _get_reply_suffix(post, content, board_id, lang)
                lines.append(f"{name}{reply_suffix}: {text}")
        except Exception as e:
            print(f"[summarize] Error while chunking post: {e}")
    # Accumulate lines from newest to oldest up to 35000 characters to avoid split lines
    total_len = 0
    limited_lines = []
    for line in reversed(lines):
        # We also collapse multiple newlines if any, but our lines are single messages anyway
        line_clean = re.sub(r'\n{2,}', '\n', line).strip()
        if not line_clean:
            continue
        if total_len + len(line_clean) + 1 > 35000:
            break
        limited_lines.append(line_clean)
        total_len += len(line_clean) + 1
    
    limited_lines.reverse()
    cleaned_chunk = "\n".join(limited_lines)
    
    context_name = f"thread {thread_id}" if thread_id else f"board {board_id}"
    logger.debug(f"[summarize] Chunk for {context_name} built, len={len(cleaned_chunk)}")
    return cleaned_chunk

async def build_board_atmosphere_context(board_id: str, exclude_post_num: int = None, limit: int = 25) -> str:
    """
    Получает последние посты на доске для понимания текущей атмосферы чата (до 25 последних сообщений).
    """
    recent_posts = []
    async with storage_lock:
        stored_nums = sorted([k for k, v in messages_storage.items() if v.get('board_id') == board_id], reverse=True)
        for pnum in stored_nums:
            if pnum == exclude_post_num:
                continue
            post_data = messages_storage.get(pnum)
            if post_data:
                recent_posts.append((pnum, post_data))
            if len(recent_posts) >= limit:
                break
                
    if len(recent_posts) < limit:
        db = await get_pool()
        needed = limit - len(recent_posts)
        exclude_clause = f"AND post_num != {exclude_post_num}" if exclude_post_num else ""
        query = f"SELECT post_num, author_id, content, timestamp FROM Posts WHERE board_id = ? {exclude_clause} ORDER BY post_num DESC LIMIT ?"
        try:
            async with db.execute(query, (board_id, needed)) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    pnum, author_id, content_raw, ts = row
                    if any(p[0] == pnum for p in recent_posts):
                        continue
                    try:
                        content = json.loads(content_raw)
                    except Exception:
                        content = {'text': str(content_raw)}
                    recent_posts.append((pnum, {
                        'author_id': author_id,
                        'content': content
                    }))
        except Exception as e:
            print(f"Error fetching atmosphere posts: {e}")

    recent_posts.sort(key=lambda x: x[0])
    
    lines = []
    for pnum, pdata in recent_posts:
        content = pdata.get('content', {})
        raw_text = content.get('text') or content.get('caption') or ""
        clean_text = clean_html_tags(raw_text).replace('\n', ' ').strip()
        if not clean_text:
            continue
        sender = "БОТ (Персона)" if pdata.get('author_id') in (0, 1488148800) else "ЮЗЕР (Анон)"
        lines.append(f"• #{pnum} [{sender}]: {clean_text[:250]}")
        
    return "\n".join(lines)

def adjust_prompt_paragraphs(prompt: str, count: int, lang: str = 'ru') -> str:
    import re
    if lang == 'ru':
        if count % 10 == 1 and count % 100 != 11:
            p_word = "абзац"
            p_word_adj = "крупный абзац"
        elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            p_word = "абзаца"
            p_word_adj = "крупных абзаца"
        else:
            p_word = "абзацев"
            p_word_adj = "крупных абзацев"
        
        prompt = re.sub(r'объемом ровно в 1-2 абзаца', f'объемом ровно в {count} {p_word}', prompt)
        prompt = re.sub(r'ровно 3-4 абзаца', f'ровно {count} {p_word}', prompt)
        prompt = re.sub(r'строго 6-8 крупных абзацев', f'строго {count} {p_word_adj}', prompt)
        prompt = re.sub(r'не менее 6-8 крупных, содержательных абзацев с подробностями', f'ровно {count} {p_word_adj} с подробностями', prompt)
        prompt = re.sub(r'1-2 предложения', f'ровно {count} {p_word}', prompt)
        prompt = re.sub(r'ультра-короткую, циничную прожарку', f'циничную прожарку', prompt)
        
        prompt += f"\n\nВАЖНО: Твой отчет должен быть структурированным и состоять СТРОГО из {count} абзацев (не больше и не меньше!). Каждый абзац должен быть содержательным, плотным и отделен от других пустой строкой. Не используй Markdown-разметку (только HTML, например <b>, <i>)."
    elif lang == 'en':
        p_word = "paragraphs" if count > 1 else "paragraph"
        prompt = re.sub(r'1-2 sentences', f'{count} {p_word}', prompt)
        prompt = re.sub(r'at least 6-8 heavy, informative paragraphs', f'exactly {count} heavy, informative {p_word}', prompt)
        prompt = re.sub(r'3-4 paragraphs', f'exactly {count} {p_word}', prompt)
        
        prompt += f"\n\nIMPORTANT: Your report must be structured and consist of EXACTLY {count} paragraphs (no more, no less!). Each paragraph must be informative, dense, separated by a blank line, and use only HTML formatting (no Markdown)."
    elif lang == 'jp':
        prompt = re.sub(r'3行で', f'{count}段落で', prompt)
        prompt += f"\n\n重要：要約は必ず正確に{count}段落で構成してください（多くても少なくてもいけません！）。各段落は空白行で区切られている必要があります。Markdownは使用せず、HTMLタグのみを使用してください。"
        
    return prompt

async def analyze_telegram_photo(bot, photo_file_id: str, caption: str = None) -> str | None:
    """
    Скачивает фото из Телеграма и анализирует его через Vision.
    Возвращает краткое описание содержимого на русском языке.
    """
    try:
        from site_tgach.vision import describe_image
        import tempfile, os
        file_info = await bot.get_file(photo_file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download_file(file_info.file_path, tmp_path)
        
        logger.info(f"🖼 [TG_BOT] Downloading Telegram photo file_id='{photo_file_id[:15]}...' for Persona analysis")
        description = await describe_image(tmp_path, caption=caption, is_passive=False, source="TG_BOT")
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if description:
            logger.info(f"✅ [TG_BOT] Photo analysis complete (desc='{description[:60]}...')")
        else:
            logger.warning(f"⚠️ [TG_BOT] Photo analysis produced no description.")
        return description
    except Exception as e:
        logger.error(f"⚠️ [TG_BOT] Telegram Vision Error: {e}", exc_info=True)
        return None
