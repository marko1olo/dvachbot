import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Setup required env var
os.environ["SECRET_KEY"] = "test-secret-key-12345"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import types
def mock_module(name):
    mod = types.ModuleType(name)
    mod.__path__ = [] # makes it a package
    sys.modules[name] = mod
    return mod

# Mock heavy/missing dependencies to allow import
mocked_deps = [
    'site_tgach', 'site_tgach.mirror_worker', 'site_tgach.tagging_worker',
    'site_tgach.security', 'site_tgach.image_processing', 'site_tgach.catbox',
    'site_tgach.neuro_poster', 'site_tgach.rss', 'site_tgach.backup',
    'site_tgach.importer', 'site_tgach.neuro_scanner', 'site_tgach.admin_config',
    'site_tgach.voice_processing', 'warhammer_mode', 'japanese_translator',
    'bs4', 'slowapi', 'slowapi.util', 'slowapi.errors', 'async_lru', 'uvicorn',
    'fastapi_cache', 'fastapi_cache.backends', 'fastapi_cache.backends.inmemory',
    'fastapi_cache.decorator', 'geoip2', 'geoip2.database', 'aiogram',
    'aiogram.types', 'aiogram.exceptions', 'aiogram.enums', 'aiogram.client',
    'aiogram.client.session', 'aiogram.client.session.aiohttp', 'common.bot_pool',
    'aiogram.webhook', 'aiogram.webhook.aiohttp_server'
]

for dep in mocked_deps:
    mock_module(dep)

# Mock PIL for mode_visuals
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageDraw'] = MagicMock()
sys.modules['PIL.ImageFont'] = MagicMock()
sys.modules['PIL.ImageFilter'] = MagicMock()

from gopnik_mode import gopnik_transform

class TestGopnikTransform(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(gopnik_transform(""), ('text', ""))
        self.assertEqual(gopnik_transform(None), ('text', ""))

    @patch('gopnik_mode.create_visual_post')
    @patch('gopnik_mode.random.random')
    def test_image_generation(self, mock_random, mock_create_visual_post):
        # Force the condition `random.random() < 0.175` to be True
        mock_random.return_value = 0.1
        # Mock the image bytes returned
        mock_create_visual_post.return_value = b"fake_image_bytes"

        result = gopnik_transform("Some short text")

        self.assertEqual(result, ('image', b"fake_image_bytes"))
        mock_create_visual_post.assert_called_once()

    @patch('gopnik_mode.create_visual_post')
    @patch('gopnik_mode.random.random')
    def test_image_generation_fallback(self, mock_random, mock_create_visual_post):
        mock_random.return_value = 0.1
        mock_create_visual_post.return_value = None

        result = gopnik_transform("Some short text")
        self.assertEqual(result[0], 'text')
        self.assertIsInstance(result[1], str)

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    @patch('gopnik_mode.random.randint')
    def test_text_transformation(self, mock_randint, mock_choice, mock_random):
        mock_random.return_value = 0.99
        mock_choice.side_effect = lambda x: x[0] if isinstance(x, list) else x

        input_text = "Привет, друг! Как дела?"
        result_type, result_data = gopnik_transform(input_text)

        self.assertEqual(result_type, 'text')
        self.assertIn("Здарова", result_data) # capitalize preserved
        self.assertIn("кореш", result_data)

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    @patch('gopnik_mode.random.randint')
    def test_add_prefix_and_suffix(self, mock_randint, mock_choice, mock_random):
        # Make random always return 0.1 to trigger prefix, suffix, parasite words
        # but mock create_visual_post to return None to avoid image generation
        mock_random.return_value = 0.1

        def choice_side_effect(seq):
            if "Чисто " in seq: return "Слышь, епта, " # Prefix
            if ", бля" in seq: return ", нахуй" # Suffix
            if isinstance(seq, list): return seq[0]
            return seq
        mock_choice.side_effect = choice_side_effect

        # Need to patch create_visual_post just in case, but let's just make it return None
        with patch('gopnik_mode.create_visual_post', return_value=None):
            # Pass a string long enough so it triggers parasite word logic
            # "Текст" -> "Малява"
            result_type, result_data = gopnik_transform("Нормальный текст.")

        self.assertEqual(result_type, 'text')
        self.assertTrue(result_data.startswith("Слышь, епта, "), f"Actual data: {result_data}")
        self.assertTrue(result_data.endswith(", нахуй."), f"Actual data: {result_data}")

    @patch('gopnik_mode.random.random')
    @patch('gopnik_mode.random.choice')
    def test_wolf_quote(self, mock_choice, mock_random):
        # Trigger wolf quote (random < 0.25), but avoid image (random > 0.175)
        # We can just return 0.2 for random.
        mock_random.return_value = 0.2

        def choice_side_effect(seq):
            if "Братва" in seq: return "Братва" # Author
            if isinstance(seq, list): return seq[0]
            return seq
        mock_choice.side_effect = choice_side_effect

        input_text = "Это длинный текст из нескольких предложений. Который нужен для того чтобы триггернуть цитату волка."
        result_type, result_data = gopnik_transform(input_text)

        self.assertEqual(result_type, 'text')
        self.assertIn("☝️ <i>Брат, запомни: ", result_data)
        self.assertIn("АУФ 🐺", result_data)
        self.assertIn("(с) Братва</i>", result_data)

if __name__ == "__main__":
    unittest.main()
