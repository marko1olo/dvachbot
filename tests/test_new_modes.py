import unittest
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from new_modes import (
    matrix_transform,
    rus_transform,
    abu_transform,
    oldweb_transform,
    jewish_transform,
    america_transform,
    holiday_transform,
    transform_america,
    transform_holiday,
)

class TestNewModes(unittest.TestCase):
    def test_matrix_transform(self):
        mode, text = matrix_transform("hello world test text")
        self.assertEqual(mode, "text")
        matrix_keywords = ["MATRIX", "МАТРИЦ", "ZION", "OPERATOR", "KERNEL", "CONSTRUCT", "AGENT", "ENCRYPT", "DECRYPT", "PAYLOAD"]
        self.assertTrue(any(k in text.upper() for k in matrix_keywords))

    def test_rus_transform(self):
        mode, text = rus_transform("я пошел пить воду")
        self.assertEqual(mode, "text")
        rus_keywords = ["БАЙКАЛ", "РУС", "ПЕРУН", "ЯЩЕР", "ВЕЧЕ", "СЛАВЯН"]
        self.assertTrue(any(k in text.upper() for k in rus_keywords))

    def test_abu_transform(self):
        mode, text = abu_transform("привет двач. как дела?")
        self.assertEqual(mode, "text")
        abu_keywords = ["АБУ", "2CH", "ДВАЧ", "СОСАЧ", "ПАРАШИ", "ДУРКА", "ПСИХИАТРИИ", "ДЕАНОН", "ПАССКОД", "СЫЧ", "БОРД", "СЕРВЕР", "КАПЧ", "ТРЕД", "МАКАК"]
        self.assertTrue(any(k in text.upper() for k in abu_keywords))

    def test_oldweb_transform(self):
        mode, text = oldweb_transform("автор привет медведь круто")
        self.assertEqual(mode, "text")
        self.assertTrue(any(m in text.upper() for m in ["УПЯЧК", "LIVEINTERNET", "QIP", "WINAMP", "ICQ", "ОНОТОЛЕ", "БАШОРГ"]))
        self.assertTrue("аффтар" in text.lower() or "превед" in text.lower() or "медвед" in text.lower())

    def test_jewish_transform(self):
        mode, text = jewish_transform("почем рыба на привозе")
        self.assertEqual(mode, "text")
        jewish_keywords = ["ДЕРИБАСОВСКАЯ", "БАЛКОВСКОЙ", "ТАЛМУД", "ШЕКЕЛ", "РЕБЕ", "ПРИВОЗ", "ЦИЛЯ", "ШАББАТ", "СИНАГОГ"]
        self.assertTrue(any(k in text.upper() for k in jewish_keywords))

    def test_america_transform(self):
        mode, text = america_transform("i want my money back")
        self.assertEqual(mode, "text")
        america_keywords = ["WALL STREET", "DISTRICT COURT", "TEXAS", "CAPITAL", "FREEDOM", "NASDAQ", "CIA", "UNITED STATES"]
        self.assertTrue(any(k in text.upper() for k in america_keywords))

    def test_holiday_transform(self):
        mode, text = holiday_transform("с новым годом аноны")
        self.assertEqual(mode, "text")
        self.assertIn("НОВОГОДН", text.upper())

    def test_aliases(self):
        self.assertIs(america_transform, transform_america)
        self.assertIs(holiday_transform, transform_holiday)

if __name__ == '__main__':
    unittest.main()

