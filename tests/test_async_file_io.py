import unittest
from unittest.mock import patch
import io
from common.async_file_io import copy_fileobj_to_temp

class TestAsyncFileIo(unittest.TestCase):
    @patch('common.async_file_io.shutil.copyfileobj')
    @patch('common.async_file_io.remove_files_best_effort')
    def test_copy_fileobj_to_temp_error(self, mock_remove, mock_copy):
        mock_copy.side_effect = Exception("Test Exception")
        source = io.BytesIO(b"test")

        with self.assertRaises(Exception) as context:
            copy_fileobj_to_temp(source)

        self.assertEqual(str(context.exception), "Test Exception")
        mock_remove.assert_called_once()

        args, kwargs = mock_remove.call_args
        self.assertIsInstance(args[0], tuple)
        self.assertEqual(len(args[0]), 1)
        self.assertTrue(isinstance(args[0][0], str))
        self.assertTrue(args[0][0].endswith(".tmp"))

if __name__ == '__main__':
    unittest.main()
