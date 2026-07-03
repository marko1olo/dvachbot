import pytest
from unittest.mock import patch
import Dubsite_tgach.security as dubsite_security
import site_tgach.security as site_security

@pytest.mark.parametrize("security_module", [
    dubsite_security,
    site_security
])
def test_get_pow_challenge_data_default(security_module):
    with patch.object(security_module, 'generate_challenge_str', return_value="mocked_challenge"):
        result = security_module.get_pow_challenge_data()
        assert result == {
            "challenge": "mocked_challenge",
            "difficulty": security_module.DEFAULT_POW_DIFFICULTY
        }

@pytest.mark.parametrize("security_module", [
    dubsite_security,
    site_security
])
def test_get_pow_challenge_data_custom_difficulty(security_module):
    with patch.object(security_module, 'generate_challenge_str', return_value="mocked_challenge_2"):
        result = security_module.get_pow_challenge_data(10)
        assert result == {
            "challenge": "mocked_challenge_2",
            "difficulty": 10
        }
