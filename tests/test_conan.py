import unittest
from unittest.mock import patch
from conan import conan_phrase

class TestConanPhrase(unittest.TestCase):
    def test_conan_phrase_default(self):
        """Test conan_phrase with default username argument"""
        result = conan_phrase()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_conan_phrase_custom(self):
        """Test conan_phrase with a custom username"""
        result = conan_phrase("TestUser")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch('conan.secrets.choice')
    def test_conan_phrase_formatting(self, mock_choice):
        """Test conan_phrase string formatting with deterministic mocked values"""
        # mock_choice is called for: tpl, inv, wgt, ach, ins, fact, catch
        mock_choice.side_effect = [
            "{name} {inv} {wgt} {ach} {ins} {fact} {catch}", # tpl
            "MOCK_INV", # inv
            "MOCK_WGT", # wgt
            "MOCK_ACH", # ach
            "MOCK_INS", # ins
            "MOCK_FACT", # fact
            "MOCK_CATCH", # catch
        ]

        result = conan_phrase("CustomUser")
        expected = "CustomUser MOCK_INV MOCK_WGT MOCK_ACH MOCK_INS MOCK_FACT MOCK_CATCH"
        self.assertEqual(result, expected)
        self.assertEqual(mock_choice.call_count, 7)

if __name__ == '__main__':
    unittest.main()
