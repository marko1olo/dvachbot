import asyncio
import contextlib
import io
import os
from pathlib import Path
import sys
from unittest import mock

import pytest

# --- Корень проекта ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Список запрещенных боевых БД ---
FORBIDDEN_DB_NAMES = {
    "dvach_bot.db",
    "2d2vach_bot.db",
    "bot_database.db",
    "database.db",
    "dvach.db",
    "dvachbot.db",
    "tgach.db",
    "hecton.db",
    "dvach_bot_backup.db",
    "dvach_bot_backup_audit.db",
    "dvach_bot_backup_before_postcopies_cleanup.db",
    "dvach_bot_backup_pre_repair.db",
    "dvach_bot_copy.db",
    "dvach_bot_stress_backup.db",
}

CRITICAL_ERROR_MSG = "CRITICAL: Production DB / Bot access forbidden in test environment!"


def _check_db_path_forbidden(database):
    """
    Проверяет путь к базе данных. Если попытка открыть боевую БД в корне проекта —
    немедленно бросает RuntimeError.
    """
    if database is None:
        return
    db_str = str(database).strip()
    if db_str == ":memory:" or (db_str.startswith("file:") and "mode=memory" in db_str):
        return

    try:
        resolved = Path(database).resolve()
    except Exception:
        resolved = None

    if resolved is not None:
        if resolved.parent == PROJECT_ROOT and (resolved.suffix == ".db" or resolved.name.lower() in FORBIDDEN_DB_NAMES):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        if resolved == (PROJECT_ROOT / "dvach_bot.db").resolve():
            raise RuntimeError(CRITICAL_ERROR_MSG)
        if resolved.name.lower() in FORBIDDEN_DB_NAMES and resolved.parent == PROJECT_ROOT:
            raise RuntimeError(CRITICAL_ERROR_MSG)
    else:
        if db_str.lower() in FORBIDDEN_DB_NAMES:
            raise RuntimeError(CRITICAL_ERROR_MSG)


# --- Установка хуков на sqlite3 и aiosqlite ---
import sqlite3
_orig_sqlite3_connect = sqlite3.connect

def guarded_sqlite3_connect(database, *args, **kwargs):
    _check_db_path_forbidden(database)
    return _orig_sqlite3_connect(database, *args, **kwargs)

sqlite3.connect = guarded_sqlite3_connect

try:
    import aiosqlite
    _orig_aiosqlite_connect = aiosqlite.connect

    def guarded_aiosqlite_connect(database, *args, **kwargs):
        _check_db_path_forbidden(database)
        return _orig_aiosqlite_connect(database, *args, **kwargs)

    aiosqlite.connect = guarded_aiosqlite_connect
except ImportError:
    pass


# --- Установка хуков на Telegram Bot API / Network ---
try:
    import aiogram.client.session.base as aiogram_base_session
    _orig_make_request = aiogram_base_session.BaseSession.make_request

    async def guarded_make_request(self, bot, method, timeout=None):
        raise RuntimeError(CRITICAL_ERROR_MSG)

    aiogram_base_session.BaseSession.make_request = guarded_make_request
except ImportError:
    pass

try:
    import aiohttp
    _orig_aiohttp_request = aiohttp.ClientSession._request

    async def guarded_aiohttp_request(self, method, str_or_url, *args, **kwargs):
        if "api.telegram.org" in str(str_or_url):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        return await _orig_aiohttp_request(self, method, str_or_url, *args, **kwargs)

    aiohttp.ClientSession._request = guarded_aiohttp_request
except ImportError:
    pass

try:
    import requests
    _orig_requests_send = requests.Session.send

    def guarded_requests_send(self, request, **kwargs):
        if "api.telegram.org" in str(getattr(request, "url", "")):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        return _orig_requests_send(self, request, **kwargs)

    requests.Session.send = guarded_requests_send
except ImportError:
    pass

try:
    import httpx
    _orig_httpx_send = httpx.Client.send

    def guarded_httpx_send(self, request, **kwargs):
        if "api.telegram.org" in str(getattr(request, "url", "")):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        return _orig_httpx_send(self, request, **kwargs)

    httpx.Client.send = guarded_httpx_send

    _orig_httpx_async_send = httpx.AsyncClient.send

    async def guarded_httpx_async_send(self, request, **kwargs):
        if "api.telegram.org" in str(getattr(request, "url", "")):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        return await _orig_httpx_async_send(self, request, **kwargs)

    httpx.AsyncClient.send = guarded_httpx_async_send
except ImportError:
    pass

try:
    import urllib.request
    _orig_urlopen = urllib.request.urlopen

    def guarded_urlopen(url, *args, **kwargs):
        req_url = getattr(url, "full_url", str(url))
        if "api.telegram.org" in str(req_url):
            raise RuntimeError(CRITICAL_ERROR_MSG)
        return _orig_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen
except ImportError:
    pass


try:
    import site_tgach
    sys.modules['Dubsite_tgach'] = site_tgach
except ImportError:
    pass


# --- Защита от выселения нативных модулей из sys.modules -------------------
for _module_name in ("numpy", "scipy", "scipy.stats", "pandas", "matplotlib",
                     "matplotlib.pyplot", "seaborn", "PIL.Image"):
    try:
        __import__(_module_name)
    except ImportError:
        pass
del _module_name

# Снимок настоящих модулей, пока ни один тестовый файл ещё не импортирован.
_PRISTINE_MODULES = dict(sys.modules)


@pytest.fixture(autouse=True)
def _restore_pristine_modules():
    """
    Возвращает подменённые модули на место перед каждым тестом и перепроверяет
    установку защитных хуков.
    """
    for _name, _real in _PRISTINE_MODULES.items():
        if sys.modules.get(_name) is not _real:
            sys.modules[_name] = _real

    # Гарантируем, что защитные хуки всегда активны
    sqlite3.connect = guarded_sqlite3_connect
    if 'aiosqlite' in sys.modules:
        import aiosqlite
        aiosqlite.connect = guarded_aiosqlite_connect

    try:
        import shared_state
        shared_state.combat_cooldowns.clear()
        shared_state._attacker_effects.clear()
        shared_state._target_attacks.clear()
    except Exception:
        pass
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_event_loop():
    import logging
    # Изоляция боевых логов от тестового загрязнения (MagicMock, test exceptions)
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        if isinstance(h, logging.FileHandler):
            root_logger.removeHandler(h)
    null_h = logging.NullHandler()
    root_logger.addHandler(null_h)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


try:
    import pytest_asyncio
    _fixture_decorator = pytest_asyncio.fixture
except ImportError:
    _fixture_decorator = pytest.fixture


@_fixture_decorator
async def isolated_test_db(tmp_path):
    """
    Фикстура для создания изолированной временной БД с полной схемой проекта.
    Никогда не касается боевой базы.
    """
    import aiosqlite
    import common.config
    import common.database
    import common.db_pool

    db_path = str(tmp_path / "isolated_test.db")
    db = await aiosqlite.connect(db_path, timeout=30.0, isolation_level=None)
    await db.execute("PRAGMA busy_timeout = 30000;")
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys = ON;")
    await db.execute("BEGIN IMMEDIATE")
    with contextlib.redirect_stdout(io.StringIO()):
        await common.database._create_tables(db)
        await common.database._apply_migrations(db)
        await common.database._create_indices(db)
        await common.database._create_triggers(db)
        await common.database._insert_initial_data(db)
    await db.execute("COMMIT")

    saved_conn = common.db_pool._db_connection
    common.db_pool._db_connection = db
    pool_stub = mock.AsyncMock(return_value=db)
    patches = [
        mock.patch.object(common.db_pool, "get_pool", pool_stub),
        mock.patch.object(common.database, "get_pool", pool_stub),
        mock.patch.object(common.db_pool, "DB_NAME", db_path),
        mock.patch.object(common.database, "DB_NAME", db_path),
        mock.patch.object(common.config, "DB_NAME", db_path),
        mock.patch.object(common.db_pool, "db_lock", common.db_pool.LazyLock()),
    ]
    for p in patches:
        p.start()
    try:
        yield db
    finally:
        for p in reversed(patches):
            p.stop()
        common.db_pool._db_connection = saved_conn
        await db.close()

