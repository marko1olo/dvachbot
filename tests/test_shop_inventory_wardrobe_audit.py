import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch

from wardrobe_engine import (
    CLOTHING_CATALOG,
    get_owned_wardrobe_items,
    get_equipped_gear,
    get_wardrobe_total_stats,
    equip_item,
    unequip_slot,
    repair_wardrobe_item,
    calculate_item_repair_cost,
    apply_armor_durability_hit,
)
from main import (
    BASE_SHOP_PRICES,
    get_current_item_price,
    _build_dressing_room_content,
    _build_inventory_content,
    resolve_shop_item,
)


class TestShopItemResolution:
    def test_russian_synonyms(self):
        assert resolve_shop_item("аптечка") == "pills"
        assert resolve_shop_item("аминазин") == "pills"
        assert resolve_shop_item("таблетки") == "pills"
        assert resolve_shop_item("заточка") == "knife"
        assert resolve_shop_item("нож") == "knife"
        assert resolve_shop_item("перцовка") == "pepperspray"
        assert resolve_shop_item("баллончик") == "pepperspray"
        assert resolve_shop_item("щит") == "shield"
        assert resolve_shop_item("зеркало") == "shield"
        assert resolve_shop_item("мутган") == "mute"
        assert resolve_shop_item("пативэн") == "partyvan"
        assert resolve_shop_item("говно") == "shit"
        assert resolve_shop_item("блевота") == "vomit"
        assert resolve_shop_item("слабительное") == "laxative"
        assert resolve_shop_item("шизотаблетка") == "schizopill"
        assert resolve_shop_item("дворник") == "janitor"
        assert resolve_shop_item("взятка") == "bribe"
        assert resolve_shop_item("фольга") == "hat_tinfoil"
        assert resolve_shop_item("корона") == "hat_crown"
        assert resolve_shop_item("ушки") == "hat_cat_ears"
        assert resolve_shop_item("шлем") == "hat_helmet"
        assert resolve_shop_item("треники") == "body_tracksuit"
        assert resolve_shop_item("кейс") == "lootbox_trash"
        assert resolve_shop_item("сейф") == "lootbox_gold"
        assert resolve_shop_item("кит") == "lootbox_whale"
        assert resolve_shop_item("огнетушитель") == "extinguisher_obep"

    def test_english_synonyms(self):
        assert resolve_shop_item("medkit") == "pills"
        assert resolve_shop_item("knife") == "knife"
        assert resolve_shop_item("pepperspray") == "pepperspray"
        assert resolve_shop_item("shield") == "shield"
        assert resolve_shop_item("mute") == "mute"
        assert resolve_shop_item("partyvan") == "partyvan"
        assert resolve_shop_item("shit") == "shit"
        assert resolve_shop_item("vomit") == "vomit"
        assert resolve_shop_item("crown") == "hat_crown"
        assert resolve_shop_item("lootbox") == "lootbox_trash"
        assert resolve_shop_item("safe") == "lootbox_gold"
        assert resolve_shop_item("whale") == "lootbox_whale"

    def test_translit_synonyms(self):
        assert resolve_shop_item("zatochka") == "knife"
        assert resolve_shop_item("percovka") == "pepperspray"
        assert resolve_shop_item("aptechka") == "pills"
        assert resolve_shop_item("shchit") == "shield"
        assert resolve_shop_item("govno") == "shit"
        assert resolve_shop_item("blevota") == "vomit"


class TestWardrobePaginationAndLimits:
    def test_dressing_room_pagination_with_many_items(self):
        """Simulates 50 owned items in wardrobe and verifies pagination prevents overflow."""
        active_items = {}
        for i, item_id in enumerate(CLOTHING_CATALOG.keys()):
            active_items[f"owned_{item_id}"] = True
            active_items[f"{item_id}_is_permanent"] = True

        # Page 1
        text_p1, kb_p1 = _build_dressing_room_content(12345, 10000, active_items, page=1, page_size=6)
        assert len(text_p1) < 1024, f"Page 1 caption length {len(text_p1)} exceeds 1024"
        assert len(kb_p1.inline_keyboard) <= 12, "Too many buttons on page 1"

        # Check navigation buttons present
        button_callbacks = [btn.callback_data for row in kb_p1.inline_keyboard for btn in row]
        assert any("wardrobe_page_2" in cb for cb in button_callbacks)

        # Page 2
        text_p2, kb_p2 = _build_dressing_room_content(12345, 10000, active_items, page=2, page_size=6)
        assert len(text_p2) < 1024
        button_callbacks_p2 = [btn.callback_data for row in kb_p2.inline_keyboard for btn in row]
        assert any("wardrobe_page_1" in cb for cb in button_callbacks_p2)

    def test_inventory_content_length_limit(self):
        """Verifies inventory formatting stays well under Telegram 4000 char limit."""
        # Create user with extensive inventory
        active_items = {
            "mute_gun": True,
            "knife_gun": True,
            "pepperspray_gun": True,
            "partyvan_gun": True,
            "shit_gun": True,
            "vomit_gun": True,
            "extinguisher_obep": True,
            "extinguisher_obep_charges": 3,
            "reflect_shield_until": int(time.time()) + 3600,
            "tinfoil_hat": int(time.time()) + 7200,
            "equipped_head": "hat_golden_crown",
            "equipped_torso": "body_sheikh_mantle",
            "equipped_face": "face_cyber_visor",
            "equipped_feet": "feet_golden_sneakers",
            "hat_golden_crown_is_permanent": True,
            "body_sheikh_mantle_is_permanent": True,
            "face_cyber_visor_is_permanent": True,
            "feet_golden_sneakers_is_permanent": True,
            "lootbox_trash": 10,
            "lootbox_gold": 5,
            "lootbox_whale": 2,
            "lockpick": 3,
            "master_key": 1,
            "chloroform": 2,
            "ksiva_polkovnik": 4,
        }
        for item_id in CLOTHING_CATALOG.keys():
            active_items[f"owned_{item_id}"] = True
            active_items[f"{item_id}_is_permanent"] = True

        from common.db_pool import get_pool
        # Mock get_pool and database calls
        with patch("main.get_pool", new_callable=AsyncMock) as mock_pool, \
             patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=500000), \
             patch("main._get_user_active_items", new_callable=AsyncMock, return_value=active_items):
            
            class AsyncContextManagerMock:
                async def __aenter__(self):
                    return mock_cur
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

            mock_db = AsyncMock()
            mock_cur = AsyncMock()
            mock_cur.fetchone = AsyncMock(return_value=("[VIP Анон]", int(time.time()) + 86400, 0))
            mock_db.execute = MagicMock(return_value=AsyncContextManagerMock())
            mock_pool.return_value = mock_db

            import asyncio
            text, kb = asyncio.run(_build_inventory_content(12345, "b"))
            assert len(text) < 3800, f"Inventory text too long: {len(text)} chars"
            assert "РЮКЗАК И ГАРДЕРОБ" in text
            assert "АКТИВНЫЕ ЭФФЕКТЫ" in text
            assert "СНАРЯЖЕНИЕ" in text
            assert "НАДЕТЫЙ ГАРДЕРОБ" in text


class TestEquipUnequipEnhancements:
    def test_unequip_by_item_id(self):
        active_items = {
            "equipped_head": "hat_crown",
            "owned_hat_crown": True,
            "hat_crown_is_permanent": True
        }
        # Unequip passing item_id directly
        ok, msg = unequip_slot(active_items, "hat_crown")
        assert ok
        assert "equipped_head" not in active_items
        assert "Корона VIP-Сыча" in msg

    def test_unequip_by_item_name(self):
        active_items = {
            "equipped_head": "hat_cat_ears",
            "owned_hat_cat_ears": True,
            "hat_cat_ears_is_permanent": True
        }
        # Unequip passing localized name
        ok, msg = unequip_slot(active_items, "Неко-Ушки")
        assert ok
        assert "equipped_head" not in active_items

    def test_equip_by_name(self):
        active_items = {
            "owned_hat_tophat": True,
            "hat_tophat_is_permanent": True
        }
        ok, msg = equip_item(active_items, "Цилиндр Джентльмена")
        assert ok
        assert active_items.get("equipped_head") == "hat_tophat"


class TestCommandExecutionAndEdgeCases:
    @pytest.mark.asyncio
    async def test_execute_shop_purchase_insufficient_funds(self):
        from main import execute_shop_purchase
        mock_db = AsyncMock()
        with patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=50):
            ok, msg, bal = await execute_shop_purchase(mock_db, 111, "b", "knife")
            assert not ok
            assert "❌" in msg or "необходимых" in msg

    @pytest.mark.asyncio
    async def test_execute_shop_purchase_non_buyable_relic(self):
        from main import execute_shop_purchase
        mock_db = AsyncMock()
        with patch("main.get_user_global_balance", new_callable=AsyncMock, return_value=1000000):
            ok, msg, bal = await execute_shop_purchase(mock_db, 111, "b", "hat_cyber_ushanka")
            assert not ok
            assert "реликвией" in msg

    @pytest.mark.asyncio
    async def test_cmd_buy_without_args(self):
        from main import cmd_buy
        mock_message = AsyncMock()
        mock_message.text = "/buy"
        mock_message.from_user.id = 111
        await cmd_buy(mock_message, "b")
        mock_message.reply.assert_called_once()
        reply_text = mock_message.reply.call_args[0][0]
        assert "БЫСТРАЯ ПОКУПКА /buy" in reply_text

    @pytest.mark.asyncio
    async def test_cmd_buy_unknown_item(self):
        from main import cmd_buy
        mock_message = AsyncMock()
        mock_message.text = "/buy unknown_gibberish_123"
        mock_message.from_user.id = 111
        await cmd_buy(mock_message, "b")
        mock_message.reply.assert_called_once()
        reply_text = mock_message.reply.call_args[0][0]
        assert "не найден в каталоге" in reply_text

    @pytest.mark.asyncio
    async def test_cmd_craft_menu(self):
        from main import cmd_craft
        mock_message = AsyncMock()
        mock_message.text = "/craft"
        mock_message.from_user.id = 111
        await cmd_craft(mock_message, "b")
        mock_message.reply.assert_called_once()
        reply_text = mock_message.reply.call_args[0][0]
        assert "МАСТЕРСКАЯ КРАФТА" in reply_text
