import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from site_tgach.main import (
    ConnectionManager,
    get_posts_from_broadcast_queue_by_post_num,
)
from site_tgach.importer import ThreadImporter


@pytest.mark.asyncio
async def test_queue_listener_strict_post_num_increment(tmp_path):
    """
    Проверяет, что выборка из BroadcastQueue идет строго по post_num > ? с сортировкой post_num ASC,
    и не пропускает посты даже при хаотичных или немонотонных created_at.
    """
    import aiosqlite

    db_path = str(tmp_path / "test_bq.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE Posts (
                post_num INTEGER PRIMARY KEY,
                board_id TEXT,
                content TEXT,
                timestamp REAL
            );
        """)
        await db.execute("""
            CREATE TABLE BroadcastQueue (
                post_num INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                is_sent_to_tg INTEGER DEFAULT 0
            );
        """)
        # Вставляем посты с немонотонными created_at
        # post 10: created_at = 1000.0
        # post 11: created_at = 500.0 (старый таймстемп!)
        # post 12: created_at = 800.0
        posts = [
            (10, "b", json.dumps({"text": "post 10"}), 1000.0),
            (11, "b", json.dumps({"text": "post 11"}), 500.0),
            (12, "b", json.dumps({"text": "post 12"}), 800.0),
        ]
        await db.executemany("INSERT INTO Posts VALUES (?, ?, ?, ?)", posts)
        bq_rows = [
            (10, 1000.0, 0),
            (11, 500.0, 0),
            (12, 800.0, 0),
        ]
        await db.executemany("INSERT INTO BroadcastQueue VALUES (?, ?, ?)", bq_rows)
        await db.commit()

        with patch("site_tgach.main.get_pool", return_value=db):
            # Запрос 1: от 0 -> должен вернуть все 3 поста по порядку post_num
            fetched, max_num = await get_posts_from_broadcast_queue_by_post_num(0)
            assert len(fetched) == 3
            assert [p["post_num"] for p in fetched] == [10, 11, 12]
            assert max_num == 12

            # Запрос 2: от 10 -> должен вернуть посты 11 и 12 (даже с меньшим timestamp!)
            fetched2, max_num2 = await get_posts_from_broadcast_queue_by_post_num(10)
            assert len(fetched2) == 2
            assert [p["post_num"] for p in fetched2] == [11, 12]
            assert max_num2 == 12

            # Запрос 3: от 12 -> пусто
            fetched3, max_num3 = await get_posts_from_broadcast_queue_by_post_num(12)
            assert len(fetched3) == 0
            assert max_num3 == 12


@pytest.mark.asyncio
async def test_connection_manager_safe_send_disconnects_and_prevents_ip_ban():
    """
    Проверяет, что при сбое отправки в сокет ConnectionManager._safe_send вызывает disconnect,
    декрементирует ip_counts и закрывает сокет, предотвращая утечку счетчика подключений и перманентный бан.
    """
    cm = ConnectionManager()

    # Создаем фейковый сокет
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock(side_effect=ConnectionResetError("Socket broken"))
    mock_ws.close = AsyncMock()
    mock_ws.client.host = "1.2.3.4"
    mock_ws.headers = {}
    mock_ws.state_client_ip = "1.2.3.4"

    # Регистрируем подключение
    cm.ip_counts["1.2.3.4"] = 1
    cm.active_connections["b/threads/ru"].add(mock_ws)

    # Вызываем _safe_send, который упадет на send_text
    await cm._safe_send(mock_ws, "test message", "b/threads/ru")

    # Проверяем, что сокет удален из активных подключений
    assert "b/threads/ru" not in cm.active_connections
    # Проверяем, что ip_counts декрементирован и очищен (не висит на 1)
    assert "1.2.3.4" not in cm.ip_counts
    # Проверяем, что close был вызван
    mock_ws.close.assert_awaited()
    # Проверяем, что повторный вызов disconnect не роняет счетчик в отрицательные значения
    cm.disconnect(mock_ws, "b", "threads", "ru")
    assert cm.ip_counts.get("1.2.3.4", 0) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast_admin_feed_key():
    """
    Проверяет, что ConnectionManager.broadcast_post транслирует сообщения в 'admin_feed/feed/ru'.
    """
    cm = ConnectionManager()
    admin_ws = MagicMock()
    admin_ws.send_text = AsyncMock()
    admin_ws.close = AsyncMock()
    admin_ws.state_client_ip = "127.0.0.1"

    key = "admin_feed/feed/ru"
    cm.active_connections[key].add(admin_ws)

    post_data = {
        "post_num": 42,
        "board_id": "b",
        "thread_id": None,
        "content": {"text": "hello admin"},
        "timestamp": 123456789.0,
        "stream": "ru",
    }

    await cm.broadcast_post(post_data, "b")
    # Проверяем, что send_text был вызван для admin_ws
    admin_ws.send_text.assert_awaited()


def test_thread_importer_import_thread_alias():
    """
    Проверяет, что в ThreadImporter метод import_thread является алиасом process_thread.
    """
    importer = ThreadImporter(bot=None, file_storage_channel_id=0)
    assert hasattr(importer, "import_thread")
    assert importer.import_thread.__name__ == importer.process_thread.__name__


@pytest.mark.asyncio
async def test_thread_importer_instant_import_registers_broadcast_queue(tmp_path):
    """
    Проверяет, что при пакетном импорте треда в _instant_import
    все созданные посты регистрируются в BroadcastQueue.
    """
    import aiosqlite

    db_path = str(tmp_path / "test_import.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE posts (
                post_num INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id TEXT,
                thread_id TEXT,
                content TEXT,
                timestamp REAL,
                author_id INTEGER,
                reply_to_post_num INTEGER,
                stream TEXT
            );
        """)
        await db.execute("""
            CREATE TABLE Threads (
                thread_id INTEGER PRIMARY KEY,
                thread_num INTEGER,
                board_id TEXT,
                op_id INTEGER,
                title TEXT,
                created_at REAL,
                last_updated_at REAL,
                is_archived INTEGER,
                stream TEXT
            );
        """)
        await db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                stream TEXT,
                PRIMARY KEY (user_id, board_id)
            );
        """)
        await db.execute("""
            CREATE TABLE ChannelCopies (
                post_num INTEGER,
                channel_id INTEGER,
                message_id INTEGER
            );
        """)
        await db.execute("""
            CREATE TABLE PostFiles (
                post_num INTEGER,
                file_type TEXT,
                original_file_id TEXT,
                thumbnail_file_id TEXT,
                original_url TEXT,
                thumbnail_url TEXT
            );
        """)
        await db.execute("""
            CREATE TABLE Backlinks (
                target_post_num INTEGER,
                source_post_num INTEGER
            );
        """)
        await db.execute("""
            CREATE TABLE BroadcastQueue (
                post_num INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                is_sent_to_tg INTEGER DEFAULT 0
            );
        """)
        await db.commit()

        importer = ThreadImporter(bot=None, file_storage_channel_id=0)
        prepared_posts = [
            {
                "old_id": "100",
                "text": "OP Post",
                "files": [],
                "timestamp": 1000.0,
                "author_id": 1,
                "subject": "OP Subject",
            },
            {
                "old_id": "101",
                "text": "Reply Post >>100",
                "files": [],
                "timestamp": 1005.0,
                "author_id": 2,
            },
        ]

        # Мокаем get_db_connection чтобы возвращал нашу тестовую БД
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_get_conn():
            yield db

        with patch("site_tgach.importer.get_db_connection", side_effect=mock_get_conn):
            await importer._instant_import(prepared_posts, target_board="b", stream="ru")

        # Проверяем, что посты созданы в BroadcastQueue
        async with db.execute("SELECT post_num, created_at FROM BroadcastQueue ORDER BY post_num ASC") as cursor:
            bq_rows = await cursor.fetchall()

        assert len(bq_rows) == 2
        # post_num должны быть 1 и 2
        assert bq_rows[0][0] == 1
        assert bq_rows[1][0] == 2
        assert bq_rows[0][1] > 0
        assert bq_rows[1][1] > 0
