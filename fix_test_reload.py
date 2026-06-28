import sys
with open("tests/test_site_importer.py", "r") as f:
    content = f.read()

new_content = content.replace("from site_tgach.importer import ThreadImporter", """
from unittest.mock import MagicMock
import importlib

# If test_main polluted the sys.modules, we need to clean it up for our test
for mod in list(sys.modules.keys()):
    if mod.startswith('site_tgach.') or mod == 'site_tgach':
        if isinstance(sys.modules[mod], MagicMock) or type(sys.modules[mod]).__name__ == 'MagicMock':
            del sys.modules[mod]

import site_tgach
# Mock some things that site_tgach.importer imports to avoid dependency errors
sys.modules['warhammer_mode'] = MagicMock()
sys.modules['common.bot_pool'] = MagicMock()
sys.modules['common.async_file_io'] = MagicMock()
sys.modules['site_tgach.image_processing'] = MagicMock()

from site_tgach.importer import ThreadImporter
""")

with open("tests/test_site_importer.py", "w") as f:
    f.write(new_content)
