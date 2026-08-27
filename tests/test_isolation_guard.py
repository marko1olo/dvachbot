import asyncio
import os
from pathlib import Path
import sqlite3
import urllib.request
import pytest
import aiosqlite
import requests
import httpx
from unittest.mock import MagicMock, AsyncMock
from aiogram import Bot

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def test_sqlite3_production_db_blocked_by_relative_name():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        sqlite3.connect("dvach_bot.db")

def test_sqlite3_production_db_blocked_by_absolute_path():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        sqlite3.connect(str(PROJECT_ROOT / "dvach_bot.db"))

def test_sqlite3_other_production_dbs_blocked():
    for name in ["2d2vach_bot.db", "bot_database.db", "tgach.db"]:
        with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
            sqlite3.connect(name)

@pytest.mark.asyncio
async def test_aiosqlite_production_db_blocked_by_relative_name():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        await aiosqlite.connect("dvach_bot.db")

@pytest.mark.asyncio
async def test_aiosqlite_production_db_blocked_by_absolute_path():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        await aiosqlite.connect(str(PROJECT_ROOT / "dvach_bot.db"))

def test_sqlite3_memory_allowed():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (x INT)")
    conn.close()

@pytest.mark.asyncio
async def test_aiosqlite_memory_allowed():
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("CREATE TABLE t (x INT)")
    await conn.close()

def test_sqlite3_temp_path_allowed(tmp_path):
    db_file = str(tmp_path / "custom.db")
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE t (x INT)")
    conn.close()
    assert os.path.exists(db_file)

@pytest.mark.asyncio
async def test_aiosqlite_temp_path_allowed(tmp_path):
    db_file = str(tmp_path / "custom_async.db")
    conn = await aiosqlite.connect(db_file)
    await conn.execute("CREATE TABLE t (x INT)")
    await conn.close()
    assert os.path.exists(db_file)

@pytest.mark.asyncio
async def test_unmocked_bot_make_request_blocked():
    bot = Bot(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        await bot.get_me()

def test_requests_telegram_api_blocked():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        requests.get("https://api.telegram.org/bot123/getMe", timeout=1)

def test_urllib_telegram_api_blocked():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        urllib.request.urlopen("https://api.telegram.org/bot123/getMe", timeout=1)

def test_httpx_telegram_api_blocked():
    with pytest.raises(RuntimeError, match="CRITICAL: Production DB / Bot access forbidden in test environment!"):
        httpx.get("https://api.telegram.org/bot123/getMe", timeout=1)

@pytest.mark.asyncio
async def test_mocked_bot_allowed():
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    res = await bot.send_message(chat_id=123, text="Safe mock message")
    assert res.message_id == 123

@pytest.mark.asyncio
async def test_isolated_test_db_fixture(isolated_test_db):
    import time
    from common.database import create_post
    post_num = await create_post(
        author_id=99999,
        board_id="b",
        content={"type": "text", "text": "Isolated test post"},
        timestamp=time.time(),
        post_mode="new_thread"
    )
    assert post_num is not None
