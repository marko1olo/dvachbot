import unittest
<<<<<<< Updated upstream
import asyncio
from unittest.mock import patch, AsyncMock
from conan import conan_phrase, conan_roaster

class TestConan(unittest.IsolatedAsyncioTestCase):
    def test_conan_phrase_default_username(self):
        phrase = conan_phrase()
        self.assertIsInstance(phrase, str)
        self.assertTrue(len(phrase) > 0)

    def test_conan_phrase_custom_username(self):
        phrase = conan_phrase(username="testuser")
        self.assertIsInstance(phrase, str)
        self.assertTrue(len(phrase) > 0)

    @patch('conan.asyncio.sleep', new_callable=AsyncMock)
    @patch('conan.secrets.choice')
    async def test_conan_roaster(self, mock_choice, mock_sleep):
        # We want to exit the loop after one iteration by raising CancelledError on the second sleep
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        # mock_choice is used for conan_phrase AND for choosing post_num_to_reply.
        # We need to make it return appropriate values depending on context or just return 1 for post and strings for phrase

        # let's write a side_effect function
        def choice_side_effect(seq):
            if isinstance(seq, list) and isinstance(seq[0], int): # list of valid posts
                return seq[0]
            elif isinstance(seq, list) and isinstance(seq[0], str): # string lists
                return seq[0]
            return seq[0]

        mock_choice.side_effect = choice_side_effect

        state = {'post_counter': 100}
        messages_storage = {1: {}}
        post_to_messages = {1: True}
        message_to_post = {}
        message_queues = {'b': asyncio.Queue()}
        format_header = AsyncMock(return_value="Conan Header")
        board_data = {
            'b': {'users': {'active': 5, 'banned': 1}},
            'empty': {'users': {'active': 1, 'banned': 1}} # 0 active recipients, should be skipped initially
        }
        storage_lock = asyncio.Lock()

        with self.assertRaises(asyncio.CancelledError):
            await conan_roaster(state, messages_storage, post_to_messages, message_to_post, message_queues, format_header, board_data, storage_lock)

        self.assertEqual(state['post_counter'], 101)
        self.assertIn(101, messages_storage)
        msg = messages_storage[101]
        self.assertEqual(msg['board_id'], 'b')
        self.assertEqual(msg['content']['header'], 'Conan Header')
        self.assertEqual(msg['content']['reply_to_post'], 1)
        self.assertTrue(len(msg['content']['text']) > 0)

        self.assertEqual(message_queues['b'].qsize(), 1)
        queued_msg = await message_queues['b'].get()
        self.assertEqual(queued_msg['post_num'], 101)
        self.assertEqual(queued_msg['recipients'], 4)
        self.assertEqual(queued_msg['content']['reply_to_post'], 1)
=======
from unittest.mock import patch
from conan import conan_phrase

class TestConanPhrase(unittest.TestCase):
    def test_conan_phrase_default(self):
        """Test conan_phrase with default username argument"""
        result = conan_phrase()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_conan_phrase_custom(self):
        """Test conan_phrase with a custom username"""
        result = conan_phrase("TestUser")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch('conan.secrets.choice')
    def test_conan_phrase_formatting(self, mock_choice):
        """Test conan_phrase string formatting with deterministic mocked values"""
        # mock_choice is called for: tpl, inv, wgt, ach, ins, fact, catch
        mock_choice.side_effect = [
            "{name} {inv} {wgt} {ach} {ins} {fact} {catch}", # tpl
            "MOCK_INV", # inv
            "MOCK_WGT", # wgt
            "MOCK_ACH", # ach
            "MOCK_INS", # ins
            "MOCK_FACT", # fact
            "MOCK_CATCH", # catch
        ]

        result = conan_phrase("CustomUser")
        expected = "CustomUser MOCK_INV MOCK_WGT MOCK_ACH MOCK_INS MOCK_FACT MOCK_CATCH"
        self.assertEqual(result, expected)
        self.assertEqual(mock_choice.call_count, 7)
>>>>>>> Stashed changes

if __name__ == '__main__':
    unittest.main()
