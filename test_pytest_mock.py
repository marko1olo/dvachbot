import pytest

@pytest.fixture(autouse=True)
def mock_all_the_things():
    pass
    # The error message says: TypeError: object MagicMock can't be used in 'await' expression
    # Meaning `generate_rss` was replaced by a MagicMock instead of an AsyncMock!
