import asyncio
import logging
import sys
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from common.task_manager import (
    spawn_task,
    close_all_tasks,
    cancel_all_background_tasks,
    register_http_client,
    unregister_http_client,
    close_tracked_http_clients,
    install_proactor_safety_net,
    _background_tasks,
    _tracked_http_clients,
    _on_task_done,
    ProactorNoiseFilter,
)


@pytest.fixture(autouse=True)
def clean_task_manager_state():
    _background_tasks.clear()
    _tracked_http_clients.clear()
    yield
    _background_tasks.clear()
    _tracked_http_clients.clear()


@pytest.mark.asyncio
async def test_proactor_safety_net_connection_reset_suppression():
    """
    Simulates remote peer dropping socket causing ConnectionResetError (WinError 10054)
    inside _ProactorBasePipeTransport._call_connection_lost during shutdown().
    Verifies that safety net catches it and finishes socket cleanup without escaping.
    """
    if sys.platform != "win32":
        pytest.skip("Windows-specific Proactor test")

    import asyncio.proactor_events as pe

    installed = install_proactor_safety_net()
    assert installed is True

    # Construct mock transport
    transport = pe._ProactorBasePipeTransport.__new__(pe._ProactorBasePipeTransport)
    transport._called_connection_lost = False
    transport._protocol = MagicMock()
    mock_sock = MagicMock()
    mock_sock.fileno.return_value = 10
    mock_sock.shutdown.side_effect = ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
    transport._sock = mock_sock
    transport._server = None

    # Should not raise ConnectionResetError
    transport._call_connection_lost(None)

    assert transport._called_connection_lost is True
    assert transport._sock is None
    mock_sock.close.assert_called_once()


@pytest.mark.asyncio
async def test_proactor_safety_net_del_closed_pipe():
    """
    Simulates GC calling __del__ when fileno() raises ValueError('I/O operation on closed pipe').
    Verifies that the patched __del__ suppresses the crash.
    """
    if sys.platform != "win32":
        pytest.skip("Windows-specific Proactor test")

    import asyncio.proactor_events as pe

    install_proactor_safety_net()

    transport = pe._ProactorBasePipeTransport.__new__(pe._ProactorBasePipeTransport)
    mock_sock = MagicMock()
    mock_sock.fileno.side_effect = ValueError("I/O operation on closed pipe")
    transport._sock = mock_sock

    # Calling __del__ should not raise ValueError
    try:
        transport.__del__()
    except ValueError as e:
        pytest.fail(f"__del__ raised ValueError: {e}")


def test_proactor_noise_filter():
    """Verifies that ProactorNoiseFilter correctly drops Windows connection lost logs."""
    noise_filter = ProactorNoiseFilter()

    # Should filter out
    rec1 = logging.LogRecord("asyncio", logging.ERROR, "", 0, "Exception in callback _ProactorBasePipeTransport._call_connection_lost()", (), None)
    assert noise_filter.filter(rec1) is False

    rec2 = logging.LogRecord("asyncio", logging.ERROR, "", 0, "ConnectionResetError: [WinError 10054] An existing connection was forcibly closed", (), None)
    assert noise_filter.filter(rec2) is False

    rec3 = logging.LogRecord("asyncio", logging.ERROR, "", 0, "ValueError: I/O operation on closed pipe", (), None)
    assert noise_filter.filter(rec3) is False

    # Should allow real errors
    rec_ok = logging.LogRecord("asyncio", logging.ERROR, "", 0, "ZeroDivisionError: division by zero", (), None)
    assert noise_filter.filter(rec_ok) is True


@pytest.mark.asyncio
async def test_close_all_tasks_cancellation_and_drain():
    """
    Spawns background tasks, then calls close_all_tasks.
    Verifies that all tasks are cancelled, background task set is cleared,
    and Proactor drain delay (0.250s) is observed.
    """
    cancelled_flags = []

    async def long_running_task(idx):
        try:
            await asyncio.sleep(100.0)
        except asyncio.CancelledError:
            cancelled_flags.append(idx)
            raise

    for i in range(5):
        spawn_task(long_running_task(i), name=f"task_{i}")

    assert len(_background_tasks) == 5

    # Give event loop a cycle so tasks enter their try block
    await asyncio.sleep(0.01)

    t0 = time.monotonic()
    await close_all_tasks(timeout=2.0, close_http_clients=False)
    elapsed = time.monotonic() - t0

    # Ensure drain delay was observed (>= 0.240s)
    assert elapsed >= 0.240, f"Expected drain delay >= 0.24s, got {elapsed:.3f}s"
    assert len(cancelled_flags) == 5
    assert len(_background_tasks) == 0


@pytest.mark.asyncio
async def test_cancel_all_background_tasks_alias():
    """Verifies that cancel_all_background_tasks acts as an alias to close_all_tasks."""
    completed = []

    async def sample_task():
        try:
            await asyncio.sleep(50.0)
        except asyncio.CancelledError:
            completed.append(True)
            raise

    spawn_task(sample_task(), name="alias_test_task")
    assert len(_background_tasks) == 1

    await asyncio.sleep(0.01)

    await cancel_all_background_tasks(timeout=2.0)
    assert len(_background_tasks) == 0
    assert completed == [True]


@pytest.mark.asyncio
async def test_tracked_http_clients_lifecycle():
    """
    Verifies that registered HTTP clients (both httpx and aiohttp styles)
    are properly closed and unregistered during close_tracked_http_clients.
    """
    mock_httpx = MagicMock(spec=["is_closed", "aclose"])
    mock_httpx.is_closed = False
    mock_httpx.aclose = AsyncMock()

    mock_aiohttp = MagicMock(spec=["closed", "close", "connector"])
    mock_aiohttp.closed = False
    mock_aiohttp.close = AsyncMock()
    mock_connector = MagicMock(spec=["closed", "close"])
    mock_connector.closed = False
    mock_connector.close = AsyncMock()
    mock_aiohttp.connector = mock_connector

    register_http_client(mock_httpx)
    register_http_client(mock_aiohttp)
    assert len(_tracked_http_clients) == 2

    # Unregister one and check
    unregister_http_client(mock_httpx)
    assert len(_tracked_http_clients) == 1
    register_http_client(mock_httpx)

    t0 = time.monotonic()
    await close_tracked_http_clients()
    elapsed = time.monotonic() - t0

    mock_httpx.aclose.assert_awaited_once()
    mock_aiohttp.close.assert_awaited_once()
    mock_connector.close.assert_awaited_once()
    assert len(_tracked_http_clients) == 0
    assert elapsed >= 0.240
    mock_connector.close.assert_awaited_once()
    assert len(_tracked_http_clients) == 0
    assert elapsed >= 0.240


@pytest.mark.asyncio
async def test_on_task_done_categorizes_connection_reset(caplog):
    """
    Verifies that _on_task_done logs connection drops as warning
    and real unexpected exceptions as error.
    """
    task_mgr_logger = logging.getLogger("task_manager")

    # 1. Connection reset
    async def failing_conn_task():
        raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")

    t1 = asyncio.create_task(failing_conn_task(), name="conn_reset_task")
    with caplog.at_level(logging.DEBUG, logger="task_manager"):
        try:
            await t1
        except ConnectionResetError:
            pass
        _on_task_done(t1)

    # Should contain warning for conn drop, not error
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING and "разрыва соединения" in r.message]
    assert len(warning_records) >= 1
    error_records_conn = [r for r in caplog.records if r.levelno == logging.ERROR and "conn_reset_task" in r.message]
    assert len(error_records_conn) == 0

    caplog.clear()

    # 2. Real error
    async def real_error_task():
        raise KeyError("unexpected_missing_key")

    t2 = asyncio.create_task(real_error_task(), name="real_error_task")
    with caplog.at_level(logging.DEBUG, logger="task_manager"):
        try:
            await t2
        except KeyError:
            pass
        _on_task_done(t2)

    error_records_real = [r for r in caplog.records if r.levelno == logging.ERROR and "real_error_task" in r.message]
    assert len(error_records_real) >= 1


@pytest.mark.asyncio
async def test_summarize_shared_http_client_close_and_drain():
    """
    Verifies that summarize.get_shared_http_client creates a valid client,
    registers it with task_manager, and close_shared_http_client closes it
    with the required 0.250s event loop yield.
    """
    import summarize

    client = summarize.get_shared_http_client()
    assert client is not None
    assert client in _tracked_http_clients

    t0 = time.monotonic()
    await summarize.close_shared_http_client()
    elapsed = time.monotonic() - t0

    assert summarize._SHARED_HTTP_CLIENT is None
    assert elapsed >= 0.240, f"Expected Proactor drain delay >= 0.24s, got {elapsed:.3f}s"

    # Subsequent call re-initializes cleanly
    new_client = summarize.get_shared_http_client()
    assert new_client is not None
    assert new_client is not client
    await summarize.close_shared_http_client()
