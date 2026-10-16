import unittest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from delivery_manager import _lie_media_kind

class TestDeliveryManager(unittest.TestCase):
    def test_lie_media_kind_none(self):
        self.assertIsNone(_lie_media_kind(None))
        self.assertIsNone(_lie_media_kind(""))

    def test_lie_media_kind_image(self):
        self.assertEqual(_lie_media_kind("photo"), "image")
        self.assertEqual(_lie_media_kind("image"), "image")
        self.assertEqual(_lie_media_kind("test.photo"), "image")
        self.assertEqual(_lie_media_kind(None, {"type": "photo"}), "image")
        self.assertEqual(_lie_media_kind(None, {"type": "some.image"}), "image")

    def test_lie_media_kind_video(self):
        self.assertEqual(_lie_media_kind("video"), "video")
        self.assertEqual(_lie_media_kind("animation"), "video")
        self.assertEqual(_lie_media_kind("gif"), "video")
        self.assertEqual(_lie_media_kind("MessageMediaDocument.video"), "video")
        self.assertEqual(_lie_media_kind(None, {"type": "video"}), "video")

    def test_lie_media_kind_document_video(self):
        self.assertEqual(_lie_media_kind("document", {"mime_type": "video/mp4"}), "video")
        self.assertEqual(_lie_media_kind("document", {"mime": "video/webm"}), "video")
        self.assertEqual(_lie_media_kind("document", {"filename": "test.mp4"}), "video")
        self.assertEqual(_lie_media_kind("document", {"file_name": "test.mov"}), "video")
        self.assertEqual(_lie_media_kind("document", {"name": "test.mkv"}), "video")

    def test_lie_media_kind_document_image(self):
        self.assertEqual(_lie_media_kind("document", {"mime_type": "image/jpeg"}), "image")
        self.assertEqual(_lie_media_kind("document", {"mime": "image/png"}), "image")
        self.assertEqual(_lie_media_kind("document", {"filename": "test.jpg"}), "image")
        self.assertEqual(_lie_media_kind("document", {"file_name": "test.webp"}), "image")
        self.assertEqual(_lie_media_kind("document", {"name": "test.gif"}), "image")

    def test_lie_media_kind_document_unknown(self):
        self.assertIsNone(_lie_media_kind("document", {"mime_type": "application/pdf"}))
        self.assertIsNone(_lie_media_kind("document", {"filename": "test.pdf"}))
        self.assertIsNone(_lie_media_kind("document"))
        self.assertIsNone(_lie_media_kind("unknown"))
        self.assertIsNone(_lie_media_kind(None, {"type": "unknown"}))

if __name__ == '__main__':
    unittest.main()
