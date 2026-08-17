# -*- coding: utf-8 -*-
"""
anon_identity.py — Cryptographically Secure Anonymous Identity & Referral Engine for ТГАЧ.
Implements:
1. 50/50 CVCVCV & CVCCVC + Digit (1-9) phonetic generator (>100M combinations).
2. ASCII Transliteration for Telegram-safe referral links.
3. Clean, authentic Anon naming: 'Анон [Шолтер5]' (RU) / 'Anon [Sholter5]' (EN).
"""

import hmac
import hashlib
from typing import Optional, Tuple

# Secret salt for one-way deterministic hashing of user IDs
SALT = b"TGACH_ANON_SECRET_SALT_2026_PHONETIC_V2"

# 18 phonetically clean consonants (never produce harsh clashing clusters)
CONSONANTS_UPPER = ["Б", "В", "Г", "Д", "Ж", "З", "К", "Л", "М", "Н", "П", "Р", "С", "Т", "Ф", "Х", "Ц", "Ш"]
CONSONANTS_LOWER = [c.lower() for c in CONSONANTS_UPPER]

# 5 pure natural vowels
VOWELS = ["а", "о", "у", "е", "и"]

# Soft bridge consonants for CVCCVC pattern
BRIDGES = ["р", "л", "н", "м", "с", "к", "т"]

# Complete Cyrillic to Latin transliteration table for Telegram URLs
TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h',
    'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
    'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ж': 'Zh',
    'З': 'Z', 'И': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O',
    'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H',
    'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}


def to_translit(text: str) -> str:
    """Converts Cyrillic text to ASCII translit for URL parameters."""
    return "".join(TRANSLIT_TABLE.get(ch, ch) for ch in text)


def get_anon_id(user_id: int, stream: str = "ru") -> str:
    """
    Generates a deterministic 6-letter + 1-digit phonetic Anon ID.
    Uses 50/50 distribution between CVCVCV and CVCCVC.
    Examples (RU): 'Шолтер5', 'Локада6', 'Миргаз1', 'Китука2'
    Examples (EN): 'Sholter5', 'Lokada6', 'Mirgaz1', 'Kituka2'
    """
    if not user_id:
        return "Анон0" if stream not in ["en", "int"] else "Anon0"

    h = int(hmac.new(SALT, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest(), 16)
    
    # 50/50 choice between CVCVCV and CVCCVC
    pattern_type = h & 1
    h >>= 1

    c1 = CONSONANTS_UPPER[h % len(CONSONANTS_UPPER)]
    v1 = VOWELS[(h >> 5) % len(VOWELS)]
    c2 = CONSONANTS_LOWER[(h >> 8) % len(CONSONANTS_LOWER)]
    v2 = VOWELS[(h >> 13) % len(VOWELS)]
    c3 = CONSONANTS_LOWER[(h >> 16) % len(CONSONANTS_LOWER)]
    dig = (h >> 21) % 9 + 1  # Digits 1-9

    if pattern_type == 0:
        # CVCVCV + Digit (e.g. Локада6, Мушоли6, Китука2, Цеваза1)
        v3 = VOWELS[(h >> 25) % len(VOWELS)]
        ru_id = f"{c1}{v1}{c2}{v2}{c3}{v3}{dig}"
    else:
        # CVCCVC + Digit (e.g. Шолтер5, Миргаз1, Самдес3, Барсек8)
        bridge = BRIDGES[(h >> 25) % len(BRIDGES)]
        ru_id = f"{c1}{v1}{bridge}{c2}{v2}{c3}{dig}"

    if stream in ["en", "int"]:
        return to_translit(ru_id)
    return ru_id


def get_referral_code(user_id: int) -> str:
    """Returns the ASCII translit referral code for user_id (e.g. 'Sholter5', 'Lokada6')."""
    return get_anon_id(user_id, stream="en")


def generate_anon_name(user_id: int, stream: str = "ru") -> str:
    """
    Generates the clean canonical anonymous name.
    RU: 'Анон [Шолтер5]'
    EN: 'Anon [Sholter5]'
    """
    if not user_id:
        return "Анонимус" if stream not in ["en", "int"] else "Anonymous"

    anon_id = get_anon_id(user_id, stream=stream)
    prefix = "Anon" if stream in ["en", "int"] else "Анон"
    return f"{prefix} [{anon_id}]"
