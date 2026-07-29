import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys

sys.modules['bjoern'] = MagicMock()

import fastapi
from starlette.requests import Request
from starlette.responses import Response

# Use mock environment variables when importing main
with patch.dict('os.environ', {'SECRET_KEY': 'test', 'DB_USER': 'test', 'DB_PASS': 'test', 'DB_HOST': 'localhost', 'DB_NAME': 'test'}):
    from Dubsite_tgach.main import country_cookie_middleware

class TestCountryCookieMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = {
            "type": "http",
            "method": "GET",
            "headers": [(b"host", b"testserver")],
        }

    async def test_static_path_skipped(self):
        self.scope["path"] = "/static/test.png"
        request = Request(self.scope)
        call_next = AsyncMock(return_value=Response(b"ok"))

        response = await country_cookie_middleware(request, call_next)

        call_next.assert_called_once_with(request)
        self.assertEqual(response.body, b"ok")
        self.assertEqual(response.headers.get("set-cookie"), None)

    @patch("Dubsite_tgach.main.get_real_ip")
    @patch("Dubsite_tgach.main.get_country_by_ip")
    async def test_country_cookie_set(self, mock_get_country, mock_get_ip):
        self.scope["path"] = "/test_path"
        request = Request(self.scope)
        call_next = AsyncMock(return_value=Response(b"ok"))

        mock_get_ip.return_value = "1.2.3.4"
        mock_get_country.return_value = "US"

        response = await country_cookie_middleware(request, call_next)

        call_next.assert_called_once_with(request)
        mock_get_ip.assert_called_once_with(request)
        mock_get_country.assert_called_once_with("1.2.3.4")

        self.assertIn("user_country=US;", response.headers.get("set-cookie", ""))
        self.assertIn("Max-Age=3600", response.headers.get("set-cookie", ""))
        self.assertIn("HttpOnly", response.headers.get("set-cookie", ""))
        self.assertIn("SameSite=lax", response.headers.get("set-cookie", ""))

    @patch("Dubsite_tgach.main.get_real_ip")
    async def test_exception_handled(self, mock_get_ip):
        self.scope["path"] = "/test_path"
        request = Request(self.scope)
        call_next = AsyncMock(return_value=Response(b"ok"))

        mock_get_ip.side_effect = Exception("Test error")

        response = await country_cookie_middleware(request, call_next)

        call_next.assert_called_once_with(request)
        self.assertEqual(response.headers.get("set-cookie"), None)
        self.assertEqual(response.body, b"ok")

if __name__ == '__main__':
    unittest.main()
