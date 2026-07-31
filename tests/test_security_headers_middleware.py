import unittest
from unittest.mock import AsyncMock, MagicMock
import os
import sys
from fastapi import Request, Response

# Setup required env var
os.environ["SECRET_KEY"] = "test"
os.environ["DB_USER"] = "test"
os.environ["DB_PASS"] = "test"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_NAME"] = "test"

# Make sure PROJECT_ROOT is in sys.path (needed if run from different working dir)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Dubsite_tgach.main import security_headers_middleware

class TestSecurityHeadersMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_security_headers_added(self):
        """
        Verify that security_headers_middleware adds the correct security headers
        to the response.
        """
        # Mock request
        request = MagicMock(spec=Request)

        # Mock response from call_next
        mock_response = Response()

        # Mock call_next function that handles the request processing
        call_next = AsyncMock(return_value=mock_response)

        # Call the middleware
        result = await security_headers_middleware(request, call_next)

        # Verify the call_next was called with the request
        call_next.assert_called_once_with(request)

        # Verify headers were added to the response
        headers = result.headers
        self.assertEqual(headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(headers.get("Strict-Transport-Security"), "max-age=63072000; includeSubDomains; preload")
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

        # Verify CSP contents
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("https://www.youtube.com", csp)
        self.assertIn("upgrade-insecure-requests", csp)

if __name__ == '__main__':
    unittest.main()
