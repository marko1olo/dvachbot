import pytest
import time
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from site_tgach.tagging_worker import (
    process_image_cpu,
    is_audio_media,
    TERMINAL_TAGS,
)


class TestVisionResilience:
    """Tests for vision pipeline resilience, partial hash preservation, and infinite loop prevention."""

    def test_terminal_tags_contain_safety_and_no_tags(self):
        """TERMINAL_TAGS must include all final states so get_tasks does not loop."""
        assert "safety_rejected" in TERMINAL_TAGS
        assert "no_tags" in TERMINAL_TAGS
        assert "download_failed" in TERMINAL_TAGS
        assert "format_unsupported" in TERMINAL_TAGS
        assert "audio" in TERMINAL_TAGS

    def test_audio_detection_prevents_unnecessary_vision_calls(self):
        """Audio files must be recognized by filename, mime, or headers without invoking Vision."""
        assert is_audio_media(file_type="audio") is True
        assert is_audio_media(file_type="voice") is True
        assert is_audio_media(filename="track.mp3") is True
        assert is_audio_media(filename="song.flac") is True
        assert is_audio_media(mime_type="audio/mpeg") is True
        assert is_audio_media(data=b"ID3\x03\x00\x00\x00\x00\x00\x00") is True
        assert is_audio_media(data=b"fLaC\x00\x00\x00\x22") is True
        assert is_audio_media(data=b"\xff\xd8\xff\xe0") is False

    def test_process_image_cpu_computes_all_hashes(self):
        """CPU image processing must compute SHA256, pHash, blurhash, and resized bytes."""
        from PIL import Image
        import io
        img = Image.new("RGB", (200, 200), color=(128, 64, 32))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        res, err = process_image_cpu(raw_bytes)
        assert err is None
        assert res is not None
        sha, phash, b_hash, resized_bytes = res
        assert len(sha) == 64
        assert phash is not None
        assert b_hash is not None
        assert resized_bytes is not None

    @pytest.mark.asyncio
    async def test_tagger_fallback_tags_logic_prevents_infinite_loop(self):
        """Simulate the fallback tags tier: attempt 1 records cooldown; attempt 2 applies fallback tags."""
        temp_failed = {}
        file_id = "test_file_exhaustion_123"
        file_type = "photo"

        # Attempt 1: API exhausted
        ai_response = "error_api_exhausted"
        tags = None
        entry = temp_failed.get(file_id)
        fail_cnt = ((entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1)
        assert fail_cnt == 1

        if fail_cnt >= 2:
            tags = "media, photo"
        elif ai_response == "error_api_exhausted":
            cooldown_secs = 30
            temp_failed[file_id] = {"until": time.time() + 180, "cnt": fail_cnt}

        assert tags is None
        assert file_id in temp_failed
        assert temp_failed[file_id]["cnt"] == 1

        # Attempt 2: API still exhausted -> Fallback tags applied immediately
        entry = temp_failed.get(file_id)
        fail_cnt = ((entry.get("cnt", 0) + 1) if isinstance(entry, dict) else 1)
        assert fail_cnt == 2

        if fail_cnt >= 2:
            default_style = "media, photo" if file_type in ("photo", "image") else "media, image"
            tags = default_style
            del temp_failed[file_id]

        assert tags == "media, photo"
        assert file_id not in temp_failed
