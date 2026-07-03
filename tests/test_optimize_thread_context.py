import unittest
import os
import asyncio

# Mock environment variables before importing
os.environ['SECRET_KEY'] = 'test_secret_key'
os.environ['BOT_TOKEN'] = 'test_bot_token'
os.environ['OPENAI_API_KEY'] = 'test_openai_api_key'

# Create and set new event loop to avoid Pyrogram/asyncio errors
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from Dubsite_tgach.main import optimize_thread_context

class TestOptimizeThreadContext(unittest.TestCase):

    def test_clean_html_removal(self):
        op_post = {'content': {'text': '<b>Bold</b> and <i>Italic</i><br>text'}}
        replies = []
        result = optimize_thread_context(op_post, replies)
        self.assertEqual(result, 'OP: Bold and Italic text')

    def test_clean_url_replacement(self):
        op_post = {'content': {'text': 'Check this out: https://example.com/some/path?q=123'}}
        replies = []
        result = optimize_thread_context(op_post, replies)
        self.assertEqual(result, 'OP: Check this out: [link]')

    def test_clean_whitespace_normalization(self):
        op_post = {'content': {'text': '  Lots   of \n space \t here  '}}
        replies = []
        result = optimize_thread_context(op_post, replies)
        self.assertEqual(result, 'OP: Lots of space here')

    def test_op_missing_or_empty(self):
        # Empty dict
        result1 = optimize_thread_context({}, [])
        self.assertEqual(result1, '')

        # Missing text
        result2 = optimize_thread_context({'content': {}}, [])
        self.assertEqual(result2, '')

        # Empty text
        result3 = optimize_thread_context({'content': {'text': ''}}, [])
        self.assertEqual(result3, '')

    def test_replies_formatting(self):
        op_post = {'content': {'text': 'OP Post'}}
        replies = [
            {'content': {'text': 'Reply 1'}},
            {'content': {'text': 'Reply 2'}},
            {'content': {'text': ''}}, # Empty reply should be ignored
            {'content': {}}, # Missing text should be ignored
            {}, # Empty dict should be ignored
            {'content': {'text': 'Reply 3'}}
        ]
        result = optimize_thread_context(op_post, replies)
        self.assertEqual(result, 'OP: OP Post | Reply 1 | Reply 2 | Reply 3')

    def test_max_posts_limit(self):
        op_post = {'content': {'text': 'OP'}}
        # Generate 50 replies
        replies = [{'content': {'text': f'Reply {i}'}} for i in range(50)]

        # Test default max_posts (40)
        result_default = optimize_thread_context(op_post, replies)
        parts_default = result_default.split(' | ')
        self.assertEqual(len(parts_default), 41) # OP + 40 replies
        self.assertEqual(parts_default[1], 'Reply 10') # First included reply is 10
        self.assertEqual(parts_default[-1], 'Reply 49') # Last included reply is 49

        # Test custom max_posts
        result_custom = optimize_thread_context(op_post, replies, max_posts=5)
        parts_custom = result_custom.split(' | ')
        self.assertEqual(len(parts_custom), 6) # OP + 5 replies
        self.assertEqual(parts_custom[1], 'Reply 45')
        self.assertEqual(parts_custom[-1], 'Reply 49')

    def test_text_truncation(self):
        long_text = 'A' * 250
        op_post = {'content': {'text': long_text}}
        replies = [{'content': {'text': long_text}}]

        result = optimize_thread_context(op_post, replies)
        parts = result.split(' | ')

        # OP text length should be 200 (due to clean truncation)
        # Plus 'OP: ' prefix = 204
        self.assertEqual(len(parts[0]), 204)
        self.assertEqual(parts[0], f'OP: {"A" * 200}')

        # Reply text length should be 200
        self.assertEqual(len(parts[1]), 200)
        self.assertEqual(parts[1], 'A' * 200)

if __name__ == '__main__':
    unittest.main()
