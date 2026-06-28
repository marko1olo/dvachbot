from new_modes import _match_case


def test_match_case():
    # 1. Empty source string
    assert _match_case("", "replacement") == "replacement"

    # 2. All uppercase source string
    assert _match_case("SOURCE", "replacement") == "REPLACEMENT"
    assert _match_case("S", "replacement") == "REPLACEMENT"

    # 3. Title case source string (first letter uppercase)
    assert _match_case("Source", "replacement") == "Replacement"

    # 4. Other/lowercase source string
    assert _match_case("source", "replacement") == "replacement"
    assert _match_case("soUrce", "replacement") == "replacement"
