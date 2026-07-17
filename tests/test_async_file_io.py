import asyncio
import io
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from common.async_file_io import (
    copy_fileobj_to_temp,
    copy_fileobj_to_temp_async,
    open_binary_writer,
    read_file_bytes,
    read_file_bytes_async,
    read_json_file,
    read_json_file_async,
    remove_files_best_effort,
    remove_files_best_effort_async,
    write_async_iter_bytes_to_file,
)


class TestAsyncFileIO(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.test_dir, "test_file.txt")
        with open(self.test_file_path, "wb") as f:
            f.write(b"test data")

        self.test_json_path = os.path.join(self.test_dir, "test_file.json")
        with open(self.test_json_path, "w", encoding="utf-8") as f:
            json.dump({"key": "value"}, f)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_copy_fileobj_to_temp_success(self):
        source = io.BytesIO(b"source data")
        path = copy_fileobj_to_temp(source, suffix=".test")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".test"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"source data")
        os.remove(path)

    @patch("common.async_file_io.remove_files_best_effort")
    @patch("common.async_file_io.shutil.copyfileobj")
    def test_copy_fileobj_to_temp_exception(self, mock_copyfileobj, mock_remove_files):
        mock_copyfileobj.side_effect = Exception("Test exception")
        source = io.BytesIO(b"source data")
        with self.assertRaisesRegex(Exception, "Test exception"):
            copy_fileobj_to_temp(source)
        self.assertTrue(mock_remove_files.called)

    async def test_copy_fileobj_to_temp_async_success(self):
        source = io.BytesIO(b"source data")
        path = await copy_fileobj_to_temp_async(source, suffix=".test")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".test"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"source data")
        os.remove(path)

    def test_read_file_bytes(self):
        data = read_file_bytes(self.test_file_path)
        self.assertEqual(data, b"test data")

    async def test_read_file_bytes_async(self):
        data = await read_file_bytes_async(self.test_file_path)
        self.assertEqual(data, b"test data")

    def test_read_json_file(self):
        data = read_json_file(self.test_json_path)
        self.assertEqual(data, {"key": "value"})

    async def test_read_json_file_async(self):
        data = await read_json_file_async(self.test_json_path)
        self.assertEqual(data, {"key": "value"})

    def test_open_binary_writer(self):
        path = os.path.join(self.test_dir, "writer.bin")
        writer = open_binary_writer(path)
        self.assertTrue(hasattr(writer, "write"))
        writer.write(b"data")
        writer.close()
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"data")

    async def test_write_async_iter_bytes_to_file(self):
        async def mock_async_iter():
            yield b"chunk1 "
            yield b""  # Empty chunk should be skipped
            yield b"chunk2"

        path = os.path.join(self.test_dir, "async_writer.bin")
        await write_async_iter_bytes_to_file(mock_async_iter(), path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"chunk1 chunk2")

    def test_remove_files_best_effort(self):
        path1 = os.path.join(self.test_dir, "to_remove1.txt")
        path2 = os.path.join(self.test_dir, "to_remove2.txt")
        with open(path1, "wb") as f:
            f.write(b"")
        with open(path2, "wb") as f:
            f.write(b"")

        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))

        # Include an empty string and a non-existent file to test robustness
        remove_files_best_effort([path1, "", "non_existent_file.txt", path2])

        self.assertFalse(os.path.exists(path1))
        self.assertFalse(os.path.exists(path2))

    async def test_remove_files_best_effort_async(self):
        path1 = os.path.join(self.test_dir, "to_remove_async1.txt")
        path2 = os.path.join(self.test_dir, "to_remove_async2.txt")
        with open(path1, "wb") as f:
            f.write(b"")
        with open(path2, "wb") as f:
            f.write(b"")

        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))

        await remove_files_best_effort_async([path1, "", "non_existent_file.txt", path2])

        self.assertFalse(os.path.exists(path1))
        self.assertFalse(os.path.exists(path2))

if __name__ == "__main__":
    unittest.main()
