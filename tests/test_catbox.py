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


def test_is_catbox_available_and_cooldown():
    import time
    import site_tgach.catbox as catbox
    from site_tgach.catbox import is_catbox_available, CATBOX_PAUSE_COOLDOWN

    assert CATBOX_PAUSE_COOLDOWN == 1800
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0
    assert is_catbox_available() is True

    # When on cooldown
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = time.time() + 1000
    assert is_catbox_available() is False

    # Reset
    catbox._CATBOX_GLOBAL_DISABLED_UNTIL = 0.0
    assert is_catbox_available() is True

