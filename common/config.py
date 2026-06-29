# -*- coding: utf-8 -*-

"""
Центральный файл конфигурации для общих модулей (бот и веб-сайт).
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# 1. СНАЧАЛА определяем корень проекта
PROJECT_ROOT = Path(__file__).parent.parent

# 2. ПОТОМ загружаем .env, используя PROJECT_ROOT
dotenv_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=dotenv_path)

# 3. ПОТОМ уже считываем переменные
BIND_IPV4 = os.getenv("BIND_IPV4", "0.0.0.0")
DB_NAME = PROJECT_ROOT / "dvach_bot.db"
DB_TIMEOUT = 30.0
DB_POST_LIMIT = int(os.getenv("DB_POST_LIMIT", "25000"))
BOT_POST_CACHE_LIMIT = int(os.getenv("BOT_POST_CACHE_LIMIT", "3300"))
BOT_COPY_CACHE_POST_LIMIT = int(os.getenv("BOT_COPY_CACHE_POST_LIMIT", "400"))
POST_COPY_RETENTION_POSTS = int(os.getenv("POST_COPY_RETENTION_POSTS", "12000"))
POST_COPY_RETENTION_DAYS = int(os.getenv("POST_COPY_RETENTION_DAYS", "30"))
BOT_PRIORITY_DELIVERY = os.getenv("BOT_PRIORITY_DELIVERY", "1").lower() not in {"0", "false", "no", "off"}
BOT_WEEKLY_ACTIVE_DAYS = int(os.getenv("BOT_WEEKLY_ACTIVE_DAYS", "7"))
BOT_WEEKLY_ACTIVE_REFRESH_SEC = int(os.getenv("BOT_WEEKLY_ACTIVE_REFRESH_SEC", "900"))
BOT_PRIORITY_SPLIT_FANOUT = os.getenv("BOT_PRIORITY_SPLIT_FANOUT", "1").lower() not in {"0", "false", "no", "off"}
BOT_PRIORITY_SPLIT_MIN_PASSIVE = int(os.getenv("BOT_PRIORITY_SPLIT_MIN_PASSIVE", "30"))
BOT_PRIORITY_PASSIVE_SLICE_SIZE = int(os.getenv("BOT_PRIORITY_PASSIVE_SLICE_SIZE", "90"))
BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE = int(os.getenv("BOT_PRIORITY_PASSIVE_MEDIA_SLICE_SIZE", "40"))
BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC = float(os.getenv("BOT_PRIORITY_PRESSURE_SLICE_AGE_SEC", "600"))
BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE = int(os.getenv("BOT_PRIORITY_PRESSURE_PASSIVE_SLICE_SIZE", "60"))
BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE = int(os.getenv("BOT_PRIORITY_PRESSURE_PASSIVE_MEDIA_SLICE_SIZE", "25"))
BOT_PASSIVE_MAX_PREEMPTIONS = int(os.getenv("BOT_PASSIVE_MAX_PREEMPTIONS", "3"))
BOT_PRIORITY_PHASE_BUDGET_SEC = float(os.getenv("BOT_PRIORITY_PHASE_BUDGET_SEC", "45"))
BOT_PASSIVE_PHASE_BUDGET_SEC = float(os.getenv("BOT_PASSIVE_PHASE_BUDGET_SEC", "25"))
BOT_DELIVERY_SLOW_PHASE_SEC = float(os.getenv("BOT_DELIVERY_SLOW_PHASE_SEC", "10"))
BOT_DELIVERY_INITIAL_CHUNK_SIZE = int(os.getenv("BOT_DELIVERY_INITIAL_CHUNK_SIZE", "12"))
BOT_DELIVERY_MIN_CHUNK_SIZE = int(os.getenv("BOT_DELIVERY_MIN_CHUNK_SIZE", "3"))
BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC = float(os.getenv("BOT_DELIVERY_PER_RECIPIENT_TIMEOUT_SEC", "20"))
BOT_DELIVERY_MAX_RECIPIENT_RETRIES = int(os.getenv("BOT_DELIVERY_MAX_RECIPIENT_RETRIES", "5"))
BOT_DELIVERY_PHASE_GUARD_SEC = float(os.getenv("BOT_DELIVERY_PHASE_GUARD_SEC", "5"))
BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC = float(os.getenv("BOT_CONTROLLED_STOP_DRAIN_TIMEOUT_SEC", "900"))
BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC = float(os.getenv("BOT_CONTROLLED_STOP_LOG_INTERVAL_SEC", "10"))
BOT_DURABLE_DELIVERY_QUEUE = os.getenv("BOT_DURABLE_DELIVERY_QUEUE", "1").lower() not in {"0", "false", "no", "off"}
BOT_B_MAX_STACKED_ANIME_IMAGES = int(os.getenv("BOT_B_MAX_STACKED_ANIME_IMAGES", "10"))
BOT_ANIME_MEDIA_CONCURRENCY = int(os.getenv("BOT_ANIME_MEDIA_CONCURRENCY", "1"))
BOT_ANIME_URL_FETCH_TIMEOUT_SEC = float(os.getenv("BOT_ANIME_URL_FETCH_TIMEOUT_SEC", "12"))
BOT_ANIME_URL_FETCH_TOTAL_SEC = float(os.getenv("BOT_ANIME_URL_FETCH_TOTAL_SEC", "35"))
BOT_ANIME_URL_FETCH_PARALLEL = int(os.getenv("BOT_ANIME_URL_FETCH_PARALLEL", "3"))
BOT_ANIME_DOWNLOAD_TIMEOUT_SEC = float(os.getenv("BOT_ANIME_DOWNLOAD_TIMEOUT_SEC", "35"))
BOT_ANIME_DOWNLOAD_TOTAL_SEC = float(os.getenv("BOT_ANIME_DOWNLOAD_TOTAL_SEC", "45"))
BOT_ANIME_DOWNLOAD_PARALLEL = int(os.getenv("BOT_ANIME_DOWNLOAD_PARALLEL", "2"))
BOT_ANIME_REFILL_ROUNDS = int(os.getenv("BOT_ANIME_REFILL_ROUNDS", "2"))
BOT_MODE_PUNCHUP_ENABLED = os.getenv("BOT_MODE_PUNCHUP_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
BOT_MODE_PUNCHUP_QUEUE_SHED_SEC = float(os.getenv("BOT_MODE_PUNCHUP_QUEUE_SHED_SEC", "8"))
BOT_MODE_PUNCHUP_SLOW_LOG_US = int(os.getenv("BOT_MODE_PUNCHUP_SLOW_LOG_US", "2500"))
BOT_CONTEXTUAL_REPLIES_ENABLED = os.getenv("BOT_CONTEXTUAL_REPLIES_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
BOT_CONTEXTUAL_REPLY_COOLDOWN_SEC = float(os.getenv("BOT_CONTEXTUAL_REPLY_COOLDOWN_SEC", "45"))
BOT_CONTEXTUAL_REPLY_DAILY_LIMIT = int(os.getenv("BOT_CONTEXTUAL_REPLY_DAILY_LIMIT", "80"))

# --- НАСТРОЙКИ МУЛЬТИЯЗЫЧНОСТИ (ПОТОКИ) ---
ENABLE_MULTILANG = False 

# Карта каналов для сохранения файлов (Stream -> Channel ID)
# Теперь os.getenv точно сработает, так как load_dotenv был вызван выше
STORAGE_CHANNELS = {
    'ru': int(os.getenv("FILE_STORAGE_CHANNEL_ID_RU", os.getenv("FILE_STORAGE_CHANNEL_ID", 0))),
    'en': int(os.getenv("FILE_STORAGE_CHANNEL_ID_EN", 0)),
    'jp': int(os.getenv("FILE_STORAGE_CHANNEL_ID_JP", 0)),
}

# Список стран СНГ для автоопределения русского потока (ISO 3166-1 alpha-2)
CIS_COUNTRY_CODES = {'RU', 'UA', 'BY', 'KZ', 'KG', 'TJ', 'UZ', 'AM', 'AZ', 'MD', 'TM'}

# Получение списка ID админов из .env (переменная ADMINS)
# Превращаем строку "123,456" в множество {123, 456}
admin_env = os.getenv("ADMINS", "")
ADMIN_IDS = {int(x.strip()) for x in admin_env.split(",") if x.strip().isdigit()}
