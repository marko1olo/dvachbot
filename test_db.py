import sys
from unittest.mock import MagicMock
import os
import asyncio

os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"
sys.modules['aiogram'] = MagicMock()
sys.modules['aiogram.types'] = MagicMock()
sys.modules['aiogram.types'].BufferedInputFile = MagicMock()
sys.modules['aiogram.types'].InputFile = MagicMock()

import common.database as db_mod
print("Database module imported successfully!")
