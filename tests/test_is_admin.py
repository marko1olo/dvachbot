import sys
import os
import unittest
import asyncio

try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

os.environ["SECRET_KEY"] = "test-secret-key-12345"

import main

class TestIsAdmin(unittest.TestCase):
    def setUp(self):
        # Save original BOARD_CONFIG
        self.original_config = getattr(main, 'BOARD_CONFIG', {})
        main.BOARD_CONFIG = {
            'board_a': {'admins': {1, 2, 3}},
            'board_b': {'admins': set()},
            'board_c': {}
        }

    def tearDown(self):
        # Restore original BOARD_CONFIG
        main.BOARD_CONFIG = self.original_config

    def test_is_admin(self):
        # Happy path - valid admins
        self.assertTrue(main.is_admin(1, 'board_a'))
        self.assertTrue(main.is_admin(3, 'board_a'))

        # Negative path - user is not an admin
        self.assertFalse(main.is_admin(4, 'board_a'))

        # Board exists but has empty admins set
        self.assertFalse(main.is_admin(1, 'board_b'))

        # Board exists but has no admins key
        self.assertFalse(main.is_admin(1, 'board_c'))

        # Non-existent board
        self.assertFalse(main.is_admin(1, 'nonexistent_board'))

        # Invalid board_id (empty string)
        self.assertFalse(main.is_admin(1, ''))

        # Invalid board_id (None)
        self.assertFalse(main.is_admin(1, None))

if __name__ == "__main__":
    unittest.main()
