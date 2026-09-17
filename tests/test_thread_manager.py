import unittest
from common.thread_manager import (
    trim_thread_posts,
    set_thread_info,
    get_thread_info,
    _threads_data
)

class TestThreadManager(unittest.TestCase):
    def setUp(self):
        # Clear out existing state to ensure clean tests
        _threads_data.clear()

    def test_trim_thread_posts_basic(self):
        set_thread_info("b", "123", {"posts": [1, 2, 3, 4, 5]})

        # Max posts is 3, should keep OP (1) and last 2 (4, 5)
        # Therefore, 2, 3 should be trimmed
        trimmed = trim_thread_posts("b", "123", 3)
        self.assertEqual(trimmed, [2, 3])
        self.assertEqual(get_thread_info("b", "123")["posts"], [1, 4, 5])

    def test_trim_thread_posts_no_trim_needed(self):
        set_thread_info("b", "124", {"posts": [1, 2, 3]})

        # Max posts is 5, no trim needed
        trimmed = trim_thread_posts("b", "124", 5)
        self.assertEqual(trimmed, [])
        self.assertEqual(get_thread_info("b", "124")["posts"], [1, 2, 3])

    def test_trim_thread_posts_empty(self):
        set_thread_info("b", "125", {"posts": []})

        trimmed = trim_thread_posts("b", "125", 5)
        self.assertEqual(trimmed, [])
        self.assertEqual(get_thread_info("b", "125")["posts"], [])

    def test_trim_thread_posts_no_posts_key(self):
        set_thread_info("b", "126", {})

        trimmed = trim_thread_posts("b", "126", 5)
        self.assertEqual(trimmed, [])
        self.assertNotIn("posts", get_thread_info("b", "126"))

    def test_trim_thread_posts_exact_limit(self):
        set_thread_info("b", "127", {"posts": [1, 2, 3, 4, 5]})

        trimmed = trim_thread_posts("b", "127", 5)
        self.assertEqual(trimmed, [])
        self.assertEqual(get_thread_info("b", "127")["posts"], [1, 2, 3, 4, 5])

if __name__ == '__main__':
    unittest.main()
