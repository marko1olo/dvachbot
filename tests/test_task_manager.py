import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock
from pathlib import Path

# Setup env variables
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ['ADMIN_CHAT_ID'] = '123456789'
os.environ['API_ID'] = '123'
os.environ['API_HASH'] = 'test_hash'
os.environ['BASE_URL'] = 'http://test.com'

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.task_manager import spawn_task, _background_tasks

class TestTaskManager(unittest.IsolatedAsyncioTestCase):
    async def dummy_coro(self):
        await asyncio.sleep(0.01)

    async def test_spawn_task_normal(self):
        coro = self.dummy_coro()
        task = spawn_task(coro, name="test_task")

        self.assertIn(task, _background_tasks)
        self.assertEqual(task.get_name(), "test_task")

        # Wait for task to finish to let the callback remove it
        await task
        # allow callbacks to run
        await asyncio.sleep(0.02)

        self.assertNotIn(task, _background_tasks)

    async def test_spawn_task_type_error_fallback(self):
        coro = self.dummy_coro()

        # Use an actual dummy task to properly test the callback behavior
        # We create it before patching so it doesn't inflate the call_count
        real_task = asyncio.create_task(coro)

        def side_effect(*args, **kwargs):
            if 'name' in kwargs:
                raise TypeError("name is an invalid keyword argument for create_task")
            return real_task

        with patch('common.task_manager.asyncio.create_task') as mock_create_task:
            mock_create_task.side_effect = side_effect

            task = spawn_task(coro, name="test_task")

            self.assertIn(real_task, _background_tasks)
            self.assertEqual(task, real_task)

            # Verify it was called twice - once with name, once without
            self.assertEqual(mock_create_task.call_count, 2)
            mock_create_task.assert_any_call(coro, name="test_task")
            mock_create_task.assert_any_call(coro)

        # Cleanup
        await real_task
        await asyncio.sleep(0.02)

if __name__ == '__main__':
    unittest.main()
