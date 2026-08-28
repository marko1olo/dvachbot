# -*- coding: utf-8 -*-
"""
Unit test verifying that an aiosqlite connection worker thread does not raise
RuntimeError('Event loop is closed') if the asyncio event loop closes before
or during queue completion.
"""

import time
import asyncio
import unittest
import aiosqlite
from common.db_pool import _patch_aiosqlite_safe_worker


class TestAiosqliteClosedLoopSafety(unittest.TestCase):
    def test_worker_thread_graceful_on_closed_loop(self):
        # Ensure patch is active
        _patch_aiosqlite_safe_worker()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Open connection on loop
        conn = loop.run_until_complete(aiosqlite.connect(":memory:"))

        # Queue a task on worker thread
        def background_db_op():
            time.sleep(0.05)
            return "ok"

        fut = loop.create_future()
        conn._tx.put_nowait((fut, background_db_op))

        # Close the event loop immediately while task is in-flight!
        loop.close()

        # Let the worker thread pick up and process task against closed loop
        time.sleep(0.15)
        conn._stop_running()
        conn.join(timeout=1.0)

        # Thread must have terminated cleanly without uncaught exception
        self.assertFalse(conn.is_alive())
