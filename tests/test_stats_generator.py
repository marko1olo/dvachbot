import unittest
from unittest.mock import patch, MagicMock
import io

from stats_generator import fetch_user_stats_data, generate_user_stats_card, UserStatsCardData

class TestStatsGenerator(unittest.TestCase):


    def test_dict_factory(self):
        from stats_generator import dict_factory
        mock_cursor = MagicMock()
        mock_cursor.description = (('id', None, None, None, None, None, None), ('name', None, None, None, None, None, None), ('value', None, None, None, None, None, None))
        row = (1, 'test', 42.0)

        result = dict_factory(mock_cursor, row)

        expected = {'id': 1, 'name': 'test', 'value': 42.0}
        self.assertEqual(result, expected)

    def test_dict_factory_empty(self):
        from stats_generator import dict_factory
        mock_cursor = MagicMock()
        mock_cursor.description = ()
        row = ()

        result = dict_factory(mock_cursor, row)

        expected = {}
        self.assertEqual(result, expected)

    @patch('stats_generator.sqlite3.connect')
    def test_fetch_user_stats_data(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock fetchone to return our profile, posts_count, rx_received, rx_given, mutes_count
        # The execute commands map directly to fetchone results.
        mock_cursor.fetchone.side_effect = [
            (150.0, 'mod', 1234567890, 'Sup', '{}'), # 1. Fetch user profile
            (2,),  # 4. Count mutes
        ]

        mock_cursor.fetchall.side_effect = [
            [(1, 1234567890, 'test', '{"text": "hello", "reactions": {"users": {"999": ["👍", "🔥"]}}}')], # 2. user posts
            [('{"reactions": {"users": {"123": ["👍", "❤️"]}}}',)], # 3. reactions given
            [(101, 100), (123, 42), (200, 10)], # 5. board posters
        ]

        stats_data = fetch_user_stats_data(123, 'test')

        self.assertEqual(stats_data['balance'], 150.0)
        self.assertEqual(stats_data['role'], 'mod')
        self.assertEqual(stats_data['custom_prefix'], 'Sup')
        self.assertEqual(stats_data['posts_count'], 1)
        self.assertEqual(stats_data['rx_received'], 2)
        self.assertEqual(stats_data['rx_given'], 2)
        self.assertEqual(stats_data['mutes_count'], 2)
        self.assertEqual(stats_data['rank'], 2)
        self.assertEqual(stats_data['total_users'], 3)
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
            'custom_prefix': 'Sup',
            'posts_count': 42,
            'rx_received': 15,
            'rx_given': 20,
            'mutes_count': 2,
            'rank': 2,
            'total_users': 3,
            'cringe_factor': 10,
            'fav_board': 'test',
            'chronotype': 'Ночной сыч',
            'post_style': 'Базовые мысли',
            'avg_len': 50,
            'approval_pct': 85,
            'badges': ['Анон']
        }
        mock_generate_schizo_name.return_value = "Базированный-Анон"

        mock_buf = io.BytesIO(b"dummy image data")
        mock_draw_user_stats_card.return_value = mock_buf

        buf, text_report = generate_user_stats_card(123, 'test', 'tester')

        self.assertEqual(buf, mock_buf)
        self.assertIn("Статистика пользователя Базированный-Анон", text_report)
        self.assertIn("Статус:</b> Модератор (Sup)", text_report)
        self.assertIn("Баланс:</b> <code>150 ₪</code>", text_report)
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
            cringe_factor=10,
            rank=2,
            total_users=3,
            slang_comment='ОП-хуй и бог тредов! База сертифицирована, скуфы падают ниц.',
            fav_board='test',
            chronotype='Ночной сыч',
            post_style='Базовые мысли',
            avg_len=50,
            approval_pct=85,
            badges=['Анон']
        )
        mock_draw_user_stats_card.assert_called_once_with(expected_data, theme='auto')


    def test_generate_all_charts_basic(self):
        import time
        import os
        import tempfile
        import sqlite3

        original_connect = sqlite3.connect

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        conn = original_connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE Posts (timestamp integer, author_id integer, board_id text, post_num integer, reply_to_post_num integer, thread_id integer, content text)")
        c.execute("CREATE TABLE Users (user_id integer, board_id text, balance real, role text, created_at integer, lie_media integer, custom_prefix text)")
        c.execute("CREATE TABLE Mutes (user_id integer, board_id text)")
        c.execute("CREATE TABLE ReactionQueue (post_num integer, user_id integer, board_id text)")

        t = int(time.time()) - 1000
        c.execute("INSERT INTO Posts VALUES (?, ?, ?, ?, ?, ?, ?)", (t, 1, 'b', 1, None, 1, '{"type": "text", "text": "test post"}'))
        c.execute("INSERT INTO Posts VALUES (?, ?, ?, ?, ?, ?, ?)", (t + 12*3600, 2, 'b', 2, 1, 1, '{"type": "photo", "caption": "test media"}'))
        c.execute("INSERT INTO Posts VALUES (?, ?, ?, ?, ?, ?, ?)", (t + 24*3600, 1, 'b', 3, 2, 1, '{"text": "база"}'))
        c.execute("INSERT INTO Posts VALUES (?, ?, ?, ?, ?, ?, ?)", (t + 36*3600, 3, 'b', 4, 3, 1, '{"text": "мат"}')) # adding some "toxicity"

        c.execute("INSERT INTO Users VALUES (1, 'b', 100, 'user', ?, 0, '')", (t,))

        conn.commit()
        conn.close()

        def mock_connect_side_effect(*args, **kwargs):
            return original_connect(db_path)

        with patch('stats_generator.sqlite3.connect', side_effect=mock_connect_side_effect):
            # Also need to mock matplotlib pie to avoid value error if no wedges
            with patch('matplotlib.axes.Axes.pie') as mock_pie:
                mock_pie.return_value = ([], [], [])

                from stats_generator import generate_all_charts

                # Since some queries hit empty result sets if data isn't robust enough,
                # we just test that the function completes without errors and yields some charts
                images = generate_all_charts()

                self.assertIsInstance(images, list)

                # Should have generated at least a few charts
                self.assertGreater(len(images), 0)

                # verify return structure
                for img_name, img_buf in images:
                    self.assertIsInstance(img_name, str)
                    self.assertTrue(img_name.endswith('.png'))
                    self.assertIsNotNone(img_buf)

        os.remove(db_path)


if __name__ == '__main__':
    unittest.main()
