import json
import time
import unittest
from unittest.mock import patch, AsyncMock

from tests.economy_live import BOARD, live_economy
import economy_extension

THROWER = 3001
TARGET = 3002

class TestEconomyExtensionShit(unittest.IsolatedAsyncioTestCase):
    async def test_cmd_shit_no_board(self):
        msg = AsyncMock()
        await economy_extension.cmd_shit(msg, None)
        msg.reply.assert_not_called()

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_no_reply(self, mock_get_reply_target):
        mock_get_reply_target.return_value = None
        async with live_economy() as live:
            msg = live.message(THROWER, with_reply=False)
            msg.reply = AsyncMock()
            await economy_extension.cmd_shit(msg, BOARD)
            msg.reply.assert_awaited_with("Нужно сделать Reply на пост жертвы!")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_target_self(self, mock_get_reply_target):
        mock_get_reply_target.return_value = THROWER
        async with live_economy() as live:
            msg = live.message(THROWER)
            msg.reply = AsyncMock()
            await economy_extension.cmd_shit(msg, BOARD)
            msg.reply.assert_awaited_with("Ты и так говно.")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_no_gun(self, mock_get_reply_target):
        mock_get_reply_target.return_value = TARGET
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {})
            msg = live.message(THROWER)
            msg.reply = AsyncMock()
            await economy_extension.cmd_shit(msg, BOARD)
            msg.reply.assert_awaited_with("У тебя нет говна в карманах! Купи его в /shop.")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_success(self, mock_get_reply_target):
        mock_get_reply_target.return_value = TARGET
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            msg = live.message(THROWER)
            msg.bot.send_message = AsyncMock()
            with patch("random.random", return_value=0.5):
                await economy_extension.cmd_shit(msg, BOARD)

            thrower_items = await live.items_of(THROWER)
            self.assertFalse(thrower_items.get("shit_gun"))
            self.assertNotIn("shit_until", thrower_items)

            target_items = await live.items_of(TARGET)
            self.assertIn("shit_until", target_items)

            calls = msg.bot.send_message.await_args_list
            self.assertTrue(any("успешно метнул кусок говна" in call.args[1] for call in calls))

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_tinfoil(self, mock_get_reply_target):
        mock_get_reply_target.return_value = TARGET
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 100.0, {"tinfoil_hat": int(time.time()) + 3600})
            msg = live.message(THROWER)
            msg.bot.send_message = AsyncMock()

            await economy_extension.cmd_shit(msg, BOARD)

            thrower_items = await live.items_of(THROWER)
            self.assertFalse(thrower_items.get("shit_gun"))
            self.assertIn("shit_until", thrower_items)

            target_items = await live.items_of(TARGET)
            self.assertNotIn("shit_until", target_items)

            # The exact message happens in line 301
            calls = msg.bot.send_message.await_args_list
            self.assertTrue(any("ветер дунул в лицо" in call.args[1] for call in calls))

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_shit_bounce(self, mock_get_reply_target):
        mock_get_reply_target.return_value = TARGET
        async with live_economy() as live:
            await live.seed_user(THROWER, 100.0, {"shit_gun": True})
            await live.seed_user(TARGET, 100.0, {})
            msg = live.message(THROWER)
            msg.bot.send_message = AsyncMock()

            with patch("random.random", return_value=0.1): # < 0.20 causes bounce
                await economy_extension.cmd_shit(msg, BOARD)

            thrower_items = await live.items_of(THROWER)
            self.assertFalse(thrower_items.get("shit_gun"))
            self.assertIn("shit_until", thrower_items)

            target_items = await live.items_of(TARGET)
            self.assertNotIn("shit_until", target_items)

            calls = msg.bot.send_message.await_args_list
            self.assertTrue(any("ветер дунул в лицо" in call.args[1] for call in calls))

if __name__ == '__main__':
    unittest.main()
