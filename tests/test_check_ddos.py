import unittest
from unittest.mock import patch
import time

from site_tgach import security

class TestCheckDdos(unittest.TestCase):
    def setUp(self):
        # Reset the global state before each test
        security.REQUEST_HISTORY.clear()
        security.IP_BAN_LIST.clear()

    @patch('site_tgach.security.random.random', return_value=0.5)
    def test_initial_request(self, mock_random):
        """Test initial request is tracked and returns False."""
        ip = "1.1.1.1"
        self.assertFalse(security.check_ddos(ip))

        self.assertIn(ip, security.REQUEST_HISTORY)
        self.assertEqual(security.REQUEST_HISTORY[ip][0], 1)
        # Should not be banned
        self.assertNotIn(ip, security.IP_BAN_LIST)

    @patch('site_tgach.security.random.random', return_value=0.5)
    def test_under_limit(self, mock_random):
        """Test making multiple requests under the limit."""
        ip = "2.2.2.2"
        for _ in range(50):
            self.assertFalse(security.check_ddos(ip))

        self.assertIn(ip, security.REQUEST_HISTORY)
        self.assertEqual(security.REQUEST_HISTORY[ip][0], 50)
        self.assertNotIn(ip, security.IP_BAN_LIST)

    @patch('site_tgach.security.random.random', return_value=0.5)
    def test_rate_limit_exceeded(self, mock_random):
        """Test making more requests than MAX_REQUESTS_PER_WINDOW bans the IP."""
        ip = "3.3.3.3"
        for _ in range(security.MAX_REQUESTS_PER_WINDOW):
            self.assertFalse(security.check_ddos(ip))

        # The next request should trigger the ban
        self.assertTrue(security.check_ddos(ip))

        # IP should be removed from REQUEST_HISTORY and added to IP_BAN_LIST
        self.assertNotIn(ip, security.REQUEST_HISTORY)
        self.assertIn(ip, security.IP_BAN_LIST)

    @patch('site_tgach.security.random.random', return_value=0.5)
    def test_ip_is_banned(self, mock_random):
        """Test that subsequent requests for a banned IP return True."""
        ip = "4.4.4.4"
        security.IP_BAN_LIST[ip] = time.time() + security.BAN_TIME

        self.assertTrue(security.check_ddos(ip))

    @patch('site_tgach.security.random.random', return_value=0.5)
    def test_ban_expiration(self, mock_random):
        """Test that a ban expires correctly."""
        ip = "5.5.5.5"
        # Set ban to a time in the past
        security.IP_BAN_LIST[ip] = time.time() - 10

        # Calling check_ddos should remove the ban and return False for the new request
        self.assertFalse(security.check_ddos(ip))
        self.assertNotIn(ip, security.IP_BAN_LIST)
        self.assertIn(ip, security.REQUEST_HISTORY)

    @patch('site_tgach.security.random.random')
    @patch('site_tgach.security.time.time')
    def test_probability_cleanup(self, mock_time, mock_random):
        """Test probability cleanup removes expired records."""
        # Set random to trigger cleanup
        mock_random.return_value = 0.005

        base_time = 1000.0
        mock_time.return_value = base_time

        # Add an expired IP (window started way back)
        expired_ip = "expired_ip"
        security.REQUEST_HISTORY[expired_ip] = [10, base_time - security.RATE_LIMIT_WINDOW * 3]

        # Add an active IP
        active_ip = "active_ip"
        security.REQUEST_HISTORY[active_ip] = [10, base_time]

        # Call check_ddos with a new IP
        self.assertFalse(security.check_ddos("new_ip"))

        # Expired IP should be removed, active IP and new IP should remain
        self.assertNotIn(expired_ip, security.REQUEST_HISTORY)
        self.assertIn(active_ip, security.REQUEST_HISTORY)
        self.assertIn("new_ip", security.REQUEST_HISTORY)

    @patch('site_tgach.security.random.random')
    @patch('site_tgach.security.time.time')
    def test_max_history_size_cleanup(self, mock_time, mock_random):
        """Test that exceeding MAX_HISTORY_SIZE triggers aggressive cleanup."""
        # Set random to NOT trigger cleanup by probability
        mock_random.return_value = 0.5

        base_time = 1000.0
        mock_time.return_value = base_time

        # Artificially fill REQUEST_HISTORY above MAX_HISTORY_SIZE
        # Using a loop instead of dict comprehension to preserve order roughly in Python 3.7+
        for i in range(security.MAX_HISTORY_SIZE + 50):
            security.REQUEST_HISTORY[f"ip_{i}"] = [1, base_time]

        # Call check_ddos
        self.assertFalse(security.check_ddos("trigger_ip"))

        # Length should be reduced (by deleting 20% of the original MAX_HISTORY_SIZE + 50)
        # Original size: 10050. 20% is ~2010. So it should be around 8040 + 1 (trigger_ip) = 8041
        self.assertTrue(len(security.REQUEST_HISTORY) < security.MAX_HISTORY_SIZE)

if __name__ == '__main__':
    unittest.main()
