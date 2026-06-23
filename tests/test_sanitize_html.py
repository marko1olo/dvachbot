import pytest
from Dubsite_tgach.main import sanitize_html as dubsite_sanitize_html
from site_tgach.main import sanitize_html as site_sanitize_html

@pytest.mark.parametrize("sanitize_html", [dubsite_sanitize_html, site_sanitize_html])
def test_sanitize_html_empty_string(sanitize_html):
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""

@pytest.mark.parametrize("sanitize_html", [dubsite_sanitize_html, site_sanitize_html])
def test_sanitize_html_basic_escape(sanitize_html):
    assert sanitize_html("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"
    assert sanitize_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

@pytest.mark.parametrize("sanitize_html", [dubsite_sanitize_html, site_sanitize_html])
def test_sanitize_html_quotes_preserved(sanitize_html):
    assert sanitize_html('"double quotes"') == '"double quotes"'
    assert sanitize_html("'single quotes'") == "'single quotes'"

@pytest.mark.parametrize("sanitize_html", [dubsite_sanitize_html, site_sanitize_html])
def test_sanitize_html_ampersand(sanitize_html):
    assert sanitize_html("a & b") == "a &amp; b"

@pytest.mark.parametrize("sanitize_html", [dubsite_sanitize_html, site_sanitize_html])
def test_sanitize_html_mixed(sanitize_html):
    assert sanitize_html('<a href="test">link & "text"</a>') == '&lt;a href="test"&gt;link &amp; "text"&lt;/a&gt;'
