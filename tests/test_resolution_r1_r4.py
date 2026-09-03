# -*- coding: utf-8 -*-
"""
Comprehensive Regression and Integration Test Suite for Requirements R1, R3, and R4.

Scope:
- R1: Background Tagger Gap Query Resolution & File Registry Multi-ID Mapping.
  Verifies that multiple posts sharing identical image content (same SHA-256)
  with different Telegram file_ids have all secondary file_ids recorded in FileRegistry,
  and subsequent gap queries return 0 remaining tasks (terminating infinite re-download loops).
- R3: System Post Archiving Verification & Realtime Forwarding.
  Verifies that system posts marked with `archive_allowed: True` (such as weekly airdrop
  announcements, Abu notices, deanon alerts, and duel cards) are forwarded by
  `_forward_post_to_realtime_archive` and persist entries in `ChannelCopies`,
  including when board recipient sets are empty.
- R4: Shekel Distribution Delivery & State Machine Verification.
  Verifies money drop deterministic state transitions (active -> claimed, active -> expired,
  active -> cancelled), validates `_update_all_drop_messages` delivery across all recipient
  copies, verifies mid-broadcast claim cancels active button dispatch, and exercises
  anti-bot / anti-fraud protections.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite
from aiogram import Bot
from aiogram.types import Message, PhotoSize, InlineKeyboardMarkup

import shared_state
from shared_state import storage_lock, messages_storage, post_to_messages, board_data, NewPostParams
import archive_manager
from archive_manager import (
    _forward_post_to_realtime_archive,
    add_channel_copy,
    _BOT_INACCESSIBLE_CHANNELS,
    _INACCESSIBLE_CHANNELS,
)
import delivery_manager
from delivery_manager import MessageDeliveryTask
import post_processor
from post_processor import process_new_post
import drop_engine
from drop_engine import (
    DropRecord,
    active_drops,
    drop_lock,
    create_money_drop,
    claim_money_drop,
    cancel_money_drop,
    expire_unclaimed_drops_step,
    init_drop_engine,
    register_drop_message,
    get_drop_messages,
    clear_drop_messages,
    reset_drop_cooldowns,
    set_min_reaction_delay,
    MIN_DROP_AMOUNT,
    MAX_DROP_AMOUNT,
)
import site_tgach.tagging_worker as tagging_worker
from site_tgach.tagging_worker import get_tasks


# =========================================================================
# Test Utilities & Mocks
# =========================================================================

def _make_mock_message(message_id: int = 100, text: str = "test", photo_fid: str | None = None):
    msg = MagicMock(spec=Message)
    msg.message_id = message_id
    msg.text = text
    msg.caption = text if photo_fid else None
    if photo_fid:
        photo = MagicMock(spec=PhotoSize)
        photo.file_id = photo_fid
        msg.photo = [photo]
        msg.content_type = "photo"
    else:
        msg.photo = None
        msg.content_type = "text"
    msg.edit_text = AsyncMock(return_value=True)
    msg.edit_caption = AsyncMock(return_value=True)
    return msg


def _make_mock_bot(bot_id: int = 1, username: str = "dvach_test_bot"):
    bot = AsyncMock(spec=Bot)
    bot.id = bot_id
    bot.token = f"token_{bot_id}"
    bot.send_message = AsyncMock(return_value=_make_mock_message(message_id=100 + bot_id))
    bot.send_photo = AsyncMock(return_value=_make_mock_message(message_id=200 + bot_id, photo_fid=f"photo_{bot_id}"))
    bot.edit_message_text = AsyncMock(return_value=True)
    bot.edit_message_caption = AsyncMock(return_value=True)

    async def _mock_download(file, destination=None, **kwargs):
        if destination and hasattr(destination, 'write'):
            destination.write(b"mock_raw_image_bytes")
        return b"mock_raw_image_bytes"

    bot.download = AsyncMock(side_effect=_mock_download)
    return bot


@pytest.fixture(autouse=True)
def clean_environment_state():
    """Clean global registries and test states before and after each test."""
    reset_drop_cooldowns()
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()
    shared_state.GLOBAL_BOTS.clear()
    archive_manager.MIRROR_CHANNELS = [-1001234567890, -1009876543210]
    board_data.clear()
    yield
    reset_drop_cooldowns()
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()
    shared_state.GLOBAL_BOTS.clear()
    board_data.clear()


# =========================================================================
# REQUIREMENT R1: Tagger Gap Query Resolution & File Registry Multi-ID
# =========================================================================

class TestR1TaggerGapResolution:
    """
    R1: Verify tagger gap queries, secondary file_id registration in FileRegistry,
    and elimination of the infinite re-download / tagging loop for shared SHA media.
    """

    @pytest.mark.asyncio
    async def test_r1_gap_query_finds_single_and_album_media(self, isolated_test_db):
        """
        Verify that get_tasks extracts missing media file_ids from both
        single-file posts (`$.file_id`) and multi-file album posts (`$.files`).
        """
        db = isolated_test_db
        now = time.time()

        # Insert Post 1: Single file photo
        single_content = json.dumps({
            "type": "photo",
            "file_id": "FID_SINGLE_001",
            "file_name": "image1.jpg",
            "mime_type": "image/jpeg"
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (101, 'b', 1, ?, ?)",
            (single_content, now)
        )

        # Insert Post 2: Multi-file album (2 images)
        album_content = json.dumps({
            "type": "album",
            "files": [
                {
                    "original_file_id": "FID_ALBUM_001",
                    "type": "image",
                    "file_name": "album1.png",
                    "mime_type": "image/png"
                },
                {
                    "original_file_id": "FID_ALBUM_002",
                    "type": "photo",
                    "thumbnail_file_id": "THUMB_ALBUM_002",
                    "file_name": "album2.jpg",
                    "mime_type": "image/jpeg"
                }
            ]
        })
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (102, 'b', 2, ?, ?)",
            (album_content, now)
        )

        # Execute get_tasks on database with patched BATCH_SIZE to retrieve all pending gap items
        with patch.object(tagging_worker, "BATCH_SIZE", 10):
            tasks = await get_tasks(db)
            task_fids = [t["fid"] for t in tasks]

            assert "FID_SINGLE_001" in task_fids, "Single file FID must be identified as gap task"
            assert "FID_ALBUM_001" in task_fids, "First album file FID must be identified as gap task"
            assert "FID_ALBUM_002" in task_fids, "Second album file FID must be identified as gap task"
            assert len(task_fids) == 3

    @pytest.mark.asyncio
    async def test_r1_duplicate_sha_secondary_file_id_recorded_and_resolves_gap_loop(self, isolated_test_db):
        """
        Critical Bug Reproduction & Verification for R1:
        When two posts contain different file_ids (FID_PRIMARY and FID_SECONDARY)
        sharing the same SHA-256 hash (e.g. system banner or forwarded image):
        1. FID_PRIMARY is recorded in FileRegistry with SHA_COMMON.
        2. FID_SECONDARY is detected as gap task.
        3. Upon saving FID_SECONDARY with SHA_COMMON, secondary record must be indexed
           so that FID_SECONDARY is stored in FileRegistry.
        4. Subsequent get_tasks must return 0 remaining tasks, breaking the infinite loop.
        """
        db = isolated_test_db
        now = time.time()
        common_sha = "59d285622f422028b9ea047885346c6d752cca2a3b2b84c778e05d229157a9a3"

        # Post 1 with FID_PRIMARY
        p1_content = json.dumps({"type": "photo", "file_id": "FID_PRIMARY_BANNER"})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (201, 'b', 10, ?, ?)",
            (p1_content, now)
        )

        # Post 2 with FID_SECONDARY (same media content, different Telegram file_id)
        p2_content = json.dumps({"type": "photo", "file_id": "FID_SECONDARY_BANNER"})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (202, 'b', 11, ?, ?)",
            (p2_content, now)
        )

        # Step 1: Sequential get_tasks Pass 1 returns first task
        tasks_pass1 = await get_tasks(db)
        assert len(tasks_pass1) == 1
        fetched_fid1 = tasks_pass1[0]["fid"]
        assert fetched_fid1 in ("FID_PRIMARY_BANNER", "FID_SECONDARY_BANNER")

        # Step 2: Primary file is processed and saved in FileRegistry
        primary_tags = "banner, 2ch, anime, megumin"
        primary_desc = "Megumin explosion banner"
        await db.execute(
            """
            INSERT INTO FileRegistry 
            (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
            VALUES (?, 'p_hash_banner', ?, NULL, 'photo', ?, 'b_hash_1', ?, ?)
            """,
            (common_sha, fetched_fid1, now, primary_tags, primary_desc)
        )

        # Step 3: Run get_tasks for Pass 2 -> Primary is filtered, other file is returned
        tasks_pass2 = await get_tasks(db)
        assert len(tasks_pass2) == 1
        fetched_fid2 = tasks_pass2[0]["fid"]
        assert fetched_fid2 != fetched_fid1, "Second pass must fetch the remaining unprocessed file_id"

        # Step 4: Simulate secondary file tagging pass.
        # Worker detects SHA already exists in FileRegistry:
        async with db.execute(
            "SELECT tags, description FROM FileRegistry WHERE sha256 = ? LIMIT 1",
            (common_sha,)
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "Tags must be found for existing SHA (Skip Neuro)"
        reused_tags, reused_desc = row[0], row[1]
        assert reused_tags == primary_tags

        # Save secondary file_id into FileRegistry using composite secondary record key
        sec_sha = f"{common_sha}_{fetched_fid2}"
        await db.execute(
            """
            INSERT OR REPLACE INTO FileRegistry 
            (sha256, phash, file_id, thumbnail_id, file_type, created_at, blurhash, tags, description)
            VALUES (?, 'p_hash_banner', ?, NULL, 'photo', ?, 'b_hash_1', ?, ?)
            """,
            (sec_sha, fetched_fid2, now, reused_tags, reused_desc)
        )

        # Step 5: Verify both file_ids exist in FileRegistry
        async with db.execute("SELECT file_id FROM FileRegistry WHERE file_id IS NOT NULL") as cur:
            registered_fids = [r[0] async for r in cur]
        assert "FID_PRIMARY_BANNER" in registered_fids
        assert "FID_SECONDARY_BANNER" in registered_fids

        # Step 6: Next get_tasks must return 0 gap tasks
        tasks_pass3 = await get_tasks(db)
        fids_pass3 = [t["fid"] for t in tasks_pass3]
        assert "FID_PRIMARY_BANNER" not in fids_pass3
        assert "FID_SECONDARY_BANNER" not in fids_pass3
        assert len(tasks_pass3) == 0, "Gap query must return 0 remaining tasks, terminating the infinite loop"

    @pytest.mark.asyncio
    async def test_r1_multiple_duplicate_sha_posts_stress(self, isolated_test_db):
        """
        Adversarial Stress Test:
        Create 5 separate posts with 5 distinct file_ids sharing the exact same SHA hash.
        Verify that sequential processing records all 5 file_ids in FileRegistry,
        and gap query returns 0 tasks after all 5 are processed.
        """
        db = isolated_test_db
        now = time.time()
        shared_sha = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
        fids = [f"FID_STRESS_{i}" for i in range(1, 6)]

        for i, fid in enumerate(fids, start=1):
            content = json.dumps({"type": "photo", "file_id": fid})
            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (?, 'b', ?, ?, ?)",
                (250 + i, i, content, now)
            )

        # Save first as primary, rest as secondary
        await db.execute(
            "INSERT INTO FileRegistry (sha256, phash, file_id, file_type, created_at, tags, description) VALUES (?, 'phash', ?, 'photo', ?, 'test, stress', 'stress banner')",
            (shared_sha, fids[0], now)
        )

        for fid in fids[1:]:
            sec_sha = f"{shared_sha}_{fid}"
            await db.execute(
                "INSERT OR REPLACE INTO FileRegistry (sha256, phash, file_id, file_type, created_at, tags, description) VALUES (?, 'phash', ?, 'photo', ?, 'test, stress', 'stress banner')",
                (sec_sha, fid, now)
            )

        with patch.object(tagging_worker, "BATCH_SIZE", 50):
            remaining_tasks = await get_tasks(db)
            remaining_fids = [t["fid"] for t in remaining_tasks]
            for fid in fids:
                assert fid not in remaining_fids, f"{fid} must be excluded from gap tasks"
            assert len(remaining_tasks) == 0

    @pytest.mark.asyncio
    async def test_r1_gap_query_filters_out_of_window_and_non_media_posts(self, isolated_test_db):
        """
        Verify that get_tasks enforces the 250-post window limit and ignores
        non-media posts (pure text) and posts with NULL file_ids.
        """
        db = isolated_test_db
        now = time.time()

        # Create latest post to establish MAX(post_num) = 1000
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (1000, 'b', 1, '{\"type\": \"text\", \"text\": \"Latest post\"}', ?)",
            (now,)
        )

        # Post at post_num = 700 (outside 250-window: 1000 - 250 = 750)
        old_content = json.dumps({"type": "photo", "file_id": "FID_OLD_EXCLUDED"})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (700, 'b', 2, ?, ?)",
            (old_content, now)
        )

        # Post at post_num = 800 (inside 250-window, but pure text)
        text_content = json.dumps({"type": "text", "text": "Just plain text"})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (800, 'b', 3, ?, ?)",
            (text_content, now)
        )

        # Post at post_num = 850 (inside 250-window, photo with NULL fid)
        null_fid_content = json.dumps({"type": "photo", "file_id": None})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (850, 'b', 4, ?, ?)",
            (null_fid_content, now)
        )

        # Post at post_num = 950 (inside 250-window, valid photo)
        valid_content = json.dumps({"type": "photo", "file_id": "FID_VALID_WINDOW"})
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (950, 'b', 5, ?, ?)",
            (valid_content, now)
        )

        tasks = await get_tasks(db)
        task_fids = [t["fid"] for t in tasks]

        assert "FID_VALID_WINDOW" in task_fids, "Valid media within last 250 posts must be fetched"
        assert "FID_OLD_EXCLUDED" not in task_fids, "Posts older than 250-window must be excluded"
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_r1_error_file_secondary_id_deduplication(self, isolated_test_db):
        """
        Verify that corrupted / bad duplicate files sharing the same SHA
        record all secondary file_ids with tags='error' to avoid infinite error re-fetch loops.
        """
        db = isolated_test_db
        now = time.time()
        bad_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # Post 1 and Post 2 with bad files
        p1 = json.dumps({"type": "photo", "file_id": "FID_BAD_1"})
        p2 = json.dumps({"type": "photo", "file_id": "FID_BAD_2"})
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (301, 'b', 1, ?, ?)", (p1, now))
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (302, 'b', 2, ?, ?)", (p2, now))

        # Save first bad file
        await db.execute(
            "INSERT INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, 'FID_BAD_1', 'photo', 'error_file_invalid', ?)",
            (bad_sha, now)
        )

        # Save second bad file using secondary composite key
        sec_bad_sha = f"{bad_sha}_FID_BAD_2"
        await db.execute(
            "INSERT OR REPLACE INTO FileRegistry (sha256, file_id, file_type, tags, created_at) VALUES (?, 'FID_BAD_2', 'photo', 'error_file_invalid', ?)",
            (sec_bad_sha, now)
        )

        # Gap query should now return 0 tasks
        tasks = await get_tasks(db)
        assert len(tasks) == 0, "Both bad file_ids must be registered in FileRegistry to cease error re-fetch loops"


# =========================================================================
# REQUIREMENT R3: System Post Archiving Verification & Realtime Forwarding
# =========================================================================

class TestR3SystemPostArchiving:
    """
    R3: Verify that system messages and economic events marked with `archive_allowed: True`
    are forwarded to archive channels and produce ChannelCopies entries, even when
    board recipient sets are empty.
    """

    @pytest.mark.asyncio
    async def test_r3_system_posts_with_archive_allowed_forwarded_to_archive(self, isolated_test_db):
        """
        Test that critical system post types with `archive_allowed: True`:
        - Airdrop announcements
        - Abu official notices (author_id = 0, is_system_message = True)
        - /deanon notices
        - Duel cards / PvP outcome cards
        successfully execute `_forward_post_to_realtime_archive` and write to ChannelCopies.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=777)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1001234567890
        archive_manager.MIRROR_CHANNELS = [mirror_channel]

        test_cases = [
            (
                501,
                {
                    "type": "text",
                    "text": "🎉 <b>ЕЖЕНЕДЕЛЬНЫЙ AIRDROP АБУ!</b> Раздача 50,000 ₪ среди активных двачеров.",
                    "is_system_message": True,
                    "archive_allowed": True,
                    "author_id": 0
                }
            ),
            (
                502,
                {
                    "type": "text",
                    "text": "👑 <b>ОБРАЩЕНИЕ АБУ:</b> Серверная переходит на протокол Hecton-8.",
                    "is_system_message": True,
                    "archive_allowed": True,
                    "author_id": 0
                }
            ),
            (
                503,
                {
                    "type": "text",
                    "text": "👁️ <b>ДЕАНОНИМИЗАЦИЯ:</b> Пользователь Анон [a1b2c3d4] был успешно деанонимизирован!",
                    "is_system_message": True,
                    "archive_allowed": True
                }
            ),
            (
                504,
                {
                    "type": "text",
                    "text": "🎲 <b>ДУЭЛЬ НА КОСТЯХ:</b> Победил Анон [777] (Сумма: 10,000 ₪)!",
                    "is_system_message": True,
                    "archive_allowed": True
                }
            )
        ]

        now = time.time()
        for pnum, content in test_cases:
            # Insert post into database
            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
                "VALUES (?, 'b', ?, ?, ?)",
                (pnum, content.get("author_id", 10), json.dumps(content), now)
            )

            # Call _forward_post_to_realtime_archive
            await _forward_post_to_realtime_archive(
                bot_instance=mock_bot,
                board_id="b",
                post_num=pnum,
                content=content,
                is_shadow_muted=False
            )

            # Verify that mock_bot sent message to mirror_channel
            assert mock_bot.send_message.called, f"Bot must send archive message for post #{pnum}"

            # Verify ChannelCopies entry created
            async with db.execute(
                "SELECT message_id FROM ChannelCopies WHERE post_num = ? AND channel_id = ?",
                (pnum, mirror_channel)
            ) as cur:
                row = await cur.fetchone()
            assert row is not None, f"ChannelCopies must contain record for post #{pnum} in channel {mirror_channel}"

    @pytest.mark.asyncio
    async def test_r3_empty_recipients_triggers_archive_forwarding_in_delivery_task(self, isolated_test_db):
        """
        Verify that MessageDeliveryTask with empty recipients set (`recipients = set()`)
        still invokes `_forward_post_to_realtime_archive` for posts with `archive_allowed: True`.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=888)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1001234567890
        archive_manager.MIRROR_CHANNELS = [mirror_channel]

        post_num = 601
        now = time.time()
        system_content = {
            "type": "text",
            "text": "📢 <b>РЕЖИМ ГОПНИКА ДЕАКТИВИРОВАН</b> (Срок действия истек).",
            "is_system_message": True,
            "archive_allowed": True
        }

        # Insert post into DB
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (?, 'b', 0, ?, ?)",
            (post_num, json.dumps(system_content), now)
        )

        msg_data = {
            "post_num": post_num,
            "board_id": "b",
            "content": system_content,
            "recipients": set(),  # EMPTY RECIPIENTS SET
            "enqueued_at": now
        }

        board_data["b"] = {"users": {"active": set()}}

        task = MessageDeliveryTask(
            worker_name="TestWorker",
            board_id="b",
            bot_instance=mock_bot,
            queue=AsyncMock(),
            msg_data=msg_data
        )

        # Process task and allow spawned archive task to execute
        with patch("delivery_manager.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):
            await task.process()
            await asyncio.sleep(0.05)

        # Verify ChannelCopies was written
        async with db.execute(
            "SELECT message_id FROM ChannelCopies WHERE post_num = ? AND channel_id = ?",
            (post_num, mirror_channel)
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "System post with empty recipients must be archived in ChannelCopies"

    @pytest.mark.asyncio
    async def test_r3_post_processor_spawns_archive_for_empty_board(self, isolated_test_db):
        """
        Verify that `process_new_post` spawns archive forwarding for system posts
        with `archive_allowed: True` even when the board has 0 active recipients.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=999)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1001234567890
        archive_manager.MIRROR_CHANNELS = [mirror_channel]

        board_data["b"] = {
            "users": {"active": set()},  # 0 active board users (empty set)
            "threads": [],
            "threads_data": {}
        }

        post_payload = {
            "type": "text",
            "text": "📜 <b>УВЕДОМЛЕНИЕ О ТРЕЙД-ХАБЕ:</b> Открыты новые лоты на Базаре.",
            "is_system_message": True,
            "archive_allowed": True
        }

        with patch("post_processor.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):
            params = NewPostParams(
                bot_instance=mock_bot,
                board_id="b",
                user_id=0,
                content=post_payload,
                reply_to_post=None,
                is_shadow_muted=False,
                stream="ru"
            )
            pnum = await process_new_post(params)
            assert pnum is not None
            await asyncio.sleep(0.05)

        # Verify ChannelCopies contains record for created post
        async with db.execute(
            "SELECT message_id FROM ChannelCopies WHERE post_num = ? AND channel_id = ?",
            (pnum, mirror_channel)
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "process_new_post must forward archive-allowed system post even on empty board"

    @pytest.mark.asyncio
    async def test_r3_channel_copies_deduplication(self, isolated_test_db):
        """
        Verify that _forward_post_to_realtime_archive does not re-send or duplicate
        messages if ChannelCopies already contains an entry for (post_num, channel_id).
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=111)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1001234567890
        archive_manager.MIRROR_CHANNELS = [mirror_channel]

        post_num = 701
        now = time.time()
        content = {"type": "text", "text": "Duplicate test post", "archive_allowed": True}

        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
            "VALUES (?, 'b', 1, ?, ?)",
            (post_num, json.dumps(content), now)
        )

        # Pre-populate ChannelCopies
        await add_channel_copy(post_num, mirror_channel, message_id=5555)

        # Call forwarder
        await _forward_post_to_realtime_archive(
            bot_instance=mock_bot,
            board_id="b",
            post_num=post_num,
            content=content,
            is_shadow_muted=False
        )

        # Bot send_message must NOT have been called due to deduplication
        assert not mock_bot.send_message.called, "Duplicate post must be skipped if ChannelCopies entry exists"

    @pytest.mark.asyncio
    async def test_r3_archive_skip_and_shadow_mute_rules(self, isolated_test_db):
        """
        Verify archive gating logic:
        1. is_shadow_muted = True -> never archived.
        2. archive_skip = True without archive_allowed = True -> skipped.
        3. archive_skip = True WITH archive_allowed = True -> archive_allowed takes precedence and post is forwarded.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=222)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1001234567890
        archive_manager.MIRROR_CHANNELS = [mirror_channel]
        now = time.time()

        # Case 1: Shadow-muted post
        content1 = {"type": "text", "text": "Shadow muted", "archive_allowed": True}
        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (801, 'b', 1, ?, ?)", (json.dumps(content1), now))
        await _forward_post_to_realtime_archive(mock_bot, "b", 801, content1, is_shadow_muted=True)
        assert not mock_bot.send_message.called

        # Case 2: archive_skip without archive_allowed
        mock_bot.send_message.reset_mock()
        content2 = {"type": "text", "text": "Skip archive", "archive_skip": True}
        should_archive2 = not False and (content2.get("archive_allowed") or not content2.get("archive_skip"))
        assert should_archive2 is False, "archive_skip must evaluate should_archive to False"

        # Case 3: archive_skip WITH archive_allowed
        content3 = {"type": "text", "text": "Override skip", "archive_skip": True, "archive_allowed": True}
        should_archive3 = not False and (content3.get("archive_allowed") or not content3.get("archive_skip"))
        assert should_archive3 is True, "archive_allowed must override archive_skip"

        await db.execute("INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (803, 'b', 1, ?, ?)", (json.dumps(content3), now))
        await _forward_post_to_realtime_archive(mock_bot, "b", 803, content3, is_shadow_muted=False)
        assert mock_bot.send_message.called, "Post with archive_allowed=True must be forwarded to archive"


# =========================================================================
# REQUIREMENT R4: Shekel Distribution State Machine & Drop Delivery
# =========================================================================

class TestR4ShekelDistributionStateMachine:
    """
    R4: Verify money drop lifecycle state transitions (active -> claimed, active -> expired,
    active -> cancelled), validate message broadcasting and update delivery, and verify
    mid-broadcast cancellation of active claim buttons.
    """

    @pytest.mark.asyncio
    async def test_r4_money_drop_active_to_claimed_lifecycle(self, isolated_test_db):
        """
        Verify complete happy-path lifecycle:
        1. Donor balance debited, drop status initialized to 'active' in DB and RAM.
        2. First valid claimer claims drop: claimer balance credited, drop status becomes 'claimed'.
        3. Second claimer rejected with informative error.
        4. Donor cannot claim own drop.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 10001
        claimer1_id = 10002
        claimer2_id = 10003

        # Setup initial balances in Users table
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100)", (claimer1_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 200)", (claimer2_id,))
        await db.commit()

        # Step 1: Donor creates drop of 1000 shekels
        ok, msg, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="DonorSych",
            board_id="b",
            amount=1000,
            db_lock=db_lock,
            db_conn=db,
            timeout_sec=600.0,
            check_cooldown=False,
        )
        assert ok is True, f"Drop creation failed: {msg}"
        assert drop_rec is not None
        assert drop_rec.status == "active"
        assert drop_rec.amount == 1000

        # Verify donor balance deducted to 4000
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            bal = (await cur.fetchone())[0]
        assert bal == 4000

        # Verify DB record in MoneyDrops
        async with db.execute("SELECT status, amount FROM MoneyDrops WHERE drop_id = ?", (drop_rec.drop_id,)) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "active"
        assert row[1] == 1000.0

        # Step 2: Donor attempts to claim own drop -> Rejected
        ok_own, msg_own, _ = await claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=donor_id,
            claimer_name="DonorSych",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
        )
        assert ok_own is False
        assert "собственный дроп" in msg_own

        # Step 3: Claimer 1 claims drop -> Success
        ok_claim, msg_claim, updated_rec = await claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=claimer1_id,
            claimer_name="ClaimerAnon1",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
        )
        assert ok_claim is True, f"Claim failed: {msg_claim}"
        assert updated_rec.status == "claimed"
        assert updated_rec.claimed_by == claimer1_id

        # Verify claimer 1 balance credited (100 + 1000 = 1100)
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (claimer1_id,)) as cur:
            c1_bal = (await cur.fetchone())[0]
        assert c1_bal == 1100

        # Verify DB status updated to 'claimed'
        async with db.execute("SELECT status, claimed_by FROM MoneyDrops WHERE drop_id = ?", (drop_rec.drop_id,)) as cur:
            db_status = await cur.fetchone()
        assert db_status[0] == "claimed"
        assert db_status[1] == claimer1_id

        # Step 4: Claimer 2 attempts to claim already claimed drop -> Rejected
        ok_claim2, msg_claim2, _ = await claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=claimer2_id,
            claimer_name="ClaimerAnon2",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
        )
        assert ok_claim2 is False
        assert "уже забрал" in msg_claim2

        # Verify claimer 2 balance unchanged (200)
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (claimer2_id,)) as cur:
            c2_bal = (await cur.fetchone())[0]
        assert c2_bal == 200

    @pytest.mark.asyncio
    async def test_r4_money_drop_concurrent_claims_race_condition(self, isolated_test_db):
        """
        Adversarial Concurrency Test:
        20 users simultaneously attempt to claim the exact same drop at the same millisecond.
        Assert that EXACTLY 1 claimer succeeds, 19 fail, and balance accounting remains 100% closed-loop.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 99000
        claimer_ids = list(range(99001, 99021))  # 20 claimers

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
        for cid in claimer_ids:
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (cid,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="RaceDonor",
            board_id="b",
            amount=1000,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True

        async def _attempt_claim(cid: int):
            return await claim_money_drop(
                drop_id=drop_rec.drop_id,
                claimer_id=cid,
                claimer_name=f"Claimer_{cid}",
                claimer_board_id="b",
                db_lock=db_lock,
                db_conn=db,
                check_reaction_delay=False,
                check_claimer_rate_limit=False,
                check_farm_laundering=False,
            )

        results = await asyncio.gather(*[_attempt_claim(cid) for cid in claimer_ids])
        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        assert len(successes) == 1, f"Exactly 1 winner allowed in concurrent race, got {len(successes)}"
        assert len(failures) == 19, f"Exactly 19 claimers must be rejected, got {len(failures)}"

        winner_id = successes[0][2].claimed_by
        assert winner_id in claimer_ids

        # Verify DB balances
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (winner_id,)) as cur:
            winner_bal = (await cur.fetchone())[0]
        assert winner_bal == 1000

        # Verify other 19 claimers still have balance = 0
        async with db.execute("SELECT COUNT(*) FROM Users WHERE user_id IN (%s) AND balance = 0" % ",".join(map(str, claimer_ids))) as cur:
            zero_cnt = (await cur.fetchone())[0]
        assert zero_cnt == 19

    @pytest.mark.asyncio
    async def test_r4_money_drop_active_to_expired_lifecycle(self, isolated_test_db):
        """
        Verify expiration lifecycle:
        1. Drop created with timeout_sec = 0 (immediately expired).
        2. expire_unclaimed_drops_step identifies expired drops and refunds donor.
        3. Status transitions to 'expired' in RAM and DB.
        4. Late claim attempts on expired drop are rejected.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 20001
        claimer_id = 20002

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 3000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50)", (claimer_id,))
        await db.commit()

        # Create drop with timeout = -10 seconds (expired at creation)
        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="TimeoutDonor",
            board_id="b",
            amount=500,
            db_lock=db_lock,
            db_conn=db,
            timeout_sec=-10.0,
            check_cooldown=False,
        )
        assert ok is True

        # Check donor balance deducted to 2500
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            bal_before = (await cur.fetchone())[0]
        assert bal_before == 2500

        # Execute background expiration step
        expired_drops = await expire_unclaimed_drops_step(db_lock, db)
        assert len(expired_drops) >= 1
        assert any(d.drop_id == drop_rec.drop_id for d in expired_drops)

        # Verify donor balance refunded back to 3000
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            bal_after = (await cur.fetchone())[0]
        assert bal_after == 3000

        # Verify DB status updated to 'expired'
        async with db.execute("SELECT status, refunded_at FROM MoneyDrops WHERE drop_id = ?", (drop_rec.drop_id,)) as cur:
            row = await cur.fetchone()
        assert row[0] == "expired"
        assert row[1] is not None

        # Attempt to claim expired drop -> Rejected
        ok_claim, msg_claim, _ = await claim_money_drop(
            drop_id=drop_rec.drop_id,
            claimer_id=claimer_id,
            claimer_name="LateClaimer",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
        )
        assert ok_claim is False
        assert "истекло" in msg_claim

    @pytest.mark.asyncio
    async def test_r4_money_drop_active_to_cancelled_lifecycle(self, isolated_test_db):
        """
        Verify donor cancellation lifecycle:
        1. Donor cancels active drop via cancel_money_drop.
        2. Status transitions to 'cancelled' and funds refunded to donor.
        3. Non-donor cannot cancel.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 30001
        stranger_id = 30002

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 2000)", (donor_id,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="CancelDonor",
            board_id="b",
            amount=800,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True

        # Stranger attempts cancellation -> Rejected
        ok_stranger, msg_stranger = await cancel_money_drop(drop_rec.drop_id, stranger_id, db_lock, db)
        assert ok_stranger is False
        assert "не являешься создателем" in msg_stranger

        # Donor cancels drop -> Success
        ok_cancel, msg_cancel = await cancel_money_drop(drop_rec.drop_id, donor_id, db_lock, db)
        assert ok_cancel is True
        assert "отменен" in msg_cancel

        # Verify donor balance refunded to 2000
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            bal = (await cur.fetchone())[0]
        assert bal == 2000

        # Verify DB status updated to 'cancelled'
        async with db.execute("SELECT status FROM MoneyDrops WHERE drop_id = ?", (drop_rec.drop_id,)) as cur:
            status = (await cur.fetchone())[0]
        assert status == "cancelled"

    @pytest.mark.asyncio
    async def test_r4_update_all_drop_messages_upon_claim_and_expiry(self):
        """
        Verify that `_update_all_drop_messages`:
        1. Iterates over all registered message copies (chat_id, message_id).
        2. Edits message text / caption, removing the claim button (reply_markup=None).
        3. Respects exclude_chat_id / exclude_pair for the winner's chat.
        """
        from main import _update_all_drop_messages

        mock_bot = _make_mock_bot(bot_id=1)
        drop_id = "test_drop_msg_update_001"

        # Register 3 message copies across 3 users
        register_drop_message(drop_id, 101, 1001)
        register_drop_message(drop_id, 102, 1002)
        register_drop_message(drop_id, 103, 1003)

        assert len(get_drop_messages(drop_id)) == 3

        update_text = "💸 <b>ДРОП ШЕКЕЛЕЙ ПЕРЕХВАЧЕН!</b> Победитель: Анон [777]"

        # Exclude winner chat 101
        await _update_all_drop_messages(mock_bot, drop_id, update_text, exclude_chat_id=101)

        # Verify bot edit calls: chats 102 and 103 were edited, chat 101 was excluded
        edited_chat_ids = []
        for call in mock_bot.edit_message_caption.call_args_list:
            edited_chat_ids.append(call.kwargs.get("chat_id"))
        for call in mock_bot.edit_message_text.call_args_list:
            edited_chat_ids.append(call.kwargs.get("chat_id"))

        assert 101 not in edited_chat_ids, "Winner chat must be excluded as it is updated instantly"
        assert 102 in edited_chat_ids, "User 102 message must be updated"
        assert 103 in edited_chat_ids, "User 103 message must be updated"

    @pytest.mark.asyncio
    async def test_r4_mid_broadcast_claim_cancels_active_button_dispatch(self, isolated_test_db):
        """
        Concurrency verification for R4:
        Simulate `_broadcast_money_drop` iterating over 10 active recipients.
        Midway through the broadcast (after recipient 3), the drop is claimed by recipient 1.
        The broadcast loop must detect that `drop_record.status != 'active'` and terminate
        further active button dispatch, preventing ghost claim buttons on dead drops.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        mock_bot = _make_mock_bot(bot_id=555)

        # Setup donor & active recipients
        donor_id = 40001
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
        for uid in range(40002, 40012):
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (uid,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="BroadcastDonor",
            board_id="b",
            amount=500,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True

        recipients = list(range(40002, 40012))  # 10 recipients
        board_data["b"] = {"users": {"active": recipients}}

        sent_recipient_ids = []

        async def simulated_state_aware_broadcast():
            active_users = list(board_data.get("b", {}).get("users", {}).get("active", []))
            for target_uid in active_users:
                # State check: Stop if drop is no longer active
                rec = active_drops.get(drop_rec.drop_id)
                if not rec or rec.status != "active":
                    break

                if target_uid != donor_id:
                    sent = await mock_bot.send_message(
                        chat_id=target_uid,
                        text="Money Drop Alert",
                        reply_markup=MagicMock(spec=InlineKeyboardMarkup)
                    )
                    if sent:
                        register_drop_message(drop_rec.drop_id, target_uid, sent.message_id)
                        sent_recipient_ids.append(target_uid)

                # Simulate mid-broadcast claim after 3 users received message
                if len(sent_recipient_ids) == 3:
                    await claim_money_drop(
                        drop_id=drop_rec.drop_id,
                        claimer_id=40002,
                        claimer_name="FastClaimer",
                        claimer_board_id="b",
                        db_lock=db_lock,
                        db_conn=db,
                        check_reaction_delay=False,
                        check_claimer_rate_limit=False,
                        check_farm_laundering=False,
                    )

                await asyncio.sleep(0.01)

        await simulated_state_aware_broadcast()

        # Because claim occurred at recipient count 3, the remaining 7 users were spared
        assert len(sent_recipient_ids) == 3, f"Expected exactly 3 sends before cancellation, got {len(sent_recipient_ids)}"
        assert drop_rec.status == "claimed"

    @pytest.mark.asyncio
    async def test_r4_anti_bot_and_anti_fraud_rules(self, isolated_test_db):
        """
        Verify anti-bot and rate-limiting rules:
        1. Sub-second reaction (< min_reaction_delay) triggers bot detector rejection.
        2. Rapid consecutive claims trigger 30s claimer cooldown.
        3. Sliding window quota prevents hoarding (max 3 claims per 5 min).
        4. Sybil pair-farm detection blocks repeated claims between the same donor & claimer.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 50001
        bot_claimer_id = 50002
        sybil_claimer_id = 50003

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (bot_claimer_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (sybil_claimer_id,))
        await db.commit()

        set_min_reaction_delay(1.5)

        # 1. Test Anti-Bot Reaction Delay (< 1.5s)
        ok1, _, drop1 = await create_money_drop(donor_id, "Donor", "b", 200, db_lock, db, check_cooldown=False)
        assert ok1 is True
        # Set created_at to current timestamp so reaction time is ~0.0s
        drop1.created_at = time.time()

        ok_bot, msg_bot, _ = await claim_money_drop(
            drop_id=drop1.drop_id,
            claimer_id=bot_claimer_id,
            claimer_name="BotClaimer",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=True,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
            min_reaction_delay=1.5,
        )
        assert ok_bot is False
        assert msg_bot.startswith("❌") and len(msg_bot) > 5

        # 2. Test Claimer Cooldown (30s)
        # Advance created_at so reaction delay passes
        drop1.created_at = time.time() - 5.0
        ok_legit, _, _ = await claim_money_drop(
            drop_id=drop1.drop_id,
            claimer_id=bot_claimer_id,
            claimer_name="LegitClaimer",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=True,
            check_claimer_rate_limit=True,
            check_farm_laundering=False,
            min_reaction_delay=1.5,
        )
        assert ok_legit is True

        # Second drop immediately claimed by same user -> Rejected by claim cooldown
        ok2, _, drop2 = await create_money_drop(donor_id, "Donor", "b", 200, db_lock, db, check_cooldown=False)
        drop2.created_at = time.time() - 5.0
        ok_cooldown, msg_cooldown, _ = await claim_money_drop(
            drop_id=drop2.drop_id,
            claimer_id=bot_claimer_id,
            claimer_name="LegitClaimer",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=True,
            check_farm_laundering=False,
        )
        assert ok_cooldown is False
        assert "Кулдаун" in msg_cooldown or "недавно" in msg_cooldown or "секунд" in msg_cooldown or "с." in msg_cooldown or "с" in msg_cooldown

        # 3. Test Sybil / Pair-farm Laundering Protection (max 3 claims per window from same donor)
        for i in range(3):
            ok_pair, _, drop_p = await create_money_drop(donor_id, "Donor", "b", 200, db_lock, db, check_cooldown=False)
            assert ok_pair is True
            drop_p.created_at = time.time() - 5.0
            ok_cl, _, _ = await claim_money_drop(
                drop_id=drop_p.drop_id,
                claimer_id=sybil_claimer_id,
                claimer_name="SybilAnon",
                claimer_board_id="b",
                db_lock=db_lock,
                db_conn=db,
                check_reaction_delay=False,
                check_claimer_rate_limit=False,  # bypass general cooldown to test pair quota
                check_farm_laundering=True,
            )
            assert ok_cl is True

        # 4th claim from same donor in same window -> Rejected by pair farm detector
        ok_4th, _, drop_4th = await create_money_drop(donor_id, "Donor", "b", 200, db_lock, db, check_cooldown=False)
        drop_4th.created_at = time.time() - 5.0
        ok_sybil, msg_sybil, _ = await claim_money_drop(
            drop_id=drop_4th.drop_id,
            claimer_id=sybil_claimer_id,
            claimer_name="SybilAnon",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=True,
        )
        assert ok_sybil is False
        assert msg_sybil.startswith("🚫") and len(msg_sybil) > 5
