import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock

sys.stdout.reconfigure(encoding='utf-8')

# Put root directory in sys.path
root_dir = r"C:\Users\danat\Desktop\dvachbot"
sys.path.insert(0, root_dir)

from fastapi.testclient import TestClient
from site_tgach.main import app

def test_r1_telegram_file_redirects():
    print("=== R1 EMPIRICAL TEST: Telegram File Redirects ===")
    
    # 1. Test direct Telegram file path cached -> should return 307 Redirect to api.telegram.org
    fake_file_id = "AgACAgIAAxkBAAI123456789"
    fake_path = "photos/file_0.jpg"
    fake_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    
    with patch("site_tgach.main.get_cached_file_path", new_callable=AsyncMock) as mock_get_cached_path, \
         patch("site_tgach.main.get_file_mirrors", new_callable=AsyncMock) as mock_get_mirrors, \
         patch("common.database.is_file_permanently_failed", new_callable=AsyncMock) as mock_failed:
        
        mock_failed.return_value = False
        mock_get_mirrors.return_value = {}
        mock_get_cached_path.return_value = (fake_path, fake_token)
        
        client = TestClient(app, follow_redirects=False)
        
        # Test endpoint /files/{file_id}
        response = client.get(f"/files/{fake_file_id}")
        
        assert response.status_code == 307, f"Expected 307 Temporary Redirect, got {response.status_code}"
        expected_url = f"https://api.telegram.org/file/bot{fake_token}/{fake_path}"
        location = response.headers.get("location")
        assert location == expected_url, f"Expected Location '{expected_url}', got '{location}'"
        assert response.headers.get("access-control-allow-origin") == "*", "CORS header missing"
        print(f"  -> /files/{fake_file_id[:10]}... correctly returned HTTP 307 Redirect to api.telegram.org")
        
        # Test alias endpoint /file/{file_id}
        response_alias = client.get(f"/file/{fake_file_id}")
        assert response_alias.status_code == 307
        assert response_alias.headers.get("location") == expected_url
        print(f"  -> /file/{fake_file_id[:10]}... alias correctly returned HTTP 307 Redirect")

        # Test external full URL path
        full_http_url = "http://example.com/test.jpg"
        response_http = client.get(f"/files/{full_http_url}")
        assert response_http.status_code == 301, f"Expected 301 for full HTTP URL, got {response_http.status_code}"
        assert response_http.headers.get("location") == "http://example.com/test.jpg"
        print(f"  -> Full HTTP URL correctly returned HTTP 301 Redirect")

    print("\n[SUCCESS] R1 TELEGRAM FILE REDIRECT TEST PASSED 100%!")

if __name__ == "__main__":
    test_r1_telegram_file_redirects()
