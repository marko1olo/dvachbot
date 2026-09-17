import unittest
from common.json_utils import fast_json_loads, fast_json_dumps

class CustomObject:
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return f"CustomObject({self.value})"

class TestJsonUtils(unittest.TestCase):
    def test_fast_json_loads_basic(self):
        data = '{"key": "value", "number": 42}'
        result = fast_json_loads(data)
        self.assertEqual(result, {"key": "value", "number": 42})

    def test_fast_json_loads_bytes(self):
        data = b'{"key": "value", "number": 42}'
        result = fast_json_loads(data)
        self.assertEqual(result, {"key": "value", "number": 42})

    def test_fast_json_loads_empty(self):
        self.assertIsNone(fast_json_loads(""))
        self.assertIsNone(fast_json_loads(b""))
        self.assertIsNone(fast_json_loads(None))

    def test_fast_json_dumps_basic(self):
        obj = {"key": "value", "number": 42}
        result = fast_json_dumps(obj)
        # Verify it can be loaded back properly
        self.assertEqual(fast_json_loads(result), obj)
        self.assertIsInstance(result, str)


    def test_fast_json_dumps_custom_object(self):
        custom = CustomObject("test")
        obj = {"custom": custom}

        result = fast_json_dumps(obj)
        loaded = fast_json_loads(result)
        self.assertEqual(loaded, {"custom": "CustomObject(test)"})

if __name__ == '__main__':
    unittest.main()
