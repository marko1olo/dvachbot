import sys
import os
import unittest
from unittest.mock import patch
from parameterized import parameterized
import importlib.util
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

dubsite_sec = load_module("dubsite_sec", os.path.join(PROJECT_ROOT, "Dubsite_tgach", "security.py"))
site_sec = load_module("site_sec", os.path.join(PROJECT_ROOT, "site_tgach", "security.py"))

class TestCheckDdos(unittest.TestCase):
    def setUp(self):
        dubsite_sec.REQUEST_HISTORY.clear()
        dubsite_sec.IP_BAN_LIST.clear()
        site_sec.REQUEST_HISTORY.clear()
        site_sec.IP_BAN_LIST.clear()

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_first_request(self, name, sec_module):
        ip = "1.2.3.4"
        with patch.object(sec_module.random, 'random', return_value=1.0):
            result = sec_module.check_ddos(ip)
            self.assertFalse(result)
            self.assertIn(ip, sec_module.REQUEST_HISTORY)
            self.assertEqual(sec_module.REQUEST_HISTORY[ip][0], 1)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_multiple_requests_under_limit(self, name, sec_module):
        ip = "1.2.3.4"
        with patch.object(sec_module.random, 'random', return_value=1.0):
            sec_module.check_ddos(ip)
            sec_module.check_ddos(ip)
            result = sec_module.check_ddos(ip)
            self.assertFalse(result)
            self.assertEqual(sec_module.REQUEST_HISTORY[ip][0], 3)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_exceeding_limit_bans_ip(self, name, sec_module):
        ip = "1.2.3.4"
        with patch.object(sec_module.random, 'random', return_value=1.0):
            for _ in range(sec_module.MAX_REQUESTS_PER_WINDOW + 1):
                result = sec_module.check_ddos(ip)
            self.assertTrue(result)
            self.assertIn(ip, sec_module.IP_BAN_LIST)
            self.assertNotIn(ip, sec_module.REQUEST_HISTORY)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_already_banned_ip(self, name, sec_module):
        ip = "1.2.3.4"
        now = time.time()
        sec_module.IP_BAN_LIST[ip] = now + sec_module.BAN_TIME
        with patch.object(sec_module.random, 'random', return_value=1.0), \
             patch.object(sec_module.time, 'time', return_value=now):
            result = sec_module.check_ddos(ip)
            self.assertTrue(result)
            self.assertIn(ip, sec_module.IP_BAN_LIST)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_ban_expired(self, name, sec_module):
        ip = "1.2.3.4"
        now = time.time()
        sec_module.IP_BAN_LIST[ip] = now - 10
        with patch.object(sec_module.random, 'random', return_value=1.0), \
             patch.object(sec_module.time, 'time', return_value=now):
            result = sec_module.check_ddos(ip)
            self.assertFalse(result)
            self.assertNotIn(ip, sec_module.IP_BAN_LIST)
            self.assertIn(ip, sec_module.REQUEST_HISTORY)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_probabilistic_cleanup(self, name, sec_module):
        ip = "1.2.3.4"
        now = time.time()
        # Create an expired entry
        expired_ip = "5.6.7.8"
        sec_module.REQUEST_HISTORY[expired_ip] = [1, now - (sec_module.RATE_LIMIT_WINDOW * 2) - 10]

        with patch.object(sec_module.random, 'random', return_value=0.001), \
             patch.object(sec_module.time, 'time', return_value=now):
            sec_module.check_ddos(ip)
            # Expired IP should be removed
            self.assertNotIn(expired_ip, sec_module.REQUEST_HISTORY)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_max_history_cleanup(self, name, sec_module):
        now = time.time()

        # Populate with MAX_HISTORY_SIZE + 1 items
        for i in range(sec_module.MAX_HISTORY_SIZE + 1):
            sec_module.REQUEST_HISTORY[f"ip{i}"] = [1, now - (sec_module.RATE_LIMIT_WINDOW * 2) - 1]

        ip = "1.2.3.4"
        with patch.object(sec_module.random, 'random', return_value=1.0), \
             patch.object(sec_module.time, 'time', return_value=now):
            sec_module.check_ddos(ip)

            self.assertLessEqual(len(sec_module.REQUEST_HISTORY), sec_module.MAX_HISTORY_SIZE)

    @parameterized.expand([
        ("dubsite", dubsite_sec),
        ("site", site_sec),
    ])
    def test_window_expiration_resets_count(self, name, sec_module):
        ip = "1.2.3.4"
        now = time.time()
        sec_module.REQUEST_HISTORY[ip] = [100, now - sec_module.RATE_LIMIT_WINDOW - 1]

        with patch.object(sec_module.random, 'random', return_value=1.0), \
             patch.object(sec_module.time, 'time', return_value=now):
            result = sec_module.check_ddos(ip)
            self.assertFalse(result)
            self.assertEqual(sec_module.REQUEST_HISTORY[ip][0], 1)
            self.assertEqual(sec_module.REQUEST_HISTORY[ip][1], now)

if __name__ == "__main__":
    unittest.main()
