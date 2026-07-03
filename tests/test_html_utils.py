import unittest
from common.html_utils import convert_site_tags_to_telegram

class TestConvertSiteTagsToTelegram(unittest.TestCase):
    def test_basic_tags(self):
        self.assertEqual(convert_site_tags_to_telegram("[b]bold[/b]"), "<b>bold</b>")
        self.assertEqual(convert_site_tags_to_telegram("[i]italic[/i]"), "<i>italic</i>")
        self.assertEqual(convert_site_tags_to_telegram("[s]strike[/s]"), "<s>strike</s>")
        self.assertEqual(convert_site_tags_to_telegram("[u]underline[/u]"), "<u>underline</u>")

    def test_code_tag(self):
        self.assertEqual(convert_site_tags_to_telegram("[code]some code[/code]"), "<code>some code</code>")

    def test_spoilers(self):
        self.assertEqual(convert_site_tags_to_telegram("||spoiler text||"), "<tg-spoiler>spoiler text</tg-spoiler>")
        self.assertEqual(convert_site_tags_to_telegram("[blur]spoiler text[/blur]"), "<tg-spoiler>spoiler text</tg-spoiler>")

    def test_visual_effects(self):
        self.assertEqual(convert_site_tags_to_telegram("[shake]shaking text[/shake]"), "<i>shaking text</i>")
        self.assertEqual(convert_site_tags_to_telegram("[rainbow]rainbow text[/rainbow]"), "<code>rainbow text</code>")
        self.assertEqual(convert_site_tags_to_telegram("[glitch]glitching text[/glitch]"), "<s><code>glitching text</code></s>")

    def test_case_insensitivity(self):
        self.assertEqual(convert_site_tags_to_telegram("[B]bold[/B]"), "<b>bold</b>")
        self.assertEqual(convert_site_tags_to_telegram("[Blur]spoiler[/BLUR]"), "<tg-spoiler>spoiler</tg-spoiler>")
        self.assertEqual(convert_site_tags_to_telegram("[I]italic[/i]"), "<i>italic</i>")

    def test_multiline_support(self):
        # tests re.DOTALL
        self.assertEqual(
            convert_site_tags_to_telegram("[b]line 1\nline 2[/b]"),
            "<b>line 1\nline 2</b>"
        )
        self.assertEqual(
            convert_site_tags_to_telegram("||spoiler\nwith newline||"),
            "<tg-spoiler>spoiler\nwith newline</tg-spoiler>"
        )

    def test_nested_tags(self):
        self.assertEqual(
            convert_site_tags_to_telegram("[b][i]bold italic[/i][/b]"),
            "<b><i>bold italic</i></b>"
        )

    def test_empty_string_and_none(self):
        self.assertEqual(convert_site_tags_to_telegram(""), "")
        self.assertEqual(convert_site_tags_to_telegram(None), "")

if __name__ == '__main__':
    unittest.main()
