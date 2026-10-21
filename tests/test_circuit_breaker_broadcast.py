import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shared_state
from broadcaster import MessageBroadcaster
from common.board_config import BOARD_CONFIG


class TestCircuitBreakerBroadcast(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.board_id = "b"
        self.board_token = BOARD_CONFIG.get("b", {}).get("token", "dummy_b_token")
        self.bot_instance = MagicMock()
        self.bot_instance.token = self.board_token

        self.b_data = {
            "users": {
                "active": set(range(1, 1001)),
                "banned": set(),
            },
            "user_settings": {},
            "user_state": {},
        }
        shared_state.board_data["b"] = self.b_data

    async def test_circuit_breaker_suppresses_mass_removal(self):
        """If > 10% or > 25 users are flagged as blocked, removal must be aborted."""
        cfg = shared_state.BroadcastConfig(
            bot_instance=self.bot_instance,
            board_id=self.board_id,
            recipients=set(range(1, 1001)),
            content={"type": "text", "text": "Test"}
        )
        broadcaster = MessageBroadcaster(cfg)
        # 150 users flagged as blocked (> 10% of 1000)
        broadcaster.blocked_users = set(range(1, 151))

        with patch("common.database.remove_users_from_board_batch", new_callable=AsyncMock) as mock_db_remove:
            await broadcaster._remove_blocked_users()
            # Database removal must NOT have been called
            mock_db_remove.assert_not_called()
            # Active set in memory must remain intact
            self.assertEqual(len(self.b_data["users"]["active"]), 1000)

    async def test_token_mismatch_suppresses_removal(self):
        """If broadcaster bot token does not match board token, removal must be aborted."""
        foreign_bot = MagicMock()
        foreign_bot.token = "completely_different_token_12345"

        cfg = shared_state.BroadcastConfig(
            bot_instance=foreign_bot,
            board_id=self.board_id,
            recipients=set(range(1, 101)),
            content={"type": "text", "text": "Test"}
        )
        broadcaster = MessageBroadcaster(cfg)
        # Small number of blocked users (below threshold)
        broadcaster.blocked_users = {1, 2, 3}

        with patch("common.database.remove_users_from_board_batch", new_callable=AsyncMock) as mock_db_remove:
            await broadcaster._remove_blocked_users()
            mock_db_remove.assert_not_called()
            self.assertIn(1, self.b_data["users"]["active"])
            self.assertIn(2, self.b_data["users"]["active"])
            self.assertIn(3, self.b_data["users"]["active"])

    async def test_normal_churn_removal_proceeds(self):
        """If blocked users is below threshold and token matches, removal proceeds normally."""
        cfg = shared_state.BroadcastConfig(
            bot_instance=self.bot_instance,
            board_id=self.board_id,
            recipients=set(range(1, 1001)),
            content={"type": "text", "text": "Test"}
        )
        broadcaster = MessageBroadcaster(cfg)
        # 3 normal user blocks
        broadcaster.blocked_users = {10, 20, 30}

        with patch("common.database.remove_users_from_board_batch", new_callable=AsyncMock) as mock_db_remove:
            await broadcaster._remove_blocked_users()
            mock_db_remove.assert_called_once()
            called_args = mock_db_remove.call_args[0]
            self.assertEqual(set(called_args[0]), {10, 20, 30})
            self.assertEqual(called_args[1], "b")
            self.assertNotIn(10, self.b_data["users"]["active"])
            self.assertNotIn(20, self.b_data["users"]["active"])
            self.assertNotIn(30, self.b_data["users"]["active"])
