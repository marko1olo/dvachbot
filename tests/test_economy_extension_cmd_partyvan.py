import asyncio
import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import economy_extension

class DummyLock:
    async def __aenter__(self):
        pass
    async def __aexit__(self, exc_type, exc, tb):
        pass

class TestEconomyExtensionPartyvan(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute("CREATE TABLE Users (user_id INTEGER, board_id TEXT, active_items TEXT, balance INTEGER)")
        await self.db.commit()

        patcher = patch('economy_extension.get_pool', return_value=self.db)
        self.mock_get_pool = patcher.start()
        self.addCleanup(patcher.stop)

        patcher_lock = patch('economy_extension.db_lock', new_callable=lambda: DummyLock())
        self.mock_db_lock = patcher_lock.start()
        self.addCleanup(patcher_lock.stop)

    async def asyncTearDown(self):
        await self.db.close()

    def get_mock_message(self):
        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = 123
        msg.reply = AsyncMock()
        msg.bot = MagicMock()
        msg.bot.send_message = AsyncMock()
        msg.delete = AsyncMock()
        return msg

    async def test_cmd_partyvan_no_board_id(self):
        message = self.get_mock_message()
        result = await economy_extension.cmd_partyvan(message, board_id=None)
        self.assertIsNone(result)

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_partyvan_no_target(self, mock_get_reply_target):
        message = self.get_mock_message()
        mock_get_reply_target.return_value = None

        await economy_extension.cmd_partyvan(message, board_id="test_board")
        message.reply.assert_called_once_with("Нужно сделать Reply на пост того, за кем высылаем Пативэн!")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_partyvan_self_target(self, mock_get_reply_target):
        message = self.get_mock_message()
        mock_get_reply_target.return_value = 123

        await economy_extension.cmd_partyvan(message, board_id="test_board")
        message.reply.assert_called_once_with("Нельзя вызвать Пативэн на самого себя, шиз.")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_partyvan_no_access(self, mock_get_reply_target):
        message = self.get_mock_message()
        mock_get_reply_target.return_value = 456

        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
                              (123, "test_board", json.dumps({})))
        await self.db.commit()

        await economy_extension.cmd_partyvan(message, board_id="test_board")
        message.reply.assert_called_once_with("У тебя нет доступа к вызову Пативэна! Купи его в /shop.")

    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_partyvan_tinfoil_hat_blocks(self, mock_get_reply_target):
        message = self.get_mock_message()
        mock_get_reply_target.return_value = 456

        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
                              (123, "test_board", json.dumps({"partyvan_gun": True})))

        future_time = int(time.time()) + 3600
        await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
                              (456, "test_board", json.dumps({"tinfoil_hat": future_time})))
        await self.db.commit()

        await economy_extension.cmd_partyvan(message, board_id="test_board")

        message.bot.send_message.assert_any_call(123, "🚔 Твой вызов ОМОНа отменили! У жертвы была надета Шапочка из фольги, они не смогли её запеленговать.", parse_mode="HTML")
        message.bot.send_message.assert_any_call(456, f"👽 Анон <code>123</code> попытался вызвать на тебя Пативэн, но Шапочка из фольги скрыла твои координаты!", parse_mode="HTML")
        message.delete.assert_called_once()

        async with self.db.execute("SELECT active_items FROM Users WHERE user_id = 123") as cur:
            row = await cur.fetchone()
            items = json.loads(row[0])
            self.assertFalse(items.get("partyvan_gun"))

    @patch('main.apply_regular_mute', new_callable=AsyncMock)
    @patch('economy_extension.get_reply_target', new_callable=AsyncMock)
    async def test_cmd_partyvan_success(self, mock_get_reply_target, mock_apply_regular_mute):
        with patch('main.board_data', new={"test_board": {"mutes": {}}}), \
             patch('main.storage_lock', new_callable=lambda: DummyLock()):

            message = self.get_mock_message()
            mock_get_reply_target.return_value = 456

            await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
                                  (123, "test_board", json.dumps({"partyvan_gun": True})))
            await self.db.execute("INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?)",
                                  (456, "test_board", json.dumps({})))
            await self.db.commit()

            await economy_extension.cmd_partyvan(message, board_id="test_board")

            message.bot.send_message.assert_any_call(
                456,
                "🚔 <b>ВНИМАНИЕ! РАБОТАЕТ ОМОН!</b>\nЗа тобой выехал Пативэн (вызван кем-то из анонов).\nТы запакован в бобик и улетаешь в мут на 12 часов.",
                parse_mode="HTML"
            )
            message.bot.send_message.assert_any_call(
                123,
                "🚔 Пативэн успешно выслан за аноном <code>456</code>!",
                parse_mode="HTML"
            )
            message.delete.assert_called_once()

            mock_apply_regular_mute.assert_called_once_with(456, "test_board", 12 * 3600)

            async with self.db.execute("SELECT active_items FROM Users WHERE user_id = 123") as cur:
                row = await cur.fetchone()
                items = json.loads(row[0])
                self.assertFalse(items.get("partyvan_gun"))

if __name__ == "__main__":
    unittest.main()
