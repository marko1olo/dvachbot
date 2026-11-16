# -*- coding: utf-8 -*-
"""
tests/test_background_workers_nonblocking.py
Unit tests verifying non-blocking execution of background workers,
event loop responsiveness, thread offloading, and WAL checkpoint timeout protections.
"""

import asyncio
import io
import os
import sys
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.db_pool import (
    db_lock,
    sqlite_wal_checkpoint_task,
    wal_checkpoint_truncate,
)
from site_tgach.main import SafeRotatingFileHandler
from main import WindowsSafeRotatingFileHandler


@pytest.mark.asyncio
async def test_wal_checkpoint_truncate_respects_timeout():
    """Verify wal_checkpoint_truncate aborts quickly and returns False when database is locked."""
    mock_db = MagicMock()

    class HangingContext:
        async def __aenter__(self):
            await asyncio.sleep(5.0)
            return MagicMock()

        async def __aexit__(self, *args):
            pass

    mock_db.execute = MagicMock(return_value=HangingContext())

    t0 = time.monotonic()
    result = await wal_checkpoint_truncate(db=mock_db, timeout=0.1)
    duration = time.monotonic() - t0

    assert result is False
    assert duration < 1.0, f"wal_checkpoint_truncate took too long: {duration:.3f}s"


@pytest.mark.asyncio
async def test_wal_checkpoint_truncate_success():
    """Verify wal_checkpoint_truncate succeeds when database is available."""
    mock_db = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(0, 10, 10))

    class MockContext:
        async def __aenter__(self):
            return mock_cursor

        async def __aexit__(self, *args):
            pass

    mock_db.execute = MagicMock(return_value=MockContext())

    result = await wal_checkpoint_truncate(db=mock_db, timeout=2.0)
    assert result is True


@pytest.mark.asyncio
async def test_sqlite_wal_checkpoint_task_timeout_handling():
    """Verify periodic wal checkpoint loop handles timeouts gracefully without crashing."""
    mock_db = MagicMock()

    class HangingContext:
        async def __aenter__(self):
            await asyncio.sleep(5.0)
            return MagicMock()

        async def __aexit__(self, *args):
            pass

    mock_db.execute = MagicMock(return_value=HangingContext())

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)):
        task = asyncio.create_task(
            sqlite_wal_checkpoint_task(interval_seconds=0.01, checkpoint_timeout=0.05)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert task.done()


@pytest.mark.asyncio
async def test_auto_memory_cleaner_offloads_gc_and_disk_to_threads():
    """Verify auto_memory_cleaner offloads gc.collect and glob/disk cleaning to threads."""
    import main

    gc_threads = []
    disk_threads = []
    real_to_thread = asyncio.to_thread

    async def instrumented_to_thread(func, *args, **kwargs):
        fname = getattr(func, "__name__", str(func))
        if "collect" in fname:
            gc_threads.append(True)
        elif "clean_temp_disk_files" in fname:
            disk_threads.append(True)
        return await real_to_thread(func, *args, **kwargs)

    async def controlled_sleep(delay):
        if delay >= 300:
            raise asyncio.CancelledError()

    with patch("asyncio.to_thread", side_effect=instrumented_to_thread), \
         patch("main.get_pool", AsyncMock(return_value=None)), \
         patch("asyncio.sleep", side_effect=controlled_sleep):
        try:
            await main.auto_memory_cleaner()
        except asyncio.CancelledError:
            pass

    assert len(gc_threads) > 0, "gc.collect was not called via asyncio.to_thread"
    assert len(disk_threads) > 0, "disk files cleaner was not called via asyncio.to_thread"


@pytest.mark.asyncio
async def test_tagger_get_neuro_tags_offloads_file_io():
    """Verify get_neuro_tags in site_tgach.tagging_worker writes and removes temp files via to_thread."""
    from site_tgach import tagging_worker

    thread_calls = []
    real_to_thread = asyncio.to_thread

    async def track_to_thread(func, *args, **kwargs):
        fname = getattr(func, "__name__", str(func))
        thread_calls.append(fname)
        return await real_to_thread(func, *args, **kwargs)

    with patch("asyncio.to_thread", side_effect=track_to_thread), \
         patch("site_tgach.vision.describe_image", AsyncMock(return_value='{"tags": "anime"}')):
        res = await tagging_worker.get_neuro_tags(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64)

    assert res == '{"tags": "anime"}'
    assert any("_write_temp_jpg" in c for c in thread_calls), "Temporary JPG was not written via asyncio.to_thread"
    assert any("_remove_temp_file" in c for c in thread_calls), "Temporary JPG was not removed via asyncio.to_thread"


@pytest.mark.asyncio
async def test_vision_prepare_image_for_groq_offloads_to_thread():
    """Verify describe_image in site_tgach.vision calls prepare_image_for_groq via asyncio.to_thread."""
    from site_tgach import vision

    prep_groq_threads = []
    real_to_thread = asyncio.to_thread

    async def track_to_thread(func, *args, **kwargs):
        fname = getattr(func, "__name__", str(func))
        if "prepare_image_for_groq" in fname:
            prep_groq_threads.append(True)
        return await real_to_thread(func, *args, **kwargs)

    # Valid 1x1 JPEG bytes
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"

    class StopExecution(Exception):
        pass

    with patch("asyncio.to_thread", side_effect=track_to_thread), \
         patch("site_tgach.vision.prepare_image_for_analysis", AsyncMock(return_value=(dummy_jpeg, None))), \
         patch("httpx.AsyncClient", side_effect=StopExecution("stop_before_network")):
        try:
            await vision.describe_image(["test_nonexistent.jpg"], caption="test", source="TAGGER")
        except StopExecution:
            pass

    assert len(prep_groq_threads) > 0, "prepare_image_for_groq was not offloaded via asyncio.to_thread"


def test_site_safe_rotating_file_handler_defer_and_restore(tmp_path):
    """Verify SafeRotatingFileHandler defers rollover on PermissionError and keeps stream valid."""
    log_file = tmp_path / "test_site.log"
    log_file.write_text("Hello\n", encoding="utf-8")

    handler = SafeRotatingFileHandler(str(log_file), maxBytes=5, backupCount=2, encoding="utf-8")

    record = MagicMock()
    record.getMessage.return_value = "Long message exceeding maxBytes"

    assert handler.shouldRollover(record) == 1

    with patch("logging.handlers.RotatingFileHandler.doRollover", side_effect=PermissionError(32, "File locked")):
        handler.doRollover()

    # Rollover was deferred for 300s
    assert handler._rollover_retry_after > time.time() + 250.0
    # Subsequent calls must return 0 to avoid hammering the disk
    assert handler.shouldRollover(record) == 0
    # Stream must not be None
    assert handler.stream is not None

    handler.close()


@pytest.mark.asyncio
async def test_postcopies_daily_cleanup_mutes_cleanup_transaction():
    """Verify postcopies_daily_cleanup_loop uses db_transaction and does not call illegal db.commit()."""
    import main

    tx_used = []
    commit_called = []

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()

    def mock_commit():
        commit_called.append(True)

    mock_db.commit = mock_commit

    class MockTx:
        def __init__(self, db, immediate=True):
            self.db = db

        async def __aenter__(self):
            tx_used.append(True)
            return self.db

        async def __aexit__(self, *args):
            pass

    async def controlled_sleep(delay):
        if delay >= 86400:
            raise asyncio.CancelledError()

    with patch("common.database.clean_old_postcopies_daily", AsyncMock(return_value=0)), \
         patch("common.database.clean_old_media_reposts_daily", AsyncMock(return_value=0)), \
         patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)), \
         patch("common.db_pool.db_transaction", MockTx), \
         patch("asyncio.sleep", side_effect=controlled_sleep):
        try:
            await main.postcopies_daily_cleanup_loop()
        except asyncio.CancelledError:
            pass

    assert len(tx_used) > 0, "db_transaction was not used for Mutes cleanup"
    assert len(commit_called) == 0, "Illegal raw db.commit() was called in autocommit mode"


@pytest.mark.asyncio
async def test_daily_airdrop_uses_transaction_no_raw_commit():
    """Verify daily_abu_airdrop_engine executes GlobalStats updates in db_transaction without raw commit."""
    from daily_abu_airdrop_engine import execute_daily_airdrop

    tx_used = []
    commit_called = []

    mock_db = MagicMock()

    class MockCursor:
        def __await__(self):
            async def _coro():
                return self
            return _coro().__await__()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def fetchone(self):
            return (0.0,)

        async def fetchall(self):
            return []

    mock_db.execute = MagicMock(return_value=MockCursor())

    def mock_commit():
        commit_called.append(True)

    mock_db.commit = mock_commit

    class MockTx:
        def __init__(self, db, *args, **kwargs):
            self.db = db

        async def __aenter__(self):
            tx_used.append(True)
            return self.db

        async def __aexit__(self, *args):
            pass

    with patch("daily_abu_airdrop_engine.fetch_daily_qualified_users", AsyncMock(return_value=[])), \
         patch("common.db_pool.db_transaction", MockTx):
        result = await execute_daily_airdrop(mock_db, bots={})

    assert result.get("status") == "skipped"
    assert len(tx_used) > 0, "db_transaction was not used when recording last_daily_airdrop_run"
    assert len(commit_called) == 0, "Raw db.commit() was called in autocommit mode"
