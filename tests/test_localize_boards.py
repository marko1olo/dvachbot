import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# we need to set env vars before importing main
os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"

sys.path.insert(0, os.path.abspath('Dubsite_tgach'))

# Mock the problematic import BEFORE importing main
sys.modules['site_tgach.neuro_poster'] = MagicMock()
sys.modules['site_tgach.neuro_poster']._execute_groq_post = MagicMock()

# Instead of globally monkey-patching MagicMock.__iter__, we will patch the
# specific module or we will create a custom class that only applies when necessary,
# OR we simply set the iter for specific objects before importing main if it fails due to router iterables.
# Actually, the memory says: "patch `unittest.mock.MagicMock.__iter__` to yield infinitely (e.g., `def infinite_iter(self): while True: yield MagicMock(); unittest.mock.MagicMock.__iter__ = infinite_iter`) before importing the target module."
# BUT to not break other tests, we should just delete it afterwards!

def infinite_iter(self):
    while True:
        yield MagicMock()

try:
    MagicMock.__iter__ = infinite_iter
    import main
finally:
    # Always restore it!
    del MagicMock.__iter__

class TestLocalizeBoards(unittest.TestCase):
    def setUp(self):
        # Reset the lru_cache for predictable testing
        main.localize_boards.cache_clear()

    @patch('main.BOARD_CONFIG', {
        'b': {'description': {'ru': 'Бред', 'en': 'Random', 'jp': 'ランダム'}},
        'a': {'description': {'ru': 'Аниме'}},
        'c': {'description': {'en': 'Anime', 'jp': 'アニメ'}},
        'd': {'description': {'jp': 'アニメ'}},
    })
    def test_localize_boards_with_dict_description(self):
        # Test language 'ru'
        ru_boards = main.localize_boards('ru')
        self.assertEqual(ru_boards['b']['description'], 'Бред')
        self.assertEqual(ru_boards['a']['description'], 'Аниме')
        self.assertEqual(ru_boards['c']['description'], 'Anime') # Fallback to en
        self.assertEqual(ru_boards['d']['description'], 'アニメ') # Fallback to first available (jp)

        # Clear cache since it relies on BOARD_CONFIG which we are testing with patched value
        main.localize_boards.cache_clear()

        # Test language 'en'
        en_boards = main.localize_boards('en')
        self.assertEqual(en_boards['b']['description'], 'Random')
        self.assertEqual(en_boards['a']['description'], 'Аниме') # Fallback to ru, then first available
        self.assertEqual(en_boards['c']['description'], 'Anime')

    @patch('main.BOARD_CONFIG', {
        'str_board': {'description': 'String Description'},
        'num_board': {'description': 123},
        'none_board': {'description': None}
    })
    def test_localize_boards_with_non_dict_description(self):
        boards = main.localize_boards('ru')

        # Test strings are kept directly in dict
        self.assertEqual(boards['str_board'], {'description': 'String Description'})

        # In current impl, string descriptions assign the original dict directly:
        # elif isinstance(desc, str):
        #     localized[board_id] = data
        self.assertIs(boards['str_board'], main.BOARD_CONFIG['str_board'])

        # For non-str/non-dict, it copies and converts to string:
        self.assertEqual(boards['num_board']['description'], '123')
        self.assertIsNot(boards['num_board'], main.BOARD_CONFIG['num_board'])

        self.assertEqual(boards['none_board']['description'], 'None')
        self.assertIsNot(boards['none_board'], main.BOARD_CONFIG['none_board'])

if __name__ == '__main__':
    unittest.main()
