import pytest
from site_tgach.main import sanitize_header_filename

def test_sanitize_header_filename():
    assert sanitize_header_filename(None) == "file"
    assert sanitize_header_filename("") == "file"
    assert sanitize_header_filename("simple.jpg") == "simple.jpg"
    assert sanitize_header_filename('image"name\r\n.png') == "imagename.png"
    assert sanitize_header_filename("\x00test.txt\x7f") == "test.txt"
    assert sanitize_header_filename("   padded.gif   ") == "padded.gif"
