# -*- coding: utf-8 -*-
"""
Unit tests for utils.py (specifically split_text edge cases and behaviors).
"""

import unittest
from utils import split_text
from common.text_chunker import count_tg_utf16_units


class TestSplitTextEdgeCases(unittest.TestCase):
    def test_empty_string(self):
        """Empty string should return a list containing a single empty string."""
        self.assertEqual(split_text("", 100), [""])

    def test_falsy_or_none(self):
        """None or falsy input should return ['']."""
        self.assertEqual(split_text(None, 100), [""])

    def test_shorter_than_limit(self):
        """Text shorter than limit should be returned intact in a single chunk."""
        text = "Hello, world!"
        chunks = split_text(text, 100)
        self.assertEqual(chunks, [text])

    def test_exact_limit(self):
        """Text whose length/units equal the limit exactly should not be split."""
        text = "a" * 100
        chunks = split_text(text, 100)
        self.assertEqual(chunks, [text])
        self.assertEqual(len(chunks), 1)

    def test_one_char_over_limit(self):
        """Text just 1 character over limit must be split and numbered (1/N), (2/N)."""
        text = "a" * 101
        chunks = split_text(text, 100)
        self.assertGreaterEqual(len(chunks), 2)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            self.assertTrue(chunk.endswith(f"\n({i}/{total})"))
            self.assertLessEqual(count_tg_utf16_units(chunk), 100)

    def test_utf16_surrogate_pairs_emojis(self):
        """
        Emojis like 🚀 or 😀 take 1 Python character but 2 UTF-16 code units.
        Telegram limits are based on UTF-16 units, so split_text must enforce this limit.
        """
        # 50 emojis = 100 UTF-16 units
        emojis = "🚀" * 50
        self.assertEqual(count_tg_utf16_units(emojis), 100)

        # Fits exactly in limit=100
        chunks = split_text(emojis, 100)
        self.assertEqual(chunks, [emojis])

        # 51 emojis = 102 UTF-16 units -> must split because it exceeds limit=100
        emojis_over = "🚀" * 51
        self.assertEqual(count_tg_utf16_units(emojis_over), 102)
        chunks = split_text(emojis_over, 100)
        self.assertGreaterEqual(len(chunks), 2)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            self.assertTrue(chunk.endswith(f"\n({i}/{total})"))
            self.assertLessEqual(count_tg_utf16_units(chunk), 100)

    def test_html_tag_balancing_across_chunks(self):
        """HTML formatting tags opened in one chunk should be closed and reopened across chunks."""
        text = "<b>" + ("word " * 60) + "</b>"
        chunks = split_text(text, 100)
        self.assertGreaterEqual(len(chunks), 2)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            self.assertTrue(chunk.endswith(f"\n({i}/{total})"))
            self.assertLessEqual(count_tg_utf16_units(chunk), 100)
            # Tag balance check: number of <b> and </b> must match
            self.assertEqual(chunk.count("<b>"), chunk.count("</b>"))

    def test_nested_html_tag_balancing(self):
        """Nested HTML tags must remain balanced in each resulting chunk."""
        text = "<b><i><u>" + ("nested text " * 30) + "</u></i></b>"
        chunks = split_text(text, 100)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(chunk.count("<b>"), chunk.count("</b>"))
            self.assertEqual(chunk.count("<i>"), chunk.count("</i>"))
            self.assertEqual(chunk.count("<u>"), chunk.count("</u>"))

    def test_split_at_natural_boundaries(self):
        """Chunks should prefer natural paragraph breaks or newlines when possible."""
        p1 = "Paragraph 1: " + ("alpha " * 15)
        p2 = "Paragraph 2: " + ("beta " * 15)
        full_text = f"{p1}\n\n{p2}"

        chunks = split_text(full_text, limit=120)
        self.assertGreaterEqual(len(chunks), 2)
        # Check that paragraph 1 is cleanly isolated in first chunk
        self.assertIn("Paragraph 1:", chunks[0])
        self.assertIn("Paragraph 2:", chunks[1])

    def test_very_small_limit(self):
        """With very small limits, effective_limit is clamped to at least 50 chars."""
        text = "This is a sentence that is longer than the minimum effective limit."
        chunks = split_text(text, limit=60)
        self.assertIsInstance(chunks, list)
        self.assertGreaterEqual(len(chunks), 1)
        for chunk in chunks:
            self.assertIsInstance(chunk, str)

    def test_multichunk_large_text_suffixes(self):
        """Large text splitting into many chunks should number each chunk sequentially."""
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 30
        chunks = split_text(text, limit=150)
        self.assertGreater(len(chunks), 3)
        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            expected_suffix = f"\n({i}/{total})"
            self.assertTrue(
                chunk.endswith(expected_suffix),
                f"Chunk {i} expected to end with {expected_suffix}, got: {chunk[-15:]}"
            )
            self.assertLessEqual(count_tg_utf16_units(chunk), 150)

    def test_single_chunk_overflow_truncation(self):
        """When chunk_html_message returns 1 chunk but after tag balancing it exceeds limit."""
        # Unbalanced HTML tags that expand upon balancing
        text = "<b><i><u><code>" + ("a" * 35)
        chunks = split_text(text, limit=60)
        self.assertEqual(len(chunks), 1)
        self.assertLessEqual(count_tg_utf16_units(chunks[0]), 60)
        self.assertEqual(chunks[0].count("<b>"), chunks[0].count("</b>"))


if __name__ == '__main__':
    unittest.main()
