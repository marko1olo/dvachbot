# -*- coding: utf-8 -*-
import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from common.database import (
    create_feedback,
    get_all_feedback,
    get_unread_feedback_count,
    create_post,
    get_post_details_for_admin,
)
from common.spam_filter import (
    contains_phone_number,
    extract_phone_numbers,
    mask_phone_numbers,
    check_dox_content,
    check_phone_dox,
    is_spam_filtered,
    check_link_or_ad_spam,
    DOX_MASK_REPLACEMENT,
)
from site_tgach.main import app

try:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-feedback-test")
except Exception:
    pass

client = TestClient(app, raise_server_exceptions=False)


# ==========================================
# 1. FEEDBACK TESTS (Single Save & Deduplication)
# ==========================================

@pytest.mark.asyncio
async def test_feedback_single_save(isolated_test_db):
    """Test that a feedback message is inserted exactly once."""
    user_id = 12345
    category = "bug"
    contact = "@tester"
    message = "First unique feedback message"

    success = await create_feedback(user_id, category, contact, message)
    assert success is True

    items = await get_all_feedback(limit=10)
    assert len(items) == 1
    assert items[0]["user_id"] == user_id
    assert items[0]["category"] == category
    assert items[0]["contact"] == contact
    assert items[0]["message"] == message


@pytest.mark.asyncio
async def test_feedback_deduplication_subsequent_call(isolated_test_db):
    """Test that submitting duplicate feedback within 10s returns True without double insert."""
    user_id = 223344
    category = "suggestion"
    contact = "@duper"
    message = "Duplicate feedback proposal text"

    # First submission
    res1 = await create_feedback(user_id, category, contact, message)
    assert res1 is True

    # Immediate second submission (same user, same text)
    res2 = await create_feedback(user_id, category, contact, message)
    assert res2 is True

    # Verify only 1 row in table
    items = await get_all_feedback(limit=10)
    matching = [i for i in items if i["user_id"] == user_id and i["message"] == message]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_feedback_concurrent_gather_deduplication(isolated_test_db):
    """Simulate parallel POST requests from duplicate frontend listeners; must save exactly once."""
    user_id = 556677
    category = "bug"
    contact = "@race"
    message = "Parallel submission test message"

    # Send 2 concurrent requests
    results = await asyncio.gather(
        create_feedback(user_id, category, contact, message),
        create_feedback(user_id, category, contact, message),
    )
    assert all(results)

    items = await get_all_feedback(limit=10)
    matching = [i for i in items if i["user_id"] == user_id and i["message"] == message]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_feedback_different_messages_or_users_saved(isolated_test_db):
    """Different messages or different users should not be falsely deduplicated."""
    await create_feedback(1001, "bug", "c1", "Message A")
    await create_feedback(1001, "bug", "c1", "Message B")
    await create_feedback(1002, "bug", "c1", "Message A")

    items = await get_all_feedback(limit=10)
    assert len(items) == 3


def test_api_feedback_endpoint_deduplication(isolated_test_db):
    """Test FastAPI /api/feedback route handles deduplication cleanly."""
    payload = {
        "category": "suggestion",
        "contact": "@apiuser",
        "message": "API feedback submission deduplication test",
    }
    
    # 1st request
    r1 = client.post("/api/feedback", json=payload)
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    # 2nd immediate duplicate request
    r2 = client.post("/api/feedback", json=payload)
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok"}


# ==========================================
# 2. ANTI-DOX & PHONE NUMBER FILTER TESTS
# ==========================================

@pytest.mark.parametrize("phone_sample", [
    "+79161234567",
    "89161234567",
    "+7 (916) 123-45-67",
    "8-916-123-45-67",
    "8 (916) 123 45 67",
    "8 916 123 45 67",
    "+380501234567",
    "+380 50 123 45 67",
    "+380 (50) 123-45-67",
    "380501234567",
    "+77011234567",
    "87011234567",
    "+7 (701) 123-45-67",
    "+375291234567",
    "+375 (29) 123-45-67",
])
def test_anti_dox_phone_number_detection(phone_sample):
    """Verify various RU/UA/KZ/BY mobile number formats are detected."""
    raw_text = f"Слив уебка звоните ему {phone_sample} деанон"
    assert contains_phone_number(raw_text) is True
    
    phones = extract_phone_numbers(raw_text)
    assert len(phones) >= 1
    assert phone_sample in phones[0]


@pytest.mark.parametrize("safe_text", [
    "Дата релиза: 2026-08-28 20:00:00",
    "Номер поста #12345678 в треде",
    "Математика: 100 + 200 = 300 шекелей",
    "Локальный IP 192.168.1.1 порт 8080",
    "Хэш файла a8f9c7e6d5b4a3f2e1d0",
    "Просто обычный пост на двач без телефонов",
])
def test_anti_dox_false_positives_prevented(safe_text):
    """Verify standard text, dates, post IDs, and IPs do not trigger phone leak filter."""
    assert contains_phone_number(safe_text) is False
    assert extract_phone_numbers(safe_text) == []
    assert mask_phone_numbers(safe_text) == safe_text


def test_anti_dox_phone_masking():
    """Verify leaked phone number is cleanly replaced with ANTI-DOX label."""
    text = "Вот его телефон +79998887766 наберите и заспамьте"
    masked = mask_phone_numbers(text)
    assert "+79998887766" not in masked
    assert DOX_MASK_REPLACEMENT in masked
    assert masked == f"Вот его телефон {DOX_MASK_REPLACEMENT} наберите и заспамьте"


def test_anti_dox_check_dox_content_and_helpers():
    """Verify check_dox_content and check_phone_dox functions."""
    text = "Деанон: 89031112233"
    has_dox, masked, phones = check_dox_content(text, user_id=100, board_id="b")
    assert has_dox is True
    assert "89031112233" not in masked
    assert len(phones) == 1

    is_dox, masked_text, reason = check_phone_dox(100, "b", text)
    assert is_dox is True
    assert "Anti-Dox" in reason
    assert "89031112233" not in masked_text


def test_anti_dox_integration_with_spam_filters():
    """Verify phone numbers are caught by is_spam_filtered and check_link_or_ad_spam."""
    dox_msg = "Сливаю номер шлюхи: +380991234567"
    
    # 1. is_spam_filtered
    assert is_spam_filtered(dox_msg, "b", user_id=999) is True

    # 2. check_link_or_ad_spam
    is_spam, reason = check_link_or_ad_spam(999, "b", dox_msg)
    assert is_spam is True
    assert "Anti-Dox" in reason or "Слив" in reason


@pytest.mark.asyncio
async def test_anti_dox_create_post_auto_masking(isolated_test_db):
    """Verify create_post automatically masks leaked phone numbers in content text before DB persist."""
    author_id = 999111
    board_id = "b"
    content = {
        "text": "Слив майора: +79169998877 звоните",
        "type": "text"
    }

    pnum = await create_post(
        author_id=author_id,
        board_id=board_id,
        content=content,
        timestamp=time.time(),
        is_from_site=True,
    )
    assert pnum is not None

    # Check saved post in DB
    details = await get_post_details_for_admin(pnum)
    assert details is not None
    saved_text = details["content"]["text"]
    assert "+79169998877" not in saved_text
    assert DOX_MASK_REPLACEMENT in saved_text
