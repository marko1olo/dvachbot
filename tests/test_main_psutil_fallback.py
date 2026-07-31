import unittest
import subprocess
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestMainPsutilFallback(unittest.TestCase):
    def get_env(self):
        env = os.environ.copy()
        env['PYTHONPATH'] = PROJECT_ROOT
        env['SECRET_KEY'] = 'test-secret-key-12345'
        env['DB_USER'] = 'test'
        env['DB_PASS'] = 'test'
        env['DB_HOST'] = 'localhost'
        env['DB_NAME'] = 'test'
        return env

    def test_psutil_missing_fallback(self):
        """Test that main.py gracefully falls back to None when psutil is missing in an isolated process."""
        script = """
import sys

# Mask psutil
sys.modules['psutil'] = None

try:
    import Dubsite_tgach.main as main
    assert getattr(main, 'psutil', ...) is None, "main.psutil should be None when psutil is missing"
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=self.get_env())

        if result.returncode != 0:
            self.fail(f"Subprocess failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        self.assertIn("SUCCESS", result.stdout)

    def test_psutil_present(self):
        """Test that main.py correctly assigns psutil when it is available in an isolated process."""
        script = """
import sys
import types

# Create a dummy psutil
dummy_psutil = types.ModuleType('psutil')
dummy_psutil.__name__ = 'psutil'
sys.modules['psutil'] = dummy_psutil

try:
    import Dubsite_tgach.main as main
    assert getattr(main, 'psutil', ...) is dummy_psutil, "main.psutil should be dummy_psutil when available"
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=self.get_env())

        if result.returncode != 0:
            self.fail(f"Subprocess failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        self.assertIn("SUCCESS", result.stdout)

if __name__ == '__main__':
    unittest.main()
