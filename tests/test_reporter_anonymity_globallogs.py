# -*- coding: utf-8 -*-
"""
tests/test_reporter_anonymity_globallogs.py — P0 Reporter Anonymity & GlobalLogs PII Eradication Tests.

Verifies:
1. safe_user_hash: deterministic 12-char HMAC-SHA256 hashing, idempotency, edge cases.
2. create_report: auto-hashing of sender_ip_hash, prevention of raw user IDs in Reports table.
3. log_global_event: defense-in-depth regex masking of 7-12 digit user IDs, preservation of post numbers and amounts.
4. main.py cmd_report & combat event audit: ensures no raw Telegram IDs leak into database or admin views.
"""

import re
import sys
import time
import unittest
from pathlib import Path
import aiosqlite

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import common.database
import common.db_pool
from common.anon_identity import safe_user_hash, get_anon_id, generate_anon_name


class TestReporterAnonymityAndGlobalLogsPII(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(":memory:", isolation_level=None)
        self.db.row_factory = aiosqlite.Row
        self._orig_db_conn = getattr(common.db_pool, "_db_connection", None)
        common.db_pool._db_connection = self.db

        # Initialize schema required for tests
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Posts (
                post_num INTEGER PRIMARY KEY,
                board_id TEXT DEFAULT 'b',
                author_id INTEGER DEFAULT 0,
                content TEXT DEFAULT '{}',
                report_count INTEGER DEFAULT 0,
                timestamp REAL DEFAULT 0
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS Reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_num INTEGER,
                category TEXT DEFAULT 'spam',
                reason TEXT,
                sender_ip_hash TEXT,
                created_at REAL NOT NULL
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS GlobalLogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                event_text TEXT NOT NULL,
                created_at REAL NOT NULL
            );
        """)

    async def asyncTearDown(self):
        common.db_pool._db_connection = self._orig_db_conn
        await self.db.close()

    # -------------------------------------------------------------------------
    # 1. safe_user_hash tests
    # -------------------------------------------------------------------------
    def test_safe_user_hash_determinism_and_length(self):
        """Проверка детерминизма, формата (12-hex) и уникальности для разных юзеров."""
        uid1 = 6557599214
        uid2 = 8501205401

        h1 = safe_user_hash(uid1)
        h2 = safe_user_hash(uid2)

        self.assertEqual(len(h1), 12)
        self.assertEqual(len(h2), 12)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{12}", h1))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{12}", h2))
        self.assertNotEqual(h1, h2)

        # Детерминизм: повторный вызов дает идентичный хеш
        self.assertEqual(safe_user_hash(uid1), h1)
        # Совпадение строкового и числового представления
        self.assertEqual(safe_user_hash(str(uid1)), h1)

    def test_safe_user_hash_idempotency(self):
        """Если значение уже является 12-значным hex-хешем, оно возвращается без изменений."""
        existing_hash = "a1b2c3d4e5f6"
        self.assertEqual(safe_user_hash(existing_hash), existing_hash)

    def test_safe_user_hash_empty_and_system(self):
        """Пустые, None и нулевые значения безопасно мапятся в 'system'."""
        self.assertEqual(safe_user_hash(None), "system")
        self.assertEqual(safe_user_hash(""), "system")
        self.assertEqual(safe_user_hash(0), "system")

    # -------------------------------------------------------------------------
    # 2. create_report & Reports table anonymity
    # -------------------------------------------------------------------------
    async def test_create_report_masks_sender_ip_hash(self):
        """Проверка, что create_report автоматически хеширует сырой user_id в sender_ip_hash."""
        # Подготавливаем пост
        await self.db.execute("INSERT INTO Posts (post_num, report_count) VALUES (589429, 0)")

        raw_reporter_id = "6557599214"
        expected_hash = safe_user_hash(raw_reporter_id)

        res = await common.database.create_report(
            post_num=589429,
            category="user_report",
            reason=f"Report from TG:Anon[{get_anon_id(int(raw_reporter_id))}]",
            sender_ip_hash=raw_reporter_id
        )
        self.assertTrue(res)

        async with self.db.execute("SELECT post_num, category, reason, sender_ip_hash FROM Reports WHERE post_num = 589429") as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        # sender_ip_hash ОБЯЗАН быть 12-значным hex-хешем, а не сырым ID
        self.assertEqual(row["sender_ip_hash"], expected_hash)
        self.assertNotIn(raw_reporter_id, row["sender_ip_hash"])
        # reason также не должен содержать сырой ID
        self.assertNotIn(raw_reporter_id, row["reason"])
        self.assertIn("Anon[", row["reason"])

    async def test_create_report_already_hashed(self):
        """Если передан уже захешированный sender_ip_hash, он сохраняется без двойного хеширования."""
        await self.db.execute("INSERT INTO Posts (post_num, report_count) VALUES (123456, 0)")

        raw_reporter_id = 7778889991
        hashed = safe_user_hash(raw_reporter_id)

        res = await common.database.create_report(
            post_num=123456,
            category="spam",
            reason="Spam in thread",
            sender_ip_hash=hashed
        )
        self.assertTrue(res)

        async with self.db.execute("SELECT sender_ip_hash FROM Reports WHERE post_num = 123456") as cur:
            row = await cur.fetchone()

        self.assertEqual(row["sender_ip_hash"], hashed)

    # -------------------------------------------------------------------------
    # 3. log_global_event defense-in-depth masking
    # -------------------------------------------------------------------------
    async def test_log_global_event_eradicates_raw_telegram_ids(self):
        """Проверка централизованной маскировки 7-12 значных ID в событиях GlobalLogs."""
        user_a = 6557599214
        user_b = 8501205401

        # Сырая строка события с незамаскированными ID (как было раньше)
        raw_event = f"🚔 PARTYVAN: Юзер {user_a} упаковал {user_b} в автозак на /b/ на 1ч"
        await common.database.log_global_event('bot', raw_event)

        async with self.db.execute("SELECT event_text FROM GlobalLogs ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()

        saved_text = row["event_text"]
        # Сырые ID юзеров не должны присутствовать в базе
        self.assertNotIn(str(user_a), saved_text)
        self.assertNotIn(str(user_b), saved_text)

        # Должны присутствовать Anon идентификаторы
        self.assertIn(f"Anon[{get_anon_id(user_a)}]", saved_text)
        self.assertIn(f"Anon[{get_anon_id(user_b)}]", saved_text)

    async def test_log_global_event_preserves_post_numbers_and_amounts(self):
        """Пост-номера (#602166, №123456) и суммы/таймауты не должны ложно маскироваться."""
        user_id = 9988776655
        text = f"Пост #602166 удален. Штраф 1488 ₪, мут 3600с юзеру {user_id}"
        await common.database.log_global_event('bot', text)

        async with self.db.execute("SELECT event_text FROM GlobalLogs ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()

        saved_text = row["event_text"]
        # Номер поста сохранен
        self.assertIn("#602166", saved_text)
        # Сумма и таймаут сохранены
        self.assertIn("1488", saved_text)
        self.assertIn("3600", saved_text)
        # Telegram ID замаскирован
        self.assertNotIn(str(user_id), saved_text)
        self.assertIn(f"Anon[{get_anon_id(user_id)}]", saved_text)

    async def test_log_global_event_idempotency_for_already_masked_text(self):
        """Если текст уже содержит Anon[...], повторная маскировка не ломает строку."""
        anon_id = get_anon_id(1234567890)
        text = f"💥 SHOOT: Юзер Anon[{anon_id}] пристрелил Anon[Бумбар7] на /b/"
        await common.database.log_global_event('bot', text)

        async with self.db.execute("SELECT event_text FROM GlobalLogs ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()

        self.assertEqual(row["event_text"], text)

    # -------------------------------------------------------------------------
    # 4. Code audit in main.py: reports and combat events
    # -------------------------------------------------------------------------
    def test_main_py_no_raw_reporter_id_leak_in_reports(self):
        """Статический аудит main.py: вставка в Reports не использует сырой reporter_id."""
        main_py = ROOT / "main.py"
        content = main_py.read_text(encoding="utf-8")

        # Проверка отсутствия старых уязвимых паттернов
        self.assertNotIn('report_reason_db = f"Report from TG:{reporter_id}"', content)
        self.assertNotIn('(post_num, "user_report", report_reason_db, str(reporter_id), time.time())', content)
        self.assertNotIn('f"🔍 <b>Репортёр:</b> <code>{reporter_id}</code>', content)

        # Проверка наличия безопасных паттернов
        self.assertIn('report_reason_db = f"Report from TG:Anon[{reporter_anon_id}]"', content)
        self.assertIn('sender_hash = safe_user_hash(reporter_id)', content)
        self.assertIn('f"🔍 <b>Репортёр:</b> <b>{escape_html(anon_reporter_str)}</b> (<code>{reporter_hash}</code>)"', content)

    def test_main_py_combat_events_anonymized(self):
        """Статический аудит main.py: боевые события логируются с Anon[...] вместо сырых ID."""
        main_py = ROOT / "main.py"
        content = main_py.read_text(encoding="utf-8")

        # Проверка ключевых боевых событий на отсутствие сырых интерполяций
        self.assertNotIn('f"🛡️ SHOOT_BOUNCE: Выстрел {ctx.user_id} срикошетил от {ctx.target_id}', content)
        self.assertNotIn('f"💥 SHOOT: Юзер {ctx.user_id} пристрелил {ctx.target_id}', content)
        self.assertNotIn('f"🧯 PEPPER: Юзер {user_id} залил перцем {target_id}', content)
        self.assertNotIn('f"🔪 ROB: Юзер {user_id} ограбил {target_id}', content)
        self.assertNotIn('f"💩 SHIT: Юзер {user_id} обмазал говном {target_id}', content)
        self.assertNotIn('f"🚔 PARTYVAN: Юзер {user_id} упаковал {target_id}', content)
        self.assertNotIn('f"🚽 CURSE: Юзер {user_id} подлил слабительное {target_id}', content)

        # Проверка наличия безопасного логирования
        self.assertIn('f"🛡️ SHOOT_BOUNCE: Выстрел Anon[{get_anon_id(ctx.user_id)}] срикошетил от Anon[{get_anon_id(ctx.target_id)}]', content)
        self.assertIn('f"💥 SHOOT: Юзер Anon[{get_anon_id(ctx.user_id)}] пристрелил Anon[{get_anon_id(ctx.target_id)}]', content)
        self.assertIn('f"🔪 ROB: Юзер Anon[{get_anon_id(user_id)}] ограбил Anon[{get_anon_id(target_id)}]', content)
        self.assertIn('f"🚔 PARTYVAN: Юзер Anon[{get_anon_id(user_id)}] упаковал Anon[{get_anon_id(target_id)}]', content)


if __name__ == "__main__":
    unittest.main()
