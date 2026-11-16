# -*- coding: utf-8 -*-
"""
Red Team Regression & Verification Suite for User Feedback, Complaints & Moderation.
Verifies fixes for issues identified in dvach_bot.db user complaints & runtime logs:
1. Feedback & suggestion submission, persistence, and rapid deduplication.
2. Report rate limiting cooldown & duplicate open post report suppression.
3. Votemute background sweeping of expired sessions from SQLite.
4. Auto-snitch administrative pardon completely lifting unbribable folk mute and clearing Users.active_items.
5. Admin force-unmute command (/unmute <id> force) overriding and clearing folk mute.
6. Documentation catalog in help_text.py exposing /feedback and /suggest across RU, EN, JP.
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import types

import admin_manager
from shared_state import BOARDS
from common.database import create_feedback, get_pool
import help_text
import main
import votemute_engine


@pytest.mark.asyncio
async def test_feedback_command_persistence_and_deduplication(isolated_test_db):
    """
    Tests feedback persistence and rapid deduplication:
    - User feedback is persisted into the Feedback table.
    - Sending identical feedback immediately afterwards is deduplicated (prevents double-firing defect).
    - Different feedback messages are correctly persisted.
    - cmd_feedback_or_suggest command processes input properly and responds to user.
    """
    db = isolated_test_db
    user_id = 123456789
    category = "complaint"
    contact = "@test_anon"
    msg_text = "Board UI text input is lagging severely on mobile"

    # 1. Direct persistence via create_feedback
    saved1 = await create_feedback(user_id, category, contact, msg_text)
    assert saved1 is True

    async with db.execute("SELECT user_id, category, contact, message FROM Feedback WHERE user_id = ?", (user_id,)) as cur:
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == user_id
    assert rows[0][1] == category
    assert rows[0][2] == contact
    assert rows[0][3] == msg_text

    # 2. Rapid duplicate submission (simulating double-firing event or accidental double-tap)
    saved2 = await create_feedback(user_id, category, contact, msg_text)
    assert saved2 is True  # returns True to caller

    # Must still only be 1 record in database (deduplicated)
    async with db.execute("SELECT COUNT(*) FROM Feedback WHERE user_id = ?", (user_id,)) as cur:
        count = (await cur.fetchone())[0]
    assert count == 1, "Expected deduplication to prevent duplicate feedback row"

    # 3. New unique feedback from same user is permitted
    saved3 = await create_feedback(user_id, "suggestion", contact, "Add dark theme switcher")
    assert saved3 is True
    async with db.execute("SELECT COUNT(*) FROM Feedback WHERE user_id = ?", (user_id,)) as cur:
        count_updated = (await cur.fetchone())[0]
    assert count_updated == 2

    # 4. End-to-end test of cmd_feedback_or_suggest handler
    mock_msg = MagicMock(spec=types.Message)
    mock_msg.from_user = MagicMock()
    mock_msg.from_user.id = 999111222
    mock_msg.from_user.username = "chad_anon"
    mock_msg.text = "/suggest Add sound effects when rolling /dice"
    mock_msg.caption = None
    mock_msg.reply_to_message = None
    mock_msg.answer = AsyncMock()

    await main.cmd_feedback_or_suggest(mock_msg, board_id="b", stream="ru")
    assert mock_msg.answer.called
    answer_text = mock_msg.answer.call_args[0][0]
    assert "Спасибо!" in answer_text

    async with db.execute("SELECT category, message FROM Feedback WHERE user_id = ?", (999111222,)) as cur:
        cmd_row = await cur.fetchone()
    assert cmd_row is not None
    assert cmd_row[0] == "suggestion"
    assert "Add sound effects" in cmd_row[1]

    # 5. Empty /feedback shows help/usage instructions
    mock_empty = MagicMock(spec=types.Message)
    mock_empty.from_user = MagicMock()
    mock_empty.from_user.id = 999111222
    mock_empty.from_user.username = "chad_anon"
    mock_empty.text = "/feedback"
    mock_empty.caption = None
    mock_empty.reply_to_message = None
    mock_empty.answer = AsyncMock()

    await main.cmd_feedback_or_suggest(mock_empty, board_id="b", stream="ru")
    assert mock_empty.answer.called
    empty_answer = mock_empty.answer.call_args[0][0]
    assert "Обратная связь" in empty_answer or "/feedback" in empty_answer


@pytest.mark.asyncio
async def test_report_cooldown_and_duplicate_suppression(isolated_test_db):
    """
    Tests /report spam defense:
    - User cooldown (30 seconds) prevents spamming multiple reports in rapid succession.
    - Duplicate reports for posts already marked 'open' in Reports table are gracefully suppressed
      without calling the AI analysis pipeline.
    """
    db = isolated_test_db
    post_num = 589400
    reporter_id = 700100200
    author_id = 700200300
    chat_id = -100123456789
    target_msg_id = 4242

    # Seed Board and Post in SQLite
    await db.execute("INSERT OR IGNORE INTO Boards (board_id, name) VALUES ('b', 'Random')")
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', ?, '{}', ?)",
        (post_num, author_id, time.time())
    )
    await db.commit()

    # Link message mapping
    async with main.storage_lock:
        main.message_to_post[(chat_id, target_msg_id)] = post_num

    # Mock reported message
    mock_reported = MagicMock(spec=types.Message)
    mock_reported.chat = MagicMock()
    mock_reported.chat.id = chat_id
    mock_reported.message_id = target_msg_id
    mock_reported.text = "Spam payload"
    mock_reported.caption = None

    # Mock user report message
    mock_report_msg = MagicMock(spec=types.Message)
    mock_report_msg.bot = MagicMock()
    mock_report_msg.from_user = MagicMock()
    mock_report_msg.from_user.id = reporter_id
    mock_report_msg.reply_to_message = mock_reported
    mock_report_msg.answer = AsyncMock()

    # 1. Cooldown test: set cooldown active for reporter
    main._REPORT_USER_COOLDOWNS[reporter_id] = time.time() - 10.0  # 10s ago (< 30s)
    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_get_auth:
        mock_get_auth.return_value = author_id
        await main.cmd_report(mock_report_msg, board_id="b", stream="ru")

    assert mock_report_msg.answer.called
    cd_reply = mock_report_msg.answer.call_args[0][0]
    assert "Слишком частые репорты" in cd_reply or "сек." in cd_reply

    # 2. Cooldown expired, but post is already under open review in Reports
    main._REPORT_USER_COOLDOWNS[reporter_id] = time.time() - 40.0  # Cooldown clear
    await db.execute(
        "INSERT INTO Reports (post_num, category, reason, status, created_at) VALUES (?, 'spam', 'ad flood', 'open', ?)",
        (post_num, time.time() - 20.0)
    )
    await db.commit()

    mock_report_msg.answer.reset_mock()
    with patch("main.get_author_id_by_reply", new_callable=AsyncMock) as mock_get_auth:
        with patch("main.process_report_pipeline") as mock_pipeline:
            mock_get_auth.return_value = author_id
            await main.cmd_report(mock_report_msg, board_id="b", stream="ru")

            assert mock_report_msg.answer.called
            dup_reply = mock_report_msg.answer.call_args[0][0]
            assert "уже передан на проверку модераторам" in dup_reply
            # Verify AI pipeline was NOT invoked
            assert not mock_pipeline.called


@pytest.mark.asyncio
async def test_sweep_expired_votemutes(isolated_test_db):
    """
    Tests sweep_expired_votemutes:
    - Atomically updates status from 'active' to 'expired' for rows where expires_at <= now.
    - Active rows with expires_at in the future remain 'active'.
    - Already completed rows ('passed', 'pardoned') are not touched.
    - Synchronizes active_votemutes in-memory dictionary.
    """
    db = isolated_test_db
    now = time.time()

    # 1. Seed three test votemutes
    await db.execute(
        "INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status) "
        "VALUES ('vm_exp_1', 'b', 1001, 101, 2001, ?, ?, 'active')",
        (now - 700, now - 100)  # Expired 100s ago
    )
    await db.execute(
        "INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status) "
        "VALUES ('vm_act_2', 'b', 1002, 102, 2002, ?, ?, 'active')",
        (now - 60, now + 540)  # Active for 540s more
    )
    await db.execute(
        "INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status) "
        "VALUES ('vm_pas_3', 'b', 1003, 103, 2003, ?, ?, 'passed')",
        (now - 900, now - 300)  # Passed earlier
    )
    await db.commit()

    # Synchronize in-memory cache
    async with votemute_engine.votemute_lock:
        votemute_engine.active_votemutes.clear()
        votemute_engine.active_votemutes['vm_exp_1'] = {
            'board_id': 'b', 'target_id': 1001, 'status': 'active', 'expires_at': now - 100
        }
        votemute_engine.active_votemutes['vm_act_2'] = {
            'board_id': 'b', 'target_id': 1002, 'status': 'active', 'expires_at': now + 540
        }

    # 2. Execute sweep
    swept_count = await votemute_engine.sweep_expired_votemutes(db=db)
    assert swept_count == 1

    # 3. Verify SQLite states
    async with db.execute("SELECT vote_id, status FROM Votemutes ORDER BY vote_id") as cur:
        rows = dict(await cur.fetchall())

    assert rows['vm_exp_1'] == 'expired'
    assert rows['vm_act_2'] == 'active'
    assert rows['vm_pas_3'] == 'passed'

    # 4. Verify in-memory cache sync
    async with votemute_engine.votemute_lock:
        assert votemute_engine.active_votemutes['vm_exp_1']['status'] == 'expired'
        assert votemute_engine.active_votemutes['vm_act_2']['status'] == 'active'


@pytest.mark.asyncio
async def test_auto_snitch_pardon_lifts_unbribable_folk_mute(isolated_test_db):
    """
    Tests administrative pardon through Auto-Snitch and lift_unbribable_folk_mute:
    - User subjected to 30-min Iron Folk Mute (unbribable_votemute_until in Users.active_items,
      row in Mutes table, active session in Votemutes).
    - When admin invokes pardon, lift_unbribable_folk_mute completely clears the unbribable flag,
      removes the mute from Mutes, updates Votemutes to 'pardoned', and evicts in-memory caches.
    - check_user_unbribable_mute confirms the user is completely unmuted.
    """
    db = isolated_test_db
    target_id = 6557599214  # Real target user from database complaints
    board_id = "b"
    now = time.time()
    mute_until = int(now + 1800)

    # 1. Setup user with unbribable folk mute in Users
    active_items = {
        votemute_engine.UNBRIBABLE_FLAG_KEY: mute_until,
        "hat": "tin_foil_hat"
    }
    await db.execute(
        "INSERT OR REPLACE INTO Users (user_id, board_id, status, cursed_until, active_items) "
        "VALUES (?, ?, 'active', 0, ?)",
        (target_id, board_id, json.dumps(active_items))
    )
    # Setup Mutes row
    await db.execute(
        "INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, thread_id, expires_at, reason) "
        "VALUES (?, ?, 'mute', '', ?, 'folk_mute')",
        (target_id, board_id, mute_until)
    )
    # Setup Votemutes row
    await db.execute(
        "INSERT OR REPLACE INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status) "
        "VALUES ('vm_folk_test', ?, ?, 589429, 5264555563, ?, ?, 'active')",
        (board_id, target_id, now - 60, now + 540)
    )
    await db.commit()

    # Verify user is initially under unbribable folk mute
    is_muted, rem = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted is True
    assert rem > 0

    # 2. Execute lift_unbribable_folk_mute
    pardon_ok = await votemute_engine.lift_unbribable_folk_mute(target_id, board_id, db=db)
    assert pardon_ok is True

    # 3. Verify user is no longer in unbribable mute
    is_muted_after, rem_after = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted_after is False
    assert rem_after == 0

    # 4. Check that other active items (e.g. hat) were preserved, but UNBRIBABLE_FLAG_KEY was removed
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as cur:
        row = await cur.fetchone()
    assert row is not None and row[0] is not None
    updated_items = json.loads(row[0])
    assert votemute_engine.UNBRIBABLE_FLAG_KEY not in updated_items
    assert updated_items.get("hat") == "tin_foil_hat"

    # 5. Check that Mutes table row was deleted
    async with db.execute("SELECT COUNT(*) FROM Mutes WHERE user_id = ? AND board_id = ?", (target_id, board_id)) as cur:
        mute_count = (await cur.fetchone())[0]
    assert mute_count == 0

    # 6. Check that Votemutes status transitioned to 'pardoned'
    async with db.execute("SELECT status FROM Votemutes WHERE vote_id = 'vm_folk_test'") as cur:
        vm_status = (await cur.fetchone())[0]
    assert vm_status == 'pardoned'

    # 7. Test Auto-Snitch callback pardon path integration
    # Re-apply folk mute
    updated_items[votemute_engine.UNBRIBABLE_FLAG_KEY] = int(time.time() + 1800)
    await db.execute(
        "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
        (json.dumps(updated_items), target_id, board_id)
    )
    await db.commit()

    mock_cb = MagicMock(spec=types.CallbackQuery)
    mock_cb.data = f"snitch:pardon:{target_id}:{board_id}:589429"
    mock_cb.from_user = MagicMock()
    mock_cb.from_user.id = 111111  # Admin ID
    mock_cb.from_user.username = "head_admin"
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock()
    mock_cb.message.edit_text = AsyncMock()
    mock_cb.message.text = "Snitch Card"

    with patch("admin_manager.is_admin", return_value=True):
        with patch("site_tgach.admin_config.ADMIN_IDS", [111111]):
            await admin_manager.handle_snitch_callback(mock_cb)

    is_muted_snitch, _ = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted_snitch is False


@pytest.mark.asyncio
async def test_admin_force_unmute(isolated_test_db):
    """
    Tests /unmute with 'force' flag by administrator:
    - Normal /unmute <id> is rejected if user is under unbribable folk mute.
    - /unmute <id> force overrides folk mute, invokes lift_unbribable_folk_mute, and frees user.
    """
    db = isolated_test_db
    target_id = 99887766
    admin_id = 55443322
    board_id = "b"
    now = time.time()

    # Seed user under folk mute
    items = {votemute_engine.UNBRIBABLE_FLAG_KEY: int(now + 1800)}
    await db.execute(
        "INSERT OR REPLACE INTO Users (user_id, board_id, status, cursed_until, active_items) VALUES (?, ?, 'active', 0, ?)",
        (target_id, board_id, json.dumps(items))
    )
    await db.commit()

    main.board_data[board_id]['mutes'][target_id] = now + 1800

    # 1. Standard /unmute (without force)
    mock_msg_normal = MagicMock(spec=types.Message)
    mock_msg_normal.from_user = MagicMock()
    mock_msg_normal.from_user.id = admin_id
    mock_msg_normal.text = f"/unmute {target_id}"
    mock_msg_normal.caption = None
    mock_msg_normal.reply_to_message = None
    mock_msg_normal.answer = AsyncMock()

    with patch("main.is_admin", return_value=True):
        await main.cmd_unmute(mock_msg_normal, board_id=board_id, stream="ru")

    assert mock_msg_normal.answer.called
    normal_resp = mock_msg_normal.answer.call_args[0][0]
    assert "Этот мут наложен народом борды" in normal_resp
    assert "/unmute <id> force" in normal_resp

    # Verify user is still muted
    is_muted_still, _ = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted_still is True

    # 2. Forced /unmute <id> force
    mock_msg_force = MagicMock(spec=types.Message)
    mock_msg_force.from_user = MagicMock()
    mock_msg_force.from_user.id = admin_id
    mock_msg_force.text = f"/unmute {target_id} force"
    mock_msg_force.caption = None
    mock_msg_force.reply_to_message = None
    mock_msg_force.answer = AsyncMock()

    with patch("main.is_admin", return_value=True):
        await main.cmd_unmute(mock_msg_force, board_id=board_id, stream="ru")

    assert mock_msg_force.answer.called
    force_resp = mock_msg_force.answer.call_args[0][0]
    assert "размучен" in force_resp

    # Verify folk mute is completely lifted
    is_muted_lifted, _ = await votemute_engine.check_user_unbribable_mute(target_id, board_id)
    assert is_muted_lifted is False


def test_help_text_catalog_includes_feedback_and_suggest():
    """
    Verifies help_text documentation:
    - /feedback and /suggest are present in 'chat' and 'all' sections for RU, EN, and JP languages.
    """
    for lang in ('ru', 'en', 'jp'):
        chat_page = help_text.get_help_hub_page('chat', lang)
        assert "/feedback" in chat_page, f"Missing /feedback in chat section for lang={lang}"
        assert "/suggest" in chat_page, f"Missing /suggest in chat section for lang={lang}"

        all_page = help_text.get_help_hub_page('all', lang)
        assert "/feedback" in all_page, f"Missing /feedback in all section for lang={lang}"
        assert "/suggest" in all_page, f"Missing /suggest in all section for lang={lang}"
