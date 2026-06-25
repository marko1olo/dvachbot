from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.task_manager import spawn_task, _background_tasks

class TestTaskManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Clear the background tasks set before each test
        _background_tasks.clear()

    async def dummy_coro(self):
        await asyncio.sleep(0.01)
        return "done"

    async def dummy_error_coro(self):
        await asyncio.sleep(0.01)
        raise ValueError("test error")

    async def test_spawn_task_adds_and_removes(self):
        task = spawn_task(self.dummy_coro())

        # It should be added immediately
        self.assertIn(task, _background_tasks)

        # Wait for completion
        await task

        # It should be removed after completion
        # add_done_callback happens at some point after task is done,
        # await task returns, but callbacks are scheduled.
        # To ensure the callback has run, we might need to yield to the event loop.
        await asyncio.sleep(0)
        self.assertNotIn(task, _background_tasks)

    async def test_spawn_task_with_name(self):
        task = spawn_task(self.dummy_coro(), name="my_test_task")

        # For python >= 3.8
        if hasattr(task, 'get_name'):
            self.assertEqual(task.get_name(), "my_test_task")

        await task
        await asyncio.sleep(0)
        self.assertNotIn(task, _background_tasks)

    async def test_spawn_task_error_removes(self):
        task = spawn_task(self.dummy_error_coro())
        self.assertIn(task, _background_tasks)

        with self.assertRaises(ValueError):
            await task

        await asyncio.sleep(0)
        self.assertNotIn(task, _background_tasks)

    async def test_spawn_task_type_error_fallback(self):
        original_create_task = asyncio.create_task

        def mock_create_task(coro, *args, **kwargs):
            if 'name' in kwargs:
                raise TypeError("name is an invalid keyword argument for create_task()")
            return original_create_task(coro)

        with patch('common.task_manager.asyncio.create_task', side_effect=mock_create_task):
            task = spawn_task(self.dummy_coro(), name="will_fail")
            self.assertIn(task, _background_tasks)
            await task
            await asyncio.sleep(0)
            self.assertNotIn(task, _background_tasks)

if __name__ == "__main__":
    unittest.main()
