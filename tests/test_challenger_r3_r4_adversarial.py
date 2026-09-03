# -*- coding: utf-8 -*-
"""
Adversarial Verification and Stress Test Harness for Dvachbot R3 & R4.

Requirements under challenge:
- R3 (Archive Mirroring):
  1. System posts on completely empty boards (recipients = set(), 0 active/passive users)
     forwarded to _forward_post_to_realtime_archive and create valid ChannelCopies
     for ALL configured MIRROR_CHANNELS.
  2. Shadow mute vs archive_allowed precedence: shadow mute (is_shadow_muted=True) MUST
     strictly take precedence and block archiving even if archive_allowed=True.
     Conversely, archive_allowed=True MUST override archive_skip=True for non-shadow-muted posts.

- R4 (Money Drop State Machine & Concurrency):
  1. High-concurrency claim race: 50 (and 100) simultaneous claim attempts on a single money drop.
     Strictly 1 winner, exactly N-1 rejected, 0 double spending, closed-loop shekel conservation.
  2. Mid-broadcast claim during 100-user broadcast: When a claim occurs mid-way (e.g. at user 35),
     subsequent users (36-100) MUST NOT receive active claim buttons, and all prior messages
     must be edited to neutralize buttons.
  3. Drop expiration & refund: Expired drops refund donor balance in DB, update all recipient
     message copies removing buttons, and reject any late claims.
  4. Concurrent race: Claim vs Expire, and Claim vs Cancel.
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
import main


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


def _make_mock_bot(bot_id: int = 1, username: str = "dvach_challenger_bot"):
    bot = AsyncMock(spec=Bot)
    bot.id = bot_id
    bot.token = f"token_{bot_id}"
    bot.send_message = AsyncMock(return_value=_make_mock_message(message_id=100 + bot_id))
    bot.send_photo = AsyncMock(return_value=_make_mock_message(message_id=200 + bot_id, photo_fid=f"photo_{bot_id}"))
    bot.send_video = AsyncMock(return_value=_make_mock_message(message_id=300 + bot_id))
    bot.send_document = AsyncMock(return_value=_make_mock_message(message_id=400 + bot_id))
    bot.send_audio = AsyncMock(return_value=_make_mock_message(message_id=500 + bot_id))
    bot.send_animation = AsyncMock(return_value=_make_mock_message(message_id=600 + bot_id))
    bot.send_voice = AsyncMock(return_value=_make_mock_message(message_id=700 + bot_id))
    bot.send_sticker = AsyncMock(return_value=_make_mock_message(message_id=800 + bot_id))
    bot.send_video_note = AsyncMock(return_value=_make_mock_message(message_id=900 + bot_id))
    bot.send_media_group = AsyncMock(return_value=[_make_mock_message(message_id=1000 + bot_id)])
    bot.edit_message_text = AsyncMock(return_value=True)
    bot.edit_message_caption = AsyncMock(return_value=True)

    async def _mock_download(file, destination=None, **kwargs):
        if destination and hasattr(destination, 'write'):
            destination.write(b"mock_bytes")
        return b"mock_bytes"

    bot.download = AsyncMock(side_effect=_mock_download)
    return bot


@pytest.fixture(autouse=True)
def clean_challenger_env():
    reset_drop_cooldowns()
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()
    shared_state.GLOBAL_BOTS.clear()
    archive_manager.MIRROR_CHANNELS = [-1001111111111, -1002222222222, -1003333333333]
    board_data.clear()
    yield
    reset_drop_cooldowns()
    _BOT_INACCESSIBLE_CHANNELS.clear()
    _INACCESSIBLE_CHANNELS.clear()
    shared_state.GLOBAL_BOTS.clear()
    board_data.clear()


# =============================================================================
# REQUIREMENT R3: ARCHIVE MIRRORING EMPIRICAL CHALLENGES
# =============================================================================

class TestAdversarialR3ArchiveMirroring:
    """
    Empirical challenges on Requirement R3:
    1. System posts on completely empty boards (recipients = set(), 0 users).
    2. Multi-channel mirroring across all configured MIRROR_CHANNELS.
    3. Shadow mute vs archive_allowed precedence matrix.
    """

    @pytest.mark.asyncio
    async def test_r3_system_posts_on_completely_empty_board_mirrored_to_all_channels(self, isolated_test_db):
        """
        Adversarial Test:
        Simulate a quiet/empty board with 0 active users (recipients = set()).
        Ensure system posts (Airdrop, Abu notice, Trade Hub, PvP duel) generate
        valid ChannelCopies for ALL configured MIRROR_CHANNELS.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=101)
        shared_state.GLOBAL_BOTS["b"] = mock_bot

        mirror_channels = [-10010001, -10010002, -10010003]
        archive_manager.MIRROR_CHANNELS = list(mirror_channels)

        board_data["b"] = {
            "users": {"active": set(), "banned": set()},
            "threads": [],
            "threads_data": {}
        }

        system_post_samples = [
            (
                1001,
                {
                    "type": "text",
                    "text": "💸 <b>ЕЖЕНЕДЕЛЬНЫЙ АИРДРОП АБУ</b>: 100,000 ₪ распределено!",
                    "is_system_message": True,
                    "archive_allowed": True,
                    "author_id": 0
                }
            ),
            (
                1002,
                {
                    "type": "text",
                    "text": "📜 <b>ОБРАЩЕНИЕ АБУ</b>: Все серверы переведены на режим повышенной готовности.",
                    "is_system_message": True,
                    "archive_allowed": True,
                    "author_id": 0
                }
            ),
            (
                1003,
                {
                    "type": "text",
                    "text": "⚔️ <b>ИТОГИ ДУЭЛИ</b>: Анон #1 победил Анона #2 в Русской Рулетке (банк 20,000 ₪)!",
                    "is_system_message": True,
                    "archive_allowed": True
                }
            ),
            (
                1004,
                {
                    "type": "text",
                    "text": "🏪 <b>БАЗАР</b>: Новый легендарный лот выставлен на продажу.",
                    "is_system_message": True,
                    "archive_allowed": True,
                    "archive_skip": True  # archive_allowed MUST override archive_skip
                }
            )
        ]

        now = time.time()
        for pnum, content in system_post_samples:
            # 1. Insert into database using valid board 'b'
            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
                "VALUES (?, 'b', ?, ?, ?)",
                (pnum, content.get("author_id", 0), json.dumps(content), now)
            )

            # 2. Simulate delivery manager task with empty recipients
            msg_data = {
                "post_num": pnum,
                "board_id": "b",
                "content": content,
                "recipients": set(),  # COMPLETELY EMPTY RECIPIENT SET
                "enqueued_at": now
            }

            task = MessageDeliveryTask(
                worker_name="AdversarialWorker",
                board_id="b",
                bot_instance=mock_bot,
                queue=AsyncMock(),
                msg_data=msg_data
            )

            with patch("delivery_manager.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):
                await task.process()
                await asyncio.sleep(0.05)

            # 3. Verify ChannelCopies contains a record for EVERY mirror channel
            for ch_id in mirror_channels:
                async with db.execute(
                    "SELECT message_id FROM ChannelCopies WHERE post_num = ? AND channel_id = ?",
                    (pnum, ch_id)
                ) as cur:
                    row = await cur.fetchone()
                assert row is not None, f"Post #{pnum} on empty board MUST be copied to mirror channel {ch_id}"
                assert row[0] > 0

    @pytest.mark.asyncio
    async def test_r3_shadow_mute_vs_archive_allowed_precedence_matrix(self, isolated_test_db):
        """
        Adversarial Precedence Test:
        Evaluate all permutations of (is_shadow_muted, archive_allowed, archive_skip) across
        delivery_manager and post_processor pipeline.
        Invariants:
        - If is_shadow_muted is True: NEVER ARCHIVED, regardless of archive_allowed or archive_skip.
        - If is_shadow_muted is False and archive_skip is True: ARCHIVED IF AND ONLY IF archive_allowed is True.
        - If is_shadow_muted is False and archive_skip is False: ALWAYS ARCHIVED.
        """
        db = isolated_test_db
        mock_bot = _make_mock_bot(bot_id=102)
        shared_state.GLOBAL_BOTS["b"] = mock_bot
        mirror_channel = -1009999999999
        archive_manager.MIRROR_CHANNELS = [mirror_channel]
        board_data["b"] = {"users": {"active": set()}}
        now = time.time()

        test_matrix = [
            # (post_num, is_shadow_muted, archive_allowed, archive_skip, expected_archived)
            (2001, True,  True,  False, False),  # 1. Shadow-muted + archive_allowed -> BLOCKED
            (2002, True,  True,  True,  False),  # 2. Shadow-muted + archive_allowed + archive_skip -> BLOCKED
            (2003, True,  False, False, False),  # 3. Shadow-muted regular -> BLOCKED
            (2004, False, False, True,  False),  # 4. Not shadow-muted + archive_skip (no allowed) -> BLOCKED
            (2005, False, True,  True,  True),   # 5. Not shadow-muted + archive_skip + archive_allowed -> ARCHIVED
            (2006, False, True,  False, True),   # 6. Not shadow-muted + archive_allowed -> ARCHIVED
            (2007, False, False, False, True),   # 7. Not shadow-muted regular -> ARCHIVED
        ]

        for pnum, shadow_muted, arch_allowed, arch_skip, expected in test_matrix:
            content = {
                "type": "text",
                "text": f"Matrix test post #{pnum}",
                "is_shadow_muted": shadow_muted,
            }
            if arch_allowed is not None:
                content["archive_allowed"] = arch_allowed
            if arch_skip is not None:
                content["archive_skip"] = arch_skip

            await db.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) "
                "VALUES (?, 'b', 12345, ?, ?)",
                (pnum, json.dumps(content), now)
            )

            mock_bot.send_message.reset_mock()

            # Execute via MessageDeliveryTask to test the full pipeline decision
            msg_data = {
                "post_num": pnum,
                "board_id": "b",
                "content": content,
                "recipients": set(),
                "enqueued_at": now
            }
            task = MessageDeliveryTask(
                worker_name="MatrixWorker",
                board_id="b",
                bot_instance=mock_bot,
                queue=AsyncMock(),
                msg_data=msg_data
            )
            with patch("delivery_manager.spawn_task", side_effect=lambda coro: asyncio.create_task(coro)):
                await task.process()
                await asyncio.sleep(0.05)

            async with db.execute(
                "SELECT message_id FROM ChannelCopies WHERE post_num = ? AND channel_id = ?",
                (pnum, mirror_channel)
            ) as cur:
                row = await cur.fetchone()

            if expected:
                assert row is not None, (
                    f"Post #{pnum} (shadow={shadow_muted}, allowed={arch_allowed}, skip={arch_skip}) "
                    f"MUST be archived, but no ChannelCopies found"
                )
            else:
                assert row is None, (
                    f"Post #{pnum} (shadow={shadow_muted}, allowed={arch_allowed}, skip={arch_skip}) "
                    f"MUST NOT be archived, but ChannelCopies entry {row} was created!"
                )


# =============================================================================
# REQUIREMENT R4: MONEY DROP STATE MACHINE & CONCURRENCY CHALLENGES
# =============================================================================

class TestAdversarialR4MoneyDropConcurrencyAndStateMachine:
    """
    Empirical challenges on Requirement R4:
    1. 50 (and 100) concurrent claim attempts on a single money drop.
    2. Mid-broadcast claim during 100-user broadcast (button neutralization & loop cutoff).
    3. Drop expiration & refund: all recipient copies edited, donor refunded.
    4. Concurrency race: Claim vs Expire, and Claim vs Cancel.
    """

    @pytest.mark.asyncio
    async def test_r4_50_concurrent_claims_strictly_one_winner_zero_double_spend(self, isolated_test_db):
        """
        Adversarial Concurrency Stress Test:
        50 concurrent workers attempt to claim a single 5,000 ₪ money drop at the exact same microsecond.
        Verifies:
        - Exactly 1 winner (status 'claimed').
        - Exactly 49 rejected claimers.
        - Closed-loop shekel conservation: Total system shekels before == Total system shekels after.
        - Zero double spending (0.0 ₪ discrepancy).
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 90000
        claimer_ids = list(range(90001, 90051))  # 50 concurrent claimers
        drop_amount = 5000

        # Initial balances: Donor has 50,000 ₪, each claimer has 0 ₪
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000)", (donor_id,))
        for cid in claimer_ids:
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (cid,))
        await db.commit()

        # Compute initial total system money
        async with db.execute("SELECT SUM(balance) FROM Users") as cur:
            initial_system_shekels = (await cur.fetchone())[0]
        assert initial_system_shekels == 50000

        # Step 1: Donor creates drop of 5,000 ₪
        ok, msg, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="GenerousSych",
            board_id="b",
            amount=drop_amount,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True, f"Drop creation failed: {msg}"
        assert drop_rec is not None
        drop_id = drop_rec.drop_id

        # Verify donor balance debited to 45,000 ₪
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            donor_bal = (await cur.fetchone())[0]
        assert donor_bal == 45000

        # Step 2: Launch 50 concurrent claim attempts simultaneously
        async def _attempt_claim(cid: int):
            return await claim_money_drop(
                drop_id=drop_id,
                claimer_id=cid,
                claimer_name=f"Claimer_{cid}",
                claimer_board_id="b",
                db_lock=db_lock,
                db_conn=db,
                check_reaction_delay=False,
                check_claimer_rate_limit=False,
                check_farm_laundering=False,
            )

        tasks = [_attempt_claim(cid) for cid in claimer_ids]
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        elapsed_time = time.perf_counter() - start_time

        successes = [r for r in results if r[0] is True]
        rejections = [r for r in results if r[0] is False]

        # Empirical proof assertions:
        assert len(successes) == 1, f"CRITICAL: Expected exactly 1 winner, but got {len(successes)}!"
        assert len(rejections) == 49, f"CRITICAL: Expected exactly 49 rejections, but got {len(rejections)}!"

        winner_rec = successes[0][2]
        winner_id = winner_rec.claimed_by
        assert winner_id in claimer_ids
        assert winner_rec.status == "claimed"

        # Verify winner balance is exactly 5,000 ₪
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (winner_id,)) as cur:
            winner_balance = (await cur.fetchone())[0]
        assert winner_balance == drop_amount

        # Verify other 49 claimers still have exactly 0 ₪
        async with db.execute(
            "SELECT COUNT(*) FROM Users WHERE user_id IN (%s) AND balance = 0" % ",".join(map(str, claimer_ids))
        ) as cur:
            zero_balance_count = (await cur.fetchone())[0]
        assert zero_balance_count == 49

        # Verify total final system money matches initial (closed loop)
        async with db.execute("SELECT SUM(balance) FROM Users") as cur:
            final_system_shekels = (await cur.fetchone())[0]
        assert final_system_shekels == initial_system_shekels, (
            f"Double spending detected! Initial: {initial_system_shekels} ₪, Final: {final_system_shekels} ₪"
        )

        # Verify MoneyDrops table consistency
        async with db.execute("SELECT status, claimed_by, amount FROM MoneyDrops WHERE drop_id = ?", (drop_id,)) as cur:
            db_row = await cur.fetchone()
        assert db_row[0] == "claimed"
        assert db_row[1] == winner_id
        assert db_row[2] == drop_amount

    @pytest.mark.asyncio
    async def test_r4_100_concurrent_claims_stress_scale(self, isolated_test_db):
        """
        Scale test: 100 simultaneous workers hammering a single drop.
        Strictly 1 winner, 99 rejections, 0 double spending.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 95000
        claimer_ids = list(range(95001, 95101))  # 100 claimers
        drop_amount = 10000

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 100000)", (donor_id,))
        for cid in claimer_ids:
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (cid,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="StressDonor",
            board_id="b",
            amount=drop_amount,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True

        tasks = [
            claim_money_drop(
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
            for cid in claimer_ids
        ]

        results = await asyncio.gather(*tasks)
        successes = [r for r in results if r[0] is True]
        rejections = [r for r in results if r[0] is False]

        assert len(successes) == 1
        assert len(rejections) == 99

        async with db.execute("SELECT SUM(balance) FROM Users") as cur:
            total_bal = (await cur.fetchone())[0]
        assert total_bal == 100000

    @pytest.mark.asyncio
    async def test_r4_mid_broadcast_claim_100_users_neutralization(self, isolated_test_db):
        """
        Adversarial Test:
        Simulate `_broadcast_money_drop` broadcasting to 100 active users.
        At user #35, user #10 claims the drop.
        Verifications:
        1. Broadcast loop breaks immediately after user #35; users #36-#100 NEVER receive messages.
        2. `_update_all_drop_messages` edits messages for users #1-#35 (excluding winner #10),
           removing the active claim button (reply_markup=None).
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        mock_bot = _make_mock_bot(bot_id=201)

        donor_id = 80000
        recipient_ids = list(range(80001, 80101))  # 100 users
        winner_id = 80010

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 50000)", (donor_id,))
        for uid in recipient_ids:
            await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (uid,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="MidBroadcastDonor",
            board_id="b",
            amount=2000,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True
        drop_id = drop_rec.drop_id

        board_data["b"] = {"users": {"active": recipient_ids}}

        sent_to_uids = []

        async def _mock_send_message(chat_id, *args, **kwargs):
            sent_to_uids.append(chat_id)
            # When user 35 receives the message, user 10 claims the drop!
            if len(sent_to_uids) == 35:
                await claim_money_drop(
                    drop_id=drop_id,
                    claimer_id=winner_id,
                    claimer_name="FastClaimer",
                    claimer_board_id="b",
                    db_lock=db_lock,
                    db_conn=db,
                    check_reaction_delay=False,
                    check_claimer_rate_limit=False,
                    check_farm_laundering=False,
                )
            return _make_mock_message(message_id=5000 + len(sent_to_uids))

        mock_bot.send_message.side_effect = _mock_send_message
        mock_bot.send_photo.side_effect = _mock_send_message

        # Execute broadcast
        await main._broadcast_money_drop(
            bot=mock_bot,
            board_id="b",
            drop_id=drop_id,
            exclude_chat_id=donor_id,
            photo_payload=None,
            caption="Money drop!",
            kb=MagicMock(spec=InlineKeyboardMarkup)
        )

        # 1. Verification of early broadcast termination:
        # Loop must have stopped at user 35!
        assert len(sent_to_uids) == 35, (
            f"Broadcast did NOT stop upon mid-broadcast claim! Sent to {len(sent_to_uids)} users instead of 35"
        )
        assert set(sent_to_uids) == set(recipient_ids[:35])

        # Verify registered message copies
        registered_msgs = get_drop_messages(drop_id)
        assert len(registered_msgs) == 35

        # 2. Verification of message neutralization:
        update_text = "💸 <b>ДРОП ПЕРЕХВАЧЕН!</b> Победитель: Анон #80010"
        await main._update_all_drop_messages(
            bot=mock_bot,
            drop_id=drop_id,
            new_text=update_text,
            exclude_chat_id=winner_id
        )

        # Winner chat must be excluded, all other 34 chats must be edited with reply_markup=None
        edited_chats = [
            call.kwargs.get("chat_id")
            for call in (mock_bot.edit_message_caption.call_args_list + mock_bot.edit_message_text.call_args_list)
        ]
        assert winner_id not in edited_chats, "Winner chat must not be edited by bulk updater"
        assert len(edited_chats) == 34, f"Expected 34 edited messages, got {len(edited_chats)}"

    @pytest.mark.asyncio
    async def test_r4_drop_expiration_message_cleanup_and_donor_refund(self, isolated_test_db):
        """
        Adversarial Test:
        1. Donor creates drop, message copies are registered across 50 users.
        2. Fast-forward expiration.
        3. Run expiration step.
        4. Verify:
           - All 50 message copies are edited to remove claim button.
           - Donor balance is 100% refunded in SQLite.
           - Drop status transitions to 'expired'.
           - Late claim attempts return informative error.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        mock_bot = _make_mock_bot(bot_id=202)
        shared_state.GLOBAL_BOTS["b"] = mock_bot

        donor_id = 70001
        late_claimer_id = 70002
        drop_amount = 3500

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (late_claimer_id,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="ExpireDonor",
            board_id="b",
            amount=drop_amount,
            db_lock=db_lock,
            db_conn=db,
            timeout_sec=0.1,  # Short expiration
            check_cooldown=False,
        )
        assert ok is True
        drop_id = drop_rec.drop_id

        # Register 50 recipient message copies
        for uid in range(70100, 70150):
            register_drop_message(drop_id, uid, uid + 10000)
        assert len(get_drop_messages(drop_id)) == 50

        # Fast-forward time past expiration
        drop_rec.expires_at = time.time() - 10.0

        # Execute expiration step
        expired_list = await expire_unclaimed_drops_step(db_lock, db)
        assert len(expired_list) == 1
        assert expired_list[0].drop_id == drop_id
        assert expired_list[0].status == "expired"

        # Verify donor balance restored to 10,000 ₪
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            restored_bal = (await cur.fetchone())[0]
        assert restored_bal == 10000

        # Verify SQLite status
        async with db.execute("SELECT status, refunded_at FROM MoneyDrops WHERE drop_id = ?", (drop_id,)) as cur:
            row = await cur.fetchone()
        assert row[0] == "expired"
        assert row[1] is not None

        # Neutralize all 50 messages
        expiry_text = "⏳ <b>ДРОП ШЕКЕЛЕЙ ИСТЕК</b>\nШекели возвращены донору."
        await main._update_all_drop_messages(mock_bot, drop_id, expiry_text)

        edited_chats = [
            call.kwargs.get("chat_id")
            for call in (mock_bot.edit_message_caption.call_args_list + mock_bot.edit_message_text.call_args_list)
        ]
        assert len(edited_chats) == 50, f"Expected 50 edited messages, got {len(edited_chats)}"

        # Late claim attempt MUST be rejected
        ok_late, msg_late, _ = await claim_money_drop(
            drop_id=drop_id,
            claimer_id=late_claimer_id,
            claimer_name="LateGuy",
            claimer_board_id="b",
            db_lock=db_lock,
            db_conn=db,
            check_reaction_delay=False,
            check_claimer_rate_limit=False,
            check_farm_laundering=False,
        )
        assert ok_late is False
        assert "истекло" in msg_late

    @pytest.mark.asyncio
    async def test_r4_race_condition_claim_vs_expire_concurrency(self, isolated_test_db):
        """
        Adversarial Race Test:
        Claim and Expire trigger at the EXACT same millisecond.
        Verifies:
        - Mutual exclusion: EITHER claim succeeds OR expire succeeds.
        - Never both: Zero possibility of donor refund + claimer payout (no double spending).
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 60001
        claimer_id = 60002
        drop_amount = 1500

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 5000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (claimer_id,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="RaceDonor",
            board_id="b",
            amount=drop_amount,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True
        drop_id = drop_rec.drop_id

        # Set expiration to current timestamp
        drop_rec.expires_at = time.time()

        # Run claim and expire concurrently
        async def _run_claim():
            return await claim_money_drop(
                drop_id=drop_id,
                claimer_id=claimer_id,
                claimer_name="RacyClaimer",
                claimer_board_id="b",
                db_lock=db_lock,
                db_conn=db,
                check_reaction_delay=False,
                check_claimer_rate_limit=False,
                check_farm_laundering=False,
            )

        async def _run_expire():
            return await expire_unclaimed_drops_step(db_lock, db)

        claim_res, expire_res = await asyncio.gather(_run_claim(), _run_expire())

        claim_ok = claim_res[0]
        expire_ok = len(expire_res) > 0 and expire_res[0].drop_id == drop_id

        # Exactly ONE must succeed
        assert (claim_ok ^ expire_ok) is True, (
            f"Race collision! claim_ok={claim_ok}, expire_ok={expire_ok}. Must be strictly XOR."
        )

        # Check closed-loop balance invariant
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            donor_bal = (await cur.fetchone())[0]
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (claimer_id,)) as cur:
            claimer_bal = (await cur.fetchone())[0]

        assert (donor_bal + claimer_bal) == 5000, (
            f"Money conservation broken! donor={donor_bal}, claimer={claimer_bal}, sum={donor_bal + claimer_bal} != 5000"
        )

    @pytest.mark.asyncio
    async def test_r4_race_condition_claim_vs_cancel_concurrency(self, isolated_test_db):
        """
        Adversarial Race Test:
        Claim and Donor Cancel trigger at the EXACT same millisecond.
        Verifies:
        - Mutual exclusion: EITHER claim succeeds OR cancel succeeds.
        - Total system money invariant strictly conserved.
        """
        db = isolated_test_db
        db_lock = asyncio.Lock()
        donor_id = 50001
        claimer_id = 50002
        drop_amount = 2000

        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 10000)", (donor_id,))
        await db.execute("INSERT INTO Users (user_id, board_id, balance) VALUES (?, 'b', 0)", (claimer_id,))
        await db.commit()

        ok, _, drop_rec = await create_money_drop(
            donor_id=donor_id,
            donor_name="CancelRaceDonor",
            board_id="b",
            amount=drop_amount,
            db_lock=db_lock,
            db_conn=db,
            check_cooldown=False,
        )
        assert ok is True
        drop_id = drop_rec.drop_id

        async def _run_claim():
            return await claim_money_drop(
                drop_id=drop_id,
                claimer_id=claimer_id,
                claimer_name="RaceClaimer",
                claimer_board_id="b",
                db_lock=db_lock,
                db_conn=db,
                check_reaction_delay=False,
                check_claimer_rate_limit=False,
                check_farm_laundering=False,
            )

        async def _run_cancel():
            return await cancel_money_drop(drop_id, donor_id, db_lock, db)

        claim_res, cancel_res = await asyncio.gather(_run_claim(), _run_cancel())

        claim_ok = claim_res[0]
        cancel_ok = cancel_res[0]

        assert (claim_ok ^ cancel_ok) is True, (
            f"Race collision! claim_ok={claim_ok}, cancel_ok={cancel_ok}. Must be strictly XOR."
        )

        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (donor_id,)) as cur:
            donor_bal = (await cur.fetchone())[0]
        async with db.execute("SELECT balance FROM Users WHERE user_id = ?", (claimer_id,)) as cur:
            claimer_bal = (await cur.fetchone())[0]

        assert (donor_bal + claimer_bal) == 10000, (
            f"Money conservation broken! donor={donor_bal}, claimer={claimer_bal}, sum={donor_bal + claimer_bal} != 10000"
        )
