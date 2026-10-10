import pytest
import hmac
import hashlib
import time
import os
import io
from urllib.parse import urlencode
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile

from site_tgach.security import (
    verify_telegram_webapp_data,
    is_safe_url,
    ALLOWED_IMPORT_DOMAINS,
)
from site_tgach.image_processing import process_and_upload_image
from common.database import search_posts


def test_tma_auth_with_bot_token(monkeypatch):
    test_token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    monkeypatch.setenv("BOT_TOKEN", test_token)

    auth_date = int(time.time())
    user_str = '{"id": 999888, "first_name": "Anon"}'
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohD9...",
        "user": user_str,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", test_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    params["hash"] = calc_hash
    init_data = urlencode(params)

    # 1. Valid token matches
    parsed = verify_telegram_webapp_data(init_data)
    assert parsed is not None
    assert parsed["user"] == user_str

    # 2. Tampered hash fails
    params_tampered = dict(params)
    params_tampered["hash"] = "deadbeef12345678"
    assert verify_telegram_webapp_data(urlencode(params_tampered)) is None

    # 3. Expired timestamp fails
    params_expired = dict(params)
    params_expired["auth_date"] = str(auth_date - 90000)
    data_check_expired = "\n".join(f"{k}={v}" for k, v in sorted(params_expired.items()) if k != "hash")
    calc_hash_expired = hmac.new(secret_key, data_check_expired.encode("utf-8"), hashlib.sha256).hexdigest()
    params_expired["hash"] = calc_hash_expired
    assert verify_telegram_webapp_data(urlencode(params_expired)) is None


def test_ssrf_validator():
    # Dangerous endpoints must be blocked
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://127.0.0.1:8000/admin")
    assert not is_safe_url("http://localhost:8000/api")
    assert not is_safe_url("http://0.0.0.0/")
    assert not is_safe_url("http://10.0.0.1/secret")
    assert not is_safe_url("http://192.168.1.1/router")
    assert not is_safe_url("http://172.16.0.1/cloud")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("gopher://127.0.0.1:6379/")
    assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")

    # Valid imageboard endpoints must be allowed
    assert is_safe_url("https://2ch.hk/b/res/123.json")
    assert is_safe_url("https://a.4cdn.org/b/thread/123.json")

    # Domain restriction checking
    assert is_safe_url("https://2ch.hk/b/res/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
    assert is_safe_url("https://a.4cdn.org/b/thread/123.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)
    assert not is_safe_url("https://attacker-site.com/evil.json", allowed_domains=ALLOWED_IMPORT_DOMAINS)


@pytest.mark.asyncio
async def test_process_and_upload_image_none_content_type():
    # Create fake upload file with content_type=None
    dummy_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
    file_obj = io.BytesIO(dummy_bytes)
    upload = UploadFile(file=file_obj, filename="test.jpg")
    upload.headers = {}
    assert upload.content_type is None

    mock_bot = MagicMock()
    mock_sent = MagicMock()
    mock_doc = MagicMock()
    mock_doc.file_id = "test_fid_123"
    mock_doc.thumbnail = None
    mock_photo = MagicMock()
    mock_photo.file_id = "test_fid_123"
    mock_sent.photo = [mock_photo]
    mock_sent.document = mock_doc
    mock_sent.message_id = 100
    mock_bot.send_photo = AsyncMock(return_value=mock_sent)
    mock_bot.send_document = AsyncMock(return_value=mock_sent)

    # Must not raise AttributeError: 'NoneType' object has no attribute 'startswith'
    res = await process_and_upload_image(
        file=upload,
        max_size_bytes=10 * 1024 * 1024,
        bot=mock_bot,
        channel_id=-100123456789,
    )
    assert res is not None
    assert "original_file_id" in res or "banned" in res or "dedup_found" in res


@pytest.mark.asyncio
async def test_search_posts_parameterization(isolated_test_db):
    # Test that search_posts executes safely with parameterized viewer_id and without acquiring write locks
    results = await search_posts("test", board_id="b", limit=10, observer_id=12345)
    assert isinstance(results, list)

    # Test with special characters in query
    results_special = await search_posts('foo"bar; DROP TABLE Posts;--', observer_id=0)
    assert isinstance(results_special, list)
