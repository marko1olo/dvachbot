import unittest
import re
from stats_generator import generate_schizo_name


class TestSchizoName(unittest.TestCase):
    def test_deterministic_output(self):
        """Test that the same user_id always produces the same name."""
        user_id = 12345
        name1 = generate_schizo_name(user_id)
        name2 = generate_schizo_name(user_id)
        self.assertEqual(name1, name2)
        # 123 is Поехавший-Сояк (#123)
        self.assertEqual(generate_schizo_name(123), "Поехавший-Сояк (#123)")

    def test_different_users(self):
        """Test that different user IDs generate different names (most of the time)."""
        name1 = generate_schizo_name(123)
        name2 = generate_schizo_name(456)
        self.assertNotEqual(name1, name2)

    def test_zero_and_none(self):
        """Test handling of 0 and None."""
        self.assertEqual(generate_schizo_name(0), "Анонимус")
        self.assertEqual(generate_schizo_name(None), "Анонимус")

    def test_format(self):
        """Test the format of the output string."""
        name = generate_schizo_name(987654321)
        # Matches formats like "Word-Word (#4321)"
        pattern = r"^[А-Яа-я]+-[А-Яа-я]+\s\(#\d{1,4}\)$"
        self.assertTrue(re.match(pattern, name), f"Name '{name}' doesn't match format")


if __name__ == "__main__":
    unittest.main()
