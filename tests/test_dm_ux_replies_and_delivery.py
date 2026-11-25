import asyncio
import html
import os
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_sent_msg(msg_id: int, file_id: str | None = None, content_type: str = "photo") -> MagicMock:
    m = MagicMock(spec=types.Message)
    m.message_id = msg_id
    m.photo = [SimpleNamespace(file_id=file_id)] if (file_id and content_type == "photo") else None
    m.video = SimpleNamespace(file_id=file_id) if (file_id and content_type == "video") else None
    m.animation = SimpleNamespace(file_id=file_id) if (file_id and content_type == "animation") else None
    m.document = SimpleNamespace(file_id=file_id) if (file_id and content_type == "document") else None
    m.audio = SimpleNamespace(file_id=file_id) if (file_id and content_type == "audio") else None
    m.voice = SimpleNamespace(file_id=file_id) if (file_id and content_type == "voice") else None
    return m


# ---------------------------------------------------------------------------
# 1. Cross-bot wrong file_id recovery, chunk-1 probe, singleflight & banners
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_bot_wrong_file_id_singleflight_and_chunk_probe(tmp_path):
    """
    25 recipients receive a photo post whose cached banner file_id belongs to another bot.
    - Chunk-1 probe sends to user #1 alone before fanning out to the rest.
    - Buffer is downloaded ONCE (from local banner fallback / pool), broken banner cache
      entry is evicted & updated, register_file_owner + add_file_mirror are recorded.
    - Recipients #2..#25 directly receive the healed file_id without 24 extra downloads.
    """
    import banner_manager
    import shared_state
    from broadcaster import MessageBroadcaster
    from shared_state import BroadcastConfig

    old_fid = "AgACAgIAAxk_OLD_BOT1_FILE_ID"
    new_fid = "AgACAgIAAxk_HEALED_BOT2_FILE_ID"
    fname = "shop_test_banner.jpg"
    banner_file = tmp_path / fname
    banner_file.write_bytes(b"JPEG_BANNER_BYTES_123")

    bot = AsyncMock()
    bot.id = 8330160701

    call_log = []
    next_mid = 1000

    async def fake_send_photo(**kwargs):
        nonlocal next_mid
        src = kwargs.get("photo")
        uid = kwargs.get("chat_id")
        call_log.append((uid, type(src).__name__, src if isinstance(src, str) else "BufferedInputFile"))
        if src == old_fid:
            raise TelegramBadRequest(
                method="sendPhoto",
                message="Telegram server says - Bad Request: wrong file identifier/HTTP URL specified",
            )
        next_mid += 1
        return _make_sent_msg(next_mid, file_id=new_fid, content_type="photo")

    bot.send_photo = AsyncMock(side_effect=fake_send_photo)

    recipients = list(range(101, 126))
    content = {
        "type": "photo",
        "file_id": old_fid,
        "banner_filename": fname,
        "text": "Shop promo banner",
        "header": "Аноним №1",
    }

    fake_cache = {"8330160701:shop_test_banner.jpg": old_fid, "7823520763:shop_test_banner.jpg": old_fid}
    fake_by_fname = {fname: old_fid}
    fake_board = {"thread": {"users": {"active": set(recipients), "banned": set()}, "user_settings": {}}}

    with (
        patch.dict(shared_state.board_data, fake_board, clear=True),
        patch.object(banner_manager, "_BANNER_CACHE", fake_cache),
        patch.object(banner_manager, "_CACHE_BY_FILENAME", fake_by_fname),
        patch.object(banner_manager, "BANNERS_DIR", str(tmp_path)),
        patch.object(banner_manager, "save_cache", MagicMock()),
        patch("broadcaster.get_file_mirrors", AsyncMock(return_value={})),
        patch("broadcaster.get_file_owner_id", AsyncMock(return_value=None)),
        patch("broadcaster.register_file_owner", AsyncMock()) as reg_owner_mock,
        patch("broadcaster.add_file_mirror", AsyncMock()) as add_mirror_mock,
        patch("broadcaster.add_post_copies", AsyncMock()),
    ):
        bc = MessageBroadcaster(
            BroadcastConfig(
                bot_instance=bot,
                board_id="thread",
                recipients=recipients,
                content=content,
            )
        )
        await bc.broadcast()
        await asyncio.sleep(0)

    assert bc.stats["success"] == 25
    assert bc.stats["errors"] == 0
    old_fid_failures = [c for c in call_log if c[2] == old_fid]
    buf_uploads = [c for c in call_log if c[2] == "BufferedInputFile"]
    healed_deliveries = [c for c in call_log if c[2] == new_fid]
    assert len(old_fid_failures) == 1
    assert len(buf_uploads) == 1
    assert len(healed_deliveries) == 24
    assert fake_cache["8330160701:shop_test_banner.jpg"] == new_fid
    assert fname not in fake_by_fname
    reg_owner_mock.assert_any_call(new_fid, 8330160701)
    add_mirror_mock.assert_any_call(old_fid, "tg_bot_8330160701", new_fid)


@pytest.mark.asyncio
async def test_prewarm_cross_bot_media_uses_existing_file_mirror():
    """
    When FileMirrors already holds tg_bot_{target_bot_id}, _prewarm_cross_bot_media swaps
    it BEFORE the broadcast begins so zero recipients suffer TelegramBadRequest.
    """
    import shared_state
    from broadcaster import MessageBroadcaster
    from shared_state import BroadcastConfig

    old_fid = "OLD_BOT_A_FID"
    mirror_fid = "MIRROR_BOT_B_FID"
    bot = AsyncMock()
    bot.id = 8330160701
    bot.send_photo = AsyncMock(return_value=_make_sent_msg(555, file_id=mirror_fid))

    content = {"type": "photo", "file_id": old_fid, "text": "Mirror test", "header": "Аноним"}
    fake_board = {"thread": {"users": {"active": {201, 202}, "banned": set()}, "user_settings": {}}}

    with (
        patch.dict(shared_state.board_data, fake_board, clear=True),
        patch("broadcaster.get_file_mirrors", AsyncMock(return_value={f"tg_bot_{bot.id}": mirror_fid})),
        patch("broadcaster.get_file_owner_id", AsyncMock(return_value=7823520763)),
        patch("broadcaster.register_file_owner", AsyncMock()),
        patch("broadcaster.add_file_mirror", AsyncMock()),
        patch("broadcaster.add_post_copies", AsyncMock()),
    ):
        bc = MessageBroadcaster(
            BroadcastConfig(
                bot_instance=bot,
                board_id="thread",
                recipients=[201, 202],
                content=content,
            )
        )
        await bc.broadcast()

    assert bc.stats["success"] == 2
    assert all(call.kwargs["photo"] == mirror_fid for call in bot.send_photo.call_args_list)


@pytest.mark.asyncio
async def test_media_group_cross_bot_file_id_healed_without_losing_items():
    """
    Album delivery with cross-bot file_id triggering 'wrong file identifier' heals items
    into BufferedInputFile via _download_media_bytes_resilient instead of dropping album items.
    """
    import shared_state
    from broadcaster import MessageBroadcaster
    from shared_state import BroadcastConfig

    old_1 = "ALBUM_OLD_1"
    old_2 = "ALBUM_OLD_2"
    healed_1 = "ALBUM_NEW_1"
    healed_2 = "ALBUM_NEW_2"
    bot = AsyncMock()
    bot.id = 8330160701

    attempt_sources = []

    async def fake_send_media_group(**kwargs):
        media_list = kwargs["media"]
        attempt_sources.append([type(m.media).__name__ for m in media_list])
        if any(m.media == old_2 for m in media_list):
            raise TelegramBadRequest(
                method="sendMediaGroup",
                message="Bad Request: failed to send message #2: wrong file identifier/HTTP URL specified",
            )
        return [_make_sent_msg(701, file_id=healed_1), _make_sent_msg(702, file_id=healed_2)]

    bot.send_media_group = AsyncMock(side_effect=fake_send_media_group)

    content = {
        "type": "media_group",
        "media": [
            {"type": "photo", "media": old_1, "file_id": old_1},
            {"type": "photo", "media": old_2, "file_id": old_2},
        ],
        "caption": "Album caption",
        "header": "Аноним",
    }
    fake_board = {"thread": {"users": {"active": {301, 302}, "banned": set()}, "user_settings": {}}}

    with (
        patch.dict(shared_state.board_data, fake_board, clear=True),
        patch("broadcaster.get_file_mirrors", AsyncMock(return_value={})),
        patch("broadcaster.get_file_owner_id", AsyncMock(return_value=None)),
        patch("broadcaster.register_file_owner", AsyncMock()),
        patch("broadcaster.add_file_mirror", AsyncMock()),
        patch("broadcaster.add_post_copies", AsyncMock()),
        patch.object(
            MessageBroadcaster,
            "_download_media_bytes_resilient",
            AsyncMock(return_value=(b"FAKE_IMG_DATA", "album_2.jpg")),
        ) as dl_mock,
    ):
        bc = MessageBroadcaster(
            BroadcastConfig(
                bot_instance=bot,
                board_id="thread",
                recipients=[301, 302],
                content=content,
            )
        )
        await bc.broadcast()

    assert bc.stats["success"] == 2
    assert dl_mock.await_count == 1
    assert len(content["media"]) == 2
    assert content["media"][1]["file_id"] == healed_2
    assert attempt_sources[1] == ["str", "BufferedInputFile"]


@pytest.mark.asyncio
async def test_bot_pool_download_media_bytes_with_pool_tries_owner_and_cooldowns_bad_bot():
    """MultiStreamBotPool.download_media_bytes_with_pool falls back to pool bot and puts 429 bots on cooldown."""
    from common.bot_pool import MultiStreamBotPool

    pool = MultiStreamBotPool()
    bad_owner = AsyncMock()
    bad_owner.id = 111
    bad_owner.get_file = AsyncMock(side_effect=TelegramRetryAfter(method="getFile", message="Too Many Requests", retry_after=30))

    good_pool_bot = AsyncMock()
    good_pool_bot.id = 222
    good_pool_bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="photos/test.jpg"))

    async def fake_download(file_path, destination):
        destination.write(b"RECOVERED_BYTES")

    good_pool_bot.download_file = AsyncMock(side_effect=fake_download)

    pool.register_external_bot(bad_owner)
    pool.register_external_bot(good_pool_bot)

    data = await pool.download_media_bytes_with_pool(
        "SOME_FID",
        owner_id=111,
        extra_bots=[bad_owner],
    )
    assert data == b"RECOVERED_BYTES"
    assert 111 in pool.cooldown_bots


# ---------------------------------------------------------------------------
# 2. Long caption UTF-16 splitting & follow-up message ID capture for replies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_photo_emoji_utf16_overflow_splits_and_returns_followup_msg_id():
    """
    550 astral emojis have len()==550 in Python str, but 1100 UTF-16 code units (>1024 Telegram limit).
    Broadcaster MUST send photo without overflowing caption and return [media_msg, text_msg]
    so replies to the follow-up text message resolve back to post_num.
    """
    import shared_state
    from broadcaster import MessageBroadcaster
    from shared_state import BroadcastConfig

    bot = AsyncMock()
    bot.id = 7823520763
    media_msg = _make_sent_msg(8001, file_id="FID_OK")
    text_msg = _make_sent_msg(8002, file_id=None)
    bot.send_photo = AsyncMock(return_value=media_msg)
    bot.send_message = AsyncMock(return_value=text_msg)

    emoji_text = "😀" * 550  # len == 550, utf16 == 1100 > 1024
    content = {"type": "photo", "file_id": "FID_OK", "caption": emoji_text, "header": "Аноним", "post_num": 999001}
    fake_board = {"b": {"users": {"active": {401}, "banned": set()}, "user_settings": {}}}

    saved_copies = []

    async def capture_copies(post_num, copies):
        saved_copies.extend(copies)

    with (
        patch.dict(shared_state.board_data, fake_board, clear=True),
        patch("broadcaster.get_file_mirrors", AsyncMock(return_value={})),
        patch("broadcaster.get_file_owner_id", AsyncMock(return_value=bot.id)),
        patch("broadcaster.register_file_owner", AsyncMock()),
        patch("broadcaster.add_post_copies", AsyncMock(side_effect=capture_copies)),
    ):
        bc = MessageBroadcaster(
            BroadcastConfig(
                bot_instance=bot,
                board_id="b",
                recipients=[401],
                content=content,
            )
        )
        await bc.broadcast()

    assert bc.stats["success"] == 1
    assert "caption" not in bot.send_photo.call_args.kwargs
    bot.send_message.assert_awaited_once()
    copy_mids = {mid for (_, mid) in saved_copies}
    assert {8001, 8002}.issubset(copy_mids)


# ---------------------------------------------------------------------------
# 3. DM Replies (RAM eviction -> PostCopies, forward_origin, external_reply, ZW/URL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_reply_from_message_ram_eviction_and_forward_origin():
    """
    When RAM message_to_post & messages_storage are cleared, resolve_reply_from_message
    resolves via SQLite PostCopies / forward_origin / external_reply and hydrates RAM.
    """
    import shared_state
    from handlers.message_router import resolve_reply_from_message

    post_num = 515151
    fake_post = {
        "post_num": post_num,
        "author_id": 777777,
        "timestamp": 1700000000,
        "content": {"type": "text", "text": "Ancient post text"},
        "board_id": "b",
        "thread_id": None,
        "reply_to_post_num": None,
    }

    reply_msg = MagicMock(spec=types.Message)
    reply_msg.chat = SimpleNamespace(id=501, type="private")
    reply_msg.from_user = SimpleNamespace(id=999)
    reply_msg.message_id = 4444
    reply_msg.text = "Старый пост"
    reply_msg.caption = None
    reply_msg.entities = []
    reply_msg.caption_entities = []
    reply_msg.forward_from_chat = None
    reply_msg.forward_from_message_id = None
    reply_msg.forward_origin = None
    reply_msg.external_reply = None

    with (
        patch.dict(shared_state.message_to_post, {}, clear=True),
        patch.dict(shared_state.messages_storage, {}, clear=True),
        patch("handlers.message_router.get_post_info_by_copy", AsyncMock(return_value=(post_num, "b"))) as copy_mock,
        patch("handlers.message_router.get_post_by_num", AsyncMock(return_value=fake_post)),
    ):
        resolved = await resolve_reply_from_message(reply_msg, chat_id=501)
        assert resolved == post_num
        assert shared_state.message_to_post[(501, 4444)] == post_num
        assert post_num in shared_state.messages_storage
        copy_mock.assert_awaited_once_with(501, 4444)

    # Also test Bot API 7 forward_origin
    fwd_msg = MagicMock(spec=types.Message)
    fwd_msg.chat = SimpleNamespace(id=501, type="private")
    fwd_msg.from_user = SimpleNamespace(id=501)
    fwd_msg.message_id = 4445
    fwd_msg.text = None
    fwd_msg.caption = None
    fwd_msg.entities = []
    fwd_msg.caption_entities = []
    fwd_msg.forward_from_chat = None
    fwd_msg.forward_from_message_id = None
    fwd_msg.forward_origin = SimpleNamespace(chat=SimpleNamespace(id=-100999), message_id=888)
    fwd_msg.external_reply = None

    async def copy_by_chat(cid, mid):
        if cid == -100999 and mid == 888:
            return (post_num, "b")
        return None

    with (
        patch.dict(shared_state.message_to_post, {}, clear=True),
        patch.dict(shared_state.messages_storage, {}, clear=True),
        patch("handlers.message_router.get_post_info_by_copy", AsyncMock(side_effect=copy_by_chat)),
        patch("handlers.message_router.get_post_by_num", AsyncMock(return_value=fake_post)),
    ):
        resolved_fwd = await resolve_reply_from_message(fwd_msg, chat_id=501)
        assert resolved_fwd == post_num


@pytest.mark.asyncio
async def test_get_post_num_by_reply_5_tier_fallback_and_tgach_url():
    """common.bot_helpers.get_post_num_by_reply uses DB copy, tgach URL entities, and zero-width markers."""
    import shared_state
    from common.bot_helpers import get_post_num_by_reply
    from post_helpers import encode_post_num_zw, extract_post_num_from_message

    msg = MagicMock(spec=types.Message)
    msg.chat = SimpleNamespace(id=601, type="private")
    msg.from_user = SimpleNamespace(id=601)
    msg.message_id = 333
    msg.text = "Открыть на сайте"
    msg.caption = None
    msg.entities = [SimpleNamespace(type="text_link", url="https://tgach.top/b/res/deadbeef.html#777123")]
    msg.caption_entities = []
    msg.forward_from_chat = None
    msg.forward_from_message_id = None
    msg.forward_origin = None

    assert extract_post_num_from_message(msg) == 777123

    # Test Tier 4 ZW decoding through get_post_num_by_reply(outer_message)
    msg_zw = MagicMock(spec=types.Message)
    msg_zw.chat = SimpleNamespace(id=601, type="private")
    msg_zw.from_user = SimpleNamespace(id=601)
    msg_zw.message_id = 334
    msg_zw.text = f"Аноним{encode_post_num_zw(777124)}"
    msg_zw.caption = None
    msg_zw.entities = []
    msg_zw.caption_entities = []
    msg_zw.forward_from_chat = None
    msg_zw.forward_from_message_id = None
    msg_zw.forward_origin = None
    outer_msg = SimpleNamespace(reply_to_message=msg_zw)

    with (
        patch.dict(shared_state.message_to_post, {}, clear=True),
        patch("common.database.get_post_info_by_copy", AsyncMock(return_value=None)),
        patch("common.database.get_post_by_num", AsyncMock(return_value={"post_num": 777124})),
    ):
        found = await get_post_num_by_reply(outer_msg)
        assert found == 777124
        assert shared_state.message_to_post[(601, 334)] == 777124


@pytest.mark.asyncio
async def test_handle_message_preserves_html_and_warns_on_deleted_reply_in_dm():
    """
    1) Inline reply `>>500123 <b>Жирный</b>` in handle_message preserves <b>...</b> HTML tags.
    2) Replying in DM to a deleted post (#500999 in text but missing in DB) notifies the DM user.
    """
    import shared_state
    from handlers.message_router import handle_message

    bot = AsyncMock()
    bot.id = 7823520763
    sent_warn = _make_sent_msg(9001)
    bot.send_message = AsyncMock(return_value=sent_warn)

    msg = MagicMock(spec=types.Message)
    msg.chat = SimpleNamespace(id=701, type="private")
    msg.from_user = SimpleNamespace(id=701, username="tester", first_name="Test", is_bot=False)
    msg.message_id = 100
    msg.content_type = "text"
    msg.text = ">>500123 Жирный текст"
    msg.html_text = "&gt;&gt;500123 <b>Жирный текст</b>"
    msg.caption = None
    msg.reply_to_message = None
    msg.forward_from = None
    msg.forward_from_chat = None
    msg.forward_origin = None
    msg.entities = []
    msg.delete = AsyncMock()
    msg.bot = bot

    b_data = {
        "users": {"active": {701}, "banned": set()},
        "user_settings": {701: {"nsfw": False, "hide": set(), "disable_ai_roasts": False, "hide_ai_slop": False}},
        "mutes": {},
        "shadow_mutes": {},
    }

    captured_params = {}

    async def fake_process_new_post(params):
        captured_params["content"] = params.content
        captured_params["reply_to_post"] = params.reply_to_post
        return 500124

    with (
        patch.dict(shared_state.board_data, {"b": b_data}, clear=True),
        patch.dict(shared_state.messages_storage, {500123: {"author_id": 888, "content": {"type": "text", "text": "op"}}}, clear=True),
        patch("handlers.message_router.get_pool", AsyncMock(return_value=AsyncMock())),
        patch("handlers.message_router._get_user_active_items", AsyncMock(return_value={})),
        patch("handlers.message_router.get_post_by_num", AsyncMock(return_value={"post_num": 500123, "author_id": 888, "content": {"text": "op"}})),
        patch("handlers.message_router.check_spam", AsyncMock(return_value=True)),
        patch("handlers.message_router.process_new_post", AsyncMock(side_effect=fake_process_new_post)),
        patch("handlers.message_router.trigger_cyberchad_with_rate_limit", AsyncMock()),
        patch("handlers.message_router.check_and_send_contextual_reply", AsyncMock()),
        patch("handlers.message_router.delete_message_after_delay", AsyncMock()),
        patch("common.database.is_shadow_muted", AsyncMock(return_value=False)),
    ):
        await handle_message(msg, board_id="b", stream="ru")

    assert captured_params["reply_to_post"] == 500123
    assert "<b>Жирный текст</b>" in captured_params["content"]["text"]

    # Now test stale deleted reply warning in DM
    stale_reply = MagicMock(spec=types.Message)
    stale_reply.chat = SimpleNamespace(id=701, type="private")
    stale_reply.from_user = SimpleNamespace(id=7823520763)
    stale_reply.message_id = 55
    stale_reply.text = "Пост #500999\nУдалённый текст"
    stale_reply.caption = None
    stale_reply.entities = []
    stale_reply.caption_entities = []
    stale_reply.forward_from_chat = None
    stale_reply.forward_from_message_id = None
    stale_reply.forward_origin = None
    stale_reply.external_reply = None

    msg2 = MagicMock(spec=types.Message)
    msg2.chat = SimpleNamespace(id=701, type="private")
    msg2.from_user = SimpleNamespace(id=701, username="tester", first_name="Test", is_bot=False)
    msg2.message_id = 101
    msg2.content_type = "text"
    msg2.text = "Отвечаю на удалённый пост"
    msg2.html_text = "Отвечаю на удалённый пост"
    msg2.caption = None
    msg2.reply_to_message = stale_reply
    msg2.forward_from = None
    msg2.forward_from_chat = None
    msg2.forward_origin = None
    msg2.entities = []
    msg2.delete = AsyncMock()
    msg2.bot = bot

    with (
        patch.dict(shared_state.board_data, {"b": b_data}, clear=True),
        patch.dict(shared_state.messages_storage, {}, clear=True),
        patch.dict(shared_state.message_to_post, {}, clear=True),
        patch("handlers.message_router.get_pool", AsyncMock(return_value=AsyncMock())),
        patch("handlers.message_router._get_user_active_items", AsyncMock(return_value={})),
        patch("handlers.message_router.get_post_info_by_copy", AsyncMock(return_value=None)),
        patch("handlers.message_router.get_post_by_num", AsyncMock(return_value=None)),
        patch("handlers.message_router.find_post_by_file_id", AsyncMock(return_value=None)),
        patch("handlers.message_router.check_spam", AsyncMock(return_value=True)),
        patch("handlers.message_router.process_new_post", AsyncMock(return_value=500125)),
        patch("handlers.message_router.trigger_cyberchad_with_rate_limit", AsyncMock()),
        patch("handlers.message_router.check_and_send_contextual_reply", AsyncMock()),
        patch("handlers.message_router.delete_message_after_delay", AsyncMock()),
        patch("common.database.is_shadow_muted", AsyncMock(return_value=False)),
    ):
        await handle_message(msg2, board_id="b", stream="ru")

    bot.send_message.assert_awaited()
    warn_text = bot.send_message.call_args.args[1]
    assert "500999" in warn_text
    assert "не найден" in warn_text.lower()


@pytest.mark.asyncio
async def test_media_group_out_of_order_caption_reply_and_no_double_mute():
    """
    Album #1 arrives without caption/reply; album #2 carries reply_to_message + caption.
    Both must merge into the active media group, user activated, and flood does not double-mute.
    """
    import shared_state
    from handlers.message_router import handle_media_group_init

    leader_msg = MagicMock(spec=types.Message)
    leader_msg.media_group_id = "grp_999"
    leader_msg.chat = SimpleNamespace(id=777, type="private")
    leader_msg.from_user = SimpleNamespace(id=777, is_bot=False)
    leader_msg.message_id = 10
    leader_msg.caption = None
    leader_msg.caption_html_text = None
    leader_msg.reply_to_message = None
    leader_msg.forward_from = None
    leader_msg.forward_from_chat = None
    leader_msg.forward_origin = None
    leader_msg.date = datetime.now(UTC)
    leader_msg.bot = AsyncMock()
    leader_msg.delete = AsyncMock()

    reply_target = MagicMock(spec=types.Message)
    reply_target.chat = SimpleNamespace(id=777, type="private")
    reply_target.from_user = SimpleNamespace(id=888)
    reply_target.message_id = 5
    reply_target.text = None
    reply_target.caption = None
    reply_target.entities = []
    reply_target.caption_entities = []
    reply_target.forward_from_chat = None
    reply_target.forward_from_message_id = None
    reply_target.forward_origin = None
    reply_target.external_reply = None

    follower_msg = MagicMock(spec=types.Message)
    follower_msg.media_group_id = "grp_999"
    follower_msg.chat = SimpleNamespace(id=777, type="private")
    follower_msg.from_user = SimpleNamespace(id=777, is_bot=False)
    follower_msg.message_id = 11
    follower_msg.caption = "Альбом ответ"
    follower_msg.caption_html_text = "<b>Альбом ответ</b>"
    follower_msg.reply_to_message = reply_target
    follower_msg.forward_from = None
    follower_msg.forward_from_chat = None
    follower_msg.forward_origin = None
    follower_msg.date = datetime.now(UTC)
    follower_msg.bot = leader_msg.bot
    follower_msg.delete = AsyncMock()

    b_data = {"users": {"active": set(), "banned": set()}, "mutes": {}, "shadow_mutes": {}}

    with (
        patch.dict(shared_state.board_data, {"b": b_data}, clear=True),
        patch.dict(shared_state.current_media_groups, {}, clear=True),
        patch.dict(shared_state.sent_media_groups, set(), clear=True),
        patch.dict(shared_state.media_group_timers, {}, clear=True),
        patch.dict(shared_state.message_to_post, {(777, 5): 424242}, clear=True),
        patch.dict(shared_state.messages_storage, {424242: {"author_id": 123, "content": {"text": "op"}}}, clear=True),
        patch("handlers.message_router.add_or_activate_user", AsyncMock()) as act_mock,
        patch("handlers.message_router.get_post_by_num", AsyncMock(return_value={"post_num": 424242, "author_id": 123, "content": {"text": "op"}})),
        patch("handlers.message_router.complete_media_group_after_delay", AsyncMock()),
        patch("common.database.is_shadow_muted", AsyncMock(return_value=False)),
        patch("common.spam_filter.is_repost_from_public", return_value=False),
        patch("common.spam_filter.get_user_total_posts", AsyncMock(return_value=10)),
        patch("common.spam_filter.check_flood", return_value=(False, "")),
    ):
        await handle_media_group_init(leader_msg, board_id="b", stream="ru")
        await handle_media_group_init(follower_msg, board_id="b", stream="ru")
        key = "777:grp_999"
        grp = shared_state.current_media_groups[key]
        assert grp["reply_to_post"] == 424242
        assert grp["reply_to_message_id"] == 5
        assert "<b>Альбом ответ</b>" in grp["caption"]
        assert 777 in b_data["users"]["active"]
        act_mock.assert_awaited_once_with(777, "b")


# ---------------------------------------------------------------------------
# 4. HTML Safety, No Double Escaping, UTF-16 Truncation, Keyboards & Zero PII
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headers_no_double_escape_and_zero_pii_leak():
    """format_header, format_thread_post_header, MessageBroadcaster & _format_quote_block never double-escape or leak author_id."""
    import shared_state
    from broadcaster import MessageBroadcaster, _format_quote_block
    from post_helpers import format_header, format_thread_post_header
    from shared_state import BroadcastConfig

    secret_uid = 987654321
    with (
        patch.dict(shared_state.board_data, {"b": {"users": {"active": set()}, "user_settings": {}}}, clear=True),
        patch("post_helpers._get_author_prefix", AsyncMock(return_value="Кофе &amp; Чай &lt;3 ")),
    ):
        hdr = await format_header(board_id="b", post_num=12345, author_id=secret_uid, stream="ru")
        thdr = await format_thread_post_header(
            board_id="b",
            local_post_num=2,
            author_id=secret_uid,
            thread_info={"op_id": 111},
            stream="ru",
            global_post_num=12346,
        )

    assert str(secret_uid) not in hdr
    assert "&amp;amp;" not in hdr
    assert str(secret_uid) not in thdr
    assert "&amp;amp;" not in thdr

    bc = MessageBroadcaster(
        BroadcastConfig(
            bot_instance=AsyncMock(id=1),
            board_id="b",
            recipients=[1],
            content={"type": "text", "text": "body", "header": hdr},
        )
    )
    assert "&amp;amp;" not in bc.base_head_html
    assert "Кофе &amp; Чай &lt;3" in bc.base_head_html

    qb = _format_quote_block({"text": "Рыба &amp; мясо &lt;100&gt;"})
    assert qb is not None
    assert "&amp;amp;" not in qb
    assert "Рыба &amp; мясо &lt;100&gt;" in qb


def test_utf16_smart_split_and_safe_truncate_post():
    """Emoji-dense HTML stays within Telegram UTF-16 caps and balances tags cleanly."""
    from common.bot_helpers import get_telegram_utf16_len, smart_split_html
    from post_helpers import safe_truncate_post

    text = "<blockquote expandable>" + ("🔥 Тест & <b>жир</b>\n" * 280) + "</blockquote>"
    chunks = smart_split_html(text, max_chunk_size=4096)
    assert len(chunks) >= 2
    for ch in chunks:
        assert get_telegram_utf16_len(ch) <= 4096

    truncated = safe_truncate_post("<blockquote>" + ("😀" * 700) + "</blockquote>", max_chars=1024)
    assert get_telegram_utf16_len(truncated) <= 1024
    assert truncated.endswith("</blockquote>")


def test_thread_entry_keyboard_rows_bounded():
    """DM inline keyboards must keep <= 3 buttons per row to avoid mobile truncation."""
    from delivery_manager import _get_thread_entry_keyboard

    for show_hist in (False, True):
        kb = _get_thread_entry_keyboard("b", show_history_button=show_hist, stream="ru")
        assert len(kb.inline_keyboard) >= 1
        for row in kb.inline_keyboard:
            assert 1 <= len(row) <= 3
            for btn in row:
                assert btn.text and btn.callback_data
