import ast
import io
import json
import runpy
from unittest.mock import patch


def test_no_unused_datetime_import():
    """Verify that datetime is not imported in scripts/generate_report_clean.py."""
    with open("scripts/generate_report_clean.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.append(node.module)

    assert "datetime" not in imported_modules
    assert "datetime.datetime" not in imported_modules


def test_generate_report_clean_execution():
    """Verify end-to-end execution of generate_report_clean.py with mock data."""
    fake_posts = [
        {
            "timestamp": 100,
            "clean_text": "почему бот тормозит",
            "author_id": "author_1",
            "thread_id": "thread_1",
            "content": json.dumps({"reply_to_post": 99}),
            "post_num": 101,
        },
        {
            "timestamp": 110,
            "clean_text": "го казино дуэль",
            "author_id": "author_2",
            "thread_id": "thread_1",
            "content": "invalid json",
            "post_num": 102,
        },
        {
            "timestamp": 120,
            "clean_text": "",
            "author_id": "author_1",
            "thread_id": None,
            "content": json.dumps({}),
            "post_num": 103,
        },
    ]
    fake_mutes = [
        {
            "user_id": "author_2",
            "expires_at": 500000,
            "board_id": "b",
            "reason": "спам",
        }
    ]
    fake_logs = [{"action": "test_log"}]

    data_map = {
        "c:/Users/danat/Desktop/dvachbot/latest_posts_clean.json": json.dumps(fake_posts),
        "c:/Users/danat/Desktop/dvachbot/recent_mutes.json": json.dumps(fake_mutes),
        "c:/Users/danat/Desktop/dvachbot/recent_logs.json": json.dumps(fake_logs),
    }
    written_contents = {}
    orig_open = open

    class TrackingStringIO(io.StringIO):
        def __init__(self, path):
            super().__init__()
            self.path = path

        def close(self):
            written_contents[self.path] = self.getvalue()
            super().close()

    def custom_open(path, mode="r", encoding=None):
        if "w" in mode:
            return TrackingStringIO(path)
        if path in data_map:
            return io.StringIO(data_map[path])
        return orig_open(path, mode, encoding=encoding)

    with patch("builtins.open", side_effect=custom_open):
        runpy.run_path("scripts/generate_report_clean.py")

    output_path = "c:/Users/danat/Desktop/dvachbot/REPORT_NEWEST_POSTS_BREAKDOWN.md"
    assert output_path in written_contents
    report_content = written_contents[output_path]

    assert "# ДЕТАЛЬНЫЙ АНАЛИЗ ПОСЛЕДНИХ 500 ПОСТОВ DVACHBOT" in report_content
    assert "почему бот тормозит" in report_content
    assert "го казино дуэль" in report_content
    assert "[ТОЛЬКО МЕДИА]" in report_content
    assert "author_1" in report_content
    assert "Тред `thread_1`" in report_content
