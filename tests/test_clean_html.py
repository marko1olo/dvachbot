import pytest
from main import clean_html_for_tg

def test_clean_html_for_tg_basic():
    assert clean_html_for_tg("") == ""
    assert clean_html_for_tg("**bold**") == "<b>bold</b>"
    assert clean_html_for_tg("*italic*") == "<i>italic</i>"
    assert clean_html_for_tg("`code`") == "<code>code</code>"

def test_clean_html_for_tg_unwrap_emoji():
    assert clean_html_for_tg('<tg-emoji emoji-id="123">👍</tg-emoji>') == "👍"
