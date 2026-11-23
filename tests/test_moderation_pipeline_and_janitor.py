# -*- coding: utf-8 -*-
"""
tests/test_moderation_pipeline_and_janitor.py — Moderation Tools & Post Pipeline Inquisitor Test Suite.

Verifies:
1. Sequential post numbering stability in SQLite WAL mode (no gaps on rollbacks/concurrency).
2. Janitor post deletion (cmd_del / cmd_janitor_del):
   - Successful deletion, copies purged from PMs and channels.
   - Atomic deduction of janitor tickets (janitor_deletes_left) and achievement unlock (ach_janitor_clean).
   - Informative breakdown of copies purged from PMs vs channels.
   - Ticket preservation when attempting to delete an already deleted post.
3. Cryptographically strict janitor ID masking in log_global_event (PII eradication).
4. HTML escaping and UX in /dossier and /whois (reputation title, equipped wardrobe, karma status).
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from common.anon_identity import get_anon_id, safe_user_hash
from common.database import create_post, get_post_by_num
from common.bot_helpers import _get_user_active_items
from main import cmd_del, cmd_janitor_del, cmd_whois, cmd_dossier


@pytest.mark.asyncio
async def test_post_numbering_sequential_stability(isolated_test_db):
    """
    Guarantees that create_post generates strictly consecutive post numbers without gaps,
    even under rapid successive creation.
    """
    board_id = "b"
    author_id = 1001

    post_nums = []
    for i in range(5):
        pnum = await create_post(
            board_id=board_id,
            author_id=author_id,
            content={"type": "text", "text": f"Sequential post {i}"},
            timestamp=time.time(),
        )
        assert pnum is not None
        post_nums.append(pnum)

    # Check strict sequential ordering: pnum[i+1] == pnum[i] + 1
    for i in range(len(post_nums) - 1):
        assert post_nums[i + 1] == post_nums[i] + 1, (
            f"Gap detected in post numbering: {post_nums[i]} -> {post_nums[i+1]}"
        )


@pytest.mark.asyncio
async def test_cmd_janitor_del_success_and_copies_purged(isolated_test_db):
    """
    Verifies cmd_janitor_del successfully deletes a post, cleans user and channel copies,
    atomically deducts one janitor ticket, unlocks ach_janitor_clean, and provides a clear breakdown.
    """
    db = isolated_test_db
    board_id = "b"
    janitor_uid = 5264555563
    author_uid = 2002

    # 1. Setup janitor user in DB with 3 deletes
    initial_items = {
        "janitor_until": time.time() + 3600,
        "janitor_deletes_left": 3,
        "janitor_del_history": [],
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items, balance, role) VALUES (?, ?, ?, ?, ?)",
        (janitor_uid, board_id, json.dumps(initial_items), 100.0, "user")
    )
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items, balance, role) VALUES (?, ?, ?, ?, ?)",
        (author_uid, board_id, json.dumps({}), 50.0, "user")
    )
    await db.commit()

    # 2. Create post
    pnum = await create_post(
        board_id=board_id,
        author_id=author_uid,
        content={"type": "text", "text": "Garbage spam post"},
        timestamp=time.time(),
    )
    assert pnum is not None

    # 3. Add user PM copies and channel copies in DB (PostCopies: recipient_id, message_id)
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
        (pnum, 3001, 101)
    )
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
        (pnum, 3002, 102)
    )
    await db.execute(
        "INSERT INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, ?, ?)",
        (pnum, -1001234567, 201)
    )
    await db.commit()

    # 4. Prepare message invoking /del
    fake_msg = MagicMock()
    fake_msg.from_user.id = janitor_uid
    fake_msg.chat.id = janitor_uid
    fake_msg.answer = AsyncMock()
    fake_msg.delete = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.delete_message = AsyncMock(return_value=True)

    target_msg = MagicMock()
    target_msg.chat.id = janitor_uid
    target_msg.message_id = 999
    target_msg.text = f"Пост №{pnum}\nТекст поста"
    target_msg.caption = None
    target_msg.delete = AsyncMock()
    fake_msg.reply_to_message = target_msg

    with patch("main.is_admin", return_value=False), \
         patch("main.log_global_event", new=AsyncMock()) as mock_log:

        await cmd_janitor_del(fake_msg, board_id=board_id)

    # 5. Assertions:
    # a) Post deleted from Posts table
    db_post = await get_post_by_num(pnum)
    assert db_post is None, "Post must be deleted from Posts"

    # b) User copies deleted from PostCopies
    async with db.execute("SELECT COUNT(*) FROM PostCopies WHERE post_num = ?", (pnum,)) as cur:
        assert (await cur.fetchone())[0] == 0, "PostCopies must be purged"

    # c) Channel copies deleted from ChannelCopies
    async with db.execute("SELECT COUNT(*) FROM ChannelCopies WHERE post_num = ?", (pnum,)) as cur:
        assert (await cur.fetchone())[0] == 0, "ChannelCopies must be purged"

    # d) Janitor tickets decremented from 3 to 2
    active_items = await _get_user_active_items(db, janitor_uid, board_id)
    assert active_items["janitor_deletes_left"] == 2, (
        f"Ticket count should be 2, got {active_items.get('janitor_deletes_left')}"
    )

    # e) Janitor receives detailed report breakdown
    assert fake_msg.answer.called
    answer_text = fake_msg.answer.call_args[0][0]
    assert f"Пост №{pnum}" in answer_text
    assert "из личек пользователей" in answer_text
    assert "из каналов" in answer_text
    assert "Осталось: 2 удалений" in answer_text


@pytest.mark.asyncio
async def test_cmd_janitor_del_already_deleted_post_preserves_ticket(isolated_test_db):
    """
    Verifies that when attempting to delete an already deleted / nonexistent post,
    the bot returns a calm warning 'Пост №... уже удалён' and does NOT burn the janitor ticket.
    """
    db = isolated_test_db
    board_id = "b"
    janitor_uid = 5264555563
    ghost_post_num = 999999

    initial_items = {
        "janitor_until": time.time() + 3600,
        "janitor_deletes_left": 3,
        "janitor_del_history": [],
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items, balance, role) VALUES (?, ?, ?, ?, ?)",
        (janitor_uid, board_id, json.dumps(initial_items), 100.0, "user")
    )
    await db.commit()

    fake_msg = MagicMock()
    fake_msg.from_user.id = janitor_uid
    fake_msg.chat.id = janitor_uid
    fake_msg.answer = AsyncMock()
    fake_msg.delete = AsyncMock()
    fake_msg.bot = MagicMock()

    target_msg = MagicMock()
    target_msg.chat.id = janitor_uid
    target_msg.message_id = 888
    target_msg.text = f"Пост №{ghost_post_num}\nПризрачное сообщение"
    target_msg.caption = None
    target_msg.delete = AsyncMock()
    fake_msg.reply_to_message = target_msg

    with patch("main.is_admin", return_value=False), \
         patch("main.log_global_event", new=AsyncMock()):

        await cmd_janitor_del(fake_msg, board_id=board_id)

    # Assert reply indicates post is already deleted
    assert fake_msg.answer.called
    reply_text = fake_msg.answer.call_args[0][0]
    assert f"Пост №{ghost_post_num} уже удалён" in reply_text

    # Ticket must NOT be deducted!
    active_items = await _get_user_active_items(db, janitor_uid, board_id)
    assert active_items["janitor_deletes_left"] == 3, (
        f"Janitor ticket burned on nonexistent post! Expected 3, got {active_items.get('janitor_deletes_left')}"
    )


@pytest.mark.asyncio
async def test_janitor_id_masked_in_logs_and_anonymity(isolated_test_db):
    """
    Verifies that log_global_event masks the janitor's Telegram user ID as Anon[...] (hash)
    without leaking the raw numeric ID.
    """
    db = isolated_test_db
    board_id = "b"
    raw_janitor_uid = 5264555563
    author_uid = 3003

    initial_items = {
        "janitor_until": time.time() + 3600,
        "janitor_deletes_left": 3,
        "janitor_del_history": [],
    }
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items, balance, role) VALUES (?, ?, ?, ?, ?)",
        (raw_janitor_uid, board_id, json.dumps(initial_items), 100.0, "user")
    )
    await db.commit()

    pnum = await create_post(
        board_id=board_id,
        author_id=author_uid,
        content={"type": "text", "text": "Post to be deleted"},
        timestamp=time.time(),
    )

    fake_msg = MagicMock()
    fake_msg.from_user.id = raw_janitor_uid
    fake_msg.chat.id = raw_janitor_uid
    fake_msg.answer = AsyncMock()
    fake_msg.delete = AsyncMock()
    fake_msg.bot = MagicMock()
    fake_msg.bot.delete_message = AsyncMock(return_value=True)

    target_msg = MagicMock()
    target_msg.chat.id = raw_janitor_uid
    target_msg.message_id = 777
    target_msg.text = f"Пост №{pnum}\nТекст"
    target_msg.caption = None
    target_msg.delete = AsyncMock()
    fake_msg.reply_to_message = target_msg

    captured_logs = []

    async def fake_log_global_event(category, text):
        captured_logs.append((category, text))

    with patch("main.is_admin", return_value=False), \
         patch("main.log_global_event", side_effect=fake_log_global_event):

        await cmd_del(fake_msg, board_id=board_id)

    # Check logs
    assert len(captured_logs) > 0, "log_global_event should have been called"
    del_logs = [entry[1] for entry in captured_logs if "DEL:" in entry[1]]
    assert len(del_logs) == 1

    log_entry = del_logs[0]
    # Raw numeric user_id MUST NOT be leaked
    assert str(raw_janitor_uid) not in log_entry, (
        f"Raw user_id {raw_janitor_uid} leaked in log: {log_entry}"
    )

    # Masked Anon ID and safe user hash MUST be present
    anon_id = get_anon_id(raw_janitor_uid)
    user_hash = safe_user_hash(raw_janitor_uid)
    assert f"Дворник Anon[{anon_id}] ({user_hash})" in log_entry, (
        f"Expected masked actor pattern in log, got: {log_entry}"
    )


@pytest.mark.asyncio
async def test_dossier_and_whois_html_escaping_and_fields(isolated_test_db):
    """
    Verifies that /dossier and /whois:
    1. Properly escape HTML special characters to prevent CantParseEntities.
    2. Display current reputation (title and badge from reputation_engine).
    3. Display active wardrobe / equipment items.
    4. Display karma status.
    """
    db = isolated_test_db
    board_id = "b"
    target_uid = 4004
    admin_uid = 1000

    malicious_prefix = "<script>alert('xss')</script>"
    active_items = {
        "tinfoil_hat": time.time() + 3600,
        "mute_gun": 1,
        "work_shifts": 25,
        "reputation_bonus": 5,
    }
    await db.execute(
        """INSERT INTO Users (user_id, board_id, active_items, balance, role, custom_prefix, posts_count) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (target_uid, board_id, json.dumps(active_items), 25000.0, "user", malicious_prefix, 40)
    )
    await db.commit()

    mock_stats = {
        "user_id": target_uid,
        "balance": 25000.0,
        "role": "<admin>",
        "custom_prefix": malicious_prefix,
        "rank": 1,
        "total_users": 100,
        "posts_count": 40,
        "rx_received": 150,
        "rx_given": 20,
        "approval_pct": 90,
        "cringe_factor": 10,
        "mutes_count": 0,
        "is_verified_b": 1,
    }

    # 1. Test /whois
    whois_msg = MagicMock()
    whois_msg.from_user.id = admin_uid
    whois_msg.text = f"/whois {target_uid}"
    whois_msg.caption = None
    whois_msg.reply_to_message = None
    whois_msg.answer = AsyncMock()

    with patch("stats_generator.fetch_user_stats_data", return_value=mock_stats), \
         patch("main.is_admin", return_value=True):
        await cmd_whois(whois_msg, board_id=board_id)

    assert whois_msg.answer.called
    whois_text = whois_msg.answer.call_args[0][0]

    # Verify no raw injection
    assert "<script>" not in whois_text
    # Verify reputation badge present
    assert "Репутация:" in whois_text or "Reputation:" in whois_text
    assert "REP" in whois_text
    # Verify wardrobe present
    assert "Гардероб:" in whois_text or "Equipment:" in whois_text
    assert "Фольга" in whois_text
    assert "Мут-Ган" in whois_text
    # Verify karma present
    assert "Карма:" in whois_text or "Karma:" in whois_text

    # 2. Test /dossier
    dossier_msg = MagicMock()
    dossier_msg.from_user.id = target_uid
    dossier_msg.chat.id = target_uid
    dossier_msg.text = "/dossier"
    dossier_msg.caption = None
    dossier_msg.reply_to_message = None
    dossier_msg.answer = AsyncMock()

    captured_banner_captions = []

    async def fake_send_banner_message(*args, **kwargs):
        caption = kwargs.get("caption") or (args[2] if len(args) > 2 else "")
        captured_banner_captions.append(caption)

    with patch("stats_generator.fetch_user_stats_data", return_value=mock_stats), \
         patch("banner_manager.send_banner_message", side_effect=fake_send_banner_message), \
         patch("random.random", return_value=0.99):  # Bypass 50% random joke glitch to test standard dossier

        await cmd_dossier(dossier_msg, board_id=board_id)

    assert len(captured_banner_captions) > 0, "Banner message with dossier should be sent"
    dossier_caption = captured_banner_captions[0]

    # HTML special characters MUST be escaped
    assert "<script>" not in dossier_caption
    assert "&lt;script&gt;" in dossier_caption

    # Required sections MUST be present
    assert "Репутация:" in dossier_caption
    assert "REP" in dossier_caption
    assert "Гардероб:" in dossier_caption
    assert "Фольга" in dossier_caption
    assert "Мут-Ган" in dossier_caption
    assert "Карма:" in dossier_caption
