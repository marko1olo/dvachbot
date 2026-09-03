# -*- coding: utf-8 -*-
import pytest
from post_helpers import _format_media_context, _format_post_text

def test_format_media_context_both_desc_and_tags():
    media_meta = {
        "description": "Портрет рыжего кота в шляпе",
        "tags": "cat, ginger_cat, hat, cute"
    }
    res = _format_media_context(media_meta)
    assert res == "[Фото: Портрет рыжего кота в шляпе. Теги: cat, ginger_cat, hat, cute]"

def test_format_media_context_desc_only():
    media_meta = {
        "description": "Портрет рыжего кота в шляпе",
        "tags": ""
    }
    res = _format_media_context(media_meta)
    assert res == "[Фото: Портрет рыжего кота в шляпе]"

def test_format_media_context_tags_only():
    media_meta = {
        "description": "",
        "tags": "anime, girl, pink_hair"
    }
    res = _format_media_context(media_meta)
    assert res == "[Фото: anime, girl, pink_hair]"

def test_format_media_context_none_or_empty():
    assert _format_media_context(None) is None
    assert _format_media_context({}) is None
    assert _format_media_context({"description": "", "tags": ""}) is None
    assert _format_media_context({"description": "   ", "tags": "   "}) is None

def test_format_media_context_error_tags_filtering():
    error_cases = [
        {"description": "", "tags": "error"},
        {"description": "", "tags": "download_failed"},
        {"description": "", "tags": "dead"},
        {"description": "", "tags": "format_unsupported"},
        {"description": "", "tags": "no_tags"},
        {"description": "", "tags": "error_no_tags"},
        {"description": "", "tags": "error_too_large"},
        {"description": "download_failed", "tags": "error"},
        {"description": "error: failed to load", "tags": "dead, format_unsupported"}
    ]
    for case in error_cases:
        assert _format_media_context(case) is None

def test_format_media_context_mixed_error_and_valid_tags():
    media_meta = {
        "description": "Кот на крыше",
        "tags": "error, cat, download_failed, roof, dead"
    }
    res = _format_media_context(media_meta)
    assert res == "[Фото: Кот на крыше. Теги: cat, roof]"

def test_format_media_context_truncation():
    long_desc = "Длинное описание " * 15  # > 150 chars
    long_tags = ", ".join([f"tag_{i}" for i in range(25)])  # > 80 chars
    media_meta = {
        "description": long_desc,
        "tags": long_tags
    }
    res = _format_media_context(media_meta)
    assert res.startswith("[Фото: ")
    assert res.endswith("]")
    assert "..." in res
    # Inner description should be <= 153 chars, tags <= 83 chars
    assert len(res) <= 260

def test_format_post_text_photo_with_text():
    content = {"type": "photo", "text": "Оцените моего кота"}
    media_meta = {"description": "Рыжий кот", "tags": "cat"}
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: Рыжий кот. Теги: cat] Оцените моего кота"

def test_format_post_text_photo_without_text():
    content = {"type": "photo"}
    media_meta = {"description": "Рыжий кот", "tags": "cat"}
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: Рыжий кот. Теги: cat]"

def test_format_post_text_photo_with_caption():
    content = {"type": "photo", "caption": "Подпись под фото"}
    media_meta = {"description": "Пейзаж", "tags": "nature"}
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: Пейзаж. Теги: nature] Подпись под фото"

def test_format_post_text_photo_fallback_when_untagged():
    content = {"type": "photo"}
    res = _format_post_text(content, "photo", media_meta=None)
    assert res == "[photo]"

def test_format_post_text_caption_fallback_when_untagged():
    content = {"type": "photo", "caption": "Подпись"}
    res = _format_post_text(content, "photo", media_meta=None)
    assert res == "Подпись"

def test_format_post_text_html_stripping():
    content = {"type": "text", "text": "<b>Жирный текст</b> и <a href='https://example.com'>ссылка</a>"}
    res = _format_post_text(content, "text", media_meta=None)
    assert res == "Жирный текст и ссылка"

def test_format_post_text_other_media_fallbacks():
    for mtype in ('video', 'document', 'animation', 'media_group', 'sticker', 'voice', 'video_note'):
        content = {"type": mtype}
        res = _format_post_text(content, mtype, media_meta=None)
        assert res == f"[{mtype}]"

def test_format_post_text_empty_post():
    content = {"type": "text", "text": ""}
    assert _format_post_text(content, "text", media_meta=None) is None
    assert _format_post_text({}, "unknown", media_meta=None) is None
