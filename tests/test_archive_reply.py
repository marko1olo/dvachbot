# -*- coding: utf-8 -*-
import json
import time
import pytest
from common.text_utils import sanitize_html
from handlers.message_router import resolve_archive_or_inline_reply


# Helper to insert test posts into isolated test DB
async def _seed_test_post(db, post_num=501707, board_id="b", author_id=123, channel_message_id=None, text="Original post"):
    content = json.dumps({"type": "text", "text": text})
    now = time.time()
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp, channel_message_id) VALUES (?, ?, ?, ?, ?, ?)",
        (post_num, board_id, author_id, content, now, channel_message_id)
    )


# ---------------------------------------------------------------------------
# Category 1: Archive Link Format Variants
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_1_archive_link_formats(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    variants = [
        "https://t.me/tgchan_archive/501707",
        "http://t.me/tgchan_archive/501707",
        "t.me/tgchan_archive/501707",
        "https://telegram.me/tgchan_archive/501707",
        "telegram.me/tgchan_archive/501707",
        "https://t.me/tgach_archive/501707",
        "http://t.me/tgach_archive/501707",
        "t.me/tgach_archive/501707",
        "https://t.me/c/1234567890/501707",
        "HTTPS://T.ME/TGCHAN_ARCHIVE/501707",
    ]

    for url in variants:
        # Without extra text -> fallback to >>501707
        pnum, cleaned = await resolve_archive_or_inline_reply(url)
        assert pnum == 501707, f"Failed resolving pnum for {url}"
        assert cleaned == ">>501707", f"Failed cleaned text fallback for {url}: got {cleaned!r}"

        # With trailing text -> cleaned text should be the message body
        pnum_text, cleaned_text = await resolve_archive_or_inline_reply(f"{url}\nтекст ответа")
        assert pnum_text == 501707, f"Failed resolving pnum for {url} with text"
        assert cleaned_text == "текст ответа", f"Failed cleaned text for {url}: got {cleaned_text!r}"


# ---------------------------------------------------------------------------
# Category 2: Query String & Fragment Consumption
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_2_query_and_fragment_consumption(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    query_cases = [
        ("https://t.me/tgchan_archive/501707?single", ">>501707"),
        ("https://t.me/tgchan_archive/501707?single\nТекст ответа", "Текст ответа"),
        ("https://t.me/tgchan_archive/501707?comment=123", ">>501707"),
        ("https://t.me/tgchan_archive/501707?comment=123\nКомментарий к посту", "Комментарий к посту"),
        ("https://t.me/tgchan_archive/501707?single&utm_source=tg", ">>501707"),
        ("https://t.me/tgchan_archive/501707#post-501707", ">>501707"),
        ("https://t.me/tgchan_archive/501707?single#fragment", ">>501707"),
        ("https://t.me/tgchan_archive/501707/?single", ">>501707"),
        ("https://t.me/tgchan_archive/501707/?single\nответ с косой чертой", "ответ с косой чертой"),
        ("https://t.me/tgchan_archive/501707?a=1&b=2\nпараметры съедены", "параметры съедены"),
    ]

    for raw_input, expected_cleaned in query_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(raw_input)
        assert pnum == 501707, f"Failed resolving pnum for query case: {raw_input}"
        assert cleaned == expected_cleaned, f"Query/fragment leaked for {raw_input}: got {cleaned!r}, expected {expected_cleaned!r}"


# ---------------------------------------------------------------------------
# Category 3: External Telegram Links Preservation (Must NOT match)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_3_external_links_preservation(isolated_test_db):
    db = isolated_test_db
    # Seed post 501707 to ensure that even if an external link ends with 501707, it is NEVER hijacked!
    await _seed_test_post(db, post_num=501707)

    external_links = [
        "https://t.me/durov/123",
        "https://t.me/random_news/456",
        "https://t.me/breakingmash/45678",
        "https://t.me/telegram/123",
        "https://t.me/external_chan/501707",
        "https://t.me/durov/501707?single\nвнешняя новость",
        "https://t.me/dvach_chatbot?start=thread_501707",
        "https://t.me/joinchat/AAAAAF123",
        "https://t.me/+AbCdEfGh123",
        "t.me/botfather",
        "https://t.me/s/durov/501707",
        "https://t.me/not_archive_channel/501707\nкомментарий",
    ]

    for ext_input in external_links:
        pnum, cleaned = await resolve_archive_or_inline_reply(ext_input)
        assert pnum is None, f"External link was incorrectly intercepted as reply: {ext_input} -> pnum={pnum}"
        assert cleaned == ext_input, f"External link text was modified: {ext_input} -> {cleaned}"


# ---------------------------------------------------------------------------
# Category 4: Board URLs (tgach.top and external boards)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_4_board_urls(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    board_cases = [
        ("https://tgach.top/b/res/501707.html#post-501707\nкомментарий", 501707, "комментарий"),
        ("https://tgach.top/b/res/501707.html#501707", 501707, ">>501707"),
        ("https://tgach.top/b/res/501707.html", 501707, ">>501707"),
        ("https://tgach.top/b/res/501707", 501707, ">>501707"),
        ("http://tgach.top/a/res/501707.html", 501707, ">>501707"),
        ("tgach.top/po/res/501707.html#post-501707", 501707, ">>501707"),
        ("tgach.top/wh40k/res/501707.html", 501707, ">>501707"),
        ("https://tgach.top/b/res/501707.html?comment=1#post-501707", 501707, ">>501707"),
        ("https://tgach.top/vg/res/501707.html?theme=dark", 501707, ">>501707"),
    ]

    for raw_url, exp_pnum, exp_cleaned in board_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(raw_url)
        assert pnum == exp_pnum, f"Board URL resolution failed for {raw_url}: got {pnum}, expected {exp_pnum}"
        assert cleaned == exp_cleaned, f"Board URL cleaned text mismatch for {raw_url}: got {cleaned!r}, expected {exp_cleaned!r}"

    # External boards (e.g. 2ch, 4chan) must NOT be intercepted
    external_boards = [
        "https://2ch.hk/b/res/501707.html",
        "https://4chan.org/b/res/501707",
        "https://example.com/b/res/501707.html",
    ]
    for ext_url in external_boards:
        pnum, cleaned = await resolve_archive_or_inline_reply(ext_url)
        assert pnum is None, f"External board link intercepted: {ext_url}"
        assert cleaned == ext_url, f"External board text altered: {ext_url}"


# ---------------------------------------------------------------------------
# Category 5: Explicit Citations
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_5_explicit_citations(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    citation_cases = [
        (">>501707\nответ на пост", 501707, "ответ на пост"),
        ("&gt;&gt;501707\nответ на пост", 501707, "ответ на пост"),
        ("#501707\nответ на пост", 501707, "ответ на пост"),
        ("№501707\nответ на пост", 501707, "ответ на пост"),
        ("Post #501707\nответ на пост", 501707, "ответ на пост"),
        ("Post#501707\nответ на пост", 501707, "ответ на пост"),
        ("Post 501707\nответ на пост", 501707, "ответ на пост"),
        (">> 501707\nответ на пост", 501707, "ответ на пост"),
        ("&gt;&gt; 501707\nответ на пост", 501707, "ответ на пост"),
        ("# 501707\nответ на пост", 501707, "ответ на пост"),
        ("№ 501707\nответ на пост", 501707, "ответ на пост"),
        (">>501707", 501707, ">>501707"),
        ("&gt;&gt;501707", 501707, ">>501707"),
        ("Post #501707", 501707, ">>501707"),
    ]

    for text_input, exp_pnum, exp_cleaned in citation_cases:
        pnum, cleaned = await resolve_archive_or_inline_reply(text_input)
        assert pnum == exp_pnum, f"Citation resolution failed for {text_input!r}: got {pnum}, expected {exp_pnum}"
        assert cleaned == exp_cleaned, f"Citation cleaned text mismatch for {text_input!r}: got {cleaned!r}, expected {exp_cleaned!r}"


# ---------------------------------------------------------------------------
# Category 6: Database Lookup Resolution Tiers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_6_database_lookup_tiers(isolated_test_db):
    db = isolated_test_db
    # Post A: Direct post_num = 501707
    await _seed_test_post(db, post_num=501707, channel_message_id=None)

    # Post B: post_num = 501708, channel_message_id = 99991
    await _seed_test_post(db, post_num=501708, channel_message_id=99991)

    # Post C: post_num = 501709, copy in PostCopies with message_id = 88882
    await _seed_test_post(db, post_num=501709, channel_message_id=None)
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, ?, ?)",
        (501709, 123456, 88882)
    )

    # Tier 1: Direct post_num
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/501707\nTier 1 direct")
    assert pnum == 501707
    assert cleaned == "Tier 1 direct"

    # Tier 2: channel_message_id lookup in Posts
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/99991\nTier 2 channel msg")
    assert pnum == 501708
    assert cleaned == "Tier 2 channel msg"

    # Tier 3: PostCopies message_id lookup
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/88882\nTier 3 copy msg")
    assert pnum == 501709
    assert cleaned == "Tier 3 copy msg"

    # Tier 4: Non-existent post ID -> returns (None, original_text)
    non_existent_url = "https://t.me/tgchan_archive/7777777\nНесуществующий пост"
    pnum, cleaned = await resolve_archive_or_inline_reply(non_existent_url)
    assert pnum is None
    assert cleaned == non_existent_url

    non_existent_cite = ">>7777777\nЦитата на несуществующий пост"
    pnum, cleaned = await resolve_archive_or_inline_reply(non_existent_cite)
    assert pnum is None
    assert cleaned == non_existent_cite


# ---------------------------------------------------------------------------
# Category 7: Whitespace & Text Boundary Cleanliness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_7_whitespace_and_boundaries(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    # Only link -> fallback to >>501707
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/501707?single")
    assert pnum == 501707
    assert cleaned == ">>501707"

    # Leading spaces
    pnum, cleaned = await resolve_archive_or_inline_reply("   https://t.me/tgchan_archive/501707?single\nтекст с пробелами")
    assert pnum == 501707
    assert cleaned == "текст с пробелами"

    # Leading newline
    pnum, cleaned = await resolve_archive_or_inline_reply("\n>>501707\nтекст с переносом строки")
    assert pnum == 501707
    assert cleaned == "текст с переносом строки"

    # Trailing newlines
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/501707?single\n\n")
    assert pnum == 501707
    assert cleaned == ">>501707"

    # Multiple whitespace and newlines around citation
    pnum, cleaned = await resolve_archive_or_inline_reply("  \n  >>501707  \n  ")
    assert pnum == 501707
    assert cleaned == ">>501707"

    # None and empty inputs
    pnum, cleaned = await resolve_archive_or_inline_reply(None)
    assert pnum is None
    assert cleaned is None

    pnum, cleaned = await resolve_archive_or_inline_reply("")
    assert pnum is None
    assert cleaned == ""

    pnum, cleaned = await resolve_archive_or_inline_reply(12345)
    assert pnum is None
    assert cleaned == 12345


# ---------------------------------------------------------------------------
# Category 8: Message Router Integration / Formatting Checks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_8_message_router_integration(isolated_test_db):
    db = isolated_test_db
    await _seed_test_post(db, post_num=501707)

    # 1. Simulate single text message reply extraction and HTML sanitization
    raw_text = "https://t.me/tgchan_archive/501707?single\n<b>Важный</b> ответ &amp; комментарий"
    reply_to_post = None
    text_for_corpus = raw_text
    content = {'text': raw_text}

    if not reply_to_post and text_for_corpus:
        resolved_pnum, cleaned_corpus_text = await resolve_archive_or_inline_reply(text_for_corpus)
        if resolved_pnum:
            reply_to_post = resolved_pnum
            text_for_corpus = cleaned_corpus_text
            content['text'] = sanitize_html(cleaned_corpus_text)

    assert reply_to_post == 501707
    assert text_for_corpus == "<b>Важный</b> ответ &amp; комментарий"
    assert "tgchan_archive" not in content['text']
    assert "?single" not in content['text']
    assert "<b>Важный</b>" in content['text']

    # 2. Simulate photo caption reply extraction and HTML sanitization
    raw_caption = "https://tgach.top/b/res/501707.html#post-501707\nПодпись к картинке"
    reply_to_post_photo = None
    text_for_corpus_photo = raw_caption
    content_photo = {'caption': raw_caption}

    if not reply_to_post_photo and text_for_corpus_photo:
        resolved_pnum, cleaned_corpus_text = await resolve_archive_or_inline_reply(text_for_corpus_photo)
        if resolved_pnum:
            reply_to_post_photo = resolved_pnum
            text_for_corpus_photo = cleaned_corpus_text
            content_photo['caption'] = sanitize_html(cleaned_corpus_text)

    assert reply_to_post_photo == 501707
    assert content_photo['caption'] == "Подпись к картинке"

    # 3. Simulate message with external link: must keep reply_to_post = None and preserve link
    raw_external = "https://t.me/durov/123\nТекст с внешней ссылкой на Дурова"
    reply_to_post_ext = None
    text_for_corpus_ext = raw_external
    content_ext = {'text': raw_external}

    if not reply_to_post_ext and text_for_corpus_ext:
        resolved_pnum, cleaned_corpus_text = await resolve_archive_or_inline_reply(text_for_corpus_ext)
        if resolved_pnum:
            reply_to_post_ext = resolved_pnum
            text_for_corpus_ext = cleaned_corpus_text
            content_ext['text'] = sanitize_html(cleaned_corpus_text)

    assert reply_to_post_ext is None
    assert text_for_corpus_ext == raw_external
    assert content_ext['text'] == raw_external

    # 4. Simulate media group caption handling
    raw_group_caption = "https://t.me/tgchan_archive/501707?comment=999\nПодпись медиагруппы"
    reply_to_group = None
    safe_caption_html = sanitize_html(raw_group_caption)

    if not reply_to_group and raw_group_caption:
        resolved_pnum, cleaned_cap = await resolve_archive_or_inline_reply(raw_group_caption)
        if resolved_pnum:
            reply_to_group = resolved_pnum
            safe_caption_html = sanitize_html(cleaned_cap)

    assert reply_to_group == 501707
    assert safe_caption_html == "Подпись медиагруппы"
