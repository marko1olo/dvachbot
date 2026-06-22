import pytest
import httpx
from site_tgach.catbox import _is_invalid_uploader

def test_is_invalid_uploader_lowercase():
    resp = httpx.Response(200, text="invalid uploader")
    assert _is_invalid_uploader(resp) is True

def test_is_invalid_uploader_mixed_case():
    resp = httpx.Response(200, text="InVaLiD UpLoAdEr")
    assert _is_invalid_uploader(resp) is True

def test_is_invalid_uploader_banned_lowercase():
    resp = httpx.Response(200, text="user is banned")
    assert _is_invalid_uploader(resp) is True

def test_is_invalid_uploader_banned_uppercase():
    resp = httpx.Response(200, text="USER IS BANNED")
    assert _is_invalid_uploader(resp) is True

def test_is_invalid_uploader_valid_text():
    resp = httpx.Response(200, text="https://files.catbox.moe/abcde.jpg")
    assert _is_invalid_uploader(resp) is False
