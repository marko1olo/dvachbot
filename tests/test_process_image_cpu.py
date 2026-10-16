import unittest
from unittest.mock import patch
import io
import hashlib
from PIL import Image

# Import the target function
try:
    from Dubsite_tgach.tagging_worker import process_image_cpu
except ModuleNotFoundError:
    process_image_cpu = None

class TestProcessImageCpu(unittest.TestCase):
    def setUp(self):
        if process_image_cpu is None:
            self.skipTest("Module Dubsite_tgach.tagging_worker not found.")

    def test_empty_bytes(self):
        result, error = process_image_cpu(b"")
        self.assertIsNone(result)
        self.assertEqual(error, "Empty bytes")

        result, error = process_image_cpu(None)
        self.assertIsNone(result)
        self.assertEqual(error, "Empty bytes")

    def test_valid_small_image(self):
        # Create a 10x10 dummy RGB image
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        image_bytes = img_buffer.getvalue()

        result, error = process_image_cpu(image_bytes)

        self.assertIsNone(error)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)

        sha, phash, b_hash, resized_bytes = result

        # Verify SHA
        self.assertEqual(sha, hashlib.sha256(image_bytes).hexdigest())

        # Verify pHash is calculated (it should be a string)
        self.assertIsInstance(phash, str)
        self.assertTrue(len(phash) > 0)

        # Verify b_hash is calculated
        self.assertIsInstance(b_hash, str)
        self.assertTrue(len(b_hash) > 0)

        # Verify resized_bytes is a valid image bytes
        resized_img = Image.open(io.BytesIO(resized_bytes))
        self.assertEqual(resized_img.format, "JPEG")
        self.assertEqual(resized_img.size, (10, 10))

    def test_valid_large_image(self):
        # Create a 2000x1500 dummy RGB image (requires resizing, MAX_SIZE = 1024)
        img = Image.new("RGB", (2000, 1500), color=(0, 255, 0))
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        image_bytes = img_buffer.getvalue()

        result, error = process_image_cpu(image_bytes)

        self.assertIsNone(error)
        self.assertIsNotNone(result)

        sha, phash, b_hash, resized_bytes = result

        # Verify resized_bytes is a valid image bytes
        resized_img = Image.open(io.BytesIO(resized_bytes))
        self.assertEqual(resized_img.format, "JPEG")

        # Resizing should maintain aspect ratio, with the largest side being 1024
        # Original: 2000x1500 (aspect ratio 4:3)
        # Resized: 1024x768
        self.assertEqual(resized_img.size, (1024, 768))

    def test_invalid_image_bytes(self):
        invalid_bytes = b"This is not a valid image file."
        result, error = process_image_cpu(invalid_bytes)

        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertTrue(error.startswith("PIL Error:"))

    @patch("Dubsite_tgach.tagging_worker.Image.open")
    def test_decompression_bomb_error(self, mock_image_open):
        mock_image_open.side_effect = Image.DecompressionBombError()

        # Valid SHA is calculated before opening image
        dummy_bytes = b"dummy bytes for hash"
        result, error = process_image_cpu(dummy_bytes)

        self.assertIsNone(result)
        self.assertEqual(error, "Decompression Bomb Detected")

    @patch("Dubsite_tgach.tagging_worker.hashlib.sha256")
    def test_unknown_cpu_error(self, mock_sha256):
        mock_sha256.side_effect = Exception("Unknown CPU hashing error")

        dummy_bytes = b"dummy bytes"
        result, error = process_image_cpu(dummy_bytes)

        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertTrue(error.startswith("CPU Error: Unknown CPU hashing error"))

if __name__ == "__main__":
    unittest.main()
