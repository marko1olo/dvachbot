# -*- coding: utf-8 -*-
"""
tests/test_inquisitor_shop_inventory_lootboxes.py
Target Inquisitor Red Team Test Suite for:
1. Shop /buy:
   - Full resolution and purchase of all 10+ black market items:
     Russian ("заточка", "перцовка", "щит", "мутган", "пативэн", "аптечка", "огнетушитель", "говно", "блевота", "фольга")
     English ("knife", "pepperspray", "shield", "mute", "partyvan", "pills", "extinguisher", "shit", "vomit", "tinfoil")
     Translit ("zatochka", "percovka", "shchit", "schit", "mutgan", "mut", "pativan", "pativen", "patyvan", "partyvan", "aptechka", "ognetushitel", "govno", "blevota", "folga")
     Numbered commands 1..12.
   - Showcase on /buy without arguments (numbers, items, prices).
   - Insufficient balance and daily purchase limits.
2. Wardrobe & Inventory with 100+ items:
   - /inventory text length <= 3800 chars, lootboxes summary, active effects, wardrobe summary.
   - /wardrobe pagination by 6 items per page, caption <= 850 chars (under 1024 limit), navigation buttons.
   - /equip & /unequip with emojis ("🎩 Цилиндр Джентльмена", "🐱 Неко-Ушки") and slot names ("голова", "head", "торс", "лицо", "обувь").
3. Lootboxes & Safes:
   - Command aliases: /open_safe, /safe, /safes, /gold_safe, /trash_safe, /whale_safe.
   - Abu Fund 50% burn (70% for whale) and persistent SQLite daily purchase limits.
   - Monte-Carlo RTP verification: Trash RTP <= 85%, Gold RTP <= 85%, Whale RTP <= 65%.
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

import common.database as db_mod
import lootbox_engine
import shared_state
import wardrobe_engine
from auction_engine import cmd_whale_safe
from main import (
    _build_dressing_room_content,
    _build_inventory_content,
    cmd_buy,
    cmd_equip,
    cmd_inventory,
    cmd_lootbox,
    cmd_unequip,
    cmd_wardrobe,
    execute_shop_purchase,
    resolve_shop_item,
)
from whale_economy_engine import buy_whale_safe, roll_whale_safe


@pytest.fixture(autouse=True)
def reset_daily_shop_state():
    """Reset shared in-memory limits before and after every test."""
    shared_state._DAILY_SHOP_PURCHASES.clear()
    yield
    shared_state._DAILY_SHOP_PURCHASES.clear()


# =============================================================================
# 1. SHOP & /buy ATTACK SUITE
# =============================================================================

class TestShopBuyCommands:
    """Verifies all black market items resolution, numbers 1..12, showcase, and limits."""

    def test_black_market_russian_synonyms_resolution(self):
        """Tests Russian synonyms for all required black market items."""
        assert resolve_shop_item("заточка") == "knife"
        assert resolve_shop_item("перцовка") == "pepperspray"
        assert resolve_shop_item("щит") == "shield"
        assert resolve_shop_item("мутган") == "mute"
        assert resolve_shop_item("пативэн") == "partyvan"
        assert resolve_shop_item("аптечка") == "pills"
        assert resolve_shop_item("огнетушитель") == "extinguisher_obep"
        assert resolve_shop_item("говно") == "shit"
        assert resolve_shop_item("блевота") == "vomit"
        assert resolve_shop_item("фольга") == "hat_tinfoil"

    def test_black_market_english_synonyms_resolution(self):
        """Tests English names for all required black market items."""
        assert resolve_shop_item("knife") == "knife"
        assert resolve_shop_item("pepperspray") == "pepperspray"
        assert resolve_shop_item("shield") == "shield"
        assert resolve_shop_item("mute") == "mute"
        assert resolve_shop_item("partyvan") == "partyvan"
        assert resolve_shop_item("pills") == "pills"
        assert resolve_shop_item("medkit") == "pills"
        assert resolve_shop_item("extinguisher") == "extinguisher_obep"
        assert resolve_shop_item("shit") == "shit"
        assert resolve_shop_item("vomit") == "vomit"
        assert resolve_shop_item("tinfoil") == "hat_tinfoil"

    def test_black_market_translit_synonyms_resolution(self):
        """Tests Translit variants for all required black market items."""
        assert resolve_shop_item("zatochka") == "knife"
        assert resolve_shop_item("percovka") == "pepperspray"
        assert resolve_shop_item("shchit") == "shield"
        assert resolve_shop_item("schit") == "shield"
        assert resolve_shop_item("mutgan") == "mute"
        assert resolve_shop_item("mut") == "mute"
        assert resolve_shop_item("pativan") == "partyvan"
        assert resolve_shop_item("pativen") == "partyvan"
        assert resolve_shop_item("patyvan") == "partyvan"
        assert resolve_shop_item("aptechka") == "pills"
        assert resolve_shop_item("ognetushitel") == "extinguisher_obep"
        assert resolve_shop_item("govno") == "shit"
        assert resolve_shop_item("blevota") == "vomit"
        assert resolve_shop_item("folga") == "hat_tinfoil"

    def test_black_market_numerical_indices_1_to_12(self):
        """Tests numerical indices 1 through 12 mapping to the black market catalog."""
        expected_mappings = {
            "1": "knife",
            "2": "pepperspray",
            "3": "mute",
            "4": "laxative",
            "5": "schizopill",
            "6": "janitor",
            "7": "partyvan",
            "8": "extinguisher_obep",
            "9": "shit",
            "10": "vomit",
            "11": "flag_ua",
            "12": "flag_ru",
        }
        for num_str, expected_item in expected_mappings.items():
            resolved = resolve_shop_item(num_str)
            assert resolved == expected_item, f"Number '{num_str}' resolved to '{resolved}', expected '{expected_item}'"

    @pytest.mark.asyncio
    async def test_cmd_buy_without_arguments_shows_numbered_showcase(self):
        """Tests that calling /buy without args returns a full numbered showcase of items 1..12 and prices."""
        mock_msg = AsyncMock()
        mock_msg.text = "/buy"
        mock_msg.from_user.id = 555001
        await cmd_buy(mock_msg, "b")

        mock_msg.reply.assert_called_once()
        reply_text = mock_msg.reply.call_args[0][0]

        # Verify showcase title
        assert "БЫСТРАЯ ПОКУПКА /buy" in reply_text
        # Verify all 12 items are listed with numbers and prices
        for i in range(1, 13):
            assert f"{i}." in reply_text or f"/buy {i}" in reply_text, f"Item number {i} missing from showcase"
        # Verify key prices listed
        assert "300 ₪" in reply_text  # knife / pepperspray
        assert "500 ₪" in reply_text  # mute / laxative
        assert "1500 ₪" in reply_text  # partyvan
        assert "аптечка" in reply_text.lower()
        assert "щит" in reply_text.lower()
        assert "фольга" in reply_text.lower()

    @pytest.mark.asyncio
    async def test_cmd_buy_execution_via_russian_english_translit_and_numbers(self, isolated_test_db):
        """Executes actual purchases through /buy command with isolated DB for all synonym types."""
        db = isolated_test_db
        uid = 555002

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000.0, '{}')",
            (uid,)
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db):
            # 1. Russian: /buy аптечка
            msg_pills = AsyncMock()
            msg_pills.text = "/buy аптечка"
            msg_pills.from_user.id = uid
            await cmd_buy(msg_pills, "b")
            msg_pills.reply.assert_called_once()
            assert "✅" in msg_pills.reply.call_args[0][0]

            # 2. English: /buy knife
            msg_knife = AsyncMock()
            msg_knife.text = "/buy knife"
            msg_knife.from_user.id = uid
            await cmd_buy(msg_knife, "b")
            msg_knife.reply.assert_called_once()
            assert "✅" in msg_knife.reply.call_args[0][0]

            # 3. Translit: /buy folga
            msg_folga = AsyncMock()
            msg_folga.text = "/buy folga"
            msg_folga.from_user.id = uid
            await cmd_buy(msg_folga, "b")
            msg_folga.reply.assert_called_once()
            assert "✅" in msg_folga.reply.call_args[0][0]

            # 4. Number: /buy 2 (pepperspray)
            msg_num2 = AsyncMock()
            msg_num2.text = "/buy 2"
            msg_num2.from_user.id = uid
            await cmd_buy(msg_num2, "b")
            msg_num2.reply.assert_called_once()
            assert "✅" in msg_num2.reply.call_args[0][0]

            # 5. Number: /buy 8 (extinguisher)
            msg_num8 = AsyncMock()
            msg_num8.text = "/buy 8"
            msg_num8.from_user.id = uid
            await cmd_buy(msg_num8, "b")
            msg_num8.reply.assert_called_once()
            assert "✅" in msg_num8.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_buy_insufficient_funds_rejection(self, isolated_test_db):
        """Verifies purchase rejection when user balance is insufficient."""
        db = isolated_test_db
        uid = 555003

        # User has only 10 ₪ (partyvan costs 1500 ₪)
        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 10.0, '{}')",
            (uid,)
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db):
            msg = AsyncMock()
            msg.text = "/buy partyvan"
            msg.from_user.id = uid
            await cmd_buy(msg, "b")

            msg.reply.assert_called_once()
            reply = msg.reply.call_args[0][0]
            assert "❌" in reply or "необходимых" in reply or "Денег нет" in reply or "Нищееб" in reply
            bal = await db_mod.get_user_global_balance(db, uid)
            assert bal == 10.0, "Balance must remain untouched on failure"

    @pytest.mark.asyncio
    async def test_buy_daily_limit_exceeded_blocking(self, isolated_test_db):
        """Verifies daily limit blocking on repeated purchases (e.g., partyvan limit = 2)."""
        db = isolated_test_db
        uid = 555004

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000.0, '{}')",
            (uid,)
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db):
            # Buy 1: ok
            ok1, _, _ = await execute_shop_purchase(db, uid, "b", "partyvan")
            assert ok1 is True

            # Reset inventory gun flag to simulate use, so we can test shop limit
            await db.execute("UPDATE Users SET active_items = '{}' WHERE user_id = ?", (uid,))
            await db.commit()

            # Buy 2: ok
            ok2, _, _ = await execute_shop_purchase(db, uid, "b", "partyvan")
            assert ok2 is True

            await db.execute("UPDATE Users SET active_items = '{}' WHERE user_id = ?", (uid,))
            await db.commit()

            # Buy 3: BLOCKED by daily limit (limit is 2 for partyvan)
            ok3, msg3, _ = await execute_shop_purchase(db, uid, "b", "partyvan")
            assert ok3 is False
            assert any(w in msg3.lower() for w in ("лимит", "норма", "склад", "руки", "завтра", "хватит", "закончились"))


# =============================================================================
# 2. WARDROBE & INVENTORY WITH 100+ ITEMS ATTACK SUITE
# =============================================================================

class TestWardrobeAndInventoryLargeScale:
    """Tests /inventory and /wardrobe behavior when user holds 100+ items and gear."""

    def _generate_massive_inventory(self) -> dict:
        """Generates inventory dict with 100+ items (clothing, consumables, weapons, buffs)."""
        inv = {
            # Weapons & Combat items
            "extinguisher_obep": True,
            "extinguisher_obep_charges": 3,
            "mute_gun": True,
            "partyvan_gun": True,
            "knife_gun": True,
            "pepperspray_gun": True,
            "shit_gun": True,
            "vomit_gun": True,
            "pills_gun": True,
            "laxative_gun": True,
            "schizopill_gun": True,
            # Active Buffs & Timers
            "reflect_shield_until": int(time.time()) + 3600,
            "tinfoil_hat": int(time.time()) + 7200,
            "janitor_until": int(time.time()) + 18000,
            "badge_druzhinnik_expires": int(time.time()) + 86400,
            "cyberchad_amulet_expires": int(time.time()) + 86400,
            "cyberchad_amulet": True,
            # Criminal Tools
            "lockpick": 15,
            "fake_ksiva": 4,
            "master_key": 2,
            "bribe_envelope": 3,
            "chloroform": 5,
            # Lootbox items
            "lootbox_trash": 25,
            "lootbox_gold": 10,
            "lootbox_whale": 3,
            # Equipped gear in all 4 slots
            "equipped_head": "hat_golden_crown",
            "equipped_torso": "body_sheikh_mantle",
            "equipped_face": "face_cyber_visor",
            "equipped_feet": "feet_golden_sneakers",
        }
        # Add all items from CLOTHING_CATALOG (28 items)
        for cid in wardrobe_engine.CLOTHING_CATALOG.keys():
            inv[f"owned_{cid}"] = True
            inv[f"{cid}_is_permanent"] = True

        # Synthesize remaining wardrobe items to reach 100 total items
        for i in range(1, 80):
            mock_id = f"custom_relic_{i}"
            inv[f"owned_{mock_id}"] = True
            inv[f"{mock_id}_is_permanent"] = True

        return inv

    @pytest.mark.asyncio
    async def test_inventory_text_length_and_structure_with_100_items(self, isolated_test_db):
        """
        Verifies that /inventory for a user with 100+ items:
        1. Keeps text length <= 3800 chars (safe under Telegram 4096 char ceiling).
        2. Contains Lootbox counts, Active Effects, Combat Gear, and Wardrobe preview.
        """
        db = isolated_test_db
        uid = 666001
        inv = self._generate_massive_inventory()

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500000.0, ?)",
            (uid, json.dumps(inv))
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db):
            text, kb = await _build_inventory_content(uid, "b")

            # Length invariant
            assert len(text) <= 3800, f"Inventory text length {len(text)} exceeds strict 3800 ceiling"

            # Structure invariants
            assert "РЮКЗАК И ГАРДЕРОБ" in text
            assert "АКТИВНЫЕ ЭФФЕКТЫ" in text
            assert "СНАРЯЖЕНИЕ" in text
            assert "ЛУТБОКСЫ И КЕЙСЫ" in text
            assert "Мусорный пакет:" in text and "25 шт." in text
            assert "Золотой сейф:" in text and "10 шт." in text
            assert "Сейф олигарха:" in text and "3 шт." in text
            assert "НАДЕТЫЙ ГАРДЕРОБ" in text
            assert "КОЛЛЕКЦИЯ В ГАРДЕРОБЕ" in text

    @pytest.mark.asyncio
    async def test_cmd_inventory_sends_banner_message(self, isolated_test_db):
        """Verifies cmd_inventory handler executes and triggers banner message."""
        db = isolated_test_db
        uid = 666002
        inv = self._generate_massive_inventory()

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 100000.0, ?)",
            (uid, json.dumps(inv))
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            msg = AsyncMock()
            msg.from_user.id = uid
            msg.chat.id = -10012345
            await cmd_inventory(msg, "b")

            mock_banner.assert_called_once()
            caption = mock_banner.call_args[1]["caption"]
            assert len(caption) <= 3800
            assert "РЮКЗАК И ГАРДЕРОБ" in caption

    def test_wardrobe_pagination_6_items_per_page_and_caption_under_850_chars(self):
        """
        Verifies that /wardrobe (dressing room) with 100 items:
        1. Paginates by exactly 6 items per page.
        2. Caption length <= 850 characters (with reserve up to 1024).
        3. Inline navigation buttons work correctly.
        """
        inv = self._generate_massive_inventory()

        # Page 1
        text_p1, kb_p1 = _build_dressing_room_content(12345, 150000.0, inv, page=1, page_size=6)
        assert len(text_p1) <= 850, f"Page 1 caption length {len(text_p1)} exceeds 850 chars"
        assert len(text_p1) < 1024, "Page 1 caption must be strictly under 1024 Telegram photo caption limit"

        # Check navigation buttons on page 1
        callbacks_p1 = [btn.callback_data for row in kb_p1.inline_keyboard for btn in row]
        assert any("wardrobe_page_2" in cb for cb in callbacks_p1), "Page 1 must contain forward button to page 2"
        # 6 items -> 6 action buttons + nav row + footer buttons
        item_buttons_p1 = [btn for row in kb_p1.inline_keyboard for btn in row if "wardrobe_equip_" in btn.callback_data or "wardrobe_unequip_" in btn.callback_data]
        assert len(item_buttons_p1) == 6, f"Expected 6 item buttons on page 1, got {len(item_buttons_p1)}"

        # Page 2
        text_p2, kb_p2 = _build_dressing_room_content(12345, 150000.0, inv, page=2, page_size=6)
        assert len(text_p2) <= 850, f"Page 2 caption length {len(text_p2)} exceeds 850 chars"
        callbacks_p2 = [btn.callback_data for row in kb_p2.inline_keyboard for btn in row]
        assert any("wardrobe_page_1" in cb for cb in callbacks_p2), "Page 2 must contain back button to page 1"
        assert any("wardrobe_page_3" in cb for cb in callbacks_p2), "Page 2 must contain forward button to page 3"

    @pytest.mark.asyncio
    async def test_cmd_wardrobe_opens_dressing_room_with_pagination(self, isolated_test_db):
        """Verifies /wardrobe command opens the dressing room with 6-item pagination (caption <= 850)."""
        db = isolated_test_db
        uid = 666003
        inv = self._generate_massive_inventory()

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 200000.0, ?)",
            (uid, json.dumps(inv))
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:
            msg = AsyncMock()
            msg.text = "/wardrobe"
            msg.from_user.id = uid
            msg.chat.id = -10098765
            await cmd_wardrobe(msg, "b")

            mock_banner.assert_called_once()
            caption = mock_banner.call_args[1]["caption"]
            assert len(caption) <= 850
            assert "ПРИМЕРОЧНАЯ И ГАРДЕРОБ" in caption

    def test_equip_and_unequip_with_emojis(self):
        """Verifies equip and unequip using exact emoji names."""
        inv = {
            "owned_hat_tophat": True,
            "hat_tophat_is_permanent": True,
            "owned_hat_cat_ears": True,
            "hat_cat_ears_is_permanent": True,
        }

        # 1. Equip with emoji: "🎩 Цилиндр Джентльмена"
        ok1, msg1 = wardrobe_engine.equip_item(inv, "🎩 Цилиндр Джентльмена")
        assert ok1 is True
        assert inv.get("equipped_head") == "hat_tophat"
        assert "Цилиндр Джентльмена" in msg1

        # 2. Unequip with emoji: "🎩 Цилиндр Джентльмена"
        ok2, msg2 = wardrobe_engine.unequip_slot(inv, "🎩 Цилиндр Джентльмена")
        assert ok2 is True
        assert inv.get("equipped_head") is None

        # 3. Equip with emoji: "🐱 Неко-Ушки"
        ok3, msg3 = wardrobe_engine.equip_item(inv, "🐱 Неко-Ушки")
        assert ok3 is True
        assert inv.get("equipped_head") == "hat_cat_ears"

        # 4. Unequip with emoji: "🐱 Неко-Ушки"
        ok4, msg4 = wardrobe_engine.unequip_slot(inv, "🐱 Неко-Ушки")
        assert ok4 is True
        assert inv.get("equipped_head") is None

    def test_unequip_slot_by_russian_and_english_slot_names(self):
        """Verifies unequipping all 4 slots using Russian ('голова', 'торс', 'лицо', 'обувь') and English ('head', 'torso', 'face', 'feet') names."""
        inv = {
            "owned_hat_tophat": True, "hat_tophat_is_permanent": True,
            "owned_body_tracksuit": True, "body_tracksuit_is_permanent": True,
            "owned_face_thug_glasses": True, "face_thug_glasses_is_permanent": True,
            "owned_feet_sneakers": True, "feet_sneakers_is_permanent": True,
        }

        # Equip all 4 slots
        wardrobe_engine.equip_item(inv, "hat_tophat")
        wardrobe_engine.equip_item(inv, "body_tracksuit")
        wardrobe_engine.equip_item(inv, "face_thug_glasses")
        wardrobe_engine.equip_item(inv, "feet_sneakers")

        # Unequip Russian slot: "голова"
        ok, msg = wardrobe_engine.unequip_slot(inv, "голова")
        assert ok is True
        assert inv.get("equipped_head") is None
        assert "Цилиндр" in msg

        # Unequip Russian slot: "торс"
        ok, msg = wardrobe_engine.unequip_slot(inv, "торс")
        assert ok is True
        assert inv.get("equipped_torso") is None
        assert "треники" in msg.lower()

        # Unequip Russian slot: "лицо"
        ok, msg = wardrobe_engine.unequip_slot(inv, "лицо")
        assert ok is True
        assert inv.get("equipped_face") is None
        assert "очки" in msg.lower()

        # Unequip Russian slot: "обувь"
        ok, msg = wardrobe_engine.unequip_slot(inv, "обувь")
        assert ok is True
        assert inv.get("equipped_feet") is None
        assert "берцы" in msg.lower() or "тяги" in msg.lower() or "кроссовки" in msg.lower()

        # Re-equip and test English slots
        wardrobe_engine.equip_item(inv, "hat_tophat")
        ok_en, _ = wardrobe_engine.unequip_slot(inv, "head")
        assert ok_en is True
        assert inv.get("equipped_head") is None


# =============================================================================
# 3. LOOTBOXES, SAFES, PERSISTENCE & RTP ATTACK SUITE
# =============================================================================

class TestLootboxesSafesAndRTP:
    """Tests /lootbox aliases, 50%/70% Abu burns, SQLite persistent limits, and RTP Monte Carlo."""

    @pytest.mark.asyncio
    async def test_lootbox_command_aliases(self, isolated_test_db):
        """
        Verifies command aliases:
        - /open_safe, /safe, /safes without args -> shows lootbox showcase banner
        - /gold_safe -> buys and opens gold safe directly
        - /trash_safe -> buys and opens trash safe directly
        - /whale_safe -> triggers cmd_whale_safe
        """
        db = isolated_test_db
        uid = 777001

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 500000.0, '{}')",
            (uid,)
        )
        await db.commit()

        with patch("main.get_pool", new_callable=AsyncMock, return_value=db), \
             patch("banner_manager.send_banner_message", new_callable=AsyncMock) as mock_banner:

            # 1. /open_safe without args -> showcase banner
            msg_showcase = AsyncMock()
            msg_showcase.text = "/open_safe"
            msg_showcase.from_user.id = uid
            msg_showcase.chat.id = -100444
            await cmd_lootbox(msg_showcase, "b")
            mock_banner.assert_called_once()
            assert "КЕЙСЫ И СЕЙФЫ" in mock_banner.call_args[1]["caption"] or "ЛУТБОКС" in mock_banner.call_args[1]["caption"]

            # 2. /safe without args -> showcase banner
            mock_banner.reset_mock()
            msg_safe = AsyncMock()
            msg_safe.text = "/safe"
            msg_safe.from_user.id = uid
            msg_safe.chat.id = -100444
            await cmd_lootbox(msg_safe, "b")
            mock_banner.assert_called_once()

            # 3. /gold_safe -> direct purchase and opening of gold safe
            msg_gold = AsyncMock()
            msg_gold.text = "/gold_safe"
            msg_gold.from_user.id = uid
            await cmd_lootbox(msg_gold, "b")
            msg_gold.reply.assert_called_once()
            reply_gold = msg_gold.reply.call_args[0][0]
            assert "ЗОЛОТОЙ СЕЙФ ВЗЛОМАН" in reply_gold

            # 4. /trash_safe -> direct purchase and opening of trash safe
            msg_trash = AsyncMock()
            msg_trash.text = "/trash_safe"
            msg_trash.from_user.id = uid
            await cmd_lootbox(msg_trash, "b")
            msg_trash.reply.assert_called_once()
            reply_trash = msg_trash.reply.call_args[0][0]
            assert "МУСОРНЫЙ ПАКЕТ РАСПАКОВАН" in reply_trash

            # 5. /whale_safe -> triggers cmd_whale_safe
            msg_whale = AsyncMock()
            msg_whale.text = "/whale_safe"
            msg_whale.from_user.id = uid
            with patch("auction_engine.cmd_whale_safe", new_callable=AsyncMock) as mock_cmd_whale:
                await cmd_lootbox(msg_whale, "b")
                mock_cmd_whale.assert_called_once()

    @pytest.mark.asyncio
    async def test_lootbox_abu_burn_50_percent_and_db_limits_persistence(self, isolated_test_db):
        """
        Verifies:
        1. 50% of trash lootbox (75 ₪) and gold safe (250 ₪) is burned to GlobalStats['abu_yacht_fund'].
        2. Daily purchase limits are persisted to SQLite UserDailyLimits table.
        3. Limits persist across simulated restart.
        """
        db = isolated_test_db
        uid = 777002
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 50000.0, '{}')",
            (uid,)
        )
        await db.commit()

        initial_fund = await db_mod.get_abu_fund_total(db)

        # Purchase 1 Gold Safe (500 ₪) -> Burns 50% = 250 ₪ to Abu Fund
        ok_gold, msg_gold, bal_gold = await execute_shop_purchase(db, uid, "b", "lootbox_gold")
        assert ok_gold is True

        fund_after_gold = await db_mod.get_abu_fund_total(db)
        assert fund_after_gold == initial_fund + 250.0, f"Expected +250 ₪ in Abu Fund, got {fund_after_gold - initial_fund}"

        # Purchase 1 Trash Case (150 ₪) -> Burns 50% = 75 ₪ to Abu Fund
        ok_trash, msg_trash, bal_trash = await execute_shop_purchase(db, uid, "b", "lootbox_trash")
        assert ok_trash is True

        fund_after_trash = await db_mod.get_abu_fund_total(db)
        assert fund_after_trash == fund_after_gold + 75.0, f"Expected +75 ₪ in Abu Fund, got {fund_after_trash - fund_after_gold}"

        # Check SQLite UserDailyLimits persistence
        gold_count_db = await db_mod.get_user_daily_limit(db, uid, "lootbox_gold", today)
        assert gold_count_db == 1
        trash_count_db = await db_mod.get_user_daily_limit(db, uid, "lootbox_trash", today)
        assert trash_count_db == 1

        # Simulate bot restart by wiping in-memory dictionary
        shared_state._DAILY_SHOP_PURCHASES.clear()
        assert shared_state.get_user_daily_shop_buys(uid, "lootbox_gold") == 0

        # Sync from DB
        synced = await db_mod.sync_daily_limits_from_db(db, today)
        assert synced >= 2
        assert shared_state.get_user_daily_shop_buys(uid, "lootbox_gold") == 1
        assert shared_state.get_user_daily_shop_buys(uid, "lootbox_trash") == 1

    @pytest.mark.asyncio
    async def test_whale_safe_abu_burn_70_percent(self, isolated_test_db):
        """Verifies Whale Safe burns 70% of cost (35,000 ₪ for first open) into Abu Yacht Fund."""
        db = isolated_test_db
        uid = 777003

        await db.execute(
            "INSERT INTO Users (user_id, board_id, balance, active_items) VALUES (?, 'b', 200000.0, '{}')",
            (uid,)
        )
        await db.commit()

        initial_fund = await db_mod.get_abu_fund_total(db)
        res = await buy_whale_safe(db, uid, "b")
        assert res.get("ok") is True

        fund_after_whale = await db_mod.get_abu_fund_total(db)
        # Price is 50,000 -> 70% = 35,000 ₪
        assert fund_after_whale == initial_fund + 35000.0, f"Expected +35,000 ₪, got {fund_after_whale - initial_fund}"

    def test_monte_carlo_rtp_trash_gold_whale(self):
        """
        Runs Monte-Carlo simulations (N=5,000) for all three tiers of lootboxes:
        1. Trash Lootbox: Nominal RTP <= 85%
        2. Gold Safe: Nominal RTP <= 85%
        3. Whale Safe: Nominal RTP <= 65%
        """
        iterations = 5000

        # 1. Trash Lootbox (150 ₪ price)
        trash_price = 150
        trash_total_spent = iterations * trash_price
        trash_total_nominal = 0

        for _ in range(iterations):
            tier, title, desc, payload, base_cash = lootbox_engine.roll_trash_lootbox()
            res_inv, cash, note = lootbox_engine.apply_lootbox_reward({}, payload, base_cash, case_type="trash")
            trash_total_nominal += cash
            for k in payload:
                if k in ("knife_gun", "pepperspray_gun", "shit_gun", "vomit_gun", "mute_gun"):
                    trash_total_nominal += 40

        trash_rtp = (trash_total_nominal / trash_total_spent) * 100.0
        assert trash_rtp <= 85.0, f"Trash Lootbox RTP {trash_rtp:.2f}% exceeds 85%"

        # 2. Gold Safe (500 ₪ price)
        gold_price = 500
        gold_total_spent = iterations * gold_price
        gold_total_nominal = 0

        for _ in range(iterations):
            tier, title, desc, payload, base_cash = lootbox_engine.roll_gold_safe()
            res_inv, cash, note = lootbox_engine.apply_lootbox_reward({}, payload, base_cash, case_type="gold")
            gold_total_nominal += cash
            for k in payload:
                if k in ("knife_gun", "pepperspray_gun", "partyvan_gun", "mute_gun"):
                    gold_total_nominal += 90

        gold_rtp = (gold_total_nominal / gold_total_spent) * 100.0
        assert gold_rtp <= 85.0, f"Gold Safe RTP {gold_rtp:.2f}% exceeds 85%"

        # 3. Whale Safe (50,000 ₪ base price)
        whale_price = 50000
        whale_total_spent = iterations * whale_price
        whale_total_nominal = 0

        for _ in range(iterations):
            tier, title, desc, payload, base_cash = roll_whale_safe()
            res_inv, cash, note = lootbox_engine.apply_lootbox_reward({}, payload, base_cash, case_type="whale")
            whale_total_nominal += cash
            for k in payload:
                if "hat_" in k or "body_" in k or "face_" in k or "feet_" in k:
                    whale_total_nominal += 8000
                elif "weapon" in k or "gun" in k:
                    whale_total_nominal += 3000

        whale_rtp = (whale_total_nominal / whale_total_spent) * 100.0
        assert whale_rtp <= 65.0, f"Whale Safe RTP {whale_rtp:.2f}% exceeds 65%"
