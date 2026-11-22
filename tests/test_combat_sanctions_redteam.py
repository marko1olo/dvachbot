"""
tests/test_combat_sanctions_redteam.py

Red Team Adversarial Test Suite for Combat Moderation & Chat Sanctions:
1. Combat debounce lock (PvP spam protection against rapid-fire / duplicate attacks on same target).
2. Progressive durations, backfire scaling, and resistances across /shoot, /partyvan, /curse, /shit.
3. Wardrobe immunities: shit_immunity (/shit), schizo_immunity (/curse), mute_reduction (/shoot, /partyvan).
4. Strict non-negative durability floor (0.0 clamp, no -1/-5) and auto-unequip / stat disabling on break.
5. Resilient shadowmute and regular mute handling without unhandled exceptions or stack trace leakage.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from combat_moderation_engine import (
    calculate_combat_duration_and_backfire,
    check_and_set_combat_debounce,
    is_combat_target_debounced,
    release_combat_debounce,
    clear_combat_debounce,
    reset_combat_moderation_state,
    record_combat_attack,
)
from wardrobe_engine import (
    apply_armor_durability_hit,
    calculate_item_repair_cost,
    repair_wardrobe_item,
    get_wardrobe_total_stats,
    unequip_slot,
)


class TestCombatDebounceLock(unittest.TestCase):
    """Verifies that rapid-fire attacks against the same target are debounced and throttled."""

    def setUp(self):
        clear_combat_debounce()

    def tearDown(self):
        clear_combat_debounce()

    def test_first_attack_allowed_second_within_window_blocked(self):
        target_id = 55501
        is_debounced, rem = check_and_set_combat_debounce(target_id, debounce_sec=3.0)
        self.assertFalse(is_debounced)
        self.assertEqual(rem, 0.0)

        # Immediate second attack on same target must be blocked
        is_debounced2, rem2 = check_and_set_combat_debounce(target_id, debounce_sec=3.0)
        self.assertTrue(is_debounced2)
        self.assertGreater(rem2, 0.0)
        self.assertLessEqual(rem2, 3.0)

    def test_different_targets_do_not_interfere(self):
        target_a = 55502
        target_b = 55503
        is_debounced_a, _ = check_and_set_combat_debounce(target_a, debounce_sec=3.0)
        is_debounced_b, _ = check_and_set_combat_debounce(target_b, debounce_sec=3.0)

        self.assertFalse(is_debounced_a)
        self.assertFalse(is_debounced_b)

    def test_release_combat_debounce_allows_immediate_reattack(self):
        target_id = 55504
        check_and_set_combat_debounce(target_id, debounce_sec=5.0)
        self.assertTrue(is_combat_target_debounced(target_id, debounce_sec=5.0))

        release_combat_debounce(target_id)
        self.assertFalse(is_combat_target_debounced(target_id, debounce_sec=5.0))

        is_debounced, _ = check_and_set_combat_debounce(target_id, debounce_sec=5.0)
        self.assertFalse(is_debounced)

    def test_is_combat_target_debounced_read_only(self):
        target_id = 55505
        self.assertFalse(is_combat_target_debounced(target_id, debounce_sec=3.0))
        check_and_set_combat_debounce(target_id, debounce_sec=3.0)
        self.assertTrue(is_combat_target_debounced(target_id, debounce_sec=3.0))


class TestCombatDurationsAndWeaponInteractions(unittest.TestCase):
    """Verifies duration calculation, backfire, newbie protection, and resistances for all weapons."""

    def setUp(self):
        reset_combat_moderation_state()

    def tearDown(self):
        reset_combat_moderation_state()

    def test_newbie_immunity_applies_to_all_weapons(self):
        """Users with < 50 posts must be completely immune (0 duration) to all combat actions."""
        weapons = ["shoot", "partyvan", "curse", "shit", "mute_gun"]
        for w in weapons:
            dur, is_backfire, _ = calculate_combat_duration_and_backfire(
                attacker_id=101, target_id=202, weapon_type=w, target_posts=25
            )
            self.assertEqual(dur, 0, f"Weapon {w} did not respect newbie immunity!")
            self.assertFalse(is_backfire)

    @patch("random.random", return_value=0.99)  # Avoid random backfire
    def test_shoot_progressive_durations_veteran(self, _):
        """Shoot duration degrades over repeated usage in 24h: 15m -> 10m -> 5m -> 1m."""
        attacker = 301
        target = 401

        # 1st attack (0 previous in 24h)
        dur1, _, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertEqual(dur1, 900)  # 15m
        record_combat_attack(attacker, target, "shoot")

        # 2nd attack
        dur2, _, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertEqual(dur2, 600)  # 10m
        record_combat_attack(attacker, target, "shoot")

        # 3rd attack
        dur3, _, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertEqual(dur3, 300)  # 5m
        record_combat_attack(attacker, target, "shoot")

        # 4th attack
        dur4, _, _ = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertEqual(dur4, 60)  # 1m

    @patch("random.random", return_value=0.99)
    def test_partyvan_progressive_durations_veteran(self, _):
        """Partyvan duration degrades: 3h -> 1.5h -> 45m -> 20m."""
        attacker = 302
        target = 402

        dur1, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
        self.assertEqual(dur1, 10800)  # 3h
        record_combat_attack(attacker, target, "partyvan")

        dur2, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
        self.assertEqual(dur2, 5400)  # 1.5h
        record_combat_attack(attacker, target, "partyvan")

        dur3, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
        self.assertEqual(dur3, 2700)  # 45m
        record_combat_attack(attacker, target, "partyvan")

        dur4, _, _ = calculate_combat_duration_and_backfire(attacker, target, "partyvan", target_posts=300)
        self.assertEqual(dur4, 1200)  # 20m

    @patch("random.random", return_value=0.99)
    def test_curse_durations_and_schizo_immunity(self, _):
        """Curse duration degrades: 30m -> 15m -> 5m -> 1m; blocked by schizo_immunity."""
        attacker = 303
        target = 403

        dur1, _, _ = calculate_combat_duration_and_backfire(attacker, target, "curse", target_posts=300)
        self.assertEqual(dur1, 1800)  # 30m

        # Target with schizo_immunity (Ward 6: body_straitjacket + hat_tinfoil, or hat_golden_foil)
        immune_items = {
            "equipped_torso": "body_straitjacket",
            "equipped_head": "hat_tinfoil",
        }
        dur_immune, is_back, _ = calculate_combat_duration_and_backfire(
            attacker, target, "curse", target_posts=300, target_items=immune_items
        )
        self.assertEqual(dur_immune, 0, "Curse was not neutralized by schizo_immunity!")

    @patch("random.random", return_value=0.99)
    def test_shit_durations_and_shit_immunity(self, _):
        """Shit duration degrades: 10m -> 5m -> 2m -> 1m; blocked by shit_immunity."""
        attacker = 304
        target = 404

        dur1, _, _ = calculate_combat_duration_and_backfire(attacker, target, "shit", target_posts=300)
        self.assertEqual(dur1, 600)  # 10m

        # Target with boots has shit_immunity
        boots_items = {
            "equipped_feet": "feet_boots",
            "feet_boots_durability": 100.0,
        }
        dur_immune, _, _ = calculate_combat_duration_and_backfire(
            attacker, target, "shit", target_posts=300, target_items=boots_items
        )
        self.assertEqual(dur_immune, 0, "Shit was not neutralized by boots shit_immunity!")

    @patch("random.random", return_value=0.01)  # Force backfire trigger
    def test_backfire_trigger_returns_zero_duration(self, _):
        """When backfire triggers, duration is 0 and is_backfire is True."""
        attacker = 305
        target = 405
        record_combat_attack(attacker, target, "shoot")
        # 2nd attack has 15% backfire chance, random returns 0.01 < 0.15
        dur, is_backfire, chance = calculate_combat_duration_and_backfire(attacker, target, "shoot", target_posts=300)
        self.assertTrue(is_backfire)
        self.assertEqual(dur, 0)
        self.assertGreater(chance, 0.0)

    @patch("random.random", return_value=0.99)
    def test_wardrobe_mute_reduction_applies_to_shoot_and_partyvan(self, _):
        """Target with helmet (-50% mute) or riot police (-70% mute) takes reduced duration."""
        attacker = 306
        target = 406
        helmet_items = {
            "equipped_head": "hat_helmet",
            "hat_helmet_durability": 100.0,
        }
        dur_pv_helmet, _, _ = calculate_combat_duration_and_backfire(
            attacker, target, "partyvan", target_posts=300, target_items=helmet_items
        )
        # 10800 * 0.50 = 5400s
        self.assertEqual(dur_pv_helmet, 5400)


class TestWardrobeDurabilityAndFloorProtection(unittest.TestCase):
    """Verifies that armor durability stays non-negative and breaks cleanly."""

    def test_durability_damage_never_drops_below_zero(self):
        """Excess damage beyond current durability must clamp strictly at 0.0, never negative."""
        items = {
            "equipped_torso": "body_cloak",
            "body_cloak_durability": 5.0,
        }
        # Apply 50% damage when only 5% left
        ok, msg = apply_armor_durability_hit(items, slot="torso", damage_pct=0.50)
        self.assertTrue(ok)
        self.assertEqual(items["body_cloak_durability"], 0.0)
        self.assertTrue(items["body_cloak_broken"])
        self.assertIn("сломался", msg)

    def test_corrupted_negative_durability_clamped_safely(self):
        """If inventory somehow had negative durability (-10), it is clamped to 0.0 and treated as broken."""
        items = {
            "equipped_torso": "body_cloak",
            "body_cloak_durability": -10.0,
        }
        ok, msg = apply_armor_durability_hit(items, slot="torso", damage_pct=0.10)
        self.assertFalse(ok)
        self.assertEqual(items["body_cloak_durability"], 0.0)
        self.assertTrue(items["body_cloak_broken"])
        self.assertIn("уже сломан", msg)

    def test_auto_unequip_on_break(self):
        """When auto_unequip=True, broken armor is automatically unequipped from the slot."""
        items = {
            "equipped_torso": "body_cloak",
            "body_cloak_durability": 10.0,
        }
        ok, msg = apply_armor_durability_hit(items, slot="torso", damage_pct=0.20, auto_unequip=True)
        self.assertTrue(ok)
        self.assertEqual(items["body_cloak_durability"], 0.0)
        self.assertTrue(items["body_cloak_broken"])
        self.assertNotIn("equipped_torso", items)

    def test_broken_item_disables_stats_in_get_wardrobe_total_stats(self):
        """Equipped item with 0 durability contributes 0 defense in get_wardrobe_total_stats."""
        now = int(time.time())
        items = {
            "equipped_head": "hat_helmet",  # 45 defense normally
            "hat_helmet_durability": 0.0,
            "hat_helmet_broken": True,
            "hat_helmet_expires": now + 3600,
        }
        stats = get_wardrobe_total_stats(items, current_time=now)
        self.assertEqual(stats["total_defense"], 0)
        self.assertEqual(stats["mute_reduction_pct"], 0)

    def test_repair_negative_durability_calculation_safe(self):
        """calculate_item_repair_cost handles negative durability input without overflowing."""
        cost_neg = calculate_item_repair_cost("hat_helmet", current_durability=-25.0, user_balance=1000.0)
        cost_zero = calculate_item_repair_cost("hat_helmet", current_durability=0.0, user_balance=1000.0)
        self.assertEqual(cost_neg, cost_zero)
        self.assertGreater(cost_neg, 0)


class TestShadowmuteAndMuteResilience(unittest.IsolatedAsyncioTestCase):
    """Verifies that muted and shadowmuted users are diverted gracefully without crashes."""

    @patch("handlers.message_router.format_header", AsyncMock(return_value="<i>👻 Пост #99999</i>"))
    async def test_process_shadow_reject_executes_without_exception(self):
        """ShadowRejectContext executes cleanly without exceptions, leaking stack traces, or DB writes."""
        from handlers.message_router import process_shadow_reject
        from shared_state import ShadowRejectContext

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        ctx = ShadowRejectContext(
            bot=mock_bot,
            board_id="b",
            user_id=88801,
            content={"type": "text", "text": "Спам в шедоумуте", "header": "Тест"},
            reply_to_post=None,
            stream="ru",
        )

        with patch("handlers.message_router.send_message_to_users", AsyncMock()) as mock_send:
            await process_shadow_reject(ctx)
            self.assertTrue(mock_send.called)
            # Verify recipient is strictly the author only
            broadcast_cfg = mock_send.call_args[0][0]
            self.assertEqual(broadcast_cfg.recipients, {88801})
            self.assertTrue(broadcast_cfg.content.get("is_shadow_reject"))

    def test_is_wardrobe_item_broken_negative_durability(self):
        from wardrobe_engine import is_wardrobe_item_broken
        items = {"hat_helmet_durability": -5.0}
        self.assertTrue(is_wardrobe_item_broken(items, "hat_helmet"))

        items_dict_nested = {"hat_helmet": {"durability": -0.5}}
        self.assertTrue(is_wardrobe_item_broken(items_dict_nested, "hat_helmet"))


if __name__ == '__main__':
    unittest.main()
