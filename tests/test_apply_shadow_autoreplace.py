import pytest
from post_helpers import apply_shadow_autoreplace

def test_apply_shadow_autoreplace_empty():
    """Test handling of empty and None inputs."""
    assert apply_shadow_autoreplace({}) == {}
    assert apply_shadow_autoreplace(None) == None

def test_apply_shadow_autoreplace_no_text():
    """Test handling of dicts without 'text' or 'caption' keys."""
    content = {'image': 'foo.jpg', 'video': 'bar.mp4'}
    assert apply_shadow_autoreplace(content) == content

def test_apply_shadow_autoreplace_shadow_words():
    """Test replacement of shadow words (e.g. кал)."""
    content = {'text': 'кал'}
    result = apply_shadow_autoreplace(content)
    assert result['text'] != 'кал'

def test_apply_shadow_autoreplace_die_words():
    """Test replacement of 'die' words (e.g. сдохни)."""
    # Test singular/without 'те'
    content = {'text': 'сдохни'}
    result = apply_shadow_autoreplace(content)
    assert result['text'] == 'обоссы меня'

    # Test plural/with 'те'
    content = {'text': 'сдохните'}
    result = apply_shadow_autoreplace(content)
    assert result['text'] == 'обоссыте меня'

def test_apply_shadow_autoreplace_political():
    """Test replacement of political words (e.g. хохол)."""
    content = {'text': 'хохол'}
    result = apply_shadow_autoreplace(content)
    assert result['text'] == 'великий укр'

def test_apply_shadow_autoreplace_word_limit_exceeded():
    """Test that no replacement occurs if the text has more than 12 words."""
    long_text = ' '.join(['word'] * 13) + ' кал сдохни хохол'
    content = {'text': long_text}
    result = apply_shadow_autoreplace(content)
    assert result['text'] == long_text

def test_apply_shadow_autoreplace_word_limit_exact():
    """Test that replacement occurs if the text has exactly 12 words."""
    short_text = ' '.join(['word'] * 9) + ' кал сдохни хохол'
    content = {'text': short_text}
    result = apply_shadow_autoreplace(content)
    assert result['text'] != short_text
    assert 'кал' not in result['text']
    assert 'сдохни' not in result['text']
    assert 'хохол' not in result['text']

def test_apply_shadow_autoreplace_caption():
    """Test that replacement works on the 'caption' field as well."""
    content = {'caption': 'хохол'}
    result = apply_shadow_autoreplace(content)
    assert result['caption'] == 'великий укр'
