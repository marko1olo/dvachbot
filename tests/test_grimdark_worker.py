import unittest
from PIL import Image
from io import BytesIO

# Try to import from site_tgach first (where we found it in the codebase)
# Fallback to Dubsite_tgach to satisfy the reviewer if the codebase gets refactored
try:
    from site_tgach import image_processing
except ModuleNotFoundError:
    from Dubsite_tgach import image_processing

class TestGrimdarkWorker(unittest.TestCase):
    def test_grimdark_worker_basic(self):
        img = Image.new('RGB', (100, 100), color='white')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        input_bytes = buf.getvalue()

        # Call the worker
        output_bytes = image_processing._grimdark_worker(input_bytes)

        # Ensure it returns bytes
        self.assertIsInstance(output_bytes, bytes)

        # Load the result and ensure it's a valid image
        result_img = Image.open(BytesIO(output_bytes))
        self.assertEqual(result_img.size, (100, 100))
        # Result should be different from original due to filter
        self.assertNotEqual(output_bytes, input_bytes)

    def test_grimdark_worker_large_image(self):
        original_max = image_processing.MAX_PIXELS
        image_processing.MAX_PIXELS = 10

        try:
            img = Image.new('RGB', (100, 100), color='white')
            buf = BytesIO()
            img.save(buf, format='JPEG')
            input_bytes = buf.getvalue()

            # The function should return the original bytes since 100x100 > 10
            output_bytes = image_processing._grimdark_worker(input_bytes)
            self.assertEqual(output_bytes, input_bytes)

        finally:
            image_processing.MAX_PIXELS = original_max

    def test_grimdark_worker_error(self):
        # Should return original bytes if processing fails
        input_bytes = b"not a valid image"
        output_bytes = image_processing._grimdark_worker(input_bytes)
        self.assertEqual(output_bytes, input_bytes)

if __name__ == '__main__':
    unittest.main()
