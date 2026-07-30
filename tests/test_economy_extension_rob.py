import asyncio
import json
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, '.')

from economy_extension import cmd_rob, get_reply_target
from tests.economy_live import live_economy, BOARD

ROBBER = 1001
VICTIM = 1002

class TestEconomyExtensionCmdRob(IsolatedAsyncioTestCase):

    async def test_without_reply(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            msg = live.message(ROBBER, with_reply=False)
            msg.reply = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=None)):
                await cmd_rob(msg, BOARD)

            msg.reply.assert_awaited_with("Нужно сделать Reply на пост жертвы!")
            self.assertTrue((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(ROBBER), 100.0)

    async def test_self_robbery(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            msg = live.message(ROBBER)
            msg.reply = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=ROBBER)):
                await cmd_rob(msg, BOARD)

            msg.reply.assert_awaited_with("Нельзя ограбить самого себя.")
            self.assertTrue((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(ROBBER), 100.0)

    async def test_without_knife(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {})
            msg = live.message(ROBBER)
            msg.reply = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=VICTIM)):
                await cmd_rob(msg, BOARD)

            msg.reply.assert_awaited_with("У тебя нет заточки! Купи её в /shop.")

    async def test_tinfoil_hat_defense(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 300.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 1000.0, {"tinfoil_hat": int(time.time()) + 3600})
            msg = live.message(ROBBER)
            msg.bot.send_message = AsyncMock()
            msg.delete = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=VICTIM)):
                await cmd_rob(msg, BOARD)

            self.assertFalse((await live.items_of(ROBBER))["knife_gun"])
            msg.bot.send_message.assert_any_call(ROBBER, "🔪 Твоя заточка сломалась о Шапочку из фольги жертвы! Ограбление не удалось.", parse_mode="HTML")

    async def test_broke_victim(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 100.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 0.0, {})
            msg = live.message(ROBBER)
            msg.bot.send_message = AsyncMock()
            msg.delete = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=VICTIM)):
                await cmd_rob(msg, BOARD)

            self.assertFalse((await live.items_of(ROBBER))["knife_gun"])
            msg.bot.send_message.assert_any_call(ROBBER, "🔪 Ты приставил заточку, но у жертвы в карманах только дыры... Грабить нечего.", parse_mode="HTML")

    async def test_successful_robbery(self):
        async with live_economy() as live:
            await live.seed_user(ROBBER, 0.0, {"knife_gun": True})
            await live.seed_user(VICTIM, 500.0, {})
            msg = live.message(ROBBER)
            msg.bot.send_message = AsyncMock()
            msg.delete = AsyncMock()

            with patch("economy_extension.get_reply_target", AsyncMock(return_value=VICTIM)):
                with patch("random.uniform", return_value=0.2):
                    await cmd_rob(msg, BOARD)

            self.assertFalse((await live.items_of(ROBBER))["knife_gun"])
            self.assertEqual(await live.balance_of(VICTIM), 400.0)
            self.assertEqual(await live.balance_of(ROBBER), 100.0)

if __name__ == "__main__":
    import unittest
    unittest.main()
