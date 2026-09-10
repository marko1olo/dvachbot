# -*- coding: utf-8 -*-
import io
import gzip
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from common.lottie_guard import (
    validate_lottie_dict,
    is_sticker_safe,
    _walk_shapes_for_exploits,
    KNOWN_CRASH_FILE_IDS,
    _SAFE_STICKERS,
    _MALICIOUS_STICKERS
)

def test_validate_lottie_dict_safe_minimal():
    valid = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {
                        "ty": "sr",
                        "pt": {"a": 0, "k": 5}  # normal 5-pointed star
                    }
                ]
            }
        ]
    }
    safe, reason = validate_lottie_dict(valid)
    assert safe is True
    assert reason == "ok"

def test_polystar_exploit_sdohbin():
    # The exact exploit vector used by 'Сдохбин'
    exploit = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {
                        "ty": "sr",
                        "pt": {"a": 0, "k": 1e+38}
                    }
                ]
            }
        ]
    }
    safe, reason = validate_lottie_dict(exploit)
    assert safe is False
    assert "Malicious Polystar point count" in reason

def test_polystar_exploit_nan_inf():
    for bad_val in [float('nan'), float('inf'), -10, 150]:
        exploit = {
            "v": "5.5.2",
            "fr": 30,
            "ip": 0,
            "op": 60,
            "w": 512,
            "h": 512,
            "layers": [
                {
                    "ty": 4,
                    "shapes": [
                        {"ty": "sr", "pt": {"k": bad_val}}
                    ]
                }
            ]
        }
        safe, reason = validate_lottie_dict(exploit)
        assert safe is False
        assert "Polystar point" in reason

def test_repeater_bomb_exploit():
    exploit = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {"ty": "rp", "c": {"k": 500}}
                ]
            }
        ]
    }
    safe, reason = validate_lottie_dict(exploit)
    assert safe is False
    assert "Malicious Repeater copy count" in reason

def test_vertex_flooding_exploit():
    exploit = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {
                        "ty": "sh",
                        "ks": {
                            "k": {
                                "v": [[0, 0]] * 4000
                            }
                        }
                    }
                ]
            }
        ]
    }
    safe, reason = validate_lottie_dict(exploit)
    assert safe is False
    assert "Excessive path vertices" in reason

def test_excessive_layers():
    exploit = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [{"ty": 4}] * 350
    }
    safe, reason = validate_lottie_dict(exploit)
    assert safe is False
    assert "Excessive layer count" in reason

def test_abnormal_dimensions_and_framerate():
    bad_dim = {"w": 5000, "h": 512, "fr": 30, "ip": 0, "op": 60, "layers": []}
    safe, reason = validate_lottie_dict(bad_dim)
    assert safe is False
    assert "Invalid canvas dimensions" in reason

    bad_fr = {"w": 512, "h": 512, "fr": 240, "ip": 0, "op": 60, "layers": []}
    safe, reason = validate_lottie_dict(bad_fr)
    assert safe is False
    assert "Abnormal framerate" in reason

@pytest.mark.asyncio
async def test_is_sticker_safe_static_webp():
    mock_bot = AsyncMock()
    mock_sticker = MagicMock()
    mock_sticker.file_id = "test_webp_file_id"
    mock_sticker.file_unique_id = "test_webp_uid"
    mock_sticker.is_animated = False
    mock_sticker.is_video = False

    safe, reason = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe is True
    assert reason == "static_webp"
    mock_bot.get_file.assert_not_called()

@pytest.mark.asyncio
async def test_is_sticker_safe_known_crash_blacklist():
    mock_bot = AsyncMock()
    mock_sticker = MagicMock()
    mock_sticker.file_id = list(KNOWN_CRASH_FILE_IDS)[0]
    mock_sticker.file_unique_id = "some_uid"

    safe, reason = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe is False
    assert "Known banned crash sticker" in reason
    mock_bot.get_file.assert_not_called()

@pytest.mark.asyncio
async def test_is_sticker_safe_animated_valid():
    valid_lottie = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [{"ty": 4, "shapes": []}]
    }
    raw_json = json.dumps(valid_lottie).encode("utf-8")
    compressed = gzip.compress(raw_json)

    mock_bot = AsyncMock()
    file_info = MagicMock()
    file_info.file_path = "stickers/valid.tgs"
    mock_bot.get_file.return_value = file_info
    mock_bot.download_file.return_value = io.BytesIO(compressed)

    mock_sticker = MagicMock()
    mock_sticker.file_id = "valid_tgs_fid_unique_123"
    mock_sticker.file_unique_id = "valid_tgs_uid_unique_123"
    mock_sticker.is_animated = True
    mock_sticker.is_video = False
    mock_sticker.file_size = len(compressed)

    safe, reason = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe is True
    assert reason == "lottie_validated_safe"

    # Subsequent check should hit memory cache immediately
    safe2, reason2 = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe2 is True
    assert reason2 == "cached_safe"

@pytest.mark.asyncio
async def test_is_sticker_safe_animated_crash_detected():
    crash_lottie = {
        "v": "5.5.2",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {"ty": "sr", "pt": {"a": 0, "k": 1e+38}}
                ]
            }
        ]
    }
    raw_json = json.dumps(crash_lottie).encode("utf-8")
    compressed = gzip.compress(raw_json)

    mock_bot = AsyncMock()
    file_info = MagicMock()
    file_info.file_path = "stickers/crash.tgs"
    mock_bot.get_file.return_value = file_info
    mock_bot.download_file.return_value = io.BytesIO(compressed)

    mock_sticker = MagicMock()
    mock_sticker.file_id = "crash_tgs_fid_unique_999"
    mock_sticker.file_unique_id = "crash_tgs_uid_unique_999"
    mock_sticker.is_animated = True
    mock_sticker.is_video = False
    mock_sticker.file_size = len(compressed)

    safe, reason = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe is False
    assert "Malicious Polystar point count" in reason

    # Cached malicious
    safe2, reason2 = await is_sticker_safe(mock_bot, mock_sticker)
    assert safe2 is False
    assert reason2 == "cached_malicious"
