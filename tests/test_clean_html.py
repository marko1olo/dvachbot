import pytest
from main import clean_html_for_tg

def test_clean_html_for_tg_basic():
    assert clean_html_for_tg("") == ""
    assert clean_html_for_tg(None) == ""
    assert clean_html_for_tg("**bold**") == "<b>bold</b>"
    assert clean_html_for_tg("*italic*") == "<i>italic</i>"
    assert clean_html_for_tg("`code`") == "<code>code</code>"
    assert clean_html_for_tg("hello **world**") == "hello <b>world</b>"
    assert clean_html_for_tg("no ** unclosed bold") == "no ** unclosed bold"
    assert clean_html_for_tg("hello *world*") == "hello <i>world</i>"
    assert clean_html_for_tg("not * italic") == "not * italic"
    assert clean_html_for_tg("**bold *italic***") == "<b>bold <i>italic</i></b>"
    assert clean_html_for_tg("hello `world`") == "hello <code>world</code>"
    assert clean_html_for_tg("hello **bold** and *italic* and `code`") == "hello <b>bold</b> and <i>italic</i> and <code>code</code>"

def test_clean_html_for_tg_unwrap_emoji():
    assert clean_html_for_tg('<tg-emoji emoji-id="123">👍</tg-emoji>') == "👍"
    assert clean_html_for_tg('<tg-emoji emoji-id="5222250679371839695">🇺🇦</tg-emoji>Сырский') == '🇺🇦Сырский'
    assert clean_html_for_tg('генерации мемов <tg-emoji emoji-id="5417906561626430968">😄</tg-emoji>') == 'генерации мемов 😄'

def test_clean_html_for_tg_br_to_newline():
    assert clean_html_for_tg("hello<br>world") == "hello\nworld"
    assert clean_html_for_tg("hello<br/>world") == "hello\nworld"
    assert clean_html_for_tg("hello<br />world") == "hello\nworld"

def test_clean_html_for_tg_layout_tags_to_newline():
    assert clean_html_for_tg("<p>hello</p><p>world</p>") == "hello\n\nworld"
    assert clean_html_for_tg("<h1>hello</h1> **world**") == "hello\n <b>world</b>"
    assert clean_html_for_tg("first<hr>second") == "first\nsecond"
    assert clean_html_for_tg("<ul><li>one</li><li>two</li></ul>") == "one\n\ntwo"
    assert clean_html_for_tg("<div>block</div>") == "block"

def test_clean_html_for_tg_strip_unallowed_tags():
    assert clean_html_for_tg("hello <script>world</script>") == "hello world"
    assert clean_html_for_tg("hello <unknown>world") == "hello world"
    assert clean_html_for_tg("<blink>test</blink>") == "test"
    assert clean_html_for_tg("<form>input</form>") == "input"

def test_clean_html_for_tg_balanced_tags():
    assert clean_html_for_tg("hello <b>world</b>") == "hello <b>world</b>"
    assert clean_html_for_tg("<b><i>test</i></b>") == "<b><i>test</i></b>"
    assert clean_html_for_tg("<a href='test'>link</a>") == "<a href='test'>link</a>"

def test_clean_html_for_tg_unclosed_tags():
    assert clean_html_for_tg("hello <b>world") == "hello <b>world</b>"
    assert clean_html_for_tg("hello <b><i>world</b>") == "hello <b><i>world</i></b>"

def test_clean_html_for_tg_stray_closing_tags():
    assert clean_html_for_tg("hello <b>world</i>") == "hello <b>world</b>"
    assert clean_html_for_tg("hello </b>world") == "hello world"

def test_clean_html_for_tg_collapse_newlines():
    assert clean_html_for_tg("line1\n\n\nline2") == "line1\n\nline2"
    assert clean_html_for_tg("line1\n\n\n\n\nline2") == "line1\n\nline2"
