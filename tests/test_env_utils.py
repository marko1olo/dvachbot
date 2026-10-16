import os
import unittest
from common.env_utils import temporary_env, proxy_env

class TestEnvUtils(unittest.TestCase):
    def test_temporary_env_no_args(self):
        """Test that calling temporary_env() without args works without exceptions."""
        with temporary_env():
            pass

    def test_temporary_env_overrides(self):
        os.environ["TEST_ENV_KEY_1"] = "original_1"
        try:
            with temporary_env(overrides={"TEST_ENV_KEY_1": "new_1", "TEST_ENV_KEY_2": "new_2"}):
                self.assertEqual(os.environ.get("TEST_ENV_KEY_1"), "new_1")
                self.assertEqual(os.environ.get("TEST_ENV_KEY_2"), "new_2")

            self.assertEqual(os.environ.get("TEST_ENV_KEY_1"), "original_1")
            self.assertNotIn("TEST_ENV_KEY_2", os.environ)
        finally:
            os.environ.pop("TEST_ENV_KEY_1", None)
            os.environ.pop("TEST_ENV_KEY_2", None)

    def test_temporary_env_remove(self):
        os.environ["TEST_ENV_KEY_3"] = "original_3"
        try:
            with temporary_env(remove=("TEST_ENV_KEY_3",)):
                self.assertNotIn("TEST_ENV_KEY_3", os.environ)

            self.assertEqual(os.environ.get("TEST_ENV_KEY_3"), "original_3")
        finally:
            os.environ.pop("TEST_ENV_KEY_3", None)

    def test_temporary_env_exception_recovery(self):
        os.environ["TEST_ENV_KEY_4"] = "original_4"
        try:
            try:
                with temporary_env(overrides={"TEST_ENV_KEY_4": "new_4"}):
                    self.assertEqual(os.environ.get("TEST_ENV_KEY_4"), "new_4")
                    raise ValueError("Test exception")
            except ValueError:
                pass

            self.assertEqual(os.environ.get("TEST_ENV_KEY_4"), "original_4")
        finally:
            os.environ.pop("TEST_ENV_KEY_4", None)

if __name__ == "__main__":
    unittest.main()
