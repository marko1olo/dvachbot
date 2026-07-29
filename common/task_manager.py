import asyncio
import logging
from typing import Coroutine, Set

_background_tasks: Set[asyncio.Task] = set()

logger = logging.getLogger("task_manager")


def _on_task_done(task: asyncio.Task) -> None:
    """
    Снимает ссылку на завершённую задачу и ОБЯЗАТЕЛЬНО забирает исключение.

    Раньше callback только выбрасывал задачу из множества. Исключение
    оставалось в объекте задачи невостребованным: при завершении не
    логировалось ничего, а стандартное предупреждение asyncio «Task exception
    was never retrieved» появлялось лишь когда объект собирал GC — без имени
    задачи и мимо логгеров проекта. То есть упавшая fire-and-forget работа
    была фактически неотслеживаемой, а таких вызовов в проекте 125.

    Отмена задачи — штатная ситуация (например замена таймера альбома или
    остановка бота), поэтому она не логируется.
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


def _derive_name(coro: Coroutine) -> str | None:
    """
    Имя задачи из самой корутины.

    Все 159 вызовов spawn_task в проекте идут без name, поэтому по умолчанию
    задача получила бы бесполезное «Task-42», и лог ошибки не позволял бы
    понять, ЧТО именно упало. Берём имя функции — так сообщение сразу
    указывает на источник, и не нужно править каждый вызов.
    """
    qualname = getattr(coro, "__qualname__", None)
    if qualname:
        return qualname
    code = getattr(coro, "cr_code", None)
    return getattr(code, "co_name", None)


def spawn_task(coro: Coroutine, name: str = None) -> asyncio.Task:
    """
    Creates an asyncio Task and retains a hard reference to it
    until it completes, preventing accidental GC during heavy load.
    """
    if name is None:
        try:
            name = _derive_name(coro)
        except Exception:
            name = None
    try:
        task = asyncio.create_task(coro, name=name)
    except TypeError:
        # Fallback for older python versions if name isn't supported
        task = asyncio.create_task(coro)

    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task
