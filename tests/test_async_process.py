import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.async_process import run_process_checked, AsyncProcessError

class MockProcess:
    def __init__(self, returncode=0, delay=None):
        self.kill_called = False
        self.returncode = returncode
        self.delay = delay

    async def wait(self):
        if self.kill_called:
            return self.returncode

        if self.delay:
            try:
                await asyncio.sleep(self.delay)
                return self.returncode
            except asyncio.CancelledError:
                raise
        else:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise

    def kill(self):
        self.kill_called = True


class TestAsyncProcess(unittest.IsolatedAsyncioTestCase):
    @patch('asyncio.create_subprocess_exec')
    async def test_timeout_handling(self, mock_create):
        mock_proc = MockProcess()
        mock_proc.kill = MagicMock(side_effect=mock_proc.kill)

        async def async_create(*args, **kwargs):
            return mock_proc

        mock_create.side_effect = async_create

        with self.assertRaises(asyncio.TimeoutError):
            await run_process_checked(['sleep', '10'], timeout=0.01)

        mock_proc.kill.assert_called_once()
        self.assertTrue(mock_proc.kill_called)

    @patch('asyncio.create_subprocess_exec')
    async def test_success(self, mock_create):
        mock_proc = MockProcess(returncode=0, delay=0.01)

        async def async_create(*args, **kwargs):
            return mock_proc

        mock_create.side_effect = async_create

        # Should not raise any exception
        await run_process_checked(['ls'])

    @patch('asyncio.create_subprocess_exec')
    async def test_failure(self, mock_create):
        mock_proc = MockProcess(returncode=1, delay=0.01)

        async def async_create(*args, **kwargs):
            return mock_proc

        mock_create.side_effect = async_create

        with self.assertRaises(AsyncProcessError) as cm:
            await run_process_checked(['ls'])

        self.assertEqual(cm.exception.returncode, 1)
        self.assertEqual(cm.exception.executable, 'ls')

    async def test_empty_args(self):
        with self.assertRaises(ValueError):
            await run_process_checked([])

if __name__ == '__main__':
    unittest.main()
