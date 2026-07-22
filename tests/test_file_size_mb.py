import unittest
from unittest.mock import patch

# Import the module to be tested
import main

class TestFileSizeMB(unittest.TestCase):
    @patch('os.path.getsize')
    @patch('os.fspath')
    def test_file_size_mb_success(self, mock_fspath, mock_getsize):
        # 1048576 bytes = 1.0 MB
        mock_getsize.return_value = 1048576
        mock_fspath.side_effect = lambda x: x

        result = main._file_size_mb('dummy/path.txt')
        self.assertEqual(result, 1.0)

        # 2621440 bytes = 2.5 MB
        mock_getsize.return_value = 2621440
        result = main._file_size_mb('dummy/path2.txt')
        self.assertEqual(result, 2.5)

    @patch('os.path.getsize')
    @patch('os.fspath')
    def test_file_size_mb_os_error(self, mock_fspath, mock_getsize):
        mock_getsize.side_effect = OSError("File not found")
        mock_fspath.side_effect = lambda x: x

        result = main._file_size_mb('missing/file.txt')
        self.assertEqual(result, 0.0)

if __name__ == '__main__':
    unittest.main()
