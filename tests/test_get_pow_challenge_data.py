import sys
import os
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class TestGetPowChallengeData(unittest.TestCase):

    def test_dubsite_get_pow_challenge_data_default_difficulty(self):
        # We fetch the module directly via import to bypass any sys.modules masking
        # that previous tests might have left around dynamically without cleaning up.
        import importlib.util
        spec = importlib.util.spec_from_file_location("Dubsite_tgach.security", os.path.join(PROJECT_ROOT, "Dubsite_tgach", "security.py"))
        if spec and spec.loader:
            security_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(security_mod)
        else:
            self.skipTest("Could not load Dubsite_tgach.security directly")
            return

        with patch.object(security_mod, 'generate_challenge_str') as mock_generate:
            mock_generate.return_value = "mocked_challenge_string"

            result = security_mod.get_pow_challenge_data()

            mock_generate.assert_called_once()
            self.assertEqual(result, {
                "challenge": "mocked_challenge_string",
                "difficulty": 4 # DEFAULT_POW_DIFFICULTY is 4
            })

    def test_dubsite_get_pow_challenge_data_custom_difficulty(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("Dubsite_tgach.security", os.path.join(PROJECT_ROOT, "Dubsite_tgach", "security.py"))
        if spec and spec.loader:
            security_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(security_mod)
        else:
            self.skipTest("Could not load Dubsite_tgach.security directly")
            return

        with patch.object(security_mod, 'generate_challenge_str') as mock_generate:
            mock_generate.return_value = "mocked_challenge_string_custom"

            result = security_mod.get_pow_challenge_data(difficulty=8)

            mock_generate.assert_called_once()
            self.assertEqual(result, {
                "challenge": "mocked_challenge_string_custom",
                "difficulty": 8
            })

    def test_site_get_pow_challenge_data_default_difficulty(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("site_tgach.security", os.path.join(PROJECT_ROOT, "site_tgach", "security.py"))
        if spec and spec.loader:
            security_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(security_mod)
        else:
            self.skipTest("Could not load site_tgach.security directly")
            return

        with patch.object(security_mod, 'generate_challenge_str') as mock_generate:
            mock_generate.return_value = "mocked_challenge_string_site"

            result = security_mod.get_pow_challenge_data()

            mock_generate.assert_called_once()
            self.assertEqual(result, {
                "challenge": "mocked_challenge_string_site",
                "difficulty": 4
            })

    def test_site_get_pow_challenge_data_custom_difficulty(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("site_tgach.security", os.path.join(PROJECT_ROOT, "site_tgach", "security.py"))
        if spec and spec.loader:
            security_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(security_mod)
        else:
            self.skipTest("Could not load site_tgach.security directly")
            return

        with patch.object(security_mod, 'generate_challenge_str') as mock_generate:
            mock_generate.return_value = "mocked_challenge_string_site_custom"

            result = security_mod.get_pow_challenge_data(difficulty=10)

            mock_generate.assert_called_once()
            self.assertEqual(result, {
                "challenge": "mocked_challenge_string_site_custom",
                "difficulty": 10
            })

if __name__ == "__main__":
    unittest.main()
