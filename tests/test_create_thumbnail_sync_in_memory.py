import unittest
import asyncio
from unittest.mock import patch
from io import BytesIO
from PIL import Image

# Initialize event loop for pyrogram before importing site_tgach modules
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

try:
    from Dubsite_tgach.image_processing import _create_thumbnail_sync_in_memory
    TARGET_MODULE = 'Dubsite_tgach.image_processing'
except ModuleNotFoundError:
    from site_tgach.image_processing import _create_thumbnail_sync_in_memory
    TARGET_MODULE = 'site_tgach.image_processing'

class TestCreateThumbnailSyncInMemory(unittest.TestCase):

    def setUp(self):
        # Create a small valid image in memory
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        self.valid_image_bytes = buffer.getvalue()

    def test_valid_image(self):
        """Test with a valid small image."""
        result = _create_thumbnail_sync_in_memory(self.valid_image_bytes)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, bytes)

        # Verify it's actually a valid JPEG image
        with Image.open(BytesIO(result)) as thumb:
            self.assertEqual(thumb.format, 'JPEG')

    def test_rgba_image_conversion(self):
        """Test with an RGBA image to ensure it converts to RGB."""
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 255))
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        rgba_image_bytes = buffer.getvalue()

        result = _create_thumbnail_sync_in_memory(rgba_image_bytes)
        self.assertIsNotNone(result)

        with Image.open(BytesIO(result)) as thumb:
            self.assertEqual(thumb.format, 'JPEG')
            self.assertEqual(thumb.mode, 'RGB')

    def test_invalid_image(self):
        """Test with invalid image bytes."""
        invalid_bytes = b"This is not an image"
        result = _create_thumbnail_sync_in_memory(invalid_bytes)
        self.assertIsNone(result)

    def test_decompression_bomb(self):
        """Test handling of DecompressionBombError."""
        with patch(f'{TARGET_MODULE}.Image.open') as mock_open:
            mock_open.side_effect = Image.DecompressionBombError("Bomb!")
            result = _create_thumbnail_sync_in_memory(self.valid_image_bytes)
            self.assertIsNone(result)

    def test_generic_exception(self):
        """Test handling of generic exception."""
        with patch(f'{TARGET_MODULE}.Image.open') as mock_open:
            mock_open.side_effect = Exception("Generic error!")
            result = _create_thumbnail_sync_in_memory(self.valid_image_bytes)
            self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
