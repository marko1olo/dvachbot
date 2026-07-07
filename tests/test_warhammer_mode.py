import unittest
import os
import sys
import re

# Ensure import paths work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# test_main.py mocks warhammer_mode and sets __getattr__ = MagicMock on it.
# Evict the mock so we import the real module.
import types
if 'warhammer_mode' in sys.modules:
    _wm = sys.modules['warhammer_mode']
    if isinstance(_wm, types.ModuleType) and getattr(_wm, '__spec__', None) is None:
        del sys.modules['warhammer_mode']

from warhammer_mode import orkify, necronify, warhammer_transform
from unittest.mock import patch, MagicMock

class TestWarhammerMode(unittest.TestCase):

    def test_orkify_basic_replacement(self):
        text = "собака чай куртка"
        result = orkify(text)
        self.assertTrue(result.isupper())
        self.assertIn("З", result)   # С -> З
        self.assertIn("Ш", result)   # Ч -> Ш
        self.assertNotIn("С", result)
        self.assertNotIn("Ч", result)
        # Note: К may appear in appended -ДАККА suffix, so don't assert its absence

    def test_orkify_dakka_append(self):
        text = "большое слово для тестирования добавления дакки"
        results = [orkify(text) for _ in range(30)]
        self.assertTrue(any("-ДАККА" in r for r in results))

    def test_orkify_gluing(self):
        text = "то ах ну да"
        results = [orkify(text) for _ in range(30)]
        has_glued = any(len(r.split()) < 4 for r in results)
        self.assertTrue(has_glued)

    def test_necronify_basic(self):
        result = necronify("тестовое сообщение")
        self.assertTrue(result.startswith("++Анализ органической речи:"))
        self.assertTrue(result.endswith("++Протокол выполнен.++"))
        self.assertIn("тестовое", result)
        self.assertIn("сообщение", result)

    def test_necronify_injection(self):
        text = "очень много разных слов для теста бинарных инъекций"
        results = [necronify(text) for _ in range(30)]
        has_binary = any(re.search(r'\+\+[01]{16}\+\+', r) for r in results)
        self.assertTrue(has_binary)





    def test_warhammer_transform_empty_text(self):
        result = warhammer_transform("")
        self.assertEqual(result, ('text', ""))

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    def test_warhammer_transform_image_success(self, mock_create, mock_random):
        mock_random.return_value = 0.1
        mock_create.return_value = b"mocked_image_bytes"
        result = warhammer_transform("короткий", header="Test", allow_image=True)
        self.assertEqual(result, ('image', b"mocked_image_bytes"))
        mock_create.assert_called_once_with(mode='warhammer', text=unittest.mock.ANY, header="Test")

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode._apply_thought_of_the_day')
    def test_warhammer_transform_image_failure_fallback(self, mock_apply, mock_create, mock_random):
        mock_random.return_value = 0.1
        mock_create.side_effect = Exception("Generation failed")
        mock_apply.return_value = "текст с МЫСЛЬ ДНЯ"
        result = warhammer_transform("текст", allow_image=True)
        self.assertEqual(result[0], 'text')
        self.assertIn("МЫСЛЬ ДНЯ", result[1])

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode._apply_thought_of_the_day')
    def test_warhammer_transform_imperium(self, mock_apply, mock_random):
        mock_random.return_value = 0.25 # < 0.30
        mock_apply.return_value = "простой с МЫСЛЬ ДНЯ"
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertIn("МЫСЛЬ ДНЯ", result[1])

    @patch('warhammer_mode.random.random')
    def test_warhammer_transform_chaos(self, mock_random):
        mock_random.return_value = 0.45 # < 0.57
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertNotIn("МЫСЛЬ ДНЯ", result[1])

    @patch('warhammer_mode.random.random')
    def test_warhammer_transform_orks(self, mock_random):
        mock_random.return_value = 0.65 # < 0.71
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertTrue(result[1].isupper())

    @patch('warhammer_mode.random.random')
    def test_warhammer_transform_necrons(self, mock_random):
        mock_random.return_value = 0.75 # < 0.80
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertTrue(result[1].startswith("++Анализ органической речи:"))

    @patch('warhammer_mode.random.random')
    def test_warhammer_transform_tyranids(self, mock_random):
        mock_random.return_value = 0.85 # < 0.88
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')

    @patch('warhammer_mode.random.random')
    def test_warhammer_transform_xenos(self, mock_random):
        mock_random.return_value = 0.90 # < 0.94
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertNotIn("МЫСЛЬ ДНЯ", result[1])

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode._apply_thought_of_the_day')
    def test_warhammer_transform_grimdark(self, mock_apply, mock_random):
        mock_random.return_value = 0.98 # >= 0.94
        mock_apply.return_value = "простой с МЫСЛЬ ДНЯ"
        result = warhammer_transform("простой", allow_image=False)
        self.assertEqual(result[0], 'text')
        self.assertIn("МЫСЛЬ ДНЯ", result[1])

if __name__ == '__main__':
    unittest.main()
