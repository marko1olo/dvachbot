# -*- coding: utf-8 -*-
"""
tests/test_stats_v2_forensics.py
================================
Comprehensive test suite verifying Requirement R5:
Database Sentiment & Moderation Forensics in stats_v2.py.
"""

import pytest
import time
import sqlite3

from stats_v2 import run_db_sentiment_moderation_forensics, generate_forensics_report_text


@pytest.mark.asyncio
async def test_sentiment_moderation_forensics(isolated_test_db):
    """Verifies that run_db_sentiment_moderation_forensics extracts structured forensics from DB."""
    db = isolated_test_db
    now_ts = time.time()

    import json
    # 1. Seed Posts (AI posts + user replies)
    p1 = "Я Киберчед. Жму 250кг на бицепс."
    p2 = ">>101 Чистая база, ты гигачад и сигма!"
    p3 = ">>101 Да пошел ты на хуй, сояк ебаный!"

    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (101, "b", 0, json.dumps({"type": "text", "text": p1}), p1, now_ts - 3600)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, reply_to_post_num, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (102, "b", 555, 101, json.dumps({"type": "text", "text": p2}), p2, now_ts - 3000)
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, reply_to_post_num, content, text_content, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (103, "b", 666, 101, json.dumps({"type": "text", "text": p3}), p3, now_ts - 2000)
    )

    # 2. Seed Mutes
    await db.execute(
        "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, ?, ?)",
        (666, "b", "shadow", now_ts + 1800)
    )
    await db.execute(
        "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, ?, ?)",
        (777, "b", "mute", now_ts + 7200)
    )

    # 3. Seed Reports
    await db.execute(
        "INSERT INTO Reports (post_num, category, reason, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (103, "flame", "Оскорбление Киберчеда", "resolved", now_ts - 1000)
    )

    # 4. Seed UserTransactions
    await db.execute(
        "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
        (555, -500.0, "rob", "Попытка ограбить Киберчеда (штраф за наглость)", int(now_ts - 1500))
    )
    await db.execute(
        "INSERT INTO UserTransactions (user_id, amount, category, description, timestamp) VALUES (?, ?, ?, ?, ?)",
        (777, 0.0, "combat", "Арест за ложный донос на Киберчеда (2ч)", int(now_ts - 1200))
    )
    await db.commit()

    import common.config
    db_uri = f"file:{common.config.DB_NAME}?mode=ro"

    res = run_db_sentiment_moderation_forensics(db_path=db_uri, days=7)

    assert res["total_posts"] >= 3
    ai_f = res["ai_forensics"]
    assert ai_f["posts_count"] == 1
    assert ai_f["replies_count"] == 2
    assert ai_f["sentiment_distribution"]["praise"] >= 1
    assert ai_f["sentiment_distribution"]["hostility"] >= 1

    mod_f = res["moderation_forensics"]
    assert mod_f["total_mutes"] == 2
    assert mod_f["total_reports"] == 1
    assert mod_f["false_report_arrests"] == 1

    eco_f = res["economy_forensics"]
    assert eco_f["robbery_fines_count"] == 1
    assert eco_f["robbery_fines_volume"] == 500.0

    # Verify text report generation
    text_report = generate_forensics_report_text(db_path=db_uri, days=7)
    assert "ФОРЕНЗИК-ОТЧЕТ" in text_report
    assert "Киберчед" in text_report
    assert "База" in text_report
