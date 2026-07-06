import unittest
import os
import sys
import re

# Ensure import paths work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from warhammer_mode import orkify, necronify

class TestWarhammerMode(unittest.TestCase):

    def test_orkify_basic_replacement(self):
        text = "собака чай куртка"
        result = orkify(text)
        self.assertTrue(result.isupper())
        self.assertIn("З", result)   # С -> З
        self.assertIn("Ш", result)   # Ч -> Ш
        self.assertNotIn("С", result)
        self.assertNotIn("Ч", result)
        # Note: К may appear in appended -ДАККА suffix, so don't assert its absence

    def test_orkify_dakka_append(self):
        text = "большое слово для тестирования добавления дакки"
        results = [orkify(text) for _ in range(30)]
        self.assertTrue(any("-ДАККА" in r for r in results))

    def test_orkify_gluing(self):
        text = "то ах ну да"
        results = [orkify(text) for _ in range(30)]
        has_glued = any(len(r.split()) < 4 for r in results)
        self.assertTrue(has_glued)

    def test_necronify_basic(self):
        result = necronify("тестовое сообщение")
        self.assertTrue(result.startswith("++Анализ органической речи:"))
        self.assertTrue(result.endswith("++Протокол выполнен.++"))
        self.assertIn("тестовое", result)
        self.assertIn("сообщение", result)

    def test_necronify_injection(self):
        text = "очень много разных слов для теста бинарных инъекций"
        results = [necronify(text) for _ in range(30)]
        has_binary = any(re.search(r'\+\+[01]{16}\+\+', r) for r in results)
        self.assertTrue(has_binary)

if __name__ == '__main__':
    unittest.main()
