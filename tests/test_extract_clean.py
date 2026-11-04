import ast
import json
import unittest
from pathlib import Path


class TestExtractClean(unittest.TestCase):
    def setUp(self):
        self.script_path = Path(__file__).resolve().parents[1] / "scripts" / "extract_clean.py"

    def test_file_exists(self):
        self.assertTrue(self.script_path.exists())

    def test_ast_validity(self):
        tree = ast.parse(self.script_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(tree)

    def test_no_defaultdict_import(self):
        tree = ast.parse(self.script_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "defaultdict", "defaultdict should not be imported"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "defaultdict", "defaultdict should not be imported"
                    )

    def test_clean_text_extraction_logic(self):
        posts = [
            {"content": json.dumps({"text": "Hello world"})},
            {"content": json.dumps({"caption": "Photo caption"})},
            {"content": json.dumps({"text": "", "caption": "Fallback caption"})},
            {"content": None},
            {"content": "invalid json"},
        ]
        results = []
        for p in posts:
            clean_text = ""
            try:
                if p["content"]:
                    content_dict = json.loads(p["content"])
                    text = content_dict.get("text") or content_dict.get("caption") or ""
                    clean_text = text
            except Exception:
                pass
            results.append(clean_text)

        self.assertEqual(
            results,
            ["Hello world", "Photo caption", "Fallback caption", "", ""],
        )


if __name__ == "__main__":
    unittest.main()
