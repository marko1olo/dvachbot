import unittest
from unittest.mock import patch
import common.locales

class TestLocales(unittest.TestCase):
    def setUp(self):
        self.mock_translations = {
            "ru": {
                "hello": "Привет, {name}",
                "goodbye": "Пока",
                "only_ru": "Только русский"
            },
            "en": {
                "hello": "Hello, {name}",
                "goodbye": "Goodbye"
            }
        }

    def test_exact_match(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            self.assertEqual(t("goodbye"), "Goodbye")

    def test_fallback_to_ru_missing_key(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            self.assertEqual(t("only_ru"), "Только русский")

    def test_fallback_to_ru_missing_lang(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("fr")
            self.assertEqual(t("goodbye"), "Пока")
            self.assertEqual(t("only_ru"), "Только русский")

    def test_missing_key_behavior_with_default(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            self.assertEqual(t("missing_key", default="default_value"), "default_value")

    def test_missing_key_behavior_without_default(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            self.assertEqual(t("missing_key"), "[missing_key]")

    def test_string_formatting(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            self.assertEqual(t("hello", name="John"), "Hello, John")

    def test_string_formatting_error_handling(self):
        with patch.dict(common.locales.TRANSLATIONS, self.mock_translations, clear=True):
            t = common.locales.get_t("en")
            # If formatting fails (e.g. missing kwarg), it should return the raw string
            self.assertEqual(t("hello", wrong_kwarg="John"), "Hello, {name}")

if __name__ == '__main__':
    unittest.main()
