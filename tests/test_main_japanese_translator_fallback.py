import sys
import unittest
import os
import subprocess

class TestMainJapaneseTranslatorFallback(unittest.TestCase):
    def test_japanese_translator_missing_subprocess(self):
        """
        Verify that Dubsite_tgach/main.py correctly handles the missing
        japanese_translator module by catching ImportError and printing a warning,
        instead of crashing the application startup.
        """
        script = """
import sys
class FailingImporter:
    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if fullname == 'japanese_translator':
            raise ImportError("Mocked ImportError")
        return None
sys.meta_path.insert(0, FailingImporter)

import io
import contextlib

stdout = io.StringIO()
with contextlib.redirect_stdout(stdout):
    try:
        import Dubsite_tgach.main
    except Exception as e:
        import traceback; traceback.print_exc()

print(stdout.getvalue().strip())
"""
        env = os.environ.copy()
        env["SECRET_KEY"] = "test"
        env["DB_USER"] = "test"
        env["DB_PASS"] = "test"
        env["DB_HOST"] = "localhost"
        env["DB_NAME"] = "test"
        env["PYTHONPATH"] = os.getcwd()
        env["PYTHONIOENCODING"] = "utf-8"

        res = subprocess.run([sys.executable, "-X", "utf8", "-c", script], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertIn("⚠️ Не удалось импортировать japanese_translator. Проверь наличие файла в корне.", res.stdout)

if __name__ == '__main__':
    unittest.main()
