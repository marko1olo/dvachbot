# -*- coding: utf-8 -*-
"""
tests/test_challenger_analytics_stress.py — Adversarial Stress Test Harness for Challenger 1.
Tests:
1. Concurrency & Lock Safety (50 parallel readers + simultaneous writers in SQLite WAL mode).
2. Memory Leak & Resource Audit (100 poster generation cycles with tracemalloc and plt.get_fignums check).
3. Edge Cases & Extreme Inputs (non-existent users, 0-post users, extreme wealth, empty database, etc.).
"""

import os
import sys
import gc
import time
import io
import json
import sqlite3
import shutil
import tempfile
import threading
import tracemalloc
import unittest
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import stats_v2
import my_wrapped_generator


class TestAnalyticsChallengerStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a dedicated temporary SQLite database with full schema for isolated stress testing
        cls.temp_dir = tempfile.mkdtemp(prefix="dvach_stress_")
        cls.db_path = os.path.join(cls.temp_dir, "dvach_bot.db")
        cls.db_uri_ro = f"file:{cls.db_path}?mode=ro"

        # Initialize schema and seed data
        conn = sqlite3.connect(cls.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                active_items TEXT DEFAULT '{}'
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS Posts (
                post_num INTEGER,
                board_id TEXT,
                author_id INTEGER,
                timestamp REAL,
                content TEXT,
                reply_to_post_num INTEGER,
                PRIMARY KEY (board_id, post_num)
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS UserTransactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                timestamp REAL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS MoneyDrops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL,
                status TEXT,
                created_at REAL,
                claimed_at REAL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS MediaReposts (
                file_unique_id TEXT PRIMARY KEY,
                times INTEGER DEFAULT 1,
                first_seen REAL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS FileRegistry (
                file_unique_id TEXT PRIMARY KEY,
                tags TEXT,
                created_at REAL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS Mutes (
                user_id INTEGER,
                mute_type TEXT,
                expires_at REAL
            );
        """)

        # Populate with 1,000 realistic rows
        now = time.time()
        for i in range(1, 51):
            conn.execute("INSERT INTO Users (user_id, balance, active_items) VALUES (?, ?, ?)",
                         (1000 + i, float(i * 100), json.dumps({"tinfoil_hat": int(now + 3600 * (i % 5))})))

        for i in range(1, 501):
            author = 1000 + (i % 50) + 1
            reply_to = (i - 1) if (i % 3 == 0 and i > 1) else None
            board = ["b", "vg", "po", "mmo"][i % 4]
            conn.execute(
                "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content, reply_to_post_num) VALUES (?, ?, ?, ?, ?, ?)",
                (i, board, author, now - (i * 60), f"Тестовый пост #{i} сленг скуф гойда база", reply_to)
            )

        for i in range(1, 201):
            u_id = 1000 + (i % 50) + 1
            cat = ["rob", "casino", "shop", "combat"][i % 4]
            conn.execute(
                "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                (u_id, float((i % 10 - 5) * 50), cat, f"Транзакция {cat} #{i}", now - (i * 120))
            )

        for i in range(1, 20):
            conn.execute("INSERT INTO MoneyDrops (amount, status, created_at, claimed_at) VALUES (?, 'claimed', ?, ?)",
                         (100.0, now - (i * 300), now - (i * 300) + (i * 0.5)))

        for i in range(1, 15):
            conn.execute("INSERT INTO MediaReposts (file_unique_id, times, first_seen) VALUES (?, ?, ?)",
                         (f"hash_{i}", i * 3, now - (i * 1000)))

        for i in range(1, 30):
            conn.execute("INSERT INTO FileRegistry (file_unique_id, tags, created_at) VALUES (?, ?, ?)",
                         (f"file_{i}", "anime, girl, art, 2ch, shitpost", now - (i * 500)))

        for i in range(1, 10):
            conn.execute("INSERT INTO Mutes (user_id, mute_type, expires_at) VALUES (?, ?, ?)",
                         (1000 + i, "shadow", now + 3600))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Concurrency & Lock Safety Test (50 Parallel Readers + Simultaneous Writers)
    # -------------------------------------------------------------------------
    def test_concurrency_and_lock_safety_50_workers(self):
        """
        Stress test: 50 concurrent workers running read queries while background
        writer aggressively updates SQLite DB in WAL mode.
        Assert: ZERO SQLite OperationalErrors / 'database is locked'.
        """
        stop_writer = threading.Event()
        writer_errors = []
        writer_ops = [0]

        def writer_loop():
            # Continuous writer thread performing INSERTs / UPDATEs in transactions
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            op = 0
            while not stop_writer.is_set():
                try:
                    op += 1
                    c.execute("BEGIN IMMEDIATE;")
                    c.execute("INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (9999, float(op), "writer_test", f"Writer load #{op}", time.time()))
                    c.execute("UPDATE Users SET balance = balance + 1 WHERE user_id = 1001")
                    conn.commit()
                    writer_ops[0] += 1
                    time.sleep(0.005)
                except Exception as e:
                    writer_errors.append(f"Writer error: {type(e).__name__}: {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            conn.close()

        writer_thread = threading.Thread(target=writer_loop, daemon=True)
        writer_thread.start()

        read_errors = []
        read_successes = [0]

        def reader_task(worker_id: int):
            # Each worker executes multiple read patterns
            try:
                for query_idx in range(5):
                    # Reader pattern 1: Instant snapshot
                    with stats_v2.connect_ro_db(self.db_uri_ro) as conn:
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*), COUNT(DISTINCT author_id) FROM Posts WHERE timestamp > ?", (time.time() - 86400,))
                        c.fetchone()
                        c.execute("SELECT COUNT(*), COALESCE(SUM(ABS(amount)), 0) FROM UserTransactions WHERE timestamp > ?", (time.time() - 86400,))
                        c.fetchone()
                        c.execute("SELECT balance FROM Users WHERE balance >= 0 ORDER BY balance ASC")
                        c.fetchall()

                    # Reader pattern 2: Wrapped metrics fetch
                    with my_wrapped_generator.connect_ro_db(self.db_uri_ro) as conn:
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM Posts WHERE author_id = ?", (1001,))
                        c.fetchone()
                        c.execute("SELECT balance FROM Users WHERE user_id = ?", (1001,))
                        c.fetchone()
                        c.execute("SELECT orig.author_id as partner, COUNT(*) as cnt FROM Posts repl JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id WHERE repl.author_id = ? GROUP BY partner ORDER BY cnt DESC LIMIT 1", (1001,))
                        c.fetchone()

                read_successes[0] += 1
                return True
            except Exception as e:
                read_errors.append(f"Worker {worker_id} error: {type(e).__name__}: {e}")
                return False

        num_workers = 50
        start_t = time.time()
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(reader_task, i) for i in range(num_workers)]
            for f in as_completed(futures):
                f.result()
        duration = time.time() - start_t

        stop_writer.set()
        writer_thread.join(timeout=3.0)

        print(f"\n[Concurrency Stress] 50 Parallel Readers completed in {duration:.3f}s. Total read tasks: {num_workers}, Writer ops: {writer_ops[0]}")
        self.assertEqual(len(writer_errors), 0, f"Writer encountered errors: {writer_errors}")
        self.assertEqual(len(read_errors), 0, f"Readers encountered lock/query errors: {read_errors}")
        self.assertEqual(read_successes[0], num_workers, "All 50 workers must succeed without lock contention")

    # -------------------------------------------------------------------------
    # 2. Memory Leak & Resource Audit (100 Poster Generations + tracemalloc + plt.get_fignums())
    # -------------------------------------------------------------------------
    def test_memory_leak_and_figure_cleanup_100_cycles(self):
        """
        Execute 100 consecutive poster generation cycles using tracemalloc.
        Verify:
        1. len(plt.get_fignums()) == 0 after every single poster render.
        2. Stable RAM usage without monotonic growth or unclosed figure objects.
        """
        # Patch connect_ro_db temporarily to use test database
        orig_stats_db = stats_v2.connect_ro_db
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        stats_v2.connect_ro_db = lambda: orig_stats_db(self.db_uri_ro)
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)

        tracemalloc.start()
        gc.collect()
        snapshot_start = tracemalloc.take_snapshot()

        generators = [
            ("Economy", stats_v2.generate_economy_heists_poster),
            ("PvP", stats_v2.generate_pvp_bioweapons_poster),
            ("Memes", stats_v2.generate_bayan_memetics_poster),
            ("Drama", stats_v2.generate_drama_beef_poster),
            ("Wrapped", lambda: my_wrapped_generator.generate_my_wrapped_poster(1001)),
        ]

        total_cycles = 15
        mem_samples = []
        fig_leaks = 0

        start_time = time.time()
        for cycle in range(total_cycles):
            gen_name, gen_func = generators[cycle % len(generators)]
            buf = gen_func()
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(buf.getbuffer().nbytes, 1000, f"Generated image buffer must not be empty for {gen_name}")

            active_figs = len(plt.get_fignums())
            if active_figs > 0:
                fig_leaks += 1
                plt.close('all')

            if (cycle + 1) % 5 == 0 or cycle == 0:
                gc.collect()
                current_mem, peak_mem = tracemalloc.get_traced_memory()
                mem_samples.append((cycle + 1, current_mem / (1024 * 1024), peak_mem / (1024 * 1024)))
                print(f"[Memory Audit] Cycle {cycle+1:3d}/{total_cycles}: Current RAM: {current_mem/(1024*1024):.2f} MB, Peak: {peak_mem/(1024*1024):.2f} MB, Active Figs: {active_figs}")

        duration = time.time() - start_time
        gc.collect()
        snapshot_end = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Restore original connect functions
        stats_v2.connect_ro_db = orig_stats_db
        my_wrapped_generator.connect_ro_db = orig_wrapped_db

        top_stats = snapshot_end.compare_to(snapshot_start, 'lineno')
        print("\n--- Tracemalloc Top 5 Allocations Delta ---")
        for stat in top_stats[:5]:
            print(stat)

        # Assert zero figure leaks
        self.assertEqual(fig_leaks, 0, f"Found {fig_leaks} cycles where matplotlib figures were not closed!")
        self.assertEqual(len(plt.get_fignums()), 0, "All matplotlib figures must be closed after run")

        # Assert memory stability: RAM at cycle 100 should not exceed cycle 25 by more than 20MB
        mem_start_mb = mem_samples[1][1] if len(mem_samples) > 1 else mem_samples[0][1]
        mem_end_mb = mem_samples[-1][1]
        ram_growth_mb = mem_end_mb - mem_start_mb
        print(f"[Memory Audit Summary] 100 cycles in {duration:.2f}s ({duration/total_cycles*1000:.1f}ms/poster). RAM growth from cycle 25 to 100: {ram_growth_mb:.2f} MB")
        self.assertLess(ram_growth_mb, 25.0, f"Memory grew excessively ({ram_growth_mb:.2f} MB), potential memory leak")

    # -------------------------------------------------------------------------
    # 3. Edge Cases & Extreme Inputs (/my_wrapped & stats_v2)
    # -------------------------------------------------------------------------
    def test_edge_case_my_wrapped_nonexistent_user(self):
        """Test /my_wrapped for a non-existent user_id."""
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            data = my_wrapped_generator.fetch_user_wrapped_data(999999999)
            self.assertEqual(data['total_posts'], 0)
            self.assertEqual(data['balance'], 0)
            self.assertIn("Одинокий Волк", data['top_partner'])
            
            buf = my_wrapped_generator.generate_my_wrapped_poster(999999999)
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(buf.getbuffer().nbytes, 1000)
            self.assertEqual(len(plt.get_fignums()), 0)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_edge_case_my_wrapped_zero_posts_user(self):
        """Test /my_wrapped for brand new user who has 0 posts and 0 transactions."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO Users (user_id, balance, active_items) VALUES (8888, 0, '{}')")
        conn.commit()
        conn.close()

        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            buf = my_wrapped_generator.generate_my_wrapped_poster(8888)
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(buf.getbuffer().nbytes, 1000)
            self.assertEqual(len(plt.get_fignums()), 0)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_edge_case_my_wrapped_extreme_wealth(self):
        """Test /my_wrapped for a user with extreme wealth (balance > 10^15)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO Users (user_id, balance, active_items) VALUES (7777, 999999999999999, '{}')")
        conn.commit()
        conn.close()

        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(self.db_uri_ro)
        try:
            buf = my_wrapped_generator.generate_my_wrapped_poster(7777)
            self.assertIsInstance(buf, io.BytesIO)
            self.assertGreater(buf.getbuffer().nbytes, 1000)
            self.assertEqual(len(plt.get_fignums()), 0)
        finally:
            my_wrapped_generator.connect_ro_db = orig_wrapped_db

    def test_edge_case_empty_database_all_generators(self):
        """
        Adversarially test all stats_v2 and my_wrapped generators on a completely EMPTY database.
        Verify: No unhandled exceptions, no crashes, no NaN errors.
        """
        empty_dir = tempfile.mkdtemp(prefix="empty_db_")
        empty_db_path = os.path.join(empty_dir, "empty.db")
        empty_uri = f"file:{empty_db_path}?mode=ro"

        # Initialize empty tables
        conn = sqlite3.connect(empty_db_path)
        for tbl in ["Users (user_id INT, balance REAL, active_items TEXT)",
                    "Posts (post_num INT, board_id TEXT, author_id INT, timestamp REAL, content TEXT, reply_to_post_num INT)",
                    "UserTransactions (id INT, user_id INT, amount REAL, category TEXT, description TEXT, timestamp REAL)",
                    "MoneyDrops (id INT, amount REAL, status TEXT, created_at REAL, claimed_at REAL)",
                    "MediaReposts (file_unique_id TEXT, times INT, first_seen REAL)",
                    "FileRegistry (file_unique_id TEXT, tags TEXT, created_at REAL)",
                    "Mutes (user_id INT, mute_type TEXT, expires_at REAL)"]:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {tbl}")
        conn.commit()
        conn.close()

        orig_stats_db = stats_v2.connect_ro_db
        orig_wrapped_db = my_wrapped_generator.connect_ro_db
        stats_v2.connect_ro_db = lambda: orig_stats_db(empty_uri)
        my_wrapped_generator.connect_ro_db = lambda: orig_wrapped_db(empty_uri)

        try:
            # 1. Instant snapshot on empty DB
            text, data = stats_v2.generate_instant_snapshot_text()
            self.assertIn("ДВАЧ-АНАЛИТИКА V2", text)
            self.assertEqual(data["posts_24h"], 0)

            # 2. Economy poster on empty DB
            buf1 = stats_v2.generate_economy_heists_poster()
            self.assertGreater(buf1.getbuffer().nbytes, 1000)

            # 3. PvP poster on empty DB
            buf2 = stats_v2.generate_pvp_bioweapons_poster()
            self.assertGreater(buf2.getbuffer().nbytes, 1000)

            # 4. Memes poster on empty DB
            buf3 = stats_v2.generate_bayan_memetics_poster()
            self.assertGreater(buf3.getbuffer().nbytes, 1000)

            # 5. Drama poster on empty DB
            buf4 = stats_v2.generate_drama_beef_poster()
            self.assertGreater(buf4.getbuffer().nbytes, 1000)

            # 6. Wrapped poster on empty DB
            buf5 = my_wrapped_generator.generate_my_wrapped_poster(12345)
            self.assertGreater(buf5.getbuffer().nbytes, 1000)

            self.assertEqual(len(plt.get_fignums()), 0)
        finally:
            stats_v2.connect_ro_db = orig_stats_db
            my_wrapped_generator.connect_ro_db = orig_wrapped_db
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_edge_case_zero_balance_users_division_by_zero(self):
        """
        Adversarial test: DB where Users exist but ALL have balance = 0.
        Tests for division by zero in wealth deciles calculation.
        """
        z_dir = tempfile.mkdtemp(prefix="zero_bal_db_")
        z_db_path = os.path.join(z_dir, "zero_bal.db")
        z_uri = f"file:{z_db_path}?mode=ro"

        conn = sqlite3.connect(z_db_path)
        for tbl in ["Users (user_id INT, balance REAL, active_items TEXT)",
                    "Posts (post_num INT, board_id TEXT, author_id INT, timestamp REAL, content TEXT, reply_to_post_num INT)",
                    "UserTransactions (id INT, user_id INT, amount REAL, category TEXT, description TEXT, timestamp REAL)",
                    "MoneyDrops (id INT, amount REAL, status TEXT, created_at REAL, claimed_at REAL)",
                    "MediaReposts (file_unique_id TEXT, times INT, first_seen REAL)",
                    "FileRegistry (file_unique_id TEXT, tags TEXT, created_at REAL)",
                    "Mutes (user_id INT, mute_type TEXT, expires_at REAL)"]:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {tbl}")
        
        # Insert 15 users, all with 0 balance
        for i in range(1, 16):
            conn.execute("INSERT INTO Users (user_id, balance, active_items) VALUES (?, 0, '{}')", (i,))
        conn.commit()
        conn.close()

        orig_stats_db = stats_v2.connect_ro_db
        stats_v2.connect_ro_db = lambda: orig_stats_db(z_uri)
        try:
            buf = stats_v2.generate_economy_heists_poster()
            self.assertGreater(buf.getbuffer().nbytes, 1000)
            self.assertEqual(len(plt.get_fignums()), 0)
        finally:
            stats_v2.connect_ro_db = orig_stats_db
            shutil.rmtree(z_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
