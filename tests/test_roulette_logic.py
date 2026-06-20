import unittest
import json
import os
import tempfile
from roulette_logic import load_roulette_data, get_random_event

class TestRouletteLogic(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file_path = os.path.join(self.temp_dir.name, "test_roulette.json")
        self.invalid_json_path = os.path.join(self.temp_dir.name, "invalid_roulette.json")

        # Create a valid JSON file
        valid_data = {
            "roulettes": [
                {
                    "name": "Roulette 1",
                    "events": [
                        {"text": "Event 1A"},
                        {"text": "Event 1B"}
                    ]
                },
                {
                    "name": "Roulette 2",
                    "events": [
                        {"text": "Event 2A"}
                    ]
                }
            ]
        }
        with open(self.test_file_path, "w", encoding="utf-8") as f:
            json.dump(valid_data, f)

        # Create an invalid JSON file
        with open(self.invalid_json_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_roulette_data_success(self):
        events = load_roulette_data(self.test_file_path)
        self.assertEqual(len(events), 3)

        # Check if source_roulette is added
        event_texts = [e["text"] for e in events]
        self.assertIn("Event 1A", event_texts)
        self.assertIn("Event 2A", event_texts)

        event_1a = next(e for e in events if e["text"] == "Event 1A")
        self.assertEqual(event_1a["source_roulette"], "Roulette 1")

        event_2a = next(e for e in events if e["text"] == "Event 2A")
        self.assertEqual(event_2a["source_roulette"], "Roulette 2")

    def test_load_roulette_data_file_not_found(self):
        events = load_roulette_data("non_existent_file.json")
        self.assertEqual(events, [])

    def test_load_roulette_data_invalid_json(self):
        events = load_roulette_data(self.invalid_json_path)
        self.assertEqual(events, [])

    def test_load_roulette_data_empty_roulettes(self):
        # Test with JSON having no roulettes
        empty_path = os.path.join(self.temp_dir.name, "empty_roulettes.json")
        with open(empty_path, "w", encoding="utf-8") as f:
            json.dump({"roulettes": []}, f)

        events = load_roulette_data(empty_path)
        self.assertEqual(events, [])

    def test_get_random_event(self):
        events = [{"text": "A"}, {"text": "B"}]
        event = get_random_event(events)
        self.assertIn(event, events)

    def test_get_random_event_empty(self):
        event = get_random_event([])
        self.assertIsNone(event)

if __name__ == "__main__":
    unittest.main()
