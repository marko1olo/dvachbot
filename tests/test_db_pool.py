import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from common.db_pool import get_pool, create_pool, close_pool, LazyLock, db_sleep
import common.db_pool as db_pool_module

class TestDbPool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset globals for clean state
        db_pool_module._db_connection = None
        db_pool_module._reconnect_lock = LazyLock()
        db_pool_module.db_lock = LazyLock()

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    async def test_get_pool_retry_failure(self, mock_sleep, mock_connect):
        # Setup mock to always raise an exception
        mock_connect.side_effect = Exception("Mocked connection failure")

        # Call the function and expect the exception to be re-raised
        with self.assertRaises(Exception) as context:
            await get_pool()

        self.assertEqual(str(context.exception), "Mocked connection failure")

        # Verify connect was called exactly 3 times
        self.assertEqual(mock_connect.call_count, 3)

        # Verify sleep was called exactly 2 times with 2 seconds
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(2)

    @patch('common.db_pool.aiosqlite.connect', new_callable=AsyncMock)
    @patch('common.db_pool.asyncio.sleep', new_callable=AsyncMock)
    async def test_get_pool_success_after_retries(self, mock_sleep, mock_connect):
        # Setup mock to fail twice, then succeed
        mock_conn = AsyncMock()
        mock_connect.side_effect = [Exception("Fail 1"), Exception("Fail 2"), mock_conn]

        pool = await get_pool()

        self.assertEqual(pool, mock_conn)
        self.assertEqual(mock_connect.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(2)

    async def test_lazy_lock_ownership_tracking(self):
        """Проверяет отслеживание владельца замка в LazyLock."""
        lock = LazyLock()
        self.assertFalse(lock.is_owned_by_current_task())
        self.assertFalse(lock.locked_by_current_task())

        async with lock:
            self.assertTrue(lock.is_owned_by_current_task())
            self.assertTrue(lock.locked_by_current_task())

            # Проверяем, что из другой задачи замок не считается принадлежащим ей
            other_task_owned = None
            async def check_other_task():
                nonlocal other_task_owned
                other_task_owned = lock.is_owned_by_current_task()

            await asyncio.create_task(check_other_task())
            self.assertFalse(other_task_owned)

        self.assertFalse(lock.is_owned_by_current_task())

    async def test_db_sleep_release_and_reacquire_when_holding_lock(self):
        """a) db_sleep отпускает db_lock, если вызван владельцем замка, и перезахватывает его после сна."""
        async with db_pool_module.db_lock:
            self.assertTrue(db_pool_module.db_lock.is_owned_by_current_task())

            lock_was_unlocked_during_sleep = False

            async def checker():
                nonlocal lock_was_unlocked_during_sleep
                await asyncio.sleep(0.01)
                lock_was_unlocked_during_sleep = not db_pool_module.db_lock.locked()

            checker_task = asyncio.create_task(checker())
            # Вызываем db_sleep прямо в той задаче, которая удерживает замок
            await db_sleep(0.05)
            await checker_task

            # После возврата из db_sleep замок снова принадлежит текущей задаче
            self.assertTrue(lock_was_unlocked_during_sleep)
            self.assertTrue(db_pool_module.db_lock.is_owned_by_current_task())

    async def test_db_sleep_does_not_release_lock_held_by_other_task(self):
        """b) db_sleep НЕ отпускает db_lock, если вызван задачей, не удерживающей lock."""
        lock_holder_started = asyncio.Event()
        lock_holder_can_exit = asyncio.Event()
        lock_held_by_task_a = False

        async def task_a():
            nonlocal lock_held_by_task_a
            async with db_pool_module.db_lock:
                lock_held_by_task_a = db_pool_module.db_lock.is_owned_by_current_task()
                lock_holder_started.set()
                await lock_holder_can_exit.wait()

        task_a_future = asyncio.create_task(task_a())
        await lock_holder_started.wait()

        # Task B вызывает db_sleep, НЕ удерживая db_lock
        self.assertFalse(db_pool_module.db_lock.is_owned_by_current_task())
        await db_sleep(0.02)

        # Проверяем, что Task A ВСЁ ЕЩЁ держит lock и Task B его не отжала
        self.assertTrue(db_pool_module.db_lock.locked())
        self.assertFalse(db_pool_module.db_lock.is_owned_by_current_task())

        lock_holder_can_exit.set()
        await task_a_future

    async def test_db_sleep_does_not_acquire_lock_if_not_held_before(self):
        """c) db_sleep НЕ захватывает db_lock по завершении, если вызывающая задача не удерживала lock до сна."""
        self.assertFalse(db_pool_module.db_lock.is_owned_by_current_task())
        self.assertFalse(db_pool_module.db_lock.locked())

        await db_sleep(0.02)

        # После сна замок остался не захваченным
        self.assertFalse(db_pool_module.db_lock.locked())
        self.assertFalse(db_pool_module.db_lock.is_owned_by_current_task())

    async def test_db_sleep_concurrent_tasks_no_lock_stealing_or_deadlock(self):
        """d) Параллельные задачи с db_sleep выполняются без кражи замка и дедлоков."""
        execution_order = []

        async def task_with_lock():
            async with db_pool_module.db_lock:
                execution_order.append("task_with_lock_start")
                await db_sleep(0.05)
                execution_order.append("task_with_lock_end")

        async def task_without_lock():
            execution_order.append("task_without_lock_start")
            await db_sleep(0.05)
            execution_order.append("task_without_lock_end")

        async def task_waiting_for_lock():
            await asyncio.sleep(0.01) # Даем первому взять замок
            async with db_pool_module.db_lock:
                execution_order.append("task_waiting_for_lock")

        await asyncio.gather(
            task_with_lock(),
            task_without_lock(),
            task_waiting_for_lock()
        )

        self.assertIn("task_with_lock_start", execution_order)
        self.assertIn("task_with_lock_end", execution_order)
        self.assertIn("task_without_lock_start", execution_order)
        self.assertIn("task_without_lock_end", execution_order)
        self.assertIn("task_waiting_for_lock", execution_order)
        # Убеждаемся, что замок в итоге свободен
        self.assertFalse(db_pool_module.db_lock.locked())

if __name__ == '__main__':
    unittest.main()
