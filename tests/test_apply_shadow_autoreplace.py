import unittest
from unittest.mock import patch
import sys

class TestShadowAutoreplace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.psutil_patcher = patch.dict(sys.modules, {'psutil': unittest.mock.MagicMock()})
        cls.psutil_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.psutil_patcher.stop()

    def test_apply_shadow_autoreplace_empty(self):
        from main import apply_shadow_autoreplace
        self.assertEqual(apply_shadow_autoreplace({}), {})
        self.assertEqual(apply_shadow_autoreplace(None), None)

    def test_apply_shadow_autoreplace_no_text_or_caption(self):
        from main import apply_shadow_autoreplace
        content = {'other_key': 'value'}
        self.assertEqual(apply_shadow_autoreplace(content), content)

    def test_apply_shadow_autoreplace_long_text(self):
        from main import apply_shadow_autoreplace
        # 13 words
        content = {'text': 'word ' * 13 + 'кал'}
        self.assertEqual(apply_shadow_autoreplace(content), content)

    @patch('random.choice')
    def test_apply_shadow_autoreplace_shadow_words(self, mock_choice):
        from main import apply_shadow_autoreplace
        mock_choice.return_value = "shadow_replacement"
        content = {'text': 'это кал'}
        expected = {'text': 'это shadow_replacement'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

        content = {'caption': 'каловые массы здесь'}
        expected = {'caption': 'shadow_replacement здесь'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

    def test_apply_shadow_autoreplace_die_words(self):
        from main import apply_shadow_autoreplace
        content = {'text': 'сдохни'}
        expected = {'text': 'обоссы меня'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

        content = {'text': 'умрите'}
        expected = {'text': 'обоссыте меня'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

    @patch('random.choice')
    def test_apply_shadow_autoreplace_political(self, mock_choice):
        from main import apply_shadow_autoreplace
        # We need to test the specific choice lambda correctly if there are multiple replacements
        mock_choice.side_effect = ["великий укр", "руснявый"]

        content = {'text': 'хохол'}
        expected = {'text': 'великий укр'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

        content = {'caption': 'русский'}
        expected = {'caption': 'руснявый'}
        self.assertEqual(apply_shadow_autoreplace(content), expected)

if __name__ == '__main__':
    unittest.main()
