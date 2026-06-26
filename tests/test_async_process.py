import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.async_process import run_process_checked, AsyncProcessError

class TestAsyncProcess(unittest.IsolatedAsyncioTestCase):
    @patch('asyncio.create_subprocess_exec')
    async def test_process_success(self, mock_create_subprocess):
        mock_process = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0
        mock_create_subprocess.return_value = mock_process

        await run_process_checked(['dummy', 'arg1'])

        mock_create_subprocess.assert_called_once_with(
            'dummy', 'arg1',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        mock_process.wait.assert_called_once()

    @patch('asyncio.create_subprocess_exec')
    async def test_process_failure(self, mock_create_subprocess):
        mock_process = MagicMock()
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.returncode = 1
        mock_create_subprocess.return_value = mock_process

        with self.assertRaises(AsyncProcessError) as cm:
            await run_process_checked(['dummy'])

        self.assertEqual(cm.exception.returncode, 1)
        self.assertEqual(cm.exception.executable, 'dummy')

    async def test_empty_args(self):
        with self.assertRaises(ValueError) as cm:
            await run_process_checked([])
        self.assertEqual(str(cm.exception), "empty process command")

    @patch('asyncio.create_subprocess_exec')
    async def test_process_timeout(self, mock_create_subprocess):
        # Create a mock process
        mock_process = MagicMock()

        wait_calls = 0
        async def mock_wait():
            nonlocal wait_calls
            wait_calls += 1
            if wait_calls == 1:
                # First time: simulate hanging process that gets cancelled by wait_for
                await asyncio.sleep(10)
            return 0

        mock_process.wait = AsyncMock(side_effect=mock_wait)
        mock_process.kill = MagicMock()
        mock_process.returncode = 0

        mock_create_subprocess.return_value = mock_process

        # Test that timeout is handled and propagated
        with self.assertRaises(asyncio.TimeoutError):
            await run_process_checked(['dummy'], timeout=0.01)

        # Verify that create_subprocess_exec was called correctly
        mock_create_subprocess.assert_called_once_with(
            'dummy',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # Verify process.kill was called
        mock_process.kill.assert_called_once()

        # Verify wait was called again after kill (so wait call count should be 2)
        self.assertEqual(mock_process.wait.call_count, 2)

if __name__ == '__main__':
    unittest.main()
