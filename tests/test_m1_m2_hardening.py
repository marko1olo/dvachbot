import asyncio
import os
import io
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

import aiosqlite
from common.db_pool import LazyLock, db_lock
import common.database as db_mod
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
)
import shared_state
import archive_manager
import invite_image_generator
from invite_image_generator import _decode_and_verify_image
import site_tgach.main as site_main
import Dubsite_tgach.main as dub_site_main


@pytest.mark.asyncio
async def test_process_memory_snapshot_safety():
    """Verify _get_process_memory_snapshot returns safe handle metrics and avoids open_files crash."""
    from main import _get_process_memory_snapshot
    snapshot = _get_process_memory_snapshot()
    assert isinstance(snapshot, dict)
    assert "pid" in snapshot
    assert "rss_mb" in snapshot
    assert "threads" in snapshot
    assert "handles" in snapshot
    assert snapshot.get("open_files") == -1


@pytest.mark.asyncio
async def test_deduct_user_global_balance_atomic(tmp_path):
    """Verify atomic multi-row balance deduction holding db_lock and transaction boundaries."""
    test_db_path = str(tmp_path / "test_economy.db")
    async with aiosqlite.connect(test_db_path, isolation_level=None) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0.0,
                active_items TEXT DEFAULT '{}',
                cursed_until INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, board_id)
            )
        """)
        
        # User 12345 has 100 on 'b' and 150 on 'vg'
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (12345, 'b', 100.0)")
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (12345, 'vg', 150.0)")
        
        total = await get_user_global_balance(db, 12345)
        assert total == 250.0

        # Deduct 150 from board 'b': 100 from 'b', 50 from 'vg'
        ok, new_total = await deduct_user_global_balance(db, 12345, 'b', 150.0)
        assert ok is True
        assert new_total == 100.0

        # Check per-board balances
        async with db.execute("SELECT balance FROM Users WHERE user_id = 12345 AND board_id = 'b'") as c:
            row = await c.fetchone()
            assert row[0] == 0.0

        async with db.execute("SELECT balance FROM Users WHERE user_id = 12345 AND board_id = 'vg'") as c:
            row = await c.fetchone()
            assert row[0] == 100.0

        # Try deducting more than total: should fail and retain balance
        ok, fail_total = await deduct_user_global_balance(db, 12345, 'b', 200.0)
        assert ok is False
        assert fail_total == 100.0

        # Deduct remaining 100
        ok, final_total = await deduct_user_global_balance(db, 12345, 'vg', 100.0)
        assert ok is True
        assert final_total == 0.0


@pytest.mark.asyncio
async def test_deduct_user_global_balance_reentrancy(tmp_path):
    """Verify deduct_user_global_balance handles callers that already own db_lock without deadlocking."""
    test_db_path = str(tmp_path / "test_reentrant.db")
    async with aiosqlite.connect(test_db_path, isolation_level=None) as db:
        await db.execute("""
            CREATE TABLE Users (
                user_id INTEGER,
                board_id TEXT,
                balance REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, board_id)
            )
        """)
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (999, 'b', 500.0)")

        # Caller already holds db_lock
        async with db_lock:
            ok, new_total = await deduct_user_global_balance(db, 999, 'b', 200.0)
            assert ok is True
            assert new_total == 300.0


def test_archive_manager_shared_state_binding():
    """Verify archive_manager uses shared_state without importing __main__."""
    assert hasattr(archive_manager, "shared_state")
    assert archive_manager.shared_state is shared_state
    assert not hasattr(archive_manager, "_main")


def test_ssl_contexts_non_blocking():
    """Verify site_tgach and Dubsite_tgach use non-blocking _NO_VERIFY_SSL context."""
    import ssl
    assert isinstance(site_main._NO_VERIFY_SSL, ssl.SSLContext)
    assert site_main._NO_VERIFY_SSL.check_hostname is False
    assert site_main._NO_VERIFY_SSL.verify_mode == ssl.CERT_NONE

    assert isinstance(dub_site_main._NO_VERIFY_SSL, ssl.SSLContext)
    assert dub_site_main._NO_VERIFY_SSL.check_hostname is False
    assert dub_site_main._NO_VERIFY_SSL.verify_mode == ssl.CERT_NONE


def test_pillow_decode_and_verify_helper():
    """Verify _decode_and_verify_image decodes valid images and rejects invalid ones safely."""
    # Generate small valid image
    img = Image.new("RGB", (64, 64), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_valid = buf.getvalue()

    decoded = _decode_and_verify_image(raw_valid)
    assert decoded is not None
    assert isinstance(decoded, Image.Image)
    assert decoded.size == (64, 64)

    # Invalid bytes
    raw_invalid = b"Not an image at all garbage data"
    assert _decode_and_verify_image(raw_invalid) is None
