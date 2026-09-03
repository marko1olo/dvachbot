import sys
from pathlib import Path
# scripts/ moved here after refactor
_scripts_dir = str(Path(__file__).resolve().parents[1] / 'scripts')
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import os
import tempfile
import unittest
from unittest.mock import patch
import io
import contextlib

import prepare_sql

class TestPrepareSql(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_file = os.path.join(self.temp_dir.name, "backup.sql")
        self.output_file = os.path.join(self.temp_dir.name, "clean_import.sql")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_input_file(self):
        # Ensure input file does not exist
        if os.path.exists(self.input_file):
            os.remove(self.input_file)

        # Capture stdout
        f = io.StringIO()
        with patch('prepare_sql.INPUT_FILE', self.input_file), \
             patch('prepare_sql.OUTPUT_FILE', self.output_file), \
             contextlib.redirect_stdout(f):
            prepare_sql.fix_dump_final()

        output = f.getvalue()
        self.assertIn("Файл backup.sql не найден!", output)
        self.assertFalse(os.path.exists(self.output_file))

    def test_fix_dump_final_filters(self):
        input_content = """PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE users (id INTEGER);
INSERT INTO sqlite_stat VALUES (1, 2);
UPDATE sqlite_sequence SET seq=1;
CREATE TRIGGER trigger_name
  BEFORE INSERT ON table_name
  FOR EACH ROW
BEGIN
  SELECT 1;
END;
CREATE VIRTUAL TABLE PostsFTS USING fts5(content);
INSERT INTO PostsFTS VALUES ('test');
INSERT INTO users VALUES (1, 'test');
SELECT * FROM sqlite_master;
COMMIT;
"""
        with open(self.input_file, 'w', encoding='utf-8') as f:
            f.write(input_content)

        with patch('prepare_sql.INPUT_FILE', self.input_file), \
             patch('prepare_sql.OUTPUT_FILE', self.output_file), \
             contextlib.redirect_stdout(io.StringIO()):
            prepare_sql.fix_dump_final()

        self.assertTrue(os.path.exists(self.output_file))

        with open(self.output_file, 'r', encoding='utf-8') as f:
            output_content = f.read()

        # Check PRAGMAs and Transaction setup
        self.assertIn("PRAGMA foreign_keys = OFF;", output_content)
        self.assertIn("PRAGMA synchronous = OFF;", output_content)
        self.assertIn("PRAGMA journal_mode = WAL;", output_content)
        self.assertIn("BEGIN TRANSACTION;", output_content)

        # Check FTS stub
        self.assertIn("CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(content, content='Posts', content_rowid='post_num');", output_content)

        # Check final COMMIT
        self.assertTrue(output_content.endswith("\nCOMMIT;"))

        # Check kept statements
        self.assertIn("CREATE TABLE users (id INTEGER);", output_content)
        self.assertIn("INSERT INTO users VALUES (1, 'test');", output_content)

        # Check filtered statements
        self.assertNotIn("sqlite_stat", output_content)
        self.assertNotIn("sqlite_sequence", output_content)
        self.assertNotIn("CREATE TRIGGER", output_content)
        self.assertNotIn("trigger_name", output_content)
        self.assertNotIn("END;", output_content)
        self.assertNotIn("SELECT * FROM sqlite_master", output_content)

if __name__ == '__main__':
    unittest.main()
