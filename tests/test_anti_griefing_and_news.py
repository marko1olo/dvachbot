# -*- coding: utf-8 -*-
import unittest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from shared_state import (
    get_target_grief_protection_remaining,
    register_target_attack,
    calculate_escalating_combat_cooldown,
    set_combat_cooldown,
    get_combat_cooldown_remaining,
    check_attack_abuse_limit
)
from post_helpers import check_post_numerals

class TestAntiGriefingAndNews(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        shared_state._TARGET_LAST_ATTACKED_TS.clear()
        shared_state._GLOBAL_COMBAT_COOLDOWNS.clear()
        shared_state._ATTACKER_SERIES_HISTORY.clear()
        shared_state._ATTACKER_TARGET_HISTORY.clear()
        shared_state._ATTACKER_ABUSE_WARNINGS.clear()

    def test_target_immunity_window(self):
        target_id = 999111
        # Initially no protection
        self.assertEqual(get_target_grief_protection_remaining(target_id), 0)

        # Register attack
        register_target_attack(target_id, duration_seconds=300)
        rem = get_target_grief_protection_remaining(target_id)
        self.assertTrue(295 <= rem <= 300)

        # Expired attack
        shared_state._TARGET_LAST_ATTACKED_TS[target_id] = time.time() - 301
        self.assertEqual(get_target_grief_protection_remaining(target_id), 0)

    def test_escalating_combat_cooldown(self):
        attacker_id = 777222
        # 1st attack
        cd1 = calculate_escalating_combat_cooldown(attacker_id, base_seconds=180)
        self.assertEqual(cd1, 180)

        # 2nd attack fast (< 3 min)
        cd2 = calculate_escalating_combat_cooldown(attacker_id, base_seconds=180)
        self.assertEqual(cd2, 360) # 2x

        # 3rd attack fast
        cd3 = calculate_escalating_combat_cooldown(attacker_id, base_seconds=180)
        self.assertEqual(cd3, 720) # 4x

    def test_numerals_quad_and_milestones(self):
        # Normal post
        self.assertIsNone(check_post_numerals(12345))
        
        # Quads
        self.assertEqual(check_post_numerals(44444), 5)
        self.assertEqual(check_post_numerals(107777), 4)
        
        # Milestones
        self.assertEqual(check_post_numerals(1000000), 8) # Миллионник
        self.assertEqual(check_post_numerals(500000), 7)  # Полумиллионник
        self.assertEqual(check_post_numerals(100000), 6)  # Сотка
        self.assertEqual(check_post_numerals(50000), 5)   # 50k

    async def test_publish_to_best_channel_deduplication(self):
        from news_channel_publisher import publish_to_best_channel
        
        mock_bot = AsyncMock()
        mock_bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=12345))

        post_data = {
            'author_id': 1234567,
            'content': {'text': 'Топ контент!', 'type': 'text'}
        }

        with patch('news_channel_publisher.get_target_channels', return_value=(-100200, -100300)), \
             patch('news_channel_publisher.add_channel_copy', new_callable=AsyncMock), \
             patch('news_channel_publisher.update_post_content', new_callable=AsyncMock):
            
            # 1st call -> should succeed
            res1 = await publish_to_best_channel(mock_bot, 'b', 55555, post_data, 5)
            self.assertTrue(res1)
            self.assertTrue(post_data.get('forwarded_to_best'))

            # 2nd call -> should be skipped (deduplicated)
            res2 = await publish_to_best_channel(mock_bot, 'b', 55555, post_data, 6)
            self.assertFalse(res2)

    async def test_publish_casino_jackpot_news(self):
        from news_channel_publisher import publish_casino_jackpot_news
        
        mock_bot = AsyncMock()
        mock_bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=54321))

        with patch('news_channel_publisher.get_target_channels', return_value=(-100200, -100300)):
            res = await publish_casino_jackpot_news(
                bot=mock_bot,
                user_id=123456,
                game_type="slots",
                bet_amount=10000,
                win_amount=500000,
                multiplier=50.0,
                symbols="[👑 | 👑 | 👑]",
                board_id="b"
            )
            self.assertTrue(res)
            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args[1]
            self.assertIn("МЕГА-ЗАНОС В КАЗИНО ТГАЧА", call_kwargs["text"])
            self.assertIn("+500,000 ₪", call_kwargs["text"])

    async def test_publish_abu_tier_upgrade(self):
        from news_channel_publisher import publish_abu_fund_tier_upgrade

        mock_bot = AsyncMock()
        mock_bot.get_me = AsyncMock(return_value=MagicMock(username="dvach_test_bot"))
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=98765))

        with patch('news_channel_publisher.get_target_channels', return_value=(-100200, -100300)):
            res = await publish_abu_fund_tier_upgrade(
                bot=mock_bot,
                old_tier=0,
                new_tier=1,
                current_fund=5000000,
                target_fund=1000000000
            )
            self.assertTrue(res)
            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args[1]
            self.assertIn("КАЗНА АБУ ПОВЫСИЛА УРОВЕНЬ", call_kwargs["text"])

if __name__ == '__main__':
    unittest.main()
