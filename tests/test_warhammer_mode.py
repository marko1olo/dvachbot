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

from unittest.mock import patch, ANY
from warhammer_mode import warhammer_transform

from warhammer_mode import orkify, necronify

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


class TestWarhammerTransform(unittest.TestCase):
    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    def test_warhammer_transform_empty(self, mock_create, mock_random):
        self.assertEqual(warhammer_transform(""), ('text', ""))
        mock_create.assert_not_called()

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    def test_warhammer_transform_image_success(self, mock_create, mock_random):
        # The regex substitutes might call random.random() depending on word match
        # Bypass the regex loop entirely by sending something that won't trigger random.random inside regexes
        mock_random.return_value = 0.1 # image chance < 0.20
        mock_create.return_value = b'test_image_bytes'

        result = warhammer_transform("123", header="test header", allow_image=True)

        self.assertEqual(result, ('image', b'test_image_bytes'))
        mock_create.assert_called_once_with(mode='warhammer', text=ANY, header="test header")

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode.orkify')
    @patch('warhammer_mode.random.choices')
    @patch('warhammer_mode.random.randint')
    def test_warhammer_transform_image_fallback_to_orks(self, mock_randint, mock_choices, mock_orkify, mock_create, mock_random):
        # "123" bypasses internal regex random calls.
        mock_random.side_effect = [0.1, 0.65] # 1st: image < 0.2, 2nd: faction orks < 0.71
        mock_create.return_value = None
        mock_orkify.return_value = "ORK TEXT"
        mock_choices.return_value = ["WAAAGH!"]
        mock_randint.return_value = 1

        result = warhammer_transform("123")

        self.assertEqual(result, ('text', "ORK TEXT WAAAGH!!!!"))
        mock_create.assert_called_once()
        mock_orkify.assert_called_once()

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode.necronify')
    def test_warhammer_transform_no_image_allowed(self, mock_necronify, mock_create, mock_random):
        mock_random.return_value = 0.75 # faction necrons < 0.80
        mock_necronify.return_value = "NECRON TEXT"

        result = warhammer_transform("123", allow_image=False)

        self.assertEqual(result, ('text', "NECRON TEXT"))
        mock_create.assert_not_called()
        mock_necronify.assert_called_once()

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode.generic_transform')
    @patch('warhammer_mode._apply_thought_of_the_day')
    def test_warhammer_transform_image_exception(self, mock_thought, mock_generic, mock_create, mock_random):
        mock_random.side_effect = [0.1, 0.1] # 1st image < 0.2, 2nd faction imperium < 0.3
        mock_create.side_effect = Exception("failed to gen image")
        mock_generic.return_value = "IMPERIUM TEXT"
        mock_thought.return_value = "THOUGHT TEXT"

        result = warhammer_transform("123")

        self.assertEqual(result, ('text', "THOUGHT TEXT"))
        mock_create.assert_called_once()
        mock_generic.assert_called_once()

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode.generic_transform')
    @patch('warhammer_mode._apply_thought_of_the_day')
    def test_warhammer_transform_imperium(self, mock_thought, mock_generic, mock_create, mock_random):
        mock_random.side_effect = [0.5, 0.2] # 1st image > 0.2, 2nd faction imperium < 0.3
        mock_generic.return_value = "IMPERIUM TEXT"
        mock_thought.return_value = "THOUGHT TEXT"

        result = warhammer_transform("123")

        self.assertEqual(result, ('text', "THOUGHT TEXT"))
        mock_create.assert_not_called()
        mock_generic.assert_called_once()

    @patch('warhammer_mode.random.random')
    @patch('warhammer_mode.create_visual_post')
    @patch('warhammer_mode.generic_transform')
    def test_warhammer_transform_chaos(self, mock_generic, mock_create, mock_random):
        mock_random.side_effect = [0.5, 0.4] # 1st image > 0.2, 2nd faction chaos < 0.57
        mock_generic.return_value = "CHAOS TEXT"

        result = warhammer_transform("123")

        self.assertEqual(result, ('text', "CHAOS TEXT"))
        mock_create.assert_not_called()
        mock_generic.assert_called_once()

if __name__ == '__main__':
    unittest.main()
