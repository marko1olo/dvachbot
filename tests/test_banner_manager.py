# -*- coding: utf-8 -*-
"""
test_banner_manager.py — Unit & Integration Tests for Banner Manager & MediaGroup Gallery
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import banner_manager
from banner_manager import (
    get_banner_file,
    get_all_banners_summary,
    CATEGORY_PATTERNS,
    _CATEGORIZED_BANNERS,
    _BANNER_CACHE,
    BANNERS_DIR,
    save_cache,
)
from main import _send_banners_page, BANNERS_PER_PAGE
from aiogram.types import FSInputFile, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMediaGroup


class TestBannerManager(unittest.TestCase):

    def test_all_banners_exist_and_count(self):
        summary = get_all_banners_summary()
        self.assertGreaterEqual(summary["total_banners"], 383)
        self.assertGreaterEqual(summary["cached_file_ids"], 0)

    def test_category_expansion_thresholds(self):
        cats = _CATEGORIZED_BANNERS
        self.assertGreaterEqual(len(cats["start"]), 383)
        self.assertGreaterEqual(len(cats["all"]), 383)

        # Requirements: shop >= 100, wallet >= 120, roulette >= 120
        self.assertGreaterEqual(len(cats["shop"]), 100, f"Shop category must have >= 100 banners, got {len(cats['shop'])}")
        self.assertGreaterEqual(len(cats["wallet"]), 120, f"Wallet category must have >= 120 banners, got {len(cats['wallet'])}")
        self.assertGreaterEqual(len(cats["roulette"]), 120, f"Roulette category must have >= 120 banners, got {len(cats['roulette'])}")

        # Check other core categories
        self.assertGreaterEqual(len(cats["night"]), 100)
        self.assertGreaterEqual(len(cats["maid"]), 100)
        self.assertGreaterEqual(len(cats["schizo"]), 100)
        self.assertGreaterEqual(len(cats["calm"]), 150)
        self.assertGreaterEqual(len(cats["newspaper"]), 100)
        self.assertGreaterEqual(len(cats["digest"]), 100)
        self.assertGreaterEqual(len(cats["summary"]), 100)
        self.assertGreaterEqual(len(cats["stats"]), 100)

    def test_new_thematic_categories_present(self):
        new_themes = ["cyberpunk", "retro", "matrix", "anime", "gothic", "chill", "market", "games", "cards", "duel"]
        for theme in new_themes:
            self.assertIn(theme, CATEGORY_PATTERNS)
            self.assertIn(theme, _CATEGORIZED_BANNERS)
            self.assertGreater(len(_CATEGORIZED_BANNERS[theme]), 0, f"Theme {theme} should have banners")

    def test_get_banner_file_for_all_categories(self):
        for cat in _CATEGORIZED_BANNERS:
            fname, payload = get_banner_file(category=cat)
            self.assertTrue(fname, f"Category {cat} returned empty filename")
            self.assertTrue(payload, f"Category {cat} returned empty payload")
            self.assertTrue((BANNERS_DIR / fname).exists(), f"Banner {fname} does not exist in {BANNERS_DIR}")

    def test_anti_repeat_shuffle_bag(self):
        user_id = 999888
        seen = []
        for _ in range(5):
            fname, _ = get_banner_file(category="shop", user_id=user_id)
            seen.append(fname)
        # Banners returned for same user should avoid immediate duplicate
        self.assertEqual(len(seen), len(set(seen)), "Expected distinct banners across 5 consecutive calls")


class TestBannerGalleryAsync(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Save cache backup
        self._orig_cache = _BANNER_CACHE.copy()
        self._orig_categorized = {k: list(v) for k, v in _CATEGORIZED_BANNERS.items()}

    async def asyncTearDown(self):
        # Restore cache
        _BANNER_CACHE.clear()
        _BANNER_CACHE.update(self._orig_cache)
        _CATEGORIZED_BANNERS.clear()
        _CATEGORIZED_BANNERS.update(self._orig_categorized)

    async def test_send_banners_page_cache_eviction_and_fallback_on_bad_request(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        all_pool = _CATEGORIZED_BANNERS.get("all", [])
        self.assertGreater(len(all_pool), 0)
        chunk = all_pool[:BANNERS_PER_PAGE]

        # Seed cache with stale file IDs
        for fn in chunk:
            _BANNER_CACHE[f"{bot.id}:{fn}"] = f"stale_remote_id_{fn}"
            _BANNER_CACHE[fn] = f"stale_remote_id_{fn}"

        # Create mock response for the second (fallback) call
        sent_messages = []
        for idx, fn in enumerate(chunk):
            mock_msg = MagicMock()
            mock_photo = MagicMock()
            mock_photo.file_id = f"fresh_remote_id_{idx}"
            mock_msg.photo = [mock_photo]
            sent_messages.append(mock_msg)

        bad_req_exc = TelegramBadRequest(
            method=SendMediaGroup(chat_id=chat_id, media=[]),
            message="Bad Request: wrong remote file identifier specified"
        )
        bot.send_media_group.side_effect = [bad_req_exc, sent_messages]

        with patch("banner_manager.save_cache") as mock_save:
            await _send_banners_page(bot, chat_id=chat_id, page=0, category="all")

        # Verify send_media_group was called twice (initial attempt + local fallback)
        self.assertEqual(bot.send_media_group.call_count, 2)

        # First call used string file IDs from cache
        first_call_media = bot.send_media_group.call_args_list[0].kwargs["media"]
        for item in first_call_media:
            self.assertIsInstance(item.media, str)
            self.assertTrue(item.media.startswith("stale_remote_id_"))

        # Second call used FSInputFile local objects
        fallback_call_media = bot.send_media_group.call_args_list[1].kwargs["media"]
        for item in fallback_call_media:
            self.assertIsInstance(item.media, FSInputFile)

        # Verify save_cache was called (during eviction and during new ID storage)
        self.assertGreaterEqual(mock_save.call_count, 2)

        # Verify stale IDs were replaced with fresh ones in _BANNER_CACHE
        for idx, fn in enumerate(chunk):
            self.assertEqual(_BANNER_CACHE[f"{bot.id}:{fn}"], f"fresh_remote_id_{idx}")
            self.assertEqual(_BANNER_CACHE[fn], f"fresh_remote_id_{idx}")

        # Verify navigation keyboard and caption was sent
        bot.send_message.assert_called_once()
        self.assertEqual(bot.send_message.call_args.kwargs["chat_id"], chat_id)
        self.assertIn("reply_markup", bot.send_message.call_args.kwargs)

    async def test_send_banners_page_empty_category_fallback_to_all(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        mock_msg = MagicMock()
        mock_photo = MagicMock()
        mock_photo.file_id = "test_fid_123"
        mock_msg.photo = [mock_photo]
        bot.send_media_group.return_value = [mock_msg]

        # Call with non-existent category
        await _send_banners_page(bot, chat_id=chat_id, page=0, category="non_existent_category_foo")

        self.assertTrue(bot.send_media_group.called)
        self.assertTrue(bot.send_message.called)

    async def test_send_banners_page_empty_pool_handling(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        _CATEGORIZED_BANNERS.clear()
        _CATEGORIZED_BANNERS["all"] = []

        await _send_banners_page(bot, chat_id=chat_id, page=0, category="all")

        self.assertEqual(bot.send_media_group.call_count, 0)
        bot.send_message.assert_called_once_with(chat_id, "❌ Баннеры не найдены.")

    async def test_send_banners_page_missing_local_files_resilience(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        # Category pointing only to non-existent local files
        _CATEGORIZED_BANNERS["missing_cat"] = ["nonexistent_banner_alpha.jpg", "nonexistent_banner_beta.jpg"]

        await _send_banners_page(bot, chat_id=chat_id, page=0, category="missing_cat")

        # Should cleanly send failure message without crashing
        self.assertEqual(bot.send_media_group.call_count, 0)
        bot.send_message.assert_called_once_with(chat_id, "❌ Не удалось загрузить баннеры для этой категории.")

    async def test_send_banners_page_fallback_failure_handling(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        # Both initial and fallback raise exceptions
        bot.send_media_group.side_effect = [
            TelegramBadRequest(
                method=SendMediaGroup(chat_id=chat_id, media=[]),
                message="Bad Request: wrong remote file identifier specified"
            ),
            Exception("Telegram network timeout during fallback")
        ]

        await _send_banners_page(bot, chat_id=chat_id, page=0, category="all")

        self.assertEqual(bot.send_media_group.call_count, 2)
        bot.send_message.assert_called_once()
        sent_text = bot.send_message.call_args.args[1] if len(bot.send_message.call_args.args) > 1 else bot.send_message.call_args.kwargs.get("text", "")
        self.assertIn("❌ Ошибка отправки баннеров", sent_text)


    async def test_send_banners_page_alpha_vs_random_sorting(self):
        bot = AsyncMock()
        bot.id = 888999
        chat_id = 123456789

        sent_messages = [MagicMock(photo=[MagicMock(file_id=f"fid_{i}")]) for i in range(10)]
        bot.send_media_group.return_value = sent_messages

        # Test alphabetical sort (default)
        await _send_banners_page(bot, chat_id=chat_id, page=0, category="all", sort="alpha")
        self.assertEqual(bot.send_media_group.call_count, 1)
        media_alpha = bot.send_media_group.call_args.kwargs["media"]
        self.assertIn("🔤 А-Я", media_alpha[0].caption)

        # Check navigation markup in message
        self.assertEqual(bot.send_message.call_count, 1)
        markup = bot.send_message.call_args.kwargs["reply_markup"]
        sort_btn = markup.inline_keyboard[1][0]
        self.assertIn("Случайно", sort_btn.text)
        self.assertIn("rnd", sort_btn.callback_data)

        # Test random sort with seed
        bot.reset_mock()
        bot.send_media_group.return_value = sent_messages
        await _send_banners_page(bot, chat_id=chat_id, page=0, category="all", sort="rnd", seed=12345)
        self.assertEqual(bot.send_media_group.call_count, 1)
        media_rnd = bot.send_media_group.call_args.kwargs["media"]
        self.assertIn("🎲 Случайно", media_rnd[0].caption)

        rnd_markup = bot.send_message.call_args.kwargs["reply_markup"]
        rnd_sort_btn = rnd_markup.inline_keyboard[1][0]
        self.assertIn("А-Я", rnd_sort_btn.text)
        self.assertIn("alpha", rnd_sort_btn.callback_data)

    async def test_cmd_banners_aliases_and_argument_parsing(self):
        from main import cmd_banners
        bot = AsyncMock()
        message = AsyncMock()
        message.bot = bot
        message.chat.id = 123456789
        message.delete = AsyncMock()

        # Test with /banner random
        message.text = "/banner random"
        with patch("main._send_banners_page") as mock_send:
            await cmd_banners(message, board_id="b")
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            self.assertEqual(call_kwargs["sort"], "rnd")
            self.assertEqual(call_kwargs["category"], "all")
            self.assertGreater(call_kwargs["seed"], 0)

        # Test with /баннер maid
        message.text = "/баннер maid"
        with patch("main._send_banners_page") as mock_send:
            await cmd_banners(message, board_id="b")
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            self.assertEqual(call_kwargs["category"], "maid")
            self.assertEqual(call_kwargs["sort"], "alpha")

        # Test with legacy callback bn:all:2
        from main import cb_banners_page
        callback = AsyncMock()
        callback.bot = bot
        callback.message.chat.id = 123456789
        callback.message.delete = AsyncMock()
        callback.data = "bn:all:2"

        with patch("main._send_banners_page") as mock_send:
            await cb_banners_page(callback)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            self.assertEqual(call_kwargs["category"], "all")
            self.assertEqual(call_kwargs["page"], 2)
            self.assertEqual(call_kwargs["sort"], "alpha")


if __name__ == "__main__":
    unittest.main()

