import os
import unittest
from common.env_utils import proxy_env, PROXY_ENV_KEYS

class TestEnvUtils(unittest.TestCase):
    def setUp(self):
        # Save current state to restore after test
        self.saved_env = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        # Clear them out for a clean slate
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        # Restore state
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_proxy_env_with_url(self):
        proxy_url = "http://my.proxy:8080"

        # Initially not set (since we cleared in setUp)
        for key in PROXY_ENV_KEYS:
            self.assertNotIn(key, os.environ)

        with proxy_env(proxy_url):
            for key in PROXY_ENV_KEYS:
                self.assertEqual(os.environ.get(key), proxy_url)

        # Restored to not set
        for key in PROXY_ENV_KEYS:
            self.assertNotIn(key, os.environ)

    def test_proxy_env_with_none(self):
        # Set them to some existing value
        for key in PROXY_ENV_KEYS:
            os.environ[key] = "http://existing.proxy:1234"

        with proxy_env(None):
            # Should be removed inside the block
            for key in PROXY_ENV_KEYS:
                self.assertNotIn(key, os.environ)

        # Should be restored outside the block
        for key in PROXY_ENV_KEYS:
            self.assertEqual(os.environ.get(key), "http://existing.proxy:1234")

    def test_proxy_env_restores_correctly_on_exception(self):
        # Set them to some existing value
        for key in PROXY_ENV_KEYS:
            os.environ[key] = "http://existing.proxy:1234"

        proxy_url = "http://my.proxy:8080"

        try:
            with proxy_env(proxy_url):
                for key in PROXY_ENV_KEYS:
                    self.assertEqual(os.environ.get(key), proxy_url)
                raise ValueError("Test Exception")
        except ValueError:
            pass

        # Should be restored outside the block despite exception
        for key in PROXY_ENV_KEYS:
            self.assertEqual(os.environ.get(key), "http://existing.proxy:1234")

if __name__ == '__main__':
    unittest.main()
