# -*- coding: utf-8 -*-
import pytest
from post_helpers import _format_post_text, _format_media_context

def test_format_post_text_with_description_and_tags():
    content = {"type": "photo", "text": "Зацените пикчу"}
    media_meta = {
        "description": "На изображении представлена Зеро Ту в красном мундире",
        "tags": "1girl, zero_two, anime, pink_hair"
    }
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: На изображении представлена Зеро Ту в красном мундире. Теги: 1girl, zero_two, anime, pink_hair] Зацените пикчу"

def test_format_post_text_photo_only_no_text():
    content = {"type": "photo"}
    media_meta = {
        "description": "Портрет черного кота",
        "tags": "cat, black_cat, meme"
    }
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: Портрет черного кота. Теги: cat, black_cat, meme]"

def test_format_post_text_tags_only():
    content = {"type": "photo"}
    media_meta = {
        "description": "",
        "tags": "landscape, mountains, sunset"
    }
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: landscape, mountains, sunset]"

def test_format_post_text_untagged_fallback():
    content = {"type": "photo"}
    res = _format_post_text(content, "photo", media_meta=None)
    assert res == "[photo]"

def test_format_post_text_caption_untagged():
    content = {"type": "photo", "caption": "Просто текст подписи"}
    res = _format_post_text(content, "photo", media_meta=None)
    assert res == "Просто текст подписи"

def test_format_post_text_error_tags_sanitization():
    content = {"type": "photo"}
    media_meta = {
        "description": "error",
        "tags": "download_failed, dead, format_unsupported, no_tags"
    }
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[photo]"

def test_format_post_text_partial_error_tags():
    content = {"type": "photo", "text": "Пост"}
    media_meta = {
        "description": "Красивый кот",
        "tags": "error, 1cat, download_failed, cute"
    }
    res = _format_post_text(content, "photo", media_meta=media_meta)
    assert res == "[Фото: Красивый кот. Теги: 1cat, cute] Пост"

def test_format_post_text_truncation():
    long_desc = "X" * 200
    long_tags = ", ".join([f"tag_{i}" for i in range(30)])
    media_meta = {
        "description": long_desc,
        "tags": long_tags
    }
    res = _format_post_text({"type": "photo"}, "photo", media_meta=media_meta)
    assert "..." in res
    assert len(res) <= 260

