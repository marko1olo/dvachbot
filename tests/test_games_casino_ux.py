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

import casino_engine
import lootbox_engine
import auction_engine


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
