import sys
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import is_request_from_ru

class TestIsRequestFromRu(unittest.IsolatedAsyncioTestCase):
    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_from_ru(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "8.8.8.8"
        mock_get_country.return_value = "RU"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertTrue(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("8.8.8.8")

    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_not_from_ru(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "8.8.8.8"
        mock_get_country.return_value = "US"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertFalse(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("8.8.8.8")

    @patch('Dubsite_tgach.main.get_real_ip')
    @patch('Dubsite_tgach.main.get_country_by_ip')
    async def test_request_local(self, mock_get_country, mock_get_ip):
        mock_get_ip.return_value = "127.0.0.1"
        mock_get_country.return_value = "XX"
        mock_request = MagicMock()

        result = await is_request_from_ru(mock_request)
        self.assertFalse(result)
        mock_get_ip.assert_called_once_with(mock_request)
        mock_get_country.assert_called_once_with("127.0.0.1")

if __name__ == '__main__':
    unittest.main()
