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
        self.assertTrue("MATRIX" in text.upper() or "SIGNAL" in text.upper() or "DECRYPT" in text.upper() or "TRACE" in text.upper())

    def test_rus_transform(self):
        mode, text = rus_transform("я пошел пить воду")
        self.assertEqual(mode, "text")
        self.assertIn("Байкал", text)

    def test_abu_transform(self):
        mode, text = abu_transform("привет двач. как дела?")
        self.assertEqual(mode, "text")
        self.assertTrue("АБУ" in text.upper() or "2CH" in text.upper() or "ДВАЧ" in text.upper())

    def test_oldweb_transform(self):
        mode, text = oldweb_transform("автор привет медведь круто")
        self.assertEqual(mode, "text")
        self.assertIn("Winamp", text)
        self.assertTrue("аффтар" in text.lower())

    def test_jewish_transform(self):
        mode, text = jewish_transform("почем рыба на привозе")
        self.assertEqual(mode, "text")
        self.assertIn("ДЕРИБАСОВСКАЯ", text)

    def test_america_transform(self):
        mode, text = america_transform("i want my money back")
        self.assertEqual(mode, "text")
        self.assertIn("DISTRICT COURT", text)

    def test_holiday_transform(self):
        mode, text = holiday_transform("с новым годом аноны")
        self.assertEqual(mode, "text")
        self.assertIn("НОВОГОДНИЙ", text)

    def test_aliases(self):
        self.assertIs(america_transform, transform_america)
        self.assertIs(holiday_transform, transform_holiday)

if __name__ == '__main__':
    unittest.main()

