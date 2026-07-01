import sys

"""
main.py
This module serves as the main entry point for the FastAPI application, handling various functionalities 
related to a web service that interacts with users and processes requests. 
Key Features:
- Implements a FastAPI application with various endpoints for user interactions.
- Integrates with external services for image processing, translation, and database management.
- Provides middleware for security, logging, and request handling.
- Implements rate limiting and IP address filtering to prevent abuse.
- Supports background tasks for processing and updating data asynchronously.
- Utilizes caching mechanisms to optimize performance.
- Handles file uploads and interactions with external APIs.
Modules and Functions:
- get_real_ip: Extracts the real IP address from the request headers.
- get_country_by_ip: Determines the country associated with a given IP address.
- is_ip_restricted: Checks if an IP address is from a banned subnet or a Tor exit node.
- is_bot_by_headers: Detects if a request is made by a bot based on headers.
- update_tor_nodes_task: Background task to update the list of Tor exit nodes.
- Various database interaction functions for managing posts, threads, and user data.
- Logging setup for tracking application events and user interactions.
Constants:
- PROXY_URL: URL for the proxy server.
- SECRET_KEY: Secret key for hashing and security purposes.
- BANNED_SUBNETS: List of IP subnets that are restricted from accessing the service.
- TOR_EXIT_NODES: Set of known Tor exit nodes to block.
Classes:
- NewPost: Pydantic model for validating new post data.
- BytesUploadFile: Wrapper class for handling byte data as file uploads.
This module is designed to be extensible and maintainable, allowing for future enhancements and integrations.
    """
import os
import asyncio
from common.task_manager import spawn_task
import json
import time
import re
import faulthandler

import hmac
import hashlib
import tracemalloc
import io
import mimetypes
import random
import secrets

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.locales import TRANSLATIONS
from common.async_file_io import (
    copy_fileobj_to_temp_async,
    read_file_bytes_async,
    remove_files_best_effort_async,
)
from common.async_process import AsyncProcessError, run_process_checked
from common.audio_effects import get_audio_filter
from common.secret_redaction import (
    add_secret_redaction_filter,
    install_logging_redaction,
)
from site_tgach.mirror_worker import close_internal_file_bots, process_mirror_queue
from site_tgach.tagging_worker import tagging_loop
import logging
from collections import defaultdict
from fastapi.responses import StreamingResponse
import orjson
import uuid
import html
import ipaddress
import socket
from fastapi import BackgroundTasks
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi import Form
import httpx
from httpx import AsyncHTTPTransport
from site_tgach.security import (
    get_pow_challenge_data,
    verify_pow,
    check_ddos,
    DEFAULT_POW_DIFFICULTY,
)
from common.database import add_file_mirror, ban_hash
from warhammer_mode import warhammer_transform
from site_tgach.image_processing import (
    apply_grimdark_filter_async,
    shutdown_image_executors,
)
from site_tgach.mtproto_client import _cleanup_idle_clients, close_all_mtproto_clients

try:
    from japanese_translator import (
        get_random_anime_image,
        get_monogatari_image,
        get_nsfw_anime_image,
        get_loli_image,
    )
except ImportError:
    print(
        "⚠️ Не удалось импортировать japanese_translator. Проверь наличие файла в корне."
    )
from site_tgach.catbox import upload_url_to_catbox
from common.database import initialize_database
from bs4 import BeautifulSoup
from site_tgach.neuro_poster import NeuroManager
from site_tgach.rss import generate_rss
from slowapi.util import get_remote_address
from common.config import ENABLE_MULTILANG
from common.database import (
    create_report,
    get_active_reports,
    set_user_stream,
    resolve_report,
    get_detailed_statistics,
    get_all_feedback,
    get_board_media_posts,
    get_updates_since,
    get_activity_history,
    get_poll_results,
)
from collections import deque, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from async_lru import alru_cache
from functools import lru_cache
from pydantic import BaseModel, Field
from common.locales import get_t
from common.database import (
    set_system_setting,
    get_system_setting,
    create_import_request,
    get_pending_import_requests,
    update_import_request_status,
    cleanup_shadow_posts_db,
    get_thread_type_and_unlock_status,
    cleanup_broadcast_queue,
)
from fastapi.middleware.gzip import GZipMiddleware


@alru_cache(maxsize=32, ttl=60)
async def get_setting_cached(key: str) -> str:
    return await get_system_setting(key)


import uvicorn
import aiohttp
from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    File,
    UploadFile,
    Form,
    Depends,
    BackgroundTasks,
    Body,
)
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import (
    RedirectResponse,
    StreamingResponse,
    Response,
    HTMLResponse,
    JSONResponse,
)
from starlette.background import BackgroundTask
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

faulthandler.enable()


def get_real_ip(request: Request) -> str:
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host


GEOIP_READER = None

_geoip_init_lock = asyncio.Lock()


@alru_cache(maxsize=10000, ttl=3600)
async def get_country_by_ip(ip: str) -> str:
    global GEOIP_READER
    if ip in ("127.0.0.1", "localhost", "::1"):
        return "XX"

    if GEOIP_READER is None:
        try:
            import geoip2.database

            db_full_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "GeoLite2-Country.mmdb"
            )
            if os.path.exists(db_full_path):
                async with _geoip_init_lock:
                    if GEOIP_READER is None:
                        GEOIP_READER = await asyncio.to_thread(
                            geoip2.database.Reader, db_full_path
                        )
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Failed to load GeoIP DB: {e}")

    if GEOIP_READER:
        try:
            response = await asyncio.to_thread(GEOIP_READER.country, ip)
            return response.country.iso_code or "XX"
        except:
            pass

    strategies = [
        {"proxy": PROXY_URL, "name": "Proxy"},
        {"proxy": None, "name": "Direct"},
    ]

    for strategy in strategies:
        try:
            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(
                timeout=3.0,
                verify=False,
                proxy=strategy["proxy"],
                transport=transport,
                trust_env=True,
            ) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}")
                if resp.status_code == 200:
                    return resp.json().get("countryCode", "XX")
        except:
            continue

    return "XX"


limiter = Limiter(key_func=get_real_ip)
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from aiogram import Bot
from itsdangerous import TimestampSigner, BadSignature
from common.config import STORAGE_CHANNELS
from common.bot_pool import global_bot_pool

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import unicodedata
from common.board_config import (
    BOARD_CONFIG,
    BOT_USERNAME,
    FILE_STORAGE_CHANNEL_ID,
    FILE_UPLOADER_BOT_TOKEN,
    THREAD_MEDIA_CHANNEL_ID,
)
from site_tgach.security import IP_BAN_LIST
from fastapi.responses import ORJSONResponse
from common.database import (
    get_op_posts_for_board,
    create_post,
    get_thread_by_op_post,
    update_shadow_mute,
    get_banned_users,
    get_shadow_muted_users,
    lift_ban,
    lift_shadow_ban,
    process_mentions_and_notify,
    get_post_by_num,
    update_post_content,
    get_post_for_broadcast,
    create_bottle,
    get_unread_bottle_count,
    read_and_delete_bottle,
    get_posts_from_broadcast_queue,
    get_user_status,
    get_shadow_mute_status,
    get_thread_op_by_post_num,
    apply_regular_mute,
    get_user_by_token,
    toggle_op_hidden,
    get_user_posts_from_list,
    create_thread_entry,
    get_post_count_in_thread,
    is_thread_archived,
    archive_thread_in_db,
    search_posts,
    delete_post_by_num,
    ban_user_on_board,
    get_chat_posts_for_board,
    get_post_copies,
    get_global_chat_posts,
    log_global_event,
    get_db_connection,
    get_all_media_from_thread,
    sync_boards_with_config,
    get_thread_ids_for_posts,
    create_alert,
    get_pending_alerts,
    mark_alert_read,
    get_all_boards_for_admin,
    set_user_role,
    get_user_role,
    get_all_alerts_for_admin,
    register_file_owner,
    get_file_owner_id,
    create_feedback,
    process_cross_links,
    get_unread_feedback_count,
    mark_feedback_read,
    get_file_mirrors,
    get_banned_files_list,
    unban_hash,
    get_blurhashes_batch,
    get_duplicate_counts,
    cleanup_old_posts_from_db,
    get_random_video_post,
    get_random_image_post,
    get_random_active_thread,
    refresh_random_indexes,
    add_post_to_random_cache,
    get_recent_posts_global,
    get_full_user_info,
    get_global_feed_posts,
    process_backlinks,
    add_to_mirror_queue,
    get_mod_queue,
    resolve_mod_queue,
    get_unread_replies_count,
    get_user_replies,
    mark_replies_read,
    toggle_post_censorship,
    get_recent_tags_summary,
    get_file_tags,
    search_files_by_tags,
    get_posts_by_file_ids,
    get_newspaper_data,
)
from site_tgach.backup import backup_loop
from site_tgach.importer import process_import_queue
from site_tgach.neuro_scanner import scanner_loop, SCANNER_TRIGGER
import asyncio
from common.db_pool import create_pool, close_pool, get_pool
from common.bot_pool import global_bot_pool
from site_tgach.admin_config import ADMIN_IDS
from site_tgach.image_processing import process_and_upload_image
from site_tgach.mirror_health import is_hf_link_allowed
from site_tgach.voice_processing import process_and_upload_voice
from PIL import Image as PilImage

PilImage.MAX_IMAGE_PIXELS = 49_000_000
import logging
import uuid

VALID_HF_REPOS = set()
try:
    _hf_accs = os.getenv("HF_ACCOUNTS", "")
    if _hf_accs:
        for _acc in _hf_accs.split(","):
            if ":" in _acc:
                _parts = _acc.split(":")
                if len(_parts) >= 2:
                    VALID_HF_REPOS.add(_parts[1].strip())
    print(f"✅ Loaded {len(VALID_HF_REPOS)} valid HF repos for link filtering.")
except Exception as e:
    print(f"⚠️ Error parsing HF_ACCOUNTS for filtering: {e}")

# --- БЛОК ЗАЩИТЫ ОТ TOR И ПЛОХИХ ПОДСЕТЕЙ ---
TOR_EXIT_NODES = set()
BANNED_SUBNETS = [
    ipaddress.ip_network("185.220.101.0/24"),  # Сетка Tor (брутфорсеры)
    ipaddress.ip_network("185.243.218.0/24"),  # Подозрительная сетка из логов
]


async def update_tor_nodes_task():
    """Фоновая задача обновления списка Tor."""
    global TOR_EXIT_NODES
    url = "https://check.torproject.org/exit-addresses"
    while True:
        try:
            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(
                transport=transport, timeout=30.0, verify=False
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    new_nodes = set(
                        re.findall(r"ExitAddress\s+(\d+\.\d+\.\d+\.\d+)", resp.text)
                    )
                    if new_nodes:
                        TOR_EXIT_NODES = new_nodes
                        logger.info(
                            f"🛡️ TOR BLOCKER: Loaded {len(TOR_EXIT_NODES)} exit nodes."
                        )
        except Exception as e:
            logger.error(f"Failed to update Tor nodes: {e}")
        await asyncio.sleep(3600)


def is_ip_restricted(ip_str: str) -> bool:
    """Проверка IP на Тор или бан-сетку."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_str in TOR_EXIT_NODES:
            return True
        for subnet in BANNED_SUBNETS:
            if ip_obj in subnet:
                return True
    except:
        pass
    return False


async def is_request_from_ru(request: Request) -> bool:
    ip = get_real_ip(request)
    country = await get_country_by_ip(ip)
    return country == "RU"


from logging.handlers import RotatingFileHandler


class _RequestIdDefaultFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "SYSTEM"
        return True


def _add_request_id_filter(handler: logging.Handler) -> logging.Handler:
    handler.addFilter(_RequestIdDefaultFilter())
    return handler


file_handler = _add_request_id_filter(
    RotatingFileHandler(
        "site.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
)
stream_handler = _add_request_id_filter(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(request_id)s] - %(message)s",
    handlers=[file_handler, stream_handler],
    force=True,
)
install_logging_redaction()
logger = logging.getLogger(__name__)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class RequestIdAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = self.extra.copy()
        if "extra" in kwargs:
            extra.update(kwargs["extra"])
        extra.setdefault("request_id", "SYSTEM")
        kwargs["extra"] = extra
        return msg, kwargs


logger = RequestIdAdapter(logger, {})

# Настройка компактного логгера посетителей
visitor_fh = RotatingFileHandler(
    "visitors.log", maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8"
)
visitor_fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
add_secret_redaction_filter(visitor_fh)
v_logger = logging.getLogger("visitor_tracker")
v_logger.addHandler(visitor_fh)
v_logger.setLevel(logging.INFO)
v_logger.propagate = False  # Не дублировать в основную консоль

# Реестр IP для отслеживания новых входов (сбрасывается при рестарте)
KNOWN_IPS = set()
# Ручной список троллинга: { "ip": "mode" }
IP_TROLL_CONFIG = {}

TELEGRAM_FILE_SEMAPHORE = asyncio.Semaphore(250)
UPLOAD_SEMAPHORE = asyncio.Semaphore(4)
POST_RATE_LIMITER = deque()
SITE_CACHE_CLEANUP_INTERVAL_SEC = int(
    os.getenv("SITE_CACHE_CLEANUP_INTERVAL_SEC", "300")
)
SITE_FASTAPI_CACHE_MAX_KEYS = int(os.getenv("SITE_FASTAPI_CACHE_MAX_KEYS", "5000"))
SITE_THREAD_VERSION_TTL_SEC = int(os.getenv("SITE_THREAD_VERSION_TTL_SEC", "86400"))
SITE_THREAD_VERSION_MAX_KEYS = int(os.getenv("SITE_THREAD_VERSION_MAX_KEYS", "5000"))
SITE_FLOOD_TRACKER_TTL_SEC = int(os.getenv("SITE_FLOOD_TRACKER_TTL_SEC", "60"))
SITE_SECURITY_MAP_MAX_KEYS = int(os.getenv("SITE_SECURITY_MAP_MAX_KEYS", "10000"))
SITE_DB_MAINTENANCE_ENABLED = os.getenv(
    "SITE_DB_MAINTENANCE_ENABLED", "0"
).strip().lower() in {"1", "true", "yes", "on"}
RANDOM_DEAD_FILE_TTL_SEC = int(os.getenv("SITE_RANDOM_DEAD_FILE_TTL_SEC", "3600"))
RANDOM_DEAD_FILE_MAX_KEYS = int(os.getenv("SITE_RANDOM_DEAD_FILE_MAX_KEYS", "5000"))
RANDOM_API_DEADLINE_SEC = float(os.getenv("SITE_RANDOM_API_DEADLINE_SEC", "6.0"))
RANDOM_AVAILABILITY_TIMEOUT_SEC = float(
    os.getenv("SITE_RANDOM_AVAILABILITY_TIMEOUT_SEC", "2.5")
)
RANDOM_DEAD_FILE_IDS: dict[str, float] = {}


def _mark_random_dead_file(file_id: str | None):
    if not file_id:
        return
    now = time.time()
    if len(RANDOM_DEAD_FILE_IDS) >= RANDOM_DEAD_FILE_MAX_KEYS:
        cutoff = now - RANDOM_DEAD_FILE_TTL_SEC
        for key, ts in list(RANDOM_DEAD_FILE_IDS.items()):
            if ts < cutoff:
                RANDOM_DEAD_FILE_IDS.pop(key, None)
        while len(RANDOM_DEAD_FILE_IDS) >= RANDOM_DEAD_FILE_MAX_KEYS:
            RANDOM_DEAD_FILE_IDS.pop(next(iter(RANDOM_DEAD_FILE_IDS)), None)
    RANDOM_DEAD_FILE_IDS[str(file_id)] = now


def _is_random_dead_file(file_id: str | None) -> bool:
    if not file_id:
        return False
    ts = RANDOM_DEAD_FILE_IDS.get(str(file_id))
    if not ts:
        return False
    if time.time() - ts > RANDOM_DEAD_FILE_TTL_SEC:
        RANDOM_DEAD_FILE_IDS.pop(str(file_id), None)
        return False
    return True


def _upload_bot_attempt_count(stream: str) -> int:
    if not global_bot_pool:
        return 0
    try:
        global_bot_pool.init_stream(stream)
        target_stream = stream if stream in global_bot_pool.iterators else "ru"
        if target_stream not in global_bot_pool.iterators:
            global_bot_pool.init_stream("ru")
            target_stream = "ru"
        bots = global_bot_pool.bots_map.get(target_stream) or {}
        return min(max(len(bots), 1), 4)
    except Exception:
        return 1


async def upload_with_bot_pool(
    file_obj, stream: str, channel_id: int, max_size_bytes: int, log
) -> tuple:
    if not global_bot_pool:
        log.error("Upload error: bot pool is unavailable")
        return (None, None)

    content_type = file_obj.content_type or "application/octet-stream"
    func = (
        process_and_upload_voice
        if content_type.startswith("audio/")
        else process_and_upload_image
    )
    attempts = _upload_bot_attempt_count(stream)
    tried_bot_ids = set()
    last_error = None

    for _ in range(attempts):
        try:
            bot_id, bot_inst = global_bot_pool.get_next_bot(stream)
        except Exception as e:
            last_error = e
            break

        if bot_id in tried_bot_ids:
            continue
        tried_bot_ids.add(bot_id)

        try:
            await file_obj.seek(0)
        except Exception:
            pass

        try:
            res = await func(file_obj, max_size_bytes, bot_inst, channel_id)
            return (res, bot_id)
        except HTTPException as e:
            last_error = e
            if e.status_code < 500:
                break
            log.warning(f"Upload retryable error on bot {bot_id}: {e.detail}")
        except Exception as e:
            last_error = e
            log.warning(f"Upload retryable error on bot {bot_id}: {e}")

    log.error(f"Upload failed after bot pool retries: {last_error}")
    return (None, None)


def _file_owner_pairs_for_upload_result(
    res_data: dict, uploader_bot_id: int | None
) -> list[tuple[str, int]]:
    pairs = []
    if not isinstance(res_data, dict):
        return pairs

    is_dedup = bool(res_data.get("dedup_found"))
    owner_bot_id = res_data.get("owner_bot_id")
    if owner_bot_id is None and not is_dedup:
        owner_bot_id = uploader_bot_id

    original_file_id = res_data.get("original_file_id")
    if original_file_id and owner_bot_id:
        pairs.append((original_file_id, owner_bot_id))

    thumbnail_owner_bot_id = res_data.get("thumbnail_owner_bot_id")
    if thumbnail_owner_bot_id is None and not is_dedup:
        thumbnail_owner_bot_id = owner_bot_id or uploader_bot_id

    thumbnail_file_id = res_data.get("thumbnail_file_id")
    if thumbnail_file_id and thumbnail_owner_bot_id:
        pairs.append((thumbnail_file_id, thumbnail_owner_bot_id))

    return pairs


# Лимиты для удержания ботов в ловушках (защита слотов соединений сервера)
ACTIVE_TROLL_CONNS = 0
MAX_TROLL_CONNS = 128
from common.database import get_archived_threads, get_chat_posts_for_board
from common.database import restore_thread_from_archive
from common.database import toggle_thread_pin
from common.database import load_all_spam_words, add_spam_word, remove_spam_word

try:
    import psutil
except ImportError:
    psutil = None
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8")
SITE_ACCESS_MODE = "PUBLIC"
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("Необходимо установить SECRET_KEY в вашем .env файле.")


def get_user_hash(user_id: Union[int, str]) -> str:

    if not user_id:
        return "system"
    return hashlib.sha256((str(user_id) + SECRET_KEY).encode()).hexdigest()[:12]


# --- Детерминированные ники из хеша автора ---
_SITE_NICK_PREFIXES = [
    "Базированный",
    "Всратый",
    "Мамкин",
    "Поехавший",
    "Соевый",
    "Диванный",
    "Опущенный",
    "Гойский",
    "Толстый",
    "Порватый",
    "Латентный",
    "Просветленный",
    "Элитный",
    "Подпивасный",
    "Двачевский",
    "Педальный",
    "Токсичный",
    "Кринжовый",
    "Аутичный",
    "Думерский",
    "Рядовой",
    "Школьный",
    "Отбитый",
    "Метаироничный",
    "Скрытый",
    "Сигма",
    "Альфа",
    "Омега",
    "Сажный",
    "Вайбовый",
    "Копиумный",
    "Попущенный",
    "Лютый",
    "Абсолютный",
    "Печальный",
    "Нищуковский",
    "Душный",
    "Шизоидный",
    "Паленый",
    "Забивной",
    "Плюшевый",
    "Астральный",
    "Комнатный",
]
_SITE_NICK_SUFFIXES = [
    "Битард",
    "Скуф",
    "Шиз",
    "Анон",
    "Ньюфаг",
    "Олдфаг",
    "Омеган",
    "Шитпостер",
    "Сыч",
    "Двачер",
    "Чухан",
    "Куколд",
    "Нормис",
    "Гигачад",
    "Подпивас",
    "Зумер",
    "Бумер",
    "Сояк",
    "Инцел",
    "Думер",
    "Говноед",
    "Симп",
    "Чмоня",
    "Байтер",
    "Ноулайфер",
    "Тролль",
    "Моралфаг",
    "Альтушка",
    "Масик",
    "Школьник",
    "Дед",
    "Хиккан",
    "Скуфидон",
    "Терпила",
    "Вахтер",
    "Тентакль",
    "Мыслитель",
    "Философ",
    "Дворник",
    "Эрудит",
    "Чел",
]


def nick_from_hash(author_id: str) -> str:
    """Детерминированный ник из 12-символьного хеша автора. Без раскрытия identity."""
    if not author_id or author_id == "system":
        return "Аноним"
    # Берём первые 8 hex-символов как seed
    try:
        seed = int(author_id[:8], 16)
    except (ValueError, TypeError):
        return "Аноним"
    rng = random.Random(seed)
    prefix = rng.choice(_SITE_NICK_PREFIXES)
    suffix = rng.choice(_SITE_NICK_SUFFIXES)
    return f"{prefix} {suffix}"


class NoParsingFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if (
            "Data should not be empty" in msg
            or "_SelectorSocketTransport" in msg
            or "_ProactorBasePipeTransport" in msg
            or "WinError 10054" in msg
        ):
            return False
        return True


PROXY_URL = "http://127.0.0.1:10808"
BOT_VIOLATIONS = defaultdict(int)
IP_WHITELIST = set()  # Сюда можно будет добавлять IP через админку (или пока вручную)
GEO_IP_CLIENT = httpx.AsyncClient(
    timeout=3.0,
    verify=False,
    transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=5),
)
# Применяем фильтр к asyncio
logging.getLogger("asyncio").addFilter(NoParsingFilter())
logging.getLogger("uvicorn.error").addFilter(NoParsingFilter())
BUMP_LIMIT = 600
CAPTCHA_SESSIONS = {}
SPAM_WORDS_CACHE: Dict[str, set] = defaultdict(set)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r'(https?://[^\s<>"\'`]+)')
CROSS_LINK_PATTERN = re.compile(r">>/([a-z0-9]+)/(\d+)")
REF_LINK_PATTERN = re.compile(r"(>>(\d+))")
SPOILER_PATTERN = re.compile(r"\|\|(.+?)\|\|")
SCRIPT_TAG_PATTERN = re.compile(
    r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", flags=re.IGNORECASE | re.DOTALL
)
SCRIPT_SINGLE_TAG_PATTERN = re.compile(r"<\s*script\b[^>]*>", flags=re.IGNORECASE)
EVENT_HANDLER_PATTERN_DOUBLE = re.compile(r'\s+on\w+\s*=\s*".*?"', flags=re.IGNORECASE)
EVENT_HANDLER_PATTERN_SINGLE = re.compile(r"\s+on\w+\s*=\s*'.*?'", flags=re.IGNORECASE)
DANGEROUS_TAGS = ["iframe", "svg", "form", "object", "embed", "link", "a", "style"]
ARCHIVE_LOCKS = defaultdict(asyncio.Lock)
DANGEROUS_TAG_PATTERNS = [
    (
        re.compile(
            rf"<\s*{tag}\b[^>]*>.*?<\s*/\s*{tag}\s*>", flags=re.IGNORECASE | re.DOTALL
        ),
        re.compile(rf"<\s*{tag}\b[^>]*>", flags=re.IGNORECASE),
    )
    for tag in DANGEROUS_TAGS
]


class NewPost(BaseModel):
    text: str = Field(..., max_length=20000)
    reply_to: Optional[int] = None


class BytesUploadFile:
    """Обертка для байтов, имитирующая UploadFile для функции process_and_upload."""

    def __init__(self, data: bytes, filename: str, content_type: str):
        self.file = io.BytesIO(data)
        self.filename = filename
        self.content_type = content_type
        self.size = len(data)

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    async def seek(self, offset: int):
        self.file.seek(offset)

    async def close(self):
        pass


ANIME_COMMAND_MAP = {
    "fap": get_random_anime_image,
    "Fap": get_random_anime_image,
    "FAP": get_random_anime_image,
    "hent": get_random_anime_image,
    "hentai": get_random_anime_image,
    "hentay": get_random_anime_image,
    "Hent": get_random_anime_image,
    "Hentai": get_random_anime_image,
    "Hentay": get_random_anime_image,
    "nsfw": get_nsfw_anime_image,
    "NSFW": get_nsfw_anime_image,
    "Nsfw": get_nsfw_anime_image,
    "gatari": get_monogatari_image,
    "monogatari": get_monogatari_image,
    "Monogatari": get_monogatari_image,
    "MONOGATARI": get_monogatari_image,
    "Gatari": get_monogatari_image,
    "loli": get_loli_image,
    "lolicon": get_loli_image,
    "lolis": get_loli_image,
    "Loli": get_loli_image,
    "Lolicon": get_loli_image,
    "Lolis": get_loli_image,
    "LOLI": get_loli_image,
    "LOLICON": get_loli_image,
    "LOLIS": get_loli_image,
}

RE_ANIME_STACK = re.compile(
    rf"/({'|'.join(ANIME_COMMAND_MAP.keys())})(?:(\d+)|(?:\s+(\d+)))?", re.IGNORECASE
)


def _resize_image_if_needed(image_bytes: bytes) -> bytes:
    MAX_DIMENSION_SUM = 10000
    MAX_ASPECT_RATIO = 20.0
    MAX_FILE_SIZE_BYTES = 9.5 * 1024 * 1024
    if not image_bytes:
        return image_bytes
    header = image_bytes[:12]
    is_media_format = (
        b"ftyp" in header
        or header.startswith(b"\x1a\x45\xdf\xa3")
        or header.startswith(b"GIF8")
    )
    if is_media_format:
        return image_bytes
    try:
        input_size = len(image_bytes)
        with PilImage.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            format_original = img.format
            if getattr(img, "is_animated", False):
                return image_bytes

            needs_resize_dims = (
                (width + height > MAX_DIMENSION_SUM)
                or (width / height > MAX_ASPECT_RATIO)
                or (height / width > MAX_ASPECT_RATIO)
            )
            if not needs_resize_dims and input_size <= MAX_FILE_SIZE_BYTES:
                if format_original == "PNG" and input_size > 5 * 1024 * 1024:
                    pass
                else:
                    output_buffer = io.BytesIO()
                    save_fmt = (
                        format_original
                        if format_original in ["PNG", "WEBP"]
                        else "JPEG"
                    )

                    save_img = img
                    if save_fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                        save_img = img.convert("RGB")
                    save_img.save(output_buffer, format=save_fmt, quality=95)
                    return output_buffer.getvalue()

            img = img.convert("RGB")
            new_width, new_height = width, height
            if width + height > MAX_DIMENSION_SUM:
                scale_factor = MAX_DIMENSION_SUM / (width + height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
            if new_width / new_height > MAX_ASPECT_RATIO:
                new_width = int(new_height * MAX_ASPECT_RATIO)
            elif new_height / new_width > MAX_ASPECT_RATIO:
                new_height = int(new_width * MAX_ASPECT_RATIO)
            if new_width != width or new_height != height:
                img = img.resize(
                    (max(1, new_width), max(1, new_height)), PilImage.LANCZOS
                )
            quality = 95
            output_buffer = io.BytesIO()
            img.save(output_buffer, format="JPEG", quality=quality)
            current_size = output_buffer.tell()
            while current_size > MAX_FILE_SIZE_BYTES and quality > 10:
                output_buffer.seek(0)
                output_buffer.truncate(0)
                if quality < 60:
                    img = img.resize(
                        (int(img.width * 0.85), int(img.height * 0.85)),
                        PilImage.LANCZOS,
                    )
                quality -= 10
                img.save(output_buffer, format="JPEG", quality=quality)
                current_size = output_buffer.tell()
            return output_buffer.getvalue()
    except Exception:
        return image_bytes


async def _download_image_with_proxy(
    url: str, timeout: int = 90, depth: int = 0
) -> tuple[bytes, int] | None:
    if depth > 3:
        return None
    import socket
    import ssl
    import aiohttp

    current_proxy = None
    try:
        from japanese_translator import get_dynamic_proxy_url

        current_proxy = get_dynamic_proxy_url()
    except ImportError:
        pass
    timeout_config = aiohttp.ClientTimeout(
        total=timeout, connect=30, sock_connect=30, sock_read=timeout
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=ssl_context)
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession(
                timeout=timeout_config,
                headers=headers,
                connector=connector,
                trust_env=False,
            ) as session:
                try:
                    async with session.get(
                        url, allow_redirects=True, proxy=current_proxy
                    ) as response:
                        if response.status == 200:
                            content_type = response.headers.get(
                                "Content-Type", ""
                            ).lower()
                            if (
                                "text/html" in content_type
                                or "application/json" in content_type
                            ):
                                return None
                            data = await response.read()
                            if (
                                data.strip().startswith(b"<")
                                and b"<html" in data[:200].lower()
                            ):
                                return None
                            if len(data) > 49.5 * 1024 * 1024:
                                return None
                            if len(data) > 0:
                                return data, len(data)
                except (aiohttp.ClientConnectorError, asyncio.TimeoutError, OSError):
                    if current_proxy:
                        async with session.get(
                            url, allow_redirects=True, proxy=None
                        ) as response:
                            if response.status == 200:
                                data = await response.read()
                                return data, len(data)
        except:
            continue
    return None


class BottleSendRequest(BaseModel):
    post_num: int
    text: str


class HardBanRequest(BaseModel):
    post_num: int
    scope: str = "current"


class HardWipeRequest(BaseModel):
    post_num: int


class LockdownRequest(BaseModel):
    enabled: bool


class OpModRequest(BaseModel):
    post_num: int
    action: str


class ReactionRequest(BaseModel):
    post_num: int
    emoji: str


class SpamWordRequest(BaseModel):
    board_id: str
    word: str


class NeuroToggleRequest(BaseModel):
    enabled: bool


class NeuroScannerConfigRequest(BaseModel):
    enabled: bool
    interval: int


class NeuroForceRequest(BaseModel):
    board_id: str
    mode: str
    stream: str = "ru"


class SystemAnnouncementRequest(BaseModel):
    text: str


class SystemSettingRequest(BaseModel):
    key: str
    value: str


class StreamChangeRequest(BaseModel):
    stream: str


class ReportPost(BaseModel):
    post_num: int
    reason: str
    category: str


class AdminAction(BaseModel):
    post_num: int


class PollVote(BaseModel):
    post_num: int
    option_index: int


class PostNumsRequest(BaseModel):
    post_nums: List[int]


class TokenAuth(BaseModel):
    token: str


class FavouriteThreads(BaseModel):
    thread_ids: List[int]


class ShadowBanRequest(BaseModel):
    target: str
    post_num: int
    duration: int
    scope: str = "current"


class LiftBanRequest(BaseModel):
    user_id: int
    board_id: str
    ban_type: str


class AdminEndlessRequest(BaseModel):
    thread_id: str
    endless: bool


class BoardBannerRequest(BaseModel):
    board_id: str
    image_url: str
    link_url: str


class AdminInspectRequest(BaseModel):
    post_num: int


class AdminPinRequest(BaseModel):
    thread_id: str
    pinned: bool


class AdminTrollRequest(BaseModel):
    ip: str
    mode: str = "gzip"  # gzip, html, xml, js, slow
    duration: int = 8640000  # По дефолту сутки


class AdminRestoreRequest(BaseModel):
    thread_id: str


class MoveThreadRequest(BaseModel):
    thread_id: str
    target_board: str


class ImportRequestModel(BaseModel):
    url: str = Field(..., max_length=500)
    board_id: str = Field(..., max_length=20)
    comment: str = Field(..., max_length=500)


class FeedbackRequestModel(BaseModel):
    category: str = Field(..., max_length=50)
    contact: Optional[str] = Field("", max_length=100)
    message: str = Field(..., max_length=3000)


SYSTEM_LOGS = deque(maxlen=100)
import asyncio
import logging

SITE_SPAM_RULES = {
    "text": {
        "max_repeats": 4,
        "window_sec": 15,
        "max_per_window": 7,
        "penalty_seconds": 300,
    },
    "files": {
        "max_repeats": 3,
        "window_sec": 60,
        "max_per_window": 12,
        "penalty_seconds": 600,
    },
}
BOARD_VERSIONS = defaultdict(lambda: time.time())
THREAD_VERSIONS = defaultdict(lambda: time.time())
site_spam_tracker = defaultdict(
    lambda: defaultdict(lambda: {"last_texts": deque(maxlen=5), "timestamps": []})
)
ROLE_HIERARCHY = {
    "user": 0,  # Обычный анон (постинг)
    "janitor": 1,  # Дворник (удаление постов, закрытие репортов)
    "mod": 2,  # Модератор (баны, теневые баны, закреп тредов)
    "admin": 3,  # Админ (вайп, смена ролей, настройки, полный доступ)
}


def check_perm(user: dict, required_role: str) -> bool:
    """
    Проверяет, достаточно ли прав у пользователя для действия.
    Возвращает True/False.
    """
    if not user:
        return False
    if user.get("id") in ADMIN_IDS:
        return True
    user_role = user.get("role", "user")
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    req_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= req_level


async def check_and_punish_site_spam(
    board_id: str, user_id: int, text: str, files: list, t
):
    clean_text = text.strip()
    if clean_text in {"🎲", "🎰", "🏀", "⚽", "🎯", "🎳"}:
        await apply_regular_mute(user_id, board_id, 60)
        log_system_event(
            f"🎲 AUTO-MUTE (Site): User {user_id} muted for 1 min (Casino spam) on /{board_id}/"
        )

        phrases = t("casino_phrases", ["No casino allowed."])
        if not isinstance(phrases, list):
            phrases = [phrases]
        phrase = random.choice(phrases)

        raise HTTPException(
            status_code=400, detail=t("casino_ban_message").format(phrase)
        )
    user_history = site_spam_tracker[board_id][user_id]
    now = time.time()

    # 1. Text Spam check
    text_violation = False
    if clean_text:
        window = SITE_SPAM_RULES["text"]["window_sec"]
        user_history["timestamps"] = [
            t_val
            for t_val in user_history.get("timestamps", [])
            if t_val > now - window
        ]
        user_history["timestamps"].append(now)
        user_history["last_texts"].append(clean_text)

        if len(user_history["timestamps"]) >= SITE_SPAM_RULES["text"]["max_per_window"]:
            text_violation = True
        elif len(user_history["last_texts"]) >= SITE_SPAM_RULES["text"]["max_repeats"]:
            if len(set(user_history["last_texts"])) == 1:
                text_violation = True

    if text_violation:
        user_history["timestamps"] = []
        user_history["last_texts"].clear()
        penalty = SITE_SPAM_RULES["text"]["penalty_seconds"]
        await apply_regular_mute(user_id, board_id, penalty)
        raise HTTPException(
            status_code=429,
            detail=f"🚫 Обнаружен спам! Вы получили мут на {penalty // 60} минут.",
        )

    # 2. Files/Images Spam check
    if files:
        if "last_file_hashes" not in user_history:
            from collections import deque

            user_history["last_file_hashes"] = deque(maxlen=10)
            user_history["file_timestamps"] = []

        file_hashes = []
        import hashlib

        for img in files:
            try:
                await img.seek(0)
                content = await img.read()
                await img.seek(0)
                if content:
                    h = hashlib.md5(content).hexdigest()
                    file_hashes.append(h)
            except Exception:
                pass

        if file_hashes:
            file_window = SITE_SPAM_RULES.get("files", {}).get("window_sec", 60)
            user_history["file_timestamps"] = [
                t_val
                for t_val in user_history["file_timestamps"]
                if t_val > now - file_window
            ]

            file_violation = False
            for h in file_hashes:
                user_history["file_timestamps"].append(now)
                user_history["last_file_hashes"].append(h)

            max_files = SITE_SPAM_RULES.get("files", {}).get("max_per_window", 12)
            max_repeats = SITE_SPAM_RULES.get("files", {}).get("max_repeats", 3)

            if len(user_history["file_timestamps"]) >= max_files:
                file_violation = True
            elif len(user_history["last_file_hashes"]) >= max_repeats:
                last_hashes = list(user_history["last_file_hashes"])[-max_repeats:]
                if len(set(last_hashes)) == 1:
                    file_violation = True

            if file_violation:
                user_history["file_timestamps"] = []
                user_history["last_file_hashes"].clear()
                penalty = SITE_SPAM_RULES.get("files", {}).get("penalty_seconds", 600)
                await apply_regular_mute(user_id, board_id, penalty)
                raise HTTPException(
                    status_code=429,
                    detail=f"🚫 Обнаружен спам картинками! Вы получили мут на {penalty // 60} минут.",
                )


async def captcha_cleanup_task():
    while True:
        await asyncio.sleep(600)
        try:
            now = time.time()
            expired = [k for k, v in CAPTCHA_SESSIONS.items() if v["expires"] < now]
            for k in expired:
                del CAPTCHA_SESSIONS[k]
            if expired:
                logger.info(f"🧹 [Captcha] Cleaned {len(expired)} expired sessions.")
        except Exception as e:
            logger.error(f"⚠️ Captcha cleanup error: {e}")


async def site_spam_cleanup_task():
    while True:
        await asyncio.sleep(3600)
        try:
            logger.info("🧹 [Site] Cleaning spam tracker memory...")
            now = time.time()
            for board_id in list(site_spam_tracker.keys()):
                board_data = site_spam_tracker[board_id]
                inactive_users = [
                    uid
                    for uid, hist in board_data.items()
                    if not hist["timestamps"] or (now - hist["timestamps"][-1] > 3600)
                ]
                for uid in inactive_users:
                    del board_data[uid]
                if not board_data:
                    del site_spam_tracker[board_id]
            logger.info("✅ [Site] Spam tracker cleaned.")
        except Exception as e:
            logger.error(f"⚠️ Error cleaning site spam tracker: {e}")


async def shadow_cleanup_task():
    while True:
        await asyncio.sleep(3600)
        try:
            if int(time.time()) % 21600 < 3700:
                logger.info("🧹 [Shadow] Cleaning old shadow posts...")
                await cleanup_shadow_posts_db(hours=24)
            if len(KNOWN_IPS) > 10000:
                KNOWN_IPS.clear()
            if len(BOT_VIOLATIONS) > 5000:
                logger.info(
                    f"🧹 [Firewall] Pruning memory... (Tracking {len(BOT_VIOLATIONS)} IPs)"
                )
                BOT_VIOLATIONS.clear()
                now = time.time()
                expired_bans = [ip for ip, exp in IP_BAN_LIST.items() if exp < now]
                for ip in expired_bans:
                    del IP_BAN_LIST[ip]
                logger.info("✅ [Firewall] Memory cleaned.")
        except Exception as e:
            logger.error(f"⚠️ Maintenance task error: {e}")


def get_user_id_from_session(request: Request) -> str:
    user = request.session.get("user")
    if user and user.get("id"):
        return str(user["id"])
    return get_real_ip(request)


async def notify_admins(bot: Bot, text: str):
    """
    Рассылает уведомления админам.
    Устойчива к блокировкам и лимитам (FloodWait).
    """
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            logger.warning(
                f"⏳ FloodWait {e.retry_after}s при отправке админу {admin_id}"
            )
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception:
                pass
        except TelegramForbiddenError:
            logger.warning(
                f"❌ Админ {admin_id} заблокировал бота! Сообщение не доставлено."
            )
        except Exception as e:
            logger.error(f"⚠️ Ошибка доставки админу {admin_id}: {e}")


limiter = Limiter(key_func=get_user_id_from_session)
signer = TimestampSigner(SECRET_KEY)


def generate_negative_id(token: str) -> int:
    hash_val = hashlib.sha256(token.encode()).hexdigest()
    val = int(hash_val[:8], 16)
    return -(val % 2147483647) - 1


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, set[WebSocket]] = defaultdict(set)
        self.ip_counts: Dict[str, int] = defaultdict(int)

    async def connect(
        self, websocket: WebSocket, board_id: str, mode: str, stream: str
    ):
        client_ip = websocket.client.host
        if websocket.headers.get("x-real-ip"):
            client_ip = websocket.headers.get("x-real-ip")
        elif websocket.headers.get("x-forwarded-for"):
            client_ip = websocket.headers.get("x-forwarded-for").split(",")[0].strip()

        self.ip_counts[client_ip] += 1

        if self.ip_counts[client_ip] > 20:
            self.ip_counts[client_ip] -= 1
            logger.warning(f"⛔ WS Limit Reached for {client_ip}")
            return

        try:
            await websocket.accept()
        except:
            self.ip_counts[client_ip] -= 1
            return

        logger.info(f"🔌 WS Connect: {client_ip} | Board: {board_id}")
        key = f"{board_id}/{mode}/{stream}"
        self.active_connections[key].add(websocket)

        if self.ip_counts[client_ip] == 1:
            v_logger.info(f"[LIVE] {client_ip} | Started session")

        websocket.state_client_ip = client_ip

    def disconnect(self, websocket: WebSocket, board_id: str, mode: str, stream: str):
        key = f"{board_id}/{mode}/{stream}"
        if key in self.active_connections:
            self.active_connections[key].discard(websocket)
            if not self.active_connections[key]:
                del self.active_connections[key]

        if hasattr(websocket, "state_client_ip"):
            ip = websocket.state_client_ip
            if self.ip_counts[ip] > 0:
                self.ip_counts[ip] -= 1
            if self.ip_counts[ip] == 0:
                v_logger.info(f"[EXIT] {ip}")
                del self.ip_counts[ip]

    async def broadcast_post_update(self, post_data: dict):
        enriched = _convert_and_enrich_posts([post_data])[0]

        message = orjson.dumps({"event_type": "update", "post": enriched}).decode(
            "utf-8"
        )

        board_id = post_data.get("board_id")
        targets = [
            f"{board_id}/threads/ru",
            f"{board_id}/threads/en",
            f"{board_id}/threads/jp",
            f"{board_id}/chat/ru",
            f"{board_id}/chat/en",
            f"{board_id}/chat/jp",
            "overboard/threads/ru",
            "overboard/threads/en",
            "overboard/threads/jp",
            "overboard/chat/ru",
            "overboard/chat/en",
            "overboard/chat/jp",
        ]

        tasks = [
            self._safe_send(conn, message, key)
            for key in targets
            if key in self.active_connections
            for conn in self.active_connections[key]
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_system_event(
        self, event_type: str, post_num: int, board_id: str
    ):
        message = orjson.dumps(
            {"event_type": event_type, "post_num": post_num, "board_id": board_id}
        ).decode("utf-8")

        targets = [
            f"{board_id}/threads/ru",
            f"{board_id}/threads/en",
            f"{board_id}/threads/jp",
            f"{board_id}/chat/ru",
            f"{board_id}/chat/en",
            f"{board_id}/chat/jp",
            "overboard/threads/ru",
            "overboard/threads/en",
            "overboard/threads/jp",
            "overboard/chat/ru",
            "overboard/chat/en",
            "overboard/chat/jp",
        ]

        tasks = []
        for key in targets:
            if key in self.active_connections:
                for conn in self.active_connections[key]:
                    tasks.append(self._safe_send(conn, message, key))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, connection: WebSocket, message: str, key: str):
        try:
            await asyncio.wait_for(connection.send_text(message), timeout=0.4)
        except Exception:
            try:
                if key in self.active_connections:
                    self.active_connections[key].discard(connection)
                    if not self.active_connections[key]:
                        del self.active_connections[key]
            except:
                pass

    async def broadcast_post(self, post_data: dict, board_id: str):
        stream = post_data.get("stream", "ru")
        is_thread = post_data.get("thread_id") is not None
        enriched_post = _convert_and_enrich_posts([post_data])[0]

        if "content" not in enriched_post or not isinstance(
            enriched_post["content"], dict
        ):
            enriched_post["content"] = {}

        if "post_num" in enriched_post:
            enriched_post["id"] = enriched_post.pop("post_num")
        pid = enriched_post.get("id")
        tid = enriched_post.get("thread_id")
        enriched_post["is_op_post"] = bool(pid and tid and pid == tid)
        message_bytes = orjson.dumps(enriched_post)
        message_str = message_bytes.decode("utf-8")
        if not message_str:
            return
        target_mode = "threads" if is_thread else "chat"
        key = f"{board_id}/{target_mode}/{stream}"
        overboard_key = f"overboard/{target_mode}/{stream}"
        targets = [key, overboard_key]
        for k in targets:
            if k in self.active_connections:
                connections = list(self.active_connections[k])
                if not connections:
                    continue
                chunk_size = 50
                connections_list = list(connections)
                for i in range(0, len(connections_list), chunk_size):
                    chunk = connections_list[i : i + chunk_size]
                    tasks = []
                    for connection in chunk:
                        tasks.append(self._safe_send(connection, message_str, k))
                    await asyncio.gather(*tasks)
                    await asyncio.sleep(0.01)
        if "admin_feed" in self.active_connections:
            admin_conns = list(self.active_connections["admin_feed"])
            admin_tasks = [
                self._safe_send(ac, message_str, "admin_feed") for ac in admin_conns
            ]
            if admin_tasks:
                await asyncio.gather(*admin_tasks, return_exceptions=True)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SPAM_WORDS_CACHE
    tasks = []

    def startup_mark(label: str, started_at: float | None = None) -> float:
        now = time.perf_counter()
        if started_at is None:
            print(f"[site-startup] {label}", flush=True)
        else:
            print(
                f"[site-startup] {label} ({(now - started_at) * 1000:.0f}ms)",
                flush=True,
            )
        return now

    startup_mark("lifespan begin")
    step_started = startup_mark("create_pool begin")
    await create_pool()
    startup_mark("create_pool done", step_started)
    step_started = startup_mark("initialize_database begin")
    await initialize_database()
    startup_mark("initialize_database done", step_started)
    step_started = startup_mark("sync_boards begin")
    await sync_boards_with_config(BOARD_CONFIG)
    startup_mark("sync_boards done", step_started)
    step_started = startup_mark("load approved boards begin")
    async with get_db_connection() as conn:
        async with conn.execute(
            "SELECT board_id, name, description FROM Boards WHERE is_approved = 1"
        ) as cursor:
            async for row in cursor:
                bid, bname, bdesc = row
                if bid not in BOARD_CONFIG:
                    BOARD_CONFIG[bid] = {"name": bname, "description": bdesc}
    startup_mark("load approved boards done", step_started)
    step_started = startup_mark("load board banners begin")
    async with get_db_connection() as conn:
        async with conn.execute("SELECT board_id, banner_data FROM Boards") as cursor:
            async for row in cursor:
                bid, bdata = row
                if bid in BOARD_CONFIG and bdata:
                    try:
                        BOARD_CONFIG[bid]["banner_data"] = json.loads(bdata)
                    except:
                        pass
    startup_mark("load board banners done", step_started)
    if not FILE_UPLOADER_BOT_TOKEN or not FILE_STORAGE_CHANNEL_ID:
        raise ValueError(
            "Missing FILE_UPLOADER_BOT_TOKEN or FILE_STORAGE_CHANNEL_ID in .env"
        )
    try:
        step_started = startup_mark("file uploader bot begin")
        file_uploader_bot = Bot(token=FILE_UPLOADER_BOT_TOKEN)
        app.state.file_uploader_bot = file_uploader_bot
        startup_mark("file uploader bot done", step_started)

        # Инициализируем пул ботов заранее (улучшение UX).
        # Это предотвратит задержку при обработке первого поста пользователем.
        if global_bot_pool:
            step_started = startup_mark("global bot pool init begin")
            logger.info("INFO:     Preloading Bot Pool...")
            global_bot_pool.init_pool()
            startup_mark("global bot pool init done", step_started)

    except Exception as e:
        logger.critical(f"🔥 BOT INIT FAILED: {e}. Uploads will fail!")
        app.state.file_uploader_bot = None
    step_started = startup_mark("background tasks begin")
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    app.state.broadcast_queue = asyncio.Queue(maxsize=1000)
    db_task = spawn_task(queue_listener(manager))
    ws_task = spawn_task(websocket_broadcaster(app.state.broadcast_queue, manager))
    spam_task = spawn_task(site_spam_cleanup_task())
    cache_cleanup_task = spawn_task(site_cache_cleanup_task())
    mtproto_task = spawn_task(mtproto_cleanup_task())
    shadow_task = spawn_task(shadow_cleanup_task())
    captcha_task = spawn_task(captcha_cleanup_task())
    tagging_task = spawn_task(tagging_loop())
    maintenance_task = None
    if SITE_DB_MAINTENANCE_ENABLED:
        maintenance_task = spawn_task(db_maintenance_task())
    else:
        logger.info(
            "INFO:     Site DB maintenance disabled; bot/database maintenance remains authoritative."
        )
    from site_tgach.hf_batcher import hf_batch_loop

    batcher_task = spawn_task(hf_batch_loop())
    from site_tgach.neuro_poster import NeuroManager

    neuro_manager = NeuroManager(app.state.file_uploader_bot)
    random_index_task = spawn_task(refresh_random_indexes())
    app.state.neuro_manager = neuro_manager
    NEURO_ENABLED = False

    async def neuro_loop():
        from site_tgach.neuro_poster import POSTING_INTERVALS

        await asyncio.sleep(30)
        while True:
            try:
                val = await get_system_setting("neuro_enabled")
                is_enabled = val == "true"
                if not is_enabled:
                    await asyncio.sleep(60)
                    continue
                min_wait = POSTING_INTERVALS.get("min", 120)
                max_wait = POSTING_INTERVALS.get("max", 300)
                wait_time = random.randint(min_wait, max_wait)
                await asyncio.sleep(wait_time)
                val_now = await get_system_setting("neuro_enabled")
                if val_now == "true":
                    await neuro_manager.run_cycle()
            except Exception as e:
                logger.error(f"Neuro loop crash: {e}")
                await asyncio.sleep(60)

    if app.state.file_uploader_bot:
        backup_task = spawn_task(backup_loop(app.state.file_uploader_bot))
    else:
        backup_task = None
    neuro_task = spawn_task(neuro_loop())
    mirror_task = spawn_task(process_mirror_queue())
    sim_task = spawn_task(process_import_queue(app.state.broadcast_queue))
    scanner_task = spawn_task(scanner_loop(app.state))
    tor_task = spawn_task(update_tor_nodes_task())
    startup_mark("background tasks done", step_started)
    try:
        tasks = [
            task
            for task in (
                db_task,
                ws_task,
                spam_task,
                cache_cleanup_task,
                shadow_task,
                maintenance_task,
                neuro_task,
                batcher_task,
                backup_task,
                mirror_task,
                captcha_task,
                tagging_task,
                sim_task,
                scanner_task,
                mtproto_task,
                random_index_task,
                tor_task,
            )
            if task is not None
        ]
    except UnboundLocalError:
        pass
    logger.info("INFO:     System started.")
    startup_mark("lifespan ready")
    try:
        yield
    finally:
        logger.info("INFO:     Shutting down...")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if global_bot_pool:
            await global_bot_pool.close_all()
        try:
            await app.state.file_uploader_bot.session.close()
        except Exception:
            pass
        shutdown_image_executors()
        await close_internal_file_bots()
        await close_all_mtproto_clients()
        if GLOBAL_HTTP_SESSION:
            await GLOBAL_HTTP_SESSION.close()
        if not GEO_IP_CLIENT.is_closed:
            await GEO_IP_CLIENT.aclose()
        if GEOIP_READER:
            try:
                await asyncio.to_thread(GEOIP_READER.close)
            except Exception:
                pass
        await close_pool()


app = FastAPI(
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url=None,
    redoc_url=None,
)
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import Response


@app.middleware("http")
async def country_cookie_middleware(request: Request, call_next):
    if request.url.path.startswith(("/static", "/files", "/ws", "/api")):
        return await call_next(request)

    response = await call_next(request)

    try:
        client_ip = get_real_ip(request)
        country = await get_country_by_ip(client_ip)
        response.set_cookie(
            key="user_country",
            value=country,
            max_age=3600,
            httponly=True,
            samesite="lax",
        )
    except Exception:
        pass

    return response


class BlockBadBots:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.blocked_agents = [
            "bytespider",
            "claudebot",
            "amazonbot",
            "semrushbot",
            "dotbot",
            "mj12bot",
            "ahrefsbot",
            "gptbot",
            "ccbot",
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        user_agent = headers.get(b"user-agent", b"").decode("latin-1").lower()
        if any(bot in user_agent for bot in self.blocked_agents):
            response = Response("Go away, bot.", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


app.add_middleware(BlockBadBots)


class LimitUploadSize:
    def __init__(self, app: ASGIApp, max_upload_size: int) -> None:
        self.app = app
        self.max_upload_size = max_upload_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = scope.get("headers", [])
        content_length = dict(content_length).get(b"content-length")
        if content_length is not None and int(content_length) > self.max_upload_size:
            response = Response(
                "File too large (Request Entity Too Large)", status_code=413
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


app.add_middleware(LimitUploadSize, max_upload_size=250 * 1024 * 1024)


@app.middleware("http")
async def custom_access_log_middleware(request: Request, call_next):
    IGNORED_PREFIXES = [
        "/api/server/pulse",
        "/api/updates/",
        "/api/captcha/status",
        "/api/global_announcement",
        "/api/bottle/count",
        "/static/img/mascot",
        "/static/",
        "/favicon.ico",
        "/logger/",
    ]

    path = request.url.path
    if any(path.startswith(prefix) for prefix in IGNORED_PREFIXES) or any(
        x in path for x in ["wp-", ".php", ".xml"]
    ):
        return await call_next(request)

    client_ip = get_real_ip(request)

    # 1. Фиксация нового посетителя (Вход)
    if client_ip not in KNOWN_IPS:
        KNOWN_IPS.add(client_ip)
        country = await get_country_by_ip(client_ip)
        v_logger.info(f"[ENTER] {client_ip} ({country})")

    # 2. Определение человекочитаемого действия
    action = f"{request.method} {path}"  # Дефолт

    if path == "/":
        action = "Main page"
    elif "/res/" in path:
        match = re.search(r"/([a-z0-9]+)/res/(\d+)", path)
        if match:
            action = f"Reading /{match.group(1)}/ #{match.group(2)}"
    elif path.endswith("/threads/"):
        board = path.split("/")[1]
        action = f"Browsing /{board}/"
    elif path.startswith("/overboard/"):
        action = "Overboard"
    elif path.startswith("/api/post/"):
        target = path.rsplit("/", 1)[-1]
        if request.method == "POST":
            action = f"POST /api/post/{target}"
        else:
            action = f"{request.method} post API /{target}/"

    v_logger.info(f"[DO] {client_ip} | {action}")

    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        if request.method == "POST" and path.startswith("/api/post/"):
            logger.exception(
                "site_post_unhandled_exception method=%s path=%s content_length=%s",
                request.method,
                path,
                request.headers.get("content-length", "-"),
            )
        raise
    if response.status_code == 403:
        logger.warning(
            f"🚫 403 FORBIDDEN: IP={client_ip} Path={request.url.path} UA={request.headers.get('user-agent')}"
        )
    process_time = (time.time() - start_time) * 1000
    if request.method == "POST" and path.startswith("/api/post/"):
        logger.info(
            "site_post_http method=%s path=%s status=%s duration_ms=%.0f content_length=%s",
            request.method,
            path,
            response.status_code,
            process_time,
            request.headers.get("content-length", "-"),
        )
    client_ip = get_real_ip(request)

    timestamp = datetime.now().strftime("%H:%M:%S")
    status_code = response.status_code
    if path.startswith("/files/") and status_code < 400:
        print(f"[{timestamp}] {client_ip:<13} file accepted ({process_time:.0f}ms)")
        return response
    status_color = "\033[32m"
    if status_code >= 500:
        status_color = "\033[31m"
    elif status_code >= 400:
        status_color = "\033[33m"
    elif status_code >= 300:
        status_color = "\033[36m"
    reset_color = "\033[0m"
    redirect_tag = ""
    if status_code in (307, 302, 301) and "location" in response.headers:
        loc = response.headers["location"]
        if "huggingface.co" in loc:
            redirect_tag = " \033[33m-> [HF]\033[0m"
        elif "catbox.moe" in loc:
            redirect_tag = " \033[35m-> [CB]\033[0m"
        elif "0x0.st" in loc:
            redirect_tag = " \033[36m-> [0x0]\033[0m"
        elif "api.telegram.org" in loc:
            redirect_tag = " \033[34m-> [TG]\033[0m"
        else:
            redirect_tag = " -> [OTHER]"

    print(
        f"[{timestamp}] {client_ip:<13} {request.method} {request.url.path} {status_color}{status_code}{reset_color}{redirect_tag} ({process_time:.0f}ms)"
    )
    return response


def clean_zalgo(text: str) -> str:
    """
    Удаляет чрезмерное количество комбинируемых символов (Zalgo),
    чтобы текст не ломал верстку.
    """
    if not text:
        return ""
    count = 0
    clean_chars = []
    for char in text:
        if unicodedata.category(char) == "Mn":
            count += 1
            if count > 4:
                continue
        else:
            count = 0
        clean_chars.append(char)
    return "".join(clean_chars)


REQUEST_FLOOD_TRACKER = defaultdict(list)
LOCAL_DIAGNOSTIC_IPS = {"127.0.0.1", "::1", "localhost"}
SITE_HEALTH_PATHS = {"/healthz", "/site_healthz"}


def is_bot_by_headers(request: Request) -> bool:
    """
    Анализирует заголовки, чтобы отличить живого анона от скрейпера.
    Возвращает True, если запрос похож на автоматизированный скрипт.
    """
    ua = request.headers.get("user-agent", "").lower()
    referer = request.headers.get("referer", "")
    accept_lang = request.headers.get("accept-language", "")
    path = request.url.path

    # 1. Список явных библиотек для автоматизации
    bot_uas = [
        "python-requests",
        "aiohttp",
        "httpx",
        "curl",
        "wget",
        "go-http-client",
        "libwww-perl",
        "python-urllib",
        "art-grabber",
    ]
    if any(bot in ua for bot in bot_uas):
        return True

    # 3. Самая эффективная проверка для API (рулетки и прочее)
    # Когда человек нажимает на кнопку на сайте, браузер ВСЕГДА шлет заголовок 'Referer'.
    # Боты-скрейперы обычно запрашивают /api/ напрямую без этого заголовка.
    # Мы не трогаем /static/, но проверяем /api/
    if path.startswith("/api/") and not referer:
        # Исключаем системные проверки или вебхуки, если они есть (в данном проекте их нет)
        return True

    # 4. Проверка на 'живого человека'
    # Браузер любого анона (даже с включенным VPN) передает язык (accept-language).
    # Простые скрипты его не передают.
    if not accept_lang and not path.startswith(("/static/", "/favicon.ico")):
        return True

    return False


@app.middleware("http")
async def ddos_guard_middleware(request: Request, call_next):
    # 1. Сначала получаем IP
    client_ip = get_real_ip(request)
    path = request.url.path
    request.state.client_ip = client_ip

    if path in SITE_HEALTH_PATHS or client_ip in LOCAL_DIAGNOSTIC_IPS:
        return await call_next(request)

    # 2. Потом проверяем черный список
    blacklist_raw = await get_setting_cached("ip_blacklist") or ""
    if client_ip in blacklist_raw.split(","):
        return Response("Banned by AI security", status_code=403)

    is_tor = client_ip in TOR_EXIT_NODES
    # 1. Проверка белого списка (кэшированная настройка из БД)
    whitelist_raw = await get_setting_cached("ip_whitelist") or ""
    if client_ip in whitelist_raw.split(","):
        return await call_next(request)

    # 2. Ручной троллинг (если ты добавил IP в список через админку)
    if client_ip in IP_TROLL_CONFIG:
        cfg = IP_TROLL_CONFIG[client_ip]
        if cfg["expires"] > time.time():
            # ПРОВЕРКА ЛИМИТА: Если ловушки полные, просто блокируем
            if ACTIVE_TROLL_CONNS >= MAX_TROLL_CONNS:
                return Response("Too many requests", status_code=429)

            m = cfg["mode"]
            if m == "gzip":
                return StreamingResponse(
                    managed_troll_generator(gzip_bomb_generator()),
                    media_type="application/x-gzip",
                    headers={"Content-Encoding": "gzip"},
                )
            if m == "html":
                return StreamingResponse(
                    managed_troll_generator(html_depth_charge_generator()),
                    media_type="text/html",
                )
            if m == "xml":
                return StreamingResponse(
                    managed_troll_generator(xml_tarpit_generator()),
                    media_type="application/xml",
                )
            if m == "js":
                return StreamingResponse(
                    managed_troll_generator(js_infinite_stream_generator()),
                    media_type="application/javascript",
                )
            if m == "slow":
                return StreamingResponse(
                    managed_troll_generator(slow_death_generator()),
                    media_type="text/plain",
                )
        else:
            del IP_TROLL_CONFIG[client_ip]

    # 3. Проверка существующего бана в памяти (IP_BAN_LIST)
    if client_ip in IP_BAN_LIST:
        if IP_BAN_LIST[client_ip] > time.time():
            if ACTIVE_TROLL_CONNS >= MAX_TROLL_CONNS:
                return Response("Banned", status_code=403)
            return StreamingResponse(
                managed_troll_generator(slow_death_generator()),
                media_type="text/plain",
                status_code=200,
            )
        else:
            del IP_BAN_LIST[client_ip]

    # 4. Умная фильтрация ботов и флуда
    # Не проверяем флуд для статических файлов, чтобы не банить анонов за загрузку стилей/картинок
    if not path.startswith(("/static/", "/files/", "/favicon.ico")):
        now = time.time()

        # Разделяем логику лимитов: для ботов — жестко, для людей — мягко.
        is_suspicious = is_bot_by_headers(request)

        flood_key = f"{client_ip}|{request.method}|{path}"

        # Авто-очистка трекера при переполнении (защита RAM)
        if len(REQUEST_FLOOD_TRACKER) > 10000:
            REQUEST_FLOOD_TRACKER.clear()

        history = REQUEST_FLOOD_TRACKER[flood_key]
        REQUEST_FLOOD_TRACKER[flood_key] = [t for t in history if now - t < 5]
        REQUEST_FLOOD_TRACKER[flood_key].append(now)

        # ЛОГИКА НАКАЗАНИЯ:
        # Если это выявленный БОТ (по заголовкам) -> лимит 3 запроса за 5 секунд.
        # Если это АНОН (нормальные заголовки) -> лимит 15 запросов за 5 секунд.

        limit_count = 3 if is_suspicious else 30

        if len(REQUEST_FLOOD_TRACKER[flood_key]) > limit_count:
            # Наказываем: Бан на 12 часов + Gzip-бомба
            IP_BAN_LIST[client_ip] = now + 43200

            reason = "Header pattern match" if is_suspicious else "Flood detected"
            log_system_event(f"🔨 AUTO-BAN: {client_ip} ({reason} on {path})")

            del REQUEST_FLOOD_TRACKER[flood_key]

            # Скармливаем боту Gzip-бомбу (10МБ нулей, сжатых до 10КБ).
            # При распаковке скрипты на Python/JS часто вылетают по памяти.
            filename = f"error_log_{secrets.token_hex(4)}.gz"
            if ACTIVE_TROLL_CONNS >= MAX_TROLL_CONNS:
                return Response("Flood detected", status_code=429)
            return StreamingResponse(
                managed_troll_generator(gzip_bomb_generator()),
                media_type="application/x-gzip",
                headers={
                    "Content-Encoding": "gzip",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

    # 5. Проверка через внешнюю функцию безопасности (check_ddos)
    if check_ddos(client_ip):
        logger.warning(f"⛔ DDOS BLACKLISTED: {client_ip}")
        return StreamingResponse(slow_death_generator(), media_type="text/plain")

    # Если всё хорошо — пропускаем запрос дальше
    response = await call_next(request)
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://www.youtube.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https: blob:; "
        "media-src 'self' https: blob:; "
        "connect-src 'self' https: wss:; "
        "frame-src 'self' https://www.youtube.com;"
    )
    return response


app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
site_root = os.path.dirname(os.path.abspath(__file__))


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        clean_path = path.split("?")[0]
        return await super().get_response(clean_path, scope)

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000"
        return resp


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/favicon.ico", status_code=301)


@app.get("/{path:path}/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon_proxy(path: str = ""):
    return RedirectResponse(url="/static/icons/icon-192.png", status_code=301)


class AdminDeleteAfterRequest(BaseModel):
    thread_id: str
    post_num: int


class ToggleBlurRequest(BaseModel):
    post_num: int


app.mount(
    "/static",
    CachedStaticFiles(directory=os.path.join(site_root, "static")),
    name="static",
)
templates = Jinja2Templates(directory=os.path.join(site_root, "templates"))


@app.get("/robots.txt", response_class=Response)
async def robots_txt(request: Request):
    base_url = str(request.base_url).rstrip("/")
    content = rf"""#
#  _______  ___    _   ___ _  _ 
# |_   _| \/  _\  /_\ / __| || |
#   | | | |/ _ \ / _ \ (__| __ |
#   |_| |_/_/ \_/_/ \_\___|_||_|
#
#  HUMANS ALLOWED. ROBOTS CONTROLLED.
#

# --- GLOBAL RULES ---
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Disallow: /auth/
Disallow: /login
Disallow: /my/
Disallow: /favourites/
Disallow: /history/
Disallow: /search
Disallow: /tv/random
Disallow: /img/random
Disallow: /*?*

# --- YANDEX ---
User-agent: Yandex
Allow: /
Disallow: /admin/
Disallow: /api/
Disallow: /search
Clean-param: sort /
Clean-param: boards /
Crawl-delay: 5

# --- GOOGLE ---
User-agent: Googlebot
Allow: /
Disallow: /*?sort=
Disallow: /*?boards=
Crawl-delay: 5

# --- OTHER GOOD BOTS ---
User-agent: Bingbot
Allow: /
User-agent: DuckDuckBot
Allow: /
User-agent: Applebot
Allow: /

# --- BAD BOTS ---
User-agent: GPTBot
Disallow: /
User-agent: ChatGPT-User
Disallow: /
User-agent: CCBot
Disallow: /
User-agent: anthropic-ai
Disallow: /
User-agent: Claude-Web
Disallow: /
User-agent: Google-Extended
Disallow: /
User-agent: FacebookBot
Disallow: /
User-agent: Bytespider
Disallow: /
User-agent: Amazonbot
Disallow: /
User-agent: MJ12bot
Disallow: /
User-agent: AhrefsBot
Disallow: /
User-agent: SemrushBot
Disallow: /
User-agent: DotBot
Disallow: /

Sitemap: {base_url}/sitemap.xml
Host: {request.url.hostname}
"""
    return Response(content=content, media_type="text/plain")


@app.get("/healthz", include_in_schema=False)
@app.get("/site_healthz", include_in_schema=False)
async def site_healthz():
    process_data = {"pid": os.getpid()}
    if psutil:
        try:
            proc = psutil.Process(os.getpid())
            mem = proc.memory_info()
            process_data.update(
                {
                    "rss_mb": round(getattr(mem, "rss", 0) / 1024 / 1024, 2),
                    "vms_mb": round(getattr(mem, "vms", 0) / 1024 / 1024, 2),
                    "threads": proc.num_threads(),
                }
            )
        except Exception as exc:
            process_data["error"] = str(exc)
    return JSONResponse(
        {
            "status": "ok",
            "pid": os.getpid(),
            "ts": round(time.time(), 3),
            "process": process_data,
            "runtime": {
                "active_connections": sum(
                    len(s) for s in manager.active_connections.values()
                ),
                "connection_keys": len(manager.active_connections),
                "request_flood_tracker": len(REQUEST_FLOOD_TRACKER),
                "ip_bans": len(IP_BAN_LIST),
                "known_ips": len(KNOWN_IPS),
            },
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/sitemap.xml", response_class=Response)
@cache(expire=3600)
async def sitemap_xml(request: Request):
    base_url = str(request.base_url).rstrip("/")
    # Статичные страницы
    static_pages = [
        "",
        "/rules/",
        "/about/",
        "/faq/",
        "/archive/threads/",
        "/archive/chat/",
        "/useful/",
        "/tags/",
    ]

    now_date = datetime.now().strftime("%Y-%m-%d")
    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # 1. Добавляем статику
    for page in static_pages:
        xml_content.append(
            f"  <url><loc>{base_url}{page}</loc><lastmod>{now_date}</lastmod><changefreq>daily</changefreq></url>"
        )

    # 2. Добавляем индексы досок
    for board_id in BOARD_CONFIG:
        xml_content.append(
            f"  <url><loc>{base_url}/{board_id}/</loc><lastmod>{now_date}</lastmod><changefreq>always</changefreq></url>"
        )
        xml_content.append(
            f"  <url><loc>{base_url}/{board_id}/catalog/</loc><lastmod>{now_date}</lastmod><changefreq>hourly</changefreq></url>"
        )

    # 3. Добавляем живые треды (последние 15 000)
    db = await get_pool()
    try:
        # Берем треды, сортируя по последнему ответу
        query = "SELECT board_id, thread_id, last_updated_at FROM Threads ORDER BY last_updated_at DESC LIMIT 15000"
        async with db.execute(query) as cursor:
            async for row in cursor:
                bid, tid, ts = row
                # Превращаем timestamp в 2026-01-26
                mod_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                xml_content.append(
                    f"  <url><loc>{base_url}/{bid}/res/{tid}.html</loc><lastmod>{mod_date}</lastmod><changefreq>hourly</changefreq></url>"
                )
    except Exception as e:
        logger.error(f"Sitemap threads error: {e}")

    # 4. Добавляем популярные теги (для SEO трафика по запросам картинок)
    try:
        popular_tags = await get_recent_tags_summary(limit_files=5000, top_n=500)
        for tag_name, _ in popular_tags:
            safe_tag = tag_name.replace(" ", "-")
            xml_content.append(
                f"  <url><loc>{base_url}/tags/{safe_tag}</loc><lastmod>{now_date}</lastmod><changefreq>weekly</changefreq></url>"
            )
    except Exception as e:
        logger.error(f"Sitemap tags error: {e}")

    # 5. Добавляем архив газеты (последние 90 дней)
    from datetime import timedelta

    for d_offset in range(90):
        d = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        xml_content.append(
            f"  <url><loc>{base_url}/newspaper/{d}</loc><lastmod>{d}</lastmod><changefreq>daily</changefreq></url>"
        )

    xml_content.append("</urlset>")
    return Response(content="\n".join(xml_content), media_type="application/xml")


@app.get("/ads.txt", include_in_schema=False)
async def ads_txt():
    return Response(content="# No ads here. Go away.", media_type="text/plain")


@app.middleware("http")
async def global_data_middleware(request: Request, call_next):
    if not request.url.path.startswith(("/static", "/ws", "/api")):
        try:
            announcement = await get_setting_cached("global_announcement")
            request.state.global_announcement = announcement
        except:
            request.state.global_announcement = ""
        try:
            lock = await get_setting_cached("lockdown_enabled")
            request.state.is_lockdown = lock == "true"
        except:
            request.state.is_lockdown = False
        user = request.session.get("user")
        if user:
            request.state.user_hash = get_user_hash(user["id"])
        else:
            guest_id = getattr(request.state, "guest_id", 0)
            if not guest_id:
                raw_token = request.cookies.get("guest_token")
                if raw_token:
                    try:
                        token_uns = signer.unsign(raw_token, max_age=31536000).decode()
                        guest_id = generate_negative_id(token_uns)
                    except:
                        pass
            request.state.user_hash = get_user_hash(guest_id) if guest_id else ""
    return await call_next(request)


@app.get("/.env", include_in_schema=False)
@app.get("/wp-login.php", include_in_schema=False)
@app.get("/admin/phpmyadmin", include_in_schema=False)
@app.get("/autodiscover/autodiscover.json", include_in_schema=False)
@app.get("/owa/auth/logon.aspx", include_in_schema=False)
async def bot_trap(request: Request):
    """Ловушка для мамкиных хакеров."""
    ip = get_real_ip(request)
    IP_BAN_LIST[ip] = time.time() + 86400
    logger.warning(f"🪤 BOT TRAPPED: {ip} tried to access sensitive paths. Banned.")
    return Response("Nice try, script kiddie.", status_code=418)


@app.middleware("http")
async def guest_identification_middleware(request: Request, call_next):
    if request.url.path.startswith("/ws/") or request.url.path.startswith("/static"):
        return await call_next(request)
    raw_token = request.cookies.get("guest_token")
    token = None
    is_new = False
    if raw_token:
        try:
            token = signer.unsign(raw_token, max_age=31536000).decode()
        except BadSignature:
            token = None
    if not token:
        token = f"{get_real_ip(request)}|{request.headers.get('User-Agent', '')}|{uuid.uuid4().hex}"
        is_new = True
    request.state.guest_id = generate_negative_id(token)
    request.state.guest_token = token
    response = await call_next(request)
    if is_new:
        signed_token = signer.sign(token).decode()
        response.set_cookie(
            key="guest_token",
            value=signed_token,
            max_age=31536000,
            httponly=True,
            samesite="lax",
        )
    return response


@app.middleware("http")
async def access_control_middleware(request: Request, call_next):
    if request.url.path.startswith("/ws/"):
        return await call_next(request)
    allowed_prefixes = ("/login", "/auth/token", "/static", "/favicon.ico")
    if request.url.path.startswith(allowed_prefixes):
        return await call_next(request)
    user = request.session.get("user")
    if SITE_ACCESS_MODE == "PRIVATE" and not user:
        return RedirectResponse(url="/login", status_code=303)
    return await call_next(request)


@app.middleware("http")
async def language_middleware(request: Request, call_next):
    try:
        host = request.headers.get("host", "").lower()

        # Жесткая привязка домена к языку/потоку
        forced_stream = None

        if "tgchan.top" in host:
            domain_lang = "en"
            site_name = "TGCHAN"
            forced_stream = "en"
        elif "tgach.top" in host:
            domain_lang = "ru"
            site_name = "ТГАЧ"
            forced_stream = "ru"
        # Сохраняем старую логику для других доменов/localhost
        elif "tgchan.jp" in host:
            domain_lang = "jp"
            site_name = "TGCHAN (JP)"
        else:
            domain_lang = "ru"
            site_name = "ТГАЧ"

        # Если домен жестко задает поток - используем его, иначе смотрим куки
        if forced_stream:
            lang = forced_stream
            stream = forced_stream
            # Форсируем stream в запросе, чтобы БД-фильтры сработали автоматически
            request.state.stream = forced_stream
        else:
            user_lang_cookie = request.cookies.get("stream")
            lang = (
                user_lang_cookie
                if user_lang_cookie in ["ru", "en", "jp"]
                else domain_lang
            )
            if ENABLE_MULTILANG:
                stream = lang
            else:
                stream = "ru"

        request.state.lang = lang
        request.state.site_name = site_name
        request.state.t = get_t(lang)
        request.state.stream = stream

        protocol = (
            "https"
            if request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
            else "http"
        )
        request.state.canonical_url = f"{protocol}://{host}{request.url.path}"

        request.state.host_ru = "tgach.top"
        request.state.host_en = "tgchan.top"

    except Exception:
        request.state.lang = "ru"
        request.state.t = get_t("ru")
        request.state.stream = "ru"
        request.state.site_name = "ТГАЧ"
    if request.url.path.startswith("/ws/") or request.url.path.startswith("/static/"):
        try:
            return await call_next(request)
        except RuntimeError as e:
            if str(e) == "No response returned.":
                return Response("OK", status_code=200)
            raise e
    try:
        response = await call_next(request)
        return response
    except RuntimeError as e:
        if str(e) == "No response returned.":
            return Response("Request processing error", status_code=500)
        raise e


async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    msg = "Анон, чет хуйню ты написал, подумай секунд 10 и попробуй еще раз."
    return ORJSONResponse(status_code=429, content={"detail": msg})


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
IS_PRODUCTION = os.getenv("SITE_URL", "").startswith("https")
app.add_middleware(
    SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=IS_PRODUCTION
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    path = request.url.path.lower()
    client_ip = get_real_ip(request)

    # 1. БЕЛЫЙ СПИСОК (Файлы и треды) - для предотвращения ложных срабатываний
    is_safe_path = (
        path.endswith(
            (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".gif",
                ".mp4",
                ".webm",
                ".mov",
                ".mkv",
                ".css",
                ".js",
                ".map",
                ".ico",
                ".svg",
                ".woff",
                ".woff2",
                ".ttf",
                ".json",
                ".html",
            )
        )
        or "/res/" in path
        or "/img/" in path
        or "/files/" in path
        or "/static/" in path
    )

    if is_safe_path:
        return Response(status_code=404)

    # 2. ПРОВЕРКА НА БОТА-СКАНЕРА (объединенный и улучшенный список)
    troll_patterns = [
        # System & Configs
        "/.env",
        "/.git",
        "/.ssh",
        "/.bash",
        "/.profile",
        "/.history",
        "/.aws",
        "/.rhosts",
        "/.sh_history",
        "/.wget",
        "/.htpasswd",
        "/.htaccess",
        "/.ds_store",
        "/.bak",
        "/.old",
        "/.save",
        "/.log",
        "/.txt",
        "/.conf",
        "/.sql",
        "/goform",
        "/hello.world",
        "/mcp",
        "/sse",
        # CMS & Frameworks
        "/wp-",
        "/wp/",
        "/xmlrpc",
        "/wlwmanifest",
        "/bitrix",
        "/joomla",
        "/drupal",
        "/laravel",
        "/symfony",
        "/storage/logs",
        "/vendor",
        "/composer",
        "/ajax",
        # Admin Panels & DBs
        "/admin",
        "/phpmyadmin",
        "/setup",
        "/config",
        "/backup",
        "/dump",
        "/db.sql",
        "/console",
        "/shell",
        "/root",
        "/eval",
        "/invoker",
        "/actuator",
        "/api/v1",
        "/dashboard",
        "/cpanel",
        "/whm",
        "/sql",
        "/install",
        "/+CSCOL+/",
        "/+CSCOL+",
        "/+CSCOE+/",
        "/+CSCOE+",
        # Scanners
        "/autodiscover",
        "/owa",
        "/exchange",
        "/ecp",
        "/_catalogs",
        "/_vti",
        "/hnap1",
        "/nmap",
        "/evox",
        "/sdk",
        "/phpunit",
        "/cgi-bin",
        "/~",
        "/_",
        "/1.bak",
        "/0.bak",
        "/a.bak",
        "/12.bak",
        "/config.json",
        "/config.php",
        "/onfig.js",
    ]

    is_bot = False

    if path.startswith(("/.", "/_", "/~", "/api/v", "/wp-")):
        is_bot = True
    elif any(p in path for p in troll_patterns):
        is_bot = True
    elif path.endswith(
        (
            ".php",
            ".asp",
            ".aspx",
            ".jsp",
            ".cgi",
            ".sh",
            ".sql",
            ".bak",
            ".old",
            ".save",
            ".log",
            ".rar",
            ".zip",
            ".7z",
            ".env",
            ".ini",
        )
    ):
        is_bot = True

    if is_bot:
        BOT_VIOLATIONS[client_ip] += 1

        # АВТО-ЗАХВАТ: Регистрация в реестре троллинга на 24 часа
        troll_mode = "gzip" if (".env" in path or "config" in path) else "slow"
        IP_TROLL_CONFIG[client_ip] = {
            "mode": troll_mode,
            "expires": time.time() + 86400,
        }

        log_system_event(
            f"🪤 AUTO-TRAP: {client_ip} triggered bot-filter on {path}. Penalty: {troll_mode.upper()} for 24h"
        )
        return await honey_pot_troll(request)

    return templates.TemplateResponse(
        request=request,
        name="error.jinja2",
        context={
            "request": request,
            "status_code": 404,
            "detail": "Страница не найдена",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    if request.method == "POST" and request.url.path.startswith("/api/post/"):
        logger.exception(
            "site_post_500 method=%s path=%s content_length=%s",
            request.method,
            request.url.path,
            request.headers.get("content-length", "-"),
            exc_info=exc,
        )
    return templates.TemplateResponse(
        request=request,
        name="error.jinja2",
        context={
            "request": request,
            "status_code": 500,
            "detail": "Внутренняя ошибка сервера",
        },
        status_code=500,
    )


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/post/"):
        return JSONResponse(
            {"Status": "Error", "Error": exc.detail, "detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )
    return templates.TemplateResponse(
        request=request,
        name="error.jinja2",
        context={
            "request": request,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    if request.url.path.startswith("/api/post/"):
        logger.warning(
            "site_post_validation_failed method=%s path=%s errors=%s",
            request.method,
            request.url.path,
            exc.errors(),
        )
    return await request_validation_exception_handler(request, exc)


async def get_current_user_or_guest(request: Request) -> dict:
    user = request.session.get("user")
    if user:
        user["is_guest"] = False
        return user
    if SITE_ACCESS_MODE == "PRIVATE":
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    guest_id = getattr(request.state, "guest_id", 0)
    if guest_id == 0:
        guest_id = generate_negative_id(get_real_ip(request))
    return {"id": guest_id, "is_admin": False, "is_guest": True}


async def get_optional_user(request: Request) -> Optional[dict]:
    return request.session.get("user")


async def get_required_user(user: Optional[dict] = Depends(get_optional_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Authorization required")
    return user


async def mtproto_cleanup_task():
    while True:
        await asyncio.sleep(600)  # Раз в 10 минут
        try:
            await _cleanup_idle_clients()
        except Exception as e:
            logger.error(f"MTProto cleanup error: {e}")


async def check_post_cooldown(request: Request, user: dict):
    is_guest = user.get("is_guest", False)
    user_id = user["id"]
    limit_seconds = 25 if is_guest else 5
    key = f"cooldown_{'guest' if is_guest else 'user'}_{user_id}"
    backend = FastAPICache.get_backend()
    last_post_time = await backend.get(key)
    if last_post_time:
        try:
            elapsed = time.time() - float(last_post_time)
            if elapsed < limit_seconds:
                raise HTTPException(
                    status_code=429,
                    detail=f"Подожди {int(limit_seconds - elapsed) + 1} сек.",
                )
        except (ValueError, TypeError):
            pass
    await backend.set(key, str(time.time()), expire=limit_seconds)


def to_makaba_post(post_data: dict, board_id: str) -> dict:
    files_makaba = []
    content = post_data.get("content", {})
    if content and content.get("files"):
        for f in content["files"]:
            files_makaba.append(
                {
                    "displayname": f.get("filename", "file.ext"),
                    "fullname": f.get("filename", "file.ext"),
                    "height": 0,
                    "width": 0,
                    "md5": "dummy",
                    "name": f.get("filename", "file.ext"),
                    "nsfw": 0,
                    "path": f.get("original_url", ""),
                    "size": 0,
                    "thumbnail": f.get("thumbnail_url", ""),
                    "tn_height": 0,
                    "tn_width": 0,
                    "type": 1 if f.get("type") in ["image", "photo"] else 6,
                }
            )
    comment = content.get("text", "")
    dt = datetime.fromtimestamp(post_data["timestamp"])
    date_str = dt.strftime("%d/%m/%y %a %H:%M:%S")
    return {
        "num": int(post_data["id"]),
        "parent": int(post_data.get("thread_id", 0) or 0),
        "date": date_str,
        "lasthit": int(post_data["timestamp"]),
        "comment": comment,
        "files": files_makaba,
        "name": "Аноним",
        "email": "sage" if post_data.get("sage") else "",
        "op": 1 if post_data.get("is_op_post") else 0,
        "trip": "",
        "banned": 0,
        "closed": 1 if post_data.get("is_archived") else 0,
        "sticky": 1 if post_data.get("is_pinned") else 0,
        "endless": 1 if post_data.get("is_endless") else 0,
    }


def log_system_event(message: str):
    spawn_task(log_global_event("site", message))
    timestamp = datetime.now().strftime("%H:%M:%S")
    SYSTEM_LOGS.appendleft(f"[{timestamp}] {message}")


def format_post_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    # --- СУПЕР-ЗАЩИТА ОТ XSS (искажение ключевых слов) ---
    # script -> sclipt (i -> l)
    text = re.sub(r"(s)(c)(r)(i)(p)(t)", r"\1\2\3l\5\6", text, flags=re.IGNORECASE)
    # iframe -> lframe (i -> l)
    text = re.sub(r"(i)(f)(r)(a)(m)(e)", r"l\2\3\4\5\6", text, flags=re.IGNORECASE)
    # expression -> explession (для CSS) (r -> l чтобы сломать слово)
    text = re.sub(
        r"(e)(x)(p)(r)(e)(s)(s)(i)(o)(n)",
        r"\1\2\3l\5\6\7\8\9\10",
        text,
        flags=re.IGNORECASE,
    )
    # style -> sty1e (l -> 1)
    text = (
        re.sub(r"(s)(t)(y)(l)(e)", r"\1\2\3\4e", text, flags=re.IGNORECASE)
        .replace("style", "sty1e")
        .replace("STYLE", "STY1E")
    )
    # События (onload, onerror, onclick...) -> 0nload...
    text = re.sub(
        r"\bon(load|error|click|mouse|key|focus|blur|change|submit)",
        r"0n\1",
        text,
        flags=re.IGNORECASE,
    )
    # javascript: -> javasclipt: (уже покрыто заменой script, но на всякий случай)

    # --- ЭКРАНИРОВАНИЕ HTML ---
    # Превращает < > " ' & в безопасные сущности
    text = html.escape(text, quote=True)

    # --- ФОРМАТИРОВАНИЕ ---
    text = re.sub(r"&lt;br\s*/?&gt;", "\n", text, flags=re.IGNORECASE)

    processed_text = URL_PATTERN.sub(
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', text
    )

    lines = []
    for line in processed_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("&gt;") and not stripped.startswith("&gt;&gt;"):
            lines.append(f'<span class="greentext">{line}</span>')
        elif stripped.startswith(">"):
            lines.append(f'<span class="greentext">{line}</span>')
        else:
            lines.append(line)
    processed_text = "<br>".join(lines)

    processed_text = re.sub(
        r"&gt;&gt;/([a-z0-9]+)/(\d+)",
        r'<a href="/\1/res/0#post-\2" class="post-link cross-board-link" data-board-id="\1" data-post-num="\2">&gt;&gt;/\1/\2</a>',
        processed_text,
    )

    processed_text = re.sub(
        r"&gt;&gt;(\d+)",
        r'<a href="#post-\1" class="post-link" data-post-num="\1">&gt;&gt;\1</a>',
        processed_text,
    )

    processed_text = re.sub(
        r"\[b\](.*?)\[/b\]", r"<b>\1</b>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[i\](.*?)\[/i\]", r"<i>\1</i>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[h1\](.*?)\[/h1\]",
        r'<h3 class="post-heading">\1</h3>',
        processed_text,
        flags=re.DOTALL,
    )

    def btn_replacer(match):
        url = match.group(1)
        safe_url = html.escape(url, quote=True)
        text = match.group(2)
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-small post-btn">{text}</a>'

    processed_text = re.sub(
        r"\[btn=(https?://[^\]]+)\](.*?)\[/btn\]",
        btn_replacer,
        processed_text,
        flags=re.DOTALL,
    )

    def size_replacer(match):
        try:
            s = int(match.group(1))
            s = max(10, min(30, s))
            return f'<span style="font-size: {s}px;">{match.group(2)}</span>'
        except:
            return match.group(2)

    processed_text = re.sub(
        r"\[size=(\d+)\](.*?)\[/size\]", size_replacer, processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[s\](.*?)\[/s\]", r"<s>\1</s>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[u\](.*?)\[/u\]", r"<u>\1</u>", processed_text, flags=re.DOTALL
    )
    processed_text = re.sub(
        r"\[code\](.*?)\[/code\]", r"<code>\1</code>", processed_text, flags=re.DOTALL
    )

    processed_text = re.sub(
        r"\[shake\](.*?)\[/shake\]",
        r'<span class="effect-shake">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )
    processed_text = re.sub(
        r"\[rainbow\](.*?)\[/rainbow\]",
        r'<span class="effect-rainbow">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )
    processed_text = re.sub(
        r"\[blur\](.*?)\[/blur\]",
        r'<span class="effect-blur">\1</span>',
        processed_text,
        flags=re.DOTALL,
    )

    def _glitch_replacer(match):
        content = match.group(1)
        return f'<span class="effect-glitch" data-text="{content}">{content}</span>'

    processed_text = re.sub(
        r"\[glitch\](.*?)\[/glitch\]", _glitch_replacer, processed_text, flags=re.DOTALL
    )
    processed_text = SPOILER_PATTERN.sub(
        r'<span class="spoiler">\1</span>', processed_text
    )

    return processed_text


def sanitize_html(text: str) -> str:
    if not text:
        return ""
    # quote=False оставляет кавычки как есть (читаемее), но убивает теги
    return html.escape(text, quote=False)


def optimize_thread_context(op_post: dict, replies: list, max_posts: int = 40) -> str:
    """
    Превращает тред в компактную строку для нейронки.
    Экономит токены: убирает HTML, обрезает длинные тексты, склеивает через разделитель.
    """

    def clean(text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"http\S+", "[link]", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:200]

    buffer = []
    op_text = op_post.get("content", {}).get("text", "")
    if op_text:
        buffer.append(f"OP: {clean(op_text)[:300]}")
    target_replies = replies[-max_posts:]
    for r in target_replies:
        txt = r.get("content", {}).get("text", "")
        if txt:
            cleaned = clean(txt)
            if cleaned:
                buffer.append(cleaned)
    return " | ".join(buffer)


def pluralize_russian(count, one, few, many):
    try:
        n = abs(int(count))
        if n % 10 == 1 and n % 100 != 11:
            return one
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return few
        else:
            return many
    except (ValueError, TypeError):
        return many


def format_bayan_label(count: int, lang: str = "ru") -> str:

    if not count or count <= 1:
        return ""
    tr = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    key = "bayan_low"
    if count > 10:
        key = "bayan_high"
    elif count > 3:
        key = "bayan_mid"
    phrases = tr.get(key, ["Баян"])
    return f"♻️ {random.choice(phrases)} ({count})"


def format_iso_time(ts: float) -> str:

    try:
        return datetime.fromtimestamp(ts).isoformat()
    except:
        return ""


def format_timestamp(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S")
    except (ValueError, TypeError):
        return ""


def format_poll_for_html(poll_data: dict) -> str:
    if not poll_data or "question" not in poll_data:
        return ""
    question = html.escape(poll_data["question"], quote=True)
    options = [html.escape(opt, quote=True) for opt in poll_data.get("options", [])]
    votes = poll_data.get("votes", {})
    total_votes = sum(len(v) for v in votes.values())

    html_parts = [f'<div class="poll-display"><h4>📊 {question}</h4>']
    for i, option_text in enumerate(options):
        vote_count = len(votes.get(str(i), []))
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
        html_parts.append(f"""
            <div class="poll-option-display" data-option-index="{i}">
                <div class="poll-option-text">{option_text} ({vote_count})</div>
                <div class="poll-bar-container">
                    <div class="poll-bar" style="width: {percentage:.1f}%;"></div>
                </div>
            </div>
        """)
    html_parts.append("</div>")
    return "".join(html_parts)


def _select_mirror_strategically(
    file_info: dict, mirrors: dict, thumb_mirrors: dict, is_ru: bool
) -> tuple[str, str]:
    """
    Выбирает URL для файла и его превью на основе приоритетов региона.
    """
    base_original_url = file_info.get("original_url", "")
    base_thumbnail_url = file_info.get("thumbnail_url", "")

    # Проверка валидности HF (из глобального списка VALID_HF_REPOS)
    hf_candidate = mirrors.get("huggingface")
    hf_valid = is_hf_link_allowed(hf_candidate, VALID_HF_REPOS)
    zeroxzero_candidate = mirrors.get("0x0")

    # --- ВЫБОР ОРИГИНАЛА ---
    selected_original = base_original_url  # По умолчанию Telegram Proxy

    if not is_ru:
        # Для ИНО-IP: Приоритет Catbox (быстрее всего)
        if "catbox" in mirrors:
            selected_original = mirrors["catbox"]
        elif hf_valid:
            selected_original = hf_candidate
        elif zeroxzero_candidate:
            selected_original = zeroxzero_candidate
    else:
        # Для RU-IP: Приоритет HF или Telegram
        if hf_valid:
            selected_original = hf_candidate
        elif "catbox" in mirrors:
            # Catbox для RU только если больше ничего нет
            selected_original = mirrors["catbox"]
        elif zeroxzero_candidate:
            selected_original = zeroxzero_candidate

    # --- ВЫБОР ПРЕВЬЮ (Thumbnail) ---
    selected_thumbnail = base_thumbnail_url

    # Приоритет №1: Telegra.ph (самый быстрый CDN для превью)
    if "telegraph" in thumb_mirrors:
        selected_thumbnail = thumb_mirrors["telegraph"]
    else:
        hf_thumb = thumb_mirrors.get("huggingface")
        hf_thumb_valid = is_hf_link_allowed(hf_thumb, VALID_HF_REPOS)
        zeroxzero_thumb = thumb_mirrors.get("0x0")

        if not is_ru:
            if "catbox" in thumb_mirrors:
                selected_thumbnail = thumb_mirrors["catbox"]
            elif hf_thumb_valid:
                selected_thumbnail = hf_thumb
            elif zeroxzero_thumb:
                selected_thumbnail = zeroxzero_thumb
        else:
            if hf_thumb_valid:
                selected_thumbnail = hf_thumb
            elif zeroxzero_thumb:
                selected_thumbnail = zeroxzero_thumb

    return selected_original, selected_thumbnail


async def enrich_extra_data(posts: List[dict], is_ru: bool = True):
    if not posts:
        return
    all_fids = []
    poll_post_ids = []
    all_post_ids = []

    for p in posts:
        all_post_ids.append(p["id"])
        files = p.get("content", {}).get("files", [])
        for f in files:
            fid = f.get("original_file_id")
            if fid:
                all_fids.append(fid)
            tid = f.get("thumbnail_file_id")
            if tid:
                all_fids.append(tid)

        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                all_post_ids.append(r["id"])
                r_files = r.get("content", {}).get("files", [])
                for rf in r_files:
                    rfid = rf.get("original_file_id")
                    if rfid:
                        all_fids.append(rfid)
                    rtid = rf.get("thumbnail_file_id")
                    if rtid:
                        all_fids.append(rtid)

        if "poll_data" in p.get("content", {}):
            poll_post_ids.append(p["id"])

        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                if "poll_data" in r.get("content", {}):
                    poll_post_ids.append(r["id"])

    dupe_map, blur_map, mirror_map = {}, {}, {}
    backlinks_map = defaultdict(list)
    tasks = []

    if all_fids:
        from common.database import get_mirrors_batch

        tasks.append(get_duplicate_counts(all_fids))
        tasks.append(get_blurhashes_batch(all_fids))
        tasks.append(get_mirrors_batch(all_fids))

    if poll_post_ids:
        for pid in poll_post_ids:
            tasks.append(get_poll_results(pid))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    res_idx = 0
    if all_fids:
        dupe_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1
        blur_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1
        mirror_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1

    poll_results_map = {}
    if poll_post_ids:
        for i, pid in enumerate(poll_post_ids):
            val = results[res_idx + i]
            if not isinstance(val, Exception):
                poll_results_map[pid] = val

    if all_post_ids:
        try:
            db = await get_pool()
            placeholders = ",".join("?" for _ in all_post_ids)
            query = f"SELECT target_post_num, source_post_num FROM Backlinks WHERE target_post_num IN ({placeholders})"
            async with db.execute(query, all_post_ids) as cursor:
                async for row in cursor:
                    target, source = row
                    backlinks_map[target].append(source)
        except Exception as e:
            print(f"Backlinks fetch error: {e}")

    for p in posts:
        db_bl = backlinks_map.get(p["id"], [])
        mem_bl = p.get("backlinks", [])
        p["backlinks"] = sorted(list(set(mem_bl) | set(db_bl)))

        def update_files(file_list):
            for f in file_list:
                fid = f.get("original_file_id")
                if not fid:
                    continue
                f["blurhash"] = blur_map.get(fid)
                f["dupe_count"] = dupe_map.get(fid, 0)

                mirrors = mirror_map.get(fid, {})
                tid = f.get("thumbnail_file_id")
                thumb_mirrors = mirror_map.get(tid, {}) if tid else {}

                f["original_url"], f["thumbnail_url"] = _select_mirror_strategically(
                    f, mirrors, thumb_mirrors, is_ru
                )

        if p.get("content", {}).get("files"):
            update_files(p["content"]["files"])
        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                r_db_bl = backlinks_map.get(r["id"], [])
                r_mem_bl = r.get("backlinks", [])
                r["backlinks"] = sorted(list(set(r_mem_bl) | set(r_db_bl)))
                if r.get("content", {}).get("files"):
                    update_files(r["content"]["files"])

        def apply_votes(post_obj):
            if "poll_data" in post_obj.get("content", {}):
                real_votes = poll_results_map.get(post_obj["id"], {})
                frontend_votes = {}
                if real_votes:
                    for opt_idx, count in real_votes.items():
                        frontend_votes[str(opt_idx)] = [0] * count
                post_obj["content"]["poll_data"]["votes"] = frontend_votes

        apply_votes(p)
        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                apply_votes(r)


def _convert_and_enrich_posts(posts: List[dict]) -> List[dict]:
    if not posts:
        return []
    for post in posts:
        if not post:
            continue
        if "post_num" in post:
            post["id"] = post.pop("post_num")
        if isinstance(post.get("content"), str):
            try:
                post["content"] = json.loads(post["content"])
            except:
                post["content"] = {"text": str(post.get("content", "")), "type": "text"}

        if not isinstance(post.get("content"), dict):
            post["content"] = {"text": "", "type": "text"}
        if post.get("latest_replies"):
            post["latest_replies"] = _convert_and_enrich_posts(post["latest_replies"])

        content = post["content"]
        if content.get("type") == "media_group" and "media" in content:
            file_list = []
            found_caption = None
            for item in content["media"]:
                f_type = item.get("type")
                f_id = item.get("file_id") or item.get("media")
                if not found_caption and item.get("caption"):
                    found_caption = item.get("caption")
                if f_id and isinstance(f_id, str) and not f_id.startswith("<"):
                    clean_type = "image" if f_type == "photo" else f_type
                    file_list.append(
                        {
                            "type": clean_type,
                            "original_file_id": f_id,
                            "thumbnail_file_id": f_id,
                            "filename": (
                                f"media_{f_id[:8]}.jpg"
                                if clean_type == "image"
                                else f"media_{f_id[:8]}.mp4"
                            ),
                        }
                    )
            content["files"] = file_list
            if not content.get("text") and found_caption:
                content["text"] = found_caption
        elif (
            content.get("type")
            in {
                "photo",
                "video",
                "animation",
                "document",
                "audio",
                "voice",
                "sticker",
                "video_note",
            }
            and "files" not in content
        ):
            file_info = {"type": content["type"]}
            ctype = content["type"]
            if (
                ctype == "photo"
                and content.get("photo")
                and isinstance(content["photo"], list)
            ):
                try:
                    file_info["original_file_id"] = content["photo"][-1].get("file_id")
                    file_info["thumbnail_file_id"] = content["photo"][0].get("file_id")
                    file_info["type"] = "image"
                except:
                    pass
            else:
                f_obj = content.get(ctype) or content
                f_id = f_obj.get("file_id")
                thumb_source = f_obj.get("thumb") or f_obj.get("thumbnail")
                if thumb_source and isinstance(thumb_source, dict):
                    file_info["thumbnail_file_id"] = thumb_source.get("file_id")
                mime = f_obj.get("mime_type", "")
                if ctype == "document" and mime.startswith("video/"):
                    file_info["type"] = "video"
                if f_id:
                    file_info["original_file_id"] = f_id
            if file_info.get("original_file_id"):
                content["files"] = [file_info]
        if "files" in content and isinstance(content["files"], list):
            valid_files = []
            for file_info in content["files"]:
                file_info.setdefault("dupe_count", 0)
                orig_url = file_info.get("original_url", "")
                if orig_url and "local_file://" in orig_url:
                    clean_id = orig_url.split("local_file://")[1]
                    file_info["original_file_id"] = clean_id
                    file_info["original_url"] = f"/files/{clean_id}"
                oid = file_info.get("original_file_id")
                if not oid or oid.startswith("<"):
                    continue
                fname = file_info.get("filename", "").lower()
                if fname.endswith((".mp4", ".webm", ".mov", ".mkv")) and file_info.get(
                    "type"
                ) not in ["voice", "audio"]:
                    file_info["type"] = "video"
                if fname.endswith(".webm") and file_info.get("type") == "sticker":
                    file_info["type"] = "video"
                ftype = file_info.get("type", "file")
                ext_map = {
                    "video": "mp4",
                    "photo": "jpg",
                    "image": "jpg",
                    "audio": "mp3",
                    "voice": "ogg",
                    "sticker": "webp",
                    "video_note": "mp4",
                    "animation": "mp4",
                    "gif": "mp4",
                }

                if (
                    not fname
                    or fname.startswith(".")
                    or fname == "file"
                    or "." not in fname
                ):
                    ext = ext_map.get(ftype, "dat")
                    prefix = (
                        "vid"
                        if ftype in ["video", "animation", "video_note", "gif"]
                        else ("aud" if ftype in ["audio", "voice"] else "img")
                    )
                    short_id = oid[:8] if oid else str(int(time.time()))
                    file_info["filename"] = f"{prefix}_{short_id}.{ext}"
                elif "." not in fname and ftype in ext_map:
                    file_info["filename"] = f"{fname}.{ext_map[ftype]}"

                from urllib.parse import quote

                safe_name = quote(str(file_info.get("filename", "file")).strip("/"))

                oid_str = str(oid) if oid else ""
                if oid_str.startswith(("http://", "https://")):
                    file_info["original_url"] = oid_str
                else:
                    clean_oid = oid_str.strip("/")
                    if clean_oid:
                        file_info["original_url"] = f"/files/{clean_oid}/{safe_name}"
                    else:
                        file_info["original_url"] = f"/files/{safe_name}"

                tid = file_info.get("thumbnail_file_id")
                if tid:
                    tid_str = str(tid)
                    if tid_str.startswith(("http://", "https://")):
                        file_info["thumbnail_url"] = tid_str
                    else:
                        file_info["thumbnail_url"] = f"/files/{tid_str.strip('/')}"
                else:
                    file_info["thumbnail_url"] = ""
                valid_files.append(file_info)
            content["files"] = valid_files
        current_type = content.get("type")
        has_text = bool(content.get("text", "").strip())
        has_files = bool(content.get("files"))
        if current_type != "poll":
            if has_files:
                content["type"] = "files"
            else:
                content["type"] = "text"
        post["report_count"] = post.get("report_count", 0)
        if "author_id" in post:
            post["author_id"] = get_user_hash(post["author_id"])
    return posts


def clean_title_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


templates.env.filters.update(
    {
        "pluralize": pluralize_russian,
        "format_post_text": format_post_text,
        "format_timestamp": format_timestamp,
        "format_poll": format_poll_for_html,
        "format_iso_time": format_iso_time,
        "bayan_label": format_bayan_label,
        "clean_title": clean_title_text,
        "nick_from_hash": nick_from_hash,
    }
)


async def queue_listener(manager: "ConnectionManager"):
    last_ts = time.time()
    logger.info(f"INFO:     DB Queue listener started. Timestamp base: {last_ts}")
    try:
        while True:
            try:
                new_posts, new_ts = await get_posts_from_broadcast_queue(last_ts)
                if new_posts:
                    affected_boards = set()
                    affected_threads = set()

                    for p in new_posts:
                        if "post_num" in p and "id" not in p:
                            p["id"] = p["post_num"]
                        affected_boards.add(p["board_id"])

                        t_id = p.get("thread_id")
                        if not t_id and p.get("is_op_post"):
                            t_id = p["id"]
                        if t_id:
                            affected_threads.add(str(t_id))

                    now = time.time()
                    # Инвалидация досок
                    for bid in affected_boards:
                        BOARD_VERSIONS[bid] = now

                    # ИЗМЕНЕНИЕ: Явное обновление оверборда
                    BOARD_VERSIONS["overboard"] = now

                    # Инвалидация тредов
                    for tid in affected_threads:
                        THREAD_VERSIONS[tid] = now

                    await enrich_extra_data(new_posts, is_ru=True)

                    for post in new_posts:
                        await manager.broadcast_post(post, post["board_id"])
                        await asyncio.sleep(0.05)
                if new_ts > last_ts:
                    last_ts = new_ts
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Queue listener error: {e}")
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass


async def db_maintenance_task():
    await asyncio.sleep(60)
    # Импортируем лок из пула (он общий, если site_tgach импортирует common)
    # Если common.db_pool используется и сайтом, и ботом - отлично.
    from common.db_pool import get_pool, db_lock

    while True:
        try:
            logger.info("🧹 [DB] Starting cleanup & maintenance...")

            # Запускаем тяжелую синхронную очистку в отдельном потоке
            await asyncio.to_thread(cleanup_old_posts_from_db)

            # Асинхронные очистки очередей
            try:
                await cleanup_broadcast_queue(retention_hours=6)
            except Exception as e:
                logger.warning(f"⚠️ Broadcast cleanup postponed: {e}")

            try:
                await cleanup_shadow_posts_db(hours=24)
            except Exception as e:
                logger.warning(f"⚠️ Shadow cleanup postponed: {e}")

            # Обслуживание FTS и оптимизация
            # Используем db_lock, так как здесь идет запись/модификация структуры
            async with db_lock:
                try:
                    db = await get_pool()
                    await db.execute("BEGIN IMMEDIATE")

                    month_ago = time.time() - (30 * 86400)
                    await db.execute(
                        "DELETE FROM GlobalLogs WHERE created_at < ?", (month_ago,)
                    )

                    try:
                        await db.execute(
                            "INSERT INTO FileTagsFTS(FileTagsFTS) VALUES('optimize');"
                        )
                        await db.execute(
                            "INSERT INTO PostsFTS(PostsFTS) VALUES('optimize');"
                        )
                    except Exception as fts_err:
                        logger.warning(f"⚠️ FTS optimize skipped: {fts_err}")

                    await db.execute("COMMIT")

                    # PRAGMA команды выполняем вне транзакции, но под локом
                    # optimize и checkpoint могут быть долгими
                    try:
                        await db.execute("PRAGMA optimize;")
                        await db.execute("PRAGMA wal_checkpoint(PASSIVE);")
                    except Exception as opt_err:
                        logger.warning(f"⚠️ DB Optimization warning: {opt_err}")

                except Exception as e:
                    try:
                        await db.execute("ROLLBACK")
                    except:
                        pass
                    logger.error(f"⚠️ FTS Maintenance error: {e}")

            logger.info("✅ [DB] Maintenance complete.")
        except Exception as e:
            logger.error(f"⚠️ DB Maintenance error: {e}")

        await asyncio.sleep(43200)


async def websocket_broadcaster(queue: asyncio.Queue, manager: "ConnectionManager"):
    logger.info("INFO:     WebSocket broadcaster started.")
    try:
        while True:
            try:
                post_data = await queue.get()
                await manager.broadcast_post(post_data, post_data["board_id"])
                queue.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Broadcaster error: {e}")
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


async def enrich_heavy_data(posts: List[dict]):
    """
    ТЯЖЕЛАЯ ФАЗА: Загрузка всех метаданных из БД.
    Этот результат будет закэширован.
    Не делает выбор зеркала (RU/Non-RU) и не ставит флаги юзера.
    """
    if not posts:
        return
    all_fids = []
    poll_post_ids = []
    all_post_ids = []

    for p in posts:
        all_post_ids.append(p["id"])
        files = p.get("content", {}).get("files", [])
        for f in files:
            fid = f.get("original_file_id")
            if fid:
                all_fids.append(fid)
            tid = f.get("thumbnail_file_id")
            if tid:
                all_fids.append(tid)

        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                all_post_ids.append(r["id"])
                r_files = r.get("content", {}).get("files", [])
                for rf in r_files:
                    rfid = rf.get("original_file_id")
                    if rfid:
                        all_fids.append(rfid)
                    rtid = rf.get("thumbnail_file_id")
                    if rtid:
                        all_fids.append(rtid)

        if "poll_data" in p.get("content", {}):
            poll_post_ids.append(p["id"])
        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                if "poll_data" in r.get("content", {}):
                    poll_post_ids.append(r["id"])

    # Параллельные запросы
    tasks = []
    if all_fids:
        from common.database import (
            get_mirrors_batch,
            get_duplicate_counts,
            get_blurhashes_batch,
        )

        tasks.append(get_duplicate_counts(all_fids))
        tasks.append(get_blurhashes_batch(all_fids))
        tasks.append(get_mirrors_batch(all_fids))

    if poll_post_ids:
        for pid in poll_post_ids:
            tasks.append(get_poll_results(pid))

    # Бэклинки теперь тоже в пуле задач
    if all_post_ids:

        async def fetch_backlinks_task(ids):
            try:
                db = await get_pool()
                placeholders = ",".join("?" for _ in ids)
                q = f"SELECT target_post_num, source_post_num FROM Backlinks WHERE target_post_num IN ({placeholders})"
                res = defaultdict(list)
                async with db.execute(q, ids) as cursor:
                    async for row in cursor:
                        res[row[0]].append(row[1])
                return res
            except:
                return {}

        tasks.append(fetch_backlinks_task(all_post_ids))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    dupe_map, blur_map, mirror_map = {}, {}, {}
    res_idx = 0
    if all_fids:
        dupe_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1
        blur_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1
        mirror_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )
        res_idx += 1

    poll_results_map = {}
    if poll_post_ids:
        for i, pid in enumerate(poll_post_ids):
            val = results[res_idx + i]
            if not isinstance(val, Exception):
                poll_results_map[pid] = val
        res_idx += len(poll_post_ids)

    # Достаем бэклинки из результатов gather
    backlinks_map = {}
    if all_post_ids:
        backlinks_map = (
            results[res_idx] if not isinstance(results[res_idx], Exception) else {}
        )

    # Применение данных
    for p in posts:
        # Backlinks
        db_bl = backlinks_map.get(p["id"], [])
        mem_bl = p.get("backlinks", [])
        p["backlinks"] = sorted(list(set(mem_bl) | set(db_bl)))

        # Polls
        if "poll_data" in p.get("content", {}):
            real_votes = poll_results_map.get(p["id"], {})
            if real_votes:
                frontend_votes = {}
                for opt_idx, count in real_votes.items():
                    frontend_votes[str(opt_idx)] = [0] * count
                p["content"]["poll_data"]["votes"] = frontend_votes

        # Files (Attach metadata, BUT DO NOT SELECT URL YET)
        def attach_file_meta(file_list):
            for f in file_list:
                fid = f.get("original_file_id")
                if not fid:
                    continue
                f["blurhash"] = blur_map.get(fid)
                f["dupe_count"] = dupe_map.get(fid, 0)

                # Сохраняем зеркала в скрытые поля для фазы гидратации
                f["_mirrors"] = mirror_map.get(fid, {})
                tid = f.get("thumbnail_file_id")
                f["_thumb_mirrors"] = mirror_map.get(tid, {}) if tid else {}

        if p.get("content", {}).get("files"):
            attach_file_meta(p["content"]["files"])

        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                r_db_bl = backlinks_map.get(r["id"], [])
                r_mem_bl = r.get("backlinks", [])
                r["backlinks"] = sorted(list(set(r_mem_bl) | set(r_db_bl)))

                if "poll_data" in r.get("content", {}):
                    real_votes = poll_results_map.get(r["id"], {})
                    if real_votes:
                        frontend_votes = {}
                        for opt_idx, count in real_votes.items():
                            frontend_votes[str(opt_idx)] = [0] * count
                        r["content"]["poll_data"]["votes"] = frontend_votes

                if r.get("content", {}).get("files"):
                    attach_file_meta(r["content"]["files"])


def finalize_posts_for_user(
    posts: List[dict], user_id: int, is_ru: bool, op_author_id: str = None
):
    """
    ЛЕГКАЯ ФАЗА: Гидратация.
    op_author_id (хэш-строка) передается при просмотре конкретного треда.
    """
    if not posts:
        return

    # Предварительно вычисляем хэш текущего пользователя для сравнения
    user_hash = get_user_hash(user_id) if user_id else None

    for p in posts:
        p_author_hash = p.get("author_id")

        # 1. Метка "Это мой пост" (You)
        if user_hash and p_author_hash == user_hash:
            p["is_yours"] = True

        # 2. Метка "Автор треда" (OP)
        # Если мы в контексте треда (op_author_id задан), помечаем посты его автора
        if op_author_id and p_author_hash == op_author_id:
            p["is_by_op"] = True

        # 3. Выбор зеркал
        def apply_urls(file_list):
            for f in file_list:
                mirrors = f.get("_mirrors", {})
                thumb_mirrors = f.get("_thumb_mirrors", {})
                f["original_url"], f["thumbnail_url"] = _select_mirror_strategically(
                    f, mirrors, thumb_mirrors, is_ru
                )

        if p.get("content", {}).get("files"):
            apply_urls(p["content"]["files"])

        # Определяем OP для вложенных ответов (превью в ленте)
        # Если op_author_id не задан (лента), считаем текущий пост OP-ом
        effective_op_id = op_author_id if op_author_id else p_author_hash

        if p.get("latest_replies"):
            for r in p["latest_replies"]:
                # Исправлено: сравниваем с хэшем (user_hash), а не int ID
                if user_hash and r.get("author_id") == user_hash:
                    r["is_yours"] = True
                # Исправлено: имя переменной (было current_op_id) и логика
                if effective_op_id and r.get("author_id") == effective_op_id:
                    r["is_by_op"] = True
                if r.get("content", {}).get("files"):
                    apply_urls(r["content"]["files"])


@app.get("/welcome")
async def welcome_page(request: Request):

    return templates.TemplateResponse(
        request=request, name="landing.jinja2", context={"request": request}
    )


@app.get("/")
async def read_root(request: Request, user: dict | None = Depends(get_optional_user)):
    if ENABLE_MULTILANG:
        stream_cookie = request.cookies.get("stream")
        if not stream_cookie:
            return RedirectResponse(url="/welcome")
    lang = getattr(request.state, "lang", "ru")
    local_boards = localize_boards(lang)

    base_url = str(request.base_url).rstrip("/")
    meta_image = f"{base_url}/static/{random.choice(['logo.png', 'logo1.png'])}"

    return templates.TemplateResponse(
        request=request,
        name="index.jinja2",
        context={
            "request": request,
            "boards": local_boards,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "meta_image": meta_image,
        },
    )


@app.get("/login")
def login_page(request: Request):
    if "user" in request.session:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        request=request,
        name="login.jinja2",
        context={
            "request": request,
            "BOT_USERNAME": BOT_USERNAME,
            "session": request.session,
        },
    )


@app.get("/rules/")
async def rules_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="rules.jinja2",
        context={"request": request, "BOT_USERNAME": BOT_USERNAME},
    )


@app.get("/auth/logout")
async def auth_logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")


@app.get("/search")
async def search_page(
    request: Request,
    query: str = "",
    archive: int = 0,
    user: dict | None = Depends(get_optional_user),
):
    clean_query = query.strip()
    if clean_query:
        clean_query = clean_query.replace('"', '""')

    observer_id = user["id"] if user else getattr(request.state, "guest_id", 0)

    results = (
        await search_posts(
            clean_query, observer_id=observer_id, only_archived=bool(archive)
        )
        if clean_query
        else []
    )
    results = _convert_and_enrich_posts(results)
    await enrich_extra_data(results)
    return templates.TemplateResponse(
        request=request,
        name="search_results.jinja2",
        context={
            "request": request,
            "query": query,
            "posts": results,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "archive": archive,
        },
    )


@app.get("/newspaper")
async def newspaper_today():
    import datetime

    today = datetime.date.today().strftime("%Y-%m-%d")
    return RedirectResponse(url=f"/newspaper/{today}")


@app.get("/newspaper/{year}-{month:int}-{day:int}")
async def newspaper_page(
    request: Request,
    year: int,
    month: int,
    day: int,
    user: dict | None = Depends(get_optional_user),
):
    date_str = f"{year}-{month:02d}-{day:02d}"
    data = await get_newspaper_data(date_str)

    if data and data.get("longest_posts"):
        data["longest_posts"] = _convert_and_enrich_posts(data["longest_posts"])
        await enrich_extra_data(data["longest_posts"])

    return templates.TemplateResponse(
        request=request,
        name="newspaper.jinja2",
        context={
            "request": request,
            "data": data,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/admin/serverConfig.json", include_in_schema=False)
async def api_dummy_config():
    """Заглушка для подавления 404 ошибок в логах от админки."""
    return JSONResponse({})


@app.get("/.well-known/security.txt", response_class=Response)
async def security_txt():
    return RedirectResponse(url="/static/security.txt")


@app.get("/favourites/")
async def favourites_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="favourites.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/overboard/")
async def overboard_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    user_agent = request.headers.get("user-agent", "").lower()
    bot_markers = [
        "bot",
        "crawl",
        "slurp",
        "spider",
        "mediapartners",
        "whatsapp",
        "telegram",
        "discord",
        "facebook",
        "pinterest",
    ]
    is_bot = any(marker in user_agent for marker in bot_markers)

    sort_mode = request.query_params.get("sort", "bump")
    if sort_mode not in ["bump", "new", "random"]:
        sort_mode = "bump"
    view_mode = request.query_params.get("view", "threads")
    if view_mode not in ["threads", "posts", "all"]:
        view_mode = "threads"

    selected_boards = request.query_params.getlist("boards") or None
    boards_key = ",".join(sorted(selected_boards)) if selected_boards else "all"
    stream = getattr(request.state, "stream", "ru")

    cache_key = f"bot_overboard_html:{sort_mode}:{view_mode}:{boards_key}:{stream}"
    if is_bot and not user:
        backend = FastAPICache.get_backend()
        if backend:
            cached = await backend.get(cache_key)
            if cached:
                return HTMLResponse(content=cached)

    posts = []
    is_skeleton = False

    if is_bot:
        observer_id = user["id"] if user else getattr(request.state, "guest_id", 0)
        if view_mode == "threads":
            raw_posts = await get_op_posts_for_board(
                selected_boards,
                sort_by=sort_mode,
                page=1,
                page_size=50,
                stream=request.state.stream,
                observer_id=observer_id,
                ignore_pin=True,
                reply_limit=2,
            )
        elif view_mode == "posts":
            raw_posts = await get_global_feed_posts(
                selected_boards,
                page=1,
                page_size=50,
                stream=request.state.stream,
                observer_id=observer_id,
                include_chat=False,
                sort_by=sort_mode,
            )
        else:
            raw_posts = await get_global_feed_posts(
                selected_boards,
                page=1,
                page_size=50,
                stream=request.state.stream,
                observer_id=observer_id,
                include_chat=True,
                sort_by=sort_mode,
            )
        posts = await asyncio.to_thread(_convert_and_enrich_posts, raw_posts)
        is_ru = await is_request_from_ru(request)
        await enrich_extra_data(posts, is_ru=is_ru)
    else:
        is_skeleton = True

    lang = getattr(request.state, "lang", "ru")
    local_boards = localize_boards(lang)

    context = {
        "request": request,
        "posts": posts,
        "site_mode": SITE_ACCESS_MODE,
        "session": {"user": user},
        "boards": local_boards,
        "all_boards": {k: v for k, v in local_boards.items() if k != "test"},
        "current_sort": sort_mode,
        "current_view": view_mode,
        "selected_boards": selected_boards or [],
        "is_skeleton": is_skeleton,
    }

    html_content = templates.get_template("overboard.jinja2").render(context)

    if is_bot and not user:
        backend = FastAPICache.get_backend()
        if backend:
            await backend.set(cache_key, html_content, expire=300)  # Кэш на 5 минут

    return HTMLResponse(content=html_content)


@app.get("/history/")
async def history_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="history.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/faq/")
async def faq_page(request: Request, user: dict | None = Depends(get_optional_user)):
    return templates.TemplateResponse(
        request=request,
        name="faq.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "bot_username": BOT_USERNAME,
        },
    )


@app.get("/about/")
async def about_page(request: Request, user: dict | None = Depends(get_optional_user)):
    return templates.TemplateResponse(
        request=request,
        name="about.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/my/")
async def my_posts_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="my_posts.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "BOT_USERNAME": BOT_USERNAME,
        },
    )


@app.get("/my/replies")
async def my_replies_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="my_replies.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "BOT_USERNAME": BOT_USERNAME,
        },
    )


@app.get("/api/my/replies/count")
async def api_my_replies_count(user: dict = Depends(get_current_user_or_guest)):
    count = await get_unread_replies_count(int(user["id"]))
    return {"count": count}


@app.get("/api/my/replies/list")
async def api_my_replies_list(
    page: int = 0, user: dict = Depends(get_current_user_or_guest)
):
    limit = 20
    offset = page * limit
    replies = await get_user_replies(int(user["id"]), limit, offset)
    return replies


class MarkReadRequest(BaseModel):
    ids: List[int] = []


@app.post("/api/my/replies/read")
async def api_my_replies_read(
    data: MarkReadRequest, user: dict = Depends(get_current_user_or_guest)
):
    await mark_replies_read(int(user["id"]), data.ids if data.ids else None)
    return {"status": "ok"}


@app.get("/useful/")
async def useful_page(request: Request, user: dict | None = Depends(get_optional_user)):
    return templates.TemplateResponse(
        request=request,
        name="useful.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "BOT_USERNAME": BOT_USERNAME,
            "t": request.state.t,
        },
    )


@app.get("/archive/")
async def archive_hub_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):

    if SITE_ACCESS_MODE == "PRIVATE" and not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        request=request,
        name="archive_hub.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/api/file/tags")
async def api_get_file_tags(file_id: str):
    """Возвращает теги для файла"""
    tags = await get_file_tags(file_id)
    return {"tags": tags}


@app.get("/search/tags")
@limiter.limit("60/minute")
async def search_tags_page(
    request: Request,
    tags: str = "",
    page: int = 1,
    user: dict | None = Depends(get_optional_user),
):
    # 1. Формируем уникальный ключ для кэша (зависит от тегов и страницы)
    # Кэшируем только для гостей (чтобы у админов работали кнопки)
    cache_key = f"search_tags:{tags}:{page}"
    backend = FastAPICache.get_backend()

    if not user and backend:
        cached_html = await backend.get(cache_key)
        if cached_html:
            return HTMLResponse(content=cached_html)

    # 2. Если в кэше нет - ищем в базе
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    search_images = []

    if tag_list:
        offset = (page - 1) * 60
        files_found = await search_files_by_tags(tag_list, limit=60, offset=offset)
        file_scores = {f["file_id"]: f["score"] for f in files_found}
        file_ids = list(file_scores.keys())

        raw_posts = await get_posts_by_file_ids(file_ids)
        posts = _convert_and_enrich_posts(raw_posts)
        await enrich_extra_data(posts)

        # Сортировка по релевантности
        def calculate_relevance(post):
            content_files = post.get("content", {}).get("files", [])
            scores = [
                file_scores.get(f.get("original_file_id"), 0) for f in content_files
            ]
            return max(scores) if scores else 0

        posts.sort(
            key=lambda p: (calculate_relevance(p), p.get("timestamp", 0)), reverse=True
        )

        for post in posts:
            post_id = post.get("id")
            board_id = post.get("board_id")
            if not post_id or not board_id:
                continue
            content = post.get("content", {})
            files = content.get("files", [])
            if not isinstance(files, list):
                continue
            for f in files:
                if not isinstance(f, dict):
                    continue
                if f.get("type") in [
                    "image",
                    "photo",
                    "sticker",
                    "gif",
                    "video",
                    "animation",
                    "video_note",
                ]:
                    img_entry = f.copy()
                    img_entry["parent_post_id"] = post_id
                    img_entry["parent_board_id"] = board_id
                    search_images.append(img_entry)

    if request.headers.get("accept") == "application/json":
        return search_images

    # 3. Рендерим шаблон в текст
    html_content = templates.get_template("search_results.jinja2").render(
        {
            "request": request,
            "query": f"Tags: {tags}",
            "search_images": search_images,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "is_tag_search": True,
        }
    )

    # 4. Сохраняем текст в кэш (на 10 минут)
    if not user and backend:
        await backend.set(cache_key, html_content, expire=600)

    return HTMLResponse(content=html_content)


@app.get("/tags/")
async def tags_index_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    # Кэшируем страницу целиком на 5 минут для всех
    cache_key = "tags_index_page_html"
    backend = FastAPICache.get_backend()

    if not user and backend:
        cached = await backend.get(cache_key)
        if cached:
            return HTMLResponse(content=cached)

    # Получаем топ тегов
    tags = await get_recent_tags_summary(limit_files=5000, top_n=200)
    tags.sort(key=lambda x: x[0])

    lang = getattr(request.state, "lang", "ru")
    base_title = "Popular Tags" if lang == "en" else "Популярные теги"

    html_content = templates.get_template("tags_index.jinja2").render(
        {
            "request": request,
            "tags": tags,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "meta_title": base_title,
        }
    )

    if not user and backend:
        await backend.set(cache_key, html_content, expire=300)

    return HTMLResponse(content=html_content)


@app.get("/tags/{tag_name}")
async def tag_seo_page(
    request: Request,
    tag_name: str,
    page: int = 1,
    user: dict | None = Depends(get_optional_user),
):
    clean_tag = tag_name.strip().replace("-", " ")

    # Кэшируем страницу конкретного тега
    cache_key = f"seo_tag:{clean_tag}:{page}"
    backend = FastAPICache.get_backend()

    if not user and backend:
        cached = await backend.get(cache_key)
        if cached:
            return HTMLResponse(content=cached)

    # Поиск (тот же механизм, что и выше, но для SEO страницы)
    offset = (page - 1) * 60
    files_found = await search_files_by_tags([clean_tag], limit=60, offset=offset)
    file_ids = [f["file_id"] for f in files_found]

    raw_posts = await get_posts_by_file_ids(file_ids)
    posts = _convert_and_enrich_posts(raw_posts)
    await enrich_extra_data(posts, is_ru=True)

    search_images = []
    for post in posts:
        # Упрощенная сборка картинок для SEO
        if post.get("content", {}).get("files"):
            for f in post["content"]["files"]:
                f["parent_post_id"] = post["id"]
                f["parent_board_id"] = post["board_id"]
                search_images.append(f)

    meta_title = f"{clean_tag.title()} Archive"
    meta_desc = f"Best {clean_tag} content."

    html_content = templates.get_template("search_results.jinja2").render(
        {
            "request": request,
            "query": f"Tag: {clean_tag}",
            "search_images": search_images,
            "boards": BOARD_CONFIG,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "is_tag_search": True,
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "current_tag": clean_tag,
        }
    )

    if not user and backend:
        await backend.set(cache_key, html_content, expire=600)

    return HTMLResponse(content=html_content)


@app.get("/{board_id}/index.json")
@cache(expire=60)
@app.get("/{board_id}/{page}.json")
async def api_makaba_index(request: Request, board_id: str, page: str = "index"):

    if board_id not in BOARD_CONFIG:
        return JSONResponse({"Error": "Board not found"}, status_code=404)
    page_num = 0
    if page != "index":
        try:
            page_num = int(page)
        except:
            if page == "catalog":
                return await api_makaba_catalog(board_id)
            raise HTTPException(404)
    threads = await get_op_posts_for_board(board_id, page=page_num + 1, page_size=20)
    threads = _convert_and_enrich_posts(threads)
    makaba_threads = []
    for thread in threads:
        op_obj = to_makaba_post(thread, board_id)
        posts_list = [op_obj]
        if "latest_replies" in thread and thread["latest_replies"]:
            for reply in thread["latest_replies"]:
                posts_list.append(to_makaba_post(reply, board_id))
        makaba_threads.append(
            {
                "posts": posts_list,
                "posts_count": thread.get("reply_count", 0) + 1,
                "files_count": 0,
            }
        )
    return {
        "Board": board_id,
        "BoardName": BOARD_CONFIG[board_id]["name"],
        "threads": makaba_threads,
    }


@app.get("/{board_id}/catalog.json")
@cache(expire=60)
async def api_makaba_catalog(board_id: str):

    if board_id not in BOARD_CONFIG:
        return JSONResponse({}, status_code=404)
    threads = await get_op_posts_for_board(
        board_id, sort_by="bump", page=1, page_size=100
    )
    threads = _convert_and_enrich_posts(threads)
    makaba_threads = []
    for thread in threads:
        op_obj = to_makaba_post(thread, board_id)
        op_obj["threads_count"] = thread.get("reply_count", 0)
        makaba_threads.append(op_obj)
    return {"threads": makaba_threads}


@app.get("/{board_id}/res/{thread_num}.json")
@cache(expire=10)
async def api_makaba_thread(board_id: str, thread_num: int):

    if board_id not in BOARD_CONFIG:
        return JSONResponse({}, status_code=404)
    thread_data = await get_thread_by_op_post(thread_num)
    if not thread_data:
        return JSONResponse({"Error": "Thread not found"}, status_code=404)
    op_post, replies = thread_data
    op_post = _convert_and_enrich_posts([op_post])[0]
    replies = _convert_and_enrich_posts(replies)
    all_posts = [to_makaba_post(op_post, board_id)]
    for p in replies:
        all_posts.append(to_makaba_post(p, board_id))
    return {
        "Board": board_id,
        "current_thread": str(thread_num),
        "threads": [{"posts": all_posts}],
        "unique_posters": "0",
    }


@app.get("/api/stats/detailed")
@cache(expire=600)
async def api_detailed_stats():
    return await get_detailed_statistics()


@app.get("/api/captcha/status")
async def api_captcha_status():
    val = await get_setting_cached("captcha_enabled")
    return {"enabled": val == "true"}


@app.get("/api/pow/challenge")
async def api_public_pow_challenge(
    request: Request, user: dict = Depends(get_current_user_or_guest)
):
    """
    Отдает задачу PoW.
    Логика:
    1. Если PoW выключен админом -> сложность 0.
    2. Если PoW включен, но юзер "свой" -> сложность 0.
    3. Иначе -> даем задачу.
    """
    is_enabled = (await get_system_setting("pow_enabled")) == "true"
    if not is_enabled:
        return {"challenge": "", "difficulty": 0}
    is_trusted = False
    if not user.get("is_guest"):
        is_trusted = True
    else:
        guest_id = int(user["id"])
        async with get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT created_at FROM Users WHERE user_id = ?", (guest_id,)
                )
            ).fetchone()
            if row and row[0]:
                age = time.time() - row[0]
                if age > 3600:
                    is_trusted = True
    if is_trusted:
        return {"challenge": "", "difficulty": 0}
    from site_tgach.security import get_pow_challenge_data

    return get_pow_challenge_data()


class PowToggleRequest(BaseModel):
    enabled: bool


import gzip

# --- ВЕЧНЫЕ ГЕНЕРАТОРЫ (СМЕРТЬ БОТАМ, 0% CPU) ---

# 1. GZIP: 10MB нулей сжаты в ~10KB. Бот распаковывает их вечно.
_ZEROS = b"\x00" * 10 * 1024 * 1024
_COMPRESSED_ZEROS = gzip.compress(_ZEROS)

# 2. HTML: Бесконечная вложенность дивов. Убивает парсеры.
_HTML_CHUNK = (b'<div class="wrapper"><div class="container">' * 500) + b"\n"

# 3. XML: Для сканеров типа _vti_bin. Бесконечная структура.
_XML_CHUNK = (
    b"<item><title>Infinite Loop</title><description>"
    + (b"blah " * 100)
    + b"</description></item>\n"
)

# 4. JS: Бесконечный поток валидных комментариев.
_JS_HEAD = b"console.log('Starting...');\n"
_JS_CHUNK = b"/* " + (b"x" * 4096) + b" */\n"


async def gzip_bomb_generator():
    """Отдает бесконечные гигабайты распакованных нулей."""
    try:
        while True:
            yield _COMPRESSED_ZEROS
            await asyncio.sleep(0.05)  # Не грузим свой канал, держим бота на крючке
    except asyncio.CancelledError:
        pass


async def html_depth_charge_generator():
    """Ломает DOM-парсеры бесконечной вложенностью."""
    yield b"<!DOCTYPE html><html><body>"
    try:
        while True:
            yield _HTML_CHUNK
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass


async def xml_tarpit_generator():
    """Ловушка для XML/RSS сканеров."""
    yield b'<?xml version="1.0"?><rss version="2.0"><channel>'
    try:
        while True:
            yield _XML_CHUNK
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass


async def js_infinite_stream_generator():
    """Вешает JS-движки, ожидающие конца файла."""
    yield _JS_HEAD
    try:
        while True:
            yield _JS_CHUNK
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass


async def slow_death_generator():
    """Классический Slow Loris: 1 байт раз в 20 секунд."""
    try:
        while True:
            yield b" "
            await asyncio.sleep(20)
    except asyncio.CancelledError:
        pass


async def managed_troll_generator(gen):
    """Обертка для контроля количества активных 'токсичных' соединений."""
    global ACTIVE_TROLL_CONNS
    ACTIVE_TROLL_CONNS += 1
    try:
        async for chunk in gen:
            yield chunk
    finally:
        ACTIVE_TROLL_CONNS -= 1


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/rest/v1/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/api/v2/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/api/v3/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/api/adx/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/api/stats/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/api/census/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/admin/{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/.env", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/config.json", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/config.js", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/config.php", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/hello.world", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/mcp", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/sse", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/wp-{path:path}", methods=["GET", "POST", "PROPFIND"])
@app.api_route("/", methods=["PROPFIND"])  # <--- ГЛАВНАЯ ЛОВУШКА ДЛЯ WebDAV БОТОВ
@app.api_route(
    "/autodiscover/{path:path}",
    methods=["GET", "POST", "PROPFIND"],
    include_in_schema=False,
)
@app.api_route(
    "/owa/{path:path}", methods=["GET", "POST", "PROPFIND"], include_in_schema=False
)
@app.api_route(
    "/.git/{path:path}", methods=["GET", "POST", "PROPFIND"], include_in_schema=False
)
async def honey_pot_troll(request: Request):
    client_ip = get_real_ip(request)
    path = request.url.path.lower()

    if path.endswith(
        (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            ".mp4",
            ".webm",
            ".mov",
            ".mkv",
            ".html",
            ".js",
            ".css",
        )
    ):
        return Response(status_code=404)

    user = request.session.get("user")
    if user and user.get("is_admin"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # ПРОВЕРКА ЛИМИТА: Если ловушки переполнены, просто отдаем 404, чтобы не вешать сервер
    if ACTIVE_TROLL_CONNS >= MAX_TROLL_CONNS:
        return Response(status_code=404)

    BOT_VIOLATIONS[client_ip] += 1
    hit_count = BOT_VIOLATIONS[client_ip]
    if hit_count >= 20:
        IP_BAN_LIST[client_ip] = time.time() + 86400 * 365
        return StreamingResponse(
            managed_troll_generator(gzip_bomb_generator()),
            media_type="application/octet-stream",
            headers={"Content-Encoding": "gzip"},
        )

    # АНАЛИЗ ЖЕРТВЫ: Подбираем идеальный яд
    path = request.url.path.lower()
    method = request.method.upper()  # Получаем метод
    accept = request.headers.get("Accept", "").lower()

    strategy = "slow"  # По умолчанию - медленная смерть

    # НОВОЕ: Если это PROPFIND - сразу XML ловушку (это WebDAV протокол)
    if method == "PROPFIND":
        strategy = "xml"

    # 1. Если ищет файлы/архивы -> GZIP BOMB
    elif any(
        x in path
        for x in [
            ".zip",
            ".tar",
            ".gz",
            ".sql",
            ".dump",
            ".bak",
            "backup",
            "admin",
            ".env",
            ".old",
        ]
    ):
        strategy = "gzip"

    # 2. Если ищет веб-страницу -> HTML DEPTH CHARGE
    elif "html" in accept or path.endswith((".php", ".asp", "/")):
        strategy = "html"

    # 3. Если ищет XML/RSS/SharePoint (_vti_bin) -> XML TARPIT
    elif "xml" in accept or "_vti" in path or ".rss" in path or ".xml" in path:
        strategy = "xml"

    # 4. Если ищет скрипты -> JS INFINITY
    elif ".js" in path or "json" in accept:
        strategy = "js"

    logger.warning(
        f"🪤 TROLLING {client_ip} with [{strategy.upper()}] on {path} ({method})"
    )

    # ИСПОЛНЕНИЕ НАКАЗАНИЯ
    if strategy == "gzip":
        filename = f"database_dump_{secrets.token_hex(4)}.sql.gz"
        return StreamingResponse(
            managed_troll_generator(gzip_bomb_generator()),
            media_type="application/x-gzip",
            headers={
                "Content-Encoding": "gzip",
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    elif strategy == "html":
        return StreamingResponse(
            managed_troll_generator(html_depth_charge_generator()),
            media_type="text/html",
        )

    elif strategy == "xml":
        return StreamingResponse(
            managed_troll_generator(xml_tarpit_generator()),
            media_type="application/xml",
        )

    elif strategy == "js":
        return StreamingResponse(
            managed_troll_generator(js_infinite_stream_generator()),
            media_type="application/javascript",
        )

    else:  # slow death
        return StreamingResponse(
            managed_troll_generator(slow_death_generator()), media_type="text/plain"
        )


@app.get("/admin/login")
async def fake_admin_panel(request: Request):
    """
    Фейковая админка. Принимает любой пароль.
    """
    return HTMLResponse("""
    <html>
    <head>
        <title>Admin Panel - Restricted Area</title>
        <style>
            body { background: #000; color: #0f0; font-family: monospace; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .box { border: 1px solid #0f0; padding: 20px; width: 300px; }
            input { background: #111; border: 1px solid #0f0; color: #fff; width: 100%; padding: 5px; margin-bottom: 10px; }
            button { background: #0f0; color: #000; border: none; padding: 5px 15px; cursor: pointer; width: 100%; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2 style="text-align:center; margin-top:0;">🛑 TOP SECRET</h2>
            <form action="/admin/dashboard_fake" method="post">
                <label>Username:</label>
                <input type="text" name="user">
                <label>Password:</label>
                <input type="password" name="pass">
                <button type="submit">LOGIN</button>
            </form>
        </div>
    </body>
    </html>
    """)


@app.post("/admin/dashboard_fake")
async def fake_admin_dashboard(request: Request):
    """
    Скример или фейковый лог ФСБ.
    """
    client_ip = get_real_ip(request)
    return HTMLResponse(f"""
    <html>
    <body style="background:#000; color:red; font-family:monospace; font-size:16px;">
        <pre id="log"></pre>
        <script>
            const ip = "{client_ip}";
            const logs = [
                "ACCESS GRANTED.",
                "INITIATING TRACE ON IP: " + ip,
                "GEOLOCATION LOCK... SUCCESS.",
                "UPLOADING BIOMETRIC DATA...",
                "SENDING REPORT TO LOCAL AUTHORITIES...",
                "DELETING SYSTEM32 ON CLIENT...",
                "ENCRYPTING LOCAL DRIVES...",
                "THANK YOU FOR VISITING."
            ];
            let i = 0;
            const el = document.getElementById('log');
            setInterval(() => {{
                if(i < logs.length) {{
                    el.innerHTML += logs[i] + "\\n";
                    i++;
                }}
            }}, 800);
        </script>
    </body>
    </html>
    """)


@app.post("/api/admin/troll_ip")
async def api_admin_troll_ip(
    data: AdminTrollRequest, user: dict = Depends(get_required_user)
):
    """Включает режим ловушки для конкретного IP."""
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    # Валидация IP (базовая)
    try:
        ipaddress.ip_address(data.ip)
    except ValueError:
        raise HTTPException(400, "Invalid IP format")

    expires = time.time() + data.duration
    IP_TROLL_CONFIG[data.ip] = {"mode": data.mode, "expires": expires}

    # Также дублируем в основной бан-лист для веса
    IP_BAN_LIST[data.ip] = expires

    log_system_event(
        f"🪤 TROLL ENABLED: {data.ip} | Mode: {data.mode} | For: {data.duration // 60} min"
    )
    return {"status": "ok", "message": f"IP {data.ip} trapped in {data.mode} hell."}


@app.get("/api/admin/troll_list")
async def api_admin_troll_list(user: dict = Depends(get_required_user)):
    """Возвращает список текущих активных ловушек."""
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    now = time.time()
    active_traps = []
    for ip, cfg in list(IP_TROLL_CONFIG.items()):
        if cfg["expires"] > now:
            active_traps.append(
                {"ip": ip, "mode": cfg["mode"], "remaining": int(cfg["expires"] - now)}
            )
        else:
            del IP_TROLL_CONFIG[ip]

    return active_traps


@app.post("/api/admin/toggle_pow")
async def api_toggle_pow(
    data: PowToggleRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    val = "true" if data.enabled else "false"
    await set_system_setting("pow_enabled", val)
    status = "ON" if data.enabled else "OFF"
    log_system_event(f"🛡️ PoW SHIELD is now {status}")
    return {"status": "ok", "mode": status}


class AdminInspectUserRequest(BaseModel):
    user_id: int


@app.post("/api/admin/set_setting")
async def api_set_system_setting(
    data: SystemSettingRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    await set_system_setting(data.key, data.value)
    await get_setting_cached.cache_clear()
    return {"status": "ok"}


@app.get("/api/admin/get_setting")
async def api_get_system_setting(key: str, user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    val = await get_system_setting(key)
    return {"key": key, "value": val}


@app.get("/api/admin/firewall_status")
async def api_firewall_status(user: dict = Depends(get_required_user)):
    """Показывает текущие баны в оперативной памяти."""
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    now = time.time()
    # Показываем только активные баны
    active_bans = {
        ip: f"{int(exp - now)} сек" for ip, exp in IP_BAN_LIST.items() if exp > now
    }
    # Показываем подозрительных (у кого > 0 нарушений)
    suspicious = {ip: count for ip, count in BOT_VIOLATIONS.items() if count > 0}

    return {
        "banned_ips": active_bans,
        "suspicious_ips": suspicious,
        "total_banned": len(active_bans),
    }


class FirewallClearRequest(BaseModel):
    ip: Optional[str] = None


@app.post("/api/admin/firewall_clear")
async def api_firewall_clear(
    data: FirewallClearRequest, user: dict = Depends(get_required_user)
):
    """Снимает бан в памяти (без перезагрузки)."""
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")

    if data.ip:
        IP_BAN_LIST.pop(data.ip, None)
        BOT_VIOLATIONS.pop(data.ip, None)
        return {"status": "ok", "message": f"IP {data.ip} разбанен и очищен."}
    else:
        # Если IP не передан, чистим всё
        IP_BAN_LIST.clear()
        BOT_VIOLATIONS.clear()
        return {"status": "ok", "message": "ПОЛНЫЙ СБРОС ФАЕРВОЛА."}


@app.get("/api/admin/recent_posts")
async def api_admin_recent_posts(user: dict = Depends(get_required_user)):
    """Возвращает последние посты для Live Feed при загрузке."""
    if not check_perm(user, "janitor"):
        raise HTTPException(403, "Forbidden")

    posts = await get_recent_posts_global(30)
    result = []
    for p in posts:
        txt = p.get("content", {}).get("text", "")
        preview = (txt[:100] + "...") if len(txt) > 100 else txt
        if not preview and p.get("content", {}).get("files"):
            preview = "[Медиа файл]"

        result.append(
            {
                "id": p["id"],
                "board": p["board_id"],
                "text": preview,
                "time": datetime.fromtimestamp(p["timestamp"]).strftime("%H:%M:%S"),
                "author": str(p["author_id"]),
            }
        )
    return result


@app.post("/api/admin/inspect_user")
async def api_admin_inspect_user(
    data: AdminInspectUserRequest, user: dict = Depends(get_required_user)
):
    """Возвращает полное досье на юзера."""
    if not check_perm(user, "mod"):
        raise HTTPException(403, "Forbidden")

    info = await get_full_user_info(data.user_id)
    if not info:
        return {"found": False}
    info["user_hash"] = get_user_hash(info["user_id"])

    return {"found": True, "data": info}


@app.get("/api/admin/pow_status")
async def api_get_pow_status(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    val = await get_system_setting("pow_enabled")
    return {"enabled": val == "true"}


@app.get("/api/pow/challenge")
async def api_public_pow_challenge():
    """
    Отдает задачу клиенту.
    Если PoW выключен глобально, можно отдавать difficulty=0,
    но лучше проверять настройку.
    """
    val = await get_system_setting("pow_enabled")
    if val != "true":
        return {"challenge": "", "difficulty": 0}
    return get_pow_challenge_data()


@app.post("/api/admin/toggle_captcha")
async def api_toggle_captcha(
    data: dict = Body(...), user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    enabled = data.get("enabled", False)
    await set_system_setting("captcha_enabled", "true" if enabled else "false")
    log_system_event(f"🛡️ CAPTCHA is now {'ON' if enabled else 'OFF'}")
    return {"status": "ok", "enabled": enabled}


@app.get("/api/captcha/generate")
@limiter.limit("20/minute")
async def api_captcha_generate(request: Request):
    now = time.time()
    to_del = [k for k, v in CAPTCHA_SESSIONS.items() if v["expires"] < now]
    for k in to_del:
        del CAPTCHA_SESSIONS[k]
    captcha_id = secrets.token_hex(16)
    modes = [
        "monkey",
        "bottle",
        "math",
        "word",
        "escobar",
        "fan",
        "find_odd",
        "spank",
        "humiliation",
        "clock",
        "can",
        "major",
        "protocol",
    ]
    mode = random.choice(modes)
    session_data = {"mode": mode, "expires": now + 2000}
    response_data = {"captcha_id": captcha_id, "mode": mode}
    if mode == "monkey":
        container_w, container_h = 300, 150
        log_x = random.randint(50, container_w - 50)
        log_y = random.randint(20, container_h - 100)
        monkey_x = 0
        monkey_y = 0
        for _ in range(10):
            monkey_x = random.randint(10, container_w - 40)
            monkey_y = random.randint(10, container_h - 40)
            if abs(monkey_x - log_x) > 60:
                break
        session_data.update({"target_x": log_x, "target_y": log_y})
        response_data.update(
            {
                "log_x": log_x,
                "log_y": log_y,
                "monkey_x": random.randint(10, container_w - 40),
                "monkey_y": random.randint(10, container_h - 40),
            }
        )
    elif mode == "bottle":
        start_angle = random.randint(-170, 170)
        session_data.update({"start_angle": start_angle})
        response_data.update({"start_angle": start_angle})
    elif mode == "math":
        a, b = random.randint(1, 10), random.randint(1, 10)
        op = random.choice(["+", "-", "*"])
        ans = a + b if op == "+" else (a - b if op == "-" else a * b)
        options = {ans}
        while len(options) < 3:
            options.add(ans + random.randint(-5, 5))
        opts_list = list(options)
        random.shuffle(opts_list)
        session_data.update({"answer": ans})
        response_data.update({"question": f"{a} {op} {b} = ?", "options": opts_list})
    elif mode == "word":
        words = [
            ("Х", "У", "Й"),
            ("Л", "О", "Х"),
            ("А", "Б", "У"),
            ("Ч", "М", "О"),
            ("Б", "А", "Н"),
            ("Х", "Р", "Ю"),
            ("Z", "O", "V"),
            ("К", "Е", "К"),
            ("П", "У", "К"),
            ("Г", "Е", "Й"),
        ]
        word = random.choice(words)
        shuffled = list(word)
        random.shuffle(shuffled)
        session_data.update({"word": "".join(word)})
        response_data.update({"chars": shuffled})
    elif mode == "escobar":
        session_data.update({"type": "logic_puzzle"})
    elif mode == "fan":
        session_data.update({"type": "skill_check"})
    elif mode == "find_odd":
        trap_index = random.randint(0, 8)
        session_data.update({"trap_index": trap_index})
        response_data.update({"trap_index": trap_index})
    elif mode == "spank":
        required_slaps = random.randint(6, 12)
        session_data.update({"required_slaps": required_slaps})
        response_data.update({"hint": f"Отшлепай её! ({required_slaps} раз)"})
    elif mode == "humiliation":
        phrases = [
            "Я люблю члены",
            "Слава Украине",
            "Слава России",
            "Я дегенерат",
            "Абу хуесос",
            "Джулуп",
            "Перемога",
            "Админ пидор",
            "Админ хуйло",
            "Я бот",
            "Я не человек",
            "Я слабак",
            "Я ничтожество",
            "Абу говноед",
            "1488",
            "Петушиная масть",
            "Сасаю хуи",
            "Двач лучше",
            "Я сосал",
            "Я обосрался",
            "Да не скуф я",
            "Я пердикс",
            "Тгач круто",
            "Моя мама шлюха",
            "Ссал в рот админу",
            "Путин хуйло",
            "Двач говно",
            "Обоссы меня",
            "Я люблю ебаться",
            "Ебал я вашу мать",
            "Админ еблан",
            "Я пидор",
            "+15",
            "Нормально долбит",
            "Я анимешник",
            "Ахмат сила",
            "Кадыров пидорас",
            "Я люблю хуй",
            "Капча говно",
            "Капчу придумал пидор",
            "Ссу в рот админу",
            "Пойду посру",
            "Я тупой школьник",
            "Меня ебало семеро",
            "666",
            "228",
            "Всем привет",
            "Степан Бандера",
            "Гомосексуализм",
            "Две вагины",
            "Цп в лс",
            "Я русский",
            "Я хохол",
            "Труп бомжа",
            "Я люблю лоликон",
            "Прости меня",
            "Кадыров пидор",
            "Аллах акбар",
            "Я нищий",
            "Есть одна тян",
            "Гомонигры",
            "Донт вейв",
            "Лоликон",
            "Швайнокарась",
            "Контрнахрюк",
            "Опущенный",
            "У меня нет отца",
            "Я вырос в детдоме",
            "Выключи капчу",
            "Ебала жаба гадюку",
            "Я жалкое чмо",
            "Меня никто не любит",
            "Я хочу поесть говна",
            "Буду дрочить",
        ]
        phrase = random.choice(phrases)
        session_data.update({"phrase": phrase})
        response_data.update({"phrase": phrase})
    elif mode == "clock":
        h = random.randint(0, 11)
        m = random.randint(0, 11) * 5
        display_h = h if h > 0 else 12
        time_str = f"{display_h:02d}:{m:02d}"
        target_h_angle = (h * 30) + (m * 0.5)
        target_m_angle = m * 6
        session_data.update({"target_h": target_h_angle, "target_m": target_m_angle})
        response_data.update(
            {
                "display_time": time_str,
                "target_h": target_h_angle,
                "target_m": target_m_angle,
            }
        )
    elif mode == "can":
        session_data.update({"type": "skill_check"})
    elif mode == "major":
        user = request.session.get("user")
        if user and user.get("id"):
            user_id = str(user["id"])
        else:
            user_id = get_real_ip(request)
        random_post_num = random.randint(180000, 320999)
        response_data.update({"user_id": user_id, "post_num": random_post_num})
    elif mode == "protocol":
        random_post_num = random.randint(180000, 320999)
        response_data.update({"post_num": random_post_num})
    CAPTCHA_SESSIONS[captcha_id] = session_data
    return response_data


@app.get("/api/updates/{board_id}")
async def api_get_updates(board_id: str, since: float):
    safe_since = max(since, time.time() - 86400)
    raw_posts = await get_updates_since(board_id, safe_since)
    return _convert_and_enrich_posts(raw_posts)


@app.get("/api/admin/activity_stats")
async def api_admin_activity_stats(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    history = await get_activity_history(7)
    return {"history": history}


@app.get("/api/admin/mod_queue")
async def api_get_mod_queue(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    return await get_mod_queue()


class ModDecision(BaseModel):
    queue_id: int
    post_num: int
    action: str


@app.post("/api/admin/mod_decision")
async def api_mod_decision(data: ModDecision, user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    if data.action == "ban":
        post = await get_post_by_num(data.post_num)
        if post:
            await ban_user_on_board(post["author_id"], post["board_id"])
            await delete_post_by_num(data.post_num)
            log_system_event(f"🔨 NEURO-MOD BAN: Post #{data.post_num}")
    elif data.action == "delete":
        await delete_post_by_num(data.post_num)
        log_system_event(f"🗑️ NEURO-MOD DEL: Post #{data.post_num}")
    elif data.action == "ignore":
        pass
    await resolve_mod_queue(data.queue_id)
    return {"status": "ok"}


ADMIN_BROADCAST_QUEUE = asyncio.Queue()


@app.websocket("/ws/admin/feed")
async def admin_feed_websocket(websocket: WebSocket):
    user = websocket.session.get("user")
    if not user or not user.get("is_admin"):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, "admin_feed", "feed", "ru")
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(websocket, "admin_feed", "feed", "ru")


@app.get("/api/media-feed/{board_id}")
async def api_get_media_feed(
    board_id: str,
    request: Request,
    page: int = 1,
    user: dict = Depends(get_current_user_or_guest),
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    stream = getattr(request.state, "stream", "ru")
    observer_id = user["id"]
    raw_posts = await get_board_media_posts(
        board_id, page=page, page_size=20, stream=stream, observer_id=observer_id
    )
    posts = _convert_and_enrich_posts(raw_posts)
    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(posts, is_ru=is_ru)
    return posts


@app.get("/{board_id}/")
async def read_board_index_redirect(board_id: str):
    """
    Редирект с корня доски сразу на треды.
    """
    return RedirectResponse(url=f"/{board_id}/threads/")


@app.get("/{board_id}/mode/")
async def read_board_mode_select(
    board_id: str, request: Request, user: dict | None = Depends(get_optional_user)
):
    """
    Старый Board Hub (выбор режима).
    """
    board_id = board_id.lower()
    if SITE_ACCESS_MODE == "PRIVATE" and not user:
        return RedirectResponse(url="/login")
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    lang = getattr(request.state, "lang", "ru")
    local_boards = localize_boards(lang)
    board_info = BOARD_CONFIG[board_id]

    return templates.TemplateResponse(
        request=request,
        name="board_hub.jinja2",
        context={
            "request": request,
            "board_id": board_id,
            "boards": local_boards,
            "board_info": board_info,
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/img/random")
async def random_image_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="random_img.jinja2",
        context={
            "request": request,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "boards": BOARD_CONFIG,
        },
    )


@app.get("/api/img/next")
@limiter.limit("60/minute")
async def api_random_image_next(request: Request, boards: Optional[str] = None):
    try:
        allowed_boards = None
        if boards:
            allowed_boards = [b.strip() for b in boards.split(",") if b.strip()]

        deadline = time.monotonic() + RANDOM_API_DEADLINE_SEC
        for _ in range(8):
            if time.monotonic() >= deadline:
                break
            post_data = await get_random_image_post(allowed_boards=allowed_boards)

            if not post_data:
                return JSONResponse({"error": "No images found"}, status_code=404)

            if isinstance(post_data["content"], str):
                try:
                    post_data["content"] = json.loads(post_data["content"])
                except:
                    continue

            enriched_list = _convert_and_enrich_posts([post_data])
            post = enriched_list[0]

            target_file = None
            files = post["content"].get("files", [])

            idx = post.get("_selected_file_index")
            if idx is not None and 0 <= idx < len(files):
                target_file = files[idx]
            elif files:
                valid_media = [
                    f for f in files if f.get("type") in ["image", "photo", "sticker"]
                ]
                if valid_media:
                    target_file = random.choice(valid_media)

            if not target_file:
                continue

            file_id = target_file.get("original_file_id")
            if not await _is_random_file_available_with_deadline(file_id, deadline):
                continue

            src = target_file.get("original_url")

            return {
                "src": src,
                "file_id": file_id,
                "post_id": post["id"],
                "board_id": post["board_id"],
                "thread_id": post.get("thread_id") or post["id"],
                "type": target_file.get("type", "image"),
                "filename": target_file.get("filename", "file.jpg"),
                "is_censored": post["content"].get("is_censored", False),
            }

        return JSONResponse({"error": "No live images found"}, status_code=404)
    except Exception as e:
        logger.error(f"Random Image API Error: {e}")
        await asyncio.sleep(0.5)
        return JSONResponse({"error": "Server error"}, status_code=500)


@app.get("/archive/threads/")
async def archive_threads_view(
    request: Request, page: int = 1, user: dict | None = Depends(get_optional_user)
):
    if page < 1:
        page = 1
    limit = 20
    raw_posts = await get_archived_threads(page=page, page_size=limit + 1)
    has_next = len(raw_posts) > limit
    posts = raw_posts[:limit]
    posts = _convert_and_enrich_posts(posts)

    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(posts, is_ru=is_ru)
    return templates.TemplateResponse(
        request=request,
        name="archive_threads.jinja2",
        context={
            "request": request,
            "posts": posts,
            "page": page,
            "has_next": has_next,
            "site_mode": SITE_ACCESS_MODE,
        },
    )


@app.post("/makaba/posting.fcgi")
async def api_makaba_posting(
    request: Request,
    task: str = Form(...),
    board: str = Form(...),
    thread: str = Form(None),
    comment: str = Form(""),
    captcha_id: Optional[str] = Form(None),
    captcha_value: Optional[str] = Form(None),
    pow_nonce: Optional[str] = Form(None),
    pow_challenge: Optional[str] = Form(None),
    email: Optional[str] = Form(None),  # ДОБАВЛЕНО
    user: dict = Depends(get_current_user_or_guest),
):
    request_id = str(uuid.uuid4())[:8]
    local_logger = RequestIdAdapter(
        logging.getLogger(__name__), {"request_id": request_id}
    )
    t = request.state.t
    current_ts = time.time()

    if task != "post":
        return JSONResponse({"Error": "Unknown task", "Status": "Error"}, 400)
    if board not in BOARD_CONFIG:
        return JSONResponse({"Error": "Invalid board", "Status": "Error"}, 404)

    is_new_thread = not thread or thread == "0"
    reply_to = int(thread) if not is_new_thread else None
    post_mode = "new_thread" if is_new_thread else "reply"
    author_id = int(user["id"])
    thread_op_num = None

    is_guest = user.get("is_guest", False)
    is_trusted = not is_guest

    if post_mode == "reply" and reply_to:
        thread_op_num = await get_thread_op_by_post_num(reply_to)
        if not thread_op_num:
            return JSONResponse(
                {"Error": "Thread not found", "Status": "Error"}, status_code=404
            )
    if (await get_system_setting("pow_enabled")) == "true" and not is_trusted:
        if not verify_pow(pow_challenge, pow_nonce, DEFAULT_POW_DIFFICULTY):
            if len(POST_RATE_LIMITER) > 50:
                return JSONResponse(
                    {
                        "Error": t(
                            "pow_failed", "Ошибка защиты PoW. Попробуйте еще раз."
                        ),
                        "Status": "Error",
                    },
                    status_code=403,
                )
            else:
                local_logger.info(
                    f"🛡️ POW MERCY (Makaba): User {author_id} passed (Low load)"
                )

    if (await get_system_setting("captcha_enabled")) == "true" and not is_trusted:
        if not captcha_id or not CAPTCHA_SESSIONS.get(captcha_id):
            return JSONResponse(
                {"Error": t("captcha_expired"), "Status": "Error"}, status_code=403
            )
        del CAPTCHA_SESSIONS[captcha_id]

    limit_seconds = 60 if is_new_thread else 15
    action_key = "thread" if is_new_thread else "post"
    cooldown_key = f"cooldown_{board}_{author_id}_{action_key}"
    backend = FastAPICache.get_backend()
    last_post_time = await backend.get(cooldown_key)
    if last_post_time and (time.time() - float(last_post_time)) < limit_seconds:
        wait_time = int(limit_seconds - (time.time() - float(last_post_time))) + 1
        return JSONResponse(
            {"Error": f"Cooldown. Wait {wait_time}s.", "Status": "Error"},
            status_code=429,
        )

    lockdown_val = await get_system_setting("lockdown_enabled")
    if lockdown_val == "true" and not user.get("is_admin"):
        logger.info(f"🛡️ Lockdown check triggered for {author_id}")
        async with get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT MIN(created_at) FROM Users WHERE user_id = ?", (author_id,)
                )
            ).fetchone()
            created_at = row[0] if row and row[0] is not None else time.time()
            if (time.time() - created_at) < 86400 and not user.get("is_admin"):
                return JSONResponse(
                    {
                        "Error": "Lockdown mode active. New users restricted.",
                        "Status": "Error",
                    },
                    status_code=403,
                )

    if await get_user_status(author_id, board) == "banned":
        lang = getattr(request.state, "lang", "ru")
        msg = TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(
            "err_banned_board", "Banned"
        )
        return JSONResponse({"Error": msg, "Status": "Error"})

    form_data = await request.form()
    files_to_process = []
    for key in form_data:
        if key.startswith("image") or key.startswith("file") or key.startswith("video"):
            file_obj = form_data[key]
            if getattr(file_obj, "filename", None):
                files_to_process.append(file_obj)

    file_sig = [(f.filename, f.size) for f in files_to_process]
    content_hash = hashlib.md5(
        f"{comment}{board}{thread}{file_sig}".encode()
    ).hexdigest()
    idemp_key = f"idemp_mob_{author_id}_{content_hash}"
    if await backend.get(idemp_key):
        return JSONResponse(
            {"Error": t("post_dup"), "Status": "Error"}, status_code=429
        )
    await backend.set(idemp_key, "1", expire=15)
    if comment:
        comment = clean_zalgo(comment)
    stop_words = SPAM_WORDS_CACHE.get("all", set()) | SPAM_WORDS_CACHE.get(board, set())
    if any(word in (comment or "").lower() for word in stop_words):
        log_system_event(
            f"🛡️ SPAM BLOCKED (Makaba): User {author_id} tried to post stop-word."
        )
        await backend.set(cooldown_key, str(time.time()), expire=limit_seconds)
        return JSONResponse({"Error": "Spam detected", "Status": "Error"})

    files_data = []
    file_owners_to_save = []
    has_banned_content = False

    if files_to_process:
        if len(files_to_process) > 5:
            lang = getattr(request.state, "lang", "ru")
            msg = TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(
                "err_max_files_4", "Max 5 files"
            )
            return JSONResponse({"Error": msg, "Status": "Error"})

        stream = getattr(request.state, "stream", "ru")
        from common.config import STORAGE_CHANNELS

        target_channel_id = STORAGE_CHANNELS.get(stream, STORAGE_CHANNELS["ru"])

        async def upload_task(f):
            async with UPLOAD_SEMAPHORE:
                TELEGRAM_SINGLE_FILE_LIMIT = 50 * 1024 * 1024
                return await upload_with_bot_pool(
                    f,
                    stream,
                    target_channel_id,
                    TELEGRAM_SINGLE_FILE_LIMIT,
                    local_logger,
                )

        tasks = [upload_task(f) for f in files_to_process]
        upload_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in upload_results:
            if isinstance(res, Exception) or not res:
                continue

            res_data, uploader_id = res
            if not res_data:
                continue

            if res_data.get("banned"):
                has_banned_content = True
                continue

            if res_data.get("original_file_id"):
                oid = res_data["original_file_id"]
                res_data["original_url"] = f"/files/{oid}"

                if res_data.get("thumbnail_file_id"):
                    tid = res_data["thumbnail_file_id"]
                    res_data["thumbnail_url"] = f"/files/{tid}"
                file_owners_to_save.extend(
                    _file_owner_pairs_for_upload_result(res_data, uploader_id)
                )

                files_data.append(res_data)

    if not comment and not files_data:
        lang = getattr(request.state, "lang", "ru")
        msg = TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get("post_empty", "Empty post")
        return JSONResponse({"Error": msg, "Status": "Error"})

    content = {
        "text": comment,
        "files": files_data,
        "type": "files" if files_data else "text",
    }
    if email == "sage":
        content["sage"] = True

    is_shadow_muted = await get_shadow_mute_status(author_id, board)
    is_shadow_final = is_shadow_muted or has_banned_content

    new_post_num = await create_post(
        author_id=author_id,
        board_id=board,
        content=content,
        timestamp=current_ts,
        reply_to=reply_to,
        is_shadow_muted=is_shadow_final,
        is_from_site=True,
        post_mode=post_mode,
        stream=getattr(request.state, "stream", "ru"),
        thread_id_from_bot=str(thread_op_num) if thread_op_num else None,
        request_id_for_log=request_id,
        file_owners=file_owners_to_save,
    )

    if not new_post_num:
        return JSONResponse({"Error": "DB Error", "Status": "Error"})

    await backend.set(cooldown_key, str(time.time()), expire=limit_seconds)

    spawn_task(
        process_cross_links(
            board, new_post_num, comment, getattr(request.state, "stream", "ru")
        )
    )

    if not is_shadow_final:
        broadcast_post = await get_post_for_broadcast(new_post_num)
        if broadcast_post:
            await request.app.state.broadcast_queue.put(broadcast_post)

    if post_mode == "new_thread":
        title = content["text"][:100] or t("default_thread_title")
        await create_thread_entry(
            new_post_num,
            board,
            author_id,
            title,
            time.time(),
            stream=getattr(request.state, "stream", "ru"),
        )
        return {"Status": "OK", "Target": new_post_num, "Num": new_post_num}
    elif post_mode == "reply" and reply_to:
        thread_id = await get_thread_op_by_post_num(reply_to)
        if thread_id:
            await update_thread_last_updated(thread_id, time.time())
            spawn_task(process_backlinks(new_post_num, content["text"], reply_to))
            if board not in ["thread", "test"]:
                await process_mentions_and_notify(
                    new_post_num, board, content["text"], reply_to
                )

    return {"Status": "OK", "Num": new_post_num}


@app.get("/archive/chat/")
async def archive_chat_view(
    request: Request, page: int = 1, user: dict | None = Depends(get_optional_user)
):

    if page < 1:
        page = 1
    limit = 50
    raw_posts = await get_global_chat_posts(page=page, page_size=limit + 1)
    has_next = len(raw_posts) > limit
    posts = raw_posts[:limit]
    posts = _convert_and_enrich_posts(posts)

    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(posts, is_ru=is_ru)
    return templates.TemplateResponse(
        request=request,
        name="archive_chat.jinja2",
        context={
            "request": request,
            "posts": posts,
            "page": page,
            "has_next": has_next,
            "site_mode": SITE_ACCESS_MODE,
        },
    )


@app.post("/api/my-posts-content")
@limiter.limit("10/minute", key_func=get_user_id_from_session)
async def api_get_my_posts_content(request: Request, data: PostNumsRequest):
    """
    1. Защищен лимитом (10 раз в минуту на IP).
    2. Защищен КЭШЕМ (60 сек). Если юзер спамит F5, база данных НЕ трогается, ответ берется из памяти.
    """
    if not data.post_nums:
        return []
    unique_ids = sorted(list(set(data.post_nums)))[:200]
    if not unique_ids:
        return []
    ids_str = ",".join(map(str, unique_ids))
    cache_key = f"myposts_v2:{hashlib.md5(ids_str.encode()).hexdigest()}"
    backend = FastAPICache.get_backend()
    if backend:
        cached_data = await backend.get(cache_key)
        if cached_data:
            return orjson.loads(cached_data)
    from common.database import get_posts_batch

    posts = await get_posts_batch(unique_ids)
    posts = _convert_and_enrich_posts(posts)

    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(posts, is_ru=is_ru)
    if backend:
        await backend.set(cache_key, orjson.dumps(posts), expire=60)
    return posts


@app.get("/{board_id}/threads/")
async def read_board_threads(
    board_id: str,
    request: Request,
    sort: str = "bump",
    user: dict | None = Depends(get_optional_user),
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")

    # --- HYBRID DELIVERY SYSTEM ---
    user_agent = request.headers.get("user-agent", "").lower()
    # Список ботов, которым нужен SSR (Server-Side Rendering)
    bot_markers = [
        "bot",
        "crawl",
        "slurp",
        "spider",
        "mediapartners",
        "whatsapp",
        "telegram",
        "discord",
        "facebook",
        "pinterest",
    ]
    is_bot = any(marker in user_agent for marker in bot_markers)

    op_posts = []
    is_skeleton = False

    sort_mode = "new" if sort == "new" else "bump"
    stream = getattr(request.state, "stream", "ru")

    cache_key = f"bot_board_html:{board_id}:{sort_mode}:{stream}"
    if is_bot and not user:
        backend = FastAPICache.get_backend()
        if backend:
            cached = await backend.get(cache_key)
            if cached:
                return HTMLResponse(content=cached)

    if is_bot:
        # SSR для ботов: грузим данные сразу
        observer_id = user["id"] if user else getattr(request.state, "guest_id", 0)
        op_posts = await get_op_posts_for_board(
            board_id,
            sort_by=sort_mode,
            page=1,
            page_size=25,
            stream=request.state.stream,
            observer_id=observer_id,
        )
        op_posts = _convert_and_enrich_posts(op_posts)
        is_ru = await is_request_from_ru(request)
        await enrich_extra_data(op_posts, is_ru=is_ru)
        uid = observer_id
        for post in op_posts:
            if post.get("author_id") == uid:
                post["is_op"] = True
    else:
        # CSR для людей: отдаем скелет, JS подгрузит данные
        is_skeleton = True

    base_url = str(request.base_url).rstrip("/")
    meta_image = f"{base_url}/static/{random.choice(['logo.png', 'logo1.png'])}"

    context = {
        "request": request,
        "board_id": board_id,
        "boards": BOARD_CONFIG,
        "board_info": BOARD_CONFIG[board_id],
        "posts": op_posts,
        "BOT_USERNAME": BOT_USERNAME,
        "current_sort": sort_mode,
        "site_mode": SITE_ACCESS_MODE,
        "session": {"user": user},
        "meta_image": meta_image,
        "is_skeleton": is_skeleton,  # Флаг для шаблона
    }

    html_content = templates.get_template("board.jinja2").render(context)

    if is_bot and not user:
        backend = FastAPICache.get_backend()
        if backend:
            await backend.set(cache_key, html_content, expire=300)  # Кэш на 5 минут

    return HTMLResponse(content=html_content)


@app.get("/{board_id}/rss.xml")
async def get_rss_feed(board_id: str, request: Request):
    return await generate_rss(board_id, request)


@app.get("/{board_id}/chat/")
async def read_board_chat(
    board_id: str,
    request: Request,
    user: dict | None = Depends(get_current_user_or_guest),
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    observer_id = user["id"]
    chat_posts = await get_chat_posts_for_board(
        board_id, offset=0, stream=request.state.stream, observer_id=observer_id
    )

    return templates.TemplateResponse(
        request=request,
        name="chat.jinja2",
        context={
            "request": request,
            "board_id": board_id,
            "boards": BOARD_CONFIG,
            "board_info": BOARD_CONFIG[board_id],
            "posts": _convert_and_enrich_posts(chat_posts),
            "BOT_USERNAME": BOT_USERNAME,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        },
    )


@app.get("/{board_id}/res/")
async def read_res_root_redirect(board_id: str):
    """
    Редирект с папки /res/ (если юзер стер номер треда) обратно на доску.
    """
    return RedirectResponse(url=f"/{board_id}/threads/", status_code=301)


@app.get("/{board_id}/res/{post_num}.html")
async def read_thread(
    board_id: str,
    post_num: int,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    board_id = board_id.lower()
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")

    # ПРЕ-ВАЛИДАЦИЯ: Находим реальный ID треда (ОП-поста)
    real_thread_id = await get_thread_op_by_post_num(post_num)
    if not real_thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    # --- HYBRID DELIVERY ---
    user_agent = request.headers.get("user-agent", "").lower()
    bot_markers = [
        "bot",
        "crawl",
        "slurp",
        "spider",
        "mediapartners",
        "whatsapp",
        "telegram",
        "discord",
        "facebook",
        "pinterest",
    ]
    is_bot = any(marker in user_agent for marker in bot_markers)

    op_post = None
    replies = []
    is_skeleton = False

    if is_bot:
        # SSR: Полный рендеринг для ботов по real_thread_id
        user_id = user["id"] if user else None
        thread_data = await get_thread_by_op_post(
            real_thread_id, current_user_id=user_id
        )
        if not thread_data:
            raise HTTPException(status_code=404, detail="Thread not found")
        op_post, replies = thread_data

        full_list = _convert_and_enrich_posts([op_post] + replies)
        is_ru = await is_request_from_ru(request)
        await enrich_extra_data(full_list, is_ru=is_ru)

        op_post = full_list[0]
        replies = full_list[1:]

        if user_id:
            user_hash = get_user_hash(user_id)
            if op_post.get("author_id") == user_hash:
                op_post["is_op_yours"] = True
            for reply in replies:
                if reply.get("author_id") == user_hash:
                    reply["is_yours"] = True
    else:
        # CSR: Скелет для людей. Используем post_num из URL для правильной прокрутки JS-ом
        is_skeleton = True
        op_post = {
            "id": real_thread_id,
            "content": {"text": f"Загрузка треда #{real_thread_id}...", "files": []},
            "timestamp": time.time(),
            "author_id": 0,
            "is_pinned": False,
            "is_endless": False,
            "is_archived": False,
            "reply_count": 0,
            "anon_count": 0,
        }
        replies = []

    stream = getattr(request.state, "stream", "ru")
    # Кэширование HTML только для анонимов и ботов (SSR)
    # Для скелета кэш не нужен (он и так легкий)
    cache_key = f"thread_html:{board_id}:{post_num}:{stream}"

    if not user and not is_skeleton:
        backend = FastAPICache.get_backend()
        if backend:
            cached = await backend.get(cache_key)
            if cached:
                return HTMLResponse(content=cached)

    # ... Мета-данные ...
    raw_text = op_post.get("content", {}).get("text", "")
    meta_desc = clean_title_text(raw_text)[:200]
    if not meta_desc:
        meta_desc = f"Тред #{post_num} в разделе /{board_id}/"

    base_url = str(request.base_url).rstrip("/")
    meta_image = ""
    files = op_post.get("content", {}).get("files", [])
    if files:
        f = files[0]
        rel_url = f.get("thumbnail_url") or f.get("original_url")
        if rel_url:
            if rel_url.startswith("http"):
                meta_image = rel_url
            else:
                meta_image = f"{base_url}{rel_url}"
    if not meta_image:
        meta_image = f"{base_url}/static/{random.choice(['logo.png', 'logo1.png'])}"

    thread_type_val = op_post.get("thread_type", "default")
    is_unlocked = True
    is_archived_val = op_post.get("is_archived", False)

    if not is_skeleton and not is_bot:
        pass
    elif is_skeleton:
        pass

    context = {
        "request": request,
        "board_id": board_id,
        "boards": BOARD_CONFIG,
        "board_info": BOARD_CONFIG[board_id],
        "op_post": op_post,
        "replies": replies,
        "BOT_USERNAME": BOT_USERNAME,
        "is_archived": is_archived_val,
        "site_mode": SITE_ACCESS_MODE,
        "session": {"user": user},
        "thread_type": thread_type_val,
        "is_unlocked": is_unlocked,
        "meta_description": meta_desc,
        "meta_image": meta_image,
        "is_skeleton": is_skeleton,
    }
    html_content = templates.get_template("thread.jinja2").render(context)

    if not user and not is_skeleton:
        backend = FastAPICache.get_backend()
        if backend:
            await backend.set(cache_key, html_content, expire=300)

    return HTMLResponse(content=html_content)


@app.get("/{board_id}/res/{post_num}/export")
async def export_thread_html(board_id: str, post_num: int):
    board_id = board_id.lower()
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")

    real_thread_id = await get_thread_op_by_post_num(post_num)
    if not real_thread_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread_data = await get_thread_by_op_post(real_thread_id)
    if not thread_data:
        raise HTTPException(status_code=404, detail="Thread not found")
    op_post, replies = thread_data

    op_post = _convert_and_enrich_posts([op_post])[0]
    replies = _convert_and_enrich_posts(replies)

    import datetime

    def format_ts(ts):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='ru'>")
    html.append("<head>")
    html.append("<meta charset='UTF-8'>")
    html.append(
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    )
    html.append(f"<title>Архив треда #{real_thread_id} - /{board_id}/</title>")
    html.append("""
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0d0f12;
            color: #c9d1d9;
            margin: 0;
            padding: 20px;
            line-height: 1.5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        header {
            border-bottom: 1px dashed #21262d;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }
        h1 {
            margin: 0;
            font-size: 1.8em;
            color: #ff9900;
        }
        .post {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .post.op-post {
            border-color: #ff9900;
        }
        .post-header {
            font-size: 0.85em;
            color: #8b949e;
            margin-bottom: 10px;
            border-bottom: 1px solid #21262d;
            padding-bottom: 5px;
        }
        .post-header strong {
            color: #ff9900;
        }
        .post-content {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .post-text {
            word-break: break-word;
        }
        .post-files-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 10px;
        }
        .file-thumb img, .file-thumb video {
            max-width: 200px;
            max-height: 200px;
            border-radius: 4px;
            border: 1px solid #30363d;
        }
        .reply-indicator {
            font-size: 0.85em;
            color: #58a6ff;
            margin: 0 0 5px 0;
        }
    </style>
    """)
    html.append("</head>")
    html.append("<body>")
    html.append("<div class='container'>")
    html.append("<header>")
    html.append(f"<h1>Тред #{real_thread_id} (Раздел /{board_id}/)</h1>")
    html.append(
        f"<p style='color:#8b949e;'>Сохранено из архива ТГАЧ. Всего постов: {len(replies) + 1}</p>"
    )
    html.append("</header>")

    # OP post
    html.append("<div class='post op-post'>")
    op_headers = f"<div class='post-header'>Анон #<strong>{op_post.get('id')}</strong> ({format_ts(op_post.get('timestamp', 0))})</div>"
    html.append(op_headers)
    html.append("<div class='post-content'>")

    if op_post.get("content", {}).get("files"):
        html.append("<div class='post-files-container'>")
        for f in op_post["content"]["files"]:
            html.append(
                f"<a href='{f.get('original_url')}' class='file-thumb' target='_blank'>"
            )
            html.append(
                f"<img src='{f.get('thumbnail_url') or f.get('original_url')}' alt='file'>"
            )
            html.append("</a>")
        html.append("</div>")

    html.append(
        f"<div class='post-text'>{op_post.get('content', {}).get('text', '')}</div>"
    )
    html.append("</div></div>")

    # Replies
    for post in replies:
        html.append("<div class='post'>")
        rep_headers = f"<div class='post-header'>Анон #<strong>{post.get('id')}</strong> ({format_ts(post.get('timestamp', 0))})</div>"
        html.append(rep_headers)
        html.append("<div class='post-content'>")

        if post.get("reply_to_post_num"):
            html.append(
                f"<p class='reply-indicator'>&gt;&gt;{post.get('reply_to_post_num')}</p>"
            )

        if post.get("content", {}).get("files"):
            html.append("<div class='post-files-container'>")
            for f in post["content"]["files"]:
                html.append(
                    f"<a href='{f.get('original_url')}' class='file-thumb' target='_blank'>"
                )
                html.append(
                    f"<img src='{f.get('thumbnail_url') or f.get('original_url')}' alt='file'>"
                )
                html.append("</a>")
            html.append("</div>")

        html.append(
            f"<div class='post-text'>{post.get('content', {}).get('text', '')}</div>"
        )
        html.append("</div></div>")

    html.append("</div>")
    html.append("</body>")
    html.append("</html>")

    headers = {
        "Content-Disposition": f"attachment; filename=thread-{board_id}-{real_thread_id}.html"
    }
    return Response(content="\n".join(html), media_type="text/html", headers=headers)


@app.get("/{board_id}/res/{post_num}/gallery")
async def thread_gallery_page(
    board_id: str,
    post_num: int,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    # Кеш HTML для анонимов на 10 сек (галерея тяжелая — много файлов)
    if not user:
        _gcache_key = f"gallery_html:{board_id}:{post_num}"
        _gbackend = FastAPICache.get_backend()
        if _gbackend:
            _gcached = await _gbackend.get(_gcache_key)
            if _gcached:
                return HTMLResponse(content=_gcached)
    media_posts_raw = await get_all_media_from_thread(post_num)
    media_posts = _convert_and_enrich_posts(media_posts_raw)
    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(media_posts, is_ru=is_ru)
    html_content = templates.get_template("gallery.jinja2").render(
        {
            "request": request,
            "board_id": board_id,
            "boards": BOARD_CONFIG,
            "op_post_num": post_num,
            "media_posts": media_posts,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
        }
    )
    if not user:
        _gbackend = FastAPICache.get_backend()
        if _gbackend:
            await _gbackend.set(_gcache_key, html_content, expire=10)
    return HTMLResponse(content=html_content)


@app.get("/{board_id}/catalog/")
async def read_board_catalog(
    board_id: str, request: Request, user: dict | None = Depends(get_optional_user)
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    user_agent = request.headers.get("user-agent", "").lower()
    bot_markers = [
        "bot",
        "crawl",
        "slurp",
        "spider",
        "mediapartners",
        "whatsapp",
        "telegram",
        "discord",
        "facebook",
        "pinterest",
    ]
    is_bot = any(marker in user_agent for marker in bot_markers)

    threads = []
    is_skeleton = False
    current_sort = request.query_params.get("sort", "bump")

    if is_bot:
        observer_id = user["id"] if user else getattr(request.state, "guest_id", 0)
        raw = await get_op_posts_for_board(
            board_id,
            sort_by=current_sort,
            page=1,
            page_size=100,
            stream=request.state.stream,
            observer_id=observer_id,
        )
        threads = _convert_and_enrich_posts(raw)
        is_ru = await is_request_from_ru(request)
        await enrich_extra_data(threads, is_ru=is_ru)
    else:
        is_skeleton = True

    return templates.TemplateResponse(
        request=request,
        name="catalog.jinja2",
        context={
            "request": request,
            "board_id": board_id,
            "boards": BOARD_CONFIG,
            "board_info": BOARD_CONFIG[board_id],
            "threads": threads,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "is_skeleton": is_skeleton,
            "current_sort": current_sort,
        },
    )


@app.get("/api/meta")
@cache(expire=9000)
async def api_get_meta(url: str):
    # 1. Базовая проверка протокола
    if not url.startswith(("http://", "https://")):
        return JSONResponse({}, status_code=400)

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (80 if parsed.scheme == "http" else 443)

        # 2. Ограничение портов (только стандартные для веба)
        if port not in (80, 443):
            return JSONResponse({"error": "Forbidden port"}, status_code=400)

        # 3. Глубокая проверка IP (Защита от SSRF)
        # Резолвим имя хоста в IP
        addr_info = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM
            ),
        )

        for item in addr_info:
            ip_str = item[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            # Блокируем приватные сети (10.x, 172.x, 192.x), петли (127.x),
            # линк-локальные (169.254.x) и прочие системные адреса
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
            ):
                logger.warning(f"🚨 SSRF ATTEMPT BLOCKED: {hostname} -> {ip_str}")
                return JSONResponse(
                    {"error": "Access to local/private network is forbidden"},
                    status_code=403,
                )

    except Exception as e:
        logger.error(f"Meta validation error for {url}: {e}")
        return JSONResponse({}, status_code=400)

    # Дальнейшая логика запросов (strategies) остается без изменений
    strategies = [
        {"proxy": PROXY_URL, "name": "Proxy"},
        {"proxy": None, "name": "Direct"},
    ]

    for strategy in strategies:
        try:
            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(
                timeout=5.0,
                verify=False,
                proxy=strategy["proxy"],
                transport=transport,
                trust_env=True,  # Важно для подхвата системного VPN
            ) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        continue
                    chunks = []
                    downloaded = 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        downloaded += len(chunk)
                        if downloaded > 1024 * 1024:  # 1MB limit
                            break

                    raw_html = b"".join(chunks).decode("utf-8", errors="ignore")

                # Если скачали успешно, парсим и возвращаем
                loop = asyncio.get_running_loop()
                soup = await loop.run_in_executor(
                    None, BeautifulSoup, raw_html, "html.parser"
                )
                title = soup.find("meta", property="og:title")
                image = soup.find("meta", property="og:image")
                desc = soup.find("meta", property="og:description")
                return {
                    "title": (
                        title["content"]
                        if title
                        else soup.title.string if soup.title else url
                    ),
                    "image": image["content"] if image else None,
                    "description": desc["content"][:100] + "..." if desc else None,
                    "url": url,
                }
        except Exception:
            continue  # Пробуем следующий метод

    return {}


@app.get("/api/my-alerts")
async def api_get_my_alerts(
    request: Request, user: dict = Depends(get_current_user_or_guest)
):
    """
    Проверяет наличие всплывающих уведомлений для текущего пользователя.
    Учитывает доску (чтобы показывать алерты только в нужном разделе).
    """
    referer = request.headers.get("referer", "")
    current_board = "main"
    match = re.search(r"/([a-z0-9]+)/", referer)
    if match:
        current_board = match.group(1)
    alerts = await get_pending_alerts(int(user["id"]), current_board)
    return alerts


class BoardRequest(BaseModel):
    board_id: str
    name: str
    description: str


@app.post("/api/board/request")
async def api_request_board(
    data: BoardRequest, user: dict = Depends(get_required_user)
):
    if not re.match(r"^[a-z0-9]{2,10}$", data.board_id):
        raise HTTPException(400, "ID доски должен быть 2-10 символов (a-z, 0-9).")
    if data.board_id in BOARD_CONFIG:
        raise HTTPException(400, "Такая доска уже есть.")
    is_approved = 1 if user.get("is_admin") else 0
    if await create_board(
        data.board_id, data.name, data.description, user["id"], is_approved
    ):
        if is_approved:
            BOARD_CONFIG[data.board_id] = {
                "name": data.name,
                "description": data.description,
            }
            localize_boards.cache_clear()
        status = "Создана!" if is_approved else "Отправлена на проверку!"
        return {"status": "ok", "message": status}
    raise HTTPException(500, "Ошибка БД (возможно ID занят)")


@app.get("/api/admin/boards")
async def api_admin_get_boards(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    return await get_all_boards_for_admin()


class BoardAction(BaseModel):
    board_id: str


@app.post("/api/admin/toggle_neuro")
async def api_set_neuro_status(
    data: NeuroToggleRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    val = "true" if data.enabled else "false"
    await set_system_setting("neuro_enabled", val)
    status = "ON" if data.enabled else "OFF"
    log_system_event(f"🤖 NEURO-POSTER is now {status}")
    return {"status": "ok", "mode": status}


@app.get("/api/admin/neuro_status")
async def api_get_neuro_status(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    val = await get_system_setting("neuro_enabled")
    return {"enabled": val == "true"}


@app.get("/api/admin/scanner_status")
async def api_get_scanner_status(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    enabled = await get_system_setting("neuro_scanner_enabled") == "true"
    interval = await get_system_setting("neuro_scanner_interval")
    try:
        interval = int(interval)
    except:
        interval = 60
    return {"enabled": enabled, "interval": interval}


@app.post("/api/admin/configure_scanner")
async def api_config_scanner(
    data: NeuroScannerConfigRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    await set_system_setting(
        "neuro_scanner_enabled", "true" if data.enabled else "false"
    )

    safe_interval = max(10, min(1440, data.interval))
    await set_system_setting("neuro_scanner_interval", str(safe_interval))

    status = "ON" if data.enabled else "OFF"
    log_system_event(
        f"🕵️ NEURO-SCANNER config: {status}, check every {safe_interval} min"
    )

    # Если включили - будим воркер мгновенно
    if data.enabled:
        SCANNER_TRIGGER.set()

    return {"status": "ok", "enabled": data.enabled, "interval": safe_interval}


@app.post("/api/admin/board/approve")
async def api_admin_approve_board(
    data: BoardAction, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    await approve_board(data.board_id)
    BOARD_CONFIG[data.board_id] = {
        "name": f"/{data.board_id}/",
        "description": "User Board",
    }
    localize_boards.cache_clear()
    return {"status": "approved"}


@app.post("/api/admin/board/delete")
async def api_admin_delete_board(
    data: BoardAction, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    await delete_board(data.board_id)
    if data.board_id in BOARD_CONFIG:
        del BOARD_CONFIG[data.board_id]
    localize_boards.cache_clear()
    return {"status": "deleted"}


@app.post("/api/admin/move_thread")
async def api_admin_move_thread(
    request: Request, data: MoveThreadRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(status_code=403, detail="Нужен ранг Moderator")
    if data.target_board not in BOARD_CONFIG:
        raise HTTPException(status_code=400, detail="Такой доски нет")

    from common.database import move_thread_to_board

    success = await move_thread_to_board(data.thread_id, data.target_board)

    if success:
        log_system_event(
            f"🚚 MOVE: Thread {data.thread_id} moved to /{data.target_board}/ by {user['id']}"
        )
        # Локализуем ответ
        t = request.state.t
        return {
            "status": "ok",
            "message": t("msg_move_success").format(data.target_board),
        }
    else:
        raise HTTPException(status_code=500, detail="Ошибка переноса (тред не найден?)")


@app.post("/api/admin/inspect_post")
async def api_admin_inspect(
    data: AdminInspectRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    from common.database import get_post_details_for_admin

    info = await get_post_details_for_admin(data.post_num)
    if not info:
        return {"found": False}
    user_hash = get_user_hash(info["author_id"])
    return {"found": True, "data": info, "user_hash": user_hash}


class ShadowWipeRequest(BaseModel):
    user_id: int
    scope: str = "current"
    board_id: str


@app.post("/api/admin/shadow_wipe_user")
async def api_admin_shadow_wipe(
    data: ShadowWipeRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    from common.database import shadow_wipe_user

    target_board = data.board_id if data.scope == "current" else "ALL"
    count = await shadow_wipe_user(data.user_id, target_board)
    log_system_event(
        f"🧛 SHADOW WIPE: User {data.user_id} on {target_board} ({count} posts)"
    )
    return {"status": "ok", "count": count, "scope": target_board}


@app.get("/api/server/pulse")
@alru_cache(maxsize=1, ttl=60)
async def api_server_pulse():

    if not psutil:
        return {}
    stats = {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
    }
    try:
        temps = psutil.sensors_temperatures()
        for name, entries in temps.items():
            if name.lower() in ["coretemp", "cpu_thermal", "k10temp", "zenpower"]:
                stats["temp"] = entries[0].current
                break
    except:
        pass
    return stats


@app.post("/api/settings/stream")
async def api_set_stream(
    data: StreamChangeRequest,
    response: Response,
    user: dict = Depends(get_current_user_or_guest),
):
    """
    Меняет поток (язык) пользователя.
    Ставит куку 'stream' и сохраняет выбор в БД (если юзер не гость).
    """
    if data.stream not in ["ru", "en", "jp"]:
        raise HTTPException(400, "Invalid stream. Allowed: ru, en, jp")
    if not user.get("is_guest"):
        await set_user_stream(int(user["id"]), "b", data.stream)
    json_response = JSONResponse({"status": "ok", "stream": data.stream})
    json_response.set_cookie(
        key="stream", value=data.stream, max_age=31536000, httponly=True, samesite="lax"
    )
    return json_response


@app.post("/api/audio/process")
@limiter.limit("5/minute", key_func=get_user_id_from_session)
async def api_process_audio(
    request: Request, effect: str = Form(...), file: UploadFile = File(...)
):
    if UPLOAD_SEMAPHORE.locked():
        raise HTTPException(status_code=503, detail="Server busy, try later")
    input_path = ""
    output_path = ""
    async with UPLOAD_SEMAPHORE:
        if effect == "none":
            return Response(await file.read(), media_type="audio/ogg")
        af_filter = get_audio_filter(effect)
        if not af_filter:
            return Response(await file.read(), media_type="audio/ogg")
        input_path = await copy_fileobj_to_temp_async(file.file, suffix=".ogg")
    output_path = input_path + "_processed.ogg"
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-af",
            af_filter,
            "-c:a",
            "libvorbis",
            "-f",
            "ogg",
            output_path,
        ]
        await run_process_checked(cmd, timeout=20)
        processed_data = await read_file_bytes_async(output_path)
        resp = Response(processed_data, media_type="audio/ogg")
        resp.headers["Content-Encoding"] = "identity"
        return resp
    except asyncio.TimeoutError:
        logger.error("FFmpeg timed out processing uploaded audio")
        return Response(await read_file_bytes_async(input_path), media_type="audio/ogg")
    except AsyncProcessError:
        logger.error("FFmpeg failed processing uploaded audio")
        return Response(await read_file_bytes_async(input_path), media_type="audio/ogg")
    finally:
        await remove_files_best_effort_async((input_path, output_path))


@app.post("/api/my-alerts/read")
async def api_read_alert(
    data: dict = Body(...), user: dict = Depends(get_current_user_or_guest)
):

    alert_id = data.get("alert_id")
    if alert_id:
        await mark_alert_read(int(alert_id))
    return {"status": "ok"}


@app.post("/api/op/moderate")
@limiter.limit("20/minute", key_func=get_user_id_from_session)
async def api_op_moderate(
    data: OpModRequest,
    request: Request,
    user: dict = Depends(get_current_user_or_guest),
):
    target_post = await get_post_by_num(data.post_num)
    if not target_post:
        raise HTTPException(404, "Post not found")
    thread_id = target_post.get("thread_id") or target_post.get("id")
    op_post = await get_post_by_num(int(thread_id))
    if not op_post:
        raise HTTPException(404, "Thread not found")
    op_author_id = op_post["author_id"]
    requestor_id = int(user["id"])
    if requestor_id != op_author_id and not user.get("is_admin"):
        raise HTTPException(403, "Вы не ОП этого треда")
    if int(data.post_num) == int(thread_id):
        raise HTTPException(400, "Нельзя скрыть ОП-пост")
    await toggle_op_hidden(data.post_num, data.action == "hide")
    updated_post = await get_post_for_broadcast(data.post_num)
    if updated_post:
        await request.app.state.broadcast_queue.put(updated_post)
    return {"status": "ok"}


class AdminAlertRequest(BaseModel):
    user_id: int
    content: str
    image_url: Optional[str] = None
    btn_text: Optional[str] = None
    btn_link: Optional[str] = None
    target_board: str = "all"


@app.post("/api/feedback")
@limiter.limit("2/minute", key_func=get_user_id_from_session)
async def api_send_feedback(
    request: Request,
    data: FeedbackRequestModel,
    bg_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_or_guest),
):
    if len(data.message) > 2000:
        raise HTTPException(400, "Too long")
    uid = int(user["id"])
    success = await create_feedback(uid, data.category, data.contact, data.message)
    if success:
        notify_text = (
            f"📬 <b>Фидбек с сайта!</b>\n\n"
            f"👤 <b>User:</b> <code>{uid}</code>\n"
            f"📂 <b>Категория:</b> {html.escape(data.category)}\n"
            f"📧 <b>Связь:</b> {html.escape(data.contact or 'Нет')}\n\n"
            f"💬 <b>Текст:</b>\n{html.escape(data.message)}"
        )
        bg_tasks.add_task(
            notify_admins, request.app.state.file_uploader_bot, notify_text
        )
        return {"status": "ok"}
    raise HTTPException(500, "Save error")


@app.post("/api/admin/send_alert")
async def api_admin_send_alert(
    data: AdminAlertRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    await create_alert(
        data.user_id,
        data.content,
        data.image_url,
        data.btn_text,
        data.btn_link,
        data.target_board,
    )
    log_system_event(f"🔔 ALERT: Sent to user {data.user_id}")
    return {"status": "sent"}


@app.post("/api/admin/force_neuro")
async def api_force_neuro(
    data: NeuroForceRequest, request: Request, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    from site_tgach.neuro_poster import BOARD_SETTINGS

    settings = BOARD_SETTINGS.get(data.board_id)
    if not settings:
        settings = {
            "style": "schizo, random, 4chan style, chaotic",
            "allow_new_threads": True,
            "enabled": True,
        }

    try:
        result_log = await request.app.state.neuro_manager.make_post(
            data.board_id, settings=settings, stream=data.stream, forced_mode=data.mode
        )
        return {"status": "ok", "log": result_log}
    except Exception as e:
        logger.error(f"Manual neuro error: {e}")
        return {"status": "error", "log": str(e)}


@app.post("/api/admin/restore_thread")
async def api_admin_restore_thread(
    data: AdminRestoreRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    await restore_thread_from_archive(data.thread_id)
    log_system_event(f"⚡ RESTORE: Thread {data.thread_id} restored by admin")
    return {"status": "ok"}


@app.post("/api/admin/set_announcement")
async def api_set_announcement(
    data: SystemAnnouncementRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    await set_system_setting("global_announcement", data.text)
    return {"status": "ok"}


@app.get("/api/admin/get_announcement")
async def api_get_announcement(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    text = await get_system_setting("global_announcement")
    return {"text": text}


class SetRoleRequest(BaseModel):
    user_id: int
    role: str


@app.post("/api/admin/pin_thread")
async def api_admin_pin_thread(
    data: AdminPinRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(status_code=403, detail="Нужен ранг Moderator")
    await toggle_thread_pin(data.thread_id, data.pinned)
    log_system_event(
        f"📌 PIN: Thread {data.thread_id} is now {'pinned' if data.pinned else 'unpinned'}"
    )
    return {"status": "ok"}


@app.post("/api/admin/toggle_blur")
async def api_admin_toggle_blur(
    data: ToggleBlurRequest, request: Request, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(status_code=403, detail="Нужен ранг Moderator")

    new_state = await toggle_post_censorship(data.post_num)

    # Сброс кэша для этого поста, чтобы пользователи сразу увидели изменения
    from fastapi_cache import FastAPICache

    await FastAPICache.clear(namespace="main", key=f"api_get_post:{data.post_num}")

    # Если это ОП-пост, сбрасываем кэш треда
    post_data = await get_post_by_num(data.post_num)
    if post_data:
        board_id = post_data.get("board_id")
        thread_id = post_data.get("thread_id")
        if board_id and thread_id:
            for stream in ["ru", "en", "jp"]:
                # Сброс кэша HTML страницы треда
                await FastAPICache.clear(
                    namespace="main", key=f"thread_html:{board_id}:{thread_id}:{stream}"
                )
                # Сброс кэша JSON API треда (версия в ключе меняется временем, но для надежности можно и так)
                # Однако версии досок обновляются в queue_listener, который сработает ниже через broadcast

    # Отправляем обновление через вебсокеты (это также обновит версии досок/тредов в queue_listener)
    updated_post = await get_post_for_broadcast(data.post_num)
    if updated_post:
        await request.app.state.broadcast_queue.put(updated_post)

    log_system_event(
        f"🌫️ CENSOR: Post #{data.post_num} censorship set to {new_state} by {user['id']}"
    )
    return {"status": "ok", "is_censored": new_state}


@app.post("/api/admin/set_banner")
async def api_admin_set_banner(
    data: BoardBannerRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "admin"):
        raise HTTPException(status_code=403, detail="Нужен ранг Admin")

    banner_json = json.dumps({"img": data.image_url, "link": data.link_url})

    # Импортируем лок
    from common.db_pool import get_pool, db_lock

    async with db_lock:
        try:
            db = await get_pool()
            await db.execute("BEGIN IMMEDIATE")

            await db.execute(
                "UPDATE Boards SET banner_data = ? WHERE board_id = ?",
                (banner_json, data.board_id),
            )

            await db.execute("COMMIT")
        except Exception as e:
            try:
                await db.execute("ROLLBACK")
            except:
                pass
            logger.error(f"Banner update error: {e}")
            raise HTTPException(status_code=500, detail="DB Error")

    if data.board_id in BOARD_CONFIG:
        BOARD_CONFIG[data.board_id]["banner_data"] = {
            "img": data.image_url,
            "link": data.link_url,
        }

    # Сбрасываем кэш локализации, чтобы новый баннер отобразился у всех
    localize_boards.cache_clear()

    log_system_event(f"🖼️ BANNER: Updated for /{data.board_id}/")
    return {"status": "ok"}


@app.post("/api/admin/set_role")
async def api_admin_set_role(
    data: SetRoleRequest, request: Request, user: dict = Depends(get_required_user)
):
    if user["id"] not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Only Root Admin can set roles")
    if data.role not in ["admin", "mod", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    await set_user_role(data.user_id, data.role)
    log_system_event(f"👑 ROLE: User {data.user_id} is now {data.role}")
    return {"status": "ok", "role": data.role}


@app.post("/api/admin/stealth_edit")
async def api_admin_stealth_edit(
    request: Request,
    post_num: int = Form(...),
    text: str = Form(...),
    delete_files: Optional[str] = Form(None),
    new_images: List[UploadFile] = File(None),
    user: dict = Depends(get_required_user),
):
    if not check_perm(user, "admin"):
        raise HTTPException(status_code=403, detail="Нужен ранг Admin")
    post = await get_post_by_num(post_num)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    content = post.get("content", {})
    current_files = content.get("files", [])

    file_owners_to_save = []

    if delete_files:
        try:
            indices_to_delete = set(json.loads(delete_files))
            current_files = [
                f for i, f in enumerate(current_files) if i not in indices_to_delete
            ]
        except json.JSONDecodeError:
            pass
    if new_images:
        if post.get("board_id") == "wh40k":
            processed_images_list = []
            for img in new_images:
                if (
                    img.filename
                    and img.content_type
                    and img.content_type.startswith("image/")
                ):
                    try:
                        await img.seek(0)
                        raw = await img.read()
                        from site_tgach.image_processing import (
                            apply_grimdark_filter_async,
                        )

                        processed = await apply_grimdark_filter_async(raw)

                        img.file.seek(0)
                        img.file.truncate(0)
                        img.file.write(processed)
                        img.file.seek(0)
                        if hasattr(img, "size"):
                            img.size = len(processed)
                        processed_images_list.append(img)
                    except Exception as e:
                        logger.error(f"WH40k Stealth Filter Error: {e}")
                        processed_images_list.append(img)
                else:
                    processed_images_list.append(img)
            new_images = processed_images_list

        stream = getattr(request.state, "stream", "ru")
        for file_obj in new_images:
            if not file_obj.filename:
                continue
            try:
                res_data, u_bot_id = await upload_with_bot_pool(
                    file_obj, stream, FILE_STORAGE_CHANNEL_ID, 29 * 1024 * 1024, logger
                )
                if res_data:
                    if res_data.get("banned"):
                        continue

                    if res_data.get("original_file_id"):
                        res_data["original_url"] = (
                            f"/files/{res_data['original_file_id']}"
                        )
                    if res_data.get("thumbnail_file_id"):
                        res_data["thumbnail_url"] = (
                            f"/files/{res_data['thumbnail_file_id']}"
                        )
                    owner_pairs = _file_owner_pairs_for_upload_result(
                        res_data, u_bot_id
                    )
                    for file_id, owner_bot_id in owner_pairs:
                        await register_file_owner(file_id, owner_bot_id)
                    file_owners_to_save.extend(owner_pairs)
                    current_files.append(res_data)
            except Exception as e:
                logger.error(f"Error processing image in stealth_edit: {e}")

    content["text"] = clean_zalgo(text or "")

    content["files"] = current_files
    content["type"] = "files" if current_files else "text"
    await update_post_content(post_num, content)

    from fastapi_cache import FastAPICache

    await FastAPICache.clear(namespace="main", key=f"api_get_post:{post_num}")

    thread_id = post.get("thread_id") or post.get("id")
    board_id = post.get("board_id")
    if thread_id and board_id:
        for stream in ["ru", "en", "jp"]:
            await FastAPICache.clear(
                namespace="main", key=f"thread_html:{board_id}:{thread_id}:{stream}"
            )

    broadcast_data = await get_post_for_broadcast(post_num)
    if broadcast_data:
        spawn_task(manager.broadcast_post_update(broadcast_data))
        spawn_task(add_post_to_random_cache(broadcast_data))

    return {"status": "ok", "new_content": content}


@app.websocket("/ws/{board_id}/{mode}")
async def websocket_endpoint(websocket: WebSocket, board_id: str, mode: str):
    if board_id in ("admin_feed", "overboard"):
        pass
    elif board_id not in BOARD_CONFIG:
        await websocket.close()
        return

    if board_id not in BOARD_CONFIG and board_id != "overboard":
        await websocket.close(code=1008)
        return
    stream = websocket.cookies.get("stream", "ru")
    await manager.connect(websocket, board_id, mode, stream)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(websocket, board_id, mode, stream)


@app.post("/api/admin/lockdown")
async def api_set_lockdown(
    data: LockdownRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "admin"):
        raise HTTPException(status_code=403, detail="Нужен ранг Admin")
    val = "true" if data.enabled else ""
    await set_system_setting("lockdown_enabled", val)
    status = "ON" if data.enabled else "OFF"
    log_system_event(f"🚨 LOCKDOWN mode is now {status}")
    return {"status": "ok", "mode": status}


@app.get("/api/admin/lockdown_status")
async def api_get_lockdown_status(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    val = await get_system_setting("lockdown_enabled")
    return {"enabled": val == "true"}


@app.post("/api/post/{board_id}")
@limiter.limit(
    "30/minute",
    key_func=get_user_id_from_session,
    error_message="Слишком часто. Подождите минуту.",
)
async def api_create_post(
    request: Request,
    board_id: str,
    user: dict = Depends(get_current_user_or_guest),
    text: Optional[str] = Form(None),
    reply_to: Optional[int] = Form(None),
    images: List[UploadFile] = File(None),
    post_mode: str = Form(...),
    poll_question: Optional[str] = Form(None),
    poll_options: List[str] = Form(None),
    sage: Optional[str] = Form(None),
    picrandom: Optional[bool] = Form(False),
    email: Optional[str] = Form(None),
    thread_type: Optional[str] = Form("default"),
    username: Optional[str] = Form(None),
    captcha_id: Optional[str] = Form(None),
    captcha_x: Optional[int] = Form(None),
    captcha_y: Optional[int] = Form(None),
    captcha_value: Optional[str] = Form(None),
    pow_nonce: Optional[str] = Form(None),
    pow_challenge: Optional[str] = Form(None),
):
    request_id = str(uuid.uuid4())[:8]
    local_logger = RequestIdAdapter(
        logging.getLogger(__name__), {"request_id": request_id}
    )
    local_logger.info("--- START api_create_post ---")
    if reply_to and reply_to > 0 and post_mode != "chat_post":
        post_mode = "reply"
    client_ip = get_real_ip(request)

    is_shadow_muted = False

    # Если юзер из Tor или плохой сети - принудительный Shadow Ban
    if is_ip_restricted(client_ip):
        is_shadow_muted = True
        logger.warning(f"🧛 SHADOW-BANNING Tor user: {client_ip}")

    # Если юзер в теневом бане (любом), обнуляем файлы для загрузки (экономим ресурсы)
    if is_shadow_muted:
        all_files_to_upload = []
        # Вместо загрузки создаем пустой контент
        content = {"text": clean_zalgo(text or ""), "files": [], "type": "text"}
        if sage:
            content["sage"] = True
        new_post_num = await create_post(
            author_id=int(user["id"]),
            board_id=board_id,
            content=content,
            timestamp=time.time(),
            reply_to=reply_to,
            is_shadow_muted=True,
            is_from_site=True,
            post_mode=post_mode,
            stream=getattr(request.state, "stream", "ru"),
        )
        return {"Status": "OK", "Num": new_post_num}
    t = request.state.t
    is_guest = user.get("is_guest", False)
    author_id = int(user["id"])
    if thread_type not in {"default", "image", "video", "audio", "media"}:
        thread_type = "default"
    if email:
        log_system_event(
            f"🤖 BOT TRAPPED: IP {get_remote_address(request)} filled honeypot."
        )
        return {"Status": "OK", "Num": 0}
    if username:
        log_system_event(
            f"🤖 BOT TRAPPED: IP {get_remote_address(request)} filled honeypot."
        )
        return {"Status": "OK", "Num": 0}
    captcha_enabled = (await get_system_setting("captcha_enabled")) == "true"
    is_guest = user.get("is_guest", False)
    user_is_trusted = False
    if not is_guest:
        user_is_trusted = True
    else:
        guest_id = int(user["id"])
        async with get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT created_at FROM Users WHERE user_id = ?", (guest_id,)
                )
            ).fetchone()
            if row and row[0]:
                age = time.time() - row[0]
                if age > 3600:
                    user_is_trusted = True
    pow_enabled = (await get_system_setting("pow_enabled")) == "true"
    if pow_enabled and not user_is_trusted:
        is_pow_valid = False
        if pow_nonce and pow_challenge:
            from site_tgach.security import DEFAULT_POW_DIFFICULTY

            if verify_pow(pow_challenge, pow_nonce, DEFAULT_POW_DIFFICULTY):
                is_pow_valid = True
                nonce_key = f"used_pow_{pow_nonce}"
                backend = FastAPICache.get_backend()
                if await backend.get(nonce_key):
                    raise HTTPException(
                        400, t("pow_replay", "Повторное использование решения")
                    )
                await backend.set(nonce_key, "1", expire=600)

        if not is_pow_valid:
            if len(POST_RATE_LIMITER) > 50:
                logger.warning(f"🛡️ POW BLOCK: User {author_id} (High load mode)")
                raise HTTPException(
                    403,
                    t(
                        "pow_failed",
                        "Ошибка защиты (PoW). Включите JavaScript или обновите страницу.",
                    ),
                )
            else:
                logger.info(
                    f"🛡️ POW MERCY: User {author_id} passed without valid PoW (Low load)"
                )
    captcha_verified = False
    global_captcha = (await get_system_setting("captcha_enabled")) == "true"
    if global_captcha or (captcha_id and captcha_id.strip()):
        if not captcha_id:
            raise HTTPException(400, t("captcha_locked"))
        session = CAPTCHA_SESSIONS.get(captcha_id)
        if not session:
            raise HTTPException(400, t("captcha_expired"))

        try:
            mode = session["mode"]
            if mode == "monkey":
                if captcha_x is None or captcha_y is None:
                    raise HTTPException(400, t("err_cap_coord"))
                if (
                    abs(captcha_x - session["target_x"]) > 25
                    or abs(captcha_y - session["target_y"]) > 25
                ):
                    raise HTTPException(400, t("err_cap_monkey"))
            elif mode == "bottle":
                val = int(captcha_value or -999)
                final_angle = (session["start_angle"] + val) % 360
                if not (final_angle < 15 or final_angle > 345):
                    raise HTTPException(400, t("err_cap_bottle"))
            elif mode == "math":
                if str(session["answer"]) != str(captcha_value):
                    raise HTTPException(400, t("err_cap_math"))
            elif mode == "word":
                if session["word"] != str(captcha_value):
                    raise HTTPException(400, t("err_cap_word"))
            elif mode == "escobar":
                if str(captcha_value) != "success":
                    raise HTTPException(400, t("err_cap_escobar"))
            elif mode == "fan":
                if str(captcha_value) != "success":
                    raise HTTPException(400, t("err_cap_fan"))
            elif mode == "find_odd":
                if str(captcha_value) != str(session["trap_index"]):
                    raise HTTPException(400, t("err_cap_odd"))
            elif mode == "spank":
                if str(captcha_value) != "success":
                    raise HTTPException(400, t("err_cap_spank"))
            elif mode == "humiliation":
                required = session.get("phrase", "").strip().lower()
                given = (captcha_value or "").strip().lower()
                if required != given:
                    raise HTTPException(400, t("err_cap_hum"))
            elif mode == "clock":
                try:
                    if not captcha_value:
                        raise ValueError()
                    user_h, user_m = map(float, captcha_value.split(":"))
                    target_h = session["target_h"]
                    target_m = session["target_m"]

                    def angle_diff(a, b):
                        diff = abs(a - b) % 360
                        return min(diff, 360 - diff)

                    if (
                        angle_diff(user_h, target_h) > 15
                        or angle_diff(user_m, target_m) > 15
                    ):
                        raise HTTPException(400, t("err_cap_clock"))
                except:
                    raise HTTPException(400, t("err_cap_clock"))
            elif mode == "can":
                if str(captcha_value) != "opened":
                    raise HTTPException(400, t("err_cap_can"))

            captcha_verified = True
        except HTTPException as e:
            if captcha_id and captcha_id in CAPTCHA_SESSIONS:
                del CAPTCHA_SESSIONS[captcha_id]
            raise e
    lockdown_val = await get_system_setting("lockdown_enabled")
    if lockdown_val == "true" and not user.get("is_admin"):
        logger.info(f"🛡️ Lockdown check triggered for {author_id}")
        async with get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT MIN(created_at) FROM Users WHERE user_id = ?", (author_id,)
                )
            ).fetchone()
            created_at = row[0] if row and row[0] is not None else time.time()
            age_seconds = time.time() - created_at
            if age_seconds < 86400:
                if not user.get("is_admin"):
                    hours_left = int((86400 - age_seconds) / 3600)
                    raise HTTPException(
                        status_code=403, detail=t("err_bunker_mode").format(hours_left)
                    )
    stream = getattr(request.state, "stream", "ru")
    file_sig = [(f.filename, f.size) for f in images or []]
    context_sig = f"{board_id}_{reply_to or 'OP'}"
    content_hash = hashlib.md5(f"{text}{file_sig}{context_sig}".encode()).hexdigest()
    idemp_key = f"idemp_{author_id}_{content_hash}"
    backend = FastAPICache.get_backend()
    if await backend.get(idemp_key):
        raise HTTPException(status_code=409, detail=t("post_dup"))
    await backend.set(idemp_key, "1", expire=10)
    if is_guest and post_mode == "chat_post":
        raise HTTPException(status_code=403, detail=t("err_guest_chat"))
    if SITE_ACCESS_MODE == "PUBLIC_READ" and is_guest:
        raise HTTPException(status_code=403, detail=t("err_read_only_mode"))
    if post_mode == "new_thread":
        limit_seconds = 600 if is_guest else 300
        limit_desc = f"{limit_seconds // 60} мин"
    elif post_mode == "chat_post":
        limit_seconds = 5
        limit_desc = "5 сек"
    else:
        limit_seconds = 10
        limit_desc = f"{limit_seconds} сек"

    action_key = "thread" if post_mode == "new_thread" else "post"
    key = f"cooldown_{board_id}_{author_id}_{action_key}"
    backend = FastAPICache.get_backend()
    last_post_time = await backend.get(key)

    if last_post_time:
        try:
            elapsed = time.time() - float(last_post_time)
            if elapsed < limit_seconds:
                wait_time = int(limit_seconds - elapsed) + 1
                msg = f"Нихуя ты скорострел. Погоди {wait_time} сек, анон."

                raise HTTPException(
                    status_code=429, detail=msg, headers={"Retry-After": str(wait_time)}
                )
        except (ValueError, TypeError):
            pass
    stop_words = SPAM_WORDS_CACHE.get("all", set()) | SPAM_WORDS_CACHE.get(
        board_id, set()
    )
    text_safe = text or ""
    if text is None:
        text = ""
    if images is None:
        images = []
    clean_text_for_check = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text).lower()
    if stop_words:
        for word in stop_words:
            if word in clean_text_for_check:
                log_system_event(
                    f"🛡️ SPAM BLOCKED: User {author_id} tried to post '{word}'"
                )
                await backend.set(key, str(time.time()), expire=limit_seconds)
                return {
                    "id": int(time.time()),
                    "board_id": board_id,
                    "author_id": author_id,
                    "content": {"text": text, "files": [], "type": "text"},
                    "timestamp": time.time(),
                    "reply_to_post_num": reply_to,
                    "thread_id": 0,
                    "is_op_post": post_mode == "new_thread",
                    "shadow_deleted": True,
                }
    if await get_user_status(author_id, board_id) == "banned":
        logger.warning(
            f"🚫 REJECTED: User {author_id} is BANNED on /{board_id}/ (IP: {request.state.client_ip})"
        )

        lang = getattr(request.state, "lang", "ru")
        msg = TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(
            "err_banned_board", "Banned."
        )
        raise HTTPException(status_code=403, detail=msg)
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            "SELECT expires_at FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute' AND expires_at > ?",
            (author_id, board_id, time.time()),
        )
        if row := await cursor.fetchone():
            remaining = int(row[0] - time.time())
            raise HTTPException(
                status_code=403, detail=t("err_mute_remaining").format(remaining)
            )
    is_shadow_muted = await get_shadow_mute_status(author_id, board_id)
    files_to_process = []
    if images:
        for img in images:
            if getattr(img, "filename", None):
                files_to_process.append(img)
    if not is_shadow_muted:
        await check_and_punish_site_spam(
            board_id, author_id, text or "", files_to_process, t
        )
    thread_op_num = None
    if post_mode == "chat_post":
        thread_op_num = None
        reply_to = None
    elif post_mode == "reply":
        if not reply_to:
            referer = request.headers.get("referer", "")
            if "/res/" in referer:
                try:
                    match = re.search(r"/res/(\d+)\.html", referer)
                    if match:
                        reply_to = int(match.group(1))
                except:
                    pass
        if not reply_to:
            raise HTTPException(
                status_code=400, detail="Не удалось определить тред. Обновите страницу."
            )

        thread_op_num = await get_thread_op_by_post_num(reply_to)
        if not thread_op_num:
            raise HTTPException(
                status_code=404,
                detail="Thread not found or reply to chat post in thread mode.",
            )
        if await is_thread_archived(thread_op_num):
            raise HTTPException(status_code=403, detail="Thread archived.")
    elif post_mode == "new_thread":
        thread_op_num = None

    user_files_count = len(files_to_process)
    files_to_generate_count = 5 - user_files_count

    anime_tasks = []
    first_cmd_name = None

    if files_to_generate_count > 0 and text and "/" in text:
        cmd_matches = RE_ANIME_STACK.findall(text)
        if cmd_matches:
            for cmd_name, num1, num2 in cmd_matches:
                if not first_cmd_name:
                    first_cmd_name = cmd_name.lower()
                if files_to_generate_count <= 0:
                    break

                cmd_lower = cmd_name.lower()
                if cmd_lower in ANIME_COMMAND_MAP:
                    count_str = num1 or num2 or "1"
                    try:
                        req_count = int(count_str)
                    except:
                        req_count = 1

                    to_take = min(req_count, files_to_generate_count)

                    fetcher = ANIME_COMMAND_MAP[cmd_lower]
                    for _ in range(to_take):
                        anime_tasks.append(fetcher())
                        files_to_generate_count -= 1

    generated_files_objects = []
    if anime_tasks:
        url_results = await asyncio.gather(*anime_tasks, return_exceptions=True)
        valid_urls = [
            u for u in url_results if isinstance(u, str) and u.startswith("http")
        ]

        if valid_urls:
            dl_tasks = [_download_image_with_proxy(u) for u in valid_urls]
            dl_results = await asyncio.gather(*dl_tasks, return_exceptions=True)

            for i, res in enumerate(dl_results):
                if isinstance(res, tuple) and res[0]:
                    img_bytes, img_len = res
                    img_bytes = await asyncio.to_thread(
                        _resize_image_if_needed, img_bytes
                    )
                    orig_url = valid_urls[i]

                    ext = "jpg"
                    if orig_url:
                        parts = orig_url.split(".")
                        if len(parts) > 1:
                            clean_ext = parts[-1].split("?")[0].lower()
                            if clean_ext in ["png", "gif", "webp", "jpeg", "jpg"]:
                                ext = clean_ext

                    mime = "image/jpeg"
                    if ext == "gif":
                        mime = "image/gif"
                    elif ext == "png":
                        mime = "image/png"
                    elif ext == "webp":
                        mime = "image/webp"

                    fake_file = BytesUploadFile(
                        img_bytes, filename=f"auto_{i}.{ext}", content_type=mime
                    )
                    generated_files_objects.append(fake_file)

    all_files_to_upload = files_to_process + generated_files_objects
    sanitized_text = clean_zalgo(text)
    if board_id == "wh40k":
        if text:
            _, res_content = await asyncio.to_thread(
                warhammer_transform, text, allow_image=False
            )
            text = res_content
            sanitized_text = sanitize_html(text)
            sanitized_text = clean_zalgo(sanitized_text)
        if all_files_to_upload:
            new_images = []
            for img in all_files_to_upload:
                if img.filename and img.content_type.startswith("image/"):
                    try:
                        await img.seek(0)
                        raw = await img.read()
                        from site_tgach.image_processing import (
                            apply_grimdark_filter_async,
                        )

                        processed = await apply_grimdark_filter_async(raw)
                        if isinstance(img, BytesUploadFile):
                            img.file = io.BytesIO(processed)
                            img.size = len(processed)
                            await img.seek(0)
                            new_images.append(img)
                        else:
                            img.file.seek(0)
                            img.file.truncate(0)
                            img.file.write(processed)
                            img.file.seek(0)
                            if hasattr(img, "size"):
                                img.size = len(processed)
                            new_images.append(img)
                    except Exception as e:
                        print(f"WH40k Filter Error: {e}")
                        new_images.append(img)
                else:
                    new_images.append(img)
            all_files_to_upload = new_images

    files_data = []
    file_owners_to_save = []
    has_banned_content = False
    is_shadow_muted = await get_shadow_mute_status(author_id, board_id)

    if is_shadow_muted and all_files_to_upload:
        local_logger.info(
            f"Shadow-banned user {author_id} attempting to upload {len(all_files_to_upload)} files. Skipping processing."
        )
        files_data = []
        for f in all_files_to_upload:
            file_type = "image"
            if f.content_type and f.content_type.startswith("video/"):
                file_type = "video"
            elif f.content_type and f.content_type.startswith("audio/"):
                file_type = "audio"

            files_data.append(
                {
                    "type": file_type,
                    "filename": f.filename,
                    "original_file_id": "shadowbanned",
                    "thumbnail_file_id": "shadowbanned_thumb",
                }
            )
        has_banned_content = True
        file_owners_to_save = []
    elif all_files_to_upload:
        if not getattr(request.app.state, "file_uploader_bot", None):
            raise HTTPException(
                status_code=503,
                detail="File upload system unavailable (Bot init failed)",
            )

        from common.config import STORAGE_CHANNELS

        target_channel_id = STORAGE_CHANNELS.get(stream, STORAGE_CHANNELS["ru"])

        async def upload_task(file_obj):
            async with UPLOAD_SEMAPHORE:
                TELEGRAM_SINGLE_FILE_LIMIT = 50 * 1024 * 1024
                return await upload_with_bot_pool(
                    file_obj,
                    stream,
                    target_channel_id,
                    TELEGRAM_SINGLE_FILE_LIMIT,
                    local_logger,
                )

        tasks = [upload_task(f) for f in all_files_to_upload if f.filename]
        if tasks:
            results = await asyncio.gather(*tasks)
            for res_data, uploader_bot_id in results:
                if not res_data:
                    continue
                if res_data.get("banned"):
                    has_banned_content = True
                    log_system_event(
                        f"⛔ SHADOW FILTER: Banned file '{res_data.get('filename')}' ({res_data.get('reason')})."
                    )
                    continue
                if res_data.get("original_file_id"):
                    oid = res_data["original_file_id"]
                    res_data["original_url"] = f"/files/{oid}"
                if res_data.get("thumbnail_file_id"):
                    tid = res_data["thumbnail_file_id"]
                    res_data["thumbnail_url"] = f"/files/{tid}"
                file_owners_to_save.extend(
                    _file_owner_pairs_for_upload_result(res_data, uploader_bot_id)
                )
                files_data.append(res_data)

    if picrandom and len(files_data) < 4:
        from common.database import get_random_file_from_db

        rand_file = await get_random_file_from_db()
        if rand_file:
            files_data.append(rand_file)
    if sanitized_text.strip().endswith("???"):
        predictions = t("magic_8ball_answers", [])
        if not isinstance(predictions, list):
            predictions = ["Yes.", "No.", "Maybe."]

        if predictions:
            prediction = random.choice(predictions)
            sanitized_text += f'<span class="magic-8ball">{prediction}</span>'

    # Удаляем триггеры команд из текста только в том случае, если у нас есть файлы (загруженные или сгенерированные)
    # Также учитываем picrandom, так как он добавит файл позже
    if (all_files_to_upload or picrandom) and anime_tasks:
        command_keys_raw = "|".join(re.escape(k) for k in ANIME_COMMAND_MAP.keys())
        sanitized_text = re.sub(
            rf"/({command_keys_raw})(?:(\d+)|(?:\s+(\d+)))?",
            "",
            sanitized_text,
            flags=re.IGNORECASE,
        ).strip()

    final_text = sanitized_text or ""
    content = {"text": final_text, "files": files_data}
    if sage:
        content["sage"] = True
    is_shadow_final = is_shadow_muted or has_banned_content
    if post_mode == "poll":
        raw_opts = [opt.strip() for opt in (poll_options or []) if opt and opt.strip()]
        clean_opts = list(dict.fromkeys(raw_opts))
        if (
            not poll_question
            or not poll_question.strip()
            or not (2 <= len(clean_opts) <= 5)
        ):
            raise HTTPException(
                status_code=400, detail="Invalid poll data (need 2-5 unique options)"
            )
        content.update(
            {
                "poll_data": {
                    "question": poll_question.strip(),
                    "options": clean_opts,
                    "votes": {},
                    "voted_users": {},
                },
                "type": "poll",
            }
        )
    else:
        if final_text:
            content["type"] = "text"
        elif files_data:
            content["type"] = "files"
        else:
            raise HTTPException(status_code=400, detail="Empty post.")
    if not final_text and not files_data:
        if has_banned_content:
            return {"Status": "OK", "Num": 0}
        raise HTTPException(
            status_code=400, detail="Empty post. Attach file or write text."
        )
    if post_mode == "reply" and thread_op_num:
        t_type, is_unlocked = await get_thread_type_and_unlock_status(
            str(thread_op_num), author_id
        )
        if t_type != "default":
            valid_file_attached = False
            if files_data:
                for f in files_data:
                    ftype = f.get("type", "file")
                    if t_type == "media":
                        valid_file_attached = True
                    elif t_type == "image" and ftype in ["image", "photo", "sticker"]:
                        valid_file_attached = True
                    elif t_type == "video" and ftype in [
                        "video",
                        "animation",
                        "video_note",
                        "gif",
                    ]:
                        valid_file_attached = True
                    elif t_type == "audio" and ftype in ["audio", "voice"]:
                        valid_file_attached = True
            if valid_file_attached:
                if not is_unlocked:
                    try:
                        db = await get_pool()
                        await db.execute(
                            "INSERT OR IGNORE INTO ThreadUnlocks (thread_id, user_id) VALUES (?, ?)",
                            (str(thread_op_num), author_id),
                        )
                        await db.commit()
                    except Exception as e:
                        local_logger.error(f"Failed to unlock thread for user: {e}")
            elif not is_unlocked:
                # Получаем локализованные названия
                type_names = {
                    "image": t("tt_image"),
                    "video": t("tt_video"),
                    "audio": t("tt_audio"),
                    "media": t("tt_media"),
                }
                req_str = type_names.get(t_type, t_type.upper())

                # ЗАЩИТА: Безопасная сборка строки ответа
                base_msg = str(t("err_thread_type", "В этом треде требуется файл:"))
                if "{0}" in base_msg:
                    err_msg = base_msg.replace("{0}", req_str)
                elif "{}" in base_msg:
                    err_msg = base_msg.format(req_str)
                else:
                    err_msg = f"{base_msg} [{req_str}]"

                raise HTTPException(status_code=400, detail=err_msg)
    await backend.set(key, str(time.time()), expire=limit_seconds)
    current_ts = time.time()
    new_post_num = 0

    local_logger.info("Calling create_post...")
    for _retry in range(3):
        try:
            # Внутри api_create_post
            new_post_num = await create_post(
                author_id=author_id,
                board_id=board_id,
                content=content,
                timestamp=current_ts,
                reply_to=reply_to,
                is_shadow_muted=is_shadow_final,
                is_from_site=True,
                post_mode=post_mode,
                stream=stream,
                ip=client_ip,  # ПЕРЕДАЕМ IP ДЛЯ ИСТОРИИ И БАНОВ
                thread_id_from_bot=str(thread_op_num) if thread_op_num else None,
                request_id_for_log=request_id,
                file_owners=file_owners_to_save,
            )
            if new_post_num:
                local_logger.info(
                    f"create_post SUCCESS, returned post_num: {new_post_num}"
                )
                break
        except Exception as e:
            if "locked" in str(e).lower():
                await asyncio.sleep(0.2)
            else:
                raise e
    if not new_post_num:
        local_logger.error("create_post FAILED after all retries.")
        raise HTTPException(status_code=500, detail="DB Error / Busy")

    # ПРАВКА: Мгновенный сброс кэша доски и overboard, чтобы пост (даже shadow) появился сразу
    now_ts = time.time()
    BOARD_VERSIONS[board_id] = now_ts
    BOARD_VERSIONS["overboard"] = now_ts

    if captcha_verified and captcha_id in CAPTCHA_SESSIONS:
        del CAPTCHA_SESSIONS[captcha_id]

    final_thread_id = 0
    local_logger.info("Creating background task for cross-links...")
    if not is_shadow_final:
        spawn_task(process_cross_links(board_id, new_post_num, sanitized_text, stream))

    async def delayed_backlinks():
        await asyncio.sleep(0.25)  # Даем базе "вздохнуть" после тяжелого INSERT
        await process_backlinks(new_post_num, sanitized_text, reply_to)

    spawn_task(delayed_backlinks())
    POST_RATE_LIMITER.append(time.time())
    while len(POST_RATE_LIMITER) > 0 and POST_RATE_LIMITER[0] < time.time() - 60:
        POST_RATE_LIMITER.popleft()
    if len(POST_RATE_LIMITER) > 100:
        try:
            current_captcha = await get_system_setting("captcha_enabled")
            if current_captcha != "true":
                await set_system_setting("captcha_enabled", "true")
                log_system_event(
                    f"🚨 ANTI-RAID: Captcha AUTO-ENABLED (Rate: {len(POST_RATE_LIMITER)} posts/min)"
                )
        except:
            pass

    if post_mode == "new_thread":
        title = sanitized_text[:255]
        if not title.strip() and first_cmd_name:
            title = f"/{first_cmd_name}"
        title = title or (
            files_data[0].get("filename", t("default_filename"))
            if files_data
            else t("default_thread_title")
        )
        if not await create_thread_entry(
            new_post_num,
            board_id,
            author_id,
            title,
            current_ts,
            stream=stream,
            thread_type=thread_type,
        ):
            await delete_post_by_num(new_post_num)
            raise HTTPException(status_code=500, detail="Thread DB Error (Rolled back)")
        final_thread_id = new_post_num
        try:
            neuro_enabled = await get_system_setting("neuro_enabled")
            if neuro_enabled == "true":
                nm = request.app.state.neuro_manager

                async def delayed_bump(bid, tid, s, manager):
                    delay = random.randint(300, 1800)
                    await asyncio.sleep(delay)
                    try:
                        await manager.make_post(
                            bid, stream=s, forced_mode="reply", forced_thread_id=tid
                        )
                    except Exception as e:
                        logger.error(f"Delayed bump failed: {e}")

                spawn_task(delayed_bump(board_id, final_thread_id, stream, nm))
        except:
            pass
    elif post_mode == "reply" and thread_op_num:
        async with get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT is_endless FROM Threads WHERE thread_id = ?",
                    (str(thread_op_num),),
                )
            ).fetchone()
            is_endless = bool(row[0]) if row else False
        if not sage:
            from common.database import update_thread_last_updated

            await update_thread_last_updated(thread_op_num, current_ts)
        if not is_shadow_final and board_id not in ["thread", "test"]:
            await process_mentions_and_notify(
                new_post_num, board_id, sanitized_text, author_id, reply_to
            )

        if is_endless:
            from common.database import trim_thread_posts

            spawn_task(trim_thread_posts(str(thread_op_num), max_posts=1000))
        else:
            if await get_post_count_in_thread(thread_op_num) >= BUMP_LIMIT:
                async with ARCHIVE_LOCKS[thread_op_num]:
                    if not await is_thread_archived(thread_op_num):
                        await archive_thread_in_db(thread_op_num)
                    if thread_op_num in ARCHIVE_LOCKS:
                        del ARCHIVE_LOCKS[thread_op_num]
        final_thread_id = thread_op_num
        # ПРАВКА: Сброс кэша конкретного треда
        if final_thread_id:
            THREAD_VERSIONS[str(final_thread_id)] = now_ts

    broadcast_post = None
    if not is_shadow_final:
        broadcast_post = await get_post_for_broadcast(new_post_num)
        if broadcast_post:
            await request.app.state.broadcast_queue.put(broadcast_post)

    local_logger.info("--- END api_create_post ---")
    if broadcast_post:
        spawn_task(add_post_to_random_cache(broadcast_post))
        return broadcast_post

    return {
        "id": new_post_num,
        "board_id": board_id,
        "author_id": author_id,
        "content": content,
        "timestamp": current_ts,
        "reply_to_post_num": reply_to,
        "thread_id": final_thread_id,
        "is_op_post": post_mode == "new_thread",
    }


@lru_cache(maxsize=8)
def localize_boards(lang: str) -> dict:
    """
    Создает копию конфига досок с переведенным описанием.
    Кэшируется для ускорения (Board Config считается неизменным).
    """
    localized = {}
    for board_id, data in BOARD_CONFIG.items():
        board_copy = data.copy()
        desc = data.get("description")
        if isinstance(desc, dict):
            board_copy["description"] = (
                desc.get(lang)
                or desc.get("en")
                or desc.get("ru")
                or list(desc.values())[0]
            )
        else:
            board_copy["description"] = str(desc)
        localized[board_id] = board_copy
    return localized


@app.post("/api/admin/cleanup_html")
async def api_admin_cleanup_html(user: dict = Depends(get_required_user)):
    """
    Разовый скрипт для очистки базы от битых тегов <img> в тексте постов.
    """
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    count = 0
    from bs4 import BeautifulSoup
    import json

    # Используем отдельное соединение для тяжелой задачи
    from common.db_pool import db_lock

    async with db_lock, get_db_connection() as conn:
        # 1. Находим посты, где в тексте есть тег <img
        # LIKE '%<img%' работает быстро
        query = "SELECT post_num, content FROM Posts WHERE content LIKE '%<img%'"

        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return {"status": "ok", "message": "База чиста, исправлять нечего."}

        # 2. Проходимся и чистим
        await conn.execute("BEGIN IMMEDIATE")

        updates = []
        for row in rows:
            post_num, raw_content = row
            try:
                content = json.loads(raw_content)
                text = content.get("text", "")

                if "<img" in text or "<IMG" in text:
                    soup = BeautifulSoup(text, "html.parser")
                    images = soup.find_all("img")

                    if images:
                        for img in images:
                            img.decompose()

                        content["text"] = str(soup)
                        new_json = json.dumps(content)

                        updates.append((new_json, post_num))
                        count += 1
            except Exception:
                continue

        if updates:
            await conn.executemany(
                "UPDATE Posts SET content = ? WHERE post_num = ?", updates
            )

        await conn.execute("COMMIT")

    log_system_event(f"🧹 HTML CLEANUP: Очищено {count} постов от битых картинок.")
    return {"status": "ok", "cleaned": count}


@app.post("/api/admin/import_thread")
async def api_import_thread(
    request: Request,
    bg_tasks: BackgroundTasks,
    data: dict = Body(...),
    user: dict | None = Depends(get_optional_user),
):
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    url = data.get("url")
    board_id = data.get("board_id")
    target_stream = data.get("stream", "ru")

    use_sim = data.get("use_simulation", False)
    sim_settings = {
        "enabled": use_sim,
        "start_delay_mins": int(data.get("start_delay", 0)),
        "interval_min": int(data.get("interval_min", 20)),
        "interval_max": int(data.get("interval_max", 120)),
    }

    if not url or not board_id or board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=400, detail="Invalid data")
    from site_tgach.importer import ThreadImporter
    from common.config import STORAGE_CHANNELS

    existing_bot = request.app.state.file_uploader_bot
    target_channel_id = STORAGE_CHANNELS.get(target_stream, STORAGE_CHANNELS["ru"])
    importer = ThreadImporter(existing_bot, target_channel_id)

    mode = "SIMULATION" if use_sim else "INSTANT"
    log_system_event(
        f"Запущен импорт ({mode}): {url} -> /{board_id}/ [{target_stream}]"
    )
    from common.database import get_db_connection
    import time

    try:
        from common.db_pool import db_lock

        async with db_lock, get_db_connection() as conn:
            await conn.execute(
                "INSERT INTO ImportRequests (user_id, url, target_board, comment, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], url, board_id, f"Manual {mode}", "approved", time.time()),
            )
            await conn.commit()
    except Exception as e:
        print(f"Warning logging import request: {e}")

    bg_tasks.add_task(
        importer.process_thread, url, board_id, target_stream, sim_settings
    )
    return {"status": "ok", "stream": target_stream}


class CancelImportRequest(BaseModel):
    task_id: str


@app.get("/api/admin/active_simulations")
async def api_get_active_simulations(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    from common.database import get_db_connection

    simulations = []

    async with get_db_connection() as conn:
        query = """
            SELECT task_id, board_id, MAX(thread_title), COUNT(*), MIN(publish_at), MAX(publish_at)
            FROM ImportQueue
            GROUP BY task_id
            ORDER BY MIN(publish_at) ASC
        """
        async with conn.execute(query) as cursor:
            async for row in cursor:
                simulations.append(
                    {
                        "task_id": row[0],
                        "board_id": row[1],
                        "title": row[2] or "Unknown Thread",
                        "remaining_posts": row[3],
                        "next_post_at": row[4],
                        "finish_at": row[5],
                    }
                )
    return simulations


@app.post("/api/admin/cancel_simulation")
async def api_cancel_simulation(
    data: CancelImportRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    from common.database import get_db_connection
    from common.db_pool import db_lock

    async with db_lock, get_db_connection() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        await conn.execute("DELETE FROM ImportQueue WHERE task_id = ?", (data.task_id,))
        await conn.execute(
            "DELETE FROM ImportRefMap WHERE task_id = ?", (data.task_id,)
        )

        await conn.execute("COMMIT")

    log_system_event(f"🚫 Импорт отменен админом. Task ID: {data.task_id}")
    return {"status": "ok"}


@app.get("/api/admin/spam_words")
@cache(expire=60)
async def api_get_spam_words(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {k: list(v) for k, v in SPAM_WORDS_CACHE.items()}


@app.post("/api/admin/add_spam_word")
async def api_add_spam_word(
    data: SpamWordRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    word = data.word.lower().strip()
    if await add_spam_word(data.board_id, word):
        SPAM_WORDS_CACHE[data.board_id].add(word)
        return {"status": "added", "word": word}
    raise HTTPException(status_code=500, detail="DB Error")


@app.post("/api/admin/remove_spam_word")
async def api_remove_spam_word(
    data: SpamWordRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    word = data.word.lower().strip()
    if await remove_spam_word(data.board_id, word):
        if word in SPAM_WORDS_CACHE[data.board_id]:
            SPAM_WORDS_CACHE[data.board_id].remove(word)
        return {"status": "removed", "word": word}
    raise HTTPException(status_code=404, detail="Not found")


def get_fastapi_cache_snapshot() -> dict:
    try:
        backend = FastAPICache.get_backend()
        store = getattr(backend, "_store", None)
        if not isinstance(store, dict):
            return {}
        now = int(time.time())
        expired = 0
        data_bytes = 0
        for key, value in list(store.items()):
            ttl_ts = getattr(value, "ttl_ts", 0)
            if ttl_ts and ttl_ts < now:
                expired += 1
            data = getattr(value, "data", "")
            if isinstance(data, (bytes, bytearray)):
                data_bytes += len(data)
            elif isinstance(data, str):
                data_bytes += len(data.encode("utf-8", errors="ignore"))
        return {
            "keys": len(store),
            "expired_keys": expired,
            "data_mb": round(data_bytes / 1024 / 1024, 2),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def cleanup_fastapi_cache_once() -> dict:
    backend = FastAPICache.get_backend()
    store = getattr(backend, "_store", None)
    lock = getattr(backend, "_lock", None)
    if not isinstance(store, dict):
        return {"keys": 0, "expired_removed": 0, "cap_removed": 0}
    now = int(time.time())
    expired_removed = 0
    cap_removed = 0

    async def _cleanup_unlocked():
        nonlocal expired_removed, cap_removed
        expired_keys = [
            key
            for key, value in list(store.items())
            if getattr(value, "ttl_ts", 0) and getattr(value, "ttl_ts", 0) < now
        ]
        for key in expired_keys:
            if key in store:
                del store[key]
                expired_removed += 1
        if SITE_FASTAPI_CACHE_MAX_KEYS > 0 and len(store) > SITE_FASTAPI_CACHE_MAX_KEYS:
            overflow = len(store) - SITE_FASTAPI_CACHE_MAX_KEYS
            removable = sorted(
                store.items(), key=lambda item: getattr(item[1], "ttl_ts", 0)
            )[:overflow]
            for key, _ in removable:
                if key in store:
                    del store[key]
                    cap_removed += 1

    if lock:
        async with lock:
            await _cleanup_unlocked()
    else:
        await _cleanup_unlocked()
    return {
        "keys": len(store),
        "expired_removed": expired_removed,
        "cap_removed": cap_removed,
    }


def cleanup_site_runtime_maps_once() -> dict:
    now = time.time()
    result = {
        "post_rate_removed": 0,
        "thread_versions_removed": 0,
        "url_status_removed": 0,
        "flood_tracker_removed": 0,
        "ip_bans_removed": 0,
        "ip_troll_removed": 0,
        "bot_violations_cleared": 0,
        "known_ips_cleared": 0,
    }
    while POST_RATE_LIMITER and POST_RATE_LIMITER[0] < now - 60:
        POST_RATE_LIMITER.popleft()
        result["post_rate_removed"] += 1
    if SITE_THREAD_VERSION_TTL_SEC > 0:
        stale_thread_keys = [
            key
            for key, ts in list(THREAD_VERSIONS.items())
            if now - float(ts or 0) > SITE_THREAD_VERSION_TTL_SEC
        ]
        for key in stale_thread_keys:
            THREAD_VERSIONS.pop(key, None)
            result["thread_versions_removed"] += 1
    if (
        SITE_THREAD_VERSION_MAX_KEYS > 0
        and len(THREAD_VERSIONS) > SITE_THREAD_VERSION_MAX_KEYS
    ):
        overflow = len(THREAD_VERSIONS) - SITE_THREAD_VERSION_MAX_KEYS
        for key, _ in sorted(THREAD_VERSIONS.items(), key=lambda item: item[1])[
            :overflow
        ]:
            THREAD_VERSIONS.pop(key, None)
            result["thread_versions_removed"] += 1
    if "URL_STATUS_CACHE" in globals():
        stale_urls = [
            key
            for key, value in list(URL_STATUS_CACHE.items())
            if isinstance(value, tuple)
            and len(value) > 1
            and now - float(value[1] or 0) > 1800
        ]
        for key in stale_urls:
            URL_STATUS_CACHE.pop(key, None)
            result["url_status_removed"] += 1
    if SITE_FLOOD_TRACKER_TTL_SEC > 0:
        stale_flood_keys = []
        for key, history in list(REQUEST_FLOOD_TRACKER.items()):
            fresh_history = [
                ts
                for ts in history
                if now - float(ts or 0) < SITE_FLOOD_TRACKER_TTL_SEC
            ]
            if fresh_history:
                if len(fresh_history) != len(history):
                    REQUEST_FLOOD_TRACKER[key] = fresh_history
            else:
                stale_flood_keys.append(key)
        for key in stale_flood_keys:
            REQUEST_FLOOD_TRACKER.pop(key, None)
            result["flood_tracker_removed"] += 1
    if (
        SITE_SECURITY_MAP_MAX_KEYS > 0
        and len(REQUEST_FLOOD_TRACKER) > SITE_SECURITY_MAP_MAX_KEYS
    ):
        overflow = len(REQUEST_FLOOD_TRACKER) - SITE_SECURITY_MAP_MAX_KEYS
        for key, _ in sorted(
            REQUEST_FLOOD_TRACKER.items(),
            key=lambda item: max(item[1]) if item[1] else 0,
        )[:overflow]:
            REQUEST_FLOOD_TRACKER.pop(key, None)
            result["flood_tracker_removed"] += 1
    expired_bans = [
        ip for ip, exp in list(IP_BAN_LIST.items()) if float(exp or 0) < now
    ]
    for ip in expired_bans:
        IP_BAN_LIST.pop(ip, None)
        result["ip_bans_removed"] += 1
    expired_trolls = [
        ip
        for ip, cfg in list(IP_TROLL_CONFIG.items())
        if float(cfg.get("expires", 0) if isinstance(cfg, dict) else 0) < now
    ]
    for ip in expired_trolls:
        IP_TROLL_CONFIG.pop(ip, None)
        result["ip_troll_removed"] += 1
    if (
        SITE_SECURITY_MAP_MAX_KEYS > 0
        and len(BOT_VIOLATIONS) > SITE_SECURITY_MAP_MAX_KEYS
    ):
        result["bot_violations_cleared"] = len(BOT_VIOLATIONS)
        BOT_VIOLATIONS.clear()
    if SITE_SECURITY_MAP_MAX_KEYS > 0 and len(KNOWN_IPS) > SITE_SECURITY_MAP_MAX_KEYS:
        result["known_ips_cleared"] = len(KNOWN_IPS)
        KNOWN_IPS.clear()
    return result


async def site_cache_cleanup_task():
    await asyncio.sleep(SITE_CACHE_CLEANUP_INTERVAL_SEC)
    while True:
        try:
            cache_result = await cleanup_fastapi_cache_once()
            map_result = cleanup_site_runtime_maps_once()
            if (
                cache_result.get("expired_removed")
                or cache_result.get("cap_removed")
                or map_result.get("thread_versions_removed")
                or map_result.get("url_status_removed")
                or map_result.get("flood_tracker_removed")
                or map_result.get("ip_bans_removed")
                or map_result.get("ip_troll_removed")
                or map_result.get("bot_violations_cleared")
                or map_result.get("known_ips_cleared")
            ):
                logger.info(
                    f"Site cache cleanup: cache={cache_result}, maps={map_result}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Site cache cleanup error: {exc}")
        await asyncio.sleep(SITE_CACHE_CLEANUP_INTERVAL_SEC)


def get_site_process_snapshot() -> dict:
    if not psutil:
        return {}
    try:
        process = psutil.Process(os.getpid())
        info = process.memory_info()
        try:
            full_info = process.memory_full_info()
        except Exception:
            full_info = info
        private_bytes = (
            getattr(full_info, "uss", None)
            or getattr(info, "private", None)
            or getattr(info, "vms", 0)
        )
        return {
            "pid": os.getpid(),
            "rss_mb": round(getattr(info, "rss", 0) / 1024 / 1024, 2),
            "private_mb": round(private_bytes / 1024 / 1024, 2),
            "vms_mb": round(getattr(info, "vms", 0) / 1024 / 1024, 2),
            "threads": process.num_threads(),
            "open_files": -1,
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_site_runtime_snapshot() -> dict:
    try:
        spam_users = sum(len(users) for users in site_spam_tracker.values())
    except Exception:
        spam_users = -1
    try:
        broadcast_queue_size = app.state.broadcast_queue.qsize()
    except Exception:
        broadcast_queue_size = None
    return {
        "broadcast_queue": broadcast_queue_size,
        "active_connections": sum(len(s) for s in manager.active_connections.values()),
        "connection_keys": len(manager.active_connections),
        "captcha_sessions": len(CAPTCHA_SESSIONS),
        "site_spam_boards": len(site_spam_tracker),
        "site_spam_users": spam_users,
        "post_rate_limiter": len(POST_RATE_LIMITER),
        "system_logs": len(SYSTEM_LOGS),
        "spam_words_boards": len(SPAM_WORDS_CACHE),
        "board_versions": len(BOARD_VERSIONS),
        "thread_versions": len(THREAD_VERSIONS),
        "url_status_cache": (
            len(URL_STATUS_CACHE) if "URL_STATUS_CACHE" in globals() else 0
        ),
        "request_flood_tracker": len(REQUEST_FLOOD_TRACKER),
        "known_ips": len(KNOWN_IPS),
        "bot_violations": len(BOT_VIOLATIONS),
        "ip_bans": len(IP_BAN_LIST),
        "ip_troll_configs": len(IP_TROLL_CONFIG),
        "fastapi_cache": get_fastapi_cache_snapshot(),
    }


@app.get("/api/admin/stats")
@cache(expire=30)
async def api_admin_stats(user: dict | None = Depends(get_optional_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    async with get_db_connection() as conn:
        posts = (await (await conn.execute("SELECT COUNT(*) FROM posts")).fetchone())[0]
        threads = (
            await (await conn.execute("SELECT COUNT(*) FROM Threads")).fetchone()
        )[0]
        top = await (
            await conn.execute(
                "SELECT board_id, COUNT(*) as c FROM posts GROUP BY board_id ORDER BY c DESC LIMIT 5"
            )
        ).fetchall()
    from common.database import get_system_queue_counts

    queues = await get_system_queue_counts()

    return {
        "total_posts": posts,
        "total_threads": threads,
        "top_boards": [{"board": r[0], "count": r[1]} for r in top],
        "active_connections": sum(len(s) for s in manager.active_connections.values()),
        "queues": queues,
        "process": get_site_process_snapshot(),
        "runtime": get_site_runtime_snapshot(),
    }


@app.get("/tv/random")
async def roulette_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="roulette.jinja2",
        context={
            "request": request,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "boards": BOARD_CONFIG,
        },
    )


@app.get("/api/tv/next")
@limiter.limit("25/minute")
async def api_roulette_next(request: Request, boards: Optional[str] = None):
    from common.database import get_random_video_post, get_file_mirrors

    # Парсим список досок из query string (?boards=b,a,gd)
    allowed_boards = None
    if boards:
        allowed_boards = [b.strip() for b in boards.split(",") if b.strip()]

    deadline = time.monotonic() + RANDOM_API_DEADLINE_SEC
    for _ in range(8):
        if time.monotonic() >= deadline:
            break
        try:
            raw_post = await get_random_video_post(allowed_boards=allowed_boards)
        except Exception:
            raw_post = None

        if not raw_post:
            return JSONResponse({"error": "No videos found"}, status_code=404)

        enriched_posts = _convert_and_enrich_posts([raw_post])
        post = enriched_posts[0]

        video_file = None
        files = post["content"].get("files", [])

        idx = raw_post.get("_selected_file_index")
        if idx is not None and 0 <= idx < len(files):
            video_file = files[idx]
        elif files:
            for f in files:
                if f["type"] in ["video", "gif", "animation", "video_note"]:
                    video_file = f
                    break

        if not video_file:
            continue

        file_id = video_file.get("original_file_id")
        if not await _is_random_file_available_with_deadline(file_id, deadline):
            continue

        src = video_file["original_url"]
        sources = [src]

        if file_id:
            mirrors_dict = await get_file_mirrors(file_id)
            if "catbox" in mirrors_dict:
                sources.append(mirrors_dict["catbox"])
            hf_source = mirrors_dict.get("huggingface")
            if is_hf_link_allowed(hf_source, VALID_HF_REPOS):
                sources.append(hf_source)
            if "0x0" in mirrors_dict:
                sources.append(mirrors_dict["0x0"])

        return {
            "src": src,
            "file_id": file_id,
            "sources": sources,
            "poster": video_file.get("thumbnail_url", ""),
            "post_id": post["id"],
            "board_id": post["board_id"],
            "thread_id": post.get("thread_id"),
            "text": post["content"].get("text", "")[:200],
            "filename": video_file.get("filename", "video.mp4"),
            "is_censored": post["content"].get("is_censored", False),
        }

    return JSONResponse({"error": "No live videos found"}, status_code=404)


@app.get("/api/global_announcement")
async def api_public_announcement():
    text = await get_system_setting("global_announcement")
    return {"text": text}


@app.get("/api/locales")
@cache(expire=86400)
async def api_get_locales():

    return TRANSLATIONS


@app.post("/api/request_import")
@limiter.limit("3/hour", key_func=get_user_id_from_session)
async def api_user_request_import(
    request: Request,
    data: ImportRequestModel,
    user: dict = Depends(get_current_user_or_guest),
):
    t = request.state.t

    if "2ch" not in data.url and "4chan" not in data.url and "arch" not in data.url:
        raise HTTPException(400, t("err_import_url"))
    if data.board_id not in BOARD_CONFIG:
        raise HTTPException(400, t("err_import_board"))
    success = await create_import_request(
        int(user["id"]), data.url, data.board_id, data.comment[:200]
    )
    if success:
        return {"status": "ok", "message": t("import_req_success")}
    raise HTTPException(500, "Ошибка сервера")


@app.get("/api/admin/import_requests")
async def api_admin_get_import_requests(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    return await get_pending_import_requests()


@app.get("/api/admin/feedback")
async def api_admin_get_feedback(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    return await get_all_feedback()


@app.get("/api/admin/feedback/count")
async def api_admin_feedback_count(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    count = await get_unread_feedback_count()
    return {"count": count}


class FeedbackReadRequest(BaseModel):
    id: int


@app.post("/api/admin/feedback/read")
async def api_admin_feedback_mark_read(
    data: FeedbackReadRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    await mark_feedback_read(data.id)
    return {"status": "ok"}


class ApproveRequestModel(BaseModel):
    request_id: int
    url: str
    board_id: str
    stream: str


@app.post("/api/admin/approve_import")
async def api_admin_approve_import(
    request: Request,
    bg_tasks: BackgroundTasks,
    data: ApproveRequestModel,
    user: dict = Depends(get_required_user),
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    from site_tgach.importer import ThreadImporter
    from common.config import STORAGE_CHANNELS

    target_channel_id = STORAGE_CHANNELS.get(data.stream, STORAGE_CHANNELS["ru"])
    importer = ThreadImporter(request.app.state.file_uploader_bot, target_channel_id)
    bg_tasks.add_task(importer.process_thread, data.url, data.board_id, data.stream)
    await update_import_request_status(data.request_id, "approved")
    log_system_event(f"✅ REQUEST APPROVED: {data.url} -> /{data.board_id}/")
    return {"status": "ok"}


@app.post("/api/admin/reject_import")
async def api_admin_reject_import(
    data: dict = Body(...), user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    req_id = data.get("request_id")
    if req_id:
        await update_import_request_status(req_id, "rejected")
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    role = user.get("role", "user")
    is_root = user.get("id") in ADMIN_IDS
    if role == "user" and not is_root:
        raise HTTPException(status_code=403, detail="Forbidden")
    return templates.TemplateResponse(
        request=request,
        name="admin.jinja2",
        context={
            "request": request,
            "boards": BOARD_CONFIG,
            "site_mode": SITE_ACCESS_MODE,
            "session": {"user": user},
            "user_role": role,
            "is_root": is_root,
        },
    )


@app.get("/api/admin/system_health")
async def api_admin_health(user: dict | None = Depends(get_optional_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    if not psutil:
        return {"error": "psutil not installed"}
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "process": get_site_process_snapshot(),
        "runtime": get_site_runtime_snapshot(),
    }


@app.get("/api/admin/logs")
async def api_admin_logs(user: dict | None = Depends(get_optional_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    async with get_db_connection() as conn:
        query = "SELECT source, event_text, created_at FROM GlobalLogs ORDER BY created_at DESC LIMIT 100"
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()
    formatted_logs = []
    for r in rows:
        src = "🤖" if r[0] == "bot" else "🌐"
        ts = datetime.fromtimestamp(r[2]).strftime("%H:%M:%S")
        formatted_logs.append(f"[{ts}] {src} {r[1]}")
    return formatted_logs


@app.get("/api/post/{post_num}")
async def api_get_post(post_num: int, request: Request):
    post = await get_post_by_num(post_num)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    enriched_list = _convert_and_enrich_posts([post])
    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(enriched_list, is_ru=is_ru)
    return enriched_list[0]


@app.get("/api/thread/{board_id}/{thread_id}")
async def api_get_thread(
    board_id: str,
    thread_id: int,
    request: Request,
    user: dict = Depends(get_current_user_or_guest),
):
    board_id = board_id.lower()

    # Кэширование на основе версии доски (обновляется при любом посте)
    current_version = BOARD_VERSIONS[board_id]
    stream = getattr(request.state, "stream", "ru")
    # Кэш общий для всех (без shadow-постов)
    cache_key = f"api_thread_full_v2:{board_id}:{thread_id}:{stream}:{current_version}"

    backend = FastAPICache.get_backend()
    cached_data = await backend.get(cache_key)

    posts_flat = []

    if cached_data:
        try:
            posts_flat = orjson.loads(cached_data)
        except:
            posts_flat = []

    if not posts_flat:
        # CACHE MISS: Тяжелая загрузка из БД (только публичные посты)
        # get_thread_by_op_post возвращает (op, replies)
        thread_data = await get_thread_by_op_post(thread_id, current_user_id=None)

        if not thread_data:
            # Если тред не найден или скрыт
            # Можно проверить shadow явно, но get_thread_by_op_post(None) уже фильтрует
            return []

        op, replies = thread_data
        raw_list = [op] + replies

        # Стандартизация и обогащение (ТЯЖЕЛАЯ ФАЗА)
        posts_flat = _convert_and_enrich_posts(raw_list)
        await enrich_heavy_data(posts_flat)

        if posts_flat:
            await backend.set(cache_key, orjson.dumps(posts_flat), expire=600)

    if cached_data:
        pass  # orjson.loads создает копию
    else:
        import copy

        posts_flat = copy.deepcopy(posts_flat)

    is_ru = await is_request_from_ru(request)
    # Передаем ID автора первого поста как op_author_id
    op_id = posts_flat[0].get("author_id") if posts_flat else None
    finalize_posts_for_user(posts_flat, int(user["id"]), is_ru, op_author_id=op_id)

    return posts_flat


@app.get("/api/catalog/{board_id}")
async def api_get_catalog(
    board_id: str,
    request: Request,
    sort: str = "bump",
    user: dict = Depends(get_current_user_or_guest),
):
    board_id = board_id.lower()
    if board_id not in BOARD_CONFIG:
        raise HTTPException(404)
    current_version = BOARD_VERSIONS[board_id]
    stream = getattr(request.state, "stream", "ru")
    selected_boards_str = ",".join(sorted(request.query_params.getlist("boards")))
    cache_key = f"api_catalog_v3:{board_id}:{sort}:{stream}:{current_version}:{selected_boards_str}"
    backend = FastAPICache.get_backend()
    cached = await backend.get(cache_key)
    if cached:
        posts = orjson.loads(cached)
    else:
        raw = await get_op_posts_for_board(
            board_id, sort_by=sort, page=1, page_size=100, stream=stream
        )
        posts = _convert_and_enrich_posts(raw)
        await enrich_heavy_data(posts)
        if posts:
            await backend.set(cache_key, orjson.dumps(posts), expire=600)
    import copy

    posts_copy = copy.deepcopy(posts)
    is_ru = await is_request_from_ru(request)
    finalize_posts_for_user(posts_copy, int(user["id"]), is_ru)
    return posts_copy


@app.get("/api/summary/{thread_id}")
@limiter.limit("20/minute", key_func=get_user_id_from_session)
async def api_thread_summary(thread_id: int, request: Request):
    current_count = await get_post_count_in_thread(thread_id)
    stream = getattr(request.state, "stream", "ru")
    cache_key = f"summary_v3_{stream}_{thread_id}"
    backend = FastAPICache.get_backend()
    cached_data_raw = await backend.get(cache_key)
    if cached_data_raw:
        try:
            cached_data = json.loads(cached_data_raw)
            cached_count = cached_data.get("count", 0)
            if (current_count - cached_count) < 8:
                return {"summary": cached_data.get("text")}
        except:
            pass
    thread_data = await get_thread_by_op_post(thread_id)
    if not thread_data:
        raise HTTPException(404, "Thread not found")
    op_post, replies = thread_data
    optimized_text = optimize_thread_context(op_post, replies, max_posts=60)
    if len(optimized_text) < 50:
        return {"summary": "Тред слишком короткий, тут нехуй анализировать."}
    stream = getattr(request.state, "stream", "ru")
    summary = await request.app.state.neuro_manager.generate_summary(
        optimized_text, stream
    )
    if summary and "API Error" not in summary:
        to_cache = json.dumps({"count": current_count, "text": summary})
        await backend.set(cache_key, to_cache, expire=86400)
    return {"summary": summary}


@app.get("/random/thread")
async def random_thread_redirect():
    res = await get_random_active_thread()
    if res:
        return RedirectResponse(url=f"/{res[0]}/res/{res[1]}.html", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/thread/{thread_id}/vibe")
@limiter.limit("5/minute", key_func=get_user_id_from_session)
async def api_thread_vibe(thread_id: int, request: Request):
    current_count = await get_post_count_in_thread(thread_id)
    stream = getattr(request.state, "stream", "ru")
    cache_key = f"vibe_v3_{stream}_{thread_id}"
    backend = FastAPICache.get_backend()
    cached_data_raw = await backend.get(cache_key)

    if cached_data_raw:
        try:
            cached_data = json.loads(cached_data_raw)
            cached_count = cached_data.get("count", 0)
            if (current_count - cached_count) < 10:
                return {
                    "vibe": cached_data.get("vibe"),
                    "icon": cached_data.get("icon"),
                }
        except:
            pass
    thread_data = await get_thread_by_op_post(thread_id)
    if not thread_data:
        raise HTTPException(404, "Thread not found")
    op_post, replies = thread_data
    optimized_text = optimize_thread_context(op_post, replies, max_posts=50)
    stream = getattr(request.state, "stream", "ru")
    vibe_raw = await request.app.state.neuro_manager.analyze_vibe(
        optimized_text, stream
    )
    icon_text = vibe_to_icon(vibe_raw)
    if vibe_raw and "API Error" not in vibe_raw:
        to_cache = json.dumps(
            {"count": current_count, "vibe": vibe_raw, "icon": icon_text}
        )
        await backend.set(cache_key, to_cache, expire=86400)
    return {"vibe": vibe_raw, "icon": icon_text}


def vibe_to_icon(vibe_text):
    v = vibe_text.lower().strip()
    mapping = {
        "toxic": "🔥 (Токсично)",
        "cozy": "🍵 (Лампово)",
        "horny": "🍑 (Дрочка)",
        "sad": "🚬 (Депрессивно)",
        "nerd": "🤓 (Душно)",
        "schizo": "🤡 (Шиза)",
        "neutral": "😐 (Нейтрально)",
        "funny": "😂",
        "lol": "😂",
        "politics": "⚔️ (Срач)",
        "war": "⚔️ (Срач)",
        "argue": "⚔️ (Срач)",
        "tech": "💾 (Техно)",
        "code": "💾 (IT)",
        "anime": "🌸 (Аниме)",
        "creep": "💀 (Крипота)",
        "dark": "💀 (Мрак)",
        "philosoph": "🧠 (Философия)",
    }
    for key, icon in mapping.items():
        if key in v:
            return icon
    return "❓ (Неясно)"


@app.get("/api/chat/{board_id}")
async def api_get_chat_posts(
    board_id: str,
    request: Request,
    page: int = 0,
    user: dict = Depends(get_current_user_or_guest),
):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")
    observer_id = user["id"]
    limit = 50
    offset = page * limit
    raw_posts = await get_chat_posts_for_board(
        board_id, offset=offset, stream=request.state.stream, observer_id=observer_id
    )
    posts = _convert_and_enrich_posts(raw_posts)

    is_ru = await is_request_from_ru(request)
    await enrich_extra_data(posts, is_ru=is_ru)
    return posts


@app.get("/api/threads/{board_id}")
async def api_get_threads(
    board_id: str,
    request: Request,
    page: int = 0,
    sort: str = "bump",
    page_size: int = 25,
    user: dict = Depends(get_current_user_or_guest),
):
    board_id = board_id.lower()
    if board_id != "overboard" and board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404, detail="Board not found")

    current_version = (
        BOARD_VERSIONS[board_id] if board_id in BOARD_VERSIONS else time.time()
    )
    stream = getattr(request.state, "stream", "ru")
    view_mode = request.query_params.get("view", "threads")
    selected_boards_list = request.query_params.getlist("boards")
    selected_boards_str = ",".join(sorted(selected_boards_list))

    # Ключ кэша теперь учитывает режим отображения (view_mode)
    cache_key = f"api_threads_v3:{board_id}:{view_mode}:{sort}:{page}:{stream}:{current_version}:{selected_boards_str}"

    backend = FastAPICache.get_backend()
    cached_data = await backend.get(cache_key)

    posts_container = []

    if cached_data:
        try:
            posts_container = orjson.loads(cached_data)
        except:
            posts_container = []

    if not posts_container:
        target_board = board_id
        if board_id == "overboard":
            target_board = selected_boards_list if selected_boards_list else None

        if board_id == "overboard" and view_mode in ["posts", "all"]:
            # Режим ленты одиночных постов
            include_chat = view_mode == "all"
            raw_posts = await get_global_feed_posts(
                target_board,
                page=page + 1,
                page_size=page_size,
                stream=stream,
                observer_id=None,  # Для кэша всегда None
                include_chat=include_chat,
                sort_by=sort,
            )
            posts_container = await asyncio.to_thread(
                _convert_and_enrich_posts, raw_posts
            )
        else:
            # Режим списка тредов
            op_posts = await get_op_posts_for_board(
                target_board,
                sort_by=("new" if sort == "new" else "bump"),
                page=page + 1,
                page_size=page_size,
                stream=stream,
                observer_id=None,  # Для кэша всегда None
                ignore_pin=(board_id == "overboard"),
            )
            posts_container = await asyncio.to_thread(
                _convert_and_enrich_posts, op_posts
            )

        await enrich_heavy_data(posts_container)

        if posts_container:
            await backend.set(cache_key, orjson.dumps(posts_container), expire=600)

    # Создаем копию для персонализации (You маркеры и зеркала)
    import copy

    posts_final = copy.deepcopy(posts_container)

    is_ru = await is_request_from_ru(request)
    user_id = user["id"]

    finalize_posts_for_user(posts_final, user_id, is_ru)

    # Проставляем служебные счетчики
    for p in posts_final:
        rc = p.get("reply_count", 0)
        p["posts_count"] = rc + 1
        p["anon_count"] = p.get("anon_count", 1)

    return posts_final


@app.post("/api/report")
@limiter.limit("5/minute")
async def api_report_post(
    data: ReportPost,
    request: Request,
    bg_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_or_guest),
):
    lang = getattr(request.state, "lang", "ru")
    ok_msg = (
        "Report sent"
        if lang == "en"
        else ("通報しました" if lang == "jp" else "Жалоба отправлена")
    )

    if SITE_ACCESS_MODE == "PUBLIC_READ" and user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not data.reason:
        raise HTTPException(status_code=400, detail="Empty reason")
    post = await get_post_by_num(data.post_num)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    sender_hash = str(user["id"])

    success = await create_report(
        data.post_num, data.category, data.reason, sender_hash
    )

    if not success:
        return {"message": ok_msg}

    board = post.get("board_id", "unknown")
    base_url = str(request.base_url).rstrip("/")
    post_link = f"{base_url}/{board}/res/{data.post_num}.html"
    notify_text = (
        f"🚨 <b>Жалоба на пост #{data.post_num}</b>\n\n"
        f"📌 <b>Доска:</b> /{board}/\n"
        f"👤 <b>От:</b> <code>{sender_hash}</code>\n"
        f"📂 <b>Категория:</b> {html.escape(data.category)}\n"
        f"📝 <b>Причина:</b> {html.escape(data.reason)}\n\n"
        f"🔗 <a href='{post_link}'>Перейти к посту</a>"
    )
    bg_tasks.add_task(notify_admins, request.app.state.file_uploader_bot, notify_text)
    return {"message": ok_msg}


@app.get("/api/admin/banned_files")
async def api_get_banned_files(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    return await get_banned_files_list()


class UnbanHashRequest(BaseModel):
    hash_value: str


@app.post("/api/admin/unban_file")
async def api_unban_file(
    data: UnbanHashRequest, user: dict = Depends(get_required_user)
):
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden")
    await unban_hash(data.hash_value)
    log_system_event(
        f"♻️ UNBAN: Hash {data.hash_value[:10]}... unbanned by {user['id']}"
    )
    return {"status": "ok"}


class BanSingleFileRequest(BaseModel):
    file_id: str
    reason: str = "Manual Ban"


@app.post("/api/admin/ban_single_file")
async def api_ban_single_file(
    data: BanSingleFileRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(403, "Forbidden")

    # Чтение (безопасно без лока в WAL)
    db = await get_pool()
    async with db.execute(
        "SELECT sha256, phash FROM FileRegistry WHERE file_id = ?", (data.file_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return {"status": "error", "message": "File not found in registry"}

    sha, phash = row
    from common.database import ban_hash

    # ban_hash уже использует db_lock и BEGIN IMMEDIATE
    if sha:
        await ban_hash(sha, "sha256", data.reason)
    if phash:
        await ban_hash(phash, "phash", data.reason)

    log_system_event(f"🚫 FILE BAN: {data.file_id} banned by {user['id']}")
    return {"status": "ok", "message": "File banned (SHA + pHash)"}


@app.get("/api/admin/reports")
async def api_admin_get_reports(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    return await get_active_reports()


class ResolveReportRequest(BaseModel):
    report_id: int
    action: str


@app.post("/api/admin/resolve_report")
async def api_admin_resolve_report(
    data: ResolveReportRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "janitor"):
        raise HTTPException(status_code=403, detail="Нужен ранг Janitor")
    if data.action == "dismiss":
        await resolve_report(data.report_id, "dismissed")
        return {"status": "dismissed"}
    await resolve_report(data.report_id, "resolved")
    return {"status": "resolved"}


@app.post("/api/admin/endless_thread")
async def api_admin_endless_thread(
    data: AdminEndlessRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(status_code=403, detail="Нужен ранг Moderator")
    from common.database import toggle_thread_endless, trim_thread_posts

    await toggle_thread_endless(data.thread_id, data.endless)
    if data.endless:
        spawn_task(trim_thread_posts(data.thread_id, max_posts=1000))
    status = "endless (cyclic)" if data.endless else "normal"
    log_system_event(f"🔄 ENDLESS: Thread {data.thread_id} is now {status}")
    return {"status": "ok"}


@app.post("/api/admin/delete_post")
@limiter.limit("30/minute")
async def api_admin_delete_post(
    data: AdminAction, request: Request, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "janitor"):
        raise HTTPException(status_code=403, detail="Нужен ранг Janitor")

    post = await get_post_by_num(data.post_num)
    if not post:
        raise HTTPException(404, "Post not found")

    # 1. Удаление из БД (посты и файлы)
    if await delete_post_by_num(data.post_num):
        # 2. Обновление счетчика постов в треде (БЫЛО ВЫРЕЗАНО, ВЕРНУЛ)
        if post.get("thread_id") and str(post["thread_id"]) != str(post["id"]):
            from common.db_pool import get_pool, db_lock

            async with db_lock:
                try:
                    db = await get_pool()
                    await db.execute("BEGIN IMMEDIATE")
                    await db.execute(
                        "UPDATE Threads SET reply_count = MAX(0, reply_count - 1) WHERE thread_id = ?",
                        (str(post["thread_id"]),),
                    )
                    await db.execute("COMMIT")
                except Exception as e:
                    try:
                        await db.execute("ROLLBACK")
                    except:
                        pass
                    logger.error(f"Counter decrement error: {e}")

        # 3. Инвалидация кэша (чтобы пост исчез сразу после F5)
        now = time.time()
        bid = post["board_id"]
        tid = str(post.get("thread_id") or post["id"])

        BOARD_VERSIONS[bid] = now
        BOARD_VERSIONS["overboard"] = now
        THREAD_VERSIONS[tid] = now

        from fastapi_cache import FastAPICache

        # Чистим кэш конкретной ручки API для этого поста
        await FastAPICache.clear(namespace="main", key=f"api_get_post:{data.post_num}")
        # Чистим HTML страницы треда во всех переводах
        for s in ["ru", "en", "jp"]:
            await FastAPICache.clear(
                namespace="main", key=f"thread_html:{bid}:{tid}:{s}"
            )

        log_system_event(f"🗑️ DEL: Post #{data.post_num} deleted by {user.get('id')}")
        # Уведомляем открытые вкладки через WS
        spawn_task(manager.broadcast_system_event("delete", data.post_num, bid))
        return {"message": "Deleted"}

    raise HTTPException(status_code=500, detail="Error deleting post")


@app.post("/api/admin/delete_after")
async def api_admin_delete_after(
    data: AdminDeleteAfterRequest, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "janitor"):
        raise HTTPException(status_code=403, detail="Нужен ранг Janitor")
    from common.database import delete_posts_in_thread_after

    await delete_posts_in_thread_after(data.thread_id, data.post_num)
    log_system_event(
        f"✂️ CUT: Thread {data.thread_id} cut after {data.post_num} by admin"
    )
    return {"status": "ok", "message": "Посты удалены"}


@app.post("/api/admin/ban_user")
@limiter.limit("30/minute")
async def api_admin_ban_user(
    data: HardBanRequest, request: Request, user: dict = Depends(get_required_user)
):
    if not check_perm(user, "mod"):
        raise HTTPException(403, "Forbidden")
    post = await get_post_by_num(data.post_num)
    if not post:
        raise HTTPException(404, "Post not found")
    victim_role = await get_user_role(post["author_id"])
    my_level = ROLE_HIERARCHY.get(user.get("role", "user"), 0)
    victim_level = ROLE_HIERARCHY.get(victim_role, 0)
    if user["id"] not in ADMIN_IDS and victim_level >= my_level:
        raise HTTPException(403, "Нельзя банить равного или старшего по званию!")
    target_board = post["board_id"] if data.scope == "current" else "ALL"
    if await ban_user_on_board(post["author_id"], target_board):
        await delete_post_by_num(data.post_num)
        log_system_event(f"🔨 HARD BAN: User {post['author_id']} on {target_board}")
        return {"message": "Banned & Deleted"}
    raise HTTPException(500, "Failed")


class BanImageRequest(BaseModel):
    post_num: int
    reason: str = "Wipe/Spam"


@app.post("/api/admin/ban_image")
async def api_admin_ban_image(
    data: BanImageRequest, user: dict = Depends(get_required_user)
):
    """
    Банит все файлы из указанного поста по их хешу (SHA256 и pHash).
    Больше эту картинку (и похожие) никто не загрузит.
    """
    if not check_perm(user, "mod"):
        raise HTTPException(403, "Forbidden")
    post = await get_post_by_num(data.post_num)
    if not post:
        raise HTTPException(404, "Post not found")
    content = post.get("content", {})
    files = content.get("files", [])
    if not files:
        return {"status": "error", "message": "No files in post"}
    banned_count = 0
    db = await get_pool()
    try:
        for f in files:
            fid = f.get("original_file_id")
            if fid:
                async with db.execute(
                    "SELECT sha256, phash FROM FileRegistry WHERE file_id = ?", (fid,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        sha, phash = row
                        if sha:
                            from common.database import ban_hash

                            await ban_hash(sha, "sha256", data.reason)
                            banned_count += 1
                        if phash:
                            await ban_hash(phash, "phash", data.reason)
        await delete_post_by_num(data.post_num)
    except Exception as e:
        logger.error(f"Image Ban Error: {e}")
        raise HTTPException(500, "DB Error")
    log_system_event(
        f"🚫 IMG BAN: Banned files from post #{data.post_num} by {user['id']}"
    )
    return {"status": "ok", "count": banned_count}


@app.post("/api/bottle/send")
@limiter.limit("1/minute", key_func=get_user_id_from_session)
async def api_send_bottle(
    data: BottleSendRequest,
    request: Request,
    user: dict = Depends(get_current_user_or_guest),
):
    lang = getattr(request.state, "lang", "ru")
    if SITE_ACCESS_MODE == "PUBLIC_READ" and user.get("is_guest"):
        msg = (
            "Token required"
            if lang == "en"
            else ("トークンが必要です" if lang == "jp" else "Нужен токен")
        )
        raise HTTPException(status_code=403, detail=msg)
    sender = int(user["id"])
    post = await get_post_by_num(data.post_num)
    if not post:
        msg = (
            "Post not found"
            if lang == "en"
            else ("投稿が見つかりません" if lang == "jp" else "Пост не найден")
        )
        raise HTTPException(status_code=404, detail=msg)
    recipient = post.get("author_id")
    if not recipient or recipient == sender:
        msg = (
            "Invalid recipient"
            if lang == "en"
            else (
                "無効な受信者です" if lang == "jp" else "Нельзя отправить самому себе"
            )
        )
        raise HTTPException(status_code=400, detail=msg)
    if not data.text.strip() or len(data.text) > 280:
        msg = (
            "Invalid text"
            if lang == "en"
            else ("テキストが無効です" if lang == "jp" else "Некорректный текст")
        )
        raise HTTPException(status_code=400, detail=msg)
    if await create_bottle(sender, recipient, data.text.strip()):
        ok_msg = (
            "Sent"
            if lang == "en"
            else ("送信しました" if lang == "jp" else "Отправлено")
        )
        return {"message": ok_msg}
    msg = "Failed" if lang == "en" else ("失敗しました" if lang == "jp" else "Ошибка")
    raise HTTPException(status_code=500, detail=msg)


@app.get("/api/bottle/count")
async def api_check_bottles(user: dict = Depends(get_required_user)):
    count = await get_unread_bottle_count(int(user["id"]))
    return {"count": count}


@app.get("/api/bottle/read")
async def api_read_bottle(request: Request, user: dict = Depends(get_required_user)):
    res = await read_and_delete_bottle(int(user["id"]))
    lang = getattr(request.state, "lang", "ru")
    empty_msg = "Empty" if lang == "en" else ("空です" if lang == "jp" else "Пусто")
    return res or {"message": empty_msg}


@app.post("/auth/token")
@limiter.limit("15/minute")
async def auth_by_token(data: TokenAuth, request: Request):
    lang = getattr(request.state, "lang", "ru")
    if not data.token.strip():
        msg = (
            "Empty token"
            if lang == "en"
            else ("トークンが空です" if lang == "jp" else "Пустой токен")
        )
        raise HTTPException(status_code=400, detail=msg)
    u = await get_user_by_token(data.token.strip())
    if not u:
        msg = (
            "Invalid token"
            if lang == "en"
            else ("無効なトークンです" if lang == "jp" else "Неверный токен")
        )
        raise HTTPException(status_code=403, detail=msg)
    uid = int(u["user_id"])
    is_admin_hard = uid in ADMIN_IDS
    role_db = await get_user_role(uid)
    is_admin = is_admin_hard or role_db == "admin"
    is_mod = role_db == "mod"
    request.session["user"] = {
        "id": uid,
        "role": role_db,
        "is_admin": role_db == "admin" or uid in ADMIN_IDS,
    }
    success_msg = (
        "Auth successful"
        if lang == "en"
        else ("認証成功" if lang == "jp" else "Успешный вход")
    )
    return {"message": success_msg}


@app.post("/api/get-my-posts")
async def api_get_my_posts(
    post_nums: List[int] = Body(...), user: dict = Depends(get_current_user_or_guest)
):
    return await get_user_posts_from_list(int(user["id"]), post_nums)


GLOBAL_HTTP_SESSION: Optional[aiohttp.ClientSession] = None


async def _fetch_telegram_path(file_id: str, bot_token: str):
    global GLOBAL_HTTP_SESSION
    if GLOBAL_HTTP_SESSION is None or GLOBAL_HTTP_SESSION.closed:
        # family=socket.AF_INET ЗАСТАВЛЯЕТ ИСПОЛЬЗОВАТЬ IPv4 (Лечит проблемы с VPN)
        connector = aiohttp.TCPConnector(
            limit=250, ttl_dns_cache=300, family=socket.AF_INET
        )
        GLOBAL_HTTP_SESSION = aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=10)
        )

    async with TELEGRAM_FILE_SEMAPHORE:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
            # Убираем прокси из аргументов, раз у тебя TUN VPN
            async with GLOBAL_HTTP_SESSION.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data["result"]["file_path"] if data.get("ok") else None
        except Exception:
            return None


def _bot_id_from_token(token: str | None) -> int | None:
    if not token or ":" not in str(token):
        return None
    try:
        return int(str(token).split(":", 1)[0])
    except (TypeError, ValueError):
        return None


def _iter_known_file_bot_tokens(
    allow_protected_tokens: bool = False,
) -> list[tuple[int | None, str]]:
    candidates: list[tuple[int | None, str]] = []
    seen_tokens = set()

    def add_token(token: str | None, bot_id: int | None = None):
        token = str(token or "").strip()
        if not token or ":" not in token or token in seen_tokens:
            return
        seen_tokens.add(token)
        candidates.append((bot_id or _bot_id_from_token(token), token))

    if global_bot_pool:
        for bot in getattr(global_bot_pool, "all_bots", []) or []:
            add_token(getattr(bot, "token", None), getattr(bot, "id", None))

    add_token(FILE_UPLOADER_BOT_TOKEN)

    if allow_protected_tokens:
        for board in (BOARD_CONFIG or {}).values():
            if isinstance(board, dict):
                add_token(board.get("token"))

    return candidates


def _resolve_known_file_bot_token(
    bot_id: int | None, allow_protected_tokens: bool = False
) -> str | None:
    if not bot_id:
        return None
    if global_bot_pool:
        bot = global_bot_pool.get_bot_by_id(bot_id)
        if bot:
            return getattr(bot, "token", None)
    for candidate_id, token in _iter_known_file_bot_tokens(
        allow_protected_tokens=allow_protected_tokens
    ):
        if candidate_id == bot_id:
            return token
    return None


async def get_cached_file_path(
    file_id: str, allow_protected_tokens: bool = False
) -> tuple[str, str] | None:
    backend = FastAPICache.get_backend()
    dead_key = (
        f"dead_file:{'protected' if allow_protected_tokens else 'public'}:{file_id}"
    )
    cached_path = await backend.get(f"fpath:{file_id}")
    if cached_path:
        p, bot_id_text = cached_path.split("|", 1)
        try:
            cached_bot_id = int(bot_id_text)
        except ValueError:
            cached_bot_id = None
        token = _resolve_known_file_bot_token(
            cached_bot_id, allow_protected_tokens=allow_protected_tokens
        )
        if token:
            return p, token

    if await backend.get(dead_key):
        return None

    # ПРАВКА: Пытаемся получить владельца несколько раз, если база занята
    owner_id = await get_file_owner_id(file_id)
    tried_tokens = set()

    # ПРАВКА: Функция-хелпер для сохранения успеха
    async def save_success(path, token, bot_id=None):
        if bot_id:
            await backend.set(f"fpath:{file_id}", f"{path}|{bot_id}", expire=3600)
            await register_file_owner(file_id, bot_id)
        return path, token

    # Пробуем владельца
    if owner_id:
        owner_token = _resolve_known_file_bot_token(
            owner_id, allow_protected_tokens=allow_protected_tokens
        )
        if owner_token:
            path = await _fetch_telegram_path(file_id, owner_token)
            if path:
                return await save_success(path, owner_token, owner_id)
            tried_tokens.add(owner_token)

    # Пробуем основного бота
    if global_bot_pool:
        main_bot = global_bot_pool.get_main_bot()
        if main_bot and main_bot.token not in tried_tokens:
            path = await _fetch_telegram_path(file_id, main_bot.token)
            if path:
                return await save_success(path, main_bot.token, main_bot.id)
            tried_tokens.add(main_bot.token)

    # Historical bot media often lacks FileOwners rows. Probe the whole pool in
    # small batches, then cache the discovered owner for future requests.
    if global_bot_pool:

        async def try_bot_batch(bot_tokens, batch_size: int = 4):
            candidates = []
            for bot_id, token in bot_tokens:
                if not token or token in tried_tokens:
                    continue
                tried_tokens.add(token)
                candidates.append((bot_id, token))

            async def fetch_with_bot(bot_id, token):
                path = await _fetch_telegram_path(file_id, token)
                if not path:
                    return None
                return path, token, bot_id

            for start in range(0, len(candidates), batch_size):
                tasks = [
                    spawn_task(fetch_with_bot(bot_id, token))
                    for bot_id, token in candidates[start : start + batch_size]
                ]
                try:
                    for task in asyncio.as_completed(tasks):
                        result = await task
                        if result:
                            for pending in tasks:
                                if not pending.done():
                                    pending.cancel()
                            await asyncio.gather(*tasks, return_exceptions=True)
                            return await save_success(*result)
                finally:
                    pending_tasks = [task for task in tasks if not task.done()]
                    for pending in pending_tasks:
                        pending.cancel()
                    if pending_tasks:
                        await asyncio.gather(*pending_tasks, return_exceptions=True)
            return None

        for stream_code in ("ru", "en", "jp"):
            try:
                global_bot_pool.init_stream(stream_code)
            except Exception:
                pass
        all_bot_tokens = _iter_known_file_bot_tokens(
            allow_protected_tokens=allow_protected_tokens
        )
        random.shuffle(all_bot_tokens)
        result = await try_bot_batch(all_bot_tokens)
        if result:
            return result
        if all_bot_tokens:
            await backend.set(dead_key, "1", expire=120)

    # No mirror or bot path is available right now. Positive hits are cached by
    # owner; full-pool misses are briefly negative-cached above to avoid hammering.
    return None


async def _is_random_file_available(file_id: str | None) -> bool:
    if not file_id or _is_random_dead_file(file_id):
        return False

    try:
        mirrors = await get_file_mirrors(file_id)
    except Exception:
        mirrors = {}

    if (
        mirrors.get("catbox")
        or mirrors.get("0x0")
        or is_hf_link_allowed(mirrors.get("huggingface"), VALID_HF_REPOS)
    ):
        return True

    if await get_cached_file_path(file_id):
        return True

    shadow_file_id = mirrors.get("tg_shadow")
    if shadow_file_id:
        if await get_cached_file_path(shadow_file_id):
            return True
        if await get_cached_file_path(shadow_file_id, allow_protected_tokens=True):
            return True

    if await get_cached_file_path(file_id, allow_protected_tokens=True):
        return True

    _mark_random_dead_file(file_id)
    if shadow_file_id:
        _mark_random_dead_file(shadow_file_id)
    return False


async def _is_random_file_available_with_deadline(
    file_id: str | None, deadline: float
) -> bool:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    timeout = min(RANDOM_AVAILABILITY_TIMEOUT_SEC, max(0.25, remaining))
    try:
        return await asyncio.wait_for(
            _is_random_file_available(file_id), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.debug(f"Random media availability timeout for {str(file_id)[:10]}")
        return False
    except Exception as e:
        logger.warning(f"Random media availability check failed: {type(e).__name__}")
        return False


async def _proxy_protected_telegram_file(
    file_id: str,
    file_path: str,
    token: str,
    filename: str | None = None,
    request: Request | None = None,
):
    try:
        await add_to_mirror_queue(file_id, "catbox")
    except Exception:
        pass

    timeout = aiohttp.ClientTimeout(total=180, sock_connect=10, sock_read=30)
    connector = aiohttp.TCPConnector(limit=1, ttl_dns_cache=300, family=socket.AF_INET)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    try:
        request_headers = {}
        if request:
            range_header = request.headers.get("range")
            if range_header:
                request_headers["Range"] = range_header
        resp = await session.get(url, headers=request_headers)
    except Exception:
        await session.close()
        raise HTTPException(status_code=404, detail="File unavailable.")

    if resp.status not in (200, 206):
        resp.release()
        await session.close()
        raise HTTPException(status_code=404, detail="File unavailable.")

    closed = False

    async def close_upstream():
        nonlocal closed
        if closed:
            return
        closed = True
        resp.release()
        await session.close()

    try:
        guessed_type = mimetypes.guess_type(filename or file_path)[0]
        media_type = resp.headers.get("Content-Type")
        if not media_type or media_type == "application/octet-stream":
            media_type = guessed_type or media_type or "application/octet-stream"

        headers = {
            "Accept-Ranges": resp.headers.get("Accept-Ranges", "bytes"),
            "Cache-Control": "public, max-age=300",
        }
        for header_name in ("Content-Length", "Content-Range", "Last-Modified", "ETag"):
            value = resp.headers.get(header_name)
            if value:
                headers[header_name] = value
    except Exception:
        await close_upstream()
        raise

    async def body_iter():
        try:
            async for chunk in resp.content.iter_chunked(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            await close_upstream()

    return StreamingResponse(
        body_iter(),
        status_code=resp.status,
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(close_upstream),
    )


@app.get("/games/abu")
async def game_abu_page(
    request: Request, user: dict | None = Depends(get_optional_user)
):
    return templates.TemplateResponse(
        request=request,
        name="game_abu.jinja2",
        context={"request": request, "user": user, "site_mode": SITE_ACCESS_MODE},
    )


URL_STATUS_CACHE = {}


async def check_url_alive(url: str) -> bool:
    if len(URL_STATUS_CACHE) > 5000:
        URL_STATUS_CACHE.clear()
    now = time.time()
    if url in URL_STATUS_CACHE:
        is_alive, ts = URL_STATUS_CACHE[url]
        if now - ts < 600:
            return is_alive
    try:
        async with httpx.AsyncClient(timeout=1.5, verify=False) as client:
            resp = await client.head(url)
            is_alive = resp.status_code == 200
            URL_STATUS_CACHE[url] = (is_alive, now)
            return is_alive
    except:
        URL_STATUS_CACHE[url] = (False, now)
        return False


@app.get("/files/{file_id:path}")
async def get_telegram_file(file_id: str, request: Request, filename: str = None):
    # Очистка file_id от лишних слешей и сегментов пути
    file_id = file_id.lstrip("/")
    if "/" in file_id:
        file_id, path_filename = file_id.split("/", 1)
        filename = filename or path_filename.rsplit("/", 1)[-1]

    # Если file_id уже является полной ссылкой, перенаправляем
    if file_id.startswith(("http://", "https://")):
        return RedirectResponse(url=file_id, status_code=301)

    # Динамическое определение страны по IP
    client_ip = get_real_ip(request)
    user_country = await get_country_by_ip(client_ip)
    is_ru = user_country == "RU"
    if user_country == "XX" or client_ip in ("127.0.0.1", "localhost", "::1"):
        accept_lang = request.headers.get("accept-language", "").lower()
        if "ru" in accept_lang or not accept_lang:
            is_ru = True

    # Заголовки против кэширования редиректов
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    # --- SMART WAIT LOOP ---
    # Ждем до 2.5 секунд появления зеркал или кэша пути.
    # Это спасает от 404 сразу после постинга.
    backend = FastAPICache.get_backend()
    mirrors = {}

    # ПРАВКА: Видео через Bot API не прогрузятся, поэтому для них ждем HF дольше (до 7.5 сек)
    is_video_ext = any(
        x in request.url.path.lower() for x in ["mp4", "webm", "mov", "gif"]
    )
    max_attempts = 15 if is_video_ext else 8

    for attempt in range(max_attempts):
        # 1. Проверяем зеркала в кэше/БД
        cache_key = f"mirrors:{file_id}"
        if backend:
            cached = await backend.get(cache_key)
            if cached:
                try:
                    mirrors = json.loads(cached)
                except:
                    mirrors = {}

        if not mirrors:
            mirrors = await get_file_mirrors(file_id)
            if mirrors and backend:
                await backend.set(cache_key, json.dumps(mirrors), expire=900)

        # Проверка валидности HF (из глобального списка VALID_HF_REPOS)
        hf_candidate = mirrors.get("huggingface")
        hf_valid = is_hf_link_allowed(hf_candidate, VALID_HF_REPOS)

        # 1. Сначала проверяем зеркала
        catbox_link = mirrors.get("catbox")
        zeroxzero_link = mirrors.get("0x0")
        if (is_ru and hf_valid) or (
            not is_ru and (catbox_link or hf_valid or zeroxzero_link)
        ):
            break

        # 2. Если файл новый (нет в кэше зеркал), пробуем Telegram СРАЗУ
        cached_path_info = await get_cached_file_path(file_id)
        if cached_path_info:
            break

        # Если это первая попытка и файл - картинка (AgAC), пробуем форсировать путь
        if attempt == 0 and file_id.startswith("AgAC"):
            cached_path_info = await get_cached_file_path(file_id)
            if cached_path_info:
                break  # Путь есть, можно отдавать

        # Если ничего нет - ждем
        if attempt < 7:
            await asyncio.sleep(0.5)

    # Извлечение (повторное для надежности)
    hf_link = mirrors.get("huggingface")
    catbox_link = mirrors.get("catbox")
    zeroxzero_link = mirrors.get("0x0")
    shadow_file_id = mirrors.get("tg_shadow")

    # 1. Telegram Direct — ПРИОРИТЕТ №1 (Если путь закеширован)
    info = await get_cached_file_path(file_id, allow_protected_tokens=True)
    if info:
        path, token = info
        return RedirectResponse(
            url=f"https://api.telegram.org/file/bot{token}/{path}",
            status_code=307,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    # 2. HuggingFace — ПРИОРИТЕТ №2 (Для РФ и ИНО, если доступен)
    if is_hf_link_allowed(hf_link, VALID_HF_REPOS):
        return RedirectResponse(url=hf_link, status_code=307, headers=no_cache_headers)

    # 3. Catbox — ПРИОРИТЕТ №3 для ИНО (В РФ пропускаем)
    if catbox_link and not is_ru:
        return RedirectResponse(
            url=catbox_link, status_code=307, headers=no_cache_headers
        )

    # 4. 0x0 — ПРИОРИТЕТ №4 для ИНО (В РФ пропускаем)
    if zeroxzero_link and not is_ru:
        return RedirectResponse(
            url=zeroxzero_link, status_code=307, headers=no_cache_headers
        )

    # 4. Shadow Telegram (Резервный прокси)
    if shadow_file_id:
        info_shadow = await get_cached_file_path(shadow_file_id)
        if info_shadow:
            path, token = info_shadow
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=3600"},
            )

    # Protected archive/chat bots must never be exposed in browser redirects.
    # Use them only as a server-side fallback and enqueue a public mirror.
    protected_candidates = []
    if shadow_file_id:
        protected_candidates.append(shadow_file_id)
    protected_candidates.append(file_id)
    seen_protected = set()
    for protected_file_id in protected_candidates:
        if not protected_file_id or protected_file_id in seen_protected:
            continue
        seen_protected.add(protected_file_id)
        protected_info = await get_cached_file_path(
            protected_file_id, allow_protected_tokens=True
        )
        if protected_info:
            path, token = protected_info
            try:
                return await _proxy_protected_telegram_file(
                    protected_file_id, path, token, filename, request
                )
            except HTTPException:
                _mark_random_dead_file(protected_file_id)
                continue

    # 5. Catbox для РФ — ПОСЛЕДНИЙ ШАНС (Если HF и TG лежат)
    if catbox_link:
        return RedirectResponse(
            url=catbox_link, status_code=307, headers=no_cache_headers
        )

    if zeroxzero_link:
        return RedirectResponse(
            url=zeroxzero_link, status_code=307, headers=no_cache_headers
        )

    # Если совсем всё плохо
    _mark_random_dead_file(file_id)
    if shadow_file_id:
        _mark_random_dead_file(shadow_file_id)
    raise HTTPException(status_code=404, detail="File unavailable.")


@app.post("/api/react")
@limiter.limit("20/minute", key_func=get_user_id_from_session)
async def api_add_reaction(
    data: ReactionRequest,
    request: Request,
    user: dict = Depends(get_current_user_or_guest),
):
    if SITE_ACCESS_MODE == "PUBLIC_READ" and user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Forbidden")
    uid = int(user["id"])
    post = await get_post_by_num(data.post_num)
    if not post or "content" not in post:
        raise HTTPException(status_code=404, detail="Post not found")
    content = post["content"]
    content.setdefault("reactions", {}).setdefault("users", {})
    user_reactions = content["reactions"]["users"].get(str(uid), [])
    if data.emoji in user_reactions:
        user_reactions.remove(data.emoji)
    elif len(user_reactions) < 2:
        user_reactions.append(data.emoji)
    content["reactions"]["users"][str(uid)] = user_reactions
    await update_post_content(data.post_num, content)
    broadcast_data = await get_post_for_broadcast(data.post_num)
    if broadcast_data:
        await request.app.state.broadcast_queue.put(broadcast_data)
    return {"status": "success"}


from common.database import save_poll_vote_db


@app.post("/api/poll/vote")
async def api_poll_vote(
    data: PollVote, request: Request, user: dict = Depends(get_current_user_or_guest)
):
    if SITE_ACCESS_MODE == "PUBLIC_READ" and user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Forbidden")
    uid = int(user["id"])
    post = await get_post_by_num(data.post_num)
    if not post or "poll_data" not in post.get("content", {}):
        raise HTTPException(status_code=404, detail="Poll not found")
    options_count = len(post["content"]["poll_data"].get("options", []))
    if not (0 <= data.option_index < options_count):
        raise HTTPException(status_code=400, detail="Invalid option")
    success = await save_poll_vote_db(data.post_num, uid, data.option_index)
    if not success:
        raise HTTPException(status_code=403, detail="Already voted")
    broadcast_data = await get_post_for_broadcast(data.post_num)
    if broadcast_data:
        try:
            request.app.state.broadcast_queue.put_nowait(broadcast_data)
        except asyncio.QueueFull:
            logger.warning("Broadcast queue full, update dropped")
    return {"status": "success"}


@app.post("/api/favourites")
async def api_get_favourite_threads(data: FavouriteThreads):
    if not data.thread_ids:
        return []
    db = await get_pool()
    clean_ids = [int(tid) for tid in data.thread_ids if str(tid).isdigit()]
    if not clean_ids:
        return []

    placeholders = ",".join("?" for _ in clean_ids)
    query = f"""
        SELECT 
            p.post_num, p.board_id, p.content, p.timestamp, p.author_id, 
            t.is_archived, t.is_pinned, t.is_endless, t.thread_type,
            p.is_shadow, p.is_op_hidden, p.stream
        FROM Posts p 
        JOIN Threads t ON p.post_num = t.thread_num 
        WHERE p.post_num IN ({placeholders})
    """

    try:
        async with db.execute(query, clean_ids) as cursor:
            rows = await cursor.fetchall()
            res = []
            for r in rows:
                try:
                    content = json.loads(r[2]) if isinstance(r[2], str) else r[2]
                except:
                    content = {"text": "❌ Какая-то хуйня с данными.", "type": "text"}

                res.append(
                    {
                        "id": r[0],
                        "board_id": r[1],
                        "content": content,
                        "timestamp": r[3],
                        "author_id": r[4],
                        "is_archived": bool(r[5]),
                        "is_pinned": bool(r[6]),
                        "is_endless": bool(r[7]),
                        "thread_type": r[8] or "default",
                        "is_shadow": bool(r[9]),
                        "is_op_hidden": bool(r[10]),
                        "stream": r[11] or "ru",
                    }
                )
            posts = _convert_and_enrich_posts(res)
            await enrich_extra_data(posts)
            for post in posts:
                post["reply_count"] = 0
                post["posts_count"] = 1
                post["anon_count"] = 1
            return posts
    except Exception as e:
        print(f"🔴 Ошибка API избранного: {e}")
        return []


@app.post("/api/get-thread-ids")
async def api_get_thread_ids(data: PostNumsRequest):
    if not data.post_nums:
        return {}
    return await get_thread_ids_for_posts(list(set(data.post_nums))[:100])


@app.post("/api/admin/wipe_user")
async def api_admin_wipe(
    data: dict = Body(...), user: dict | None = Depends(get_optional_user)
):
    if not check_perm(user, "admin"):
        raise HTTPException(status_code=403, detail="Нужен ранг Admin")
    pid = data.get("post_num")
    if not pid:
        raise HTTPException(status_code=400, detail="No post ID")

    from common.db_pool import (
        get_db_connection as get_pool_conn,
    )  # Или просто get_pool, но тут использовался контекст

    # В оригинале использовался get_db_connection() который создает новое соединение.
    # Чтобы использовать db_lock эффективно, лучше использовать get_pool().

    from common.db_pool import get_pool, db_lock

    async with db_lock:
        try:
            db = await get_pool()
            # Чтение можно без транзакции, если мы не боимся фантомов, но для вайпа лучше сразу залочить
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT author_id FROM Posts WHERE post_num = ?", (pid,)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                await db.execute("COMMIT")
                raise HTTPException(status_code=404, detail="Not found")

            author_id = row[0]
            await db.execute("DELETE FROM Posts WHERE author_id = ?", (author_id,))
            await db.execute("DELETE FROM Threads WHERE op_id = ?", (author_id,))

            await db.execute("COMMIT")

            log_system_event(f"☢️ WIPE: User {author_id} wiped completely.")
            return {"status": "ok"}

        except HTTPException:
            raise
        except Exception as e:
            try:
                await db.execute("ROLLBACK")
            except:
                pass
            logger.error(f"Wipe error: {e}")
            raise HTTPException(status_code=500, detail="DB Error")


@app.get("/api/admin/alerts_history")
async def api_admin_alerts_history(user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    alerts = await get_all_alerts_for_admin(limit=50)
    return alerts


@app.get("/api/admin/users/{board_id}")
@cache(expire=10)
async def api_admin_get_users(board_id: str, user: dict = Depends(get_required_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=404, detail="Not Found")
    return {
        "banned": await get_banned_users(board_id),
        "shadow": await get_shadow_muted_users(board_id),
    }


@app.post("/api/admin/shadow_ban")
async def api_shadow_ban(
    data: ShadowBanRequest, user: dict = Depends(get_required_user)
):
    """
    Выдает теневой бан.
    Логика:
    1. Если передан post_num > 0 -> ищем автора этого поста.
    2. Если post_num == 0 -> используем data.target как прямой ID пользователя.
    """
    if not check_perm(user, "mod"):
        raise HTTPException(
            status_code=403, detail="Недостаточно прав (нужен Moderator)"
        )
    user_id_to_ban = None
    board_id_of_post = None
    if data.post_num > 0:
        post = await get_post_by_num(data.post_num)
        if not post:
            raise HTTPException(
                status_code=404, detail=f"Пост №{data.post_num} не найден."
            )
        user_id_to_ban = post["author_id"]
        board_id_of_post = post["board_id"]
    else:
        target_str = data.target.strip()
        if target_str.startswith("#") or target_str.startswith("№"):
            try:
                p_num = int(re.sub(r"\D", "", target_str))
                post = await get_post_by_num(p_num)
                if not post:
                    raise HTTPException(
                        status_code=404, detail=f"Пост {target_str} не найден."
                    )
                user_id_to_ban = post["author_id"]
                board_id_of_post = post["board_id"]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Неверный формат номера поста в поле target.",
                )
        else:
            try:
                user_id_to_ban = int(target_str)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Укажите ID пользователя в поле target или номер поста.",
                )
    if not user_id_to_ban or user_id_to_ban == 0:
        raise HTTPException(
            status_code=400, detail="Не удалось определить ID пользователя для бана."
        )
    if data.scope == "global":
        target_board = "ALL"
    else:
        target_board = board_id_of_post if board_id_of_post else "b"
    expires_at = time.time() + data.duration
    try:
        from common.database import update_shadow_mute

        await update_shadow_mute(user_id_to_ban, target_board, expires_at)
        from common.db_pool import db_lock

        async with db_lock, get_db_connection() as conn:
            await conn.execute(
                """INSERT INTO AdminActionQueue (action_type, user_id, board_id, expires_at) 
                   VALUES (?, ?, ?, ?)""",
                ("shadow_mute", user_id_to_ban, target_board, expires_at),
            )
            await conn.commit()
        scope_log = (
            "ГЛОБАЛЬНО" if target_board == "ALL" else f"на доске /{target_board}/"
        )
        log_system_event(
            f"👻 SHADOW BAN: Мод {user['id']} забанил {user_id_to_ban} {scope_log} на {data.duration // 60} мин."
        )
        return {
            "status": "ok",
            "user_id": user_id_to_ban,
            "board": target_board,
            "expires": expires_at,
        }
    except Exception as e:
        logger.error(f"Shadow ban error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка базы данных.")


@app.post("/api/admin/lift_ban")
async def api_lift_ban(data: LiftBanRequest, user: dict = Depends(get_required_user)):
    if not check_perm(user, "mod"):
        raise HTTPException(status_code=403, detail="Нужен ранг Moderator")
    if data.ban_type == "ban":
        await lift_ban(data.user_id, data.board_id)
    elif data.ban_type == "shadow":
        await lift_shadow_ban(data.user_id, data.board_id)
    return {"message": "Lifted"}


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    while True:
        try:
            print("🚀 Starting server...")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                reload=False,
                loop="asyncio",
                proxy_headers=True,
                forwarded_allow_ips="*",
                log_config=None,
                access_log=False,
                server_header=False,
                date_header=False,
                timeout_keep_alive=10,
                limit_concurrency=1000,
            )
        except KeyboardInterrupt:
            print("🛑 Server stopped by user.")
            break
        except Exception as e:
            print(f"🔥 Server crashed: {e}")
            print("🔄 Restarting in 3 seconds...")
            time.sleep(3)
