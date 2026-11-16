# -*- coding: utf-8 -*-
"""
tests/test_post_headers_badges_and_banners.py — Inquisitor Red Team Test Suite
Covers:
1. post_helpers: format_header and format_thread_post_header equipped perks & badges
   (Monocle -> [⚜️ Олигарх], Crown -> 👑 / 👑👑, Luxury watch -> ⌚, properly escaped).
2. stats_generator: /passport profile card gear stats integration
   (defense, toxicity modifier, charisma/luck bonuses from wardrobe_engine).
3. banner_manager: Dimension and aspect ratio validation guard, quarantine,
   and graceful fallback on PHOTO_INVALID_DIMENSIONS.
"""

import os
import io
import json
import time
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from PIL import Image

import post_helpers
from post_helpers import format_header, format_thread_post_header, _get_author_prefix
import stats_generator
from stats_generator import UserStatsCardData, _format_text_report, draw_user_stats_card, fetch_user_stats_data
import banner_manager
from banner_manager import (
    validate_banner_dimensions,
    _get_safe_fs_input_file,
    send_banner_message,
    QUARANTINED_BANNERS,
    MAX_TELEGRAM_PHOTO_DIMENSION,
    MAX_TELEGRAM_PHOTO_RATIO,
    get_banner_file,
)


def _make_mock_db_with_row(row):
    mock_db = AsyncMock()
    mock_cursor = MagicMock()
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_cursor.fetchone = AsyncMock(return_value=row)
    mock_db.execute = MagicMock(return_value=mock_cursor)
    return mock_db


# =============================================================================
# 1. POST HEADERS, STATS & BADGES
# =============================================================================

@pytest.mark.asyncio
async def test_author_prefix_equipped_monocle():
    """Verify that equipped monocle renders promised [⚜️ Олигарх] badge."""
    user_items = {
        "equipped_face": "face_monocle",
        "face_monocle_is_permanent": True
    }
    mock_db = _make_mock_db_with_row((json.dumps(user_items), None, 0))

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)):
        prefix = await _get_author_prefix(author_id=12345, board_id="b")
        assert "[⚜️ Олигарх]" in prefix

        hdr = await format_header(board_id="b", post_num=1001, author_id=12345)
        assert "[⚜️ Олигарх]" in hdr
        assert "Пост №1001" in hdr or "Post No.1001" in hdr or "№1001" in hdr

        thread_info = {"op_id": 99999}
        th_hdr = await format_thread_post_header(board_id="b", local_post_num=5, author_id=12345, thread_info=thread_info)
        assert "[⚜️ Олигарх]" in th_hdr
        assert "5/500" in th_hdr


@pytest.mark.asyncio
async def test_author_prefix_equipped_crown_and_golden_crown():
    """Verify that hat_crown gives 👑 and hat_golden_crown gives 👑👑."""
    # Regular VIP Crown
    items_crown = {
        "equipped_head": "hat_crown",
        "hat_crown_is_permanent": True
    }
    mock_db_crown = _make_mock_db_with_row((json.dumps(items_crown), None, 0))

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db_crown)):
        prefix = await _get_author_prefix(author_id=101, board_id="b")
        assert "👑" in prefix
        hdr = await format_header(board_id="b", post_num=2002, author_id=101)
        assert "👑" in hdr

    # Golden Crown
    items_gcrown = {
        "equipped_head": "hat_golden_crown",
        "hat_golden_crown_is_permanent": True
    }
    mock_db_gcrown = _make_mock_db_with_row((json.dumps(items_gcrown), None, 0))

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db_gcrown)):
        prefix_g = await _get_author_prefix(author_id=102, board_id="b")
        assert "👑👑" in prefix_g


@pytest.mark.asyncio
async def test_author_prefix_equipped_luxury_watch():
    """Verify that luxury watch accessory gives ⌚ badge."""
    items_watch = {
        "equipped_wrist": "luxury_watch",
        "luxury_watch": True
    }
    mock_db = _make_mock_db_with_row((json.dumps(items_watch), None, 0))

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)):
        prefix = await _get_author_prefix(author_id=303, board_id="b")
        assert "⌚" in prefix


@pytest.mark.asyncio
async def test_author_prefix_combined_gear_and_html_escaping():
    """Verify that multiple gear pieces combine cleanly and custom_prefix is HTML-escaped."""
    items_combo = {
        "equipped_head": "hat_crown",
        "hat_crown_is_permanent": True,
        "equipped_face": "face_monocle",
        "face_monocle_is_permanent": True,
        "equipped_wrist": "luxury_watch",
        "badge_color": "gold",
        "badge_color_active": True
    }
    dangerous_prefix = "<script>alert('xss')</script> VIP"
    prefix_exp = int(time.time()) + 3600
    mock_db = _make_mock_db_with_row((json.dumps(items_combo), dangerous_prefix, prefix_exp))

    with patch("common.db_pool.get_pool", AsyncMock(return_value=mock_db)):
        prefix = await _get_author_prefix(author_id=555, board_id="b")
        # Check badges
        assert "👑" in prefix
        assert "[⚜️ Олигарх]" in prefix
        assert "⌚" in prefix
        assert "🟡" in prefix
        # Check HTML escaping
        assert "<script>" not in prefix
        assert "&lt;script&gt;" in prefix


@pytest.mark.asyncio
async def test_author_prefix_self_isolation_mode():
    """Verify that self-isolated users have all badges/prefixes completely hidden."""
    from shared_state import board_data
    board_data["b"] = {
        "user_settings": {
            999: {"is_isolated": True}
        }
    }
    prefix = await _get_author_prefix(author_id=999, board_id="b")
    assert prefix == ""


# =============================================================================
# 2. STATS GENERATOR & /PASSPORT GEAR STATS
# =============================================================================

def test_passport_text_report_shows_gear_stats():
    """Verify that /passport text report shows non-zero gear stats when player has wardrobe items."""
    active_items = {
        "equipped_head": "hat_helmet",
        "hat_helmet_is_permanent": True,
        "equipped_face": "face_monocle",
        "face_monocle_is_permanent": True,
        "equipped_torso": "body_sheikh_mantle",
        "body_sheikh_mantle_is_permanent": True,
        "equipped_feet": "feet_golden_sneakers",
        "feet_golden_sneakers_is_permanent": True
    }

    card_data = UserStatsCardData(
        user_id=777,
        board_id="b",
        schizo_name="Олигарх-Анон",
        role_name="VIP",
        active_items=active_items
    )

    report = _format_text_report(card_data)
    assert "Характеристики шмота:" in report
    assert "🛡️ Защита:" in report
    assert "☣️ Токсичность:" in report
    assert "🎭 Харизма:" in report
    assert "🍀 Удача:" in report
    # Total defense for helmet(45) + mantle(60) + monocle(10) + sneakers(30) = 145
    assert "+145" in report


def test_passport_draw_card_integrates_gear_stats():
    """Verify that draw_user_stats_card compiles PNG image with gear stats embedded."""
    active_items = {
        "equipped_head": "hat_golden_crown",
        "hat_golden_crown_is_permanent": True,
        "equipped_torso": "body_sheikh_mantle",
        "body_sheikh_mantle_is_permanent": True
    }

    card_data = UserStatsCardData(
        user_id=888,
        board_id="b",
        schizo_name="Царь Борды",
        role_name="Олигарх",
        active_items=active_items
    )

    buf = draw_user_stats_card(card_data, theme="gold")
    assert isinstance(buf, io.BytesIO)
    buf.seek(0)
    img = Image.open(buf)
    assert img.size == (960, 540)
    assert card_data.gear_defense > 0


def test_fetch_user_stats_data_computes_wardrobe_gear():
    """Verify that fetch_user_stats_data includes gear stats in its returned dictionary."""
    active_items = {
        "equipped_head": "hat_crown",
        "hat_crown_is_permanent": True,
        "equipped_face": "face_monocle",
        "face_monocle_is_permanent": True
    }

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.side_effect = [
        (1500.0, 'user', time.time(), '', json.dumps(active_items)),  # profile
        (0,),  # mutes count
        (5, 2),  # duel stats
    ]
    mock_cursor.fetchall.side_effect = [
        [],  # posts
        [],  # rx_given_posts
        [(999, 10)],  # board_posters
    ]

    with patch("stats_generator.connect_stats_db", return_value=mock_conn):
        stats = fetch_user_stats_data(user_id=999, board_id="b")
        assert "gear_defense" in stats
        assert "gear_toxicity" in stats
        assert "gear_charisma" in stats
        assert "gear_luck" in stats
        assert stats["gear_defense"] >= 10  # from crown and monocle
        assert "Олигарх" in stats["badges"]


# =============================================================================
# 3. BANNER MANAGER DIMENSION GUARD & CORRUPT BANNERS
# =============================================================================

def test_validate_banner_dimensions_normal_image(tmp_path):
    """Verify that valid 1920x1080 image passes validation."""
    test_img = tmp_path / "valid_banner.jpg"
    im = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
    im.save(test_img, "JPEG")

    is_valid, reason = validate_banner_dimensions(test_img)
    assert is_valid is True
    assert reason is None


def test_validate_banner_dimensions_extreme_aspect_ratio(tmp_path):
    """Verify that 850x27638px (ratio ~32.5:1) is rejected for exceeding ratio 20:1."""
    extreme_img = tmp_path / "extreme_strip.jpg"
    im = Image.new("RGB", (850, 27638), color=(255, 0, 0))
    im.save(extreme_img, "JPEG")

    is_valid, reason = validate_banner_dimensions(extreme_img)
    assert is_valid is False
    assert "Aspect ratio" in reason or "Dimension exceeds" in reason


def test_validate_banner_dimensions_oversized_single_dimension(tmp_path):
    """Verify that image with dimension > 10000px is rejected."""
    oversized_img = tmp_path / "oversized.jpg"
    im = Image.new("RGB", (10001, 800), color=(0, 255, 0))
    im.save(oversized_img, "JPEG")

    is_valid, reason = validate_banner_dimensions(oversized_img)
    assert is_valid is False
    assert "Dimension exceeds" in reason or "10000px" in reason


def test_quarantined_corrupt_banner_rejected():
    """Verify that the notorious sample_b8d5a566f74cc07816a3635c6ef08a2a.jpg is quarantined."""
    is_valid, reason = validate_banner_dimensions("sample_b8d5a566f74cc07816a3635c6ef08a2a.jpg")
    assert is_valid is False
    assert "Quarantined" in reason
    assert "sample_b8d5a566f74cc07816a3635c6ef08a2a.jpg" in QUARANTINED_BANNERS


def test_safe_fs_input_file_quarantines_extreme_or_corrupt(tmp_path):
    """Verify that _get_safe_fs_input_file does not return corrupt or unnormalizable files."""
    corrupt_file = tmp_path / "corrupt.jpg"
    with open(corrupt_file, "wb") as f:
        f.write(b"NOT_A_VALID_JPEG_HEADER_CORRUPT_BYTES")

    fs = _get_safe_fs_input_file(corrupt_file)
    assert fs is None
    assert corrupt_file.name in QUARANTINED_BANNERS


@pytest.mark.asyncio
async def test_send_banner_message_photo_invalid_dimensions_fallback():
    """
    Verify that when Telegram rejects an image with PHOTO_INVALID_DIMENSIONS,
    send_banner_message quarantines the offending file, does NOT crash unhandled,
    and cleanly falls back to text delivery with markup intact.
    """
    mock_bot = AsyncMock()
    mock_bot.id = 77777

    # send_photo throws PHOTO_INVALID_DIMENSIONS
    mock_bot.send_photo.side_effect = Exception("Bad Request: PHOTO_INVALID_DIMENSIONS")

    text_sent_msg = MagicMock()
    text_sent_msg.message_id = 123456
    mock_bot.send_message.return_value = text_sent_msg

    markup = MagicMock()
    result = await send_banner_message(
        bot=mock_bot,
        chat_id=98765,
        caption="<b>Test message with corrupt banner</b>",
        reply_markup=markup,
        banner_name="Anime_character_in_arch_pose_6483f872.jpg"
    )

    assert result == text_sent_msg
    # Verify fallback send_message was called with text and markup
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 98765
    assert call_kwargs["text"] == "<b>Test message with corrupt banner</b>"
    assert call_kwargs["reply_markup"] == markup
