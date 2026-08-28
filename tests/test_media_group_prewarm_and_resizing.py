# -*- coding: utf-8 -*-
"""
Tests for:
1. media_utils._resize_image_if_needed: clamps resolution and byte size.
2. japanese_translator._fetch_from_yandere_paginated: selects sample_url/jpeg_url.
3. broadcaster.MessageBroadcaster: warms up file_id on first recipient and reuses it for subsequent recipients.
"""

import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

from media_utils import _resize_image_if_needed
from japanese_translator import _fetch_from_yandere_paginated
from broadcaster import MessageBroadcaster
from shared_state import BroadcastConfig


class TestMediaResizing(unittest.TestCase):
    def test_resize_clamps_large_dimensions(self):
        # Create image with 3200x2400
        img = Image.new("RGB", (3200, 2400), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        raw_bytes = buf.getvalue()

        resized = _resize_image_if_needed(raw_bytes)
        self.assertIsNotNone(resized)

        with Image.open(io.BytesIO(resized)) as out_img:
            w, h = out_img.size
            self.assertLessEqual(max(w, h), 2560)
            self.assertLessEqual(w + h, 4096)


class TestYandereSampleUrl(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_sample_url_over_file_url(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        # Post has huge file_url (20MB) and lightweight sample_url (300KB)
        mock_resp.json = AsyncMock(return_value=[
            {
                "id": 12345,
                "file_url": "https://files.yande.re/image/huge_original_25mb.png",
                "sample_url": "https://files.yande.re/sample/sample_light_300kb.jpg",
                "jpeg_url": "https://files.yande.re/jpeg/jpeg_light_500kb.jpg",
                "tags": "loli solo",
            }
        ])

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = ctx

        res = await _fetch_from_yandere_paginated(
            mock_session, headers={}, proxy=None,
            base_tags="loli", rating_tag="rating:s", max_page=1,
            site_url="https://yande.re/post.json"
        )
        self.assertEqual(res, "https://files.yande.re/sample/sample_light_300kb.jpg")


class TestBroadcasterMediaGroupPrewarm(unittest.IsolatedAsyncioTestCase):
    @patch("broadcaster._order_recipients_for_delivery")
    async def test_media_group_file_id_caching_and_warmup(self, mock_order):
        # 3 recipients
        mock_order.return_value = ([101, 102, 103], 1, 2)

        bot = MagicMock()
        # Mock message returned with file_id
        sent_m1 = MagicMock()
        photo_obj = MagicMock()
        photo_obj.file_id = "cached_photo_fid_999"
        sent_m1.photo = [photo_obj]
        sent_m1.video = None
        sent_m1.document = None
        sent_m1.audio = None

        bot.send_media_group = AsyncMock(return_value=[sent_m1])

        raw_content = {
            "type": "media_group",
            "media": [
                {"type": "photo", "media": b"dummy_image_bytes_here"}
            ],
            "caption": "Test album"
        }

        config = BroadcastConfig(
            bot_instance=bot,
            board_id="ai",
            recipients=[101, 102, 103],
            content=raw_content,
            reply_info=None,
            keyboard=None,
            verbose=False,
            delivery_phase="full",
        )

        broadcaster = MessageBroadcaster(config)
        broadcaster.b_data = {"users": {"banned": set()}, "user_settings": {}}

        results = await broadcaster.broadcast()

        # All 3 recipients must succeed
        self.assertEqual(len(results), 3)
        self.assertEqual(bot.send_media_group.call_count, 3)

        # First call was raw bytes, second and third calls must have the cached string file_id!
        call2_media = bot.send_media_group.call_args_list[1][1]["media"]
        self.assertEqual(call2_media[0].media, "cached_photo_fid_999")

        call3_media = bot.send_media_group.call_args_list[2][1]["media"]
        self.assertEqual(call3_media[0].media, "cached_photo_fid_999")
