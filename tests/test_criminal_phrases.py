# -*- coding: utf-8 -*-
"""
tests/test_criminal_phrases.py — Comprehensive test suite for criminal phrases module.
Verifies all 9 criminal phrase categories meet strict size, uniqueness, and content invariants.
"""

import pytest
from common import criminal_phrases

EXPECTED_CATEGORIES = [
    ("SCOUT_FAIL_SPOTTED_PHRASES", criminal_phrases.SCOUT_FAIL_SPOTTED_PHRASES),
    ("SCOUT_SUCCESS_COMMENTARY", criminal_phrases.SCOUT_SUCCESS_COMMENTARY),
    ("PICKPOCKET_SILENT_SUCCESS_PHRASES", criminal_phrases.PICKPOCKET_SILENT_SUCCESS_PHRASES),
    ("PICKPOCKET_LOUD_FAIL_PHRASES", criminal_phrases.PICKPOCKET_LOUD_FAIL_PHRASES),
    ("HEIST_WIN_PHRASES", criminal_phrases.HEIST_WIN_PHRASES),
    ("HEIST_LOSE_PHRASES", criminal_phrases.HEIST_LOSE_PHRASES),
    ("LOAN_PAKHOM_COLLECTOR_PHRASES", criminal_phrases.LOAN_PAKHOM_COLLECTOR_PHRASES),
    ("ARREST_DRUZHINA_PHRASES", criminal_phrases.ARREST_DRUZHINA_PHRASES),
    ("LAUNDER_WASHER_PHRASES", criminal_phrases.LAUNDER_WASHER_PHRASES),
]


def test_all_nine_categories_exist_and_non_empty():
    """Verify that all 9 required criminal phrase lists exist in the module and are non-empty."""
    assert len(EXPECTED_CATEGORIES) == 9
    for name, phrase_list in EXPECTED_CATEGORIES:
        assert hasattr(criminal_phrases, name), f"Missing category list {name}"
        assert isinstance(phrase_list, list), f"{name} is not a list"
        assert len(phrase_list) > 0, f"{name} is empty"


@pytest.mark.parametrize("category_name,phrase_list", EXPECTED_CATEGORIES)
def test_category_has_minimum_30_phrases(category_name, phrase_list):
    """Verify each category has at least 30 phrases."""
    assert len(phrase_list) >= 30, (
        f"Category '{category_name}' has only {len(phrase_list)} phrases, expected at least 30"
    )


@pytest.mark.parametrize("category_name,phrase_list", EXPECTED_CATEGORIES)
def test_category_phrases_are_unique(category_name, phrase_list):
    """Verify all phrases within each category are unique (no duplicates)."""
    unique_phrases = set(phrase_list)
    assert len(unique_phrases) == len(phrase_list), (
        f"Category '{category_name}' contains duplicate phrases: {len(phrase_list) - len(unique_phrases)} duplicates"
    )


@pytest.mark.parametrize("category_name,phrase_list", EXPECTED_CATEGORIES)
def test_category_entries_are_valid_strings(category_name, phrase_list):
    """Verify all entries are valid, non-empty stripped strings with meaningful length."""
    for idx, phrase in enumerate(phrase_list):
        assert isinstance(phrase, str), f"Phrase #{idx} in '{category_name}' is not a string: {phrase!r}"
        stripped = phrase.strip()
        assert len(stripped) > 0, f"Phrase #{idx} in '{category_name}' is empty or whitespace"
        assert len(stripped) >= 5, f"Phrase #{idx} in '{category_name}' is suspiciously short: {phrase!r}"


def test_helper_getters_return_valid_phrases():
    """Verify helper getter functions return random valid phrases from their respective lists."""
    getters_and_lists = [
        (criminal_phrases.get_scout_fail_phrase, criminal_phrases.SCOUT_FAIL_SPOTTED_PHRASES),
        (criminal_phrases.get_scout_success_commentary, criminal_phrases.SCOUT_SUCCESS_COMMENTARY),
        (criminal_phrases.get_pickpocket_silent_success_phrase, criminal_phrases.PICKPOCKET_SILENT_SUCCESS_PHRASES),
        (criminal_phrases.get_pickpocket_loud_fail_phrase, criminal_phrases.PICKPOCKET_LOUD_FAIL_PHRASES),
        (criminal_phrases.get_heist_win_phrase, criminal_phrases.HEIST_WIN_PHRASES),
        (criminal_phrases.get_heist_lose_phrase, criminal_phrases.HEIST_LOSE_PHRASES),
        (criminal_phrases.get_loan_pakhom_collector_phrase, criminal_phrases.LOAN_PAKHOM_COLLECTOR_PHRASES),
        (criminal_phrases.get_arrest_druzhina_phrase, criminal_phrases.ARREST_DRUZHINA_PHRASES),
        (criminal_phrases.get_launder_washer_phrase, criminal_phrases.LAUNDER_WASHER_PHRASES),
    ]

    for getter, source_list in getters_and_lists:
        phrase = getter()
        assert isinstance(phrase, str)
        assert len(phrase) > 0
        assert phrase in source_list
