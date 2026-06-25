import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from common.http_utils import is_retryable_error

class TestHttpUtils(unittest.TestCase):
    def test_is_retryable_error_retryable_statuses(self):
        """Test that retryable HTTP statuses return True."""
        retryable_statuses = [429, 500, 502, 503, 504]
        for status in retryable_statuses:
            with self.subTest(status=status):
                req = httpx.Request('GET', 'http://example.com')
                res = httpx.Response(status, request=req)
                err = httpx.HTTPStatusError('err', request=req, response=res)
                self.assertTrue(is_retryable_error(err))

    def test_is_retryable_error_non_retryable_statuses(self):
        """Test that non-retryable HTTP statuses return False."""
        non_retryable_statuses = [400, 401, 403, 404, 422]
        for status in non_retryable_statuses:
            with self.subTest(status=status):
                req = httpx.Request('GET', 'http://example.com')
                res = httpx.Response(status, request=req)
                err = httpx.HTTPStatusError('err', request=req, response=res)
                self.assertFalse(is_retryable_error(err))

    def test_is_retryable_error_other_exceptions(self):
        """Test that non-HTTPStatusError exceptions return False."""
        req = httpx.Request('GET', 'http://example.com')
        exceptions = [
            ValueError("value error"),
            httpx.TimeoutException("timeout", request=req),
            httpx.ConnectError("connect error", request=req),
        ]
        for exc in exceptions:
            with self.subTest(exception=type(exc).__name__):
                self.assertFalse(is_retryable_error(exc))

if __name__ == "__main__":
    unittest.main()
