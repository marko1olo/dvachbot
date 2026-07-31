import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from site_tgach.media_utils import detect_media_type

class TestDetectMediaType(unittest.TestCase):
    def test_video_by_ftyp_header(self):
        # 'ftyp' in header
        data = b'\x00\x00\x00\x1cftypmp42'
        self.assertEqual(detect_media_type(data, "http://example.com/file.unknown"), "video")

    def test_video_by_webm_header(self):
        # webm signature \x1A\x45\xDF\xA3
        data = b'\x1A\x45\xDF\xA3\x01\x00\x00\x00'
        self.assertEqual(detect_media_type(data, "http://example.com/file.unknown"), "video")

    def test_animation_by_gif_header(self):
        # GIF8 signature
        data = b'GIF89a...'
        self.assertEqual(detect_media_type(data, "http://example.com/file.unknown"), "animation")

    def test_video_by_mp4_extension(self):
        data = b'random data'
        self.assertEqual(detect_media_type(data, "http://example.com/file.mp4"), "video")
        self.assertEqual(detect_media_type(data, "http://example.com/file.MP4"), "video")

    def test_video_by_webm_extension(self):
        data = b'random data'
        self.assertEqual(detect_media_type(data, "http://example.com/file.webm"), "video")
        self.assertEqual(detect_media_type(data, "http://example.com/file.WEBM"), "video")

    def test_video_by_mov_extension(self):
        data = b'random data'
        self.assertEqual(detect_media_type(data, "http://example.com/file.mov"), "video")
        self.assertEqual(detect_media_type(data, "http://example.com/file.MOV"), "video")

    def test_animation_by_gif_extension(self):
        data = b'random data'
        self.assertEqual(detect_media_type(data, "http://example.com/file.gif"), "animation")
        self.assertEqual(detect_media_type(data, "http://example.com/file.GIF"), "animation")

    def test_photo_fallback(self):
        # JPEG or any other data that doesn't match above headers and has a different extension
        data = b'\xFF\xD8\xFF\xE0\x00\x10JFIF'
        self.assertEqual(detect_media_type(data, "http://example.com/file.jpg"), "photo")
        self.assertEqual(detect_media_type(data, "http://example.com/file.unknown"), "photo")

        # Empty data and unknown url
        self.assertEqual(detect_media_type(b'', ""), "photo")

if __name__ == '__main__':
    unittest.main()
