import pytest
import re
import shared_state
from shared_state import board_data
import main
from main import ModeTransformer
import mode_visuals
from mode_visuals import create_visual_post
import zaputin_mode
from zaputin_mode import zaputin_transform

def test_mode_transformer_standalone():
    """Standalone post: header is default 'Пост /b/', no reply, visual allowed."""
    board_data['b']['zaputin_mode'] = True
    content = {'type': 'text', 'text': 'Тестовый текст поста'}
    transformer = ModeTransformer(content, 'b')
    transformer._determine_text_key()

    assert transformer.header == "Пост /b/"
    assert transformer.reply_to_post is None
    assert transformer.allow_visual is True


def test_mode_transformer_reply_in_content():
    """Reply passed in content['reply_to_post']: preserved in header and modified_content."""
    board_data['b']['zaputin_mode'] = True
    content = {'type': 'text', 'text': 'Тестовый ответ на пост', 'reply_to_post': 549872}
    transformer = ModeTransformer(content, 'b')
    transformer._determine_text_key()

    assert transformer.header == "Пост /b/ >>549872"
    assert transformer.reply_to_post == 549872
    assert transformer.modified_content.get('reply_to_post') == 549872
    assert transformer.allow_visual is True


def test_mode_transformer_reply_in_text():
    """Reply passed via >>12345 in plain text: recognized, set in header and modified_content."""
    board_data['b']['zaputin_mode'] = True
    content = {'type': 'text', 'text': '>>549872 Базированный ответ'}
    transformer = ModeTransformer(content, 'b')
    transformer._determine_text_key()

    assert transformer.header == "Пост /b/ >>549872"
    assert transformer.reply_to_post == 549872
    assert transformer.modified_content.get('reply_to_post') == 549872
    assert transformer.allow_visual is True


def test_mode_transformer_visual_image_preserves_reply():
    """When visual transform returns image, reply_to_post is preserved in modified_content."""
    board_data['b']['zaputin_mode'] = True
    content = {'type': 'text', 'text': '>>549872 Zа наших!', 'reply_to_post': 549872}
    transformer = ModeTransformer(content, 'b')
    transformer._determine_text_key()

    fake_bytes = b"FAKE_IMAGE_DATA_BYTES"
    applied = transformer._handle_transform_result(('image', fake_bytes))

    assert applied is True
    assert transformer.modified_content['type'] == 'photo'
    assert transformer.modified_content['image_bytes'] == fake_bytes
    assert transformer.modified_content.get('reply_to_post') == 549872


def test_demotivator_style_header_selection():
    """Demotivator style uses def_head for generic board header and custom header for replies."""
    orig_choice = mode_visuals.random.choice

    def selective_choice(seq):
        if isinstance(seq, list) and 'demotivator' in seq:
            return 'demotivator'
        return orig_choice(seq)

    mode_visuals.random.choice = selective_choice
    try:
        # Generic header should render without error
        img1 = create_visual_post(mode='zaputin', text='Тестовое сообщение', header='Пост /b/')
        assert img1 is not None

        # Reply header should render without error
        img2 = create_visual_post(mode='zaputin', text='Тестовый ответ', header='Пост /b/ >>549872')
        assert img2 is not None

        # Text with >>549872 should auto-detect reply
        img3 = create_visual_post(mode='zaputin', text='>>549872 Тестовый ответ', header='Пост /b/')
        assert img3 is not None
    finally:
        mode_visuals.random.choice = orig_choice


def test_zaputin_transform_reply_handling():
    """zaputin_transform respects reply headers and produces valid text/image output."""
    res = zaputin_transform('>>549872 Работаем, братья!', header='Пост /b/ >>549872')
    assert isinstance(res, tuple)
    res_type, res_data = res
    assert res_type in ('image', 'text')
    if res_type == 'image':
        assert isinstance(res_data, (bytes, bytearray))
    else:
        assert isinstance(res_data, str)
