import unittest
import os
import tempfile
import asyncio

# Setup env variables before importing
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ["ADMIN_CHAT_ID"] = "123456789"
os.environ["API_ID"] = "123"
os.environ["API_HASH"] = "test_hash"
os.environ["BASE_URL"] = "http://test.com"

from site_tgach.backup import split_file_by_size

class TestBackupSplit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file_path = os.path.join(self.temp_dir.name, "test_file.txt")
        self.file_content = b"A" * 1024 * 1024 # 1 MB of data
        with open(self.test_file_path, "wb") as f:
            f.write(self.file_content)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_split_file_no_split(self):
        # File is exactly the chunk size, shouldn't split
        chunk_size = 1024 * 1024
        result = split_file_by_size(self.test_file_path, chunk_size)
        self.assertEqual(result, [self.test_file_path])
        self.assertTrue(os.path.exists(self.test_file_path))

        # File is smaller than chunk size, shouldn't split
        chunk_size = 2 * 1024 * 1024
        result = split_file_by_size(self.test_file_path, chunk_size)
        self.assertEqual(result, [self.test_file_path])
        self.assertTrue(os.path.exists(self.test_file_path))

    def test_split_file_with_split(self):
        # Split into 4 chunks (3 full, 1 partial)
        chunk_size = 300 * 1024
        result = split_file_by_size(self.test_file_path, chunk_size)

        self.assertEqual(len(result), 4)
        for i, part in enumerate(result):
            self.assertEqual(part, f"{self.test_file_path}.{i+1:03d}")
            self.assertTrue(os.path.exists(part))

        # Reconstruct the file
        reconstructed = b""
        for part in result:
            with open(part, "rb") as f:
                reconstructed += f.read()

        self.assertEqual(reconstructed, self.file_content)
        self.assertFalse(os.path.exists(self.test_file_path))

    def test_split_file_exact_multiple(self):
        # Split into exactly 4 chunks
        chunk_size = 256 * 1024
        result = split_file_by_size(self.test_file_path, chunk_size)

        self.assertEqual(len(result), 4)
        for i, part in enumerate(result):
            self.assertEqual(part, f"{self.test_file_path}.{i+1:03d}")
            self.assertTrue(os.path.exists(part))

        # Reconstruct the file
        reconstructed = b""
        for part in result:
            with open(part, "rb") as f:
                reconstructed += f.read()

        self.assertEqual(reconstructed, self.file_content)
        self.assertFalse(os.path.exists(self.test_file_path))

if __name__ == "__main__":
    unittest.main()
