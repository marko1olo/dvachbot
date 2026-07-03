import sys
import unittest
import os
import ast

def get_format_timestamp_function():
    # Use robust path resolution so it works from anywhere
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    main_py_path = os.path.join(project_root, "main.py")

    with open(main_py_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Extract the function dynamically to avoid importing main.py's side effects
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'format_timestamp':
            # compile and eval
            code = compile(ast.Module(body=[node], type_ignores=[]), filename="<ast>", mode="exec")
            from datetime import datetime, UTC
            namespace = {'datetime': datetime, 'UTC': UTC}
            exec(code, namespace)
            return namespace['format_timestamp']
    return None

format_timestamp = get_format_timestamp_function()

class TestFormatTimestamp(unittest.TestCase):
    def test_valid_timestamp(self):
        ts = 1609459200.0 # 2021-01-01 00:00:00 UTC
        result = format_timestamp(ts)
        self.assertTrue(result.startswith("01.01.21 00:00") or result == "01.01.21 00:00")

    def test_zero_timestamp(self):
        ts = 0.0
        result = format_timestamp(ts)
        self.assertTrue(result.startswith("01.01.70 00:00") or result == "01.01.70 00:00")

    def test_invalid_timestamp_type(self):
        self.assertEqual(format_timestamp("not a float"), "")
        self.assertEqual(format_timestamp(None), "")
        self.assertEqual(format_timestamp([]), "")
        self.assertEqual(format_timestamp({}), "")

    def test_invalid_timestamp_value(self):
        self.assertEqual(format_timestamp(float('inf')), "")
        self.assertEqual(format_timestamp(float('-inf')), "")
        self.assertEqual(format_timestamp(float('nan')), "")

    def test_negative_timestamp(self):
        try:
            result = format_timestamp(-1000.0)
            self.assertTrue(isinstance(result, str))
        except Exception as e:
            self.fail(f"Negative timestamp should not raise an exception: {e}")

if __name__ == '__main__':
    unittest.main()
