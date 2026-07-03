import unittest
import time
import asyncio

# Mock necessary globals in main before importing
import main

class MockQueue:
    def __init__(self, items):
        self._queue = items

class TestSummarizeLiveQueueAges(unittest.TestCase):

    def setUp(self):
        # Save original state
        self.original_message_queues = main.message_queues
        self.original_current_deliveries = main.current_deliveries

        main.message_queues = {}
        main.current_deliveries = {}

    def tearDown(self):
        # Restore original state
        main.message_queues = self.original_message_queues
        main.current_deliveries = self.original_current_deliveries

    def test_process_board_queue(self):
        now = time.time()
        items = [
            {"enqueued_at": now - 10, "post_num": 1},
            {"enqueued_at": now - 5, "post_num": 2},
            {"enqueued_at": now - 20, "post_num": 3},
            "not a dict",
            {"post_num": 4}, # no enqueued_at
        ]
        queue = MockQueue(items)

        ages, oldest_age, oldest_post = main._process_board_queue(queue, now)

        # We expect ages to be approximately [10.0, 5.0, 20.0]
        self.assertEqual(len(ages), 3)
        self.assertAlmostEqual(ages[0], 10.0, places=1)
        self.assertAlmostEqual(ages[1], 5.0, places=1)
        self.assertAlmostEqual(ages[2], 20.0, places=1)

        self.assertAlmostEqual(oldest_age, 20.0, places=1)
        self.assertEqual(oldest_post, 3)

    def test_process_in_flight_deliveries(self):
        now = time.time()
        main.current_deliveries = {
            "b": {
                "started_at": now - 5,
                "enqueued_at": now - 10,
                "other_data": "value"
            },
            "int": {
                "started_at": "invalid",
                "enqueued_at": now - 2,
            }
        }

        in_flight = main._process_in_flight_deliveries(now)

        self.assertEqual(len(in_flight), 2)

        self.assertAlmostEqual(in_flight["b"]["run_sec"], 5.0, places=1)
        self.assertAlmostEqual(in_flight["b"]["age_sec"], 10.0, places=1)
        self.assertEqual(in_flight["b"]["other_data"], "value")

        self.assertIsNone(in_flight["int"]["run_sec"])
        self.assertAlmostEqual(in_flight["int"]["age_sec"], 2.0, places=1)

    def test_summarize_live_queue_ages(self):
        now = time.time()
        main.message_queues = {
            "b": MockQueue([{"enqueued_at": now - 10, "post_num": 100}]),
            "int": MockQueue([])
        }
        main.current_deliveries = {
            "b": {"started_at": now - 2, "enqueued_at": now - 12}
        }

        queue_sizes = {"b": 1, "int": 0}

        summary = main._summarize_live_queue_ages(queue_sizes)

        # Check by_board
        self.assertIn("b", summary["by_board"])
        self.assertEqual(summary["by_board"]["b"]["size"], 1)
        self.assertAlmostEqual(summary["by_board"]["b"]["oldest_age_sec"], 10.0, places=1)
        self.assertEqual(summary["by_board"]["b"]["oldest_post"], 100)

        self.assertNotIn("int", summary["by_board"])

        # Check oldest
        self.assertEqual(len(summary["oldest"]), 1)
        self.assertEqual(summary["oldest"][0][0], "b") # board
        self.assertAlmostEqual(summary["oldest"][0][1], 10.0, places=1) # age
        self.assertEqual(summary["oldest"][0][2], 100) # post_num

        # Check in_flight
        self.assertIn("b", summary["in_flight"])
        self.assertAlmostEqual(summary["in_flight"]["b"]["run_sec"], 2.0, places=1)

if __name__ == '__main__':
    unittest.main()
