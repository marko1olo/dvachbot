import sys
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ["SECRET_KEY"] = "test-secret-key-12345"
os.environ["BOT_TOKEN"] = "123:test"

import asyncio

try:
    asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from Dubsite_tgach.main import _select_mirror_strategically

class TestSelectMirrorStrategically(unittest.TestCase):

    def test_basic_image_no_mirrors(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        orig, thumb = _select_mirror_strategically(file_info, {}, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/img.jpg')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_video_with_huggingface(self):
        file_info = {'original_url': 'http://base.com/vid.mp4', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'video'}
        mirrors = {'huggingface': 'http://hf.co/vid.mp4'}
        orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://hf.co/vid.mp4')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_video_no_huggingface(self):
        file_info = {'original_url': 'http://base.com/vid.mp4', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'video'}
        mirrors = {'telegram': 'http://tg.co/vid.mp4'}
        orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/vid.mp4')
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

    def test_image_with_huggingface_selected(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        mirrors = {'huggingface': 'http://hf.co/img.jpg'}

        with patch('main.random.choice', return_value='huggingface'):
            orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://hf.co/img.jpg')

    def test_image_with_huggingface_not_selected(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        mirrors = {'huggingface': 'http://hf.co/img.jpg'}

        with patch('main.random.choice', return_value='telegram'):
            orig, thumb = _select_mirror_strategically(file_info, mirrors, {}, is_ru=True)
        self.assertEqual(orig, 'http://base.com/img.jpg')

    def test_thumb_with_huggingface(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'huggingface': 'http://hf.co/thumb.jpg', 'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=True)
        self.assertEqual(thumb, 'http://hf.co/thumb.jpg')

    def test_thumb_catbox_not_ru(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=False)
        self.assertEqual(thumb, 'http://catbox.moe/thumb.jpg')

    def test_thumb_catbox_is_ru(self):
        file_info = {'original_url': 'http://base.com/img.jpg', 'thumbnail_url': 'http://base.com/thumb.jpg', 'type': 'photo'}
        thumb_mirrors = {'catbox': 'http://catbox.moe/thumb.jpg'}
        orig, thumb = _select_mirror_strategically(file_info, {}, thumb_mirrors, is_ru=True)
        self.assertEqual(thumb, 'http://base.com/thumb.jpg')

if __name__ == '__main__':
    unittest.main()
