import pytest
import os
import sys

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["DB_USER"] = "test"
os.environ["DB_PASS"] = "test"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_NAME"] = "test"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.mark.asyncio
async def test_ads_txt():
    """Test that the /ads.txt endpoint returns the expected content and status."""
    # Test the ads_txt function directly to avoid TestClient issues
    from Dubsite_tgach.main import ads_txt

    response = await ads_txt()

    # Fastapi Response defaults to 200 if not specified
    assert response.status_code == 200
    assert response.media_type == "text/plain"
    assert response.body.decode("utf-8") == "# No ads here. Go away."
