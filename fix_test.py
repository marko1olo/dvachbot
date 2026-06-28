with open("tests/test_site_importer.py", "r") as f:
    content = f.read()

# Instead of importing ThreadImporter directly, we will use mock_module just like in test_main
new_content = """import unittest
import asyncio
import os
import sys

# Add project root to sys.path to allow importing from site_tgach
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables needed for initialization
os.environ["SECRET_KEY"] = "dummy_secret_key"
os.environ["BOT_TOKEN"] = "dummy_bot_token"
os.environ["OPENAI_API_KEY"] = "dummy_openai_key"

import types
def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# If the test suite already ran test_main.py, the site_tgach modules might be MagicMocks.
# In that case, we need to reload the actual site_tgach.importer module to test the real logic,
# but to do that, we must ensure its dependencies don't fail.
# Instead of reloading, a simpler approach is to test the actual function directly
# by importing its code, or let's just make sure we are not using a mocked version of ThreadImporter.

try:
    from site_tgach.importer import ThreadImporter
    from unittest.mock import MagicMock
    if isinstance(ThreadImporter, MagicMock):
        import importlib

        # Un-mock site_tgach.importer specifically
        if 'site_tgach.importer' in sys.modules:
            del sys.modules['site_tgach.importer']

        # We also need to unmock site_tgach if it's a mock
        if 'site_tgach' in sys.modules and isinstance(sys.modules['site_tgach'], MagicMock):
            del sys.modules['site_tgach']

        # And any other mocked dependencies of site_tgach.importer that prevent it from loading.
        # But wait, importer.py imports from site_tgach.image_processing, etc.
        # Let's mock them properly instead of as MagicMocks, or mock the specific functions.
        # Since we just want to test extract_posts_data, we can pull the class out without evaluating the whole module? No.

        # A safer trick is to define extract_posts_data directly in the test to verify logic? No, we must test the actual file.
except ImportError:
    pass
"""

with open("tests/test_site_importer.py", "w") as f:
    f.write(content) # I will use a different approach
