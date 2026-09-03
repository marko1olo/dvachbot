import shared_state
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
from common.text_utils import clean_html_tags, clean_ai_thinking, strip_thinking_tags
from bot_helpers import delete_message_after_delay, check_cooldown, _activate_mode, disable_mode_after_delay
from common.task_manager import spawn_task
import operator
from post_helpers import (
    create_post, _format_post_text, _format_media_context, _MEDIA_DESC_CACHE,
    _get_author_name, _get_reply_suffix, _get_cached_anon_name, RE_MULTI_NEWLINES,
    _MEDIA_ERROR_TAGS, update_post_content, format_header
)
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
runtime_logger = getattr(shared_state, 'runtime_logger', logging.getLogger("runtime"))

# Idempotency guard: prevents the same voice/audio file_id from being roasted multiple times
# concurrently (e.g. from gap worker re-fetching + normal delivery path)
_ROAST_IN_FLIGHT: set[str] = set()

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

async def _safe_send_voice_roast(
    message: Message,
    voice_bytes: bytes,
    caption: str = "🔥 Разъёб от Киберчеда",
    log_prefix: str = "Voice Roast",
    reply_to_message_id: int | None = None,
) -> bool:
    """
    Надёжная отправка голосового ответа Киберчеда:
    1. Проверяет наличие message, chat и валидного message_id / reply_to_message_id.
    2. Пробует отправить reply_voice / send_voice с reply_to_message_id и allow_sending_without_reply=True.
    3. При 'message to be replied not found' или любой ошибке реплая (удаленный пост, анонимный канал, смена чата),
       автоматически переключается на answer_voice / send_voice без reply_to_message_id.
    4. Корректно обрабатывает запреты на отправку ГС (Telegram Premium / права чата) и блокировку бота.
    """
    if not message or not voice_bytes:
        return False

    from aiogram.types import BufferedInputFile
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

    # 1. Попытка реплая с флагом allow_sending_without_reply=True
    try:
        voice_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
        if (
            reply_to_message_id
            and reply_to_message_id != getattr(message, "message_id", None)
            and hasattr(message, "bot")
            and message.bot
            and hasattr(message, "chat")
            and message.chat
        ):
            try:
                await message.bot.send_voice(
                    chat_id=message.chat.id,
                    voice=voice_file,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                    allow_sending_without_reply=True
                )
                return True
            except TypeError:
                voice_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
                await message.bot.send_voice(
                    chat_id=message.chat.id,
                    voice=voice_file,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id
                )
                return True
            except Exception:
                pass

        if hasattr(message, "reply_voice"):
            try:
                await message.reply_voice(voice_file, caption=caption, allow_sending_without_reply=True)
                return True
            except TypeError:
                voice_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
                await message.reply_voice(voice_file, caption=caption)
                return True
        elif hasattr(message, "answer_voice"):
            await message.answer_voice(voice_file, caption=caption)
            return True
    except TelegramBadRequest as err:
        err_msg = str(err).lower()
        if "voice_messages_forbidden" in err_msg or "voices_forbidden" in err_msg:
            logger.info(f"ℹ️ [{log_prefix}] Отправка ГС запрещена настройками приватности чата, переключаемся на send_audio...")
            try:
                audio_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
                if hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
                    await message.bot.send_audio(
                        chat_id=message.chat.id,
                        audio=audio_file,
                        caption=caption,
                        title="Разъёб от Киберчеда",
                        performer="Киберчед",
                        reply_to_message_id=reply_to_message_id,
                        allow_sending_without_reply=True
                    )
                    return True
                elif hasattr(message, "reply_audio"):
                    await message.reply_audio(audio_file, caption=caption, title="Разъёб от Киберчеда", performer="Киберчед", allow_sending_without_reply=True)
                    return True
                elif hasattr(message, "answer_audio"):
                    await message.answer_audio(audio_file, caption=caption, title="Разъёб от Киберчеда", performer="Киберчед")
                    return True
            except Exception as audio_err:
                logger.warning(f"⚠️ [{log_prefix}] Не удалось отправить аудио-фолбэк после запрета ГС: {audio_err}")
                return False
            return False
        if "message to be replied not found" in err_msg or "message to reply not found" in err_msg or "reply message not found" in err_msg:
            logger.debug(f"ℹ️ [{log_prefix}] message_id={reply_to_message_id or getattr(message, 'message_id', None)} не найден (удален/анонимный пост), переходим на answer...")
        else:
            logger.info(f"ℹ️ [{log_prefix}] reply_voice/send_voice не удался ({err}), отправляем answer...")
    except TelegramForbiddenError as err:
        logger.info(f"ℹ️ [{log_prefix}] Чат недоступен (бот заблокирован пользователем или чат удален): {err}")
        return False
    except Exception as err:
        logger.debug(f"ℹ️ [{log_prefix}] reply_voice завершился с ошибкой: {err}")

    # 2. Безопасный Fallback: отправка напрямую в чат через answer_voice / send_voice / send_audio
    try:
        voice_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
        if hasattr(message, "answer_voice"):
            await message.answer_voice(voice_file, caption=caption)
            return True
        elif hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
            await message.bot.send_voice(chat_id=message.chat.id, voice=voice_file, caption=caption)
            return True
    except TelegramBadRequest as fb_err:
        fb_msg = str(fb_err).lower()
        if "voice_messages_forbidden" in fb_msg or "voices_forbidden" in fb_msg:
            logger.info(f"ℹ️ [{log_prefix}] Отправка ГС запрещена настройками чата, отправляем аудио-фолбэк...")
            try:
                audio_file = BufferedInputFile(voice_bytes, filename="cyberchad_roast.ogg")
                if hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
                    await message.bot.send_audio(
                        chat_id=message.chat.id,
                        audio=audio_file,
                        caption=caption,
                        title="Разъёб от Киберчеда",
                        performer="Киберчед"
                    )
                    return True
                elif hasattr(message, "answer_audio"):
                    await message.answer_audio(audio_file, caption=caption, title="Разъёб от Киберчеда", performer="Киберчед")
                    return True
            except Exception as audio_err:
                logger.warning(f"⚠️ [{log_prefix}] Не удалось отправить аудио-фолбэк в fallback блоке: {audio_err}")
        else:
            logger.warning(f"⚠️ [{log_prefix}] Не удалось отправить answer_voice: {fb_err}")
    except TelegramForbiddenError as fb_err:
        logger.info(f"ℹ️ [{log_prefix}] Чат недоступен при отправке answer_voice: {fb_err}")
    except Exception as fb_err:
        logger.warning(f"⚠️ [{log_prefix}] Не удалось отправить голосовой ответ Киберчеда: {fb_err}")

    return False


async def _safe_send_roast(
    message: Message,
    target_text: str,
    reply_to_message_id: int | None = None,
    log_prefix: str = "Roast"
) -> bool:
    """
    Надёжная отправка текстового роаста с реплаем к исходному посту.
    1. Пробует message.reply / bot.send_message с reply_to_message_id и allow_sending_without_reply=True.
    2. При ошибке реплая (удален пост / сменился контекст) автоматически шлет напрямую через answer.
    3. При ошибке 'message is too long' обрезает текст и отправляет сокращенный вариант.
    """
    if not message or not target_text:
        return False

    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

    try:
        if (
            reply_to_message_id
            and reply_to_message_id != getattr(message, "message_id", None)
            and hasattr(message, "bot")
            and message.bot
            and hasattr(message, "chat")
            and message.chat
        ):
            try:
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    text=target_text,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_message_id,
                    allow_sending_without_reply=True
                )
                return True
            except TypeError:
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    text=target_text,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_message_id
                )
                return True
            except Exception:
                pass

        if hasattr(message, "reply"):
            try:
                await message.reply(target_text, parse_mode="HTML", allow_sending_without_reply=True)
                return True
            except TypeError:
                await message.reply(target_text, parse_mode="HTML")
                return True
        elif hasattr(message, "answer"):
            await message.answer(target_text, parse_mode="HTML")
            return True
    except TelegramBadRequest as err:
        err_msg = str(err).lower()
        if "message to be replied not found" in err_msg or "message to reply not found" in err_msg or "reply message not found" in err_msg:
            try:
                if hasattr(message, "answer"):
                    await message.answer(target_text, parse_mode="HTML")
                    return True
                elif hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
                    await message.bot.send_message(chat_id=message.chat.id, text=target_text, parse_mode="HTML")
                    return True
            except Exception as ans_err:
                logger.warning(f"⚠️ [{log_prefix}] Fallback answer failed: {ans_err}")
        elif "message is too long" in err_msg:
            short_text = target_text[:3800] + "… <i>[сокращено]</i>"
            try:
                if hasattr(message, "reply"):
                    try:
                        await message.reply(short_text, parse_mode="HTML", allow_sending_without_reply=True)
                        return True
                    except TypeError:
                        await message.reply(short_text, parse_mode="HTML")
                        return True
                elif hasattr(message, "answer"):
                    await message.answer(short_text, parse_mode="HTML")
                    return True
                elif hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
                    await message.bot.send_message(chat_id=message.chat.id, text=short_text, parse_mode="HTML")
                    return True
            except Exception as short_err:
                logger.warning(f"⚠️ [{log_prefix}] Truncated send failed: {short_err}")
        else:
            logger.warning(f"⚠️ [{log_prefix}] TelegramBadRequest: {err}")
    except TelegramForbiddenError as err:
        logger.info(f"ℹ️ [{log_prefix}] Чат недоступен: {err}")
    except Exception as err:
        logger.warning(f"⚠️ [{log_prefix}] Ошибка отправки текстового роаста: {err}")

    # Fallback answer
    try:
        if hasattr(message, "answer"):
            await message.answer(target_text[:3800], parse_mode="HTML")
            return True
        elif hasattr(message, "bot") and message.bot and hasattr(message, "chat") and message.chat:
            await message.bot.send_message(chat_id=message.chat.id, text=target_text[:3800], parse_mode="HTML")
            return True
    except Exception as final_err:
        logger.warning(f"⚠️ [{log_prefix}] Итоговый fallback не удался: {final_err}")

    return False

async def transcribe_and_roast_voice_note(bot, message: Message, board_id: str = 'b', stream: str = 'ru', post_num: int | None = None):
    """
    Автоматическая транскрипция ГС и кружочков (Whisper/Groq STT + Gemini Multimodal Fallback)
    с адаптивными таймаутами для аудио любой длительности (включая 5-15+ минут),
    защитой от лимитов длины сообщений Telegram и 2ch-роастом.
    """
    if not message or not bot:
        return

    # Защита от бесконечной петли: игнорируем ботов, системные сообщения и уже сгенерированные роасты
    if getattr(getattr(message, 'from_user', None), 'is_bot', None) is True:
        return
    if getattr(message, 'is_system_message', None) is True:
        return
    caption_raw = (getattr(message, 'caption', '') or '').lower() if isinstance(getattr(message, 'caption', None), str) else ''
    if 'разъёб от киберчеда' in caption_raw or 'разъеб от киберчеда' in caption_raw or 'вердикт /b/' in caption_raw or 'шкала говноедства' in caption_raw:
        return

    try:
        content_type = message.content_type
        if content_type not in ('voice', 'video_note', 'audio'):
            return

        is_video_note = (content_type == 'video_note')
        media_obj = getattr(message, content_type, None)
        if not media_obj:
            return

        duration = int(getattr(media_obj, 'duration', 0) or 0)
        file_id = getattr(media_obj, 'file_id', None)

        # Idempotency guard: skip if this exact file is already being roasted
        if not file_id:
            return
        if file_id in _ROAST_IN_FLIGHT:
            logger.debug(f"[STT] file_id={file_id} already in flight — skipping duplicate roast")
            return
        _ROAST_IN_FLIGHT.add(file_id)

        transcript = None
        audio_bytes = None

        # 1. Скачивание аудиофайла через Telegram Bot API
        if file_id and bot:
            try:
                file_info = await bot.get_file(file_id)
                if file_info and file_info.file_path:
                    file_bytes_io = await bot.download_file(file_info.file_path)
                    audio_bytes = file_bytes_io.read() if hasattr(file_bytes_io, 'read') else file_bytes_io.getvalue()
            except Exception as dl_err:
                logger.warning(f"⚠️ [STT] Не удалось скачать медиа (file_id={file_id}): {dl_err}")

        if not audio_bytes:
            return

        # Адаптивный таймаут для STT: базово 60с, до 300с для длинных войсов (5+ минут)
        stt_timeout = max(60.0, min(300.0, float(duration) * 0.8 + 45.0))

        # 2. Попытка 1 (Основная): Прямой мультимодальный STT + Роаст через Gemini 3.5 / 3.1 Flash-Lite за 1 запрос
        transcript = ""
        roast = ""
        try:
            import base64
            from common.token_pool import google_pool
            from summarize import _load_google_keys
            google_keys = (google_pool.get_all_active_tokens() if hasattr(google_pool, "get_all_active_tokens") else []) or getattr(google_pool, "tokens", []) or _load_google_keys()
            proxy_url = os.getenv("PROXY_URL") or None
            if google_keys:
                b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                mime_type = "video/mp4" if is_video_note else "audio/ogg"
                voice_prompt = (
                    "Ты — агрессивный, циничный, мизантропичный анон из /b/ Двача.\n"
                    "Послушай прикрепленное голосовое сообщение / кружочек.\n\n"
                    "Выполни две задачи строго в указанном формате:\n"
                    "1. В блоке ТРАНСКРИПЦИЯ: дословно расшифруй всё, что сказал автор на языке оригинала (без вступительных слов и пояснений). Если в записи только тишина, шум или неразборчивое мычание, напиши [Тишина/Невнятно].\n"
                    "2. В блоке ВЕРДИКТ: напиши 1-2 ядовитых, смешных предложения, жестко разнеся автора за его слова, интонацию, голос и логику. Используй сочный двачерский сленг и мат по делу. Запрещены кавычки вокруг ответа, приветствия и морализаторство.\n\n"
                    "ФОРМАТ ОТВЕТА (СТРОГО СОБЛЮДАЙ СТРУКТУРУ):\n"
                    "ТРАНСКРИПЦИЯ: <дословный текст речи автора>\n"
                    "ВЕРДИКТ: <жесткий уничтожающий роаст автора>\n"
                )
                gemini_payload = {
                    "contents": [{
                        "parts": [
                            {"inlineData": {"mimeType": mime_type, "data": b64_audio}},
                            {"text": voice_prompt}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
                }
                gemini_timeout = max(35.0, min(180.0, float(duration) * 0.7 + 25.0))
                models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
                for gkey in google_keys:
                    for model_name in models_to_try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gkey}"
                        for proxy in [None, proxy_url] if proxy_url else [None]:
                            try:
                                async with httpx.AsyncClient(proxy=proxy, verify=False, timeout=gemini_timeout) as client:
                                    resp = await client.post(url, json=gemini_payload)
                                    if resp.status_code == 200:
                                        gdata = resp.json()
                                        parts = gdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                        if parts and "text" in parts[0]:
                                            raw_voice_res = parts[0]["text"].strip()
                                            # Парсинг ТРАНСКРИПЦИИ и ВЕРДИКТА
                                            t_part, r_part = "", ""
                                            for line in raw_voice_res.split("\n"):
                                                sline = line.strip()
                                                if sline.upper().startswith("ТРАНСКРИПЦИЯ:") or sline.upper().startswith("TRANSCRIPT:"):
                                                    t_part += sline.split(":", 1)[1].strip() + " "
                                                elif sline.upper().startswith("ВЕРДИКТ:") or sline.upper().startswith("РОАСТ:") or sline.upper().startswith("ROAST:"):
                                                    r_part += sline.split(":", 1)[1].strip() + " "
                                                elif r_part:
                                                    r_part += sline + " "
                                                elif t_part:
                                                    t_part += sline + " "
                                            
                                            transcript = t_part.strip() or raw_voice_res
                                            if r_part.strip():
                                                roast = clean_html_tags(clean_ai_thinking(r_part.strip())).strip()
                                            logger.info(f"✅ [Voice 1-Step] Успешная обработка через {model_name} (STT: {len(transcript)} симв., Roast: {len(roast)} симв.)")
                                            break
                                    elif resp.status_code == 429:
                                        break
                            except Exception:
                                continue
                        if transcript and roast:
                            break
                    if transcript and roast:
                        break
        except Exception as gemini_voice_err:
            logger.warning(f"⚠️ [Voice] Ошибка прямого Gemini Voice пайплайна: {gemini_voice_err}")

        # 3. Попытка 2 (Резервный Fallback): Groq Whisper STT + Text LLM Roast
        if not transcript:
            try:
                from common.token_pool import groq_pool
                groq_tokens = groq_pool.get_all_active_tokens() or getattr(groq_pool, "tokens", []) or []
                if not groq_tokens and os.getenv("GROQ_API_KEY"):
                    groq_tokens = [os.getenv("GROQ_API_KEY")]

                for token in groq_tokens:
                    if not token:
                        continue
                    try:
                        ext = ".mp4" if is_video_note else ".ogg"
                        filename = f"speech{ext}"
                        headers = {"Authorization": f"Bearer {token}"}
                        files = {"file": (filename, audio_bytes, "application/octet-stream")}
                        data = {
                            "model": "whisper-large-v3-turbo",
                            "response_format": "json",
                            "prompt": "Разговорная речь на русском языке, без субтитров и титров."
                        }
                        
                        async with httpx.AsyncClient(timeout=stt_timeout) as client:
                            resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                            if resp.status_code == 200:
                                res_data = resp.json()
                                candidate_text = res_data.get("text", "").strip()
                                # Фильтрация Whisper-галлюцинаций (Дима Торжок, Синецкая и т.д.)
                                candidate_lower = candidate_text.lower()
                                if any(h in candidate_lower for h in ("дима торжок", "dimatorzhok", "dima torzhok", "субтитры сделал", "редактор субтитров", "синецкая")):
                                    candidate_text = ""
                                if candidate_text:
                                    transcript = candidate_text
                                    logger.info(f"✅ [STT Fallback] Успешная расшифровка через Groq Whisper ({duration}с, {len(transcript)} симв.)")
                                    break
                            elif resp.status_code in (413, 429, 500, 502, 503):
                                logger.warning(f"⚠️ [STT Fallback] Groq status {resp.status_code}, пробуем следующий ключ...")
                                continue
                    except httpx.TimeoutException:
                        logger.warning(f"⚠️ [STT Fallback] Groq Timeout ({stt_timeout}s) для {duration}с аудио.")
                        break
                    except Exception as groq_err:
                        logger.warning(f"⚠️ [STT Fallback] Ошибка запроса к Groq: {groq_err}")
                        continue
            except Exception as e:
                logger.warning(f"⚠️ [STT Fallback] Ошибка пула Groq: {e}")

        # Если STT не отработал — молча выходим
        if not transcript:
            logger.warning(f"⚠️ [STT] Не удалось расшифровать аудио ({duration} сек)")
            return

        # 4. Если роаст ещё не сгенерирован (через Fallback STT) — генерируем через текстовую LLM
        if not roast and transcript:
            transcript_for_roast = transcript[:2000]
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
                    f"Слова автора: «{transcript_for_roast}»"
                )
                raw_roast = await summarize_text_with_hf(prompt, f"Слова автора: «{transcript_for_roast}»", model_preference="persona")
                if raw_roast and len(raw_roast.strip()) > 5:
                    roast = clean_html_tags(clean_ai_thinking(raw_roast)).strip()
            except Exception as roast_err:
                logger.warning(f"⚠️ Ошибка генерации роаста: {roast_err}")

        if not roast:
            roasts = CONTEXTUAL_REPLIES.get(r'\b(голосов[ауи]|кружоч[еик]|гс|записал|послушай|аудио)\b', [
                "засунь свое ГС себе в жопу и напиши текстом, шепелявый"
            ])
            roast = random.choice(roasts)


        icon = "📹" if is_video_note else "🎙"
        title = "Кружочек" if is_video_note else "Голосовое сообщение"

        # Форматирование длительности (сек / мин сек)
        if duration >= 60:
            mins = duration // 60
            secs = duration % 60
            dur_str = f"{mins} мин {secs} сек" if secs else f"{mins} мин"
        else:
            dur_str = f"{duration} сек"

        # Защита от переполнения лимита Telegram (4096 символов)
        max_disp_len = 2600
        if len(transcript) > max_disp_len:
            display_transcript = transcript[:max_disp_len] + "… <i>[текст сокращен]</i>"
        else:
            display_transcript = transcript

        formatted_response = (
            f"<b>{icon} {title}</b> (<i>{dur_str}</i>)\n"
            f"📝 <b>Транскрипция:</b> <i>«{escape_html(display_transcript)}»</i>\n\n"
            f"🔥 <b>Вердикт /b/ AI:</b>\n"
            f"{escape_html(roast)}"
        )

        author_id = getattr(getattr(message, 'from_user', None), 'id', None) or (message.chat.id if getattr(message, 'chat', None) else 0)
        b_data = getattr(shared_state, 'board_data', {}).get(board_id, {})
        author_settings = b_data.get('user_settings', {}).get(author_id, {}) if author_id else {}
        author_disabled_ai = bool(author_settings.get('disable_ai_roasts') or author_settings.get('hide_ai_slop'))

        # Определяем target_msg_id для точного ответа на пост автора в чате
        target_msg_id = None
        if post_num and author_id:
            try:
                async with shared_state.storage_lock:
                    raw_msg_id = shared_state.post_to_messages.get(post_num, {}).get(author_id)
                    if not raw_msg_id:
                        stored = messages_storage.get(post_num)
                        if stored:
                            raw_msg_id = stored.get('author_message_id')
                    if raw_msg_id:
                        target_msg_id = raw_msg_id[0] if isinstance(raw_msg_id, list) else raw_msg_id
            except Exception as lookup_err:
                logger.debug(f"ℹ️ Error looking up target_msg_id for voice roast: {lookup_err}")
        if not target_msg_id:
            target_msg_id = getattr(message, 'message_id', None)

        # 1. ТЕКСТОВЫЙ РОАСТ: ВСЕГДА отправляется автору мгновенно с реплаем к посту (без ожидания 5-минутной очереди!)
        if not author_disabled_ai:
            await _safe_send_roast(
                message,
                formatted_response,
                reply_to_message_id=target_msg_id,
                log_prefix="Voice Roast Text"
            )

        # 2. ГОЛОСОВОЙ РОАСТ Киберчеда (.ogg Opus): ВСЕГДА генерируется и отправляется автору мгновенно с реплаем к посту
        voice_bytes = None
        try:
            from common.tts_engine import synthesize_cyberchad_voice_with_meta
            voice_res = await synthesize_cyberchad_voice_with_meta(roast)
            if isinstance(voice_res, tuple):
                voice_bytes, _ = voice_res
            else:
                voice_bytes = voice_res
        except Exception as tts_err:
            logger.warning(f"⚠️ [Voice Roast] Ошибка синтеза речи Киберчеда: {tts_err}")

        if not author_disabled_ai and voice_bytes:
            try:
                await _safe_send_voice_roast(
                    message,
                    voice_bytes,
                    caption="🔥 Разъёб от Киберчеда",
                    log_prefix="Voice Roast",
                    reply_to_message_id=target_msg_id
                )
            except Exception as tts_err:
                logger.warning(f"⚠️ [Voice Roast] Не удалось отправить голосовой ответ Киберчеда: {tts_err}")

        # 3. Публикация текстового роаста на доску (для остальных подписчиков доски)
        if post_num and board_id != 'trash':
            try:
                from common.bot_helpers import process_new_post
                # Исключаем автора из пассивной очереди, так как он уже получил роаст мгновенно выше
                await process_new_post(shared_state.NewPostParams(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content={
                        'type': 'text',
                        'text': formatted_response,
                        'is_system_message': True,
                        'archive_allowed': True,
                        'is_ai_roast': True,
                        'is_ai': True,
                        'exclude_recipients': [author_id] if author_id else []
                    },
                    reply_to_post=post_num,
                    is_shadow_muted=False,
                    stream=stream
                ))
            except Exception as board_pub_err:
                logger.warning(f"⚠️ Ошибка рассылки роаста ГС на доску: {board_pub_err}")

        # 4. Публикация голосового роаста Киберчеда на доску (для остальных подписчиков доски)
        if post_num and board_id != 'trash' and voice_bytes:
            try:
                from common.bot_helpers import process_new_post
                await process_new_post(shared_state.NewPostParams(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content={
                        'type': 'voice',
                        'voice_bytes': voice_bytes,
                        'caption': '🔥 Разъёб от Киберчеда',
                        'is_ai_roast': True,
                        'is_ai': True,
                        'reply_to': post_num,
                        'exclude_recipients': [author_id] if author_id else []
                    },
                    reply_to_post=post_num,
                    is_shadow_muted=False,
                    stream=stream
                ))
            except Exception as voice_pub_err:
                logger.warning(f"⚠️ Ошибка рассылки голосового роаста ГС на доску: {voice_pub_err}")
    except Exception as e:
        logger.error(f"❌ Ошибка в transcribe_and_roast_voice_note: {e}", exc_info=True)
    finally:
        # Release the idempotency lock regardless of outcome
        if 'file_id' in dir() or 'file_id' in locals():
            _ROAST_IN_FLIGHT.discard(file_id)


MUSIC_EXTENSIONS = ('.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.wma', '.aiff', '.alac')

def is_music_document(doc) -> bool:
    """Checks if a Telegram Document is an audio/music file by extension or MIME type."""
    if not doc:
        return False
    fn = getattr(doc, 'file_name', '') or ''
    mt = getattr(doc, 'mime_type', '') or ''
    ext = os.path.splitext(fn.lower())[1]
    if ext in MUSIC_EXTENSIONS:
        return True
    if mt.startswith('audio/') or mt in ('application/ogg', 'application/x-flac', 'audio/x-m4a', 'audio/x-wav'):
        return True
    return False

def format_music_duration(duration: int | float | None) -> str:
    """Форматирует длительность трека в секундах в человекочитаемый вид."""
    if duration is None:
        return "время не указано"
    try:
        dur_int = int(duration)
    except (ValueError, TypeError):
        return "время не указано"
    if dur_int <= 0:
        return "время не указано"
    if dur_int >= 60:
        mins = dur_int // 60
        secs = dur_int % 60
        return f"{mins} мин {secs} сек" if secs else f"{mins} мин"
    return f"{dur_int} сек"

format_duration = format_music_duration

def extract_music_metadata(message: Message) -> dict:
    """Extracts artist, title, filename, duration, file_id and mime_type from Message (Audio/Document)."""
    artist = None
    title = None
    filename = ""
    duration = 0
    file_id = None
    file_size = 0
    mime_type = "audio/mpeg"
    audio = getattr(message, 'audio', None)
    doc = getattr(message, 'document', None)

    if audio:
        file_id = getattr(audio, 'file_id', None)
        if isinstance(file_id, str):
            pass
        elif file_id is not None:
            file_id = str(file_id)

        perf = getattr(audio, 'performer', None)
        if isinstance(perf, str) and perf.strip():
            artist = perf.strip()

        t = getattr(audio, 'title', None)
        if isinstance(t, str) and t.strip():
            title = t.strip()

        fn = getattr(audio, 'file_name', None)
        if isinstance(fn, str):
            filename = fn

        dur = getattr(audio, 'duration', 0)
        try:
            duration = int(dur) if isinstance(dur, (int, float)) or (isinstance(dur, str) and dur.isdigit()) else 0
        except Exception:
            duration = 0

        fs = getattr(audio, 'file_size', 0)
        try:
            file_size = int(fs) if isinstance(fs, (int, float)) else 0
        except Exception:
            file_size = 0

        mt = getattr(audio, 'mime_type', None)
        if isinstance(mt, str):
            mime_type = mt
    elif doc and is_music_document(doc):
        file_id = getattr(doc, 'file_id', None)
        if isinstance(file_id, str):
            pass
        elif file_id is not None:
            file_id = str(file_id)

        fn = getattr(doc, 'file_name', None)
        if isinstance(fn, str):
            filename = fn

        fs = getattr(doc, 'file_size', 0)
        try:
            file_size = int(fs) if isinstance(fs, (int, float)) else 0
        except Exception:
            file_size = 0

        mt = getattr(doc, 'mime_type', None)
        if isinstance(mt, str):
            mime_type = mt

    # Regex fallback for Artist - Title on filename
    if filename and (not artist or not title):
        base_name = os.path.splitext(filename)[0]
        # Remove leading release tags like [FLAC] [2024] [320kbps] [OST] [Remastered]
        clean_base = re.sub(r'^(?:\[[^\]]*\]\s*)+', '', base_name).strip()
        # Split on first occurrence of hyphen surrounded by spaces
        m_parts = re.split(r'\s+[-–—]\s+', clean_base, maxsplit=1)
        if len(m_parts) == 2:
            if not artist and m_parts[0].strip():
                artist = m_parts[0].strip()
            if not title and m_parts[1].strip():
                title = m_parts[1].strip()

    if not artist or not artist.strip():
        artist = "Неизвестный исполнитель"
    else:
        artist = artist.strip()

    if title and title.strip():
        title = title.strip()
    elif filename:
        base = os.path.splitext(filename)[0]
        title = base if base.strip() else "Без названия"
    else:
        title = "Без названия"

    dur_str = format_music_duration(duration)

    return {
        "artist": artist,
        "title": title,
        "filename": filename,
        "file_name": filename,
        "duration": duration,
        "dur_str": dur_str,
        "file_id": file_id,
        "file_size": file_size,
        "mime_type": mime_type,
    }


MUSIC_ROAST_SYSTEM_PROMPT = (
    "Кто-то на /b/ прислал трек. Послушай. Твоя задача — ЛИЧНЫЙ УДАР прямо в ебало человеку который это прислал.\n"
    "Говори на «ты», грубо, без разогрева. Он сидит и читает — сделай так, чтобы у него горело.\n"
    "МАТ ОБЯЗАТЕЛЕН — без него текст слабый и беззубый. Хуячь без цензуры, но по делу.\n\n"
    "Примеры ударов (с матом как надо):\n"
    "- Рэп про деньги/понты → ты греешь своё нищебродское эго чужими деньгами из клипа, у тебя в кармане хуй да маленько\n"
    "- Депрессивный/дед-инсайд → ты не страдаешь, ты просто ленивый мудак которому влом встать с дивана\n"
    "- Кальянный/пацанский → в реале ты облизываешь яйца первому кто посмотрит на тебя косо, петушок комнатный\n"
    "- Поп/K-pop/тикток → ты пустое место, в черепке буквально один клип и те чужой\n"
    "- Техно/инструментал → понтуешься вкусом, хотя сам не знаешь чем бас от пердежа отличается\n"
    "- Патриотика → диванный вояка, чья вся война — срать в чате и репостить военкоров\n\n"
    "2-3 предложения. Каждое — удар. Не объясняй, не рефлексируй, просто бей.\n"
    "Последняя строка: ОЦЕНКА: <число>/10 💩 (<приговор человеку, не треку>)"
)

# Rate limiting: хранит timestamps отправок треков по user_id для защиты от спама
# { user_id: [timestamp1, timestamp2, ...] }
_music_roast_user_times: dict[int, list[float]] = {}
MUSIC_ROAST_RATE_LIMIT = 8          # треков в час максимум
MUSIC_ROAST_RATE_WINDOW_SEC = 3600  # окно (1 час)
MUSIC_ROAST_FLOOD_RESPONSES = [
    "Слышь, пидор, ты восьмой трек за час слить пришёл? Даже мусоровоз так не воняет. Иди отдохни, дай ушам людей передышку.",
    "Восемь треков за час — это уже не вкус, это болезнь. Тебя слушать невозможно, тебя читать невозможно, ты невозможен.",
    "Стоп, ты опять? Девять треков в час — ты вообще понимаешь, что это симптом? Сходи к врачу, пока доктор ещё слышит.",
    "Слушай, я понимаю, у тебя нет друзей и говорить не с кем. Но засирать борду десятью треками в час — это уже перебор даже для тебя.",
    "Ты что, плейлистом отстреливаешься от реальности? Уже столько треков, что у меня уши вянут, а у тебя самооценка не растёт.",
    "Продолжай, продолжай. Может на пятнадцатом треке кто-нибудь наконец скажет тебе, что ты молодец. Спойлер: нет.",
    "Флуд треками — это новый тип аутизма. Зафиксировано. Можешь выдыхать, следующую пачку приму через час.",
]

DEFAULT_MUSIC_ROASTS = [
    (
        "Ты присылаешь этот кал так, будто ждёшь аплодисментов — но единственное, что ты заслужил, это пинок под зад и напоминание, "
        "что вкус не появляется сам по себе, его нужно развивать, а не гнобить людей своей помойкой. "
        "Сними наушники, омежка, выйди на улицу — даже бомжи у падика слушают лучше.",
        "0/10 💩 (гимн сыча с нулевой самооценкой и бесконечным временем)"
    ),
    (
        "Ты отправил это — и в этот момент где-то во вселенной умерла нота. "
        "Под этот автотюновый понос ты, наверное, воображаешь себя кем-то — но мы-то видим реального тебя: "
        "мамины дошираки, Redmi в трещинах, и влажные фантазии о жизни, которой у тебя никогда не будет.",
        "0/10 💩 (высер для нищих позёров, которые называют это «вайбом»)"
    ),
    (
        "Этот унылый говнарь послал треком SOS — мол, оцените, я тоже чувствую. "
        "Чувствуем. Чувствуем, что тебе нужна не музыка, а нормальный режим дня и хоть один живой друг. "
        "Твой удел — пердеть в продавленный диван и называть это «богатым внутренним миром».",
        "0/10 💩 (диагноз: хроническое говноедство с осложнениями)"
    ),
]


def parse_music_roast_response(raw_text: str) -> tuple[str, str]:
    """
    Splits AI music review into roast text and rating.
    """
    clean_text = clean_ai_thinking(raw_text).strip()
    lines = [l.strip() for l in clean_text.split('\n') if l.strip()]
    if not lines:
        return "Очередной бездарный кал, высранный ради стримов и тиктока.", "10/10 💩 (Клинический говноед)"

    rating = None
    roast_lines = []

    last_line = lines[-1]
    rating_match = re.search(r'(?:(?:ОЦЕНКА|Шкала говноедства|Вердикт|Рейтинг|Шкала кала):\s*)(.*)$', last_line, re.IGNORECASE)
    if rating_match:
        rating = rating_match.group(1).strip()
        roast_lines = lines[:-1]
    elif re.search(r'\b\d{1,2}\s*/\s*10\b', last_line) and len(last_line) < 80:
        rating = last_line
        roast_lines = lines[:-1]
    else:
        roast_lines = lines

    roast_text = "\n\n".join(roast_lines).strip()
    if not roast_text and rating:
        roast_text = rating
        rating = "10/10 💩 (Полная безвкусица)"
    elif not rating:
        fallback_ratings = [
            "10/10 💩 (Абсолютный шедевр мочи)",
            "9/10 💩 (Клиническая стадия ушного кала)",
            "10/10 💩 (Дно пробито, слушатель слит)",
            "8/10 💩 (Тикток-шлак для дегенератов)",
            "0/10 💩 (Даже бомжи на помойке слушают лучше)",
            "10/10 💩 (Смертельная доза кринжа)"
        ]
        rating = random.choice(fallback_ratings)

    roast_text = clean_html_tags(roast_text)
    roast_text = re.sub(r'^[«"\'\`]+|[»"\'\`]+$', '', roast_text).strip()
    rating = clean_html_tags(rating)
    rating = re.sub(r'^[«"\'\`]+|[»"\'\`]+$', '', rating).strip()

    return roast_text, rating


async def handle_music_roast(bot, message: Message, board_id: str = 'b', stream: str = 'ru', post_num: int | None = None):
    """
    Автоматический двачерский /b/ музкритик-роаст для любых аудио/музыкальных треков
    (Audio и Document с расширениями .mp3, .wav, .flac, .ogg, .m4a и др.).
    Извлекает метаданные (исполнитель, трек, длительность), скачивает семпл (до 20МБ),
    транскрибирует текст через Whisper/Gemini STT и выдает токсичный разнос вкуса.
    """
    if not message or not bot:
        return

    # Защита от бесконечной петли: игнорируем ботов, системные сообщения и уже сгенерированные роасты
    if getattr(getattr(message, 'from_user', None), 'is_bot', None) is True:
        return
    if getattr(message, 'is_system_message', None) is True:
        return
    caption_raw = (getattr(message, 'caption', '') or '').lower() if isinstance(getattr(message, 'caption', None), str) else ''
    if 'разъёб от киберчеда' in caption_raw or 'разъеб от киберчеда' in caption_raw or 'вердикт /b/' in caption_raw or 'шкала говноедства' in caption_raw:
        return

    # Игнорируем сообщения, которые не являются аудио или музыкальными документами
    is_audio = bool(getattr(message, 'audio', None))
    is_music_doc = bool(getattr(message, 'document', None) and is_music_document(message.document))
    if not is_audio and not is_music_doc:
        return

    # --- RATE LIMIT: >8 треков в час → голосовая заглушка Киберчеда ---
    sender_id = getattr(getattr(message, 'from_user', None), 'id', None) or 0
    if sender_id:
        import time as _time
        _now = _time.monotonic()
        _times = _music_roast_user_times.setdefault(sender_id, [])
        # Чистим старые записи за пределами окна
        _music_roast_user_times[sender_id] = [t for t in _times if _now - t < MUSIC_ROAST_RATE_WINDOW_SEC]
        if len(_music_roast_user_times[sender_id]) >= MUSIC_ROAST_RATE_LIMIT:
            # Пишем что сколько времени до сброса
            _remaining = int(MUSIC_ROAST_RATE_WINDOW_SEC - (_now - _music_roast_user_times[sender_id][0]))
            _mins_left = max(1, _remaining // 60)
            stub_text = random.choice(MUSIC_ROAST_FLOOD_RESPONSES)
            stub_text += f" Следующий приму через ~{_mins_left} мин."
            try:
                await _safe_send_roast(message, f"🎵 {stub_text}", log_prefix="Music Flood Stub")
            except Exception:
                pass
            try:
                from common.tts_engine import synthesize_cyberchad_voice_with_meta
                stub_voice_res = await synthesize_cyberchad_voice_with_meta(stub_text)
                stub_voice_bytes = stub_voice_res[0] if isinstance(stub_voice_res, tuple) else stub_voice_res
                if stub_voice_bytes:
                    await _safe_send_voice_roast(
                        message, stub_voice_bytes,
                        caption="🔇 Хватит уже",
                        log_prefix="Music Flood Voice"
                    )
            except Exception as _tts_err:
                logger.debug(f"[Music Flood] TTS error: {_tts_err}")
            return
        # Записываем текущий запрос
        _music_roast_user_times[sender_id].append(_now)

    try:
        meta = extract_music_metadata(message)
        artist = meta["artist"]
        title = meta["title"]
        filename = meta["filename"]
        duration = meta["duration"]
        dur_str = meta["dur_str"]
        file_id = meta["file_id"]
        file_size = meta["file_size"]
        mime_type = meta["mime_type"]

        audio_bytes = None
        sample_note = None

        # 1. Скачивание аудиофайла до 20MB через Telegram Bot API
        if file_size > 20 * 1024 * 1024:
            sample_note = "[Файл >20MB — семпл не скачан]"
        elif file_id:
            try:
                file_info = await bot.get_file(file_id)
                if file_info and getattr(file_info, 'file_path', None):
                    fi_size = getattr(file_info, 'file_size', 0)
                    if isinstance(fi_size, (int, float)) and fi_size > 20 * 1024 * 1024:
                        sample_note = "[Файл >20MB — семпл не скачан]"
                    else:
                        file_bytes_io = await bot.download_file(file_info.file_path)
                        downloaded = file_bytes_io.read() if hasattr(file_bytes_io, 'read') else file_bytes_io.getvalue()
                        if len(downloaded) > 20 * 1024 * 1024:
                            sample_note = "[Файл >20MB — семпл не скачан]"
                        else:
                            audio_bytes = downloaded
            except Exception as dl_err:
                logger.warning(f"⚠️ [Music STT] Не удалось скачать аудио (file_id={file_id}): {dl_err}")
                if "file is too big" in str(dl_err).lower() or "too large" in str(dl_err).lower():
                    sample_note = "[Файл >20MB — семпл не скачан]"

        # 2. Прямой 1-Step Мультимодальный анализ и Роаст через Gemini (как в Voice Note Roast)
        transcript = ""
        roast_text = None
        rating = None

        if audio_bytes and len(audio_bytes) < 20 * 1024 * 1024:
            try:
                import base64
                from common.token_pool import google_pool
                from summarize import _load_google_keys
                google_keys = (google_pool.get_all_active_tokens() if hasattr(google_pool, "get_all_active_tokens") else []) or getattr(google_pool, "tokens", []) or _load_google_keys()
                proxy_url = os.getenv("PROXY_URL") or None
                if google_keys:
                    b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                    m_type = mime_type if (mime_type and mime_type.startswith("audio/")) else "audio/mpeg"
                    music_prompt = (
                        f"Кто-то на /b/ прислал трек «{artist} — {title}» ({dur_str}). "
                        f"Файл: «{filename}».\n"
                        "Послушай и ударь КОНКРЕТНО в того кто это прислал — не в трек, а в человека.\n"
                        "Говори на «ты», без разогрева. МАТ ОБЯЗАТЕЛЕН — без него текст слабый и беззубый. Хуячь по делу.\n\n"
                        "Логика удара под жанр:\n"
                        "- Рэп/деньги/понты → ты греешь нищебродское эго чужими деньгами, у тебя в кармане хуй да маленько\n"
                        "- Депрессивный/дед-инсайд → ты не страдаешь, ты просто ленивый мудак которому влом встать с дивана\n"
                        "- Кальянный/пацанский → в реале ты облизываешь яйца первому кто посмотрит косо, петушок\n"
                        "- Поп/K-pop/тикток → ты пустой — в голове один клип и тот чужой\n"
                        "- Техно/инструментал → понтуешься вкусом, а сам не отличишь бас от своего же пердежа\n"
                        "- Патриотика → диванный вояка, вся война которого — срать в чате и репостить военкоров\n\n"
                        "ФОРМАТ ОТВЕТА — СТРОГО:\n"
                        "ТРАНСКРИПЦИЯ: <дословный текст песни на языке оригинала; если инструментал — [Инструментал/Без слов]>\n"
                        "ВЕРДИКТ: <2-3 предложения прямо в ебало тому кто прислал — жёстко, с матом, без вступлений>\n"
                        "ШКАЛА: <число 0-10>/10\n"
                    )
                    gemini_payload = {
                        "contents": [{
                            "parts": [
                                {"inlineData": {"mimeType": m_type, "data": b64_audio}},
                                {"text": music_prompt}
                            ]
                        }],
                        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
                    }
                    gemini_timeout = max(35.0, min(180.0, float(duration) * 0.7 + 25.0))
                    models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
                    for gkey in google_keys:
                        for model_name in models_to_try:
                            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gkey}"
                            for proxy in [None, proxy_url] if proxy_url else [None]:
                                try:
                                    async with httpx.AsyncClient(proxy=proxy, verify=False, timeout=gemini_timeout) as client:
                                        resp = await client.post(url, json=gemini_payload)
                                        if resp.status_code == 200:
                                            gdata = resp.json()
                                            parts = gdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                            if parts and "text" in parts[0]:
                                                raw_music_res = parts[0]["text"].strip()
                                                t_part, v_part, s_part = "", "", ""
                                                for line in raw_music_res.split("\n"):
                                                    sline = line.strip()
                                                    if sline.upper().startswith("ТРАНСКРИПЦИЯ:") or sline.upper().startswith("TRANSCRIPT:"):
                                                        t_part = sline.split(":", 1)[1].strip()
                                                    elif sline.upper().startswith("ВЕРДИКТ:") or sline.upper().startswith("РОАСТ:") or sline.upper().startswith("VERDICT:"):
                                                        v_part = sline.split(":", 1)[1].strip()
                                                    elif sline.upper().startswith("ШКАЛА:") or sline.upper().startswith("ОЦЕНКА:") or sline.upper().startswith("RATING:"):
                                                        s_part = sline.split(":", 1)[1].strip()
                                                    elif v_part and not s_part:
                                                        v_part += " " + sline
                                                    elif t_part and not v_part and not s_part:
                                                        t_part += " " + sline

                                                if t_part:
                                                    transcript = t_part.strip()
                                                if v_part:
                                                    roast_text = clean_html_tags(clean_ai_thinking(v_part.strip())).strip()
                                                if s_part:
                                                    m_score = re.search(r'(\d+)(?:/10)?', s_part)
                                                    if m_score:
                                                        rating = min(10, max(0, int(m_score.group(1))))
                                                elif raw_music_res:
                                                    parsed_r, parsed_s = parse_music_roast_response(raw_music_res)
                                                    if parsed_r: roast_text = parsed_r
                                                    if parsed_s: rating = parsed_s

                                                if roast_text:
                                                    if rating is None: rating = random.randint(1, 9)
                                                    logger.info(f"✅ [Music 1-Step] Успешная мультимодальная рецензия через {model_name} (STT: {len(transcript)} симв., Roast: {len(roast_text)} симв., Оценка: {rating}/10)")
                                                    break
                                        elif resp.status_code == 429:
                                            break
                                except Exception:
                                    continue
                            if roast_text:
                                break
                        if roast_text:
                            break
            except Exception as gemini_err:
                logger.warning(f"⚠️ [Music Roast] Ошибка прямого Gemini 1-Step Music пайплайна: {gemini_err}")

        # 3. Резервный Fallback: Если Gemini недоступен или файл >20MB — текстовый роаст по метаданным
        if not roast_text:
            try:
                lyrics_context = transcript[:1500] if transcript else (sample_note or "[Семпл не скачан]")
                track_context = f"Исполнитель: «{artist}»\nНазвание трека: «{title}»\nДлительность: {dur_str}\nФрагмент/текст: «{lyrics_context}»"
                user_msg = f"Отрецензируй и уничтожь следующий музыкальный трек:\n\n{track_context}"
                raw_ai_roast = await summarize_text_with_hf(MUSIC_ROAST_SYSTEM_PROMPT, user_msg, model_preference="persona")
                if raw_ai_roast and len(raw_ai_roast.strip()) > 5:
                    roast_text, rating = parse_music_roast_response(raw_ai_roast)
            except Exception as ai_err:
                logger.warning(f"⚠️ [Music Roast] Ошибка генерации текстовой ИИ-рецензии: {ai_err}")

        if not roast_text:
            logger.warning(f"⚠️ [Music Roast] Не удалось сгенерировать рецензию для «{artist} — {title}»")
            return
        if rating is None:
            rating = random.randint(1, 9)

        # Обработка инструментала/отсутствия слов
        if transcript:
            cleaned_trans = transcript.strip()
            if cleaned_trans in ("[Инструментал]", "[Инструментальная музыка]", "[Тишина]", "") or len(cleaned_trans) < 2:
                lyrics_display = "[Инструментальный трек / неразборчивый вокал]"
            else:
                lyrics_display = cleaned_trans[:600] + ("..." if len(cleaned_trans) > 600 else "")
        elif sample_note:
            lyrics_display = sample_note[:600]
        else:
            lyrics_display = "[Инструментальный трек / неразборчивый вокал]"

        if not roast_text:
            fb_text, fb_rating = random.choice(DEFAULT_MUSIC_ROASTS)
            roast_text = fb_text
            rating_str = fb_rating
        else:
            rating_str = f"{rating}/10 💩"

        # Форматирование итогового ответа
        formatted_response = (
            f"🎵 <b>Трек:</b> {escape_html(artist)} — {escape_html(title)} (<i>{dur_str}</i>)\n\n"
            f"🔥 <b>Вердикт /b/ музкритика:</b>\n"
            f"{escape_html(roast_text)}\n\n"
            f"💩 <b>Шкала говноедства:</b> {escape_html(rating_str)}"
        )

        author_id = getattr(getattr(message, 'from_user', None), 'id', None) or (message.chat.id if getattr(message, 'chat', None) else 0)
        b_data = getattr(shared_state, 'board_data', {}).get(board_id, {})
        author_settings = b_data.get('user_settings', {}).get(author_id, {}) if author_id else {}
        author_disabled_ai = bool(author_settings.get('disable_ai_roasts') or author_settings.get('hide_ai_slop'))

        # Сохранение в базу данных для ТОПа говноедов
        if author_id:
            try:
                from common.database import add_music_roast, get_db
                if isinstance(rating, int):
                    score_val = min(10, max(0, rating))
                else:
                    score_match = re.search(r'(\d+)\s*/\s*10', str(rating))
                    score_val = int(score_match.group(1)) if score_match else 0
                db = await get_db()
                await add_music_roast(
                    db,
                    user_id=author_id,
                    board_id=board_id,
                    post_num=post_num,
                    artist=artist,
                    title=title,
                    score=score_val,
                    rating_text=rating_str,
                    roast_text=roast_text
                )
            except Exception as db_save_err:
                logger.debug(f"ℹ️ Error logging music roast to DB: {db_save_err}")

        # Определяем target_msg_id для точного ответа на пост автора в чате
        target_msg_id = None
        if post_num and author_id:
            try:
                async with shared_state.storage_lock:
                    raw_msg_id = shared_state.post_to_messages.get(post_num, {}).get(author_id)
                    if not raw_msg_id:
                        stored = messages_storage.get(post_num)
                        if stored:
                            raw_msg_id = stored.get('author_message_id')
                    if raw_msg_id:
                        target_msg_id = raw_msg_id[0] if isinstance(raw_msg_id, list) else raw_msg_id
            except Exception as lookup_err:
                logger.debug(f"ℹ️ Error looking up target_msg_id for music roast: {lookup_err}")
        if not target_msg_id:
            target_msg_id = getattr(message, 'message_id', None)

        # 1. ТЕКСТОВЫЙ РОАСТ: ВСЕГДА отправляется автору мгновенно с реплаем к посту (без ожидания 5-минутной очереди!)
        if not author_disabled_ai:
            await _safe_send_roast(
                message,
                formatted_response,
                reply_to_message_id=target_msg_id,
                log_prefix="Music Roast Text"
            )

        # 2. ГОЛОСОВОЙ РОАСТ Киберчеда (.ogg Opus): ВСЕГДА генерируется и отправляется автору мгновенно с реплаем к посту
        voice_bytes = None
        try:
            from common.tts_engine import synthesize_cyberchad_voice_with_meta
            voice_summary = f"{roast_text} Оценка: {rating}"
            voice_res = await synthesize_cyberchad_voice_with_meta(voice_summary)
            if isinstance(voice_res, tuple):
                voice_bytes, _ = voice_res
            else:
                voice_bytes = voice_res
        except Exception as tts_err:
            logger.warning(f"⚠️ [Music Roast] Ошибка синтеза речи Киберчеда: {tts_err}")

        if not author_disabled_ai and voice_bytes:
            try:
                await _safe_send_voice_roast(
                    message,
                    voice_bytes,
                    caption="🔥 Разъёб от Киберчеда",
                    log_prefix="Music Roast",
                    reply_to_message_id=target_msg_id
                )
            except Exception as tts_err:
                logger.warning(f"⚠️ [Music Roast] Не удалось отправить голосовой ответ Киберчеда: {tts_err}")

        # 3. Публикация текстового роаста на доску (для остальных подписчиков доски)
        if post_num and board_id != 'trash':
            try:
                from common.bot_helpers import process_new_post
                # Исключаем автора из пассивной очереди, так как он уже получил роаст мгновенно выше
                await process_new_post(shared_state.NewPostParams(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content={
                        'type': 'text',
                        'text': formatted_response,
                        'is_system_message': True,
                        'archive_allowed': True,
                        'is_ai_roast': True,
                        'is_ai': True,
                        'exclude_recipients': [author_id] if author_id else []
                    },
                    reply_to_post=post_num,
                    is_shadow_muted=False,
                    stream=stream
                ))
            except Exception as board_pub_err:
                logger.warning(f"⚠️ [Music Roast] Ошибка рассылки роаста трека на доску: {board_pub_err}")

        # 4. Публикация голосового роаста Киберчеда на доску (для остальных подписчиков доски)
        if post_num and board_id != 'trash' and voice_bytes:
            try:
                from common.bot_helpers import process_new_post
                await process_new_post(shared_state.NewPostParams(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content={
                        'type': 'voice',
                        'voice_bytes': voice_bytes,
                        'caption': '🔥 Разъёб от Киберчеда',
                        'is_ai_roast': True,
                        'is_ai': True,
                        'reply_to': post_num,
                        'exclude_recipients': [author_id] if author_id else []
                    },
                    reply_to_post=post_num,
                    is_shadow_muted=False,
                    stream=stream
                ))
            except Exception as voice_pub_err:
                logger.warning(f"⚠️ [Music Roast] Ошибка рассылки голосового роаста трека на доску: {voice_pub_err}")
    except Exception as e:
        logger.error(f"❌ [Music Roast] Ошибка в handle_music_roast: {e}", exc_info=True)


_BOARD_FIGHT_TRACKER: dict[str, list[tuple[float, int, str, int]]] = {}
_LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION: dict[str, float] = {}
_LAST_CYBERCHAD_INTERVENTION: dict[str, float] = _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION
_LAST_DIRECT_ROAST_USER_TS: dict[tuple[str, int], float] = {}

CYBERCHAD_FIGHT_INTERVENTION_PROMPT = (
    "Ты — Киберчед, легендарный альфа-анон из /b/ Двача. "
    "В чате разгорелся тупой омежий срач между анонами. "
    "Твоя задача — вломиться в спор и одной сочной, брутальной, ядовитой репликой (2-3 коротких предложения) "
    "размазать обоих клоунов по стенке, высмеяв их кукареканье, девичьи визги и то, какими жалкими петухами они выглядят со стороны.\n\n"
    "СТРОГИЕ ПРАВИЛА:\n"
    "1. Запрещены любые приветствия, преамбулы и вводные фразы.\n"
    "2. Запрещены кавычки вокруг ответа.\n"
    "3. Пиши разговорным двачерским языком с отборным матом по делу.\n"
    "4. Это текст ИСКЛЮЧИТЕЛЬНО ДЛЯ ГОЛОСОВОЙ ОЗВУЧКИ — он должен звучать нагло, уверенно и хлестко."
)

CYBERCHAD_DIRECT_ROAST_PROMPT = (
    "Ты — Киберчед, легендарный альфа-анон и абсолютный босс Двача (/b/). "
    "Один из сычей-омежек посмел дерзко и нагло ответить лично тебе или кукарекнуть в твой адрес. "
    "Твоя задача — уничтожить этого дерзкого анона персонализированным, брутальным, ядовитым голосовым разносом (2-3 коротких хлестких предложения). "
    "Опусти его на землю, размажь его жалкие потуги казаться крутым, высмей его аргументы и укажи его место у параши.\n\n"
    "СТРОГИЕ ПРАВИЛА:\n"
    "1. Запрещены любые приветствия, преамбулы, вводные слова вроде 'Слышь' в начале каждой фразы или мета-комментарии.\n"
    "2. Запрещены кавычки вокруг ответа.\n"
    "3. Пиши разговорным двачерским языком с отборным сочным матом по делу.\n"
    "4. Опирайся на контекст треда и конкретные слова анона, бей точно в цель.\n"
    "5. Это текст ИСКЛЮЧИТЕЛЬНО ДЛЯ ГОЛОСОВОЙ ОЗВУЧКИ — он должен звучать максимально нагло, брутально и доминантно."
)

async def register_post_and_maybe_trigger_cyberchad_intervention(
    bot,
    board_id: str,
    user_id: int,
    text: str,
    post_num: int | None = None,
    reply_to_post: int | None = None,
    stream: str = 'ru'
) -> None:
    """
    Отслеживает срачи в чате и прямые реплаи на посты Киберчеда.
    Киберчед самостоятельно врывается в тред СТРОГО ГОЛОСОВЫМ СООБЩЕНИЕМ (без текста!).
    Кулдаун спонтанных интервенций: строго не чаще 1 раза в час (>= 3600.0с) на доску.
    Прямые ответы Киберчеду обрабатываются независимо от кулдауна доски с личным анти-флудом.
    """
    if not text or not user_id or user_id <= 0 or board_id == 'trash':
        return
        
    now = time.time()
    if board_id not in _BOARD_FIGHT_TRACKER:
        _BOARD_FIGHT_TRACKER[board_id] = []
        
    # Очищаем историю старше 180 секунд
    tracker = _BOARD_FIGHT_TRACKER[board_id]
    _BOARD_FIGHT_TRACKER[board_id] = [entry for entry in tracker if now - entry[0] <= 180]
    _BOARD_FIGHT_TRACKER[board_id].append((now, user_id, str(text), post_num or 0))
    
    recent_entries = _BOARD_FIGHT_TRACKER[board_id]

    from common.anon_identity import get_anon_id
    from common.bot_helpers import process_new_post
    from common.tts_engine import synthesize_cyberchad_voice_with_meta
    from common.database import get_post_by_num

    # 1. Проверяем, ответили ли ПРЯМО КИБЕРЧЕДУ (Reply на пост Киберчеда / упоминание)
    is_direct_reply_to_chad = False
    target_post_data = None
    target_post_text = ""

    if reply_to_post:
        try:
            # Сначала проверяем RAM messages_storage
            async with storage_lock:
                target_post_data = messages_storage.get(reply_to_post)
            # Затем БД
            if not target_post_data:
                target_post_data = await get_post_by_num(reply_to_post)

            if target_post_data:
                author = target_post_data.get("author_id")
                if author in (0, 1488148800):
                    is_direct_reply_to_chad = True
                else:
                    c_dict = target_post_data.get("content", {})
                    if isinstance(c_dict, str):
                        import json
                        try: c_dict = json.loads(c_dict)
                        except Exception: c_dict = {'text': c_dict}
                    if isinstance(c_dict, dict):
                        if (
                            c_dict.get("is_ai_roast")
                            or c_dict.get("is_ai")
                            or c_dict.get("is_ai_persona")
                            or "Киберчед" in str(c_dict)
                        ):
                            is_direct_reply_to_chad = True
                        target_post_text = c_dict.get('text') or c_dict.get('caption') or ""
        except Exception as e:
            logger.debug(f"[Cyberchad] Error checking target post {reply_to_post}: {e}")

    # Также проверяем прямое текстовое упоминание Киберчеда
    if not is_direct_reply_to_chad and text:
        if re.search(r'(?i)\b(киберчед|чед|cyberchad)\b', text):
            is_direct_reply_to_chad = True

    should_intervene = False
    is_direct_mode = False
    user_prompt_text = ""
    system_prompt = CYBERCHAD_FIGHT_INTERVENTION_PROMPT

    # Формируем контекст окружающих сообщений
    fight_snippets = []
    for _, u, t, p in recent_entries[-6:]:
        anon_tag = f"Анон [{get_anon_id(u)}]"
        p_ref = f" >>{p}" if p else ""
        fight_snippets.append(f"{anon_tag}{p_ref}: {t[:150]}")
    fight_context = "\n".join(fight_snippets)

    if is_direct_reply_to_chad:
        # Прямой ответ Киберчеду — проверяем только per-user cooldown (10s), не блокируясь 3600s таймером доски
        last_user_direct = _LAST_DIRECT_ROAST_USER_TS.get((board_id, user_id), 0.0)
        if now - last_user_direct < 10.0:
            return

        should_intervene = True
        is_direct_mode = True
        system_prompt = CYBERCHAD_DIRECT_ROAST_PROMPT

        # Извлекаем контекст цепочки предков
        chain_context = ""
        if reply_to_post:
            try:
                chain_context = await build_reply_chain_context(reply_to_post, max_depth=10)
            except Exception as chain_err:
                logger.debug(f"[Cyberchad] Error building chain context: {chain_err}")

        thread_context_part = f"=== КОНТЕКСТ ТРЕДА (ЦЕПОЧКА ОТВЕТОВ) ===\n{chain_context}\n\n" if chain_context else f"=== АТМОСФЕРА В ТРЕДЕ ===\n{fight_context}\n\n"
        target_post_part = f"=== ПОСТ КИБЕРЧЕДА, НА КОТОРЫЙ ОТВЕТИЛ АНОН ===\n>>{reply_to_post}: {target_post_text[:300]}\n\n" if (reply_to_post and target_post_text) else ""

        user_prompt_text = (
            f"{thread_context_part}"
            f"{target_post_part}"
            f"=== ДЕРЗКИЙ ОТВЕТ АНОНА [Анон {get_anon_id(user_id)} >>{post_num or 'new'}] ===\n"
            f"{text}\n\n"
            f"ТВОЙ ГОЛОСОВОЙ РАЗНОС (только текст реплики Киберчеда для озвучки):"
        )
    else:
        # Спонтанная интервенция в срач — строго проверяем кулдаун >= 3600с на доску!
        last_interv = _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION.get(board_id, 0.0)
        if now - last_interv < 3600.0:
            return

        if len(recent_entries) >= 4:
            # Проверяем наличие как минимум 2 разных участников и агрессивных маркеров срача
            authors = {e[1] for e in recent_entries}
            if len(authors) >= 2:
                aggro_count = 0
                aggro_patterns = (
                    r'>>\d+', r'\b(хуй|пизд|ебл|чухан|омег|терпил|соси|чмо|клоун|долбоеб|высер|пасть|уеб|завали|заточку|говно)\b'
                )
                for _, _, msg_txt, _ in recent_entries:
                    msg_low = msg_txt.lower()
                    if any(re.search(pat, msg_low) for pat in aggro_patterns):
                        aggro_count += 1
                if aggro_count >= 3:
                    should_intervene = True
                    is_direct_mode = False
                    system_prompt = CYBERCHAD_FIGHT_INTERVENTION_PROMPT
                    user_prompt_text = f"Разнеси участников этого срача в чате:\n\n{fight_context}"

    if should_intervene and user_prompt_text:
        if is_direct_mode:
            _LAST_DIRECT_ROAST_USER_TS[(board_id, user_id)] = now
        else:
            _LAST_SPONTANEOUS_CYBERCHAD_INTERVENTION[board_id] = now

        logger.info(f"💥 [Cyberchad Intervention] Запуск голосового разъёба на /{board_id}/ (direct: {is_direct_mode})...")
        try:
            raw = await summarize_text_with_hf(system_prompt, user_prompt_text, model_preference="persona")
            if raw and len(raw.strip()) > 5:
                roast_text = clean_html_tags(clean_ai_thinking(raw)).strip()
                voice_res = await synthesize_cyberchad_voice_with_meta(roast_text)
                voice_bytes = voice_res[0] if isinstance(voice_res, tuple) else voice_res

                if voice_bytes:
                    # ВАЖНО: СТРОГО ТОЛЬКО ГОЛОСОВОЕ СООБЩЕНИЕ, БЕЗ ТЕКСТОВОГО СООБЩЕНИЯ!
                    target_post_ref = post_num if is_direct_mode else (recent_entries[-1][3] if recent_entries else None)
                    await process_new_post(shared_state.NewPostParams(
                        bot_instance=bot,
                        board_id=board_id,
                        user_id=0,
                        content={
                            'type': 'voice',
                            'voice_bytes': voice_bytes,
                            'caption': '🔥 Разъёб от Киберчеда',
                            'is_ai_roast': True,
                            'is_ai': True,
                            'reply_to': target_post_ref
                        },
                        reply_to_post=target_post_ref,
                        is_shadow_muted=False,
                        stream=stream
                    ))
                    logger.info(f"✅ [Cyberchad Intervention] Голосовой разъёб успешно отправлен на /{board_id}/")
        except Exception as interv_err:
            logger.warning(f"⚠️ [Cyberchad Intervention] Ошибка интервенции: {interv_err}")


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
        
    raw_chain = []
    current_num = target_post_num
    visited = set()
    
    while current_num and current_num not in visited and len(raw_chain) < max_depth:
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
        elif not isinstance(content, dict):
            content = {'text': str(content)}
                
        author_id = post_data.get('author_id', -1)
        is_bot = (author_id == 0 or author_id == 1488148800)
        
        reply_to = post_data.get('reply_to_post_num') or post_data.get('reply_to') or content.get('reply_to_post')
        
        raw_chain.append({
            'post_num': current_num,
            'is_bot': is_bot,
            'author_id': author_id,
            'content': content,
            'reply_to': reply_to
        })
        
        current_num = reply_to

    if not raw_chain:
        return ""

    raw_chain.reverse()
    
    file_ids = set()
    for item in raw_chain:
        c = item.get('content', {})
        if isinstance(c, dict):
            fid = c.get('file_id')
            if fid and isinstance(fid, str):
                file_ids.add(fid)
            for m in c.get('media', []):
                if isinstance(m, dict) and m.get('file_id') and isinstance(m.get('file_id'), str):
                    file_ids.add(m.get('file_id'))

    media_meta_map = {}
    if file_ids:
        missing_file_ids = [fid for fid in file_ids if fid not in _MEDIA_DESC_CACHE]
        if missing_file_ids:
            try:
                db = await get_pool()
                placeholders = ",".join("?" for _ in missing_file_ids)
                async with db.execute(
                    f"SELECT file_id, tags, description FROM FileRegistry WHERE file_id IN ({placeholders})",
                    tuple(missing_file_ids)
                ) as cursor:
                    found_fids = set()
                    for row in await cursor.fetchall():
                        fid_val = row[0]
                        meta = {'tags': row[1] or '', 'description': row[2] or ''}
                        _format_media_context(meta)
                        _MEDIA_DESC_CACHE[fid_val] = meta
                        found_fids.add(fid_val)
                    for fid_val in missing_file_ids:
                        if fid_val not in found_fids:
                            _MEDIA_DESC_CACHE[fid_val] = {'tags': '', 'description': '', 'formatted': None}
            except Exception as meta_err:
                logger.debug(f"[reply_chain] Media meta batch load error: {meta_err}")

        for fid in file_ids:
            if fid in _MEDIA_DESC_CACHE:
                media_meta_map[fid] = _MEDIA_DESC_CACHE[fid]

    lines = []
    for item in raw_chain:
        content = item.get('content', {})
        msg_type = content.get('type', 'text') if isinstance(content, dict) else 'text'
        fid = content.get('file_id') if isinstance(content, dict) else None
        if not fid and isinstance(content, dict) and content.get('media'):
            for m in content.get('media', []):
                if isinstance(m, dict) and m.get('file_id'):
                    fid = m.get('file_id')
                    break
        media_meta = media_meta_map.get(fid) if fid else None
        formatted_text = _format_post_text(content, msg_type, media_meta=media_meta)
        if not formatted_text:
            formatted_text = f"[{msg_type}]" if msg_type else ""
        clean_text = clean_html_tags(formatted_text).replace('\n', ' ').strip()
        
        if item['is_bot']:
            sender = "ТЫ (Персона)"
        else:
            anon_hash = str(abs(hash(str(item.get('author_id', 'anon')))))[:4]
            sender = f"Анон #{anon_hash}"
        reply_prefix = f" (в ответ на #{item['reply_to']})" if item['reply_to'] else ""
        lines.append(f"• #{item['post_num']} [{sender}]{reply_prefix}: {clean_text[:300]}")
        
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
                'archive_allowed': True,
                'is_ai_persona': True,
                'is_ai': True,
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

def _fast_storage_ts(val) -> float:
    if type(val) is datetime:
        return val.timestamp()
    if val is None:
        return 0.0
    if type(val) in (int, float):
        return float(val)
    return normalize_storage_timestamp(val)

async def get_board_chunk(board_id: str, hours: int = 6, thread_id: str | None = None, lang: str | None = None) -> str:
    now_ts = time.time()
    time_threshold_ts = now_ts - (hours * 3600)
    stream_lang = lang or ('en' if board_id == 'int' else 'ru')
    
    async with storage_lock:
        if thread_id:
            b_data = board_data.get(board_id, {})
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info:
                return ""
            thread_post_nums = set(thread_info.get('posts', []))
            post_tuples = []
            for p_num, p in messages_storage.items():
                if p_num in thread_post_nums:
                    post_tuples.append((_fast_storage_ts(p.get('timestamp')), p))
            post_tuples.sort(key=operator.itemgetter(0))
            post_iterator = [p for _, p in post_tuples]
        else:
            board_posts = []
            for p in messages_storage.values():
                if p.get('board_id') == board_id and p.get('author_id') != 0:
                    board_posts.append((_fast_storage_ts(p.get('timestamp')), p))
            board_posts.sort(key=operator.itemgetter(0))
            
            total_board_posts = len(board_posts)
            if total_board_posts <= 150:
                post_iterator = [p for _, p in board_posts]
            else:
                posts_in_last_6h = [p for ts, p in board_posts if ts >= time_threshold_ts]
                count_6h = len(posts_in_last_6h)
                if count_6h < 150:
                    post_iterator = [p for _, p in board_posts[-150:]]
                elif count_6h > 200:
                    post_iterator = [p for _, p in board_posts[-200:]]
                else:
                    post_iterator = posts_in_last_6h

    # Batch-fetch media tags & descriptions for all image posts in post_iterator
    missing_file_ids = None
    for post in post_iterator:
        c = post.get('content')
        if isinstance(c, dict):
            fid = c.get('file_id')
            if fid and isinstance(fid, str) and fid not in _MEDIA_DESC_CACHE:
                if missing_file_ids is None:
                    missing_file_ids = []
                missing_file_ids.append(fid)
            elif not fid and c.get('media'):
                for m in c.get('media', []):
                    if isinstance(m, dict):
                        mfid = m.get('file_id')
                        if mfid and isinstance(mfid, str) and mfid not in _MEDIA_DESC_CACHE:
                            if missing_file_ids is None:
                                missing_file_ids = []
                            missing_file_ids.append(mfid)

    if missing_file_ids:
        missing_file_ids = list(dict.fromkeys(missing_file_ids))
        try:
            from common.database import get_pool
            db = await get_pool()
            placeholders = ",".join("?" for _ in missing_file_ids)
            async with db.execute(
                f"SELECT file_id, tags, description FROM FileRegistry WHERE file_id IN ({placeholders})",
                tuple(missing_file_ids)
            ) as cursor:
                found_fids = set()
                for row in await cursor.fetchall():
                    fid_val = row[0]
                    meta = {'tags': row[1] or '', 'description': row[2] or ''}
                    _format_media_context(meta)
                    _MEDIA_DESC_CACHE[fid_val] = meta
                    found_fids.add(fid_val)
                for fid_val in missing_file_ids:
                    if fid_val not in found_fids:
                        _MEDIA_DESC_CACHE[fid_val] = {'tags': '', 'description': '', 'formatted': None}
        except Exception as meta_err:
            logger.debug(f"[summarize] Media meta batch load error: {meta_err}")

    lines = []
    for post in post_iterator:
        try:
            content = post.get('content')
            if not isinstance(content, dict):
                continue
            
            fid = content.get('file_id')
            if not fid and content.get('media'):
                for m in content.get('media', []):
                    if isinstance(m, dict) and m.get('file_id'):
                        fid = m.get('file_id')
                        break
            
            media_meta = _MEDIA_DESC_CACHE.get(fid) if fid else None
            msg_type = content.get('type', 'text')

            text = _format_post_text(content, msg_type, media_meta=media_meta)
            if not text:
                continue

            name = content.get('username') or content.get('name') or content.get('author_name')
            if not name:
                author_id = post.get('author_id')
                if author_id and author_id != 0:
                    name = _get_cached_anon_name(author_id, stream_lang)
                else:
                    name = "Anon" if stream_lang == 'en' else ("名無し" if stream_lang == 'jp' else "Анон")

            reply_to = content.get('reply_to_post') or post.get('reply_to_post_num')
            if reply_to:
                if stream_lang == 'en':
                    lines.append(f"{name} (reply to #{reply_to}): {text}")
                elif stream_lang == 'jp':
                    lines.append(f"{name} (>>{reply_to}): {text}")
                else:
                    lines.append(f"{name} (Ответ на #{reply_to}): {text}")
            else:
                lines.append(f"{name}: {text}")
        except Exception as e:
            logger.warning(f"[summarize] Error while chunking post: {e}")

    # Accumulate lines from newest to oldest up to 35000 characters to avoid split lines
    total_len = 0
    limited_lines = []
    for line in reversed(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
        if '\n\n' in line_clean:
            line_clean = RE_MULTI_NEWLINES.sub('\n', line_clean)
        line_len = len(line_clean)
        if total_len + line_len + 1 > 35000:
            break
        limited_lines.append(line_clean)
        total_len += line_len + 1
    
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
            logger.warning(f"[atmosphere] Error fetching atmosphere posts: {e}")

    recent_posts.sort(key=lambda x: x[0])
    
    file_ids = set()
    for pnum, pdata in recent_posts:
        c = pdata.get('content', {})
        if isinstance(c, dict):
            fid = c.get('file_id')
            if fid and isinstance(fid, str):
                file_ids.add(fid)
            for m in c.get('media', []):
                if isinstance(m, dict) and m.get('file_id') and isinstance(m.get('file_id'), str):
                    file_ids.add(m.get('file_id'))

    media_meta_map = {}
    if file_ids:
        missing_file_ids = [fid for fid in file_ids if fid not in _MEDIA_DESC_CACHE]
        if missing_file_ids:
            try:
                db = await get_pool()
                placeholders = ",".join("?" for _ in missing_file_ids)
                async with db.execute(
                    f"SELECT file_id, tags, description FROM FileRegistry WHERE file_id IN ({placeholders})",
                    tuple(missing_file_ids)
                ) as cursor:
                    found_fids = set()
                    for row in await cursor.fetchall():
                        fid_val = row[0]
                        meta = {'tags': row[1] or '', 'description': row[2] or ''}
                        _format_media_context(meta)
                        _MEDIA_DESC_CACHE[fid_val] = meta
                        found_fids.add(fid_val)
                    for fid_val in missing_file_ids:
                        if fid_val not in found_fids:
                            _MEDIA_DESC_CACHE[fid_val] = {'tags': '', 'description': '', 'formatted': None}
            except Exception as meta_err:
                logger.debug(f"[atmosphere] Media meta batch load error: {meta_err}")

        for fid in file_ids:
            if fid in _MEDIA_DESC_CACHE:
                media_meta_map[fid] = _MEDIA_DESC_CACHE[fid]

    lines = []
    for pnum, pdata in recent_posts:
        content = pdata.get('content', {})
        if not isinstance(content, dict):
            content = {'text': str(content)}
        msg_type = content.get('type', 'text')
        fid = content.get('file_id')
        if not fid and content.get('media'):
            for m in content.get('media', []):
                if isinstance(m, dict) and m.get('file_id'):
                    fid = m.get('file_id')
                    break
        media_meta = media_meta_map.get(fid) if fid else None
        formatted_text = _format_post_text(content, msg_type, media_meta=media_meta)
        if not formatted_text:
            continue
        clean_text = clean_html_tags(formatted_text).replace('\n', ' ').strip()
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
        ext = os.path.splitext(file_info.file_path or "")[1].lower()
        if ext in ['.tgs', '.webm']:
            return None
        with tempfile.NamedTemporaryFile(suffix=ext or ".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download_file(file_info.file_path, tmp_path)
        
        logger.info(f"🖼 [TG_BOT] Downloading Telegram photo file_id='{photo_file_id[:15]}...' for Persona analysis")
        description = await describe_image(tmp_path, caption=caption, is_passive=False, source="TG_BOT")
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if description and not description.startswith("error_"):
            logger.info(f"✅ [TG_BOT] Photo analysis complete (desc='{description[:60]}...')")
            return description
        else:
            logger.warning(f"⚠️ [TG_BOT] Photo analysis produced no valid description ({description}).")
            return None
    except Exception as e:
        logger.error(f"⚠️ [TG_BOT] Telegram Vision Error: {e}", exc_info=True)
        return None
