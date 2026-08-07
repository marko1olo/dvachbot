import asyncio
import logging
from typing import Coroutine, Set, Any

_background_tasks: Set[asyncio.Task] = set()

logger = logging.getLogger("task_manager")


def _on_task_done(task: asyncio.Task) -> None:
    """
    Снимает ссылку на завершённую задачу и ОБЯЗАТЕЛЬНО забирает исключение.
    """
    _background_tasks.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.error(
            "Фоновая задача %r завершилась с ошибкой: %s: %s",
            task.get_name(), type(exc).__name__, exc,
            exc_info=exc,
        )


def _derive_name(coro: Any) -> str | None:
    qualname = getattr(coro, "__qualname__", None)
    if qualname:
        return qualname
    code = getattr(coro, "cr_code", None)
    return getattr(code, "co_name", None)


async def _wrap_awaitable(awaitable: Any) -> Any:
    return await awaitable


def spawn_task(coro: Any, name: str = None) -> asyncio.Task:
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

async def cancel_all_background_tasks():
    """
    Cancels all background tasks currently tracked by the task manager.
    Should be called during graceful shutdown.
    """
    logger.info(f"Cancelling {len(_background_tasks)} active background tasks...")
    for task in list(_background_tasks):
        if not task.done():
            task.cancel()
    
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    logger.info("All background tasks have been cancelled and awaited.")
