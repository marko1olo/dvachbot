import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from unittest.mock import patch, AsyncMock
from create_new_db import main

class TestCreateNewDb(unittest.IsolatedAsyncioTestCase):
    @patch('create_new_db.initialize_database', new_callable=AsyncMock)
    @patch('builtins.print')
    @patch('create_new_db.DB_NAME', 'test_db.db')
    async def test_main_success(self, mock_print, mock_initialize_database):
        result = await main()

        mock_initialize_database.assert_awaited_once()
        mock_print.assert_called_once_with("database initialized:", 'test_db.db')
        self.assertEqual(result, 0)

if __name__ == '__main__':
    unittest.main()
