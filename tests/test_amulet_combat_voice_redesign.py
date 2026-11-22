# -*- coding: utf-8 -*-
"""
Tests for redesigned Cyberchad Amulet combat defense, voice/circle processing, and rate-limit rejections.
"""

import sys
import os
import pytest

import importlib.util
import os
import pytest

_scratch_path = r"C:\Users\danat\.gemini\antigravity\brain\8da18977-910b-4fec-b437-6072f419cad8\scratch\amulet_combat_voice_redesign.py"
spec = importlib.util.spec_from_file_location("amulet_combat_voice_redesign", _scratch_path)
acvr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acvr)


def test_cyberchad_amulet_defense_prompt_quality():
    """Verify CYBERCHAD_AMULET_DEFENSE_PROMPT combines boss hype and opponent destruction."""
    prompt = acvr.CYBERCHAD_AMULET_DEFENSE_PROMPT
    assert "ХАЙП БОССА" in prompt or "ХАЙП ХОЗЯИНА" in prompt
    assert "РАЗНОС ОППОНЕНТА" in prompt
    assert "JSON" in prompt
    assert '"reply": true' in prompt
    assert '"thought"' in prompt
    assert '"text"' in prompt
    assert "ЗАПРЕТ НА УНЫЛЫЕ ШТАМПЫ" in prompt
    # Ensure it's not a tiny stub
    assert len(prompt) > 500


def test_chad_amulet_defense_moods_archetypes():
    """Verify CHAD_AMULET_DEFENSE_MOODS includes all requested combat archetypes."""
    moods = acvr.CHAD_AMULET_DEFENSE_MOODS
    assert len(moods) >= 8

    required_archetypes = [
        "mad_pitbull",       # Бешеный питбуль
        "bratva_strela",      # Братва на стрелке
        "mafia_hitman",       # Мафиозная расправа
        "techno_executor",    # Техно-экзекутор
        "snarky_bodyguard",   # Язвительный телохранитель
        "mocking_second",     # Глумящийся секундант
        "berserk_crusher",    # Яростный сокрушитель (legacy compatible)
        "cold_butcher",       # Хладнокровный мясник (legacy compatible)
        "inquisitor_executioner", # Техно-инквизитор (legacy compatible)
        "contemptuous_cleanser",  # Брезгливый чистильщик (legacy compatible)
    ]
    for arch in required_archetypes:
        assert arch in moods, f"Missing archetype: {arch}"
        data = moods[arch]
        assert data["id"] == arch
        assert len(data["title"]) >= 3
        assert len(data["description"]) >= 15
        assert len(data["prompt_instruction"]) >= 50
        assert len(data["thought_prompt"]) >= 15


def test_cyberchad_amulet_defense_fallback_roasts():
    """Verify CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS has >= 15 brutal lines."""
    roasts = acvr.CYBERCHAD_AMULET_DEFENSE_FALLBACK_ROASTS
    assert len(roasts) >= 15
    for r in roasts:
        assert isinstance(r, str)
        assert len(r) >= 30
        # No emojis or quote wrapping
        assert not r.startswith('"')
        assert not r.endswith('"')


def test_voice_and_circle_prompts():
    """Verify dynamic voice and video note prompt generators."""
    voice_prompt = acvr.build_cyberchad_amulet_voice_prompt(is_video_note=False)
    circle_prompt = acvr.build_cyberchad_amulet_voice_prompt(is_video_note=True)

    # Voice prompt should focus on audio / timbre / leadership
    assert "ГОЛОСОВОЕ СООБЩЕНИЕ" in voice_prompt
    assert "баритон" in voice_prompt.lower() or "тембр" in voice_prompt.lower()
    assert "ТРАНСКРИПЦИЯ" in voice_prompt
    assert "ВЕРДИКТ" in voice_prompt

    # Circle prompt should focus on video / camera / visuals
    assert "КРУЖОЧЕК" in circle_prompt
    assert "видеоряд" in circle_prompt.lower() or "в кадре" in circle_prompt.lower()

    # Both ban boring clichés
    assert "забудь унылый скулёж" in voice_prompt.lower() or "забудь унылый скулеж" in voice_prompt.lower()
    assert "забудь унылый скулёж" in circle_prompt.lower() or "забудь унылый скулеж" in circle_prompt.lower()

    # Fallback prompt
    fb_prompt = acvr.build_cyberchad_amulet_voice_fallback_prompt("Привет Киберчед", is_video_note=True)
    assert "Привет Киберчед" in fb_prompt
    assert "кружочек" in fb_prompt


def test_voice_fallback_roasts():
    """Verify voice fallback roasts list is expanded and diverse."""
    roasts = acvr.CYBERCHAD_AMULET_VOICE_FALLBACK_ROASTS
    assert len(roasts) >= 10
    # Has lines for both audio timbre and video circle
    assert any("тембр" in r.lower() or "баритон" in r.lower() for r in roasts)
    assert any("кружоч" in r.lower() or "кадр" in r.lower() for r in roasts)


def test_rate_limit_rejections_quality():
    """Verify rate limit rejections expanded to 10-12 funny lines asking for a breather."""
    rejections = acvr.CYBERCHAD_AMULET_RATE_LIMIT_REJECTIONS
    assert len(rejections) >= 10
    assert len(rejections) <= 15

    # Check key thematic motifs requested by user
    roasts_str = " ".join(rejections).lower()
    assert "дуло" in roasts_str or "пулем" in roasts_str or "ствол" in roasts_str
    assert any("шеф" in r.lower() or "босс" in r.lower() or "командир" in r.lower() for r in rejections)
