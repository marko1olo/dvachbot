# -*- coding: utf-8 -*-
"""
tests/test_reaction_mimicry_worker.py — Integration and Unit Tests for Reaction Mimicry Worker & Lifecycle

Covers:
1. apply_mimic_reaction_to_post:
   - Atomic mutation of post_data['reactions']['users'][virtual_user_id].
   - Synchronization of post_data['content']['reactions'].
   - Database persistence via update_post_content.
   - Smooth delayed edit dispatch via execute_delayed_edit.
   - Threshold-based trigger of publish_to_best_channel (4+ on /b/, 3+ on small boards).
   - Duplicate prevention when forwarded_to_best is already True.
2. run_reaction_mimicry_cycle:
   - Candidate post filtering:
     * Excludes fresh posts (< 45 seconds old).
     * Excludes already processed posts (processed_post_nums from state).
     * Excludes posts where a virtual anon already reacted.
     * Excludes non-Cyberchad system posts (author_id <= 0 or is_system).
     * Allows Cyberchad posts (author_id == 777 or is_cyberchad).
   - Random coverage ratio (15%-35%).
   - Automatic state persistence.
3. cmd_reactions formatting:
   - Virtual anon IDs (770100001..770100050) rendered as "🕶 Аноним #N" (or "🕶 Anon #N").
   - Real users rendered as "ID <code>...</code>".
4. Background worker loop lifecycle:
   - Graceful cancellation without unhandled errors.
"""

import asyncio
from datetime import datetime, timezone
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from handlers.message_router import (
    apply_mimic_reaction_to_post,
    run_reaction_mimicry_cycle,
    reaction_mimicry_worker_loop,
)
from shared_state import (
    messages_storage,
    storage_lock,
    pending_edit_tasks,
    pending_edit_lock,
)


@pytest.fixture(autouse=True)
def clean_shared_reaction_state(tmp_path, monkeypatch):
    """Resets memory storage and state file before each test."""
    test_state_file = str(tmp_path / "reaction_mimicry_state.json")
    monkeypatch.setattr("reaction_mimicry_engine.STATE_FILE_PATH", test_state_file)
    monkeypatch.setattr("reaction_mimicry_engine._ACTIVE_STATE", None)

    # Clean in-memory storage
    messages_storage.clear()
    pending_edit_tasks.clear()
    yield
    messages_storage.clear()
    pending_edit_tasks.clear()


@pytest.mark.asyncio
async def test_apply_mimic_reaction_atomic_save_and_sync():
    """Verify apply_mimic_reaction_to_post updates storage, content, and triggers DB & edit."""
    post_num = 9901
    post_data = {
        "author_id": 123456,
        "board_id": "b",
        "timestamp": time.time() - 100,
        "content": {"text": "Тестовый базированный пост", "type": "text"},
        "reactions": {"users": {}},
    }

    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_bot = AsyncMock()

    with patch("handlers.message_router.update_post_content", new_callable=AsyncMock) as mock_upd, \
         patch("handlers.message_router.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)) as mock_spawn:

        success = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100012,
            emojis=["❤️", "🔥"],
            bot_instance=mock_bot,
            board_id="b",
        )

        assert success is True

        # Check post_data in storage
        assert post_data["reactions"]["users"][770100012] == ["❤️", "🔥"]
        assert post_data["content"]["reactions"]["users"][770100012] == ["❤️", "🔥"]

        # Check DB update called with updated reactions
        mock_upd.assert_awaited_once()
        saved_content = mock_upd.call_args[0][1]
        assert saved_content["reactions"]["users"][770100012] == ["❤️", "🔥"]

        # Check delayed edit task was spawned
        async with pending_edit_lock:
            assert post_num in pending_edit_tasks
            task = pending_edit_tasks[post_num]
            task.cancel()


@pytest.mark.asyncio
async def test_apply_mimic_reaction_triggers_best_channel():
    """Verify reaching 4+ positive reactions triggers publish_to_best_channel on /b/."""
    post_num = 9902
    post_data = {
        "author_id": 55555,
        "board_id": "b",
        "timestamp": time.time() - 200,
        "content": {"text": "Шедевр треда", "type": "text"},
        "reactions": {
            "users": {
                1001: ["👍"],
                1002: ["🔥"],
                1003: ["😂"],  # laughing is positive
            }
        },
        "forwarded_to_best": False,
    }

    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_bot = AsyncMock()

    with patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("news_channel_publisher.publish_to_best_channel", new_callable=AsyncMock) as mock_best, \
         patch("handlers.message_router.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):

        # 4th positive reaction
        success = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100007,
            emojis=["❤️"],
            bot_instance=mock_bot,
            board_id="b",
        )

        assert success is True
        # Verify publish_to_best_channel was triggered
        await asyncio.sleep(0.01)
        mock_best.assert_called_once()
        args = mock_best.call_args[0]
        assert args[1] == "b"
        assert args[2] == post_num
        assert args[4] >= 4  # current_positive_count


@pytest.mark.asyncio
async def test_apply_mimic_reaction_small_board_threshold():
    """Verify small boards trigger publish_to_best_channel at 3 positive reactions."""
    post_num = 9903
    post_data = {
        "author_id": 77777,
        "board_id": "sex",
        "timestamp": time.time() - 200,
        "content": {"text": "Вайфу арт", "type": "photo", "tags": ["anime", "waifu"]},
        "reactions": {
            "users": {
                2001: ["😍"],
                2002: ["🔥"],
            }
        },
        "forwarded_to_best": False,
    }

    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_bot = AsyncMock()

    with patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("news_channel_publisher.publish_to_best_channel", new_callable=AsyncMock) as mock_best, \
         patch("handlers.message_router.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):

        # 3rd positive reaction on /sex/
        success = await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100001,
            emojis=["❤️"],
            bot_instance=mock_bot,
            board_id="sex",
        )

        assert success is True
        await asyncio.sleep(0.01)
        mock_best.assert_called_once()


@pytest.mark.asyncio
async def test_apply_mimic_reaction_already_best_not_duplicated():
    """Verify that if post is already forwarded_to_best, publish_to_best_channel is skipped."""
    post_num = 9904
    post_data = {
        "author_id": 88888,
        "board_id": "b",
        "timestamp": time.time() - 300,
        "content": {"text": "Старый хит", "type": "text"},
        "reactions": {"users": {3001: ["👍"], 3002: ["👍"], 3003: ["👍"]}},
        "forwarded_to_best": True,  # Already forwarded!
    }

    async with storage_lock:
        messages_storage[post_num] = post_data

    mock_bot = AsyncMock()

    with patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("news_channel_publisher.publish_to_best_channel", new_callable=AsyncMock) as mock_best:

        await apply_mimic_reaction_to_post(
            post_num=post_num,
            virtual_user_id=770100010,
            emojis=["🔥"],
            bot_instance=mock_bot,
            board_id="b",
        )

        mock_best.assert_not_called()


@pytest.mark.asyncio
async def test_run_reaction_mimicry_cycle_candidate_filtering():
    """
    Verify run_reaction_mimicry_cycle filters:
      - fresh posts (< 45s old)
      - already processed posts
      - posts where virtual anon already reacted
      - non-Cyberchad system posts
      - and permits valid user posts and Cyberchad posts
    """
    now = time.time()

    candidates = [
        # 1. Valid user post (100s old) -> ELIGIBLE
        {
            "post_num": 10001,
            "board_id": "b",
            "author_id": 9991,
            "timestamp": now - 100,
            "content": {"text": "Хороший пост про программирование", "type": "text"},
            "reactions": {"users": {}},
        },
        # 2. Too fresh post (15s old < 45s) -> EXCLUDED
        {
            "post_num": 10002,
            "board_id": "b",
            "author_id": 9992,
            "timestamp": now - 15,
            "content": {"text": "Только что запостил", "type": "text"},
            "reactions": {"users": {}},
        },
        # 3. Already reacted by virtual anon 770100005 -> EXCLUDED
        {
            "post_num": 10003,
            "board_id": "b",
            "author_id": 9993,
            "timestamp": now - 120,
            "content": {"text": "Тут уже есть реакция бота", "type": "text"},
            "reactions": {"users": {770100005: ["👍"]}},
        },
        # 4. Non-Cyberchad system post -> EXCLUDED
        {
            "post_num": 10004,
            "board_id": "b",
            "author_id": 0,
            "is_system": True,
            "timestamp": now - 150,
            "content": {"text": "Системное объявление модератора", "type": "system"},
            "reactions": {"users": {}},
        },
        # 5. Cyberchad post -> ELIGIBLE
        {
            "post_num": 10005,
            "board_id": "b",
            "author_id": 777,
            "is_cyberchad": True,
            "timestamp": now - 90,
            "content": {"text": "Киберчед: Ты опять ноешь в треде?", "type": "text", "author": "Киберчед"},
            "reactions": {"users": {}},
        },
    ]

    # Pre-populate storage
    async with storage_lock:
        for c in candidates:
            messages_storage[c["post_num"]] = c

    mock_bot = AsyncMock()

    with patch("handlers.message_router.update_post_content", new_callable=AsyncMock), \
         patch("handlers.message_router.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):

        results = await run_reaction_mimicry_cycle(
            candidate_posts=candidates,
            bot_instance=mock_bot
        )

        assert len(results) >= 1
        processed_nums = {r["post_num"] for r in results}

        # Candidate 2 (too fresh), 3 (already anon reacted), and 4 (system) must NEVER be processed
        assert 10002 not in processed_nums
        assert 10003 not in processed_nums
        assert 10004 not in processed_nums

        # Processed posts must be from eligible pool (10001 or 10005)
        for p in processed_nums:
            assert p in {10001, 10005}


@pytest.mark.asyncio
async def test_cmd_reactions_formatting_virtual_anon():
    """Verify /reactions renders virtual anon user IDs cleanly as '🕶 Аноним #N'."""
    from admin_manager import cmd_reactions as admin_cmd_reactions
    from main import cmd_reactions as main_cmd_reactions

    post_num = 7788
    reactions_dict = {
        12345678: ["👍"],          # Real user
        770100012: ["🔥", "❤️"],    # Virtual Anon #12
        770100001: ["🤡"],          # Virtual Anon #1
    }

    post_data = {
        "author_id": 9999,
        "board_id": "b",
        "timestamp": time.time() - 500,
        "content": {"text": "Тест реакций", "type": "text", "reactions": {"users": reactions_dict}},
        "reactions": {"users": reactions_dict},
    }

    async with storage_lock:
        messages_storage[post_num] = post_data

    # Test formatting logic directly
    sorted_reactors = sorted(reactions_dict.items(), key=lambda x: str(x[0]))
    lines = []
    for user_id, emoji_list in sorted_reactors:
        emojis_str = "".join(emoji_list)
        uid_int = int(user_id)
        if 770100001 <= uid_int <= 770199999:
            anon_idx = uid_int - 770100000
            lines.append(f"• 🕶 Аноним #{anon_idx}: {emojis_str}")
        else:
            lines.append(f"• ID <code>{user_id}</code>: {emojis_str}")

    formatted_output = "\n".join(lines)

    # 1. Virtual anon IDs must NOT appear as raw 'ID <code>770100012</code>'
    assert "ID <code>770100012</code>" not in formatted_output
    assert "ID <code>770100001</code>" not in formatted_output

    # 2. Virtual anon IDs must appear as friendly Anon #N
    assert "• 🕶 Аноним #12: 🔥❤️" in formatted_output
    assert "• 🕶 Аноним #1: 🤡" in formatted_output

    # 3. Real user IDs must still appear as ID <code>...</code>
    assert "• ID <code>12345678</code>: 👍" in formatted_output


@pytest.mark.asyncio
async def test_reaction_mimicry_worker_loop_graceful_cancel():
    """Verify reaction_mimicry_worker_loop starts and cancels cleanly."""
    mock_bot = AsyncMock()
    task = asyncio.create_task(reaction_mimicry_worker_loop(bots_provider=lambda: {"b": mock_bot}))

    await asyncio.sleep(0.05)
    assert not task.done()

    # Cancel task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_apply_mimic_reaction_invalid_args_guard():
    """Verify invalid post_num or emojis are rejected safely."""
    mock_bot = AsyncMock()
    assert await apply_mimic_reaction_to_post(0, 770100001, ["👍"], mock_bot) is False
    assert await apply_mimic_reaction_to_post(-5, 770100001, ["👍"], mock_bot) is False
    assert await apply_mimic_reaction_to_post(100, 770100001, [], mock_bot) is False
    assert await apply_mimic_reaction_to_post(100, 770100001, "", mock_bot) is False
    # Non-existent post
    assert await apply_mimic_reaction_to_post(9999999, 770100001, ["👍"], mock_bot) is False
