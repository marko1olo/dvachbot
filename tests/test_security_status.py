import json
import tempfile
import unittest
from pathlib import Path
from security_status import load_json, add_blocker

class TestSecurityStatus(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_json_non_existent_file(self):
        """Test that load_json returns an empty dictionary for a non-existent file."""
        file_path = self.tmp_path / "non_existent.json"
        self.assertEqual(load_json(file_path), {})

    def test_load_json_valid_json(self):
        """Test that load_json correctly parses and returns valid JSON."""
        file_path = self.tmp_path / "valid.json"
        file_path.write_text('{"key": "value", "number": 42}', encoding="utf-8")
        result = load_json(file_path)
        self.assertEqual(result, {"key": "value", "number": 42})

    def test_load_json_invalid_json(self):
        """Test that load_json raises a JSONDecodeError for invalid JSON."""
        file_path = self.tmp_path / "invalid.json"
        file_path.write_text('{"key": "value",', encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            load_json(file_path)

    def test_add_blocker_positive_count(self):
        """Test that add_blocker appends a dictionary when count > 0."""
        blockers = []
        add_blocker(blockers, "test_code", 1, "test detail")
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0], {"code": "test_code", "count": 1, "detail": "test detail"})

    def test_add_blocker_zero_count(self):
        """Test that add_blocker does not append when count == 0."""
        blockers = []
        add_blocker(blockers, "test_code", 0, "test detail")
        self.assertEqual(len(blockers), 0)

    def test_add_blocker_negative_count(self):
        """Test that add_blocker does not append when count < 0."""
        blockers = []
        add_blocker(blockers, "test_code", -1, "test detail")
        self.assertEqual(len(blockers), 0)

if __name__ == "__main__":
    unittest.main()
