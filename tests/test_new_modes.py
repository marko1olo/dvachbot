import unittest
from unittest.mock import patch
from new_modes import _choose

class TestChoose(unittest.TestCase):
    @patch('new_modes.random.choice')
    def test_choose_delegates_to_random_choice(self, mock_choice):
        mock_choice.return_value = "b"
        values = ["a", "b", "c"]

        result = _choose(values)

        mock_choice.assert_called_once_with(("a", "b", "c"))
        self.assertEqual(result, "b")

    def test_choose_empty_sequence(self):
        with self.assertRaises(IndexError):
            _choose([])

if __name__ == '__main__':
    unittest.main()
