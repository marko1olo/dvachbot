import pytest
import os
import sys
import logging
from unittest.mock import patch, MagicMock


def test_site_safe_rotating_file_handler(tmp_path):
    """Bug 1: SafeRotatingFileHandler suppresses PermissionError / OSError on rollover."""
    from site_tgach.main import SafeRotatingFileHandler

    log_file = tmp_path / "test_site.log"
    handler = SafeRotatingFileHandler(str(log_file), maxBytes=100, backupCount=2, encoding="utf-8")

    # Mock doRollover to raise PermissionError [WinError 32]
    with patch("logging.handlers.RotatingFileHandler.doRollover", side_effect=PermissionError(32, "The process cannot access the file")):
        handler.doRollover()

    with patch("logging.handlers.RotatingFileHandler.doRollover", side_effect=OSError("File locked")):
        handler.doRollover()

    handler.close()


def test_site_public_url_and_media_helpers():
    """Bug 2: _site_public_url, _site_file_source, _site_file_send_type work across modules."""
    import common.config as cfg
    from archive_manager import _site_public_url, _site_file_source, _site_file_send_type
    import delivery_manager
    import main

    assert hasattr(cfg, "SITE_PUBLIC_BASE_URL")
    base_url = cfg.SITE_PUBLIC_BASE_URL

    # Test _site_public_url
    assert _site_public_url(None) is None
    assert _site_public_url("") is None
    assert _site_public_url("https://example.com/img.jpg") == "https://example.com/img.jpg"
    assert _site_public_url("/files/image.png") == f"{base_url}/files/image.png"
    assert _site_public_url("files/image.png") == f"{base_url}/files/image.png"

    # Test delivery_manager and main exports
    assert hasattr(delivery_manager, "_site_public_url")
    assert hasattr(main, "_site_public_url")
    assert hasattr(delivery_manager, "_site_file_source")
    assert hasattr(main, "_site_file_source")
    assert hasattr(delivery_manager, "_site_file_send_type")

    # Test _site_file_send_type
    assert _site_file_send_type({"type": "image", "filename": "pic.jpg"}) == "photo"
    assert _site_file_send_type({"type": "video", "filename": "video.mp4"}) == "video"
    assert _site_file_send_type({"type": "gif", "filename": "anim.gif"}) == "animation"

    # Test _site_file_source
    file_info = {"original_file_id": "tg_file_123", "original_url": "/files/pic.jpg"}
    assert _site_file_source(file_info, prefer_url=False) == "tg_file_123"
    assert _site_file_source(file_info, prefer_url=True) == f"{base_url}/files/pic.jpg"

    # Test _site_media_item in delivery_manager
    media_item = delivery_manager._site_media_item({"type": "photo", "original_file_id": "file_123", "filename": "a.jpg"})
    assert media_item is not None
    assert media_item["type"] == "photo"
    assert media_item["file_id"] == "file_123"


def test_media_utils_cv2_optional():
    """Bug 3: media_utils has optional cv2 import and safe Pillow fallback."""
    import media_utils

    assert hasattr(media_utils, "cv2")
    assert media_utils.cv2 is None or hasattr(media_utils.cv2, "__name__")

    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    result = media_utils._resize_image_if_needed(img_bytes)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_shared_state_drop_and_trim_copy_maps():
    """Bug 4: _drop_post_copy_maps_unlocked and _trim_post_copy_maps_unlocked work and are exported."""
    import shared_state
    from shared_state import (
        _drop_post_copy_maps_unlocked,
        _trim_post_copy_maps_unlocked,
        _trim_messages_storage_unlocked,
        post_to_messages,
        message_to_post,
        messages_storage,
    )
    import broadcaster

    assert hasattr(broadcaster, "_drop_post_copy_maps_unlocked")
    assert hasattr(broadcaster, "_trim_post_copy_maps_unlocked")

    test_post_num = 99999999
    post_to_messages[test_post_num] = {101: 5001, 102: [5002, 5003]}
    message_to_post[(101, 5001)] = test_post_num
    message_to_post[(102, 5002)] = test_post_num
    message_to_post[(102, 5003)] = test_post_num

    removed = _drop_post_copy_maps_unlocked(test_post_num)
    assert removed == 3
    assert test_post_num not in post_to_messages
    assert (101, 5001) not in message_to_post

    post_to_messages[888881] = {101: 1}
    post_to_messages[888882] = {101: 2}
    trimmed_posts, trimmed_refs = _trim_post_copy_maps_unlocked(1)
    assert trimmed_posts >= 1


def test_japanese_translator_anime_safety_negative_tags():
    """Bug 5: ANIME_SAFETY_NEGATIVE_TAGS is defined and valid in japanese_translator."""
    import japanese_translator

    assert hasattr(japanese_translator, "ANIME_SAFETY_NEGATIVE_TAGS")
    tags = japanese_translator.ANIME_SAFETY_NEGATIVE_TAGS
    assert isinstance(tags, (list, tuple, set))
    assert len(tags) > 0
    tags_str = " ".join(str(t) for t in tags)
    assert "-shota" in tags_str
    assert "-guro" in tags_str
    assert "-gore" in tags_str
