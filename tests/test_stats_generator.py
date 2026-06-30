import unittest
from unittest.mock import patch, MagicMock
import io

from stats_generator import fetch_user_stats_data, generate_user_stats_card, draw_user_stats_card, UserStatsCardData

class TestStatsGenerator(unittest.TestCase):

    @patch('stats_generator.sqlite3.connect')
    def test_fetch_user_stats_data(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock fetchone to return our profile, posts_count, rx_received, rx_given, mutes_count
        # The execute commands map directly to fetchone results.
        mock_cursor.fetchone.side_effect = [
            (150.0, 'mod', 1234567890, 10, 'Sup'), # 1. Fetch user profile
            (42,), # 2. Count actual posts
            (15,), # 3. Count reactions received
            (20,), # 4. Count reactions given
            (2,),  # 5. Count mutes
        ]

        # Mock fetchall for the all_users query
        mock_cursor.fetchall.return_value = [
            (101,), (123,), (200,)
        ]

        stats_data = fetch_user_stats_data(123, 'test')

        expected_data = {
            'balance': 150.0,
            'role': 'mod',
            'created_at': 1234567890,
            'lie_media': 10,
            'custom_prefix': 'Sup',
            'posts_count': 42,
            'rx_received': 15,
            'rx_given': 20,
            'mutes_count': 2,
            'rank': 2,
            'total_users': 3
        }

        self.assertEqual(stats_data, expected_data)
        mock_connect.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('stats_generator.draw_user_stats_card')
    @patch('stats_generator.fetch_user_stats_data')
    @patch('stats_generator.generate_schizo_name')
    def test_generate_user_stats_card(self, mock_generate_schizo_name, mock_fetch_user_stats_data, mock_draw_user_stats_card):
        mock_fetch_user_stats_data.return_value = {
            'balance': 150.0,
            'role': 'mod',
            'created_at': 1234567890,
            'lie_media': 10,
            'custom_prefix': 'Sup',
            'posts_count': 42,
            'rx_received': 15,
            'rx_given': 20,
            'mutes_count': 2,
            'rank': 2,
            'total_users': 3
        }
        mock_generate_schizo_name.return_value = "Базированный-Анон"

        mock_buf = io.BytesIO(b"dummy image data")
        mock_draw_user_stats_card.return_value = mock_buf

        buf, text_report = generate_user_stats_card(123, 'test', 'tester')

        self.assertEqual(buf, mock_buf)
        self.assertIn("Статистика пользователя Базированный-Анон", text_report)
        self.assertIn("Статус:</b> Модератор (Sup)", text_report)
        self.assertIn("Баланс:</b> 150 RUB", text_report)
        self.assertIn("Ранг борды:</b> #2 из 3", text_report)

        expected_data = UserStatsCardData(
            user_id=123,
            board_id='test',
            schizo_name='Базированный-Анон',
            role_name='Модератор',
            custom_prefix='Sup',
            role='mod',
            posts_count=42,
            rx_received=15,
            rx_given=20,
            mutes_count=2,
            balance=150.0,
            lie_media=10,
            rank=2,
            total_users=3,
            slang_comment='ОП-хуй и бог тредов! База сертифицирована, скуфы падают ниц.'
        )
        mock_draw_user_stats_card.assert_called_once_with(expected_data)

if __name__ == '__main__':
    unittest.main()
