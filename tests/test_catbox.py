import pytest
from Dubsite_tgach.catbox import _read_upload_file

def test_read_upload_file_success(tmp_path):
    """Test reading a valid file returns name and content."""
    test_file = tmp_path / "test_image.png"
    test_content = b"fake image content"
    test_file.write_bytes(test_content)

    file_source = str(test_file)
    name, content = _read_upload_file(file_source)

    assert name == "test_image.png"
    assert content == test_content

def test_read_upload_file_not_found():
    """Test reading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        _read_upload_file("non_existent_file.jpg")
