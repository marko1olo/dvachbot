import unittest
import re
import html
from abu_engine import (
    transform_abu_mode,
    generate_bugurt,
    generate_deanon,
    generate_opushchenie,
    generate_psychiatry,
    generate_abu_voice,
    _format_procedural_bugurt,
    _format_greentext_novel,
    _format_thread_mirror,
    _format_abu_voice_memo,
    _format_psych_dossier,
    _format_abu_ticket,
    _format_server_incident,
    _format_captcha_disaster,
    _format_board_catalog,
    _format_opushchenie,
    _format_punitive_deanon,
    _format_punitive_psychiatry,
    _format_abu_execution_voice,
    _ABU_LEXICON,
)

ZOOMER_BAN_WORDS = ["скуф", "альтушк", "масик", "тиндер", "онлифанс", "нормис", "кринж"]

class TestAbuEngineSuite(unittest.TestCase):
    def test_lexicon_no_zoomer_words(self):
        """Verifies that _ABU_LEXICON does not contain any zoomer slang."""
        for word, replacements in _ABU_LEXICON.items():
            for ban in ZOOMER_BAN_WORDS:
                self.assertNotIn(ban, word.lower(), f"Zoomer word '{ban}' found in lexicon key '{word}'")
                for r in replacements:
                    self.assertNotIn(ban, r.lower(), f"Zoomer word '{ban}' found in replacement '{r}'")

    def test_all_13_formats_direct(self):
        """Tests each of the 13 generation formats directly with realistic 2ch input."""
        sample = "сижу ночью в сычевальне, пью пиво и думаю о жизни"
        formats = [
            _format_procedural_bugurt,
            _format_greentext_novel,
            _format_thread_mirror,
            _format_abu_voice_memo,
            _format_psych_dossier,
            _format_abu_ticket,
            _format_server_incident,
            _format_captcha_disaster,
            _format_board_catalog,
            _format_opushchenie,
            _format_punitive_deanon,
            _format_punitive_psychiatry,
            _format_abu_execution_voice,
        ]
        for fmt in formats:
            out = fmt(sample)
            self.assertIsInstance(out, str)
            self.assertGreater(len(out), 40, f"Output from {fmt.__name__} was too short")
            for ban in ZOOMER_BAN_WORDS:
                self.assertNotIn(ban, out.lower(), f"Zoomer word '{ban}' found in {fmt.__name__} output")

    def test_html_safety(self):
        """Verifies that malicious or broken HTML tags in input are safely neutralized."""
        malicious = "привет <script>alert(1)</script> <b>жирный <i>курсив</b> <a href='evil.com'>клик</a>"
        b = generate_bugurt(malicious)
        self.assertNotIn("<script>", b)
        self.assertNotIn("<a href='evil.com'>", b)

        d = generate_deanon(malicious)
        self.assertNotIn("<script>", d)

        o = generate_opushchenie(malicious)
        self.assertNotIn("<script>", o)

    def test_standalone_helpers(self):
        """Verifies that all standalone generator functions return valid non-empty strings."""
        text = "хочу купить пасскод у наримана"
        self.assertIn("БУГУРТ", generate_bugurt(text).upper())
        self.assertIn("ДЕАНОН", generate_deanon(text).upper())
        self.assertIn("ОПУСКАНИЯ", generate_opushchenie(text).upper())
        self.assertIn("ПСИХИАТРИИ", generate_psychiatry(text).upper())
        self.assertIn("НАРИМАН", generate_abu_voice(text).upper())

    def test_transform_abu_mode_dispatcher(self):
        """Runs the main dispatcher 50 times across short, medium, and long texts."""
        samples = [
            "лол",
            "сап двач",
            "батя принес пиво и ремень",
            "написал бугурт про еот и сижу плачу в сычевальне под одеялом",
        ]
        for _ in range(50):
            for s in samples:
                mode, out = transform_abu_mode(s)
                self.assertEqual(mode, "text")
                self.assertGreater(len(out), 50)
                for ban in ZOOMER_BAN_WORDS:
                    self.assertNotIn(ban, out.lower())

if __name__ == '__main__':
    unittest.main()
