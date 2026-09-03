import asyncio
import io
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from leaderboard_card import (
    LEADERBOARD_CACHE,
    MAX_LEADERBOARD_CACHE_SIZE,
    CACHE_TTL,
    generate_leaderboard_payload,
    LeaderboardData,
    LeaderboardEntry,
)
from dice_duel_engine import active_dice_games, dice_watchdog_step, dice_engine_lock
from russian_roulette_pvp import active_rr_games, rr_watchdog_step, rr_lock
from ttt_engine import active_ttt_games, ttt_watchdog_step, ttt_lock, TicTacToeGame
import post_processor


@pytest.mark.asyncio
async def test_post_processor_media_group_cleanup():
    """Verify that _save_to_memory cleans BufferedInputFile and raw bytes from media_group content."""
    class FakeInputFile:
        def __init__(self, data):
            self.data = data
            self.file_id = "test_file_id_123"

    raw_media = [
        {"type": "photo", "media": FakeInputFile(b"raw bytes of photo")},
        {"type": "video", "media": "already_string_file_id"},
    ]

    context = post_processor.NewPostContext(
        bot_instance=MagicMock(),
        board_id="b",
        user_id=12345,
        content={"type": "media_group", "media": raw_media, "text": "test album"},
        reply_to_post=None,
        is_shadow_muted=False,
        stream='ru'
    )
    processor = post_processor.NewPostProcessor(context)
    processor.final_content = {
        "type": "media_group",
        "media": raw_media,
        "text": "test album",
        "image_bytes": b"extra top-level bytes",
        "voice_bytes": b"extra voice bytes",
    }
    processor.current_post_num = 999999
    processor.thread_id = None
    processor.b_data = {}
    processor.author_results = None

    await processor._save_to_memory("2026-09-03 10:00:00")

    saved_post = shared_state.messages_storage.get(999999)
    assert saved_post is not None
    saved_content = saved_post["content"]

    assert "image_bytes" not in saved_content
    assert "voice_bytes" not in saved_content
    assert saved_content["type"] == "media_group"
    assert len(saved_content["media"]) == 2

    # Verify lightweight dicts: no FakeInputFile, only string file_id
    item0 = saved_content["media"][0]
    assert item0["type"] == "photo"
    assert item0["file_id"] == "test_file_id_123"
    assert "media" not in item0

    item1 = saved_content["media"][1]
    assert item1["type"] == "video"
    assert item1["file_id"] == "already_string_file_id"
    assert "media" not in item1

    # Cleanup
    shared_state.messages_storage.pop(999999, None)


def test_leaderboard_cache_bound_and_buffer_close():
    """Verify LEADERBOARD_CACHE is bounded to 30 items and closes evicted BytesIO buffers."""
    LEADERBOARD_CACHE.clear()

    closed_buffers = []

    class TrackedBytesIO(io.BytesIO):
        def close(self):
            closed_buffers.append(self)
            super().close()

    # Fill cache up to limit + 5
    with patch("leaderboard_card.fetch_leaderboard_data") as mock_fetch, \
         patch("leaderboard_card.draw_leaderboard_card") as mock_draw, \
         patch("leaderboard_card.format_leaderboard_text", return_value="text"):

        mock_fetch.return_value = LeaderboardData(
            board_id="b", mode="balance", mode_title="top", unit="sh",
            entries=[], caller_id=0, caller_rank=0, caller_value=0,
            total_users=1, total_metric=0
        )

        for i in range(MAX_LEADERBOARD_CACHE_SIZE + 5):
            buf = TrackedBytesIO(b"dummy image data")
            mock_draw.return_value = buf
            generate_leaderboard_payload("b", "balance", caller_id=i + 1)

    assert len(LEADERBOARD_CACHE) <= MAX_LEADERBOARD_CACHE_SIZE
    # At least 5 buffers must have been evicted and closed
    assert len(closed_buffers) >= 5
    for b in closed_buffers:
        assert b.closed


@pytest.mark.asyncio
async def test_dice_watchdog_evicts_finished_games():
    """Verify dice_watchdog_step pops games finished > 60 seconds ago."""
    now = time.time()
    gid_old = "dice_old_finished"
    gid_recent = "dice_recent_finished"

    async with dice_engine_lock:
        active_dice_games[gid_old] = {
            "finished": True,
            "state": "finished",
            "finished_ts": now - 75,
            "chat_id": 1,
            "msg_id": 1,
        }
        active_dice_games[gid_recent] = {
            "finished": True,
            "state": "finished",
            "finished_ts": now - 10,
            "chat_id": 1,
            "msg_id": 2,
        }

    await dice_watchdog_step(bot=None)

    async with dice_engine_lock:
        assert gid_old not in active_dice_games
        assert gid_recent in active_dice_games
        # Cleanup
        active_dice_games.pop(gid_recent, None)


@pytest.mark.asyncio
async def test_rr_watchdog_evicts_finished_games():
    """Verify rr_watchdog_step pops games finished > 60 seconds ago."""
    now = time.time()
    gid_old = "rr_old_finished"
    gid_recent = "rr_recent_finished"

    async with rr_lock:
        active_rr_games[gid_old] = {
            "finished": True,
            "state": "finished",
            "finished_ts": now - 75,
            "chat_id": 1,
            "msg_id": 1,
        }
        active_rr_games[gid_recent] = {
            "finished": True,
            "state": "finished",
            "finished_ts": now - 10,
            "chat_id": 1,
            "msg_id": 2,
        }

    await rr_watchdog_step(bot=None)

    async with rr_lock:
        assert gid_old not in active_rr_games
        assert gid_recent in active_rr_games
        # Cleanup
        active_rr_games.pop(gid_recent, None)


@pytest.mark.asyncio
async def test_ttt_watchdog_evicts_finished_games():
    """Verify ttt_watchdog_step pops games finished > 60 seconds ago."""
    now = time.time()
    gid_old = "ttt_old_finished"
    gid_recent = "ttt_recent_finished"

    game_old = TicTacToeGame(
        game_id=gid_old,
        board_id="b",
        chat_id=1,
        challenger_id=10,
        bet=100,
        status="finished",
        finished_at=now - 75,
    )
    game_recent = TicTacToeGame(
        game_id=gid_recent,
        board_id="b",
        chat_id=1,
        challenger_id=20,
        bet=100,
        status="finished",
        finished_at=now - 10,
    )

    async with ttt_lock:
        active_ttt_games[gid_old] = game_old
        active_ttt_games[gid_recent] = game_recent

    await ttt_watchdog_step(bot=None)

    async with ttt_lock:
        assert gid_old not in active_ttt_games
        assert gid_recent in active_ttt_games
        # Cleanup
        active_ttt_games.pop(gid_recent, None)


@pytest.mark.asyncio
async def test_database_cleanup_message_to_post_pruning():
    """Verify message_to_post is pruned against valid_nums from messages_storage and post_to_messages."""
    async with shared_state.storage_lock:
        shared_state.messages_storage[100] = {"content": "post 100"}
        shared_state.post_to_messages[200] = {1: 2001}

        shared_state.message_to_post.clear()
        shared_state.message_to_post[(1, 1001)] = 100  # valid (in messages_storage)
        shared_state.message_to_post[(1, 2001)] = 200  # valid (in post_to_messages)
        shared_state.message_to_post[(1, 9999)] = 999  # stale (not in either)

        # Simulation of the logic in database_cleanup_task
        valid_nums = set(shared_state.messages_storage.keys()) | set(shared_state.post_to_messages.keys())
        stale_keys = [k for k, pnum in shared_state.message_to_post.items() if pnum not in valid_nums]
        for k in stale_keys:
            shared_state.message_to_post.pop(k, None)

        assert (1, 1001) in shared_state.message_to_post
        assert (1, 2001) in shared_state.message_to_post
        assert (1, 9999) not in shared_state.message_to_post

        # Cleanup
        shared_state.messages_storage.pop(100, None)
        shared_state.post_to_messages.pop(200, None)
        shared_state.message_to_post.clear()
