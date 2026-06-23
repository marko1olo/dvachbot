import pytest
from Dubsite_tgach.main import sitemap_xml
class MockRequest:
    base_url = "http://example.com/"

import asyncio
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_sitemap_xml():
    req = MockRequest()
    with patch('Dubsite_tgach.main.get_pool') as mock_get_pool:
        # Mocking the async iterator for the cursor
        class MockCursor:
            def __init__(self):
                self.data = [
                    ("b", "1", 123456789.0),
                    ("a", "2", 123456788.0)
                ]
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            async def __aiter__(self):
                for item in self.data:
                    yield item

        mock_db = MagicMock()
        mock_db.execute.return_value = MockCursor()
        mock_get_pool.return_value = mock_db

        # Test original implementation
        res = await sitemap_xml(req)
        assert res.status_code == 200

        content = res.body.decode('utf-8')
        assert "http://example.com/b/res/1.html" in content
        assert "http://example.com/a/res/2.html" in content
