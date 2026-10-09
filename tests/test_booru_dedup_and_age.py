import sys
import asyncio
from unittest.mock import patch

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\danat\Desktop\dvachbot")

from japanese_translator import (
    BOORU_MIN_YEAR,
    BOORU_MIN_TIMESTAMP,
    SAFEBOORU_MIN_ID,
    _post_is_too_old,
    is_image_recent,
    record_served_image,
    LOLI_IMAGE_NEGATIVE_TAGS,
)

print("--- 1. Testing Age Constants ---")
assert BOORU_MIN_YEAR == 2012
assert BOORU_MIN_TIMESTAMP == 1325376000
assert SAFEBOORU_MIN_ID == 750000
print("✅ Constants verified.")

print("--- 2. Testing _post_is_too_old ---")
# Safebooru tests
old_safebooru_id = {'id': 700000, 'change': 1320000000}
new_safebooru_id = {'id': 7500000, 'change': 1790000000}
assert _post_is_too_old(old_safebooru_id, 'safebooru') is True, "Old safebooru ID should be rejected"
assert _post_is_too_old(new_safebooru_id, 'safebooru') is False, "New safebooru ID should be accepted"

old_safebooru_ts = {'id': 900000, 'change': 1300000000}
assert _post_is_too_old(old_safebooru_ts, 'safebooru') is True, "Old timestamp should be rejected"

# Yande.re / Konachan tests (created_at timestamp)
old_yandere = {'created_at': 1300000000} # 2011
new_yandere = {'created_at': 1700000000} # 2023
assert _post_is_too_old(old_yandere, 'yande.re') is True, "Old yandere post should be rejected"
assert _post_is_too_old(new_yandere, 'yande.re') is False, "New yandere post should be accepted"

# Danbooru / Gelbooru date string tests
old_danbooru = {'created_at': '2010-05-20T12:00:00.000+09:00'}
new_danbooru = {'created_at': '2023-01-15T12:00:00.000+09:00'}
assert _post_is_too_old(old_danbooru, 'danbooru') is True, "2010 Danbooru post should be rejected"
assert _post_is_too_old(new_danbooru, 'danbooru') is False, "2023 Danbooru post should be accepted"
print("✅ _post_is_too_old passed all tests.")

print("--- 3. Testing Deduplication Cache ---")
test_url = "https://example.com/image_123.jpg"
test_hash = "abcdef1234567890"

assert is_image_recent(url=test_url) is False
assert is_image_recent(content_hash=test_hash) is False

record_served_image(url=test_url, content_hash=test_hash)

assert is_image_recent(url=test_url) is True
assert is_image_recent(content_hash=test_hash) is True
assert is_image_recent(url="https://example.com/other.jpg") is False
print("✅ is_image_recent and record_served_image verified.")

print("--- 4. Testing Negative Tags ---")
expected_tags = {"-lowres", "-sketch", "-comic", "-monochrome", "-bad_anatomy", "-screencap"}
assert expected_tags.issubset(set(LOLI_IMAGE_NEGATIVE_TAGS)), f"Missing quality tags in LOLI_IMAGE_NEGATIVE_TAGS: {LOLI_IMAGE_NEGATIVE_TAGS}"
print("✅ Quality tags present in LOLI_IMAGE_NEGATIVE_TAGS.")

print("--- 5. Testing _collect_stacked_anime_downloads In-Batch Dedup & Full Refill ---")
from main import _collect_stacked_anime_downloads

import pytest

@pytest.mark.asyncio
async def test_collect_refill():
    urls = [
        "https://example.com/pic1.jpg",
        "https://example.com/pic1.jpg", # Duplicate in batch!
        "https://example.com/pic2.jpg",
    ]
    replacement_urls = [
        "https://example.com/pic3_replacement.jpg",
        "https://example.com/pic4_replacement.jpg",
    ]

    async def mock_fetcher():
        if urls:
            return urls.pop(0)
        if replacement_urls:
            return replacement_urls.pop(0)
        return "https://example.com/final_fallback.jpg"

    dummy_bytes = b"JPEG_BYTES_UNIQUE_"
    async def mock_downloader(urls_to_download, board_id, user_id, source):
        results = []
        for i, u in enumerate(urls_to_download):
            b = dummy_bytes + u.encode('utf-8')
            results.append((i, u, (b,)))
        return results

    tasks = [mock_fetcher, mock_fetcher, mock_fetcher]
    with patch("main._run_bounded_anime_downloads", side_effect=mock_downloader):
        res = await _collect_stacked_anime_downloads(tasks, "b", 12345, "test")
        print(f"Collected items: {len(res)} (expected 3)")
        assert len(res) == 3, f"Expected 3 unique items, got {len(res)}"
        all_payloads = [item[0] for item in res]
        assert len(set(all_payloads)) == 3, "All collected payloads must be distinct!"
        print("✅ In-batch dedup and refill successfully yielded full 3 unique images.")

if __name__ == "__main__":
    asyncio.run(test_collect_refill())
    print("\n🎉 ALL VERIFICATION TESTS PASSED 100%!")
