import sys
import types
from unittest.mock import MagicMock

def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

mocked_deps = [
    'aiohttp', 'aiogram', 'aiogram.client', 'aiogram.client.default',
    'aiogram.exceptions', 'aiogram.filters', 'aiogram.types', 'aiogram.utils',
    'aiogram.utils.media_group', 'aiogram.fsm', 'aiogram.fsm.state', 'aiogram.fsm.context',
    'aiosqlite', 'pandas', 'matplotlib', 'matplotlib.pyplot', 'matplotlib.dates',
    'matplotlib.ticker', 'matplotlib.colors', 'numpy', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont',
    'dotenv', 'psutil', 'ujson', 'summarize', 'openai', 'httpx', 'itsdangerous', 'jinja2',
    'fastapi', 'starlette'
]

for dep in mocked_deps:
    mock_module(dep)

# Return MagicMock for any attribute access on our mocked modules
for mod_name in sys.modules:
    if mod_name in mocked_deps:
        sys.modules[mod_name].__getattr__ = lambda name: MagicMock()

try:
    from main import generate_anon_name
    print("Successfully imported!")
except Exception as e:
    print(f"Failed to import: {e}")
