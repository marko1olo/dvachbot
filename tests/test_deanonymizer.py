import pytest
from unittest.mock import patch
from deanonymizer import generate_deanon_info

def test_generate_deanon_info_en():
    """Test generating English deanonymization info."""
    result = generate_deanon_info(lang='en')
    assert isinstance(result, str)
    assert "[DEANONYMIZATION REPORT]" in result
    assert len(result) > 0

@pytest.mark.parametrize("style", [
    'standard', 'fsb', 'ukrainian', 'chechen', 'official', 'schizo',
    'news', 'old_school_hacker', 'psych_eval', 'hitman', 'dating_app',
    'housing_report', 'cultist'
])
def test_generate_deanon_info_ru_all_styles(style):
    """Test generating Russian (default) deanonymization info for all possible styles."""
    with patch('deanonymizer.random.choice', return_value=style):
        result = generate_deanon_info(lang='ru')
        assert isinstance(result, str)
        assert len(result) > 0

def test_generate_deanon_info_default():
    """Test generating default (Russian) deanonymization info."""
    result = generate_deanon_info()
    assert isinstance(result, str)
    assert len(result) > 0
