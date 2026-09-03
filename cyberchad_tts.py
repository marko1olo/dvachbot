# -*- coding: utf-8 -*-
"""
Cyberchad Cloud TTS & DSP Engine root module for DvachBot.
Re-exports core synthesis functions, preset configurations, and DSP pipelines from common.tts_engine.
"""

from common.tts_engine import (
    CyberchadPreset,
    CYBERCHAD_PRESETS,
    DEFAULT_VOICE,
    CYBERCHAD_FFMPEG_FILTER,
    clean_tts_text,
    get_preset,
    get_random_preset,
    list_presets,
    synthesize_cyberchad_voice,
    synthesize_cyberchad_voice_with_meta,
)

__all__ = [
    "CyberchadPreset",
    "CYBERCHAD_PRESETS",
    "DEFAULT_VOICE",
    "CYBERCHAD_FFMPEG_FILTER",
    "clean_tts_text",
    "get_preset",
    "get_random_preset",
    "list_presets",
    "synthesize_cyberchad_voice",
    "synthesize_cyberchad_voice_with_meta",
]
