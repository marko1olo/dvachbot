# -*- coding: utf-8 -*-
"""
Tests for split_text utility function in utils.py.
Validates chunking, HTML tag balancing, Telegram UTF-16 unit limits,
numbering suffixes, and edge cases.
"""

import pytest
from utils import split_text
from common.text_chunker import count_tg_utf16_units, get_open_tags


class TestSplitTextBasics:
    """Basic behavior and edge cases with short texts and empty input."""

    def test_empty_string(self):
        """Empty string returns a list with a single empty string."""
        assert split_text("", 100) == [""]

    def test_short_text_fits_within_limit(self):
        """Text whose length is strictly less than limit should be returned intact without suffixes."""
        text = "Hello world! Short message."
        res = split_text(text, 100)
        assert res == [text]
        assert len(res) == 1

    def test_text_exactly_at_limit(self):
        """Text whose length matches limit exactly should not be split."""
        text = "a" * 100
        res = split_text(text, 100)
        assert res == [text]
        assert len(res) == 1

    @pytest.mark.parametrize("limit", [50, 100, 500, 4096])
    def test_single_chunk_invariant(self, limit):
        """Any text well under the limit returns unchanged."""
        text = "Simple short text"
        res = split_text(text, limit)
        assert res == [text]


class TestSplitTextChunkingAndSuffixes:
    """Tests chunking logic, boundary handling, and (i/N) pagination suffixes."""

    def test_text_exceeding_limit_adds_numbering_suffix(self):
        """Text exceeding limit is broken into multiple chunks with (i/N) suffixes."""
        text = "Word " * 100  # 500 chars
        limit = 150
        chunks = split_text(text, limit)

        assert len(chunks) > 1
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            expected_suffix = f"\n({i + 1}/{total})"
            assert chunk.endswith(expected_suffix), f"Chunk {i} missing suffix: {chunk}"
            assert count_tg_utf16_units(chunk) <= limit

    def test_each_chunk_strictly_respects_limit(self):
        """Ensures that for large text, all chunks strictly satisfy count_tg_utf16_units <= limit."""
        text = "Paragraph one with plenty of descriptive content.\n\n" * 50
        limit = 400
        chunks = split_text(text, limit)

        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            units = count_tg_utf16_units(chunk)
            assert units <= limit, f"Chunk {i + 1}/{len(chunks)} exceeded limit {limit}: {units} units"

    def test_reconstruction_contains_all_content(self):
        """Ensures all words from the original text are retained across chunks."""
        words = [f"word{i}" for i in range(200)]
        text = " ".join(words)
        chunks = split_text(text, limit=120)

        # Strip pagination suffix from chunks and rejoin
        reconstructed = ""
        for chunk in chunks:
            # Suffix is \n(i/N)
            cleaned = chunk.rsplit("\n(", 1)[0]
            reconstructed += " " + cleaned

        for w in words:
            assert w in reconstructed, f"Word {w} lost during split_text!"

    def test_split_prefers_newlines_over_spaces(self):
        """Checks that chunking breaks at clean paragraph / newline boundaries when possible."""
        p1 = "A" * 60
        p2 = "B" * 60
        text = f"{p1}\n\n{p2}"
        # effective_limit = max(50, 100 - 25) = 75
        chunks = split_text(text, limit=100)
        assert len(chunks) == 2
        assert "A" * 60 in chunks[0]
        assert "B" * 60 in chunks[1]


class TestSplitTextHtmlBalancing:
    """Validates HTML tag balancing and formatting across chunks."""

    def test_html_tag_closed_and_reopened_across_chunks(self):
        """HTML formatting tags like <b> must be properly closed and reopened across chunks."""
        body = "Very long bold content text. " * 50  # ~1500 chars
        text = f"<b>{body}</b>"
        limit = 800

        chunks = split_text(text, limit=limit)
        assert len(chunks) > 1

        for idx, chunk in enumerate(chunks):
            assert count_tg_utf16_units(chunk) <= limit
            # Tags must be balanced: get_open_tags should return empty list
            open_tags = get_open_tags(chunk)
            assert not open_tags, f"Chunk {idx + 1} has unclosed tags: {open_tags} in '{chunk}'"

        # The first chunk should start with <b> and close with </b> before suffix
        assert chunks[0].startswith("<b>")
        assert "</b>" in chunks[0]
        # Subsequent chunk should reopen <b>
        assert chunks[1].startswith("<b>")
        assert "</b>" in chunks[1]

    def test_nested_html_tags_balanced(self):
        """Nested formatting tags <b><i>...</i></b> must be balanced in all parts."""
        inner = "Nested italic and bold words inside. " * 50
        text = f"<b>Important: <i>{inner}</i> finish.</b>"
        limit = 800

        chunks = split_text(text, limit=limit)
        assert len(chunks) > 1

        for idx, chunk in enumerate(chunks):
            assert count_tg_utf16_units(chunk) <= limit
            open_tags = get_open_tags(chunk)
            assert not open_tags, f"Chunk {idx + 1} has unbalanced tags: {open_tags}"

    def test_unclosed_html_in_input_is_balanced_in_single_chunk(self):
        """If input has unclosed HTML tags but fits in limit, split_text balances them."""
        text = "<b>Unclosed bold text"
        res = split_text(text, limit=100)
        assert res == ["<b>Unclosed bold text</b>"]

    def test_unclosed_html_in_input_balanced_across_multiple_chunks(self):
        """If input has unclosed tags and exceeds limit, each chunk is validly balanced."""
        text = "<b>" + ("Unclosed long bold block of text. " * 35)
        chunks = split_text(text, limit=300)
        assert len(chunks) > 1
        for idx, chunk in enumerate(chunks):
            open_tags = get_open_tags(chunk)
            assert not open_tags, f"Unclosed tags in chunk {idx + 1}: {open_tags}"


class TestSplitTextUnicodeAndAstralChars:
    """Ensures UTF-16 surrogate pairs (e.g. emojis) are counted properly and never clipped."""

    def test_emojis_count_as_2_utf16_units(self):
        """Astral emojis count as 2 UTF-16 units; chunking respects limit without surrogate splitting."""
        # 🔥 is 2 UTF-16 code units
        emojis = "🔥" * 60  # 120 UTF-16 units
        limit = 100
        chunks = split_text(emojis, limit=limit)

        assert len(chunks) > 1
        for idx, chunk in enumerate(chunks):
            units = count_tg_utf16_units(chunk)
            assert units <= limit
            # Ensure no lone surrogate corrupted utf-8 encoding/decoding
            assert chunk.encode("utf-16", errors="strict")

    def test_cyrillic_and_mixed_unicode_text(self):
        """Cyrillic characters (BMP, 1 unit each) mixed with emoji and punctuation."""
        sample = "Привет, мир! 🚀 " * 20
        limit = 120
        chunks = split_text(sample, limit=limit)
        assert len(chunks) > 1
        for chunk in chunks:
            assert count_tg_utf16_units(chunk) <= limit


class TestSplitTextBoundaryAndEdgeCases:
    """Stress tests and boundary condition edge cases."""

    def test_continuous_unbroken_string(self):
        """String with no spaces or newlines splits cleanly without infinite loop."""
        text = "X" * 300
        limit = 90
        chunks = split_text(text, limit=limit)
        assert len(chunks) > 1
        for chunk in chunks:
            assert count_tg_utf16_units(chunk) <= limit

    def test_minimum_practical_limit(self):
        """Function operates correctly with small limits (e.g. limit=60)."""
        text = "Small limit test with various words to chunk."
        chunks = split_text(text, limit=60)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert count_tg_utf16_units(chunk) <= 60

    def test_telegram_standard_limit(self):
        """Standard 4096 character limit handles large text properly."""
        p = "Это стандартный параграф текста для проверки лимита Telegram. " * 80  # ~4960 chars
        chunks = split_text(p, limit=4096)
        assert len(chunks) == 2
        for chunk in chunks:
            assert count_tg_utf16_units(chunk) <= 4096
            assert chunk.endswith(f"\n({chunks.index(chunk) + 1}/2)")
