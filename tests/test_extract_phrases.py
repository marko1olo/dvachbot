import unittest
import os
import tempfile
import ast

from extract_phrases import extract_strings

class TestExtractPhrases(unittest.TestCase):
    def setUp(self):
        # Create a temporary python file to parse
        self.fd, self.filepath = tempfile.mkstemp(suffix='.py')

    def tearDown(self):
        os.close(self.fd)
        os.remove(self.filepath)

    def write_code(self, code: str):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(code)

    def test_extract_send_message_arg(self):
        self.write_code("bot.send_message('Hello world')\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 1)
        self.assertEqual(phrases[0]['text'], 'Hello world')
        self.assertEqual(phrases[0]['line'], 1)

    def test_extract_reply_arg(self):
        self.write_code("message.reply('Reply text')\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 1)
        self.assertEqual(phrases[0]['text'], 'Reply text')
        self.assertEqual(phrases[0]['line'], 1)

    def test_extract_answer_arg(self):
        self.write_code("callback.answer('Answer text')\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 1)
        self.assertEqual(phrases[0]['text'], 'Answer text')
        self.assertEqual(phrases[0]['line'], 1)

    def test_extract_keyword_text(self):
        self.write_code("bot.send_message(chat_id=123, text='Keyword text')\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 1)
        self.assertEqual(phrases[0]['text'], 'Keyword text')
        self.assertEqual(phrases[0]['line'], 1)

    def test_extract_multiple(self):
        self.write_code(
            "def foo():\n"
            "    bot.send_message('Msg 1')\n"
            "    message.reply(text='Msg 2')\n"
        )
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 2)
        self.assertEqual(phrases[0]['text'], 'Msg 1')
        self.assertEqual(phrases[0]['line'], 2)
        self.assertEqual(phrases[1]['text'], 'Msg 2')
        self.assertEqual(phrases[1]['line'], 3)

    def test_ignore_other_functions(self):
        self.write_code("print('Ignore me')\nother.method('Ignore too')\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 0)

    def test_ignore_non_string(self):
        self.write_code("bot.send_message(123)\nbot.send_message(text=456)\n")
        phrases = extract_strings(self.filepath)
        self.assertEqual(len(phrases), 0)

if __name__ == '__main__':
    unittest.main()
