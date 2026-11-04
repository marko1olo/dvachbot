import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from admin_manager import process_admin_menu
from shared_state import board_data


class TestProcessAdminMenu(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        board_data.clear()

    async def asyncTearDown(self):
        board_data.clear()

    async def test_no_board_id_denied(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:lockdown"
        cb.answer = AsyncMock()

        await process_admin_menu(cb, None)
        cb.answer.assert_awaited_once_with("У вас нет прав.", show_alert=True)

    async def test_not_admin_denied(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:lockdown"
        cb.answer = AsyncMock()

        with patch("admin_manager.is_admin", return_value=False):
            await process_admin_menu(cb, "b")
        cb.answer.assert_awaited_once_with("У вас нет прав.", show_alert=True)

    async def test_lockdown_toggle_on(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:lockdown"
        cb.answer = AsyncMock()
        board_data["b"] = {"lockdown": False}

        with patch("admin_manager.is_admin", return_value=True), \
             patch("common.database.set_system_setting", new_callable=AsyncMock) as mock_set:
            await process_admin_menu(cb, "b")

            self.assertTrue(board_data["b"]["lockdown"])
            mock_set.assert_awaited_once_with("lockdown_enabled", "true")
            cb.answer.assert_awaited_once_with("Локдаун ВКЛЮЧЕН", show_alert=True)

    async def test_lockdown_toggle_off(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:lockdown"
        cb.answer = AsyncMock()
        board_data["b"] = {"lockdown": True}

        with patch("admin_manager.is_admin", return_value=True), \
             patch("common.database.set_system_setting", new_callable=AsyncMock) as mock_set:
            await process_admin_menu(cb, "b")

            self.assertFalse(board_data["b"]["lockdown"])
            mock_set.assert_awaited_once_with("lockdown_enabled", "false")
            cb.answer.assert_awaited_once_with("Локдаун ВЫКЛЮЧЕН", show_alert=True)

    async def test_lockdown_default_missing_key_toggle_on(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:lockdown"
        cb.answer = AsyncMock()
        board_data["b"] = {}

        with patch("admin_manager.is_admin", return_value=True), \
             patch("common.database.set_system_setting", new_callable=AsyncMock) as mock_set:
            await process_admin_menu(cb, "b")

            self.assertTrue(board_data["b"]["lockdown"])
            mock_set.assert_awaited_once_with("lockdown_enabled", "true")
            cb.answer.assert_awaited_once_with("Локдаун ВКЛЮЧЕН", show_alert=True)

    async def test_unknown_action_ignored(self):
        cb = MagicMock()
        cb.from_user.id = 123
        cb.data = "admin_menu:other_action"
        cb.answer = AsyncMock()
        board_data["b"] = {"lockdown": False}

        with patch("admin_manager.is_admin", return_value=True), \
             patch("common.database.set_system_setting", new_callable=AsyncMock) as mock_set:
            await process_admin_menu(cb, "b")

            self.assertFalse(board_data["b"]["lockdown"])
            mock_set.assert_not_called()
            cb.answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
