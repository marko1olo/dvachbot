import pytest
from extract_all_phrases import extract_strings_from_file

def test_extract_strings_success(tmp_path):
    # Test typical success case extracting Cyrillic strings from target methods
    test_file = tmp_path / "test_success.py"
    test_file.write_text("""
def my_func():
    send_message('Привет мир!')
    reply("Как дела?")
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 2

    assert phrases[0]['text'] == 'Привет мир!'
    assert phrases[0]['file'] == str(test_file)
    assert phrases[0]['line'] == 3

    assert phrases[1]['text'] == 'Как дела?'
    assert phrases[1]['file'] == str(test_file)
    assert phrases[1]['line'] == 4

def test_extract_strings_kwargs(tmp_path):
    # Test extracting strings passed as keyword argument 'text'
    test_file = tmp_path / "test_kwargs.py"
    test_file.write_text("""
def my_func():
    send_message(text='Это тестовое сообщение')
    reply(chat_id=123, text='Другое сообщение')
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 2

    assert phrases[0]['text'] == 'Это тестовое сообщение'
    assert phrases[0]['line'] == 3
    assert phrases[1]['text'] == 'Другое сообщение'
    assert phrases[1]['line'] == 4

def test_extract_strings_non_target_methods(tmp_path):
    # Ensure it ignores strings from non-target methods or variables
    test_file = tmp_path / "test_non_target.py"
    test_file.write_text("""
print("Не должно извлекаться")
my_var = "Тоже не должно"
custom_method("И это тоже")
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 0

def test_extract_strings_invalid_syntax(tmp_path):
    # Syntax error in file should return an empty list gracefully
    test_file = tmp_path / "test_invalid.py"
    test_file.write_text("""
def func():
    if True
        print('missing colon')
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 0

def test_extract_strings_file_not_found():
    # File not found should be handled and return empty list
    phrases = extract_strings_from_file("non_existent_file.py")
    assert len(phrases) == 0

def test_extract_strings_attribute_call(tmp_path):
    # Ensure attribute method calls (like bot.send_message) are extracted
    test_file = tmp_path / "test_attr_call.py"
    test_file.write_text("""
def send_to_user(bot):
    bot.send_message(chat_id=123, text='Здравствуйте')
    client.reply_photo(photo='url', caption='ignored', text='Фото')
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 2

    assert phrases[0]['text'] == 'Здравствуйте'
    assert phrases[0]['line'] == 3

    assert phrases[1]['text'] == 'Фото'
    assert phrases[1]['line'] == 4

def test_extract_strings_non_cyrillic(tmp_path):
    # Only cyrillic strings should be extracted
    test_file = tmp_path / "test_non_cyrillic.py"
    test_file.write_text("""
def func():
    send_message("Hello world")
    reply(text="How are you?")
    answer("Привет")
    """, encoding="utf-8")

    phrases = extract_strings_from_file(str(test_file))
    assert len(phrases) == 1
    assert phrases[0]['text'] == 'Привет'
