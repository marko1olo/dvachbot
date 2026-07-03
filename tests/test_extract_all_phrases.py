import pytest
import os
import tempfile
from extract_all_phrases import extract_strings_from_file

def create_temp_file(content):
    """Helper to create a temporary file with given content."""
    fd, path = tempfile.mkstemp(suffix='.py')
    with open(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def test_file_not_found():
    """Test extracting strings from a non-existent file."""
    assert extract_strings_from_file("non_existent_file.py") == []

def test_syntax_error():
    """Test extracting strings from a file with invalid Python syntax."""
    content = "def invalid_syntax(:\n    pass"
    path = create_temp_file(content)
    try:
        assert extract_strings_from_file(path) == []
    finally:
        os.remove(path)

def test_no_target_methods():
    """Test when there are no target function calls."""
    content = "print('Привет')"
    path = create_temp_file(content)
    try:
        assert extract_strings_from_file(path) == []
    finally:
        os.remove(path)

def test_no_strings_in_target_method():
    """Test target methods that don't contain string arguments."""
    content = "send_message(user_id, 123)"
    path = create_temp_file(content)
    try:
        assert extract_strings_from_file(path) == []
    finally:
        os.remove(path)

def test_non_cyrillic_strings():
    """Test that non-Cyrillic strings are ignored."""
    content = "send_message('Hello World')"
    path = create_temp_file(content)
    try:
        assert extract_strings_from_file(path) == []
    finally:
        os.remove(path)

def test_cyrillic_strings_positional():
    """Test finding Cyrillic strings in positional arguments."""
    content = "send_message('Привет мир')\nreply('Как дела?')"
    path = create_temp_file(content)
    try:
        result = extract_strings_from_file(path)
        assert len(result) == 2
        assert result[0]['text'] == 'Привет мир'
        assert result[0]['line'] == 1
        assert result[0]['file'] == path

        assert result[1]['text'] == 'Как дела?'
        assert result[1]['line'] == 2
        assert result[1]['file'] == path
    finally:
        os.remove(path)

def test_cyrillic_strings_attribute():
    """Test finding Cyrillic strings in attribute calls (e.g., bot.send_message)."""
    content = "bot.send_message(chat_id, 'Тестовое сообщение')"
    path = create_temp_file(content)
    try:
        result = extract_strings_from_file(path)
        assert len(result) == 1
        assert result[0]['text'] == 'Тестовое сообщение'
        assert result[0]['line'] == 1
        assert result[0]['file'] == path
    finally:
        os.remove(path)

def test_cyrillic_strings_keyword():
    """Test finding Cyrillic strings in the 'text' keyword argument."""
    content = "send_message(chat_id=123, text='Сообщение по ключу')"
    path = create_temp_file(content)
    try:
        result = extract_strings_from_file(path)
        assert len(result) == 1
        assert result[0]['text'] == 'Сообщение по ключу'
        assert result[0]['line'] == 1
        assert result[0]['file'] == path
    finally:
        os.remove(path)

def test_non_text_keyword_ignored():
    """Test that Cyrillic strings in other keyword arguments are ignored."""
    content = "send_message(chat_id=123, caption='Описание')"
    path = create_temp_file(content)
    try:
        result = extract_strings_from_file(path)
        assert result == []
    finally:
        os.remove(path)
