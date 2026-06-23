import pytest
from Dubsite_tgach.image_processing import encode_83

def test_encode_83_zero():
    assert encode_83(0, 1) == "0"
    assert encode_83(0, 2) == "00"
    assert encode_83(0, 3) == "000"

def test_encode_83_max_single_char():
    assert encode_83(82, 1) == "~"

def test_encode_83_multi_char():
    assert encode_83(83, 2) == "10"
    assert encode_83(83 * 2, 2) == "20"
    assert encode_83(83 * 83 - 1, 2) == "~~"

def test_encode_83_mixed():
    # Value 84 should be 1 * 83^1 + 1 * 83^0, which is "11"
    assert encode_83(84, 2) == "11"
    # Value 1 * 83^2 + 2 * 83^1 + 3 * 83^0 = 6889 + 166 + 3 = 7058 -> "123"
    assert encode_83(7058, 3) == "123"

def test_encode_83_padding():
    # Length 3, but value fits in 1 char
    assert encode_83(1, 3) == "001"
    assert encode_83(82, 3) == "00~"
