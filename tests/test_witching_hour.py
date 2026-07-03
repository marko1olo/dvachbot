import unittest
from datetime import datetime, timedelta, timezone
import asyncio
import time
from unittest.mock import patch
import witching_hour

def test_is_witching_hour_active_initial_state():
    # Initial state is usually 0 for both timestamps
    witching_hour.witching_hour_start_ts = 0
    witching_hour.witching_hour_end_ts = 0
    with patch('time.time', return_value=1000):
        # When both are 0, 0 <= 1000 <= 0 is false.
        # But if time.time() happens to return 0, 0 <= 0 <= 0 is true.
        # Let's test non-zero time which is the common case
        assert not witching_hour.is_witching_hour_active()

    with patch('time.time', return_value=0):
        # Edge case: time.time() returns exactly 0
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_before_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=999):
        assert not witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_start():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_in_middle():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=1500):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_at_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2000):
        assert witching_hour.is_witching_hour_active()

def test_is_witching_hour_active_after_end():
    witching_hour.witching_hour_start_ts = 1000
    witching_hour.witching_hour_end_ts = 2000
    with patch('time.time', return_value=2001):
        assert not witching_hour.is_witching_hour_active()


MSK_OFFSET = timezone(timedelta(hours=3))

class StopLoopException(Exception):
    pass

class TestWitchingHourScheduler(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.orig_start = witching_hour.witching_hour_start_ts
        self.orig_end = witching_hour.witching_hour_end_ts

    def tearDown(self):
        witching_hour.witching_hour_start_ts = self.orig_start
        witching_hour.witching_hour_end_ts = self.orig_end

    @patch('witching_hour.asyncio.sleep')
    @patch('witching_hour.datetime')
    @patch('witching_hour.random.randint')
    async def test_witching_hour_scheduler_before_4am(self, mock_randint, mock_datetime, mock_sleep):
        mock_randint.return_value = 30

        # 01:00 MSK = 22:00 UTC previous day.
        now_utc = datetime(2023, 10, 1, 22, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now_utc

        mock_sleep.side_effect = StopLoopException()

        with self.assertRaises(StopLoopException):
            await witching_hour.witching_hour_scheduler()

        now_msk = now_utc.astimezone(MSK_OFFSET)
        target_date = now_msk
        start_time_msk = target_date.replace(hour=2, minute=30, second=0, microsecond=0)
        end_time_msk = start_time_msk + timedelta(hours=1)

        self.assertEqual(witching_hour.witching_hour_start_ts, start_time_msk.timestamp())
        self.assertEqual(witching_hour.witching_hour_end_ts, end_time_msk.timestamp())

        next_schedule_time = target_date.replace(hour=4, minute=5, second=0, microsecond=0)
        expected_sleep_seconds = (next_schedule_time - now_msk).total_seconds()

        mock_sleep.assert_called_once_with(max(10, expected_sleep_seconds))

    @patch('witching_hour.asyncio.sleep')
    @patch('witching_hour.datetime')
    @patch('witching_hour.random.randint')
    async def test_witching_hour_scheduler_after_4am(self, mock_randint, mock_datetime, mock_sleep):
        mock_randint.return_value = 15

        # 05:00 MSK
        now_utc = datetime(2023, 10, 1, 2, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now_utc

        mock_sleep.side_effect = StopLoopException()

        with self.assertRaises(StopLoopException):
            await witching_hour.witching_hour_scheduler()

        now_msk = now_utc.astimezone(MSK_OFFSET)
        target_date = now_msk + timedelta(days=1)
        start_time_msk = target_date.replace(hour=2, minute=15, second=0, microsecond=0)
        end_time_msk = start_time_msk + timedelta(hours=1)

        self.assertEqual(witching_hour.witching_hour_start_ts, start_time_msk.timestamp())
        self.assertEqual(witching_hour.witching_hour_end_ts, end_time_msk.timestamp())

        next_schedule_time = target_date.replace(hour=4, minute=5, second=0, microsecond=0)
        expected_sleep_seconds = (next_schedule_time - now_msk).total_seconds()

        mock_sleep.assert_called_once_with(max(10, expected_sleep_seconds))
