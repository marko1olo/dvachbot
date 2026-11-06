import time
import json
import sqlite3
import pytest
import aiosqlite
from unittest.mock import patch

from common.db_pool import db_transaction
from common.database import (
    create_thread,
    get_thread_op_by_post_num,
    _delete_in_chunks,
)


@pytest.mark.asyncio
async def test_transaction_collision_raises_runtime_error_no_blind_rollback(tmp_path):
    """
    Верифицирует, что при ошибке 'cannot start a transaction within a transaction'
    db_transaction НЕ вызывает ROLLBACK чужой транзакции, а немедленно выбрасывает
    RuntimeError("Database transaction collision: connection already in transaction").
    """
    db_path = str(tmp_path / "test_collision.db")
    db = await aiosqlite.connect(db_path, isolation_level=None)
    try:
        with patch.object(
            db,
            "execute",
            side_effect=aiosqlite.OperationalError("cannot start a transaction within a transaction")
        ) as mock_execute:
            with pytest.raises(RuntimeError) as exc_info:
                async with db_transaction(db):
                    pass

            assert "Database transaction collision: connection already in transaction" in str(exc_info.value)

            # Проверяем, что ROLLBACK НЕ был вызван внутри блока обработки коллизии!
            called_statements = [call.args[0] for call in mock_execute.call_args_list if call.args]
            assert "ROLLBACK" not in called_statements
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_create_thread_and_helpers_with_hex_thread_id(isolated_test_db):
    """
    Верифицирует, что hex-строка thread_id принимается create_thread без исключений ValueError,
    и корректно сохраняется в таблицу Threads.
    """
    db = isolated_test_db
    ts = time.time()
    hex_thread_id = "deadbeefcafe1234"
    op_post_id = 998877

    # Создание треда с hex-идентификатором
    ok = await create_thread(
        thread_id=hex_thread_id,
        board_id="b",
        op_id=op_post_id,
        title="Hex Thread Test",
        created_at=ts
    )
    assert ok is True

    # Проверяем сохраненные значения в Threads
    async with db.execute("SELECT thread_id, thread_num, op_id, title FROM Threads WHERE thread_id = ?", (hex_thread_id,)) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == hex_thread_id
        # thread_num должен безопасно смапиться на op_id или 0
        assert row[1] == op_post_id
        assert row[2] == op_post_id
        assert row[3] == "Hex Thread Test"


@pytest.mark.asyncio
async def test_get_thread_op_by_post_num_returns_str(isolated_test_db):
    """
    Верифицирует, что get_thread_op_by_post_num возвращает str(thread_id),
    включая hex-строки без падений.
    """
    db = isolated_test_db
    ts = time.time()
    hex_id = "abcd1234ef5678"

    # Вставляем пост с hex_id и валидным JSON контентом
    content_json = json.dumps({"type": "text", "text": "test content"})
    cursor = await db.execute(
        "INSERT INTO Posts (board_id, thread_id, author_id, content, timestamp) VALUES ('b', ?, 101, ?, ?)",
        (hex_id, content_json, ts)
    )
    post_num = cursor.lastrowid

    res = await get_thread_op_by_post_num(post_num)
    assert res == hex_id
    assert isinstance(res, str)


@pytest.mark.asyncio
async def test_schema_indices_no_idx_posts_thread_num(isolated_test_db):
    """
    Верифицирует, что фиктивный индекс idx_posts_thread_num не создается,
    а корректные индексы Posts присутствуют.
    """
    db = isolated_test_db

    async with db.execute("PRAGMA index_list('Posts')") as cursor:
        indices = await cursor.fetchall()
        index_names = [row[1] for row in indices]

    # idx_posts_thread_num не должен существовать
    assert "idx_posts_thread_num" not in index_names

    # Корректные индексы должны существовать
    assert "idx_posts_board_post_num" in index_names
    assert "idx_posts_thread_timestamp" in index_names


def test_delete_in_chunks_busy_timeout():
    """
    Верифицирует, что _delete_in_chunks устанавливает PRAGMA busy_timeout = 30000.
    """
    con = sqlite3.connect(":memory:", isolation_level=None)
    try:
        con.execute("CREATE TABLE TestTable (rowid INTEGER PRIMARY KEY, val TEXT)")
        con.execute("INSERT INTO TestTable (val) VALUES ('x'), ('y')")

        _delete_in_chunks(con, "TestTable", "val = 'x'", ())

        # Проверяем установленный busy_timeout
        cur = con.execute("PRAGMA busy_timeout;")
        timeout = cur.fetchone()[0]
        assert timeout == 30000
    finally:
        con.close()
