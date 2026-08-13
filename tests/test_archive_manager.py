import pytest
from archive_manager import _build_archive_header

def test_build_archive_header():
    # 1. No match, fallback to raw_header
    content = {'header': 'Some random string'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | Some random string'

    # 2. Match without letters in prefix
    content = {'header': '123 Пост №123'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '123 <b>/b/</b> | Пост №123'

    # 3. Match with letters in prefix and replies
    content = {'header': 'Prefix Пост №123', 'reply_to_post': '456'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | Пост №123 (ответ на №456)\n\n<b>Prefix :</b>'

    # 4. English language
    content = {'header': 'Prefix Пост №123', 'reply_to_post': '456'}
    res = _build_archive_header('b', 123, content, 'en')
    assert res == '<b>/b/</b> | Пост №123 (reply to №456)\n\n<b>Prefix :</b>'

    # 5. Empty header, uses post_num
    content = {}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | Пост №123'

    # 6. Prefix ending with -
    content = {'header': 'Anon- Пост №123'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | Пост №123\n\n<b>Anon :</b>'

    # 7. Post No.
    content = {'header': 'Anon- Post No.123'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | Post No.123\n\n<b>Anon :</b>'

    # 8. レス番
    content = {'header': 'Anon- レス番 123'}
    res = _build_archive_header('b', 123, content, 'ru')
    assert res == '<b>/b/</b> | レス番 123\n\n<b>Anon :</b>'
