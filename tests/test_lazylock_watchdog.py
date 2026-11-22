import asyncio
import time
import pytest
from common.db_pool import LazyLock

@pytest.mark.asyncio
async def test_lazylock_watchdog_hung_break():
    lock = LazyLock()
    
    # 1. Acquire lock
    await lock.acquire()
    assert lock.locked()
    
    # 2. Simulate hung acquisition (> 35s watchdog threshold)
    lock._acquired_at = time.monotonic() - 40.0
    
    # 3. Another task tries to acquire: it should detect hung lock and break it
    async def second_task():
        return await lock.acquire(timeout=2.0)
        
    t = asyncio.create_task(second_task())
    res = await t
    assert res is True
    assert lock.locked()
    assert lock._owner is t
    lock.release()
    assert not lock.locked()

@pytest.mark.asyncio
async def test_lazylock_reentrant():
    lock = LazyLock()
    await lock.acquire()
    assert lock._depth == 1
    await lock.acquire()
    assert lock._depth == 2
    lock.release()
    assert lock._depth == 1
    assert lock.locked()
    lock.release()
    assert lock._depth == 0
    assert not lock.locked()
