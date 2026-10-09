import pytest
from unittest.mock import AsyncMock, patch
from site_tgach.main import format_content_disposition, export_thread_html

def test_format_content_disposition_ascii():
    header = format_content_disposition("inline", "sample_image.png")
    assert header == 'inline; filename="sample_image.png"'
    # Starlette encodes headers to latin-1; ensure no exception
    header.encode("latin-1")

def test_format_content_disposition_unicode():
    header = format_content_disposition("attachment", "мем_тест.jpg")
    # Must contain ASCII fallback filename and UTF-8 encoded filename*
    assert 'filename=' in header
    assert "filename*=UTF-8''" in header
    # Crucial: the whole header string MUST be encodable to latin-1 (no ordinal > 255)
    encoded = header.encode("latin-1")
    assert b"%D0%BC%D0%B5%D0%BC" in encoded

def test_format_content_disposition_sanitization():
    dirty = 'evil"filename\r\nwith\x00bad_chars.png'
    header = format_content_disposition("attachment", dirty)
    assert "\r" not in header
    assert "\n" not in header
    assert "\x00" not in header
    header.encode("latin-1")

def test_format_content_disposition_empty():
    header = format_content_disposition("inline", "")
    assert header == 'inline; filename="file"'
    header = format_content_disposition("attachment", None)
    assert header == 'attachment; filename="file"'

@pytest.mark.asyncio
async def test_export_thread_html_with_files_escaping():
    """Verify export_thread_html executes html.escape without list collision."""
    mock_op = {
        "post_num": 12345,
        "board_id": "b",
        "thread_id": None,
        "created_at": 1700000000,
        "content": {
            "text": "Hello <world> & 'test'",
            "files": [
                {
                    "original_file_id": "https://example.com/file&quote.jpg",
                    "thumbnail_url": "https://example.com/thumb.jpg"
                }
            ]
        }
    }
    mock_reply = {
        "post_num": 12346,
        "board_id": "b",
        "thread_id": 12345,
        "reply_to_post_num": 12345,
        "created_at": 1700000100,
        "content": {
            "text": ">>12345 answer",
            "files": []
        }
    }

    with patch("site_tgach.main.BOARD_CONFIG", {"b": {}}), \
         patch("site_tgach.main.get_thread_op_by_post_num", AsyncMock(return_value=12345)), \
         patch("site_tgach.main.get_thread_by_op_post", AsyncMock(return_value=(mock_op, [mock_reply]))):
        response = await export_thread_html("b", 12345)
        assert response.status_code == 200
        body = response.body.decode("utf-8")
        assert "Тред #12345" in body
        assert "file&amp;quote.jpg" in body
        assert "Content-Disposition" in response.headers
