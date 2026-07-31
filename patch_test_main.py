with open('tests/test_main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I will add the test case to test_main.py
test_class = """
class TestAdjustPromptParagraphs(unittest.TestCase):
    def test_ru_paragraphs(self):
        from main import adjust_prompt_paragraphs
        # 1
        prompt = "объемом ровно в 1-2 абзаца"
        res = adjust_prompt_paragraphs(prompt, 1, 'ru')
        self.assertIn("ровно в 1 абзац", res)
        self.assertIn("СТРОГО из 1 абзацев", res)

        # 2
        prompt = "ровно 3-4 абзаца"
        res = adjust_prompt_paragraphs(prompt, 2, 'ru')
        self.assertIn("ровно 2 абзаца", res)
        self.assertIn("СТРОГО из 2 абзацев", res)

        # 5
        prompt = "строго 6-8 крупных абзацев"
        res = adjust_prompt_paragraphs(prompt, 5, 'ru')
        self.assertIn("строго 5 крупных абзацев", res)

        # 11
        prompt = "не менее 6-8 крупных, содержательных абзацев с подробностями"
        res = adjust_prompt_paragraphs(prompt, 11, 'ru')
        self.assertIn("ровно 11 крупных абзацев с подробностями", res)

        # 21
        prompt = "1-2 предложения"
        res = adjust_prompt_paragraphs(prompt, 21, 'ru')
        self.assertIn("ровно 21 абзац", res)

        prompt = "ультра-короткую, циничную прожарку"
        res = adjust_prompt_paragraphs(prompt, 1, 'ru')
        self.assertIn("циничную прожарку", res)

    def test_en_paragraphs(self):
        from main import adjust_prompt_paragraphs
        # 1
        prompt = "1-2 sentences"
        res = adjust_prompt_paragraphs(prompt, 1, 'en')
        self.assertIn("1 paragraph", res)
        self.assertIn("EXACTLY 1 paragraphs", res)

        # 3
        prompt = "3-4 paragraphs"
        res = adjust_prompt_paragraphs(prompt, 3, 'en')
        self.assertIn("exactly 3 paragraphs", res)

        prompt = "at least 6-8 heavy, informative paragraphs"
        res = adjust_prompt_paragraphs(prompt, 5, 'en')
        self.assertIn("exactly 5 heavy, informative paragraphs", res)

    def test_jp_paragraphs(self):
        from main import adjust_prompt_paragraphs
        prompt = "3行で"
        res = adjust_prompt_paragraphs(prompt, 3, 'jp')
        self.assertIn("3段落で", res)
        self.assertIn("正確に3段落で", res)

        prompt = "3行で"
        res = adjust_prompt_paragraphs(prompt, 2, 'jp')
        self.assertIn("2段落で", res)

if __name__ == '__main__':
"""

new_content = content.replace("if __name__ == '__main__':", test_class)

with open('tests/test_main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
