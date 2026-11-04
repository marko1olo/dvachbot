import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from site_tgach.main import app
import common.database as db_mod
import common.db_pool as db_pool

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-tags")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_external_deps(isolated_test_db):
    with patch("site_tgach.main.get_country_by_ip", new_callable=AsyncMock) as mock_country:
        mock_country.return_value = "RU"
        yield mock_country


def test_tags_index_page_handles_slash_and_head():
    with patch("site_tgach.main.get_recent_tags_summary", new_callable=AsyncMock) as mock_summary:
        mock_summary.return_value = [("anime", 10), ("cat", 5)]

        # GET /tags/ (with slash)
        resp1 = client.get("/tags/")
        assert resp1.status_code == 200
        assert "text/html" in resp1.headers["content-type"]

        # GET /tags (without slash)
        resp2 = client.get("/tags")
        assert resp2.status_code == 200

        # HEAD /tags/
        resp3 = client.head("/tags/")
        assert resp3.status_code == 200

        # HEAD /tags
        resp4 = client.head("/tags")
        assert resp4.status_code == 200


def test_tag_seo_page_handles_html_suffix_and_head():
    with patch("site_tgach.main.search_files_by_tags", new_callable=AsyncMock) as mock_search, \
         patch("site_tgach.main.get_posts_by_file_ids", new_callable=AsyncMock) as mock_get_posts:
        mock_search.return_value = [{"file_id": "test_fid", "score": 1.0, "tags": "red hair"}]
        mock_get_posts.return_value = []

        # Normal tag
        resp1 = client.get("/tags/red_hair")
        assert resp1.status_code == 200
        mock_search.assert_called_with(["red_hair"], limit=60, offset=0)

        # Crawler URL with .html
        resp2 = client.get("/tags/red_hair.html")
        assert resp2.status_code == 200
        assert mock_search.call_args[0][0] == ["red_hair"]

        # Crawler URL with .htm
        resp3 = client.get("/tags/blue-sky.htm")
        assert resp3.status_code == 200
        assert mock_search.call_args[0][0] == ["blue sky"]

        # HEAD request
        resp4 = client.head("/tags/red_hair")
        assert resp4.status_code == 200


def test_search_tags_page_handles_head():
    with patch("site_tgach.main.search_files_by_tags", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        resp = client.head("/search/tags?tags=anime")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_files_by_tags_and_get_file_tags_do_not_acquire_db_lock(isolated_test_db):
    """Verifies that read-only tag queries do not acquire the global write lock db_lock."""
    db = isolated_test_db
    # Seed FileRegistry with a test row
    await db.execute(
        "INSERT INTO FileRegistry (file_id, tags, created_at) VALUES ('fid_cat', 'cat, cute', 1700000000)"
    )
    await db.commit()

    with patch.object(db_pool.db_lock, "acquire", side_effect=AssertionError("db_lock should not be acquired for reads!")):
        # 1. get_file_tags should not acquire db_lock
        tags = await db_mod.get_file_tags("fid_cat")
        assert tags == ["cat", "cute"]

        # 2. search_files_by_tags should not acquire db_lock
        res = await db_mod.search_files_by_tags(["cat"], limit=10, offset=0)
        assert isinstance(res, list)
