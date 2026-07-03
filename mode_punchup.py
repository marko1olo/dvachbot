from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from mode_punchup_data import (
    MODE_PUNCHUP_PROFILES,
    _COMMON_SOURCE_TERMS,
    _MODE_VOCAB,
    _MODE_PHRASE_EXPANSIONS,
    _MODE_SIGNATURES,
    _MODE_EXTRA_20260514,
    _MODE_LATE_SPICE_20260514,
    _MODE_EXTRA_20260515,
    _CROSS_TOPIC_SOURCE_CATEGORIES,
)


ReplacementValue = str | Sequence[str]


def _key(text: str) -> str:
    return text.casefold().replace("ё", "е")


def _choose(value: ReplacementValue) -> str:
    if isinstance(value, str):
        return value
    return random.choice(value)


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _build_pattern(replacements: Mapping[str, ReplacementValue]) -> re.Pattern[str] | None:
    if not replacements:
        return None
    words = sorted((re.escape(word) for word in replacements), key=len, reverse=True)
    return re.compile(r"(?iu)(?<![\w])(" + "|".join(words) + r")(?![\w])")


def _swap_words(text: str, profile: dict) -> str:
    pattern = profile.get("pattern")
    replacements = profile.get("replacements", {})
    if not pattern or not replacements:
        return text
    chance = profile.get("replace_chance", 0.28)

    def repl(match: re.Match[str]) -> str:
        source = match.group(0)
        if random.random() > chance:
            return source
        value = replacements.get(_key(source))
        if value is None:
            return source
        return _match_case(source, _choose(value))

    return pattern.sub(repl, text)


def _inject(text: str, profile: dict) -> str:
    if len(text) > profile.get("max_text_for_inject", 1100):
        return text
    words = text.split()
    if len(words) < 6 or random.random() > profile.get("inject_chance", 0.34):
        return text
    injections = profile.get("injections", ())
    if not injections:
        return text
    max_items = min(profile.get("max_injections", 2), max(1, len(words) // 20))
    for _ in range(random.randint(1, max_items)):
        idx = random.randrange(1, len(words))
        words.insert(idx, random.choice(injections))
    return " ".join(words)


def _add_signature(text: str, profile: dict) -> str:
    signatures = profile.get("signatures", ())
    if not signatures:
        return text
    if len(text) > profile.get("max_text_for_signature", 1200):
        return text
    if random.random() > profile.get("signature_chance", 0.16):
        return text
    signature = random.choice(signatures)
    if signature in text:
        return text
    if text.endswith((".", "!", "?", "...", "]")):
        return f"{text} {signature}"
    return f"{text}. {signature}"


def _decorate(text: str, profile: dict) -> str:
    if not text or not text.strip():
        return text
    return _swap_words(text, profile)




def _extend_unique(target: list[str], items: Sequence[str]) -> None:
    seen = set(target)
    for item in items:
        if item not in seen:
            target.append(item)
            seen.add(item)


def _apply_vocab_expansion(profile: dict, vocab: Mapping[str, ReplacementValue]) -> None:
    replacements = profile.setdefault("replacements", {})
    for category, sources in _COMMON_SOURCE_TERMS.items():
        value = vocab.get(category)
        if value is None:
            continue
        for source in sources:
            replacements.setdefault(source, value)

def _apply_cross_topic_vocabulary(profile: dict, vocab: Mapping[str, ReplacementValue]) -> None:
    replacements = profile.setdefault("replacements", {})
    for source, category in _CROSS_TOPIC_SOURCE_CATEGORIES.items():
        value = vocab.get(category)
        if value is not None:
            replacements.setdefault(source, value)


for _mode_name, _profile in MODE_PUNCHUP_PROFILES.items():
    _vocab = _MODE_VOCAB.get(_mode_name, {})
    _apply_vocab_expansion(_profile, _vocab)
    _phrases = _MODE_PHRASE_EXPANSIONS.get(_mode_name, {})
    for _field in ("prefixes", "suffixes", "injections"):
        _extend_unique(_profile.setdefault(_field, []), _phrases.get(_field, ()))
    _extend_unique(_profile.setdefault("signatures", []), _MODE_SIGNATURES.get(_mode_name, ()))
    _extra = _MODE_EXTRA_20260514.get(_mode_name, {})
    for _field in ("prefixes", "suffixes", "injections"):
        _extend_unique(_profile.setdefault(_field, []), _extra.get(_field, ()))
    _extend_unique(_profile.setdefault("signatures", []), _extra.get("signatures", ()))
    for _key_raw, _value in _extra.get("replacements", {}).items():
        _profile.setdefault("replacements", {})[_key_raw] = _value
    _late_spice = _MODE_LATE_SPICE_20260514.get(_mode_name, {})
    for _field in ("prefixes", "suffixes", "injections"):
        _extend_unique(_profile.setdefault(_field, []), _late_spice.get(_field, ()))
    _extend_unique(_profile.setdefault("signatures", []), _late_spice.get("signatures", ()))
    for _key_raw, _value in _late_spice.get("replacements", {}).items():
        _profile.setdefault("replacements", {})[_key_raw] = _value
    _extra_20260515 = _MODE_EXTRA_20260515.get(_mode_name, {})
    for _field in ("prefixes", "suffixes", "injections"):
        _extend_unique(_profile.setdefault(_field, []), _extra_20260515.get(_field, ()))
    _extend_unique(_profile.setdefault("signatures", []), _extra_20260515.get("signatures", ()))
    for _key_raw, _value in _extra_20260515.get("replacements", {}).items():
        _profile.setdefault("replacements", {})[_key_raw] = _value
    _apply_cross_topic_vocabulary(_profile, _vocab)
    _profile["replace_chance"] = max(_profile.get("replace_chance", 0.0), 0.42)
    _profile["inject_chance"] = max(_profile.get("inject_chance", 0.0), 0.46)
    _profile["prefix_chance"] = max(_profile.get("prefix_chance", 0.0), 0.30)
    _profile["suffix_chance"] = max(_profile.get("suffix_chance", 0.0), 0.30)
    _profile["signature_chance"] = max(_profile.get("signature_chance", 0.0), 0.16)
    _profile["max_injections"] = max(_profile.get("max_injections", 0), 3)


for _profile in MODE_PUNCHUP_PROFILES.values():
    _profile["replacements"] = {_key(key): value for key, value in _profile.get("replacements", {}).items()}
    _profile["pattern"] = _build_pattern(_profile["replacements"])


def punch_up_mode_text(text: str, mode_key: str | None) -> str:
    if not mode_key:
        return text
    profile = MODE_PUNCHUP_PROFILES.get(mode_key)
    if not profile:
        return text
    return _decorate(text, profile)
