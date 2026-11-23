import asyncio
import logging
import sys
from typing import Set, Any, Optional

_background_tasks: Set[asyncio.Task] = set()
_tracked_http_clients: Set[Any] = set()

logger = logging.getLogger("task_manager")


class ProactorNoiseFilter(logging.Filter):
    """
    Suppresses noisy WinError 10054 / _ProactorBasePipeTransport tracebacks
    emitted by asyncio default logger when sockets are reset by peer on Windows.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if (
            "_ProactorBasePipeTransport" in msg
            or "WinError 10054" in msg
            or "_call_connection_lost" in msg
            or "I/O operation on closed pipe" in msg
        ):
            return False
        return True


def install_proactor_safety_net() -> bool:
    """
    On Windows (ProactorEventLoop), abrupt socket disconnection by remote hosts
    (Telegram, Groq, Gemini, Edge-TTS) causes ConnectionResetError (WinError 10054)
    inside _ProactorBasePipeTransport._call_connection_lost when calling self._sock.shutdown().
    In Python on Windows, this unhandled exception aborts self._sock.close() and leaks
    the socket handle until GC, where __del__ then raises ValueError: I/O operation on closed pipe.
    
    This function installs a defensive patch around _ProactorBasePipeTransport._call_connection_lost
    and __del__ to ensure graceful socket cleanup without uncaught callback crashes.
    """
    if sys.platform != "win32":
        return False
    try:
        import asyncio.proactor_events as pe

        orig_call_connection_lost = pe._ProactorBasePipeTransport._call_connection_lost
        if not getattr(orig_call_connection_lost, "_is_proactor_safety_patched", False):
            def _patched_call_connection_lost(self, exc):
                try:
                    orig_call_connection_lost(self, exc)
                except (ConnectionResetError, OSError, ValueError):
                    try:
                        if hasattr(self, "_sock") and self._sock is not None:
                            self._sock.close()
                            self._sock = None
                    except Exception:
                        pass
                    if hasattr(self, "_server") and self._server is not None:
                        try:
                            self._server._detach(self)
                            self._server = None
                        except Exception:
                            pass
                    self._called_connection_lost = True

            _patched_call_connection_lost._is_proactor_safety_patched = True
            pe._ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost

        orig_del = pe._ProactorBasePipeTransport.__del__
        if not getattr(orig_del, "_is_proactor_safety_patched", False):
            def _patched_del(self, _warn=None):
                try:
                    if _warn is not None:
                        orig_del(self, _warn)
                    else:
                        orig_del(self)
                except (ValueError, OSError, AttributeError):
                    pass

            _patched_del._is_proactor_safety_patched = True
            pe._ProactorBasePipeTransport.__del__ = _patched_del

        logging.getLogger("asyncio").addFilter(ProactorNoiseFilter())
        return True
    except Exception as e:
        logger.warning(f"Could not install Windows Proactor safety net: {e}")
        return False


# Auto-install on Windows on import
if sys.platform == "win32":
    install_proactor_safety_net()


def _on_task_done(task: asyncio.Task) -> None:
    """
    Снимает ссылку на завершённую задачу и ОБЯЗАТЕЛЬНО забирает исключение.
    Логирует ожидаемые разрывы сокетов (WinError 10054 / reset by peer) как warning,
    а реальные сбои выполнения — как error.
    """
    _background_tasks.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        exc_type_name = type(exc).__name__
        is_conn_drop = isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError))
        if not is_conn_drop:
            if exc_type_name in ("ServerDisconnectedError", "ClientOSError", "RemoteProtocolError", "IncompleteReadError"):
                is_conn_drop = True
            elif isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10053, 10054, 10058):
                is_conn_drop = True

        if is_conn_drop:
            logger.warning(
                "Фоновая задача %r прервана из-за разрыва соединения (%s): %s",
                task.get_name(), exc_type_name, exc,
            )
        else:
            logger.error(
                "Фоновая задача %r завершилась с ошибкой: %s: %s",
                task.get_name(), exc_type_name, exc,
                exc_info=exc,
            )


def _derive_name(coro: Any) -> Optional[str]:
    qualname = getattr(coro, "__qualname__", None)
    if qualname:
        return qualname
    code = getattr(coro, "cr_code", None)
    return getattr(code, "co_name", None)


async def _wrap_awaitable(awaitable: Any) -> Any:
    return await awaitable


def register_http_client(client: Any) -> None:
    """
    Register an httpx.AsyncClient or aiohttp.ClientSession to be closed
    gracefully when close_all_tasks() is called during shutdown.
    """
    if client is not None:
        _tracked_http_clients.add(client)


def unregister_http_client(client: Any) -> None:
    """
    Unregister an HTTP client that was already closed.
    """
    _tracked_http_clients.discard(client)


async def close_tracked_http_clients() -> None:
    """
    Gracefully close all registered HTTP clients and sessions, followed by
    Windows Proactor event loop drain (await asyncio.sleep(0.250)).
    """
    clients = list(_tracked_http_clients)
    _tracked_http_clients.clear()

    for client in clients:
        try:
            # 1. aiohttp ClientSession (identified by .closed property and .close())
            if hasattr(client, "closed") and hasattr(client, "close") and callable(client.close):
                if not getattr(client, "closed", False):
                    res = client.close()
                    if asyncio.iscoroutine(res):
                        await res
                connector = getattr(client, "connector", None) or getattr(client, "_connector", None)
                if connector and not getattr(connector, "closed", False):
                    c_res = connector.close()
                    if asyncio.iscoroutine(c_res):
                        await c_res
            # 2. httpx.AsyncClient (identified by .aclose())
            elif hasattr(client, "aclose") and callable(client.aclose):
                if not getattr(client, "is_closed", False):
                    await client.aclose()
            # 3. Generic client with close()
            elif hasattr(client, "close") and callable(client.close):
                if not getattr(client, "is_closed", False) and not getattr(client, "closed", False):
                    res = client.close()
                    if asyncio.iscoroutine(res):
                        await res
        except Exception as e:
            logger.warning(f"Error closing tracked HTTP client {client!r}: {e}")

    await asyncio.sleep(0.250)


def spawn_task(coro: Any, name: Optional[str] = None) -> asyncio.Task:
    """
    Creates an asyncio Task and retains a hard reference to it
    until it completes, preventing accidental GC during heavy load.
    Supports standard coroutines and Aiogram SendMessage/TelegramMethod awaitables.
    """
    if not asyncio.iscoroutine(coro):
        coro = _wrap_awaitable(coro)

    if name is None:
        try:
            name = _derive_name(coro)
        except Exception:
            name = None

    try:
        task = asyncio.create_task(coro, name=name)
    except TypeError:
        task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


async def close_all_tasks(timeout: float = 10.0, close_http_clients: bool = True) -> None:
    """
    Cancels and awaits all background tasks currently tracked by task manager.
    Optionally closes summarize._SHARED_HTTP_CLIENT and any registered HTTP clients/sessions.
    Includes mandatory 0.250s sleep to let Windows Proactor transports drain cleanly.
    """
    active_tasks = [t for t in _background_tasks if not t.done()]
    count = len(active_tasks)
    if count > 0:
        logger.info(f"Cancelling {count} active background tasks...")
        for task in active_tasks:
            task.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(*active_tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({timeout}s) waiting for background tasks to cancel.")
        except Exception as e:
            logger.warning(f"Exception during background tasks cancellation: {e}")

    _background_tasks.clear()

    if close_http_clients:
        try:
            import summarize
            if hasattr(summarize, "close_shared_http_client"):
                await summarize.close_shared_http_client()
        except Exception as e:
            logger.debug(f"Could not close shared http client from summarize: {e}")

    await close_tracked_http_clients()
    logger.info("All background tasks and HTTP clients have been closed and drained.")


# Alias for full backward compatibility
cancel_all_background_tasks = close_all_tasks
