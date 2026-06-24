import sys
import unittest
import subprocess
import os

class TestRootMainAiosqliteImport(unittest.TestCase):
    def test_missing_aiosqlite_exits(self):
        # We run a small script in a subprocess that hides aiosqlite, mocks dependencies
        # and imports main.py
        script = """
import sys
import types
from unittest.mock import MagicMock
original_import = __import__
mocked_modules = {}

def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'aiosqlite':
        raise ImportError("Mocked ImportError for aiosqlite")
    try:
        return original_import(name, globals, locals, fromlist, level)
    except ImportError:
        # Do not mock the main module itself
        if name == 'main':
            raise
        if name not in mocked_modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            mod.__getattr__ = lambda n: MagicMock()
            sys.modules[name] = mod
            mocked_modules[name] = mod
        return mocked_modules[name]

import builtins
builtins.__import__ = mock_import

import main
"""
        env = os.environ.copy()
        # Ensure the project root is in PYTHONPATH so main.py can be found
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = project_root

        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env)

        self.assertEqual(result.returncode, 1)
        self.assertIn("Библиотека aiosqlite не установлена", result.stdout)

if __name__ == '__main__':
    unittest.main()
