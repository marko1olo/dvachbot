import sys
from pathlib import Path
# scripts/ moved here after refactor
_scripts_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import unittest
import tempfile
import os
import builtins
from unittest.mock import patch
from datetime import datetime, timedelta
import analyze_logs


class TestAnalyzeLogs(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory and file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_filepath = os.path.join(self.temp_dir.name, "visitors.log")

    def tearDown(self):
        self.temp_dir.cleanup()
        # Clean up the output file if it exists
        if os.path.exists("site_stats.md"):
            os.remove("site_stats.md")

    def create_log_file(self, content):
        with open(self.log_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def test_analyze_visitors_log_basic(self):
        # Test basic functionality with some valid and invalid entries
        now = datetime.now()
        dt1 = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        dt2 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

        # Valid DO
        log_content = f"{dt1},123 | [DO] 1.2.3.4 | GET /api/data\n"
        # Valid ENTER
        log_content += f"{dt1},123 | [ENTER] 1.2.3.4 (US)\n"
        # Valid LIVE
        log_content += f"{dt2},123 | [LIVE] 1.2.3.4\n"
        # Invalid format
        log_content += f"invalid line\n"
        # Old date
        old_dt = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        log_content += f"{old_dt},123 | [DO] 1.2.3.4 | GET /api/data\n"

        self.create_log_file(log_content)

        analyze_logs.analyze_visitors_log(self.log_filepath)

        self.assertTrue(os.path.exists("site_stats.md"))
        with open("site_stats.md", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("**Уникальных IP:** 1", content)
            self.assertIn("**Всего запросов/действий:** 1", content)
            self.assertIn("**Предположительно Живых людей:** 1", content)
            self.assertIn("**US**: 1 уников", content)
            self.assertIn("`/api/data`: 1 раз", content)

    def test_analyze_visitors_log_bot(self):
        # Test bot detection logic
        now = datetime.now()
        dt1 = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        # Bot does DO but no LIVE
        log_content = f"{dt1},123 | [DO] 1.2.3.5 | GET /api/bot_endpoint\n"

        self.create_log_file(log_content)

        analyze_logs.analyze_visitors_log(self.log_filepath)

        self.assertTrue(os.path.exists("site_stats.md"))
        with open("site_stats.md", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("**Уникальных IP:** 1", content)
            self.assertIn("**Всего запросов/действий:** 1", content)
            self.assertIn("**Предположительно Ботов/Скриптов/Парсеров:** 1", content)
            self.assertIn("`/api/bot_endpoint`: 1 раз", content)

    def test_analyze_visitors_log_empty_or_invalid(self):
        # Test with empty file
        self.create_log_file("")
        analyze_logs.analyze_visitors_log(self.log_filepath)
        with open("site_stats.md", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("**Уникальных IP:** 0", content)

        # Test with unparsable lines
        self.create_log_file("completely unparsable line\nand another one")
        analyze_logs.analyze_visitors_log(self.log_filepath)
        with open("site_stats.md", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("**Уникальных IP:** 0", content)

    def test_analyze_visitors_log_date_parse_error(self):
        # Test date parse error by providing valid general format but invalid date string
        log_content = f"9999-99-99 99:99:99,123 | [DO] 1.2.3.4 | GET /api/data\n"
        self.create_log_file(log_content)

        analyze_logs.analyze_visitors_log(self.log_filepath)
        with open("site_stats.md", "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("**Уникальных IP:** 0", content)
