import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mode_visuals import create_visual_post, FontFitConfig

class TestModeVisuals(unittest.TestCase):
    @patch('mode_visuals._find_best_font_size')
    @patch('mode_visuals._draw_text_with_shadow')
    @patch('mode_visuals.Image')
    @patch('mode_visuals.ImageDraw')
    @patch('mode_visuals.os.path.exists')
    @patch('mode_visuals.random.choice')
    def test_create_visual_post_template_mode(self, mock_choice, mock_exists, mock_draw, mock_image, mock_draw_shadow, mock_find_font):
        mock_exists.return_value = True
        mock_choice.return_value = {
            'filename': 'gopnik1.png',
            'text_area': (100, 100, 400, 400),
            'font_path': 'fonts/Impact.ttf',
            'max_font_size': 45,
            'text_color': (255, 255, 255),
            'text_align': 'center'
        }

        mock_img = MagicMock()
        mock_img_rgb = MagicMock()
        mock_img.convert.side_effect = [mock_img, mock_img_rgb] # One for RGBA, one for RGB
        mock_img.size = (500, 500)
        mock_image.open.return_value = mock_img

        mock_draw_instance = MagicMock()
        mock_draw.Draw.return_value = mock_draw_instance

        mock_find_font.return_value = (MagicMock(), "Test text")

        result = create_visual_post('gopnik', 'Test text')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, bytes)
        mock_image.open.assert_called_once_with('templates/gopnik1.png')
        mock_img_rgb.save.assert_called_once()
        mock_draw_instance.multiline_text.assert_called_once()

    @patch('mode_visuals._find_best_font_size')
    @patch('mode_visuals._draw_text_with_shadow')
    @patch('mode_visuals.Image')
    @patch('mode_visuals.ImageDraw')
    @patch('mode_visuals.os.path.exists')
    @patch('mode_visuals.glob.glob')
    @patch('mode_visuals.random.choice')
    def test_create_visual_post_dynamic_mode_bottom(self, mock_choice, mock_glob, mock_exists, mock_draw, mock_image, mock_draw_shadow, mock_find_font):
        mock_exists.return_value = True
        mock_glob.return_value = ['templates/polish/file1.png']
        # Mocks random choice for list of files, then for layout, then for font
        mock_choice.side_effect = ['templates/polish/file1.png', 'font1.ttf']

        mock_img = MagicMock()
        mock_img_rgb = MagicMock()
        # In DYNAMIC_MODES: convert("RGBA"), then alpha_composite returns a new img.
        # But our mock just returns mock_img. Then at the end it does convert("RGB").
        mock_img.convert.side_effect = [mock_img, mock_img_rgb]
        mock_img.size = (1024, 1024)
        mock_image.open.return_value = mock_img

        mock_overlay = MagicMock()
        mock_image.new.return_value = mock_overlay
        mock_image.alpha_composite.return_value = mock_img

        mock_draw_instance = MagicMock()
        mock_draw.Draw.return_value = mock_draw_instance

        mock_find_font.return_value = (MagicMock(), "Test text")

        result = create_visual_post('polish', 'Test text')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, bytes)
        mock_image.open.assert_called_once_with('templates/polish/file1.png')
        mock_img_rgb.save.assert_called_once()
        mock_draw_shadow.assert_called_once()

    @patch('mode_visuals._find_best_font_size')
    @patch('mode_visuals._draw_text_with_shadow')
    @patch('mode_visuals.Image')
    @patch('mode_visuals.ImageDraw')
    @patch('mode_visuals.os.path.exists')
    @patch('mode_visuals.glob.glob')
    @patch('mode_visuals.random.choice')
    def test_create_visual_post_dynamic_mode_split_with_header(self, mock_choice, mock_glob, mock_exists, mock_draw, mock_image, mock_draw_shadow, mock_find_font):
        mock_exists.return_value = True
        mock_glob.return_value = ['templates/polish/file1.png']
        # Mocks random choice for list of files, then for layout ('split'), then for font
        mock_choice.side_effect = ['templates/polish/file1.png', 'split', 'font1.ttf']

        mock_img = MagicMock()
        mock_img_rgb = MagicMock()
        mock_img.convert.side_effect = [mock_img, mock_img_rgb]
        mock_img.size = (1024, 1024)
        mock_image.open.return_value = mock_img

        mock_overlay = MagicMock()
        mock_image.new.return_value = mock_overlay
        mock_image.alpha_composite.return_value = mock_img

        mock_draw_instance = MagicMock()
        mock_draw.Draw.return_value = mock_draw_instance

        mock_find_font.return_value = (MagicMock(), "Test text")

        result = create_visual_post('polish', 'Test text', header='Test header')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, bytes)
        mock_image.open.assert_called_once_with('templates/polish/file1.png')
        mock_img_rgb.save.assert_called_once()
        self.assertEqual(mock_draw_shadow.call_count, 2)

    @patch('mode_visuals.os.path.exists')
    @patch('mode_visuals.random.choice')
    def test_create_visual_post_file_not_exists(self, mock_choice, mock_exists):
        mock_exists.return_value = False
        mock_choice.return_value = {
            'filename': 'gopnik1.png',
            'text_area': (100, 100, 400, 400),
            'font_path': 'fonts/Impact.ttf',
            'max_font_size': 45,
            'text_color': (255, 255, 255),
            'text_align': 'center'
        }

        result = create_visual_post('gopnik', 'Test text')
        self.assertIsNone(result)

    @patch('mode_visuals.glob.glob')
    def test_create_visual_post_dynamic_mode_no_files(self, mock_glob):
        mock_glob.return_value = []
        result = create_visual_post('polish', 'Test text')
        self.assertIsNone(result)

    def test_create_visual_post_unknown_mode(self):
        result = create_visual_post('unknown', 'Test text')
        self.assertIsNone(result)

    @patch('mode_visuals.os.path.exists')
    @patch('mode_visuals.random.choice')
    def test_create_visual_post_exception(self, mock_choice, mock_exists):
        # Trigger an exception intentionally
        mock_exists.side_effect = Exception("Test exception")
        mock_choice.return_value = {
            'filename': 'gopnik1.png',
            'text_area': (100, 100, 400, 400),
            'font_path': 'fonts/Impact.ttf',
            'max_font_size': 45,
            'text_color': (255, 255, 255),
            'text_align': 'center'
        }

        result = create_visual_post('gopnik', 'Test text')
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
