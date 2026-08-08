import asyncio
import time
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# Put root directory in sys.path
root_dir = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, root_dir)

from common.db_pool import db_lock, db_sleep, LazyLock

async def test_scenario_lock_ownership_tracking():
    print("[1/5] Testing LazyLock ownership tracking...")
    lock = LazyLock()
    
    assert not lock.locked(), "Lock should be unlocked initially"
    assert not lock.is_owned_by_current_task(), "Should not be owned initially"
    
    async with lock:
        assert lock.locked(), "Lock should be locked inside context"
        assert lock.is_owned_by_current_task(), "Should be owned by current task"
        assert lock.locked_by_current_task(), "locked_by_current_task should return True"
        
        # Verify another task sees locked()=True but is_owned_by_current_task()=False
        other_owned = [None]
        async def subtask():
            other_owned[0] = lock.is_owned_by_current_task()
            
        t = asyncio.create_task(subtask())
        await t
        assert other_owned[0] is False, "Other task must NOT report owning the lock"
        
    assert not lock.locked(), "Lock should be released"
    assert not lock.is_owned_by_current_task(), "Should not be owned after exit"
    print("  -> PASSED")

async def test_scenario_db_sleep_owner_vs_nonowner():
    print("[2/5] Testing db_sleep behavior for lock owner vs non-owner...")
    
    # Non-owner calling db_sleep: lock should remain unaffected
    async with db_lock:
        non_owner_released = [False]
        async def non_owner_task():
            # db_lock is held by parent task, not this task
            assert not db_lock.is_owned_by_current_task(), "Non-owner task must not own db_lock"
            start_t = time.monotonic()
            await db_sleep(0.05)
            dur = time.monotonic() - start_t
            assert dur >= 0.04, f"db_sleep non-owner delayed correctly ({dur:.3f}s)"
            # Verify db_lock is STILL locked by the parent task!
            assert db_lock.locked(), "db_lock must remain locked by owner"
            non_owner_released[0] = True
            
        t = asyncio.create_task(non_owner_task())
        await t
        assert non_owner_released[0], "Non-owner task completed"
        assert db_lock.is_owned_by_current_task(), "Parent task still owns db_lock"

    # Owner calling db_sleep: lock should be temporarily released during sleep and reacquired after
    async with db_lock:
        assert db_lock.is_owned_by_current_task()
        interleaved_acquired = [False]
        
        async def other_task_acquires_during_sleep():
            # Wait a tiny bit for main task to enter db_sleep
            await asyncio.sleep(0.01)
            # Main task released db_lock in db_sleep, so this task should get the lock
            async with db_lock:
                interleaved_acquired[0] = True

        bg_task = asyncio.create_task(other_task_acquires_during_sleep())
        
        # Call db_sleep while holding db_lock
        await db_sleep(0.05)
        await bg_task
        
        assert interleaved_acquired[0], "Interleaved task successfully acquired lock while owner slept!"
        assert db_lock.is_owned_by_current_task(), "Owner task reacquired db_lock upon wake up!"

    print("  -> PASSED")

async def test_scenario_high_concurrency_stress():
    print("[3/5] Stress testing high concurrency db_sleep (50 workers x 20 iterations)...")
    
    counter = [0]
    errors = []
    deadlocks_detected = False
    
    async def worker(worker_id: int):
        try:
            for i in range(20):
                # 50% chance of acquiring db_lock, 50% chance of calling db_sleep without lock
                if i % 2 == 0:
                    async with db_lock:
                        assert db_lock.is_owned_by_current_task(), f"Worker {worker_id} must own lock"
                        counter[0] += 1
                        await db_sleep(0.001)
                        assert db_lock.is_owned_by_current_task(), f"Worker {worker_id} must reacquire lock"
                else:
                    assert not db_lock.is_owned_by_current_task() or db_lock._owner == asyncio.current_task()
                    await db_sleep(0.001)
        except Exception as e:
            errors.append((worker_id, e))

    tasks = [asyncio.create_task(worker(i)) for i in range(50)]
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)
    except asyncio.TimeoutError:
        deadlocks_detected = True

    assert not deadlocks_detected, "DEADLOCK DETECTED! Tasks timed out after 10 seconds."
    assert len(errors) == 0, f"Errors occurred during concurrency stress: {errors}"
    assert counter[0] == 50 * 10, f"Expected 500 increment operations, got {counter[0]}"
    print(f"  -> PASSED ({counter[0]} operations completed cleanly)")

async def test_scenario_cancellation_and_exceptions():
    print("[4/5] Testing db_sleep cancellation & exception safety...")
    
    # Test task cancelled during db_sleep
    cancelled_reacquired = [False]
    
    async def cancelling_task():
        async with db_lock:
            assert db_lock.is_owned_by_current_task()
            try:
                await db_sleep(1.0)
            except asyncio.CancelledError:
                # The finally block in db_sleep should reacquire the lock even on CancelledError!
                cancelled_reacquired[0] = db_lock.is_owned_by_current_task()
                raise

    t = asyncio.create_task(cancelling_task())
    await asyncio.sleep(0.02)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass

    assert cancelled_reacquired[0], "db_sleep must reacquire lock in finally block even when cancelled"
    assert not db_lock.locked(), "Lock must be released when cancelling_task exits context manager"
    print("  -> PASSED")

async def test_scenario_no_lock_stealing_under_race():
    print("[5/5] Testing zero lock stealing under heavy race conditions...")
    
    stolen_locks = []
    
    async def task_a():
        async with db_lock:
            # Task A holds lock and sleeps
            await db_sleep(0.05)
            # Verify lock is still owned by Task A when it wakes up
            if not db_lock.is_owned_by_current_task():
                stolen_locks.append("Task A lock stolen!")

    async def task_b():
        # Task B calls db_sleep WITHOUT holding db_lock
        await db_sleep(0.02)
        # Task B calls release directly on db_lock? Non-owner shouldn't release!
        if db_lock.is_owned_by_current_task():
            stolen_locks.append("Task B falsely acquired ownership!")

    await asyncio.gather(task_a(), task_b())
    assert len(stolen_locks) == 0, f"Lock stealing occurred: {stolen_locks}"
    print("  -> PASSED")

async def main():
    print("=== R3 EMPIRICAL STRESS TEST SUITE ===")
    await test_scenario_lock_ownership_tracking()
    await test_scenario_db_sleep_owner_vs_nonowner()
    await test_scenario_high_concurrency_stress()
    await test_scenario_cancellation_and_exceptions()
    await test_scenario_no_lock_stealing_under_race()
    print("\n[SUCCESS] ALL 5/5 R3 STRESS SCENARIOS PASSED WITH ZERO LOCK STEAL, ZERO DEADLOCKS, ZERO UNHANDLED EXCEPTIONS!")

if __name__ == "__main__":
    asyncio.run(main())
