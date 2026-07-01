import pytest
import os

from unittest.mock import patch, MagicMock, mock_open

# Ensure tests can import status_check
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from status_check import (
    format_age,
    format_queue_value,
    format_sys_value,
    get_db_file_sizes,
    get_system_health,
    get_last_errors,
)

def test_format_age(monkeypatch):
    import time

    # Mock time.time to be deterministic
    fake_now = 1000000.0
    monkeypatch.setattr(time, "time", lambda: fake_now)

    # Edge cases
    assert format_age(None) == "[dim]N/A[/dim]"
    assert format_age(0) == "[dim]N/A[/dim]"

    # Under 60 seconds -> seconds
    assert format_age(fake_now - 10) == "[green]10s ago[/green]"
    assert format_age(fake_now - 59) == "[green]59s ago[/green]"

    # Under 1 hour -> minutes
    assert format_age(fake_now - 60) == "[green]1m ago[/green]"
    assert format_age(fake_now - 3599) == "[green]59m ago[/green]"

    # Under 24 hours -> hours
    assert format_age(fake_now - 3600) == "[yellow]1h ago[/yellow]"
    assert format_age(fake_now - 86399) == "[yellow]23h ago[/yellow]"

    # Over 24 hours -> days
    assert format_age(fake_now - 86400) == "[bold red]1d ago[/bold red]"
    assert format_age(fake_now - 86400 * 5) == "[bold red]5d ago[/bold red]"

def test_format_queue_value():
    # String
    assert format_queue_value("Error") == "[bold red]Error[/bold red]"

    # > 1000
    assert format_queue_value(1001) == "[bold red]1,001[/bold red]"

    # > 100
    assert format_queue_value(101) == "[bold yellow]101[/bold yellow]"
    assert format_queue_value(1000) == "[bold yellow]1,000[/bold yellow]"

    # <= 100
    assert format_queue_value(100) == "[green]100[/green]"
    assert format_queue_value(0) == "[green]0[/green]"

def test_format_sys_value():
    # Invalid type
    assert format_sys_value(None) == "[dim]N/A[/dim]"
    assert format_sys_value("10") == "[dim]N/A[/dim]"

    # > 90
    assert format_sys_value(95) == "[bold red]95.0%[/bold red]"
    assert format_sys_value(90.1) == "[bold red]90.1%[/bold red]"

    # > 75
    assert format_sys_value(90) == "[bold yellow]90.0%[/bold yellow]"
    assert format_sys_value(75.1) == "[bold yellow]75.1%[/bold yellow]"

    # <= 75
    assert format_sys_value(75) == "[green]75.0%[/green]"
    assert format_sys_value(0) == "[green]0.0%[/green]"

    # custom unit
    assert format_sys_value(50, unit=" MB") == "[green]50.0 MB[/green]"

@patch('status_check.os.path.exists')
@patch('status_check.os.path.getsize')
def test_get_db_file_sizes(mock_getsize, mock_exists):
    # Mock files
    # DB_NAME, DB_NAME-wal, DB_NAME-shm

    # Scenario: DB exists, WAL missing, SHM access error
    def mock_exists_impl(path):
        return path in ["dvach_bot.db", "dvach_bot.db-shm"]

    mock_exists.side_effect = mock_exists_impl

    def mock_getsize_impl(path):
        if path == "dvach_bot.db":
            return 1024 * 1024 * 5  # 5 MB
        raise OSError("Access denied")

    mock_getsize.side_effect = mock_getsize_impl

    sizes = get_db_file_sizes()
    assert sizes["dvach_bot.db"] == "5.00 MB"
    assert sizes["dvach_bot.db-wal"] == "[dim]Not found[/dim]"
    assert sizes["dvach_bot.db-shm"] == "[red]Access Error[/red]"

@patch('status_check.psutil')
def test_get_system_health(mock_psutil_module):
    # Case 1: psutil is None
    # Assuming psutil might not be installed
    import status_check
    original_psutil = status_check.psutil

    status_check.psutil = None
    try:
        assert get_system_health() == {"cpu": "N/A", "ram": "N/A", "disk": "N/A"}
    finally:
        status_check.psutil = original_psutil

    # Case 2: psutil works
    mock_psutil_module.cpu_percent.return_value = 42.5

    mock_ram = MagicMock()
    mock_ram.percent = 60.0
    mock_psutil_module.virtual_memory.return_value = mock_ram

    mock_disk = MagicMock()
    mock_disk.percent = 80.0
    mock_psutil_module.disk_usage.return_value = mock_disk

    assert get_system_health() == {"cpu": 42.5, "ram": 60.0, "disk": 80.0}

    # Case 3: Exception
    mock_psutil_module.cpu_percent.side_effect = Exception("Mock Error")
    assert get_system_health() == {"cpu": "Error", "ram": "Error", "disk": "Error"}


@patch('status_check.os.path.exists')
def test_get_last_errors(mock_exists):
    # Case 1: Log file doesn't exist
    mock_exists.return_value = False
    assert get_last_errors() == ["Log file not found."]

    # Case 2: Log file exists, read valid lines
    mock_exists.return_value = True

    log_content = """2023-01-01 [INFO] - Everything is fine
2023-01-02 [ERROR] - Bad thing happened
2023-01-03 [WARNING] - Careful
2023-01-04 [CRITICAL] - System down
2023-01-05 [Exception] - Unhandled exception in task
"""
    with patch("builtins.open", mock_open(read_data=log_content)):
        errors = get_last_errors()
        assert len(errors) == 3
        # Should be in reverse order
        assert "Unhandled exception in task" in errors[0]
        assert "System down" in errors[1]
        assert "Bad thing happened" in errors[2]

    # Case 3: More than 5 errors
    log_content_many = "\n".join([f"2023-01-01 [ERROR] - Error {i}" for i in range(10)])
    with patch("builtins.open", mock_open(read_data=log_content_many)):
        errors = get_last_errors()
        assert len(errors) == 5

    # Case 4: Exception reading file
    with patch("builtins.open", side_effect=Exception("Read error")):
        errors = get_last_errors()
        assert len(errors) == 1
        assert "Could not read log file" in errors[0]


import asyncio
from unittest.mock import AsyncMock

from status_check import (
    get_queue_details,
    get_activity,
    get_media_stats,
    get_top_activity
)

@pytest.mark.asyncio
async def test_get_queue_details():
    mock_conn = AsyncMock()

    # We have 8 queues. Let's make some return rows and some fail to test exception handling.
    # get_queue_details uses asyncio.gather to get 8 cursors.

    async def mock_execute(query, *args, **kwargs):
        mock_cursor = AsyncMock()
        if "Tagging" in query or "FileRegistry" in query:
            mock_cursor.fetchone.return_value = (5, 100000)
        elif "PendingHF" in query:
            mock_cursor.fetchone.return_value = (None, None)
        elif "MirrorQueue" in query:
            mock_cursor.fetchone.return_value = None
        elif "Reports" in query:
            # Simulate exception
            raise Exception("DB Error")
        else:
            mock_cursor.fetchone.return_value = (10, 200000)
        return mock_cursor

    mock_conn.execute = AsyncMock(side_effect=mock_execute)

    details = await get_queue_details(mock_conn)

    assert "Tagging (Neuro)" in details
    assert details["Tagging (Neuro)"] == {"count": 5, "oldest": 100000}

    assert details["HuggingFace"] == {"count": 0, "oldest": 0}
    assert details["Mirrors (Catbox)"] == {"count": 0, "oldest": 0}
    assert details["Reports"] == {"count": "N/A", "oldest": 0}
    assert details["Mod Queue (Neuro)"] == {"count": 10, "oldest": 200000}


@pytest.mark.asyncio
async def test_get_activity():
    mock_conn = AsyncMock()

    async def mock_execute(query, *args, **kwargs):
        mock_cursor = AsyncMock()
        if "Posts" in query:
            mock_cursor.fetchone.return_value = (10, 100)
        elif "Threads" in query:
            mock_cursor.fetchone.return_value = (2, 20)
        elif "Users" in query:
            mock_cursor.fetchone.return_value = (5, 50)
        return mock_cursor

    mock_conn.execute = AsyncMock(side_effect=mock_execute)

    activity = await get_activity(mock_conn)

    assert activity["posts_1h"] == 10
    assert activity["posts_24h"] == 100
    assert activity["threads_1h"] == 2
    assert activity["threads_24h"] == 20
    assert activity["users_1h"] == 5
    assert activity["users_24h"] == 50

@pytest.mark.asyncio
async def test_get_activity_operational_error():
    import aiosqlite
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = aiosqlite.OperationalError("DB Locked")

    activity = await get_activity(mock_conn)
    assert activity["posts_1h"] == "N/A"
    assert activity["users_24h"] == "N/A"


@pytest.mark.asyncio
async def test_get_media_stats():
    mock_conn = AsyncMock()

    async def mock_execute(query, *args, **kwargs):
        mock_cursor = AsyncMock()
        if "GROUP BY file_type" in query:
            # For MagicMock/AsyncMock __aiter__ expects something iterable,
            # and _AsyncIterator wraps it. So we pass an iterable, not an async generator.
            mock_cursor.__aiter__.return_value = [("image", 100), ("video", 50), (None, 5)]
        else:
            if "WHERE" not in query:
                mock_cursor.fetchone.return_value = (1000,)
            elif "tags IS NOT NULL" in query:
                mock_cursor.fetchone.return_value = (500,)
            elif "phash IS NOT NULL" in query:
                mock_cursor.fetchone.return_value = (800,)
            elif "blurhash IS NOT NULL" in query:
                mock_cursor.fetchone.return_value = (600,)
            elif "thumbnail_id IS NOT NULL" in query:
                mock_cursor.fetchone.return_value = (400,)
        return mock_cursor

    mock_conn.execute = AsyncMock(side_effect=mock_execute)

    stats = await get_media_stats(mock_conn)

    assert stats["total_files"] == 1000
    assert stats["with_tags"] == 500
    assert stats["has_phash"] == 800
    assert stats["has_blurhash"] == 600
    assert stats["total_thumbnails"] == 400

    assert stats["by_type"]["image"] == 100
    assert stats["by_type"]["video"] == 50
    assert stats["by_type"]["unknown"] == 5


@pytest.mark.asyncio
async def test_get_top_activity():
    mock_conn = AsyncMock()

    async def mock_execute(query, *args, **kwargs):
        mock_cursor = AsyncMock()
        if "GROUP BY board_id" in query:
            mock_cursor.fetchall.return_value = [("b", 100), ("po", 50)]
        elif "Threads WHERE is_archived = 0" in query:
            mock_cursor.fetchall.return_value = [(123, "b", "Thread 1", 50)]
        return mock_cursor

    mock_conn.execute = AsyncMock(side_effect=mock_execute)

    top = await get_top_activity(mock_conn)

    assert top["boards"] == [("b", 100), ("po", 50)]
    assert top["threads"] == [(123, "b", "Thread 1", 50)]

@pytest.mark.asyncio
async def test_get_top_activity_error():
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("DB Error")

    top = await get_top_activity(mock_conn)

    assert top["boards"] == []
    assert top["threads"] == []
