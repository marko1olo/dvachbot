import pytest
from unittest.mock import patch
from help_text import (
    generate_boards_list,
    BOARD_LIST_HEADERS_RU,
    BOARD_LIST_HEADERS_EN,
    BOARD_LIST_HEADERS_JP,
)

@pytest.fixture
def board_configs():
    return {
        'test': {
            'name': '/test/',
            'username': '@test_board',
            'description': 'Test board should be skipped'
        },
        'b': {
            'name': '/b/',
            'username': '@b_board',
            'description': {
                'ru': 'Бред',
                'en': 'Random',
                'jp': 'ランダム'
            }
        },
        'a': {
            'name': '/a/',
            'username': '@a_board',
            'description': 'Anime'
        },
        'c': {
            'name': '/c/',
            'username': '@c_board',
            'description': {
                'ru': 'Только русский',
                'fr': 'Seulement russe' # no en, no jp
            }
        },
        'd': {
            'name': '/d/',
            'username': '@d_board',
            'description': {
                'jp': 'アニメ',
                'en': 'English Fallback'
            }
        },
        'e': {
            'name': '/e/',
            'username': '@e_board',
            'description': None
        }
    }

def test_generate_boards_list_ru(board_configs):
    with patch('random.choice', side_effect=lambda x: x[0]):
        result = generate_boards_list(board_configs, lang='ru')

    assert BOARD_LIST_HEADERS_RU[0] in result
    assert "<b>/b/</b> Бред - @b_board" in result
    assert "<b>/a/</b> Anime - @a_board" in result
    assert "<b>/c/</b> Только русский - @c_board" in result
    assert "<b>/d/</b> English Fallback - @d_board" in result
    assert "<b>/e/</b>  - @e_board" in result
    assert "/test/" not in result

def test_generate_boards_list_en(board_configs):
    with patch('random.choice', side_effect=lambda x: x[0]):
        result = generate_boards_list(board_configs, lang='en')

    assert BOARD_LIST_HEADERS_EN[0] in result
    assert "<b>/b/</b> Random - @b_board" in result
    assert "<b>/c/</b> Только русский - @c_board" in result  # First available if no en
    assert "<b>/d/</b> English Fallback - @d_board" in result

def test_generate_boards_list_jp(board_configs):
    with patch('random.choice', side_effect=lambda x: x[0]):
        result = generate_boards_list(board_configs, lang='jp')

    assert BOARD_LIST_HEADERS_JP[0] in result
    assert "<b>/b/</b> ランダム - @b_board" in result
    assert "<b>/d/</b> アニメ - @d_board" in result
    assert "<b>/c/</b> Только русский - @c_board" in result  # First available if no jp and no en

def test_string_constants_types():
    from help_text import (
        HELP_TEXT_COMMANDS,
        HELP_TEXT_EN_COMMANDS,
        HELP_TEXT_JP_COMMANDS,
        BOARD_LIST_HEADERS_RU,
        BOARD_LIST_HEADERS_EN,
        BOARD_LIST_HEADERS_JP,
        THREAD_PROMO_TEXT_RU,
        THREAD_PROMO_TEXT_EN,
        THREAD_PROMO_TEXT_JP,
        MODE_INFO_TEXT_RU,
        MODE_INFO_TEXT_EN,
        MODE_INFO_TEXT_JP,
        CHANNEL_PROMO_TEXT_RU,
        CHANNEL_PROMO_TEXT_EN,
        CHANNEL_PROMO_TEXT_JP,
        MECHANICS_INFO_TEXT_RU,
        MECHANICS_INFO_TEXT_EN,
        MECHANICS_INFO_TEXT_JP
    )

    lists_to_check = [
        HELP_TEXT_COMMANDS,
        HELP_TEXT_EN_COMMANDS,
        HELP_TEXT_JP_COMMANDS,
        BOARD_LIST_HEADERS_RU,
        BOARD_LIST_HEADERS_EN,
        BOARD_LIST_HEADERS_JP,
        THREAD_PROMO_TEXT_RU,
        THREAD_PROMO_TEXT_EN,
        THREAD_PROMO_TEXT_JP,
        MODE_INFO_TEXT_RU,
        MODE_INFO_TEXT_EN,
        MODE_INFO_TEXT_JP,
        CHANNEL_PROMO_TEXT_RU,
        CHANNEL_PROMO_TEXT_EN,
        CHANNEL_PROMO_TEXT_JP,
        MECHANICS_INFO_TEXT_RU,
        MECHANICS_INFO_TEXT_EN,
        MECHANICS_INFO_TEXT_JP
    ]

    for string_list in lists_to_check:
        assert isinstance(string_list, list)
        assert len(string_list) > 0
        for item in string_list:
            assert isinstance(item, str)
            assert len(item) > 0

def test_specific_constants_content():
    from help_text import (
        HELP_TEXT_COMMANDS,
        BOARD_LIST_HEADERS_RU
    )

    # Check that SOME essential keywords are in the Russian help text
    assert "/start" in HELP_TEXT_COMMANDS[0]
    assert "/help" in HELP_TEXT_COMMANDS[0]
    assert "ТГАЧ" in HELP_TEXT_COMMANDS[0]

    # Check board headers
    assert any("доск" in header.lower() for header in BOARD_LIST_HEADERS_RU)
