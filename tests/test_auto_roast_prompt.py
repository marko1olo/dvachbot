# tests/test_auto_roast_prompt.py
import unittest
import os
import re
import sys

# Add project root to sys.path if not present
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_assets import ROAST_PROMPTS


class TestAutoRoastPrompt(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.ai_manager_path = os.path.join(self.project_root, 'ai_manager.py')
        
        with open(self.ai_manager_path, 'r', encoding='utf-8') as f:
            self.ai_manager_code = f.read()

        # Extract the inline prompt definition from transcribe_and_roast_voice_note
        match = re.search(r'prompt\s*=\s*\((.*?)\)\n\s*from common\.token_pool', self.ai_manager_code, re.DOTALL)
        self.assertTrue(match, "Could not find inline prompt definition in ai_manager.py")
        self.inline_prompt_raw = match.group(1)
        
        # Construct single string representing the evaluated prompt
        lines = [line.strip().strip('"').strip("'") for line in self.inline_prompt_raw.splitlines() if line.strip()]
        self.inline_prompt = " ".join(lines).replace("{transcript}", "Тестовая аудио расшифровка")

    def test_no_polite_ai_disclaimers(self):
        """Assert that inline prompt and ROAST_PROMPTS do NOT contain polite AI disclaimers/cliches."""
        forbidden_disclaimers = [
            "без ИИ-вежливости",
            "как ИИ",
            "как языковая модель",
            "извините",
            "я ИИ",
            "как бот"
        ]

        # Check inline prompt in ai_manager.py
        inline_lower = self.inline_prompt.lower()
        for disclaimer in forbidden_disclaimers:
            self.assertNotIn(
                disclaimer.lower(),
                inline_lower,
                f"Inline prompt contains forbidden disclaimer/cliche: '{disclaimer}'"
            )

        # Check ROAST_PROMPTS in data/text_assets.json
        self.assertTrue(ROAST_PROMPTS, "ROAST_PROMPTS should not be empty")
        for idx, prompt_str in enumerate(ROAST_PROMPTS):
            prompt_lower = prompt_str.lower()
            for disclaimer in forbidden_disclaimers:
                self.assertNotIn(
                    disclaimer.lower(),
                    prompt_lower,
                    f"ROAST_PROMPTS[{idx}] contains forbidden disclaimer/cliche: '{disclaimer}'"
                )

    def test_no_typos(self):
        """Assert that prompts contain no typos like 'отроастить'."""
        forbidden_typos = [
            "отроастить",
            "отроасти",
            "отроасть"
        ]
        
        inline_lower = self.inline_prompt.lower()
        for typo in forbidden_typos:
            self.assertNotIn(
                typo,
                inline_lower,
                f"Inline prompt contains typo: '{typo}'"
            )

        for idx, prompt_str in enumerate(ROAST_PROMPTS):
            prompt_lower = prompt_str.lower()
            for typo in forbidden_typos:
                self.assertNotIn(
                    typo,
                    prompt_lower,
                    f"ROAST_PROMPTS[{idx}] contains typo: '{typo}'"
                )

    def test_covers_voice_and_video_notes(self):
        """Assert that inline prompt explicitly addresses both voice notes and video note circles."""
        inline_lower = self.inline_prompt.lower()
        
        # Voice note terms: голосовуху / голосовухи / голосовое
        has_voice = any(term in inline_lower for term in ["голосовух", "голосовое", "голосовая"])
        self.assertTrue(
            has_voice,
            "Inline prompt does not explicitly address voice notes ('голосовуху'/'голосовые')"
        )

        # Video note terms: кружочек / кружочки / кружочка
        has_video = any(term in inline_lower for term in ["кружоч", "круглые видео"])
        self.assertTrue(
            has_video,
            "Inline prompt does not explicitly address video note circles ('кружочек'/'кружочки')"
        )

    def test_negative_constraints_present(self):
        """Assert that negative constraints against intro fluff, outer quotes, and disclaimers are present."""
        inline_lower = self.inline_prompt.lower()

        # Constraints against intro fluff (e.g. запрещены вступления / преамбулы / вот твоя прожарка)
        has_intro_constraint = any(term in inline_lower for term in ["вступлени", "преамбул", "приветстви"])
        self.assertTrue(
            has_intro_constraint,
            "Inline prompt is missing negative constraints against intro fluff"
        )

        # Constraints against outer quotes or disclaimers
        has_quote_or_disclaimer_constraint = any(term in inline_lower for term in ["кавычки", "оговорки", "оправдани"])
        self.assertTrue(
            has_quote_or_disclaimer_constraint,
            "Inline prompt is missing negative constraints against quotes or disclaimers"
        )

        # Check ROAST_PROMPTS for negative constraints
        for idx, prompt_str in enumerate(ROAST_PROMPTS):
            p_lower = prompt_str.lower()
            has_roast_constraint = any(
                term in p_lower for term in ["запрещ", "без вступлений", "никакой вежливости", "без преамбул"]
            )
            self.assertTrue(
                has_roast_constraint,
                f"ROAST_PROMPTS[{idx}] is missing negative constraints against fluff/disclaimers"
            )

    def test_no_formal_address_in_roast_prompts(self):
        """Assert that ROAST_PROMPTS do NOT contain formal Russian address ('Вы —', 'Проанализируйте', etc.) and start with 'Ты —'."""
        formal_markers = [
            "Вы —",
            "Представьте",
            "Проанализируйте",
            "Выдайте",
            "Разнесите",
            "Укажите"
        ]
        for idx, prompt_str in enumerate(ROAST_PROMPTS):
            for marker in formal_markers:
                self.assertNotIn(
                    marker,
                    prompt_str,
                    f"ROAST_PROMPTS[{idx}] still uses formal address marker: '{marker}'"
                )
            self.assertTrue(
                prompt_str.startswith("Ты —"),
                f"ROAST_PROMPTS[{idx}] should start with informal address 'Ты —'"
            )


if __name__ == '__main__':
    unittest.main()
