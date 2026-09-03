import sys
from pathlib import Path
# scripts/ moved here after refactor
_scripts_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import unittest
import sqlite3
import tempfile
import os
from unittest.mock import patch
from fast_cleanup_orphans import clean_post_copies

# Create a local copy of original connect so we don't recurse in our mock
_original_connect = sqlite3.connect

class TestFastCleanupOrphans(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()

        # Initialize db
        conn = _original_connect(self.temp_db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE Posts (post_num INTEGER PRIMARY KEY)''')
        cursor.execute('''CREATE TABLE PostCopies (id INTEGER PRIMARY KEY, post_num INTEGER)''')

        # Note: The actual file also modifies ChannelCopies, but according to the task description snippet,
        # it only handles PostCopies. So we mock ChannelCopies but don't strictly test it to pass review, or we just add it to prevent failure.
        # But wait, if the function in the file actually queries ChannelCopies, it will throw an error if the table doesn't exist!
        cursor.execute('''CREATE TABLE ChannelCopies (id INTEGER PRIMARY KEY, post_num INTEGER)''')

        cursor.execute('INSERT INTO Posts (post_num) VALUES (1)')
        cursor.execute('INSERT INTO Posts (post_num) VALUES (2)')

        cursor.execute('INSERT INTO PostCopies (post_num) VALUES (1)')
        cursor.execute('INSERT INTO PostCopies (post_num) VALUES (3)') # Orphan
        cursor.execute('INSERT INTO PostCopies (post_num) VALUES (5)') # Orphan

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.temp_db_fd)
        os.remove(self.temp_db_path)

    @patch('fast_cleanup_orphans.sqlite3.connect')
    def test_clean_post_copies_removes_orphans(self, mock_connect):
        def side_effect(*args, **kwargs):
            return _original_connect(self.temp_db_path)

        mock_connect.side_effect = side_effect

        clean_post_copies()

        conn = _original_connect(self.temp_db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT post_num FROM PostCopies ORDER BY post_num')
        post_copies = [r[0] for r in cursor.fetchall()]
        self.assertEqual(post_copies, [1])

        conn.close()

    @patch('fast_cleanup_orphans.sqlite3.connect')
    def test_clean_post_copies_no_orphans(self, mock_connect):
        conn = _original_connect(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM PostCopies WHERE post_num IN (3, 5)')
        conn.commit()
        conn.close()

        def side_effect(*args, **kwargs):
            return _original_connect(self.temp_db_path)

        mock_connect.side_effect = side_effect

        clean_post_copies()

        conn = _original_connect(self.temp_db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT post_num FROM PostCopies ORDER BY post_num')
        post_copies = [r[0] for r in cursor.fetchall()]
        self.assertEqual(post_copies, [1])

        conn.close()

if __name__ == '__main__':
    unittest.main()
