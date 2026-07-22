import unittest
from unittest.mock import patch, MagicMock
import sys

# Mock mode_visuals before importing polish_mode to avoid PIL dependency issues
sys.modules['mode_visuals'] = MagicMock()
import polish_mode

class TestPolishTransform(unittest.TestCase):
    def setUp(self):
        self.random_patcher = patch('polish_mode.random.random')
        self.mock_random = self.random_patcher.start()
        # Always return 0.9 for random.random() to avoid visual post generation
        # (which triggers when < 0.25) and other random injection (kurwa etc).
        self.mock_random.return_value = 0.9

    def tearDown(self):
        self.random_patcher.stop()

    def test_empty_text(self):
        res_type, res_val = polish_mode.polish_transform("")
        self.assertEqual(res_type, "text")
        self.assertEqual(res_val, "")

    def test_short_message_no_kurwa(self):
        # random.random() is 0.9, > 0.4, so no ", kurwa" appended
        res_type, res_val = polish_mode.polish_transform("привет")
        self.assertEqual(res_type, "text")
        # polish_mode should polonize "привет" (stage word replacement)
        # Assuming the dictionary translates it to 'siema'
        self.assertEqual(res_val, "siema")

    def test_short_message_with_kurwa(self):
        # force random.random() to be < 0.4
        self.mock_random.return_value = 0.1
        # It's < 0.25 so it might trigger visual post.
        # But create_visual_post mock returns whatever.
        # Let's mock create_visual_post to return None to fall back to text.
        with patch('polish_mode.create_visual_post', return_value=None):
            res_type, res_val = polish_mode.polish_transform("привет")
            self.assertEqual(res_type, "text")
            self.assertEqual(res_val, "siema, kurwa")

    def test_visual_post_short_message(self):
        self.mock_random.return_value = 0.1
        with patch('polish_mode.create_visual_post', return_value=b'image_data'):
            res_type, res_val = polish_mode.polish_transform("привет")
            self.assertEqual(res_type, "image")
            self.assertEqual(res_val, b'image_data')

    def test_visual_post_long_message(self):
        self.mock_random.return_value = 0.1
        # Text needs to be > 2 words for the long pipeline, but < 180 chars for visual post
        text = "один два три четыре пять"
        with patch('polish_mode.create_visual_post', return_value=b'image_data'):
            res_type, res_val = polish_mode.polish_transform(text)
            self.assertEqual(res_type, "image")
            self.assertEqual(res_val, b'image_data')

    def test_long_message_text(self):
        # Long text ( > 2 words), no visual post (random > 0.25)
        text = "это очень длинное предложение для теста"
        # Mocking all internal stages is too brittle, so let's just assert
        # that it goes through the pipeline and returns a text tuple.
        res_type, res_val = polish_mode.polish_transform(text)
        self.assertEqual(res_type, "text")
        self.assertIsInstance(res_val, str)
        # Verify it changed
        self.assertNotEqual(res_val, text)

if __name__ == '__main__':
    unittest.main()
