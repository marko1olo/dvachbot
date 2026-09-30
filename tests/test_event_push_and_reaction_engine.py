# -*- coding: utf-8 -*-
"""
tests/test_event_push_and_reaction_engine.py — Тесты для event_push_engine и reaction_broadcast_engine.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import event_push_engine
import reaction_broadcast_engine


def test_can_push_cooldown():
    event_push_engine._user_event_cooldowns.clear()
    uid = 12345
    etype = "duel"
    
    assert event_push_engine._can_push(uid, etype) is True
    assert event_push_engine._can_push(uid, etype) is False
    
    # Different event type
    assert event_push_engine._can_push(uid, "rr") is True


def test_build_deeplink():
    link = event_push_engine._build_deeplink("@dvach_bot", "duel")
    assert link == "https://t.me/dvach_bot"


def test_build_push_message():
    msg = event_push_engine._build_push_message("duel", "ВЫЗОВ НА ДУЭЛЬ", ["Ставка: 1000", "Оппонент: Анон"])
    assert "<b>ВЫЗОВ НА ДУЭЛЬ</b>" in msg
    assert "Ставка: 1000" in msg


@pytest.mark.asyncio
async def test_push_duel_open():
    mock_bot = AsyncMock()
    mock_bot.me = MagicMock()
    mock_bot.me.username = "test_bot"
    
    with patch("event_push_engine.push_event_to_board", new_callable=AsyncMock) as mock_push:
        mock_push.return_value = 1
        event_push_engine._user_event_cooldowns.clear()
        sent = await event_push_engine.push_duel_open(
            bot=mock_bot,
            board_id="b",
            challenger_anon_id="Anon#123",
            amount=500,
            exclude_uid=111,
        )
        assert sent == 1
        assert mock_push.call_count == 1


def test_reaction_broadcast_phrases():
    phrases = reaction_broadcast_engine.REACTION_MOTIVATION_TEXTS
    assert len(phrases) >= 20
    for p in phrases:
        assert isinstance(p, str)
        assert len(p) > 20


@pytest.mark.asyncio
async def test_reaction_broadcast_blocked_users_excluded(isolated_test_db):
    db = isolated_test_db
    # Populate Users table with 3 users
    await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (101, 'b', 50)")
    await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (202, 'b', 20)")
    await db.execute("INSERT INTO Users (user_id, board_id, posts_count) VALUES (303, 'b', 10)")
    await db.commit()

    with patch("reaction_broadcast_engine.get_pool", return_value=db), \
         patch("reaction_broadcast_engine._load_state", return_value={"blocked_user_ids": [202]}):
        recipients = await reaction_broadcast_engine.get_reaction_broadcast_recipients(exclude_blocked=True)
        assert 101 in recipients
        assert 303 in recipients
        assert 202 not in recipients
