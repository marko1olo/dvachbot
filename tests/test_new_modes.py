import unittest
from unittest.mock import patch
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from new_modes import _choose

class TestChoose(unittest.TestCase):
    @patch('new_modes.random.choice')
    def test_choose_with_list(self, mock_choice):
        mock_choice.return_value = 'b'
        values = ['a', 'b', 'c']
        result = _choose(values)
        self.assertEqual(result, 'b')
        mock_choice.assert_called_once_with(('a', 'b', 'c'))

    @patch('new_modes.random.choice')
    def test_choose_with_tuple(self, mock_choice):
        mock_choice.return_value = 'x'
        values = ('x', 'y')
        result = _choose(values)
        self.assertEqual(result, 'x')
        mock_choice.assert_called_once_with(('x', 'y'))

    @patch('new_modes.random.choice')
    def test_choose_with_set(self, mock_choice):
        mock_choice.return_value = '1'
        values = {'1', '2'}
        result = _choose(values)
        self.assertEqual(result, '1')

        # We can't guarantee order with set, so we check if the arg is a tuple with those elements
        args, _ = mock_choice.call_args
        self.assertIsInstance(args[0], tuple)
        self.assertEqual(set(args[0]), {'1', '2'})

    def test_choose_empty_sequence(self):
        # random.choice raises IndexError when choosing from an empty sequence
        with self.assertRaises(IndexError):
            _choose([])

if __name__ == '__main__':
    unittest.main()
