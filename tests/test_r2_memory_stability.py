import pytest
import re
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch

import shared_state
from shared_state import BoundedDict, message_to_post
from common.text_chunker import (
    count_tg_utf16_units,
    utf16_to_char_index,
    get_open_tags,
    chunk_html_message,
    safe_html_truncate,
)


class HTMLTagValidator(HTMLParser):
    """HTML parser that verifies all tags are properly balanced and closed."""
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in ("br", "hr", "img"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"Unexpected end tag </{tag}> with empty stack")
        elif self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"Mismatched end tag </{tag}>, expected </{self.stack[-1]}>")

    def validate(self, html_text: str):
        self.reset()
        self.stack.clear()
        self.errors.clear()
        self.feed(html_text)
        if self.stack:
            self.errors.append(f"Unclosed tags at end: {self.stack}")
        return len(self.errors) == 0, self.errors


class TestBoundedDict:
    """Comprehensive tests for BoundedDict capacity enforcement and FIFO/LRU eviction."""

    def test_bounded_dict_basic_ops(self):
        bd = BoundedDict(max_size=5)
        for i in range(5):
            bd[f"k{i}"] = i
        assert len(bd) == 5
        assert bd["k0"] == 0
        assert bd.get("k4") == 4
        assert "k2" in bd
        assert bd.pop("k2") == 2
        assert len(bd) == 4

    def test_bounded_dict_evicts_oldest_on_limit_exceeded(self):
        """Inserting items past max_size evicts oldest in O(1) time."""
        limit = 100
        bd = BoundedDict(max_size=limit)
        for i in range(250):
            bd[i] = f"val_{i}"
        
        assert len(bd) == limit
        # Oldest 150 items (0..149) should have been evicted
        for i in range(150):
            assert i not in bd
        # Latest 100 items (150..249) must be retained
        for i in range(150, 250):
            assert i in bd
            assert bd[i] == f"val_{i}"

    def test_bounded_dict_reassign_refreshes_recency(self):
        """Setting an existing key moves it to most recent, surviving eviction."""
        bd = BoundedDict(max_size=3)
        bd["a"] = 1
        bd["b"] = 2
        bd["c"] = 3

        # Re-set "a" -> "a" moves to most recent
        bd["a"] = 10
        # Add "d" -> should evict "b" (oldest), not "a"
        bd["d"] = 4
        assert len(bd) == 3
        assert "b" not in bd
        assert "a" in bd
        assert "c" in bd
        assert "d" in bd

    def test_bounded_dict_update_enforces_limit(self):
        bd = BoundedDict(max_size=5)
        bd.update({f"key_{i}": i for i in range(10)})
        assert len(bd) == 5
        for i in range(5):
            assert f"key_{i}" not in bd
        for i in range(5, 10):
            assert f"key_{i}" in bd

    def test_bounded_dict_setdefault_enforces_limit(self):
        bd = BoundedDict(max_size=3)
        bd["x"] = 1
        bd["y"] = 2
        bd["z"] = 3
        bd.setdefault("w", 4)
        assert len(bd) == 3
        assert "x" not in bd
        assert bd["w"] == 4

    def test_shared_state_message_to_post_is_bounded(self):
        """Verifies shared_state.message_to_post is an instance of BoundedDict with max_size=20000."""
        assert isinstance(shared_state.message_to_post, BoundedDict)
        assert shared_state.message_to_post.max_size == 20000

    def test_db_fallback_simulation_on_cache_eviction(self):
        """
        Simulates resolving post_num after cache eviction:
        When an old copy is evicted from message_to_post in RAM,
        the DB fallback to get_post_info_by_copy recovers post_num.
        """
        cache = BoundedDict(max_size=3)
        db_store = {
            (100, 1001): 501,
            (100, 1002): 502,
            (100, 1003): 503,
            (100, 1004): 504,
        }

        # Populate cache
        for k, v in db_store.items():
            cache[k] = v

        # Cache only contains latest 3
        assert len(cache) == 3
        assert (100, 1001) not in cache

        # Simulated lookup function matching handlers/message_router.py pattern
        def resolve_post(chat_id, mid):
            hit = cache.get((chat_id, mid))
            if hit is not None:
                return hit
            # Fallback to DB
            return db_store.get((chat_id, mid))

        assert resolve_post(100, 1001) == 501
        assert resolve_post(100, 1004) == 504


class TestTextChunker:
    """Comprehensive tests for proactive HTML-aware message chunking and tag balancing."""

    def test_count_tg_utf16_units(self):
        assert count_tg_utf16_units("") == 0
        assert count_tg_utf16_units("hello") == 5
        assert count_tg_utf16_units("Привет, мир!") == 12
        # Emojis in astral plane count as 2 UTF-16 units
        assert count_tg_utf16_units("🔥") == 2
        assert count_tg_utf16_units("💩") == 2
        assert count_tg_utf16_units("A🔥B") == 4

    def test_chunk_html_message_under_limit(self):
        text = "<b>Short text</b> under the limit."
        chunks = chunk_html_message(text, max_chars=4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_html_message_paragraph_splitting(self):
        p1 = "Paragraph 1: " + ("word " * 500)
        p2 = "Paragraph 2: " + ("word " * 500)
        full_text = f"{p1}\n\n{p2}"
        
        chunks = chunk_html_message(full_text, max_chars=3500)
        assert len(chunks) >= 2
        for chk in chunks:
            assert count_tg_utf16_units(chk) <= 3500

    def test_chunk_html_message_balances_open_tags(self):
        """When text wrapped in HTML is split, tags are closed in chunk 1 and reopened in chunk 2."""
        content = "Аноны на борде обсуждали важные темы. " * 80
        full_text = f"<b><i>{content}</i></b>"

        chunks = chunk_html_message(full_text, max_chars=1000)
        assert len(chunks) > 1

        validator = HTMLTagValidator()
        for idx, chk in enumerate(chunks):
            assert count_tg_utf16_units(chk) <= 1000
            valid, errors = validator.validate(chk)
            assert valid, f"Chunk {idx} has unbalanced tags: {errors} | Text: {chk[:100]}...{chk[-100:]}"
            # First chunk must end with closing tags
            if idx == 0:
                assert chk.endswith("</i></b>")
            # Intermediate / final chunks must start with reopening tags
            if idx > 0:
                assert chk.startswith("<b><i>")

    def test_chunk_html_message_nested_blockquotes_and_links(self):
        """Blockquotes and hyperlinks are preserved and properly closed/reopened across boundaries."""
        link_url = "https://2ch.hk/b/res/123456.html"
        long_para = "Двачеры спорят о жизни и судьбе анонима. " * 60
        full_text = (
            f"<blockquote><b>Цитата Смотрящего:</b>\n"
            f"<a href=\"{link_url}\">{long_para}</a></blockquote>"
        )

        chunks = chunk_html_message(full_text, max_chars=800)
        assert len(chunks) > 1

        validator = HTMLTagValidator()
        for idx, chk in enumerate(chunks):
            assert count_tg_utf16_units(chk) <= 800
            valid, errors = validator.validate(chk)
            assert valid, f"Chunk {idx} invalid: {errors}\nContent: {chk}"

    def test_chunk_html_message_does_not_slice_inside_tag(self):
        """Chunking must never cut through an HTML tag or HTML entity."""
        tag = '<a href="https://very-long-url.example.com/path?param1=value1&param2=value2">'
        text = "Hello " * 100 + tag + "Link Text" + "</a>" + " World " * 100

        chunks = chunk_html_message(text, max_chars=600)
        for idx, chk in enumerate(chunks):
            assert "<a href=" not in chk or tag in chk or chk.startswith(tag), f"Cut inside tag in chunk {idx}"
            # Check no unclosed < bracket without matching >
            open_count = chk.count("<")
            close_count = chk.count(">")
            assert open_count == close_count, f"Mismatched angle brackets in chunk {idx}"

    def test_safe_html_truncate_closes_tags(self):
        """safe_html_truncate truncates cleanly and closes all open tags."""
        text = "<b><i><u>" + ("Очень длинный текст поста " * 50) + "</u></i></b>"
        truncated = safe_html_truncate(text, max_units=200, suffix="…")
        
        assert count_tg_utf16_units(truncated) <= 200
        assert truncated.endswith("…</u></i></b>")
        validator = HTMLTagValidator()
        valid, errors = validator.validate(truncated)
        assert valid, f"Truncated text has tag errors: {errors}"

    def test_safe_html_truncate_short_text_unchanged(self):
        short = "<b>Короткий текст</b>"
        assert safe_html_truncate(short, max_units=1000) == short
