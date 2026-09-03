# -*- coding: utf-8 -*-
"""
Adversarial Stress Test Suite for Dvachbot Telegram Link Parsing & Archive Reply Resolution
Module: handlers/message_router.py
Functions: RE_ARCHIVE_LINK, resolve_archive_or_inline_reply
"""
import json
import time
import pytest
from handlers.message_router import RE_ARCHIVE_LINK, resolve_archive_or_inline_reply


async def _seed_test_post(db, post_num=501707, board_id="b", author_id=123, channel_message_id=None, text="Sample post"):
    content = json.dumps({"type": "text", "text": text})
    now = time.time()
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp, channel_message_id) VALUES (?, ?, ?, ?, ?, ?)",
        (post_num, board_id, author_id, content, now, channel_message_id)
    )


# ---------------------------------------------------------------------------
# Test Suite 1: Complex URLs (Query params, fragments, port, schemes)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_complex_archive_urls(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    complex_cases = [
        # (input_text, expected_post_num, expected_cleaned_text)
        ("https://t.me/tgchan_archive/501707?single&utm_source=tg#anchor", 501707, ">>501707"),
        ("https://t.me/tgchan_archive/501707?single&utm_source=tg#anchor\nОтвет на пост", 501707, "Ответ на пост"),
        ("http://t.me/tgchan_archive/501707/?param=val", 501707, ">>501707"),
        ("http://t.me/tgchan_archive/501707/?param=val\nкоммент", 501707, "коммент"),
        ("https://t.me/tgchan_archive/501707/?param=1&foo=bar&baz=123#sec2", 501707, ">>501707"),
        ("https://t.me/tgach_archive/501707?comment=42", 501707, ">>501707"),
        ("https://telegram.me/tgchan_archive/501707?ref=123\nтест", 501707, "тест"),
        ("https://t.me/c/1234567890/501707?single\nответ на пост в супергруппе", 501707, "ответ на пост в супергруппе"),
        ("https://tgach.top/b/res/501707.html?filter=all#post-501707", 501707, ">>501707"),
        ("https://tgach.top/b/res/12345.html?foo=bar#post-501707", 501707, ">>501707"),
        ("https://tgach.top/vg/res/501707?theme=dark#anchor\nгейминг тред", 501707, "гейминг тред"),
        ("https://tgach.top/wh40k/res/501707/?param=test\nза императора", 501707, "за императора"),
    ]

    for raw_input, exp_pnum, exp_cleaned in complex_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(raw_input)
        assert pnum == exp_pnum, f"Failed resolving pnum for {raw_input!r}: got {pnum}, expected {exp_pnum}"
        assert cleaned == exp_cleaned, f"Failed cleaned text for {raw_input!r}: got {cleaned!r}, expected {exp_cleaned!r}"


# ---------------------------------------------------------------------------
# Test Suite 2: Malicious / Tricky Channel Names (Must NOT Match)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_malicious_and_tricky_channel_names(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    tricky_channels = [
        "https://t.me/tgchan_archive_fake/501707",
        "https://t.me/not_tgchan_archive/501707",
        "https://t.me/durov_tgchan_archive/501707",
        "https://t.me/tgchan_archive2/501707",
        "https://t.me/tgach_archive_scam/501707",
        "https://t.me/my_tgach_archive/501707",
        "https://t.me/tgchan_archive/extra/501707",
        "https://t.me/tgchan_archives/501707",
        "https://t.me/c//501707",
        "https://t.me/c/abc/501707",
        "http://tgchan_archive/501707/?param=val",  # Missing t.me domain
        "https://faketgach.top/b/res/501707.html",
        "https://tgach.top.scam.com/b/res/501707.html",
    ]

    for tricky_url in tricky_channels:
        pnum, cleaned = await resolve_archive_or_inline_reply(tricky_url)
        assert pnum is None, f"Tricky channel URL was hijacked as archive reply: {tricky_url} -> pnum={pnum}"
        assert cleaned == tricky_url, f"Tricky channel text was mutated: {tricky_url} -> {cleaned}"


# ---------------------------------------------------------------------------
# Test Suite 3: External Telegram & Web URLs with existing DB post numbers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_external_channel_urls_preservation(isolated_test_db):
    db = isolated_test_db
    # Seed post 501707 to ensure external URLs with same number are strictly preserved
    await _seed_test_post(db, post_num=501707)

    external_urls = [
        "https://t.me/durov/501707",
        "https://t.me/news/501707?single",
        "https://t.me/crypto/501707#anchor",
        "https://t.me/s/tgchan_archive/501707",
        "https://t.me/s/durov/501707",
        "https://2ch.hk/b/res/501707.html",
        "https://4chan.org/b/501707",
        "https://example.com/501707",
        "https://t.me/durov/501707\nПривет Дуров",
        "https://2ch.hk/b/res/501707.html#501707\nСсылка на сосач",
    ]

    for ext_url in external_urls:
        pnum, cleaned = await resolve_archive_or_inline_reply(ext_url)
        assert pnum is None, f"External URL was falsely matched: {ext_url} -> pnum={pnum}"
        assert cleaned == ext_url, f"External URL was altered: {ext_url} -> {cleaned}"


# ---------------------------------------------------------------------------
# Test Suite 4: Whitespace, Newlines, Tabs & Boundary Cleanliness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_whitespace_and_boundaries_stress(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    boundary_cases = [
        # (input_text, expected_post_num, expected_cleaned_text)
        ("   \t\n  https://t.me/tgchan_archive/501707  \n\t  ", 501707, ">>501707"),
        ("\n\n\n>>501707\n\n\n", 501707, ">>501707"),
        ("\t#501707\t", 501707, ">>501707"),
        ("  №501707\nОтвет", 501707, "Ответ"),
        ("   Post #501707\nТестовое сообщение", 501707, "Тестовое сообщение"),
        ("https://t.me/tgchan_archive/501707\n\nТекст ответа со смайликами 🚀🔥", 501707, "Текст ответа со смайликами 🚀🔥"),
        ("https://t.me/tgchan_archive/501707   много пробелов после ссылки", 501707, "много пробелов после ссылки"),
    ]

    for raw_input, exp_pnum, exp_cleaned in boundary_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(raw_input)
        assert pnum == exp_pnum, f"Failed boundary test for {raw_input!r}: got {pnum}"
        assert cleaned == exp_cleaned, f"Boundary text mismatch for {raw_input!r}: got {cleaned!r}, expected {exp_cleaned!r}"


# ---------------------------------------------------------------------------
# Test Suite 5: Mid-Sentence Links & Non-Reply Contexts (Must NOT Intercept)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mid_sentence_and_enclosed_links_not_intercepted(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    non_reply_contexts = [
        "Посмотри на https://t.me/tgchan_archive/501707 вот это",
        "Вот ссылка: https://t.me/tgchan_archive/501707",
        "(https://t.me/tgchan_archive/501707)",
        "[Ссылка](https://t.me/tgchan_archive/501707)",
        "!https://t.me/tgchan_archive/501707",
        "Загляни на >>501707 потом",  # Mid-sentence citation
    ]

    for ctx_text in non_reply_contexts:
        pnum, cleaned = await resolve_archive_or_inline_reply(ctx_text)
        assert pnum is None, f"Mid-sentence or enclosed link was falsely intercepted: {ctx_text!r} -> pnum={pnum}"
        assert cleaned == ctx_text, f"Mid-sentence text was modified: {ctx_text!r} -> {cleaned!r}"


# ---------------------------------------------------------------------------
# Test Suite 6: ReDoS & Large Input Stress Harness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_redos_and_adversarial_stress(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    # 1. Very long query parameter
    long_query = "https://t.me/tgchan_archive/501707?" + ("a=" * 2000)
    t0 = time.perf_counter()
    pnum, cleaned = await resolve_archive_or_inline_reply(long_query)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2, f"ReDoS vulnerability detected on long query: elapsed {elapsed}s"
    assert pnum == 501707
    assert cleaned == ">>501707"

    # 2. Very long non-matching link with repeated slashes/special chars
    adversarial_junk = "https://t.me/" + ("archive/" * 500) + "501707"
    t0 = time.perf_counter()
    pnum, cleaned = await resolve_archive_or_inline_reply(adversarial_junk)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2, f"ReDoS vulnerability detected on junk link: elapsed {elapsed}s"
    assert pnum is None
    assert cleaned == adversarial_junk

    # 3. Oversized integer (overflow safety)
    huge_int_link = "https://t.me/tgchan_archive/" + ("9" * 100)
    pnum, cleaned = await resolve_archive_or_inline_reply(huge_int_link)
    assert pnum is None
    assert cleaned == huge_int_link

    # 4. Zero & negative inputs
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/0")
    assert pnum is None

    pnum, cleaned = await resolve_archive_or_inline_reply(">>-501707")
    assert pnum is None
    assert cleaned == ">>-501707"


# ---------------------------------------------------------------------------
# Test Suite 7: DB Fallback Tiers Completeness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_fallback_tiers_stress(isolated_test_db):
    db = isolated_test_db
    # Direct post
    await _seed_test_post(db, post_num=600001, channel_message_id=None)

    # Channel message mapping
    await _seed_test_post(db, post_num=600002, channel_message_id=770002)

    # PostCopies mapping
    await _seed_test_post(db, post_num=600003, channel_message_id=None)
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
        (600003, 99999, 880003)
    )

    # Tier 1 Direct
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/600001\nDirect post")
    assert pnum == 600001
    assert cleaned == "Direct post"

    # Tier 2 Channel Message ID
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/770002\nChannel post")
    assert pnum == 600002
    assert cleaned == "Channel post"

    # Tier 3 PostCopies Message ID
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/880003\nCopy post")
    assert pnum == 600003
    assert cleaned == "Copy post"

    # Non-matching ID
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/9999999\nNon-existent post")
    assert pnum is None
    assert cleaned == "https://t.me/tgchan_archive/9999999\nNon-existent post"
