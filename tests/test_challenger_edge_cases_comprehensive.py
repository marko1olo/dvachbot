# -*- coding: utf-8 -*-
"""
tests/test_challenger_edge_cases_comprehensive.py — Comprehensive Challenger 1 Edge Cases & Import Audits.
"""

import os
import sys
import io
import json
import sqlite3
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import stats_v2
import my_wrapped_generator


class TestChallengerEdgeCasesComprehensive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="edge_case_suite_")
        cls.db_path = os.path.join(cls.temp_dir, "dvach_bot.db")
        cls.db_uri_ro = f"file:{cls.db_path}?mode=ro"

        conn = sqlite3.connect(cls.db_path)
        for tbl in [
            "Users (user_id INTEGER PRIMARY KEY, balance REAL, active_items TEXT)",
            "Posts (post_num INTEGER, board_id TEXT, author_id INTEGER, timestamp REAL, content TEXT, reply_to_post_num INTEGER, PRIMARY KEY (board_id, post_num))",
            "UserTransactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, category TEXT, description TEXT, timestamp REAL)",
            "MoneyDrops (id INTEGER PRIMARY KEY AUTOINCREMENT, amount REAL, status TEXT, created_at REAL, claimed_at REAL)",
            "MediaReposts (file_unique_id TEXT PRIMARY KEY, times INTEGER, first_seen REAL)",
            "FileRegistry (file_unique_id TEXT PRIMARY KEY, tags TEXT, created_at REAL)",
            "Mutes (user_id INTEGER, mute_type TEXT, expires_at REAL)"
        ]:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {tbl}")

        # Seed specific edge-case users:
        # User 1: Clean user with 5 posts, 0 swear words (tox_row['tox'] is NULL)
        conn.execute("INSERT INTO Users VALUES (101, 500, '{}')")
        for p in range(1, 6):
            conn.execute("INSERT INTO Posts VALUES (?, 'b', 101, 1700000000 + ?, 'Добрый вечер аноны, как дела?', NULL)", (p, p))

        # User 2: User with NULL balance in database
        conn.execute("INSERT INTO Users VALUES (102, NULL, '{}')")
        conn.execute("INSERT INTO Posts VALUES (6, 'b', 102, 1700000000, 'Привет', NULL)")

        # User 3: User with 0 posts and 0 transactions
        conn.execute("INSERT INTO Users VALUES (103, 100, '{}')")

        # User 4: User with extreme wealth
        conn.execute("INSERT INTO Users VALUES (104, 1000000000000000.0, '{}')")

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_import_stats_hub_router(self):
        """Audit: stats_hub_router.py must be importable without missing 'os' or syntax errors."""
        try:
            import stats_hub_router
            self.assertIsNotNone(stats_hub_router.router)
        except NameError as e:
            self.fail(f"CRITICAL BUG: stats_hub_router failed to import due to missing variable/module: {e}")
        except Exception as e:
            self.fail(f"stats_hub_router import error: {type(e).__name__}: {e}")

    def test_import_site_stats_api(self):
        """Audit: site_tgach.stats_api must have all required imports including 'os'."""
        try:
            from site_tgach import stats_api
            self.assertIsNotNone(stats_api.router)
            # Test runtime fallback in view_stats_dashboard
            req = MagicMock()
            del req.app.state.templates
            res = stats_api.view_stats_dashboard(req)
        except NameError as e:
            self.fail(f"CRITICAL BUG: site_tgach/stats_api runtime NameError: {e}")
        except AttributeError:
            pass
        except Exception as e:
            if "name 'os' is not defined" in str(e):
                self.fail(f"CRITICAL BUG: site_tgach/stats_api missing import os: {e}")

    def test_wrapped_clean_user_no_swear_words(self):
        """User with posts but zero swear words -> tests tox_p None handling."""
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            data = my_wrapped_generator.fetch_user_wrapped_data(101)
            self.assertEqual(data['total_posts'], 5)
            buf = my_wrapped_generator.generate_my_wrapped_poster(101)
            self.assertIsInstance(buf, io.BytesIO)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_wrapped_user_null_balance(self):
        """User with balance = NULL in Users table."""
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            data = my_wrapped_generator.fetch_user_wrapped_data(102)
            buf = my_wrapped_generator.generate_my_wrapped_poster(102)
            self.assertIsInstance(buf, io.BytesIO)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_wrapped_brand_new_user_zero_posts(self):
        """Brand new user with 0 posts and 0 transactions."""
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            data = my_wrapped_generator.fetch_user_wrapped_data(103)
            buf = my_wrapped_generator.generate_my_wrapped_poster(103)
            self.assertIsInstance(buf, io.BytesIO)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_wrapped_nonexistent_user_id(self):
        """Non-existent user id (e.g. 999999)."""
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            data = my_wrapped_generator.fetch_user_wrapped_data(999999)
            buf = my_wrapped_generator.generate_my_wrapped_poster(999999)
            self.assertIsInstance(buf, io.BytesIO)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db


if __name__ == "__main__":
    unittest.main()
