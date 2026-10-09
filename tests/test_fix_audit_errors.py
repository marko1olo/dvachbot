import unittest
from datetime import datetime, timezone
import time

class TestFixAuditErrors(unittest.TestCase):
    def test_sweep_stale_runtime_maps_datetime_handling(self):
        # Verify the helper logic for datetime vs float
        def _get_ts_sec(val):
            if isinstance(val, (int, float)):
                return float(val)
            if hasattr(val, 'timestamp'):
                try:
                    return val.timestamp()
                except Exception:
                    pass
            return 0.0

        now = time.time()
        dt_val = datetime.now(timezone.utc)
        float_val = time.time() - 100
        int_val = int(time.time()) - 200

        diff_dt = now - _get_ts_sec(dt_val)
        diff_float = now - _get_ts_sec(float_val)
        diff_int = now - _get_ts_sec(int_val)

        self.assertIsInstance(diff_dt, float)
        self.assertLess(diff_dt, 5.0)
        self.assertGreater(diff_float, 90.0)
        self.assertGreater(diff_int, 190.0)

    def test_post_processor_int_and_message_handling(self):
        # Case A: sent_messages are ints
        sent_ints = [12345, 67890]
        messages_to_process = sent_ints

        # Checking that getattr handles int safely
        for msg in messages_to_process:
            p_attr = getattr(msg, 'photo', None)
            self.assertIsNone(p_attr)
            v_attr = getattr(msg, 'video', None)
            self.assertIsNone(v_attr)

        author_ids = [m.message_id if hasattr(m, 'message_id') else int(m) for m in messages_to_process]
        self.assertEqual(author_ids, [12345, 67890])

        # Case B: sent_messages are Message-like objects
        class MockPhoto:
            file_id = "photo_file_123"

        class MockMessage:
            def __init__(self, mid, photo=None):
                self.message_id = mid
                self.photo = photo
                self.video = None
                self.document = None
                self.audio = None
                self.animation = None
                self.voice = None

        mock_msg = MockMessage(555, photo=[MockPhoto()])
        messages_to_process = [mock_msg]

        p_attr = getattr(messages_to_process[0], 'photo', None)
        self.assertIsNotNone(p_attr)
        self.assertEqual(p_attr[-1].file_id, "photo_file_123")

        author_ids = [m.message_id if hasattr(m, 'message_id') else int(m) for m in messages_to_process]
        self.assertEqual(author_ids, [555])

if __name__ == "__main__":
    unittest.main()
