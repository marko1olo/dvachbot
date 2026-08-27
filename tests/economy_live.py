"""
Оснастка для тестов ЖИВОЙ экономики.

ЗАЧЕМ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ. Тесты /rob и /curse раньше импортировали cmd_rob и
cmd_curse из economy_extension.py. Эти функции зарегистрированы на
economy_router, а Dispatcher разрешает СВОИ обработчики раньше включённых
под-роутеров - значит, версии из economy_extension не вызываются никогда.
Тесты зеленели, ни разу не коснувшись работающего кода: фикс гонки в /rob
двое суток считался применённым, лежа в недостижимом файле.

Поэтому обработчик здесь достаётся ЧЕРЕЗ РЕГИСТРАЦИЮ на main.dp, а не по имени
модуля (см. live_handler). Подсунуть тесту мёртвую копию нельзя даже случайно:
если живого обработчика на dp нет, оснастка падает, а не тихо берёт другой.

БОЕВАЯ БД НЕДОСТИЖИМА ПО ПОСТРОЕНИЮ. Мало пропатчить common.db_pool.get_pool:
common/database.py на строке 35 делает `from common.db_pool import get_pool` на
уровне модуля, то есть держит ОТДЕЛЬНУЮ ссылку на функцию, которую подмена
атрибута в db_pool не затрагивает. Поэтому live_economy() закрывает все двери
сразу: обе ссылки на get_pool, кэш соединения _db_connection и DB_NAME в трёх
модулях - и всё это через patch с автоматическим откатом, так что за пределами
контекста ни один глобал не остаётся сдвинутым.

Схема поднимается настоящими билдерами common.database (те же пять функций, что
вызывает initialize_database), а не самодельным CREATE TABLE: дыры в схеме уже
ловились именно на чистой БД, и подделывать её здесь означало бы потерять эту
ось проверки. Сам initialize_database не годится - он глотает исключение и
делает sys.exit(1), что убило бы прогон pytest вместо честного падения теста.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# main.py на импорте печатает баннеры и предупреждения - глушим, чтобы не
# засорять вывод pytest. Импорт тяжёлый (~30 с в холодном процессе), но в общем
# прогоне его уже оплатил tests/test_batch_replies.py, и модуль берётся из кэша.
import aiosqlite  # noqa: E402
import common.config  # noqa: E402
import common.database  # noqa: E402
import common.db_pool  # noqa: E402
from aiogram.filters import Command  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import main  # noqa: E402

BOARD = "b"
# Куда «отвечает» тестовое сообщение. Числа произвольные, важно лишь чтобы
# get_author_id_by_reply нашла по этой паре запись в message_to_post.
REPLY_CHAT_ID = -100999
REPLY_MESSAGE_ID = 555
REPLY_POST_NUM = 777


def _command_names(handler) -> set[str]:
    """Имена команд, на которые подписан обработчик aiogram."""
    names: set[str] = set()
    for flt in handler.filters or ():
        callback = getattr(flt, "callback", flt)
        if isinstance(callback, Command):
            names.update(c for c in callback.commands if isinstance(c, str))
    return names


def dp_own_handlers(command: str) -> list:
    """Обработчики команды, объявленные на САМОМ Dispatcher (живые)."""
    return [h.callback for h in main.dp.message.handlers
            if command in _command_names(h)]


def sub_router_handlers(command: str) -> list[tuple[str, object]]:
    """Обработчики команды из включённых под-роутеров (затенённые).

    Возвращает пары (имя роутера, функция). Именно здесь лежат недостижимые
    копии из economy_extension.
    """
    out: list[tuple[str, object]] = []

    def walk(router):
        for sub in router.sub_routers:
            for h in sub.message.handlers:
                if command in _command_names(h):
                    out.append((sub.name, h.callback))
            walk(sub)

    walk(main.dp)
    return out


def live_handler(command: str):
    """Функция, которую бот РЕАЛЬНО исполнит на /<command>.

    Ищется по регистрации на main.dp, а не по имени модуля - в этом весь смысл
    оснастки. Любая неоднозначность здесь падает: два обработчика на одну
    команду в самом Dispatcher означают, что один из них затенён и проверять
    надо не его.
    """
    own = dp_own_handlers(command)
    assert own, (
        f"на main.dp нет обработчика /{command}. Если он переехал в под-роутер, "
        f"порядок разрешения изменился и тест обязан быть переписан, а не "
        f"подправлен: найдено в под-роутерах {sub_router_handlers(command)}"
    )
    assert len(own) == 1, (
        f"на main.dp {len(own)} обработчиков /{command}: {[f.__name__ for f in own]}. "
        f"Победит первый, остальные затенены"
    )
    handler = own[0]
    assert handler.__module__ == "main", (
        f"живой обработчик /{command} неожиданно объявлен в {handler.__module__}"
    )
    return handler


async def _build_schema(path: str):
    """Настоящая схема проекта на чистом файле, теми же билдерами, что в проде."""
    db = await aiosqlite.connect(path, timeout=30.0, isolation_level=None)
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
    return db


class LiveEconomy:
    """Настоящая БД плюс мелкая обвязка, чтобы позвать живой обработчик."""

    def __init__(self, db):
        self.db = db

    async def seed_user(self, user_id: int, balance: float = 0.0,
                        items: dict | None = None) -> None:
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, board_id) DO UPDATE SET "
            "balance = excluded.balance, active_items = excluded.active_items",
            (user_id, BOARD, balance, json.dumps(items or {})))
        await self.db.commit()

    async def balance_of(self, user_id: int) -> float:
        async with self.db.execute(
                "SELECT SUM(balance) FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, BOARD)) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] is not None else 0.0

    async def items_of(self, user_id: int) -> dict:
        async with self.db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, BOARD)) as cur:
            row = await cur.fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    async def column_of(self, user_id: int, column: str):
        """Значение отдельной КОЛОНКИ Users - не то же самое, что ключ в JSON."""
        async with self.db.execute(
                f"SELECT {column} FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, BOARD)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    def aim_at(self, target_id: int) -> None:
        """Сделать так, чтобы Reply тестового сообщения указывал на target_id.

        Заполняются те же два глобала main, из которых читает настоящая
        get_author_id_by_reply, - функция не подменяется.
        """
        main.message_to_post[(REPLY_CHAT_ID, REPLY_MESSAGE_ID)] = REPLY_POST_NUM
        main.messages_storage[REPLY_POST_NUM] = {"author_id": target_id}

    @staticmethod
    def message(user_id: int, with_reply: bool = True):
        msg = mock.MagicMock()
        msg.from_user.id = user_id
        if with_reply:
            msg.reply_to_message = mock.MagicMock()
            msg.reply_to_message.chat.id = REPLY_CHAT_ID
            msg.reply_to_message.message_id = REPLY_MESSAGE_ID
        else:
            msg.reply_to_message = None
        msg.answer = mock.AsyncMock()
        msg.bot = mock.MagicMock()
        msg.bot.send_message = mock.AsyncMock()
        return msg

    @staticmethod
    def answers(msg) -> list[str]:
        """Тексты, отправленные через message.answer."""
        return [c.args[0] for c in msg.answer.call_args_list if c.args]


@contextlib.asynccontextmanager
async def live_economy():
    """Временная БД с настоящей схемой; боевая БД недостижима внутри блока."""
    work = tempfile.mkdtemp(prefix="dvach-econ-")
    db_path = os.path.join(work, "fresh.db")
    db = await _build_schema(db_path)
    import shared_state
    shared_state.reset_combat_state()

    saved_storage = dict(main.messages_storage)
    saved_map = dict(main.message_to_post)
    saved_conn = common.db_pool._db_connection
    common.db_pool._db_connection = db
    pool_stub = mock.AsyncMock(return_value=db)
    patches = [
        mock.patch.object(common.db_pool, "get_pool", pool_stub),
        mock.patch.object(common.database, "get_pool", pool_stub),
        mock.patch.object(common.db_pool, "DB_NAME", db_path),
        mock.patch.object(common.database, "DB_NAME", db_path),
        mock.patch.object(common.config, "DB_NAME", db_path),
        mock.patch.object(common.db_pool, "db_lock", asyncio.Lock()),
    ]
    for p in patches:
        p.start()
    try:
        yield LiveEconomy(db)
    finally:
        for p in reversed(patches):
            p.stop()
        common.db_pool._db_connection = saved_conn
        main.messages_storage.clear()
        main.messages_storage.update(saved_storage)
        main.message_to_post.clear()
        main.message_to_post.update(saved_map)
        shared_state.reset_combat_state()
        await db.close()
        shutil.rmtree(work, ignore_errors=True)
