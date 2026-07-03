import unittest
import subprocess
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestUjsonFallback(unittest.TestCase):
    def test_ujson_fallback_in_subprocess(self):
        """Test that main.py gracefully falls back to standard json when ujson is missing in an isolated process."""
        script = """
import sys
import os

# Mask ujson
sys.modules['ujson'] = None

try:
    import main
    import json
    assert main.json is json, "main.json did not fallback to built-in json"
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        env = os.environ.copy()
        env['PYTHONPATH'] = PROJECT_ROOT
        env['SECRET_KEY'] = 'test-secret-key-12345'

        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env)

        if result.returncode != 0:
            self.fail(f"Subprocess failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        self.assertIn("SUCCESS", result.stdout)

if __name__ == '__main__':
    unittest.main()
