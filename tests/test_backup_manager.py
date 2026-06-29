import unittest
from unittest.mock import patch, MagicMock, call, mock_open
import os
import sqlite3
import asyncio

# Setup env variables before importing main to prevent pyrogram issues
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"
os.environ["ADMIN_CHAT_ID"] = "123456789"
os.environ["API_ID"] = "123"
os.environ["API_HASH"] = "test_hash"
os.environ["BASE_URL"] = "http://test.com"

# Setup asyncio loop for possible Pyrogram imports in conftest/module loading
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from backup_manager import create_gzipped_dump


class TestBackupManager(unittest.TestCase):

    @patch("backup_manager.os.path.exists")
    def test_missing_database_file(self, mock_exists):
        """Test that missing database file returns None."""
        mock_exists.return_value = False

        result = create_gzipped_dump("missing.db", "out_dir")

        self.assertIsNone(result)
        mock_exists.assert_called_once_with("missing.db")

    @patch("backup_manager.os.remove")
    @patch("backup_manager.glob.glob")
    @patch("backup_manager.gzip.open")
    @patch("backup_manager.sqlite3.connect")
    @patch("backup_manager.datetime")
    @patch("backup_manager.os.makedirs")
    @patch("backup_manager.os.path.exists")
    def test_successful_dump_without_rotation(
        self,
        mock_exists,
        mock_makedirs,
        mock_datetime,
        mock_connect,
        mock_gzip_open,
        mock_glob,
        mock_remove,
    ):
        """Test successful dump creation when there are <= 2 existing backups (no rotation needed)."""
        mock_exists.return_value = True

        # Mock datetime
        mock_datetime.now.return_value.strftime.return_value = "2023-01-01_12-00"

        # Mock sqlite connect
        mock_con = MagicMock()
        mock_con.iterdump.return_value = ["INSERT INTO test VALUES(1);", "COMMIT;"]
        mock_connect.return_value.__enter__.return_value = mock_con

        # Mock glob to return 2 files
        mock_glob.return_value = ["backup1.sql.gz", "backup2.sql.gz"]

        result = create_gzipped_dump("test.db", "out_dir")

        expected_path = os.path.join("out_dir", "db_backup_2023-01-01_12-00.sql.gz")
        self.assertEqual(result, expected_path)

        mock_makedirs.assert_called_once_with("out_dir", exist_ok=True)
        mock_connect.assert_called_once_with("test.db")
        mock_gzip_open.assert_called_once_with(expected_path, "wt", encoding="utf-8")

        # Verify writing to gzip
        handle = mock_gzip_open.return_value.__enter__.return_value
        handle.write.assert_has_calls(
            [call("INSERT INTO test VALUES(1);\n"), call("COMMIT;\n")]
        )

        # Verify no removal occurred
        mock_remove.assert_not_called()

    @patch("backup_manager.os.remove")
    @patch("backup_manager.os.path.getmtime")
    @patch("backup_manager.glob.glob")
    @patch("backup_manager.gzip.open")
    @patch("backup_manager.sqlite3.connect")
    @patch("backup_manager.datetime")
    @patch("backup_manager.os.makedirs")
    @patch("backup_manager.os.path.exists")
    def test_successful_dump_with_rotation(
        self,
        mock_exists,
        mock_makedirs,
        mock_datetime,
        mock_connect,
        mock_gzip_open,
        mock_glob,
        mock_getmtime,
        mock_remove,
    ):
        """Test dump creation with rotation (> 2 backups existing, verifying oldest is removed based on getmtime)."""
        mock_exists.return_value = True
        mock_datetime.now.return_value.strftime.return_value = "2023-01-01_12-00"

        # Mock sqlite connect
        mock_con = MagicMock()
        mock_con.iterdump.return_value = []
        mock_connect.return_value.__enter__.return_value = mock_con

        # Mock 4 existing backups
        mock_glob.return_value = [
            "backup1.sql.gz",
            "backup2.sql.gz",
            "backup3.sql.gz",
            "backup4.sql.gz",
        ]

        # Mock getmtime to return different times so they sort predictability
        # backup2 is oldest (10), backup4 is newest (40)
        mtimes = {
            "backup1.sql.gz": 30,
            "backup2.sql.gz": 10,
            "backup3.sql.gz": 20,
            "backup4.sql.gz": 40,
        }
        mock_getmtime.side_effect = lambda path: mtimes[path]

        result = create_gzipped_dump("test.db", "out_dir")

        expected_path = os.path.join("out_dir", "db_backup_2023-01-01_12-00.sql.gz")
        self.assertEqual(result, expected_path)

        # The list sorted by mtime will be: backup2(10), backup3(20), backup1(30), backup4(40)
        # Since max_backups=2, the oldest 2 should be deleted: backup2 and backup3
        mock_remove.assert_has_calls([call("backup2.sql.gz"), call("backup3.sql.gz")])
        self.assertEqual(mock_remove.call_count, 2)

    @patch("backup_manager.os.remove")
    @patch("backup_manager.sqlite3.connect")
    @patch("backup_manager.datetime")
    @patch("backup_manager.os.makedirs")
    @patch("backup_manager.os.path.exists")
    def test_exception_during_dump_creation(
        self, mock_exists, mock_makedirs, mock_datetime, mock_connect, mock_remove
    ):
        """Test exception handling during dump creation, verifying it returns None and cleans up the partial dump."""

        # mock_exists.side_effect = [True, True] # True for db, True for cleanup check
        def exists_side_effect(path):
            return True

        mock_exists.side_effect = exists_side_effect

        mock_datetime.now.return_value.strftime.return_value = "2023-01-01_12-00"

        # Simulate an error during dump creation
        mock_connect.side_effect = sqlite3.Error("Test DB Error")

        result = create_gzipped_dump("test.db", "out_dir")

        self.assertIsNone(result)

        # Should have tried to clean up the partial dump file
        expected_path = os.path.join("out_dir", "db_backup_2023-01-01_12-00.sql.gz")
        mock_remove.assert_called_once_with(expected_path)

    @patch("backup_manager.os.remove")
    @patch("backup_manager.os.path.getmtime")
    @patch("backup_manager.glob.glob")
    @patch("backup_manager.gzip.open")
    @patch("backup_manager.sqlite3.connect")
    @patch("backup_manager.datetime")
    @patch("backup_manager.os.makedirs")
    @patch("backup_manager.os.path.exists")
    def test_exception_during_old_backup_deletion(
        self,
        mock_exists,
        mock_makedirs,
        mock_datetime,
        mock_connect,
        mock_gzip_open,
        mock_glob,
        mock_getmtime,
        mock_remove,
    ):
        """Test exception handling during old backup deletion (e.g. os.remove throws OSError), verifying it continues execution."""
        mock_exists.return_value = True
        mock_datetime.now.return_value.strftime.return_value = "2023-01-01_12-00"

        # Mock sqlite connect
        mock_con = MagicMock()
        mock_con.iterdump.return_value = []
        mock_connect.return_value.__enter__.return_value = mock_con

        # Mock 3 existing backups to trigger rotation of 1
        mock_glob.return_value = ["backup1.sql.gz", "backup2.sql.gz", "backup3.sql.gz"]
        mock_getmtime.side_effect = (
            lambda path: 10
        )  # time doesn't matter, just needs sorting

        # Simulate OSError during deletion of old backup
        mock_remove.side_effect = OSError("Permission denied")

        result = create_gzipped_dump("test.db", "out_dir")

        expected_path = os.path.join("out_dir", "db_backup_2023-01-01_12-00.sql.gz")

        # Result should still be the path (not None), since dump was successful
        self.assertEqual(result, expected_path)

        # Called once to attempt removal but raised exception, which should be caught
        self.assertEqual(mock_remove.call_count, 1)


if __name__ == "__main__":
    unittest.main()
