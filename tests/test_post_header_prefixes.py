import random
import re
from unittest.mock import patch
import pytest

from post_helpers import _get_random_header_prefix, format_header


def test_get_random_header_prefix_aryan():
    """Verify that 'Ариец - ' prefix is returned in range [0.168, 0.170) and empty string for >= 0.170."""
    test_cases = [
        (0.167, "Свиноёб - "),
        (0.168, "Ариец - "),
        (0.169, "Ариец - "),
        (0.16999, "Ариец - "),
        (0.170, ""),
        (0.250, ""),
        (0.800, ""),
    ]

    for rand_val, expected in test_cases:
        with patch("random.random", return_value=rand_val):
            actual = _get_random_header_prefix(lang='ru')
            assert actual == expected, f"At {rand_val}: expected '{expected}', got '{actual}'"


def test_get_random_header_prefix_distribution_monte_carlo():
    """Verify calibrated probability is ~17% (up to 0.170) and 'Ариец - ' drops under Monte Carlo."""
    rng = random.Random(42)
    trials = 20000
    counts = {}

    with patch("random.random", side_effect=lambda: rng.random()):
        for _ in range(trials):
            prefix = _get_random_header_prefix(lang='ru')
            counts[prefix] = counts.get(prefix, 0) + 1

    total_with_prefix = sum(cnt for pfx, cnt in counts.items() if pfx != "")
    prefix_rate = total_with_prefix / trials

    # Expected threshold is 0.170 (17.0%). Monte Carlo over 20,000 trials should stay within [15.5%, 18.5%]
    assert 0.155 <= prefix_rate <= 0.185, f"Prefix rate {prefix_rate:.4f} outside of expected range 15.5-18.5%"

    assert "Ариец - " in counts, "Prefix 'Ариец - ' was never generated"
    assert counts["Ариец - "] > 0


def test_main_prefixes_shop_list():
    """Verify that main.py prefix shop list contains '[Ариец]' and slice indices are 13."""
    with open("main.py", "r", encoding="utf-8") as f:
        main_content = f.read()

    match = re.search(r'prefixes = \[\s*([\s\S]*?)\]\s*chosen = random\.choice\(prefixes\[:(\d+)\]\) if random\.random\(\) < 0\.85 else random\.choice\(prefixes\[(\d+):\]\)', main_content)
    assert match is not None, "prefixes assignment and slice selection not found in main.py"

    prefixes_block, common_slice, rare_slice = match.groups()
    assert int(common_slice) == 13, f"Common slice index should be 13, got {common_slice}"
    assert int(rare_slice) == 13, f"Rare slice index should be 13, got {rare_slice}"

    assert "[Ариец]" in prefixes_block, "'[Ариец]' not found in main.py prefixes list"


@pytest.mark.asyncio
async def test_format_header_with_aryan_prefix(isolated_test_db):
    """Verify format_header renders with 'Ариец - '."""
    with patch("random.random", return_value=0.169):
        header = await format_header(
            board_id="b",
            post_num=12345,
            author_id=0,
            stream="ru",
        )
        assert "Ариец - " in header
        assert "Пост №12345" in header
