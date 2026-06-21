import asyncio
from common.task_manager import spawn_task
from typing import Coroutine, Set, Any

_background_tasks: Set[asyncio.Task] = set()

def spawn_task(coro: Coroutine, name: str = None) -> asyncio.Task:
    """
    Creates an asyncio Task and retains a hard reference to it 
    until it completes, preventing accidental GC during heavy load.
    """
    try:
        task = spawn_task(coro, name=name)
    except TypeError:
        # Fallback for older python versions if name isn't supported
        task = spawn_task(coro)
        
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
