# -*- coding: utf-8 -*-
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from archive_manager import _update_archive_post_content
from common.database import create_post, get_post_by_num, update_post_content


@pytest.mark.asyncio
async def test_archive_update_preserves_canonical_post_text(isolated_test_db):
    """
    Verify that _update_archive_post_content preserves the post's canonical text
    already stored in the database, updating only media metadata (file_id, media).
    """
    original_text = "Оригинальный авторский текст треда на сайте"
    initial_content = {
        "type": "photo",
        "text": original_text,
        "files": [{"original_url": "/files/test.png"}]
    }

    # 1. Create post in database
    post_num = await create_post(
        author_id=12345,
        board_id="b",
        content=initial_content,
        timestamp=1700000000,
        ip="127.0.0.1"
    )
    assert post_num is not None

    # 2. Call _update_archive_post_content with a caller dictionary that might have corrupted/service text
    corrupted_caller_content = {
        "type": "photo",
        "text": "🌱 На сайте создан новый тред! 🔗 Читать на сайте",
        "is_system_message": True
    }
    await _update_archive_post_content(
        post_num=post_num,
        content=corrupted_caller_content,
        content_type="photo",
        new_files_data=["telegram_file_id_abc123"],
        sender_bot_id=1001
    )

    # 3. Verify that DB still has the authentic original text and the new file_id
    updated_post = await get_post_by_num(post_num)
    assert updated_post is not None
    c = updated_post["content"]
    if isinstance(c, str):
        c = json.loads(c)

    assert c.get("text") == original_text
    assert c.get("file_id") == "telegram_file_id_abc123"
    assert not c.get("is_system_message")
    assert "На сайте создан новый тред" not in c.get("text")


@pytest.mark.asyncio
async def test_site_thread_broadcaster_separation_of_broadcast_and_storage(isolated_test_db):
    """
    Verify that site_posts_broadcaster in delivery_manager correctly separates:
    - Real post content stored in messages_storage and forwarded to archive
    - Service notification broadcast_content sent to Telegram users via enqueue_board_message
    """
    import delivery_manager

    post_num = 887766
    author_id = 554433
    board_id = "b"
    real_post_text = "Интересная тема для обсуждения от пользователя сайта"

    site_post_data = {
        "post_num": post_num,
        "board_id": board_id,
        "author_id": author_id,
        "stream": "ru",
        "post_mode": "new_thread",
        "thread_id": post_num,
        "timestamp": 1700000000,
        "content": {
            "type": "photo",
            "text": real_post_text,
            "files": [{
                "type": "image",
                "original_url": "/files/photo.png",
                "filename": "photo.png"
            }]
        }
    }

    mock_bot = AsyncMock()
    mock_bot.id = 1
    shared_state.messages_storage.clear()

    b_dict = {
        board_id: {
            "users": {"active": {author_id, 999999}, "banned": set()},
            "mutes": {},
            "shadow_mutes": {}
        }
    }
    with patch("delivery_manager.asyncio.sleep", new_callable=AsyncMock), \
         patch("common.database.get_and_clear_broadcast_queue", new_callable=AsyncMock) as mock_queue, \
         patch("common.database.mark_broadcast_posts_sent", new_callable=AsyncMock) as mock_mark_sent, \
         patch("delivery_manager.mark_broadcast_posts_sent", new_callable=AsyncMock), \
         patch("delivery_manager.enqueue_board_message", new_callable=AsyncMock, return_value=True) as mock_enqueue, \
         patch("delivery_manager._forward_post_to_realtime_archive", new_callable=AsyncMock) as mock_archive, \
         patch.dict(main_global_bots := getattr(shared_state, "GLOBAL_BOTS", {}), {board_id: mock_bot}, clear=False), \
         patch.dict(shared_state.board_data, b_dict), \
         patch.dict(delivery_manager.board_data, b_dict):

        # Return the post once, then cancel/break
        call_count = 0
        async def mock_get_queue():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [site_post_data]
            raise asyncio.CancelledError()

        mock_queue.side_effect = mock_get_queue

        try:
            await delivery_manager.site_posts_broadcaster()
        except asyncio.CancelledError:
            pass

        # 1. Check messages_storage: MUST contain the REAL user post
        assert post_num in shared_state.messages_storage
        stored_content = shared_state.messages_storage[post_num]["content"]
        assert stored_content.get("text") == real_post_text
        assert "На сайте создан новый тред" not in stored_content.get("text", "")
        assert not stored_content.get("is_system_message")

        # 2. Check enqueue_board_message: MUST receive broadcast_content with notice and link
        assert mock_enqueue.call_count == 1
        enqueue_item = mock_enqueue.call_args[0][1]
        bc = enqueue_item["content"]
        assert bc.get("is_system_message") is True
        assert "На сайте создан новый тред" in bc.get("text", "")
        assert f"https://tgach.top/{board_id}/res/{post_num}.html" in bc.get("text", "")

        # 3. Check archive forward: MUST be called with REAL user post content
        assert mock_archive.call_count == 1
        archive_call_content = mock_archive.call_args[1]["content"]
        assert archive_call_content.get("text") == real_post_text
        assert "На сайте создан новый тред" not in archive_call_content.get("text", "")


@pytest.mark.asyncio
async def test_cyberchad_voice_verdict_broadcasts_to_board_for_all_users():
    """
    Verify that transcribe_and_roast_voice_note sends:
    1. Instant direct reply to the author in PM
    2. Broadcasts text verdict + voice roast to the board (process_new_post) for all other users
    """
    from ai_manager import transcribe_and_roast_voice_note
    import io

    mock_bot = AsyncMock()
    mock_bot.get_file.return_value = MagicMock(file_path="voice/note.ogg", file_size=500_000)
    mock_bot.download_file.return_value = io.BytesIO(b"MOCK_OGG_PAYLOAD_TEST_1234567890123456")

    mock_msg = MagicMock()
    mock_msg.content_type = "voice"
    mock_msg.voice = MagicMock(duration=15, file_id="voice_fid_999", file_size=500_000)
    mock_msg.video_note = None
    mock_msg.from_user = MagicMock(id=112233, is_bot=False)
    mock_msg.reply = AsyncMock()
    mock_msg.reply_voice = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "Расшифрованный текст голосового"}

    mock_http_client = AsyncMock()
    mock_http_client.post.return_value = mock_resp

    with patch("ai_manager.httpx.AsyncClient") as mock_httpx_cls, \
         patch("ai_manager.summarize_text_with_hf", new_callable=AsyncMock) as mock_summarize, \
         patch("common.tts_engine.synthesize_cyberchad_voice_with_meta", new_callable=AsyncMock) as mock_synth_meta, \
         patch("ai_manager._safe_send_roast", new_callable=AsyncMock) as mock_safe_send, \
         patch("ai_manager._safe_send_voice_roast", new_callable=AsyncMock) as mock_safe_send_voice, \
         patch("common.bot_helpers.process_new_post", new_callable=AsyncMock) as mock_process_post:

        mock_httpx_cls.return_value.__aenter__.return_value = mock_http_client
        mock_summarize.return_value = "Хуета полная. Заткнись и не позорься."
        mock_synth_meta.return_value = (b"CYBERCHAD_SYNTH_VOICE_OGG", {})

        await transcribe_and_roast_voice_note(
            bot=mock_bot,
            message=mock_msg,
            board_id="b",
            stream="ru",
            post_num=556677
        )

        # 1. Author receives direct roast in PM
        assert mock_safe_send.call_count == 1
        assert mock_safe_send_voice.call_count == 1

        # 2. Board receives process_new_post calls (1 for text verdict, 1 for voice roast)
        assert mock_process_post.call_count == 2

        # 3. Text verdict call on board
        text_call = mock_process_post.call_args_list[0][0][0]
        assert text_call.board_id == "b"
        assert text_call.reply_to_post == 556677
        assert text_call.content["type"] == "text"
        assert text_call.content["is_ai_roast"] is True
        assert 112233 in text_call.content["exclude_recipients"]

        # 4. Voice roast call on board
        voice_call = mock_process_post.call_args_list[1][0][0]
        assert voice_call.board_id == "b"
        assert voice_call.reply_to_post == 556677
        assert voice_call.content["type"] == "voice"
        assert voice_call.content["voice_bytes"] == b"CYBERCHAD_SYNTH_VOICE_OGG"
        assert voice_call.content["caption"] == "🔥 Разъёб от Киберчеда"
        assert 112233 in voice_call.content["exclude_recipients"]
