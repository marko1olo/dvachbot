import asyncio
import pytest
import aiosqlite
from common.db_pool import LazyLock, db_lock, db_sleep

@pytest.mark.asyncio
async def test_db_sleep_cancellation_during_sleep():
    """
    Stress-test: Task acquires db_lock, calls db_sleep, and is cancelled during asyncio.sleep.
    Verify: Lock is reacquired during finally, and when task finishes unwinding, lock is cleanly released.
    """
    lock = LazyLock()
    acquired_evt = asyncio.Event()

    async def worker():
        async with lock:
            acquired_evt.set()
            # Wait inside db_sleep with custom delay
            # We mock db_lock in db_sleep by testing logic directly or via db_lock
            pass

    # Now test with global db_lock
    lock_held = asyncio.Event()

    async def task_holding_lock():
        async with db_lock:
            lock_held.set()
            await db_sleep(5.0)

    t = asyncio.create_task(task_holding_lock())
    await lock_held.wait()
    
    # Verify db_lock was released during db_sleep
    assert not db_lock.locked()
    assert not db_lock.is_owned_by_current_task()

    # Cancel task during sleep
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t

    # After cancellation unwinds through db_sleep's finally (which reacquires lock)
    # and async with db_lock's __aexit__ (which releases lock),
    # db_lock must be completely unlocked and free!
    assert not db_lock.locked(), "db_lock was left locked after cancelled task unwound!"
    assert db_lock._owner is None, "db_lock owner was not cleared!"

@pytest.mark.asyncio
async def test_db_sleep_cancellation_during_reacquire():
    """
    Stress-test: Task A acquires db_lock, calls db_sleep. Task B grabs db_lock.
    Task A finishes asyncio.sleep and is blocked trying to reacquire db_lock in finally.
    Task A is cancelled while blocked on reacquire.
    Verify: Task B still holds db_lock, and when Task B finishes, db_lock is released cleanly.
    """
    task_a_released = asyncio.Event()
    task_b_got_lock = asyncio.Event()

    async def task_a():
        async with db_lock:
            # db_sleep will release db_lock, sleep 0.1s, then try to reacquire
            await db_sleep(0.1)

    async def task_b():
        await asyncio.sleep(0.02) # Wait for Task A to enter db_sleep and release lock
        async with db_lock:
            task_b_got_lock.set()
            await asyncio.sleep(0.3) # Hold lock long enough for Task A to attempt reacquire

    ta = asyncio.create_task(task_a())
    tb = asyncio.create_task(task_b())

    await task_b_got_lock.wait()
    # At this point, Task B holds db_lock. Task A is waking up from sleep(0.1) and waiting on db_lock.acquire()
    await asyncio.sleep(0.15)
    
    # Cancel Task A while it is waiting in finally: await db_lock.acquire()
    ta.cancel()
    with pytest.raises(asyncio.CancelledError):
        await ta

    # Task B should still complete normally holding db_lock
    await tb

    assert not db_lock.locked(), "db_lock should be unlocked after Task B completes!"
    assert db_lock._owner is None, "db_lock owner should be None!"

@pytest.mark.asyncio
async def test_non_owner_calling_db_sleep():
    """
    Stress-test: Task A holds db_lock. Task B (not owner) calls db_sleep.
    Verify: Task B does not release Task A's lock, nor does it affect Task A's ownership.
    """
    task_a_holding = asyncio.Event()
    task_b_done = asyncio.Event()

    async def task_a():
        async with db_lock:
            task_a_holding.set()
            await asyncio.sleep(0.2)

    async def task_b():
        await task_a_holding.wait()
        assert db_lock.locked()
        assert not db_lock.is_owned_by_current_task()
        
        # Call db_sleep from non-owner task
        await db_sleep(0.05)
        
        # Verify lock was NOT released during Task B's sleep
        assert db_lock.locked()
        assert not db_lock.is_owned_by_current_task()
        task_b_done.set()

    ta = asyncio.create_task(task_a())
    tb = asyncio.create_task(task_b())

    await task_b_done.wait()
    await ta

    assert not db_lock.locked()

@pytest.mark.asyncio
async def test_high_concurrency_db_sleep_retries():
    """
    Stress-test: 50 concurrent tasks contending for db_lock with simulated DB locked exceptions and rapid retries.
    """
    counter = 0
    num_tasks = 50

    async def worker(worker_id: int):
        nonlocal counter
        for attempt in range(5):
            async with db_lock:
                assert db_lock.is_owned_by_current_task()
                # Simulate work
                current_val = counter
                await db_sleep(0.001)
                counter = current_val + 1
                break

    tasks = [asyncio.create_task(worker(i)) for i in range(num_tasks)]
    await asyncio.gather(*tasks)

    assert counter == num_tasks
    assert not db_lock.locked()

@pytest.mark.asyncio
async def test_lazylock_cross_task_safety():
    """
    Verify LazyLock correctly identifies owner across multiple tasks.
    """
    lock = LazyLock()
    
    assert not lock.locked()
    assert not lock.is_owned_by_current_task()

    async with lock:
        assert lock.locked()
        assert lock.is_owned_by_current_task()

        async def subtask():
            return lock.is_owned_by_current_task()

        sub_result = await asyncio.create_task(subtask())
        assert not sub_result, "Subtask should NOT be marked as owner of the lock!"

    assert not lock.locked()
    assert not lock.is_owned_by_current_task()
