import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import time

os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.test_main import mocked_deps, mock_module
for dep in mocked_deps:
    if dep not in sys.modules:
        mock_module(dep)

# Fix MagicMock to avoid StopIteration during mock unpacks
def infinite_iter(self):
    while True:
        yield MagicMock()
import unittest.mock
unittest.mock.MagicMock.__iter__ = infinite_iter

for mod_name in sys.modules:
    if mod_name.startswith('site_tgach.') or mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

sys.modules['async_lru'].alru_cache = lambda *args, **kwargs: (lambda func: func)
sys.modules['aiogram.fsm.state'].StatesGroup = type('MockStatesGroup', (), {})
sys.modules['aiogram.fsm.state'].State = lambda *args, **kwargs: MagicMock()
sys.modules['aiogram'].BaseMiddleware = type('MockBaseMiddleware', (), {'__call__': AsyncMock()})

# Provide a robust mock for aiogram Routers/Dispatcher so decorators just return the function
class MockRouter:
    def __getattr__(self, name):
        if name in ('middleware', 'register'):
            return MagicMock()

        def _decorator(*args, **kwargs):
            def _wrapper(func):
                return func
            return _wrapper
        return _decorator

    def __call__(self, *args, **kwargs):
        def _wrapper(func):
            return func
        return _wrapper

class MockDP:
    def __getattr__(self, name):
        return MockRouter()

sys.modules['aiogram'].Dispatcher = MagicMock(return_value=MockDP())
sys.modules['aiogram'].Router = MagicMock(return_value=MockRouter())

from main import cb_shop_buy

class TestCBShopBuy(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patcher_pool = patch('common.db_pool.get_pool', new_callable=AsyncMock)
        self.patcher_lock = patch('common.db_pool.db_lock', AsyncMock())

        self.mock_get_pool = self.patcher_pool.start()
        self.mock_db_lock = self.patcher_lock.start()

        self.mock_db = MagicMock()
        self.mock_cursor = AsyncMock()

        # db.execute returns a context manager that must be async
        class AsyncContextManagerMock:
            def __init__(self, cursor_mock):
                self.cursor_mock = cursor_mock

            async def __aenter__(self):
                return self.cursor_mock

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            def __await__(self):
                async def _mock_awaitable():
                    return self.cursor_mock
                return _mock_awaitable().__await__()

        self.mock_execute = MagicMock(return_value=AsyncContextManagerMock(self.mock_cursor))
        self.mock_db.execute = self.mock_execute

        self.mock_db.commit = AsyncMock()
        self.mock_get_pool.return_value = self.mock_db

        self.mock_cb = MagicMock()
        self.mock_cb.from_user.id = 123
        self.mock_cb.answer = AsyncMock()
        self.mock_cb.message.html_text = "Balance: 1000.00"
        self.mock_cb.message.reply_markup = MagicMock()
        self.mock_cb.message.edit_text = AsyncMock()

    async def asyncTearDown(self):
        self.patcher_pool.stop()
        self.patcher_lock.stop()

    async def test_no_board_id(self):
        await cb_shop_buy(self.mock_cb, None)
        self.mock_get_pool.assert_not_called()

    async def test_not_enough_balance(self):
        self.mock_cb.data = "shop_buy_janitor"
        self.mock_cursor.fetchone.return_value = (500, "{}")

        await cb_shop_buy(self.mock_cb, "test_board")

        self.mock_cb.answer.assert_called_once_with(
            "❌ Не хватает бабок! Нужно 700 RUB, у тебя 500 RUB.",
            show_alert=True
        )
        self.mock_db.commit.assert_not_called()

    async def test_buy_janitor(self):
        self.mock_cb.data = "shop_buy_janitor"
        self.mock_cursor.fetchone.return_value = (1000, "{}")

        current_time = int(time.time())
        with patch('time.time', return_value=current_time):
            await cb_shop_buy(self.mock_cb, "test_board")

        self.mock_db.commit.assert_called_once()

        update_calls = [call for call in self.mock_execute.call_args_list if "UPDATE Users SET balance = balance - ?" in call[0][0]]
        self.assertEqual(len(update_calls), 1)

        args = update_calls[0][0][1]
        self.assertEqual(args[0], 700)
        active_items = json.loads(args[1])
        self.assertEqual(active_items["janitor_until"], current_time + 6 * 3600)
        self.assertEqual(active_items["janitor_deletes_left"], 10)
        self.assertEqual(args[2], 123)
        self.assertEqual(args[3], "test_board")

        self.assertTrue(self.mock_cb.answer.call_args[0][0].startswith("🧹 Ты купил Билет Дворника"))

    async def test_buy_mute_gun(self):
        self.mock_cb.data = "shop_buy_mute"
        self.mock_cursor.fetchone.return_value = (1000, "{}")

        await cb_shop_buy(self.mock_cb, "test_board")

        update_calls = [call for call in self.mock_execute.call_args_list if "UPDATE Users SET balance = balance - ?" in call[0][0]]
        args = update_calls[0][0][1]
        active_items = json.loads(args[1])
        self.assertTrue(active_items["mute_gun"])

        self.assertTrue(self.mock_cb.answer.call_args[0][0].startswith("🔫 Ты купил Мут-Ган"))

    async def test_buy_mute_gun_already_owned(self):
        self.mock_cb.data = "shop_buy_mute"
        self.mock_cursor.fetchone.return_value = (1000, json.dumps({"mute_gun": True}))

        await cb_shop_buy(self.mock_cb, "test_board")

        self.mock_cb.answer.assert_called_once_with(
            "У тебя уже есть Мут-Ган! Сделай Reply на пост с командой /shoot", show_alert=True
        )
        self.mock_db.commit.assert_not_called()

    async def test_buy_shield(self):
        self.mock_cb.data = "shop_buy_shield"
        self.mock_cursor.fetchone.return_value = (1000, "{}")

        current_time = int(time.time())
        with patch('time.time', return_value=current_time):
            await cb_shop_buy(self.mock_cb, "test_board")

        update_calls = [call for call in self.mock_execute.call_args_list if "UPDATE Users SET balance = balance - ?" in call[0][0]]
        args = update_calls[0][0][1]
        active_items = json.loads(args[1])
        self.assertEqual(active_items["reflect_shield_until"], current_time + 24 * 3600)

        self.assertTrue(self.mock_cb.answer.call_args[0][0].startswith("🛡️ Ты купил Зеркальный Щит"))

    async def test_buy_prefix(self):
        self.mock_cb.data = "shop_buy_prefix"
        self.mock_cursor.fetchone.return_value = (1000, "{}")

        with patch('random.random', return_value=0.5), \
             patch('random.choice', return_value="[TestPrefix]"):
            await cb_shop_buy(self.mock_cb, "test_board")

        prefix_update_calls = [call for call in self.mock_execute.call_args_list if "UPDATE Users SET custom_prefix = ?" in call[0][0]]
        self.assertEqual(len(prefix_update_calls), 1)
        args = prefix_update_calls[0][0][1]
        self.assertEqual(args[0], "[TestPrefix]")
        self.assertEqual(args[2], 123)

        update_calls = [call for call in self.mock_execute.call_args_list if "UPDATE Users SET balance = balance - ?" in call[0][0]]
        args = update_calls[0][0][1]
        self.assertEqual(args[0], 300)

        self.assertTrue(self.mock_cb.answer.call_args[0][0].startswith("👑 Рулетка крутится"))

if __name__ == "__main__":
    unittest.main()
