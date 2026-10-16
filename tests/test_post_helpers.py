import pytest
from post_helpers import check_post_numerals

def test_check_post_numerals():
    # Test boundary condition where length is less than 4 (should return None)
    assert check_post_numerals(1) is None
    assert check_post_numerals(12) is None
    assert check_post_numerals(123) is None

    # Test cases where length is >= 4, but repetition is less than minimum special key (4)
    assert check_post_numerals(1234) is None
    assert check_post_numerals(1122) is None
    assert check_post_numerals(1112) is None
    assert check_post_numerals(1222) is None

    # Test valid special numerals keys from shared_state.SPECIAL_NUMERALS_CONFIG (4 to 8)
    # Testing EXACT matches of trailing repeating digits
    assert check_post_numerals(1111) == 4
    assert check_post_numerals(21111) == 4
    assert check_post_numerals(91111) == 4

    assert check_post_numerals(11111) == 5
    assert check_post_numerals(211111) == 5

    assert check_post_numerals(111111) == 6
    assert check_post_numerals(2111111) == 6

    assert check_post_numerals(1111111) == 7
    assert check_post_numerals(21111111) == 7

    assert check_post_numerals(11111111) == 8
    assert check_post_numerals(211111111) == 8

    # Test a repetition beyond the maximum config key (9). The config currently stops at 8.
    # It will return None because 9 is not in SPECIAL_NUMERALS_CONFIG.
    assert check_post_numerals(111111111) is None

    # Test numbers ending in zero
    assert check_post_numerals(10000) == 4
    assert check_post_numerals(200000) == 5

    # Edge cases - extremely large numbers
    # A huge repetition matching up to 8 (because > 8 not in config)
    assert check_post_numerals(9999999999999999923333) == 4
