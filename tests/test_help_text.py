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


def test_economy_help_pages_exist():
    import help_text
    expected_keys = ["economy", "work", "shop", "casino", "duel", "dice_duel", "cases", "lootbox"]
    for k in expected_keys:
        assert k in help_text.HELP_HUB_PAGES_RU, f"Missing RU help page for {k}"
        assert k in help_text.HELP_HUB_PAGES_EN, f"Missing EN help page for {k}"
        assert k in help_text.HELP_HUB_PAGES_JP, f"Missing JP help page for {k}"


def test_work_help_invariants():
    import help_text
    for page_key in ["work", "economy"]:
        text_ru = help_text.HELP_HUB_PAGES_RU[page_key]
        assert "1-3" in text_ru and "100%" in text_ru
        assert "4-6" in text_ru and "80%" in text_ru
        assert "7-10" in text_ru and "55%" in text_ru
        assert "11-15" in text_ru and "35%" in text_ru
        assert "16+" in text_ru and "20%" in text_ru
        assert "45,000" in text_ru
        assert "2.25x" in text_ru

        text_en = help_text.HELP_HUB_PAGES_EN[page_key]
        assert "1-3" in text_en and "100%" in text_en
        assert "4-6" in text_en and "80%" in text_en
        assert "7-10" in text_en and "55%" in text_en
        assert "11-15" in text_en and "35%" in text_en
        assert "16+" in text_en and "20%" in text_en
        assert "45,000" in text_en
        assert "2.25x" in text_en


def test_shop_help_invariants():
    import help_text
    for page_key in ["shop", "economy"]:
        text_ru = help_text.HELP_HUB_PAGES_RU[page_key]
        assert "таблетки" in text_ru.lower()
        assert "шапочки" in text_ru.lower() or "фольги" in text_ru.lower()
        assert "заточки" in text_ru.lower()
        assert "0%" in text_ru
        assert "10,000" in text_ru
        assert "пативэн" in text_ru.lower()
        assert "мут" in text_ru.lower()
        assert "дворник" in text_ru.lower()
        assert "огнетушитель" in text_ru.lower()
        assert "+300%" in text_ru
        assert "4x" in text_ru
        assert "1M" in text_ru or "1 000 000" in text_ru or "1,000,000" in text_ru

        text_en = help_text.HELP_HUB_PAGES_EN[page_key]
        assert "0%" in text_en
        assert "10,000" in text_en
        assert "+300%" in text_en
        assert "4x" in text_en


def test_casino_help_invariants():
    import help_text
    for page_key in ["casino", "economy"]:
        text_ru = help_text.HELP_HUB_PAGES_RU[page_key]
        assert "500" in text_ru
        assert "75,000" in text_ru
        assert "10%" in text_ru
        assert "10k" in text_ru or "10 000" in text_ru or "10,000" in text_ru
        assert "4x" in text_ru
        assert "яхты абу" in text_ru.lower()
        assert "1.5" in text_ru

        text_en = help_text.HELP_HUB_PAGES_EN[page_key]
        assert "500" in text_en
        assert "75,000" in text_en
        assert "10%" in text_en
        assert "1.5" in text_en


def test_duel_help_invariants():
    import help_text
    for page_key in ["duel", "economy"]:
        text_ru = help_text.HELP_HUB_PAGES_RU[page_key]
        assert "5%" in text_ru
        assert "95%" in text_ru
        assert "0%" in text_ru
        assert "50" in text_ru
        assert "50,000" in text_ru
        assert "50%" in text_ru
        assert "30" in text_ru

        text_en = help_text.HELP_HUB_PAGES_EN[page_key]
        assert "5%" in text_en
        assert "95%" in text_en
        assert "0%" in text_en
        assert "50,000" in text_en
        assert "30" in text_en


def test_cases_help_invariants():
    import help_text
    for page_key in ["cases", "economy"]:
        text_ru = help_text.HELP_HUB_PAGES_RU[page_key]
        assert "10" in text_ru
        assert "11" in text_ru
        assert "40%" in text_ru
        assert "60%" in text_ru

        text_en = help_text.HELP_HUB_PAGES_EN[page_key]
        assert "10" in text_en
        assert "11" in text_en
        assert "40%" in text_en
        assert "60%" in text_en


def test_get_help_hub_page_all_categories():
    from help_text import get_help_hub_page
    for cat in ["economy", "work", "shop", "casino", "duel", "dice_duel", "cases", "lootbox"]:
        for lang in ['ru', 'en', 'jp']:
            content = get_help_hub_page(cat, lang=lang)
            assert isinstance(content, str)
            assert len(content) > 50
            # Ensure HTML tags are balanced
            for tag in ["b", "i", "code", "pre", "a"]:
                open_c = content.count(f"<{tag}>") + content.count(f"<{tag} ")
                close_c = content.count(f"</{tag}>")
                assert open_c == close_c, f"Tag {tag} unbalanced in {cat} ({lang})"



def test_no_help_page_truncated():
    import help_text
    all_dicts = [
        ("RU", help_text.HELP_HUB_PAGES_RU),
        ("EN", help_text.HELP_HUB_PAGES_EN),
        ("JP", help_text.HELP_HUB_PAGES_JP),
    ]
    for lang, pages in all_dicts:
        for cat, text in pages.items():
            assert "[Текст сокращен]" not in text, f"{lang}:{cat} contains '[Текст сокращен]'"
            assert "[Текст сокращён]" not in text, f"{lang}:{cat} contains '[Текст сокращён]'"
            assert "Текст сокращен" not in text, f"{lang}:{cat} contains 'Текст сокращен'"
            assert len(text) <= 4096, f"{lang}:{cat} exceeds 4096 chars ({len(text)})"


def test_main_help_page_length():
    import help_text
    for lang, pages in [("RU", help_text.HELP_HUB_PAGES_RU), ("EN", help_text.HELP_HUB_PAGES_EN), ("JP", help_text.HELP_HUB_PAGES_JP)]:
        assert len(pages["main"]) <= 1000, f"{lang} main page too long: {len(pages['main'])}"


def test_all_23_help_categories_exist():
    import help_text
    expected_23 = [
        "main", "chat", "economy", "media", "ai", "modes", "actions", "settings", "all", "boards",
        "work", "shop", "casino", "duel", "dice_duel", "cases", "lootbox",
        "crime", "darknet", "loan", "loans", "heist", "heists"
    ]
    for cat in expected_23:
        for lang in ['ru', 'en', 'jp']:
            content = help_text.get_help_hub_page(cat, lang=lang)
            assert isinstance(content, str)
            assert len(content) > 50, f"Page {cat} ({lang}) too short"
            assert "[Текст сокращен]" not in content


@pytest.mark.asyncio
async def test_banner_manager_help_no_truncation():
    from unittest.mock import AsyncMock, MagicMock
    from banner_manager import send_banner_message
    from aiogram import Bot, types

    mock_bot = AsyncMock(spec=Bot)
    mock_bot.id = 99999
    photo_msg = MagicMock(spec=types.Message)
    photo_msg.message_id = 123
    mock_photo = MagicMock()
    mock_photo.file_id = "test_file_id"
    photo_msg.photo = [mock_photo]
    photo_msg.video = None
    photo_msg.animation = None
    mock_bot.send_photo.return_value = photo_msg

    text_msg = MagicMock(spec=types.Message)
    text_msg.message_id = 124
    mock_bot.send_message.return_value = text_msg

    long_caption = "<b>Detailed Help</b>\n" + ("Text " * 300)
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])

    with patch("banner_manager.get_banner_file", return_value=("test.jpg", "file_id_123")):
        res = await send_banner_message(
            bot=mock_bot,
            chat_id=12345,
            caption=long_caption,
            reply_markup=kb,
            category="help",
            parse_mode="HTML"
        )
        assert res is not None
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "[Текст сокращен]" not in sent_text
        assert "[Текст сокращён]" not in sent_text
        assert len(sent_text) == len(long_caption)
