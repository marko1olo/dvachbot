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

from Dubsite_tgach.main import get_country_by_ip


class TestGetCountryByIp(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # get_country_by_ip обёрнута в alru_cache. Заглушка-обход выше
        # срабатывает, только если Dubsite_tgach.main импортируется впервые
        # ИМЕННО здесь. Если модуль уже импортирован другим тестом
        # (например tests/test_check_perm.py), работает настоящий кэш, и тесты
        # получали закэшированный ответ предыдущего кейса ('YY' вместо 'ZZ').
        # Чистим кэш явно — корректно при любом варианте.
        for attr in ("cache_clear", "invalidate_all"):
            clear = getattr(get_country_by_ip, attr, None)
            if callable(clear):
                result = clear()
                if hasattr(result, "__await__"):
                    await result
                break

    async def test_local_ip(self):
        self.assertEqual(await get_country_by_ip("127.0.0.1"), "XX")
        self.assertEqual(await get_country_by_ip("localhost"), "XX")
        self.assertEqual(await get_country_by_ip("::1"), "XX")

    @patch('Dubsite_tgach.main.GEOIP_READER')
    async def test_geoip_reader_success(self, mock_geoip_reader):
        mock_response = MagicMock()
        mock_response.country.iso_code = "RU"
        mock_geoip_reader.country.return_value = mock_response

        result = await get_country_by_ip("95.173.136.1")
        self.assertEqual(result, "RU")

    @patch('Dubsite_tgach.main.GEOIP_READER')
    async def test_geoip_reader_raises_exception(self, mock_geoip_reader):
        mock_geoip_reader.country.side_effect = Exception("GeoIP Lookup Failed")
        result = await get_country_by_ip("8.8.8.8")
        self.assertEqual(result, "XX")

    @patch('Dubsite_tgach.main.GEOIP_READER', None)
    @patch('os.path.exists', return_value=False)
    async def test_geoip_reader_missing_db(self, mock_exists):
        result = await get_country_by_ip("8.8.4.4")
        self.assertEqual(result, "XX")

if __name__ == '__main__':
    unittest.main()
