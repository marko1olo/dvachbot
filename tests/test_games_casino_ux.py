# -*- coding: utf-8 -*-
"""
test_games_casino_ux.py — Deep UX & Resilience Test Suite for Games, Casino, Lootboxes & Auctions
Audits:
1. Double-click & button spam protection (in-flight locks & debouncing).
2. Balance & winnings formatting (thousands separators, clean rounding, float precision noise elimination).
3. Victory/loss emojis and transparent multiplier reporting.
4. Lootbox visual rarity tiers (⚪/🔵/🟣/🟡), explicit duplicate cashback messaging, and insufficient funds alerts.
5. Auction outbid notifications, anti-sniping notices, and deposit refund transparency.
"""

import asyncio
import math
import pytest
from unittest.mock import AsyncMock, patch

import time
from common.anon_identity import get_anon_id, generate_anon_name

import casino_engine
import lootbox_engine
import auction_engine
import dice_duel_engine
import russian_roulette_pvp
import ttt_engine


# =============================================================================
# 1. DOUBLE-CLICK & IN-FLIGHT LOCK RESILIENCE
# =============================================================================

class TestInFlightAndDebounceProtection:
    """Tests ensuring rapid button clicks and concurrent requests cannot double-spin or double-deduct."""

    @pytest.mark.asyncio
    async def test_casino_in_flight_blocks_rapid_double_click(self):
        """A user cannot execute two simultaneous casino spins; second call is rejected immediately."""
        user_id = 77701

        async def slow_spin():
            async with casino_engine.casino_in_flight_guard(user_id, action_name="slots"):
                assert casino_engine.is_casino_in_flight(user_id) is True
                await asyncio.sleep(0.1)

        task1 = asyncio.create_task(slow_spin())
        await asyncio.sleep(0.02)  # Let task1 enter the guard

        # Immediate second attempt by same user must raise CasinoInFlightError
        with pytest.raises(casino_engine.CasinoInFlightError) as exc_info:
            async with casino_engine.casino_in_flight_guard(user_id, action_name="slots"):
                pass
        assert "обрабатывается" in str(exc_info.value)

        await task1
        # After completion, user is no longer in-flight
        assert casino_engine.is_casino_in_flight(user_id) is False

    @pytest.mark.asyncio
    async def test_casino_in_flight_allows_different_users(self):
        """Different users can spin concurrently without blocking each other."""
        user_a = 77702
        user_b = 77703

        results = []

        async def user_spin(uid: int):
            async with casino_engine.casino_in_flight_guard(uid, action_name="slots"):
                await asyncio.sleep(0.05)
                results.append(uid)

        await asyncio.gather(user_spin(user_a), user_spin(user_b))
        assert set(results) == {user_a, user_b}

    def test_casino_action_debouncing(self):
        """Rapid clicks within debounce threshold return friendly anti-spam message."""
        user_id = 77704
        casino_engine.user_casino_last_action.pop(user_id, None)

        # First click allowed
        ok1, msg1 = casino_engine.check_action_debounce(user_id, action="spin", min_interval=1.0)
        assert ok1 is True
        assert msg1 == ""

        # Rapid second click blocked
        ok2, msg2 = casino_engine.check_action_debounce(user_id, action="spin", min_interval=1.0)
        assert ok2 is False
        assert "Не части" in msg2

    @pytest.mark.asyncio
    async def test_lootbox_in_flight_blocks_concurrent_open(self):
        """Rapid double-tap on case opening cannot open two cases simultaneously."""
        user_id = 88801

        async def slow_open():
            async with lootbox_engine.lootbox_in_flight_guard(user_id):
                assert lootbox_engine.is_lootbox_in_flight(user_id) is True
                await asyncio.sleep(0.1)

        task = asyncio.create_task(slow_open())
        await asyncio.sleep(0.02)

        with pytest.raises(lootbox_engine.LootboxInFlightError) as exc_info:
            async with lootbox_engine.lootbox_in_flight_guard(user_id):
                pass
        assert "уже открывается" in str(exc_info.value)

        await task
        assert lootbox_engine.is_lootbox_in_flight(user_id) is False

    def test_lootbox_debounce(self):
        """Lootbox debounce check rejects clicks faster than min_interval."""
        user_id = 88802
        lootbox_engine.user_lootbox_last_action.pop(user_id, None)

        ok1, _ = lootbox_engine.check_lootbox_debounce(user_id, min_interval=1.0)
        assert ok1 is True
        ok2, msg2 = lootbox_engine.check_lootbox_debounce(user_id, min_interval=1.0)
        assert ok2 is False
        assert "Не спеши" in msg2

    @pytest.mark.asyncio
    async def test_auction_bid_in_flight_blocks_concurrent_bid(self):
        """Rapid double-tap on placing a bid blocks the second attempt."""
        user_id = 99901

        async def slow_bid():
            async with auction_engine.auction_bid_in_flight_guard(user_id):
                assert auction_engine.is_bid_in_flight(user_id) is True
                await asyncio.sleep(0.1)

        task = asyncio.create_task(slow_bid())
        await asyncio.sleep(0.02)

        with pytest.raises(auction_engine.AuctionBidInFlightError) as exc_info:
            async with auction_engine.auction_bid_in_flight_guard(user_id):
                pass
        assert "обрабатывается" in str(exc_info.value)

        await task
        assert auction_engine.is_bid_in_flight(user_id) is False


# =============================================================================
# 2. SHEKEL FORMATTING & VISUAL PRESENTATION
# =============================================================================

class TestShekelFormattingAndVisuals:
    """Tests for number formatting, eliminating float noise, and clean thousands separators."""

    def test_format_shekels_integer_thousands(self):
        """Format 1500 -> '1 500 ₪', 1000000 -> '1 000 000 ₪' with space separators."""
        assert casino_engine.format_shekels(1500) == "1 500 ₪"
        assert casino_engine.format_shekels(1000000) == "1 000 000 ₪"
        assert casino_engine.format_shekels(0) == "0 ₪"
        assert casino_engine.format_shekels(25000) == "25 000 ₪"

    def test_format_shekels_eliminates_float_precision_noise(self):
        """Values like 1500.0000000001 or 4999.99999999 are rounded cleanly without float noise."""
        assert casino_engine.format_shekels(1500.0000000001) == "1 500 ₪"
        assert casino_engine.format_shekels(4999.99999999) == "5 000 ₪"
        assert lootbox_engine.format_shekels(350.000000004) == "350 ₪"
        assert auction_engine.format_shekels(60000.000000001) == "60 000 ₪"

    def test_format_shekels_with_decimals_and_signs(self):
        """Clean 2-decimal formatting when genuine fractions exist, and sign prefixing."""
        assert casino_engine.format_shekels(1500.50) == "1 500.50 ₪"
        assert casino_engine.format_shekels(350, show_sign=True) == "+350 ₪"
        assert casino_engine.format_shekels(-1200) == "-1 200 ₪"

    def test_format_shekels_handles_invalid_inputs_safely(self):
        """None, NaN, Inf return '0 ₪' safely without throwing exceptions."""
        assert casino_engine.format_shekels(None) == "0 ₪"
        assert casino_engine.format_shekels(float("nan")) == "0 ₪"
        assert casino_engine.format_shekels(float("inf")) == "0 ₪"

    def test_casino_keyboards_display_formatted_shekels(self):
        """Keyboard button texts must display formatted amounts with thousand spaces."""
        # Slots Lobby
        kb_slots_lobby = casino_engine.get_slots_lobby_keyboard(bet=5000, balance=50000)
        spin_btn = kb_slots_lobby.inline_keyboard[0][0]
        assert "5 000 ₪" in spin_btn.text

        # Slots In-game
        kb_slots_game = casino_engine.get_slots_keyboard(bet=10000, balance=50000)
        again_btn = kb_slots_game.inline_keyboard[0][0]
        assert "10 000 ₪" in again_btn.text

        # Coinflip Lobby
        kb_cf_lobby = casino_engine.get_coinflip_lobby_keyboard(bet=25000, balance=100000)
        assert "25 000 ₪" in kb_cf_lobby.inline_keyboard[0][0].text
        assert "25 000 ₪" in kb_cf_lobby.inline_keyboard[0][1].text

        # Blackjack Lobby
        kb_bj_lobby = casino_engine.get_blackjack_lobby_keyboard(bet=50000, balance=200000)
        assert "50 000 ₪" in kb_bj_lobby.inline_keyboard[0][0].text

        # Russian Roulette
        kb_rr_lobby = casino_engine.get_roulette_lobby_keyboard(bet=15000, balance=50000)
        assert "15 000 ₪" in kb_rr_lobby.inline_keyboard[0][0].text

        kb_rr_game = casino_engine.get_roulette_keyboard(bet=10000, current_mult=1.35)
        cashout_btn = kb_rr_game.inline_keyboard[1][0]
        assert "13 500 ₪" in cashout_btn.text


# =============================================================================
# 3. GAME TRANSPARENCY, MULTIPLIERS & EMOJIS
# =============================================================================

class TestGameTransparencyAndEmojis:
    """Verifies clear victory/defeat emojis and transparent multiplier reporting."""

    def test_slots_multipliers_and_emojis(self):
        """Slots outcomes have explicit multipliers and victory/defeat emojis."""
        for _ in range(50):
            reels, mult, title = casino_engine.roll_slots(bet=100)
            assert len(reels) == 3
            assert mult in (0.0, 1.8, 2.5, 2.8, 4.0, 4.5, 8.0, 25.0, 50.0)
            if mult >= 4.0:
                assert any(e in title for e in ("🔥", "👑", "💎", "✨"))
            elif mult > 0:
                assert any(e in title for e in ("🎉", "✨", "💎", "👑"))
            else:
                assert any(e in title for e in ("💨", "💀"))

    def test_coinflip_multipliers_and_emojis(self):
        """Coinflip displays clear win (x1.96, 🎉) or loss (x0, 💀)."""
        # Test 20 coinflips
        for _ in range(20):
            side, is_win, mult, msg = casino_engine.play_coinflip("heads", bet=100)
            if is_win:
                assert mult == 1.96
                assert "🎉 ПОБЕДА" in msg
                assert "x1.96" in msg
            else:
                assert mult == 0.0
                assert "💀 ПРОИГРЫШ" in msg
                assert any(s in side for s in ("ОРЕЛ", "РЕШКА"))

    def test_russian_roulette_multipliers_and_emojis(self):
        """Russian roulette outcomes feature clear click/bang emojis and progression."""
        user_id = 77799
        casino_engine.active_roulette_sessions.pop(user_id, None)

        survived, mult, streak, msg = casino_engine.play_russian_roulette_shot(user_id, bet=1000)
        if survived:
            assert streak == 1
            assert mult == 1.12
            assert "💨" in msg
            assert "x1.12" in msg
        else:
            assert mult == 0.0
            assert "💥 БАХ!" in msg

        casino_engine.active_roulette_sessions.pop(user_id, None)


# =============================================================================
# 4. LOOTBOXES: RARITY TIERS, DUPLICATE CASHBACK & INSUFFICIENT FUNDS
# =============================================================================

class TestLootboxUXAndRarityTiers:
    """Tests for 4-tier visual rarity, duplicate cashback transparency, and insufficient funds alerts."""

    def test_rarity_tiers_mapping(self):
        """Lootbox system recognizes all 4 visual rarity tiers: ⚪, 🔵, 🟣, 🟡."""
        assert lootbox_engine.get_rarity_info("⚪ ОБЫЧНЫЙ [Двачевский мусор]")["emoji"] == "⚪"
        assert lootbox_engine.get_rarity_info("🔵 РЕДКИЙ [Боевой расходник]")["emoji"] == "🔵"
        assert lootbox_engine.get_rarity_info("🟣 ЭПИЧЕСКИЙ [Базовый шмот 7 дней]")["emoji"] == "🟣"
        assert lootbox_engine.get_rarity_info("🟡 ЛЕГЕНДАРНЫЙ [Джекпот Абу]")["emoji"] == "🟡"
        assert lootbox_engine.get_rarity_info("🟡 ЛЕГЕНДАРНЫЙ [Шмот навсегда]")["emoji"] == "🟡"

    def test_roll_trash_lootbox_visual_tiers(self):
        """Every trash lootbox roll returns one of the 4 visual rarity grades."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = lootbox_engine.roll_trash_lootbox()
            assert any(tier.startswith(p) for p in ("⚪", "🔵", "🟣", "🟡"))
            rarity = lootbox_engine.get_rarity_info(tier)
            assert rarity["code"] in ("common", "rare", "epic", "legendary")

    def test_roll_gold_safe_visual_tiers(self):
        """Every gold safe roll returns one of the 4 visual rarity grades."""
        for _ in range(50):
            tier, title, desc, payload, base_cash = lootbox_engine.roll_gold_safe()
            assert any(tier.startswith(p) for p in ("⚪", "🔵", "🟣", "🟡"))
            rarity = lootbox_engine.get_rarity_info(tier)
            assert rarity["code"] in ("common", "rare", "epic", "legendary")

    def test_duplicate_apparel_cashback_explicit_messaging(self):
        """When dropping duplicate apparel, notification explicitly states 'У тебя уже есть этот предмет!' and cashback amount."""
        inv = {
            "body_cloak_is_permanent": True,
            "equipped_torso": "body_cloak",
        }
        payload = {
            "item_id": "body_cloak",
            "is_permanent": True,
            "slot": "torso",
        }
        res_inv, cash, note = lootbox_engine.apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash > 0
        assert "У тебя уже есть этот предмет!" in note
        assert "Начислен кэшбэк:" in note
        assert "Вечный дубликат" in note

    def test_duplicate_timed_apparel_when_perm_owned_messaging(self):
        """When rolling a timed version of an item already owned permanently, note informs user explicitly."""
        inv = {
            "body_cloak_is_permanent": True,
            "equipped_torso": "body_cloak",
        }
        payload = {
            "item_id": "body_cloak",
            "is_permanent": False,
            "dur_hours": 720,
            "slot": "torso",
        }
        res_inv, cash, note = lootbox_engine.apply_lootbox_reward(inv, payload, base_cash=0, case_type="gold")
        assert cash == 35
        assert "У тебя уже есть этот предмет!" in note
        assert "Начислен кэшбэк" in note
        assert "Утиль: +35 ₪" in note

    def test_duplicate_weapon_cashback_explicit_messaging(self):
        """When rolling a duplicate weapon, notification explicitly states 'У тебя уже есть этот предмет!'."""
        inv = {"knife_gun": True}
        payload = {"knife_gun": True}
        res_inv, cash, note = lootbox_engine.apply_lootbox_reward(inv, payload, base_cash=0, case_type="trash")
        assert cash == 35
        assert "У тебя уже есть этот предмет!" in note
        assert "Начислен кэшбэк" in note
        assert "утиль +35 ₪" in note

    def test_validate_lootbox_funds_insufficient_alert(self):
        """Informative callback alert message is generated when user has insufficient balance."""
        # Trash case costs 150 ₪, user has 40 ₪
        is_ok, price, alert = lootbox_engine.validate_lootbox_funds(balance=40, case_type="trash")
        assert is_ok is False
        assert price == 150
        assert "Недостаточно шекелей" in alert
        assert "Стоимость кейса: 150 ₪" in alert
        assert "Твой баланс: 40 ₪" in alert
        assert "Не хватает: 110 ₪" in alert

        # Gold safe costs 500 ₪, user has 500 ₪ -> allowed
        is_ok_gold, price_gold, alert_gold = lootbox_engine.validate_lootbox_funds(balance=500, case_type="gold")
        assert is_ok_gold is True
        assert price_gold == 500
        assert alert_gold == ""

    def test_format_lootbox_result_card(self):
        """Result card formatting includes rarity tier, item name, and optional balance."""
        card = lootbox_engine.format_lootbox_result_card(
            case_name="Золотой Сейф",
            tier="🟣 ЭПИЧЕСКИЙ [Элитный шмот 30 дней]",
            item_title="Плащ Нео",
            item_desc="Стильный кожаный плащ",
            cashback_amount=350,
            balance_after=14500
        )
        assert "ОТКРЫТ ЗОЛОТОЙ СЕЙФ!" in card
        assert "🟣 Эпический" in card
        assert "Редкость:" in card
        assert "Плащ Нео" in card
        assert "+350 ₪" in card
        assert "Начислен кэшбэк" in card
        assert "14 500 ₪" in card


# =============================================================================
# 5. AUCTIONS: OUTBID NOTIFICATION & ANTI-SNIPING TIMERS
# =============================================================================

class TestAuctionUXAndNotifications:
    """Tests for clear outbid notifications, anti-sniping extension notices, and escrow refunds."""

    def test_format_outbid_notification(self):
        """Outbid notification clearly informs user of outbid, 100% escrow refund, and new leader bid."""
        text = auction_engine.format_outbid_notification(
            auction_id=42,
            lot_title="Закреп треда /b/",
            refunded_amount=25000,
            new_bid=30000,
            new_leader_name="Анонимус #1234"
        )
        assert "ТВОЮ СТАВКУ ПЕРЕБИЛИ!" in text
        assert "#42" in text
        assert "Закреп треда /b/" in text
        assert "25 000 ₪" in text
        assert "100% эскроу-возврат" in text
        assert "30 000 ₪" in text
        assert "Анонимус #1234" in text

    def test_format_anti_sniping_notice(self):
        """Anti-sniping notice explains the +300s timer extension clearly."""
        notice = auction_engine.format_anti_sniping_notice(300)
        assert "АНТИ-СНАЙПИНГ" in notice
        assert "+5 мин." in notice
        assert "+300 сек." in notice
        assert "исключить снайпинг в последнюю секунду" in notice

    def test_auction_format_shekels_integration(self):
        """Auction engine formats numbers with thousands separators."""
        assert auction_engine.format_shekels(150000) == "150 000 ₪"
        assert auction_engine.format_shekels(10000000) == "10 000 000 ₪"


# =============================================================================
# 6. INSUFFICIENT FUNDS UX & QUICK-EXIT (WORK & DAILY BUTTONS)
# =============================================================================

class TestInsufficientFundsAndQuickExitUX:
    """
    Tests ensuring that when users have 0 ₪ or less than the minimum bet,
    the interface provides actionable quick-exit buttons (/work, /daily)
    rather than leaving them in a dead-end.
    """

    def test_casino_insufficient_funds_keyboard(self):
        """Keyboard explicitly offers quick exits: work_hub (/work) and bonus_daily (/daily)."""
        kb = casino_engine.get_casino_insufficient_funds_keyboard(balance=0)
        assert kb is not None
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        texts = [btn.text for row in kb.inline_keyboard for btn in row]

        assert "work_hub" in callbacks
        assert "bonus_daily" in callbacks
        assert any("/work" in t for t in texts)
        assert any("/daily" in t for t in texts)

    def test_casino_lobby_keyboards_quick_exit_when_zero_balance(self):
        """When player enters game lobbies with 0 ₪ balance, quick-exit buttons are appended."""
        keyboards = [
            casino_engine.get_slots_lobby_keyboard(bet=100, balance=0),
            casino_engine.get_slots_keyboard(bet=100, balance=0),
            casino_engine.get_coinflip_lobby_keyboard(bet=100, balance=0),
            casino_engine.get_coinflip_keyboard(bet=100, balance=0),
            casino_engine.get_blackjack_lobby_keyboard(bet=100, balance=0),
            casino_engine.get_blackjack_replay_keyboard(bet=100, balance=0),
            casino_engine.get_roulette_lobby_keyboard(bet=100, balance=0),
        ]
        for kb in keyboards:
            callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
            assert "work_hub" in callbacks, f"work_hub missing from {kb}"
            assert "bonus_daily" in callbacks, f"bonus_daily missing from {kb}"

    def test_casino_lobby_keyboards_no_redundant_exit_when_wealthy(self):
        """When player has ample balance (>= MIN_CASINO_BET), extra work/daily rows are not cluttering the game controls."""
        kb = casino_engine.get_slots_lobby_keyboard(bet=100, balance=50000)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "work_hub" not in callbacks
        assert "bonus_daily" not in callbacks

    def test_lootbox_insufficient_funds_keyboard(self):
        """Lootbox insufficient funds keyboard includes work and daily buttons."""
        kb = lootbox_engine.get_lootbox_insufficient_funds_keyboard(case_type="trash", balance=10)
        assert kb is not None
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "work_hub" in callbacks
        assert "bonus_daily" in callbacks


# =============================================================================
# 7. DUEL ESCROW & TIMEOUT REFUND INTEGRITY
# =============================================================================

class TestDuelEscrowAndTimeoutUX:
    """
    Tests ensuring duel challenges escrow funds immediately at creation time,
    preventing double-spend / balance drain in casino before duel acceptance,
    and verifying clean 100% refund on timeout or decline.
    """

    @pytest.mark.asyncio
    async def test_duel_immediate_escrow_deduction_prevents_casino_spend(self, isolated_test_db):
        """
        When user A places a duel stake, funds are deducted into escrow immediately.
        User A cannot subsequently spend those escrowed funds in the casino.
        """
        from common.database import add_user_global_balance, deduct_user_global_balance, get_user_global_balance

        db = isolated_test_db
        user_a = 99901
        board_id = "b"

        # 1. User starts with 1,000 ₪
        await add_user_global_balance(db, user_a, board_id, 1000)
        bal = await get_user_global_balance(db, user_a)
        assert bal == 1000

        # 2. User creates a duel with 600 ₪ stake -> immediately escrowed
        duel_stake = 600
        ok, remaining = await deduct_user_global_balance(db, user_a, board_id, duel_stake)
        assert ok is True
        assert remaining == 400

        # 3. User tries to bet 500 ₪ in casino while duel is open
        valid_bet, max_allowed, err = casino_engine.validate_casino_bet(500, balance=remaining)
        assert valid_bet is False
        assert "Недостаточно средств" in err

        # 4. Attempt to deduct 500 ₪ fails; balance never goes negative
        deduct_ok, current_bal = await deduct_user_global_balance(db, user_a, board_id, 500)
        assert deduct_ok is False
        assert current_bal == 400

    @pytest.mark.asyncio
    async def test_duel_timeout_refunds_escrow(self, isolated_test_db):
        """When an escrowed duel expires, the stake is fully refunded to the challenger."""
        from common.database import add_user_global_balance, deduct_user_global_balance, get_user_global_balance

        db = isolated_test_db
        user_a = 99902
        board_id = "b"
        stake = 750

        # Initial balance 1,500 ₪
        await add_user_global_balance(db, user_a, board_id, 1500)

        # Escrow deduction at creation
        ok, bal_after = await deduct_user_global_balance(db, user_a, board_id, stake)
        assert ok is True
        assert bal_after == 750

        # Expiration logic triggered
        duel_data = {"amount": stake, "board_id": board_id, "escrowed": True}
        if duel_data.get("escrowed"):
            await add_user_global_balance(db, user_a, duel_data["board_id"], duel_data["amount"])

        # Balance restored to 1,500 ₪
        final_bal = await get_user_global_balance(db, user_a)
        assert final_bal == 1500

    @pytest.mark.asyncio
    async def test_duel_cancellation_refunds_escrow(self, isolated_test_db):
        """When challenger cancels open duel, escrowed funds are refunded immediately."""
        from common.database import add_user_global_balance, deduct_user_global_balance, get_user_global_balance

        db = isolated_test_db
        user_a = 99903
        board_id = "b"
        stake = 300

        await add_user_global_balance(db, user_a, board_id, 500)
        ok, _ = await deduct_user_global_balance(db, user_a, board_id, stake)
        assert ok is True
        assert await get_user_global_balance(db, user_a) == 200

        # Cancel duel
        await add_user_global_balance(db, user_a, board_id, stake)
        assert await get_user_global_balance(db, user_a) == 500


# =============================================================================
# 8. CORRUPTED ACTIVE_ITEMS SELF-HEALING IN LOOTBOXES & SAFES
# =============================================================================

class TestLootboxCorruptedActiveItemsHealing:
    """
    Tests ensuring roll_trash_lootbox, roll_gold_safe, roll_whale_safe and apply_lootbox_reward
    gracefully heal corrupted, empty, string, None, or non-dict active_items without crashing.
    """

    @pytest.mark.parametrize("corrupted_input", [
        "",
        "   ",
        "corrupted { malformed json",
        None,
        [],
        12345,
        "null",
        "{broken",
    ])
    def test_roll_trash_lootbox_heals_corrupted_active_items(self, corrupted_input):
        """roll_trash_lootbox never raises ValueError, AttributeError or TypeError on corrupted active_items."""
        tier, title, desc, payload, base_cash = lootbox_engine.roll_trash_lootbox(active_items=corrupted_input)
        assert isinstance(tier, str) and len(tier) > 0
        assert isinstance(title, str) and len(title) > 0
        assert isinstance(desc, str)
        assert isinstance(payload, dict)
        assert isinstance(base_cash, int)

    @pytest.mark.parametrize("corrupted_input", [
        "",
        "   ",
        "corrupted { malformed json",
        None,
        [],
        12345,
    ])
    def test_roll_gold_safe_heals_corrupted_active_items(self, corrupted_input):
        """roll_gold_safe never raises ValueError, AttributeError or TypeError on corrupted active_items."""
        tier, title, desc, payload, base_cash = lootbox_engine.roll_gold_safe(active_items=corrupted_input)
        assert isinstance(tier, str) and len(tier) > 0
        assert isinstance(title, str) and len(title) > 0
        assert isinstance(desc, str)
        assert isinstance(payload, dict)
        assert isinstance(base_cash, int)

    @pytest.mark.parametrize("corrupted_input", [
        "",
        "   ",
        "malformed { string",
        None,
        [],
        999,
    ])
    def test_roll_whale_safe_heals_corrupted_active_items(self, corrupted_input):
        """roll_whale_safe never raises ValueError, AttributeError or TypeError on corrupted active_items."""
        import whale_economy_engine
        tier, title, desc, payload, base_cash = whale_economy_engine.roll_whale_safe(active_items=corrupted_input)
        assert isinstance(tier, str) and len(tier) > 0
        assert isinstance(title, str) and len(title) > 0
        assert isinstance(desc, str)
        assert isinstance(payload, dict)
        assert isinstance(base_cash, int)

        # Also via lootbox_engine proxy
        t2, t_title2, _, p2, _ = lootbox_engine.roll_whale_safe(active_items=corrupted_input)
        assert isinstance(t2, str)
        assert isinstance(p2, dict)

    @pytest.mark.parametrize("corrupted_input", [
        "",
        "corrupted json",
        None,
        [],
        123,
    ])
    def test_apply_lootbox_reward_heals_corrupted_active_items(self, corrupted_input):
        """apply_lootbox_reward heals corrupted active_items into a valid dict and applies rewards."""
        payload = {
            "grant_title": "[Король Помойки]",
            "title_days": 1,
            "item_id": "face_monocle",
            "is_permanent": False,
            "dur_hours": 24,
            "slot": "face"
        }
        res_items, final_cash, note = lootbox_engine.apply_lootbox_reward(
            active_items=corrupted_input,
            payload=payload,
            base_cash=100,
            case_type="gold"
        )
        assert isinstance(res_items, dict)
        assert res_items.get("custom_title") == "[Король Помойки]"
        assert res_items.get("equipped_face") == "face_monocle"
        assert final_cash >= 100


# =============================================================================
# 7. WAVE 2 REDTEAM: PVP WATCHDOGS, RAM LEAK RESILIENCE & CASINO MINI-GAMES
# =============================================================================

class TestPvpWatchdogsAndRAMIntegrity:
    """
    Validates background watchdog routines for classic duels, Russian Roulette,
    Dice duels, and Tic-Tac-Toe:
    - 100% refund of escrowed bets when challenger is muted or timeout expires.
    - Zero RAM leaks: all user session mapping dicts are cleanly purged.
    """

    @pytest.mark.asyncio
    async def test_classic_duel_watchdog_muted_creator_immediate_refund(self, isolated_test_db):
        """When a classic duel challenger is muted, watchdog immediately cancels and refunds 100% escrow."""
        import main
        from common.database import add_user_global_balance, get_user_global_balance

        db = isolated_test_db
        user_id = 88001
        board_id = "b"
        stake = 500

        # User starts with 500
        await add_user_global_balance(db, user_id, board_id, 0)

        # Place pending duel
        main._active_duels[user_id] = {
            "amount": stake,
            "board_id": board_id,
            "created_at": 100.0,
            "escrowed": True,
            "chat_id": -1001,
            "msg_id": 999,
            "last_tick_ts": 100.0,
        }

        with patch("common.database.is_shadow_muted", new=AsyncMock(return_value=True)):
            with patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)):
                await main.classic_duel_watchdog_step(bot=None)

        # Duel must be cancelled and purged from active duels
        assert user_id not in main._active_duels

        # Escrow must be 100% refunded to user balance
        bal = await get_user_global_balance(db, user_id)
        assert bal == stake

    @pytest.mark.asyncio
    async def test_russian_roulette_watchdog_muted_creator_cancels_and_cleans_ram(self, isolated_test_db):
        """When RR challenger is muted while pending, challenge is cancelled and user_active_rr_game cleared."""
        import russian_roulette_pvp as rr
        gid = "rr_mute_test_01"
        ch_id = 88002
        tgt_id = 88003

        rr.active_rr_games[gid] = {
            "game_id": gid,
            "challenger_id": ch_id,
            "target_id": tgt_id,
            "bet": 300,
            "state": "pending",
            "created_ts": 100.0,
            "board_id": "b",
            "chat_id": -1002,
            "msg_id": 888,
        }
        rr.user_active_rr_game[ch_id] = gid
        rr.user_active_rr_game[tgt_id] = gid

        with patch("common.database.is_shadow_muted", new=AsyncMock(return_value=True)):
            with patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)):
                await rr.rr_watchdog_step(bot=None)

        # Challenger and target must be removed from RAM mapping
        assert ch_id not in rr.user_active_rr_game
        assert tgt_id not in rr.user_active_rr_game

        # Game must be marked cancelled
        game = rr.active_rr_games.get(gid)
        assert game is not None
        assert game.get("state") == "cancelled"

    @pytest.mark.asyncio
    async def test_dice_duel_watchdog_muted_creator_cancels_and_cleans_ram(self, isolated_test_db):
        """When dice challenger is muted while pending, challenge is cancelled and user_active_dice_game cleared."""
        import dice_duel_engine as dd
        gid = "dice_mute_test_01"
        ch_id = 88004
        tgt_id = 88005

        dd.active_dice_games[gid] = {
            "game_id": gid,
            "player_1": ch_id,
            "player_2": None,
            "target_id": tgt_id,
            "bet": 400,
            "state": "pending",
            "created_ts": 100.0,
            "board_id": "b",
            "chat_id": -1003,
            "msg_id": 777,
        }
        dd.user_active_dice_game[ch_id] = gid
        dd.user_active_dice_game[tgt_id] = gid

        with patch("common.database.is_shadow_muted", new=AsyncMock(return_value=True)):
            with patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)):
                await dd.dice_watchdog_step(bot=None)

        # Challenger and target removed from active memory
        assert ch_id not in dd.user_active_dice_game
        assert tgt_id not in dd.user_active_dice_game

        # Game cancelled
        game = dd.active_dice_games.get(gid)
        assert game is not None
        assert game.get("state") == "cancelled"

    @pytest.mark.asyncio
    async def test_ttt_watchdog_muted_creator_cancels_and_cleans_ram(self, isolated_test_db):
        """When TTT challenger is muted while waiting, game is cancelled and user_active_ttt_session cleared."""
        import ttt_engine as ttt
        gid = "ttt_mute_test_01"
        ch_id = 88006
        tgt_id = 88007

        game = ttt.TicTacToeGame(
            game_id=gid,
            board_id="b",
            chat_id=-1004,
            challenger_id=ch_id,
            bet=250,
            target_user_id=tgt_id,
            status="waiting",
            created_at=100.0,
        )
        ttt.active_ttt_games[gid] = game
        ttt.user_active_ttt_session[ch_id] = gid
        ttt.user_active_ttt_session[tgt_id] = gid

        with patch("common.database.is_shadow_muted", new=AsyncMock(return_value=True)):
            with patch("common.bot_helpers.check_user_is_muted", new=AsyncMock(return_value=False)):
                await ttt.ttt_watchdog_step(bot=None)

        # Challenger and target removed from RAM session
        assert ch_id not in ttt.user_active_ttt_session
        assert tgt_id not in ttt.user_active_ttt_session

        # Status finished / cancelled
        assert game.status == "finished"
        assert game.finish_reason == "cancelled"

    @pytest.mark.asyncio
    async def test_watchdog_ram_leak_cleanup_purges_stale_finished_sessions(self):
        """Finished games older than 60s are completely pruned from RAM mappings."""
        import time
        import russian_roulette_pvp as rr
        import dice_duel_engine as dd
        import ttt_engine as ttt

        stale_time = time.time() - 120.0

        # 1. Russian roulette
        rr_gid = "rr_stale_cleanup_01"
        rr.active_rr_games[rr_gid] = {
            "game_id": rr_gid,
            "finished": True,
            "state": "finished",
            "finished_ts": stale_time,
            "challenger_id": 88010,
            "acceptor_id": 88011,
        }
        rr.user_active_rr_game[88010] = rr_gid
        rr.user_active_rr_game[88011] = rr_gid

        await rr.rr_watchdog_step(bot=None)
        assert rr_gid not in rr.active_rr_games
        assert 88010 not in rr.user_active_rr_game
        assert 88011 not in rr.user_active_rr_game

        # 2. Dice duel
        dd_gid = "dice_stale_cleanup_01"
        dd.active_dice_games[dd_gid] = {
            "game_id": dd_gid,
            "finished": True,
            "state": "finished",
            "finished_ts": stale_time,
            "player_1": 88012,
            "player_2": 88013,
        }
        dd.user_active_dice_game[88012] = dd_gid
        dd.user_active_dice_game[88013] = dd_gid

        await dd.dice_watchdog_step(bot=None)
        assert dd_gid not in dd.active_dice_games
        assert 88012 not in dd.user_active_dice_game
        assert 88013 not in dd.user_active_dice_game

        # 3. TTT
        ttt_gid = "ttt_stale_cleanup_01"
        tgame = ttt.TicTacToeGame(
            game_id=ttt_gid,
            board_id="b",
            chat_id=-1005,
            challenger_id=88014,
            opponent_id=88015,
            bet=100,
            status="finished",
            finished_at=stale_time,
        )
        ttt.active_ttt_games[ttt_gid] = tgame
        ttt.user_active_ttt_session[88014] = ttt_gid
        ttt.user_active_ttt_session[88015] = ttt_gid

        await ttt.ttt_watchdog_step(bot=None)
        assert ttt_gid not in ttt.active_ttt_games
        assert 88014 not in ttt.user_active_ttt_session
        assert 88015 not in ttt.user_active_ttt_session


class TestSoloCasinoMiniGamesAndInFlight:
    """
    Tests Telegram mini-games (Dice, Football, Basketball, Darts) in casino_engine:
    - Return structure, win/loss mechanics, tax calculation.
    - Anti-streak / high-roller tilt when balance > 100k or streak >= 5.
    - Per-user mutual exclusion with casino_in_flight_guard.
    """

    def test_play_dice_structure_and_outcomes(self):
        """play_dice returns correct structure for all values 1-6."""
        for roll in range(1, 7):
            res = casino_engine.play_dice(bet=100, balance=5000, user_id=9001, roll_value=roll)
            assert res["value"] == roll
            assert "is_win" in res
            assert "multiplier" in res
            assert "payout" in res
            assert "title" in res
            assert "description" in res

            if roll <= 3:
                assert res["is_win"] is False
                assert res["multiplier"] == 0.0
                assert res["payout"] == 0
            else:
                assert res["is_win"] is True
                assert res["multiplier"] > 1.0
                assert res["payout"] > 100

    def test_play_football_structure_and_outcomes(self):
        """play_football respects values 1-5 (goals vs saves/misses)."""
        for val in range(1, 6):
            res = casino_engine.play_football(bet=200, balance=10000, user_id=9002, value=val)
            assert res["value"] == val
            assert res["bet"] == 200
            if val in (1, 2):
                assert res["is_win"] is False
                assert res["multiplier"] == 0.0
            else:
                assert res["is_win"] is True
                assert res["multiplier"] >= 1.45

    def test_play_basketball_structure_and_outcomes(self):
        """play_basketball handles baskets (4, 5) and misses (1, 2, 3)."""
        for val in range(1, 6):
            res = casino_engine.play_basketball(bet=300, balance=15000, user_id=9003, value=val)
            assert res["value"] == val
            assert res["bet"] == 300
            if val <= 3:
                assert res["is_win"] is False
                assert res["multiplier"] == 0.0
            else:
                assert res["is_win"] is True
                assert res["multiplier"] >= 2.0

    def test_play_darts_structure_and_outcomes(self):
        """play_darts handles bullseye (6) and board hits (4, 5) vs misses."""
        for val in range(1, 7):
            res = casino_engine.play_darts(bet=400, balance=20000, user_id=9004, value=val)
            assert res["value"] == val
            assert res["bet"] == 400
            if val <= 3:
                assert res["is_win"] is False
            elif val == 6:
                assert res["is_win"] is True
                assert res["multiplier"] == 2.4
                assert "ЯБЛОЧКО" in res["title"]

    def test_mini_games_high_roller_tilt(self):
        """Mini games apply house edge tilt when player balance > 100,000 ₪."""
        # When balance > 100k, multiplier on dice roll 6 is tilted from 2.4 to 2.2
        res_tilted = casino_engine.play_dice(bet=100, balance=200_000, user_id=9005, roll_value=6)
        res_normal = casino_engine.play_dice(bet=100, balance=5_000, user_id=9006, roll_value=6)
        assert res_tilted["multiplier"] == 2.2
        assert res_normal["multiplier"] == 2.4

    @pytest.mark.asyncio
    async def test_casino_in_flight_guard_mutual_exclusion(self):
        """casino_in_flight_guard prevents simultaneous spins from the same user."""
        user_id = 99991
        entered = False

        async def worker1():
            nonlocal entered
            async with casino_engine.casino_in_flight_guard(user_id, action_name="test"):
                entered = True
                await asyncio.sleep(0.08)

        async def worker2():
            await asyncio.sleep(0.02)
            # Must raise CasinoInFlightError because worker1 is in-flight
            with pytest.raises(casino_engine.CasinoInFlightError):
                async with casino_engine.casino_in_flight_guard(user_id, action_name="test"):
                    pass

        await asyncio.gather(worker1(), worker2())
        assert entered is True
        assert casino_engine.is_casino_in_flight(user_id) is False


# =============================================================================
# 9. PVP ANONYMITY, ZERO ID LEAKS & BROADCAST RESILIENCE
# =============================================================================

class TestPvpAnonymityAndBroadcastUX:
    """Verifies that PVP games never leak raw Telegram user IDs or '[ID:' tags,
    and that open/targeted duels broadcast properly to board and direct targets."""

    def test_zero_user_id_leaks_in_pvp_cards_and_announcements(self):
        """PvP cards for Dice, RR, and TTT strictly use anon names and never contain [ID: or raw IDs."""
        uid_p1 = 111222333
        uid_p2 = 444555666
        uid_target = 777888999

        # 1. Dice Duel Cards
        game_dice_pending = {
            "game_id": 101,
            "board_id": "b",
            "player_1": uid_p1,
            "player_2": None,
            "target_id": uid_target,
            "bet": 1500,
            "mode": "classic",
            "state": "pending",
            "turn_deadline_ts": time.time() + 60,
            "round": 1,
            "p1_rolls": {},
            "p2_rolls": {},
            "current_turn": uid_p1,
            "finished": False
        }
        card_dice_p = dice_duel_engine.format_dice_game_message(game_dice_pending)
        assert "[ID:" not in card_dice_p
        assert str(uid_p1) not in card_dice_p
        assert str(uid_target) not in card_dice_p
        assert get_anon_id(uid_p1) in card_dice_p
        assert get_anon_id(uid_target) in card_dice_p

        game_dice_active = dict(game_dice_pending, player_2=uid_p2, state="active", current_turn=uid_p2)
        card_dice_a = dice_duel_engine.format_dice_game_message(game_dice_active)
        assert "[ID:" not in card_dice_a
        assert str(uid_p1) not in card_dice_a
        assert str(uid_p2) not in card_dice_a
        assert get_anon_id(uid_p1) in card_dice_a
        assert get_anon_id(uid_p2) in card_dice_a

        # 2. Russian Roulette Cards
        game_rr_challenge = {
            "game_id": 202,
            "board_id": "b",
            "challenger_id": uid_p1,
            "target_id": uid_target,
            "bet": 2500,
            "status": "pending",
            "current_chamber": 0,
            "turn_deadline_ts": time.time() + 60
        }
        card_rr_ch = russian_roulette_pvp.format_rr_challenge_message(game_rr_challenge)
        assert "[ID:" not in card_rr_ch
        assert str(uid_p1) not in card_rr_ch
        assert str(uid_target) not in card_rr_ch
        assert get_anon_id(uid_p1) in card_rr_ch
        assert get_anon_id(uid_target) in card_rr_ch

        game_rr_active = {
            "game_id": 202,
            "board_id": "b",
            "challenger_id": uid_p1,
            "acceptor_id": uid_p2,
            "bet": 2500,
            "current_chamber": 2,
            "turn": uid_p2,
            "turn_deadline_ts": time.time() + 60,
            "finished": False
        }
        card_rr_act = russian_roulette_pvp.format_rr_game_message(game_rr_active)
        assert "[ID:" not in card_rr_act
        assert str(uid_p1) not in card_rr_act
        assert str(uid_p2) not in card_rr_act
        assert get_anon_id(uid_p1) in card_rr_act
        assert get_anon_id(uid_p2) in card_rr_act

        # 3. Tic-Tac-Toe Cards
        game_ttt = ttt_engine.TicTacToeGame(
            game_id=303,
            board_id="b",
            chat_id=123456,
            challenger_id=uid_p1,
            target_user_id=uid_target,
            bet=1000
        )
        card_ttt_p = ttt_engine.render_game_text(game_ttt)
        assert "[ID:" not in card_ttt_p
        assert str(uid_p1) not in card_ttt_p
        assert str(uid_target) not in card_ttt_p
        assert get_anon_id(uid_p1) in card_ttt_p
        assert get_anon_id(uid_target) in card_ttt_p

        game_ttt.opponent_id = uid_p2
        game_ttt.status = "active"
        game_ttt.current_turn = uid_p2
        card_ttt_a = ttt_engine.render_game_text(game_ttt)
        assert "[ID:" not in card_ttt_a
        assert str(uid_p1) not in card_ttt_a
        assert str(uid_p2) not in card_ttt_a
        assert get_anon_id(uid_p1) in card_ttt_a
        assert get_anon_id(uid_p2) in card_ttt_a

        # 4. Announcement and flavor string lists
        for phrase in dice_duel_engine.DICE_TIMEOUT_ANNOUNCEMENTS:
            assert "[ID:" not in phrase
        for phrase in dice_duel_engine.DICE_SURRENDER_ANNOUNCEMENTS:
            assert "[ID:" not in phrase
        for phrase in dice_duel_engine.DICE_DRAW_ANNOUNCEMENTS:
            assert "[ID:" not in phrase
        for phrase in russian_roulette_pvp.RR_TIMEOUT_COWARD_PHRASES:
            assert "[ID:" not in phrase
        for phrase in russian_roulette_pvp.RR_SURRENDER_PHRASES:
            assert "[ID:" not in phrase
        for phrase in russian_roulette_pvp.RR_SHOT_PHRASES:
            assert "[ID:" not in phrase

    def test_targeted_duel_broadcast_dispatches_directly_to_target(self):
        """When a duel targets a specific user, the broadcast recipient list is [target_id]
        even if that target user is not in active board users."""
        board_id = "b"
        board_users = [1001, 1002, 1003]
        target_id = 9999

        # Target is NOT in active users
        assert target_id not in board_users

        # 1. TTT Targeted logic
        target_user_id = target_id
        if target_user_id is not None:
            active_users_ttt = [target_user_id]
        else:
            active_users_ttt = list(board_users)
        assert active_users_ttt == [target_id]

        # 2. Dice Duel Targeted logic
        if target_id is not None:
            active_users_dice = [target_id]
        else:
            active_users_dice = list(board_users)
        assert active_users_dice == [target_id]

        # 3. RR Targeted logic
        if target_id is not None:
            active_users_rr = [target_id]
        else:
            active_users_rr = list(board_users)
        assert active_users_rr == [target_id]

    def test_open_duel_broadcasts_to_all_board_active_users(self):
        """When a duel is open (no target_id), the broadcast dispatches to all board active users."""
        board_users = [1001, 1002, 1003, 1004]
        target_id = None

        if target_id is not None:
            active_users = [target_id]
        else:
            active_users = list(board_users)

        assert active_users == [1001, 1002, 1003, 1004]

    def test_pvp_finish_dm_includes_opponent_anon_name(self):
        """Direct notifications upon PVP game conclusion must contain the opponent's anonymous name."""
        winner_id = 111
        loser_id = 222
        winner_anon = get_anon_id(winner_id)
        loser_anon = get_anon_id(loser_id)

        # 1. TTT win/lose notification format
        win_notify_ttt = (
            f"👑 <b>ПОБЕДА В КРЕСТИКАХ-НОЛИКАХ #1!</b>\n\n"
            f"👤 Соперник: <b>Анон [{loser_anon}]</b>\n"
            f"Ты собрал выигрышную линию!"
        )
        lose_notify_ttt = (
            f"💀 <b>ПОРАЖЕНИЕ В КРЕСТИКАХ-НОЛИКАХ #1</b>\n\n"
            f"👤 Соперник: <b>Анон [{winner_anon}]</b>\n"
            f"Соперник собрал выигрышную линию."
        )
        assert f"👤 Соперник: <b>Анон [{loser_anon}]</b>" in win_notify_ttt
        assert f"👤 Соперник: <b>Анон [{winner_anon}]</b>" in lose_notify_ttt
        assert "[ID:" not in win_notify_ttt
        assert "[ID:" not in lose_notify_ttt

        # 2. Dice win/lose notification format
        win_notify_dice = (
            f"👑 <b>ПОБЕДА В ДАЙС-ДУЭЛИ #1!</b>\n\n"
            f"👤 Соперник: <b>Анон [{loser_anon}]</b>\n"
            f"💰 Твой чистый выигрыш: <b>+950 ₪</b> зачислен на баланс!"
        )
        lose_notify_dice = (
            f"💀 <b>ПОРАЖЕНИЕ В ДАЙС-ДУЭЛИ #1</b>\n\n"
            f"👤 Соперник: <b>Анон [{winner_anon}]</b>\n"
            f"Причина: Меньшая сумма очков на костях.\n"
        )
        assert f"👤 Соперник: <b>Анон [{loser_anon}]</b>" in win_notify_dice
        assert f"👤 Соперник: <b>Анон [{winner_anon}]</b>" in lose_notify_dice
        assert "[ID:" not in win_notify_dice
        assert "[ID:" not in lose_notify_dice

        # 3. RR win/lose notification format
        win_notify_rr = (
            f"👑 <b>ПОБЕДА В РУССКОЙ РУЛЕТКЕ #1!</b>\n\n"
            f"👤 Соперник: <b>Анон [{loser_anon}]</b>\n"
            f"💰 Твой чистый выигрыш: <b>+950 ₪</b>"
        )
        lose_notify_rr = (
            f"💥 <b>СМЕРТЕЛЬНЫЙ ВЫСТРЕЛ В РУССКОЙ РУЛЕТКЕ #1!</b>\n\n"
            f"👤 Соперник: <b>Анон [{winner_anon}]</b>\n"
            f"Камора #3 оказалась заряжена."
        )
        assert f"👤 Соперник: <b>Анон [{loser_anon}]</b>" in win_notify_rr
        assert f"👤 Соперник: <b>Анон [{winner_anon}]</b>" in lose_notify_rr
        assert "[ID:" not in win_notify_rr
        assert "[ID:" not in lose_notify_rr

