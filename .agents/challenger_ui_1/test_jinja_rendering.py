import os
import sys
import re
import html
import unittest
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = r"C:\Users\danat\Desktop\dvachbot"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def pluralize_russian(count, one, few, many):
    try:
        n = abs(int(count))
        if n % 10 == 1 and n % 100 != 11:
            return one
        elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
            return few
        else:
            return many
    except (ValueError, TypeError, OverflowError):
        return many

def format_timestamp(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return ""

def format_iso_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).isoformat()
    except Exception:
        return ""

def format_bayan_label(count: int, lang: str = "ru") -> str:
    if not count or count <= 1:
        return ""
    return f"♻️ Баян ({count})"

def mock_clean_title(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', str(text))

def mock_format_post_text(text):
    if not text:
        return ""
    return html.escape(str(text))

class MockUrl:
    def __init__(self, url="http://localhost:8000/b/"):
        self._url = url

class MockRequestState:
    def __init__(self, lang="ru"):
        self.lang = lang
    def t(self, key, *args, **kwargs):
        translations = {
            "site_name": "Тгач",
            "gallery_title": "Галерея",
            "audio_voice_label": "Голосовое сообщение",
            "audio_random_artists": ["Анонимный артист"],
            "audio_random_tracks": ["Без названия"]
        }
        val = translations.get(key, key)
        if kwargs and isinstance(val, str):
            for k, v in kwargs.items():
                val = val.replace(f"{{{k}}}", str(v))
        return val

class MockRequest:
    def __init__(self):
        self.state = MockRequestState()
        self.url = MockUrl()

class TestJinjaTemplateRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template_dir = os.path.join(PROJECT_ROOT, "site_tgach", "templates")
        cls.env = Environment(loader=FileSystemLoader(template_dir))
        cls.env.filters.update({
            "pluralize": pluralize_russian,
            "format_post_text": mock_format_post_text,
            "format_timestamp": format_timestamp,
            "format_iso_time": format_iso_time,
            "bayan_label": format_bayan_label,
            "clean_title": mock_clean_title
        })
        cls.request = MockRequest()
        cls.board_info = {"id": "b", "name": "Бред"}
        cls.boards = {"b": {"id": "b", "name": "Бред"}}

    def test_catalog_edge_cases(self):
        template = self.env.get_template("catalog.jinja2")
        test_threads = [
            # 1. Missing file_id, fallback to external URLs
            {
                "id": 101,
                "content": {
                    "text": "Thread with external URLs only",
                    "is_censored": False,
                    "files": [
                        {
                            "thumbnail_file_id": None,
                            "original_file_id": None,
                            "thumbnail_url": "https://catbox.moe/thumb.jpg",
                            "original_url": "https://catbox.moe/orig.jpg",
                            "type": "image",
                            "filename": "ext.jpg",
                            "blurhash": "L6PZf-00_4="
                        }
                    ]
                }
            },
            # 2. Missing external URLs, uses local proxy /files/
            {
                "id": 102,
                "content": {
                    "text": "Thread with local proxy file_ids only",
                    "is_censored": True,
                    "files": [
                        {
                            "thumbnail_file_id": "thumb_fid_102",
                            "original_file_id": "orig_fid_102",
                            "thumbnail_url": None,
                            "original_url": None,
                            "type": "video",
                            "filename": "video.mp4",
                            "blurhash": None
                        }
                    ]
                }
            },
            # 3. Both file_id and external URL missing
            {
                "id": 103,
                "content": {
                    "text": "Thread with missing media links",
                    "is_censored": False,
                    "files": [
                        {
                            "thumbnail_file_id": None,
                            "original_file_id": None,
                            "thumbnail_url": None,
                            "original_url": None,
                            "type": "image",
                            "filename": "missing.jpg",
                            "blurhash": None
                        }
                    ]
                }
            },
            # 4. Special characters in text and filenames
            {
                "id": 104,
                "content": {
                    "text": "<script>alert('xss')</script> >>9999 '><a href=\"bad\">Link</a>",
                    "is_censored": False,
                    "files": [
                        {
                            "thumbnail_file_id": "tfid_104",
                            "original_file_id": "ofid_104",
                            "thumbnail_url": "https://catbox.moe/104.jpg",
                            "original_url": "https://catbox.moe/104.jpg",
                            "type": "image",
                            "filename": "file\"'<>with_special.jpg"
                        }
                    ]
                }
            },
            # 5. Multiple files
            {
                "id": 105,
                "content": {
                    "text": "Multi file thread",
                    "files": [
                        {"thumbnail_file_id": "tf1", "original_file_id": "of1", "type": "image"},
                        {"thumbnail_file_id": "tf2", "original_file_id": "of2", "type": "gif"}
                    ]
                }
            }
        ]

        rendered = template.render(
            board_id="b",
            board_info=self.board_info,
            boards=self.boards,
            threads=test_threads,
            current_sort="bump",
            is_skeleton=False,
            request=self.request
        )

        self.assertIn("/files/thumb_fid_102", rendered)
        self.assertIn("/files/orig_fid_102", rendered)
        self.assertIn("https://catbox.moe/thumb.jpg", rendered)
        # Check no corrupt href or unescaped XSS script tags in rendered HTML attributes
        self.assertNotIn("<script>alert", rendered)
        self.assertNotIn("href=\"bad\"", rendered)

    def test_thread_edge_cases(self):
        template = self.env.get_template("thread.jinja2")
        op_post = {
            "id": 201,
            "timestamp": 1700000000.0,
            "author_id": "author123",
            "is_op_yours": False,
            "is_op_hidden": False,
            "content": {
                "text": "OP Post text with >>5555 & ' \" < >",
                "is_censored": False,
                "files": [
                    {
                        "thumbnail_file_id": "op_thumb_id",
                        "original_file_id": "op_orig_id",
                        "thumbnail_url": "https://catbox.moe/op_thumb.jpg",
                        "original_url": "https://catbox.moe/op_orig.jpg",
                        "type": "image",
                        "filename": "op_image.png",
                        "blurhash": "L6PZf-00_4="
                    },
                    {
                        "thumbnail_file_id": None,
                        "original_file_id": "op_vid_orig_id",
                        "thumbnail_url": None,
                        "original_url": "https://catbox.moe/vid.mp4",
                        "type": "video",
                        "filename": "video.mp4"
                    }
                ]
            }
        }

        replies = [
            {
                "id": 202,
                "timestamp": 1700000100.0,
                "author_id": "author456",
                "content": {
                    "text": "Reply text with multiple media",
                    "files": [
                        {
                            "thumbnail_file_id": "reply_t_id",
                            "original_file_id": "reply_o_id",
                            "thumbnail_url": "https://catbox.moe/reply.png",
                            "original_url": "https://catbox.moe/reply.png",
                            "type": "image",
                            "filename": "reply.png"
                        },
                        {
                            "thumbnail_file_id": None,
                            "original_file_id": "reply_audio_id",
                            "thumbnail_url": None,
                            "original_url": "https://catbox.moe/audio.mp3",
                            "type": "audio",
                            "filename": "audio.mp3",
                            "mime_type": "audio/mpeg"
                        }
                    ]
                }
            }
        ]

        rendered = template.render(
            board_id="b",
            board_info=self.board_info,
            boards=self.boards,
            thread_id=201,
            op_post=op_post,
            posts=replies,
            request=self.request
        )

        self.assertIn("/files/op_thumb_id", rendered)
        self.assertIn("/files/op_orig_id", rendered)
        self.assertIn("/files/reply_t_id", rendered)
        self.assertIn("/files/reply_audio_id", rendered)

    def test_board_edge_cases(self):
        template = self.env.get_template("board.jinja2")
        posts = [
            {
                "id": 301,
                "timestamp": 1700000000.0,
                "author_id": "auth1",
                "content": {
                    "text": "Board OP post",
                    "files": [
                        {
                            "thumbnail_file_id": "op_audio_t",
                            "original_file_id": "op_audio_o",
                            "thumbnail_url": None,
                            "original_url": "https://catbox.moe/song.mp3",
                            "type": "audio",
                            "filename": "song.mp3",
                            "mime_type": "audio/mpeg"
                        },
                        {
                            "thumbnail_file_id": None,
                            "original_file_id": "doc_file_id_999",
                            "thumbnail_url": None,
                            "original_url": "https://catbox.moe/doc.pdf",
                            "type": "document",
                            "filename": "doc.pdf"
                        }
                    ]
                },
                "replies": [
                    {
                        "id": 302,
                        "timestamp": 1700000100.0,
                        "author_id": "auth2",
                        "content": {
                            "text": "Reply with audio",
                            "files": [
                                {
                                    "thumbnail_file_id": None,
                                    "original_file_id": "reply_audio_file_id",
                                    "thumbnail_url": None,
                                    "original_url": "https://catbox.moe/voice.ogg",
                                    "type": "voice",
                                    "filename": "voice_123.ogg"
                                }
                            ]
                        }
                    }
                ]
            }
        ]

        rendered = template.render(
            board_id="b",
            board_info=self.board_info,
            boards=self.boards,
            posts=posts,
            request=self.request
        )

        self.assertIn("/files/reply_audio_file_id", rendered)

    def test_gallery_edge_cases(self):
        template = self.env.get_template("gallery.jinja2")
        threads = [
            {
                "id": 401,
                "content": {
                    "text": "Gallery item",
                    "files": [
                        {
                            "thumbnail_file_id": "gal_t_401",
                            "original_file_id": "gal_o_401",
                            "thumbnail_url": "https://catbox.moe/gal.jpg",
                            "original_url": "https://catbox.moe/gal.jpg",
                            "type": "image",
                            "filename": "gal.jpg"
                        }
                    ]
                }
            }
        ]

        rendered = template.render(
            board_id="b",
            board_info=self.board_info,
            boards=self.boards,
            op_post_num=401,
            threads=threads,
            request=self.request
        )

        self.assertIn("/files/gal_t_401", rendered)
        self.assertIn("/files/gal_o_401", rendered)

if __name__ == "__main__":
    unittest.main()
