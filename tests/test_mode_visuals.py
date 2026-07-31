import unittest
from unittest.mock import patch, MagicMock
import os
import io
from PIL import Image, ImageFont

from mode_visuals import create_visual_post

class TestModeVisuals(unittest.TestCase):
    def setUp(self):
        # We need to mock os.path.exists and glob.glob
        self.patcher_exists = patch('mode_visuals.os.path.exists')
        self.mock_exists = self.patcher_exists.start()
        self.mock_exists.return_value = True

        self.patcher_glob = patch('mode_visuals.glob.glob')
        self.mock_glob = self.patcher_glob.start()
        self.mock_glob.return_value = ['fake_file.png']

        self.patcher_open = patch('mode_visuals.Image.open')
        self.mock_open = self.patcher_open.start()

        # We mock Image.open to return a real image that behaves like Image.open return value
        # But wait, we can just use a real image and not mock Image.open if we don't want to.
        # However, to avoid loading from disk 'fake_file.png', we will mock Image.open
        # and make it return a real newly created image.

        def open_mock(fp, *args, **kwargs):
            return Image.new('RGBA', (1024, 1024), color='red')

        self.mock_open.side_effect = open_mock

        self.patcher_font = patch('mode_visuals.ImageFont.truetype')
        self.mock_font = self.patcher_font.start()
        # Return a default font instead of failing
        self.mock_font.return_value = ImageFont.load_default()

        # Mock the draw object to avoid MagicMock vs int comparison
        self.patcher_draw = patch('mode_visuals.ImageDraw.Draw')
        self.mock_draw_cls = self.patcher_draw.start()

        self.mock_draw = MagicMock()
        # Set return value for textlength
        self.mock_draw.textlength.return_value = 50
        # Set return value for multiline_textbbox
        self.mock_draw.multiline_textbbox.return_value = (0, 0, 100, 50)
        self.mock_draw_cls.return_value = self.mock_draw

    def tearDown(self):
        patch.stopall()

    def test_create_visual_post_template_mode(self):
        # 'gopnik' is a template mode
        result = create_visual_post('gopnik', 'hello world', 'header text')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, bytes)
        # Check it looks like PNG signature
        self.assertTrue(result.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_create_visual_post_dynamic_mode_bottom(self):
        with patch('mode_visuals.random.choice') as mock_choice:
            mock_choice.side_effect = lambda seq: seq[0] if seq else None

            result = create_visual_post('polish', 'hello world', 'header text')
            self.assertIsNotNone(result)
            self.assertIsInstance(result, bytes)
            self.assertTrue(result.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_create_visual_post_dynamic_mode_split(self):
        def custom_choice(seq):
            if 'split' in seq: return 'split'
            if isinstance(seq, list) or isinstance(seq, tuple): return seq[-1]
            return seq

        with patch('mode_visuals.random.choice', side_effect=custom_choice):
            result = create_visual_post('ukrainian', 'hello world', 'header text')
            self.assertIsNotNone(result)
            self.assertTrue(result.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_create_visual_post_dynamic_mode_no_files(self):
        self.mock_glob.return_value = []
        result = create_visual_post('polish', 'hello world', 'header text')
        self.assertIsNone(result)

    def test_create_visual_post_unknown_mode(self):
        result = create_visual_post('unknown_mode', 'hello', None)
        self.assertIsNone(result)

    def test_create_visual_post_file_not_exists(self):
        self.mock_exists.return_value = False
        result = create_visual_post('gopnik', 'hello', None)
        self.assertIsNone(result)

    def test_create_visual_post_exception(self):
        self.mock_open.side_effect = Exception("File error")
        result = create_visual_post('gopnik', 'hello', None)
        self.assertIsNone(result)

    def test_create_visual_post_no_header(self):
        result = create_visual_post('warhammer', 'just text')
        self.assertIsNotNone(result)

if __name__ == '__main__':
    unittest.main()
