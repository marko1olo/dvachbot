# -*- coding: utf-8 -*-
"""
test_banner_manager.py — Unit & Integration Tests for Banner Manager & MediaGroup Gallery
"""

import sys
import json
import time
import tempfile
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
    flush_cache,
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

    def test_subsection_categories_pool_size_and_reachability(self):
        from banner_manager import SUBSECTION_CATEGORIES, resolve_category_candidates
        all_banners = set(_CATEGORIZED_BANNERS["all"])
        self.assertGreaterEqual(len(all_banners), 1441)
        self.assertEqual(len(all_banners), 1657)

        all_reached = set()
        for subsection, cats in SUBSECTION_CATEGORIES.items():
            resolved = resolve_category_candidates(subsection)
            pool = set()
            for cat in resolved:
                pool.update(_CATEGORIZED_BANNERS.get(cat, []))
            self.assertGreaterEqual(
                len(pool), 700,
                f"Subsection '{subsection}' pool too small: {len(pool)} < 700"
            )
            all_reached.update(pool)

        self.assertEqual(
            len(all_reached), len(all_banners),
            f"Expected 100% reachability (1064 banners), but only {len(all_reached)} were reachable"
        )

    def test_get_banner_file_for_subsections(self):
        from banner_manager import SUBSECTION_CATEGORIES
        for sub in SUBSECTION_CATEGORIES:
            fname, payload = get_banner_file(category=sub)
            self.assertTrue(fname, f"Subsection {sub} returned empty banner filename")
            self.assertTrue((BANNERS_DIR / fname).exists(), f"Banner {fname} does not exist")


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

    async def test_quick_menu_banners_click(self):
        from main import handle_quick_menu_click
        bot = AsyncMock()
        callback = AsyncMock()
        callback.bot = bot
        callback.message.chat.id = 123456789
        callback.from_user.id = 597708036
        callback.data = "menu_banners"

        with patch("main._send_banners_page") as mock_send:
            await handle_quick_menu_click(callback, state=AsyncMock(), board_id="b", stream="ru")
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            self.assertEqual(call_kwargs["bot"], bot)
            self.assertEqual(call_kwargs["chat_id"], 123456789)
            self.assertEqual(call_kwargs["page"], 0)
            self.assertEqual(call_kwargs["category"], "all")


class TestBannerCacheDebounce(unittest.TestCase):
    """Unit tests for debounced save_cache, flush_cache, and atexit registration."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_cache_path = Path(self.tmp_dir.name) / "banners_cache.json"
        self._orig_cache_file = banner_manager.CACHE_FILE
        self._orig_cache = banner_manager._BANNER_CACHE.copy()
        self._orig_last_save = banner_manager._LAST_CACHE_SAVE_TIME
        self._orig_dirty = banner_manager._CACHE_DIRTY
        banner_manager.CACHE_FILE = self.test_cache_path

    def tearDown(self):
        banner_manager.CACHE_FILE = self._orig_cache_file
        banner_manager._BANNER_CACHE.clear()
        banner_manager._BANNER_CACHE.update(self._orig_cache)
        banner_manager._LAST_CACHE_SAVE_TIME = self._orig_last_save
        banner_manager._CACHE_DIRTY = self._orig_dirty
        self.tmp_dir.cleanup()

    def test_save_cache_force_true_writes_immediately(self):
        banner_manager._BANNER_CACHE["force_key.jpg"] = "fid_force_123"
        result = save_cache(force=True)
        self.assertTrue(result)
        self.assertFalse(banner_manager._CACHE_DIRTY)
        self.assertTrue(self.test_cache_path.exists())

        with open(self.test_cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("force_key.jpg"), "fid_force_123")

    def test_save_cache_debouncing_under_threshold(self):
        # Initial save to establish cache file on disk and last_save_time
        banner_manager._BANNER_CACHE["init_key.jpg"] = "fid_init"
        save_cache(force=True)
        self.assertFalse(banner_manager._CACHE_DIRTY)

        # Mutate cache and call save_cache(force=False) within 5 seconds
        banner_manager._BANNER_CACHE["debounced_key.jpg"] = "fid_debounced"
        result = save_cache(force=False)
        self.assertFalse(result)  # Disk write was deferred
        self.assertTrue(banner_manager._CACHE_DIRTY)

        # File on disk still does NOT have the debounced key
        with open(self.test_cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("debounced_key.jpg", data)

    def test_save_cache_writes_after_debounce_interval_elapsed(self):
        # Initial save
        save_cache(force=True)
        banner_manager._BANNER_CACHE["after_interval.jpg"] = "fid_after"

        # Simulate 6.0 seconds elapsed
        banner_manager._LAST_CACHE_SAVE_TIME = time.time() - 6.0
        result = save_cache(force=False)
        self.assertTrue(result)  # Disk write occurred
        self.assertFalse(banner_manager._CACHE_DIRTY)

        with open(self.test_cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("after_interval.jpg"), "fid_after")

    def test_flush_cache_syncs_dirty_cache(self):
        save_cache(force=True)
        banner_manager._BANNER_CACHE["flush_key.jpg"] = "fid_flush"
        save_cache(force=False)  # Debounced, dirty = True
        self.assertTrue(banner_manager._CACHE_DIRTY)

        result = flush_cache()
        self.assertTrue(result)
        self.assertFalse(banner_manager._CACHE_DIRTY)

        with open(self.test_cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("flush_key.jpg"), "fid_flush")

    def test_reload_banners_and_dynamic_categorization(self):
        # Create a mock temporary banner file in BANNERS_DIR
        test_banner = BANNERS_DIR / "test_cyberpunk_neon_temp_banner.jpg"
        test_banner.write_text("fake image data")
        try:
            total = banner_manager.reload_banners()
            self.assertIn("test_cyberpunk_neon_temp_banner.jpg", _CATEGORIZED_BANNERS["all"])
            self.assertIn("test_cyberpunk_neon_temp_banner.jpg", _CATEGORIZED_BANNERS["start"])
            self.assertIn("test_cyberpunk_neon_temp_banner.jpg", _CATEGORIZED_BANNERS["cyberpunk"])
            self.assertIn("test_cyberpunk_neon_temp_banner.jpg", _CATEGORIZED_BANNERS["night"])
        finally:
            if test_banner.exists():
                test_banner.unlink()
            cat_file = BANNERS_DIR.parent.parent / "data" / "banner_categories.json"
            if cat_file.exists():
                try:
                    with open(cat_file, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    for k in c_data:
                        if isinstance(c_data[k], list) and "test_cyberpunk_neon_temp_banner.jpg" in c_data[k]:
                            c_data[k].remove("test_cyberpunk_neon_temp_banner.jpg")
                    with open(cat_file, "w", encoding="utf-8") as f:
                        json.dump(c_data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            banner_manager.reload_banners()

    def test_video_banner_detection_and_send(self):
        import asyncio
        from banner_manager import is_video_banner, send_banner_message
        self.assertTrue(is_video_banner("test_animation.mp4"))
        self.assertTrue(is_video_banner("sample.webm"))
        self.assertTrue(is_video_banner("movie.mov"))
        self.assertFalse(is_video_banner("image.jpg"))
        self.assertFalse(is_video_banner("banner.png"))
        self.assertFalse(is_video_banner(""))

        # Test send_banner_message with mock bot and video
        mock_bot = MagicMock()
        mock_bot.id = 12345
        mock_video_msg = MagicMock()
        mock_video_msg.video = MagicMock(file_id="cached_vid_fid_999")
        mock_video_msg.photo = None
        mock_video_msg.animation = None

        async def mock_send_video(*args, **kwargs):
            return mock_video_msg

        mock_bot.send_video = mock_send_video

        # Use an existing .mp4 from BANNERS_DIR or a mock video banner
        video_banners = [fn for fn in _CATEGORIZED_BANNERS["all"] if is_video_banner(fn)]
        self.assertGreater(len(video_banners), 0, "Expected video banners in BANNERS_DIR")
        chosen_vid = video_banners[0]

        async def run_send():
            return await send_banner_message(
                bot=mock_bot,
                chat_id=999,
                caption="Test video caption",
                banner_name=chosen_vid
            )

        msg = asyncio.run(run_send())
        self.assertIsNotNone(msg)
        self.assertEqual(banner_manager._BANNER_CACHE.get(f"12345:{chosen_vid}"), "cached_vid_fid_999")


if __name__ == "__main__":
    unittest.main()

