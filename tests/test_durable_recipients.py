import unittest
from delivery_manager import _durable_recipients_from_item

class TestDurableRecipients(unittest.TestCase):
    def test_empty_dict(self):
        self.assertEqual(_durable_recipients_from_item({}), [])

    def test_valid_ints(self):
        item = {"recipients": [3, 1, 2]}
        self.assertEqual(_durable_recipients_from_item(item), [3, 1, 2])

    def test_valid_strings(self):
        item = {"recipients": ["3", "1", "2"]}
        self.assertEqual(_durable_recipients_from_item(item), [])

    def test_mixed_valid_invalid(self):
        item = {"recipients": [1, "foo", 3]}
        self.assertEqual(_durable_recipients_from_item(item), [1, 3])

    def test_duplicate_ints(self):
        item = {"recipients": [1, 1, 2, 2, 3, 3]}
        self.assertEqual(_durable_recipients_from_item(item), [1, 1, 2, 2, 3, 3])

    def test_invalid_recipients_type(self):
        item = {"recipients": "not a list"}
        self.assertEqual(_durable_recipients_from_item(item), [])

    def test_negative_and_zero(self):
        item = {"recipients": [0, -5, -10, 10, 20]}
        self.assertEqual(_durable_recipients_from_item(item), [0, -5, -10, 10, 20])
