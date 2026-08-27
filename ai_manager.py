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
            logger.warning(f"⚠️ [{log_prefix}] Отправка ГС запрещена настройками приватности чата/пользователя: {err}")
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

    # 2. Безопасный Fallback: отправка напрямую в чат через answer_voice
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
            logger.warning(f"⚠️ [{log_prefix}] Отправка ГС запрещена настройками чата: {fb_err}")
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

        # 2. Попытка 1: Groq Whisper STT (whisper-large-v3-turbo) с ротацией ключей
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
                    data = {"model": "whisper-large-v3-turbo", "response_format": "json"}
                    
                    async with httpx.AsyncClient(timeout=stt_timeout) as client:
                        resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                        if resp.status_code == 200:
                            res_data = resp.json()
                            candidate_text = res_data.get("text", "").strip()
                            if candidate_text:
                                transcript = candidate_text
                                logger.info(f"✅ [STT] Успешная расшифровка через Groq Whisper ({duration}с, {len(transcript)} симв.)")
                                break
                        elif resp.status_code in (413, 429, 500, 502, 503):
                            logger.warning(f"⚠️ [STT] Groq status {resp.status_code}, пробуем следующий ключ...")
                            continue
                except httpx.TimeoutException:
                    logger.warning(f"⚠️ [STT] Groq Timeout ({stt_timeout}s) для {duration}с аудио. Переход на Gemini...")
                    break
                except Exception as groq_err:
                    logger.warning(f"⚠️ [STT] Ошибка запроса к Groq: {groq_err}")
                    continue
        except Exception as e:
            logger.warning(f"⚠️ [STT] Ошибка пула Groq: {e}")

        # 3. Попытка 2: Gemini Multimodal Audio Fallback (нативная поддержка длинных аудио до 9.5 часов)
        if not transcript:
            try:
                import base64
                from common.token_pool import google_pool
                from summarize import _load_google_keys
                google_keys = getattr(google_pool, "tokens", []) or _load_google_keys()
                proxy_url = os.getenv("PROXY_URL") or None
                if google_keys:
                    b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                    mime_type = "video/mp4" if is_video_note else "audio/ogg"
                    gemini_payload = {
                        "contents": [
                            {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": b64_audio
                                        }
                                    },
                                    {
                                        "text": "Расшифруй это голосовое сообщение / видеозапись дословно на русском языке. Запиши строго только расшифрованный текст, без комментариев, пояснений, кавычек и вступительных фраз."
                                    }
                                ]
                            }
                        ]
                    }
                    gemini_timeout = max(45.0, min(240.0, float(duration) * 0.7 + 30.0))
                    for gkey in google_keys:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gkey}"
                        for proxy in [None, proxy_url] if proxy_url else [None]:
                            try:
                                async with httpx.AsyncClient(proxy=proxy, verify=False, timeout=gemini_timeout) as client:
                                    resp = await client.post(url, json=gemini_payload)
                                    if resp.status_code == 200:
                                        gdata = resp.json()
                                        parts = gdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                        if parts and "text" in parts[0]:
                                            candidate_text = parts[0]["text"].strip()
                                            if candidate_text and candidate_text != "[Тишина]" and len(candidate_text) > 1:
                                                transcript = candidate_text
                                                logger.info(f"✅ [STT] Успешная расшифровка через Gemini Audio ({duration}с, {len(transcript)} симв.)")
                                                break
                                    elif resp.status_code == 429:
                                        break
                            except Exception:
                                continue
                        if transcript:
                            break
            except Exception as gemini_stt_err:
                logger.warning(f"⚠️ [STT] Ошибка Gemini STT фолбэка: {gemini_stt_err}")

        # Если STT не отработал — молча выходим
        if not transcript:
            logger.warning(f"⚠️ [STT] Не удалось расшифровать аудио ({duration} сек)")
            return

        # 4. Генерация уничтожающего двачевского роаста
        roast = None
        transcript_for_roast = transcript[:2000]
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
                    f"Слова автора: «{transcript_for_roast}»"
                )
                from common.token_pool import groq_pool
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
    "Ты — ультра-токсичный, циничный, мизантропичный музыкальный критик и илитный сноб из раздела /b/ Двача. "
    "Твоя задача — максимально жестко, уничтожающе и с ядовитым двачерским сарказмом разнести музыкальный вкус анона, "
    "приславшего этот трек.\n"
    "Проанализируй исполнителя, название трека, звучание/жанр (дрилл, фонк, дед-инсайд рэп, попса, k-pop, кальянный рэп, шансон, аниме-ост, думающий автотюн-шлак, говнорок) "
    "и распознанный фрагмент текста/семпла.\n\n"
    "СТРОГИЕ ПРАВИЛА И ЗАПРЕТЫ:\n"
    "1. Запрещены любые приветствия, преамбулы и вежливые вступления (НЕЛЬЗЯ: 'Вот моя рецензия:', 'Привет', 'Слушай сюда', 'Ну что сказать').\n"
    "2. Запрещены оговорки, морализаторство, извинения, дисклеймеры и политкорректность.\n"
    "3. Запрещены кавычки вокруг всего ответа.\n"
    "4. Обращайся к автору строго на 'ты' (Ты — ...).\n"
    "5. Напиши 1-2 концентрированных, убийственно едких абзаца рецензии, а в самом конце на отдельной строке поставь вердикт и оценку по шкале говноедства в формате: 'ОЦЕНКА: <оценка>/10 💩 (<краткий диагноз>)'.\n"
    "6. Используй аутентичный двачерский сленг и отборный мат по делу."
)

DEFAULT_MUSIC_ROASTS = [
    (
        "Ты на полном серьезе включил это убожество и решил, что другим анонам не все равно на твой дегенеративный вкус? "
        "Бессвязное бубнение под три притопа два прихлопа, сведенное глухим школьником на коленке.",
        "10/10 💩 (Шедевр мочи)"
    ),
    (
        "Типичный автотюновый высер для малолетних тиктокеров без намека на слух и смысл. "
        "Твой плейлист нужно немедленно сжечь в биореакторе вместе с наушниками.",
        "9/10 💩 (Ушной СПИД)"
    ),
    (
        "Такое чувство, что исполнитель записал этот трек сидя на унитазе в приступе тяжелой диареи. "
        "А ты это радостно хаваешь и еще на доску тащишь.",
        "10/10 💩 (Потомственный говноед)"
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

        # 2. Транскрипция текста песни/семпла через STT (Whisper + Gemini fallback)
        transcript = None
        if audio_bytes:
            stt_timeout = max(60.0, min(300.0, float(duration) * 0.8 + 45.0))
            # Попытка 1: Groq Whisper
            try:
                from common.token_pool import groq_pool
                groq_tokens = getattr(groq_pool, "tokens", []) or (groq_pool.get_all_active_tokens() if hasattr(groq_pool, "get_all_active_tokens") else []) or []
                if not groq_tokens and os.getenv("GROQ_API_KEY"):
                    groq_tokens = [os.getenv("GROQ_API_KEY")]

                ext = os.path.splitext(filename.lower())[1] if filename else ".mp3"
                if not ext or ext not in MUSIC_EXTENSIONS:
                    ext = ".mp3"

                for token in groq_tokens:
                    if not token:
                        continue
                    try:
                        headers = {"Authorization": f"Bearer {token}"}
                        files = {"file": (f"track{ext}", audio_bytes, mime_type)}
                        data = {"model": "whisper-large-v3-turbo", "response_format": "json"}
                        async with httpx.AsyncClient(timeout=stt_timeout) as client:
                            resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                            if resp.status_code == 200:
                                res_data = resp.json()
                                candidate_text = res_data.get("text", "").strip()
                                if candidate_text:
                                    transcript = candidate_text
                                    logger.info(f"✅ [Music STT] Успешная расшифровка через Groq Whisper ({len(transcript)} симв.)")
                                    break
                            elif resp.status_code in (413, 429, 500, 502, 503):
                                continue
                    except httpx.TimeoutException:
                        break
                    except Exception as groq_err:
                        logger.warning(f"⚠️ [Music STT] Groq error: {groq_err}")
                        continue
            except Exception as e:
                logger.warning(f"⚠️ [Music STT] Groq pool error: {e}")

            # Попытка 2: Gemini Audio Fallback
            if not transcript:
                try:
                    import base64
                    from common.token_pool import google_pool
                    from summarize import _load_google_keys
                    google_keys = getattr(google_pool, "tokens", []) or (google_pool.get_all_active_tokens() if hasattr(google_pool, "get_all_active_tokens") else []) or _load_google_keys()
                    proxy_url = os.getenv("PROXY_URL") or None
                    if google_keys:
                        b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                        gemini_payload = {
                            "contents": [
                                {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": mime_type if mime_type.startswith("audio/") else "audio/mpeg",
                                                "data": b64_audio
                                            }
                                        },
                                        {
                                            "text": "Расшифруй слова/текст этой песни или аудиозаписи дословно на языке оригинала. Запиши строго только распознанный текст песни или фрагмента, без комментариев, пояснений, кавычек и вступительных фраз. Если это инструментал без слов, напиши [Инструментал]."
                                        }
                                    ]
                                }
                            ]
                        }
                        gemini_timeout = max(45.0, min(240.0, float(duration) * 0.7 + 30.0))
                        for gkey in google_keys:
                            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gkey}"
                            for proxy in [None, proxy_url] if proxy_url else [None]:
                                try:
                                    async with httpx.AsyncClient(proxy=proxy, verify=False, timeout=gemini_timeout) as client:
                                        resp = await client.post(url, json=gemini_payload)
                                        if resp.status_code == 200:
                                            gdata = resp.json()
                                            parts = gdata.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                            if parts and "text" in parts[0]:
                                                cand = parts[0]["text"].strip()
                                                if cand and cand not in ("[Тишина]", "[Инструментал]") and len(cand) > 1:
                                                    transcript = cand
                                                    logger.info(f"✅ [Music STT] Успешная расшифровка через Gemini Audio ({len(transcript)} симв.)")
                                                    break
                                        elif resp.status_code == 429:
                                            break
                                except Exception:
                                    continue
                            if transcript:
                                break
                except Exception as gemini_err:
                    logger.warning(f"⚠️ [Music STT] Gemini audio error: {gemini_err}")

        # Обработка инструментала/отсутствия слов
        if transcript:
            cleaned_trans = transcript.strip()
            if cleaned_trans in ("[Инструментал]", "[Инструментальная музыка]", "[Тишина]", "") or len(cleaned_trans) < 2:
                lyrics_sample = "[Инструментальный трек / неразборчивый вокал]"
            else:
                lyrics_sample = cleaned_trans[:350]
        elif sample_note:
            lyrics_sample = sample_note
        else:
            lyrics_sample = "[Инструментальный трек / неразборчивый вокал]"

        # 3. Генерация 2ch /b/ музыкальной рецензии
        roast_text = None
        rating = None
        try:
            track_context = f"Исполнитель: «{artist}»\nНазвание трека: «{title}»\nДлительность: {dur_str}\nФрагмент текста/семпла: «{lyrics_sample}»"
            user_msg = f"Отрецензируй и уничтожь следующий музыкальный трек:\n\n{track_context}"
            raw_ai_roast = await summarize_text_with_hf(MUSIC_ROAST_SYSTEM_PROMPT, user_msg, model_preference="persona")
            if raw_ai_roast and len(raw_ai_roast.strip()) > 5:
                roast_text, rating = parse_music_roast_response(raw_ai_roast)
        except Exception as ai_err:
            logger.warning(f"⚠️ [Music Roast] Ошибка генерации ИИ-рецензии: {ai_err}")

        if not roast_text or not rating:
            fb_text, fb_rating = random.choice(DEFAULT_MUSIC_ROASTS)
            if not roast_text:
                roast_text = fb_text
            if not rating:
                rating = fb_rating

        # Форматирование итогового ответа
        formatted_response = (
            f"🎵 <b>Трек:</b> {escape_html(artist)} — {escape_html(title)} (<i>{dur_str}</i>)\n"
            f"📝 <b>Текст / Семпл:</b> <i>«{escape_html(lyrics_sample)}»</i>\n\n"
            f"🔥 <b>Вердикт /b/ музкритика:</b>\n"
            f"{escape_html(roast_text)}\n\n"
            f"💩 <b>Шкала говноедства:</b> {escape_html(rating)}"
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

async def get_board_chunk(board_id: str, hours: int = 6, thread_id: str | None = None, lang: str | None = None) -> str:
    now_ts = time.time()
    time_threshold_ts = now_ts - (hours * 3600)
    lines = []
    
    async with storage_lock:
        if thread_id:
            b_data = board_data[board_id]
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info:
                return ""
            thread_post_nums = set(thread_info.get('posts', []))
            post_iterator = [p for p_num, p in messages_storage.items() if p_num in thread_post_nums]
            time_threshold_ts = 0.0
            # Сортируем сообщения треда по времени
            post_iterator.sort(key=lambda x: normalize_storage_timestamp(x.get('timestamp')))
        else:
            board_posts = [p for p in messages_storage.values() if p.get('board_id') == board_id and p.get('author_id') != 0]
            board_posts.sort(key=lambda x: normalize_storage_timestamp(x.get('timestamp')))
            
            posts_in_last_6h = [p for p in board_posts if normalize_storage_timestamp(p.get('timestamp')) >= time_threshold_ts]
            count_6h = len(posts_in_last_6h)
            
            # 150-200 последних сообщений либо 6 часов (выбираем оптимальный диапазон)
            if count_6h < 150:
                target_posts = board_posts[-150:]
            elif count_6h > 200:
                target_posts = board_posts[-200:]
            else:
                target_posts = posts_in_last_6h
            post_iterator = target_posts
            time_threshold_ts = 0.0
    for post in post_iterator:
        try:
            if post.get('board_id') != board_id:
                continue
            if normalize_storage_timestamp(post.get('timestamp')) < time_threshold_ts:
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
