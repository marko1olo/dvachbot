# -*- coding: utf-8 -*-
"""
Cyberchad Cloud TTS & DSP Engine for DvachBot.
Synthesizes speech using Microsoft Edge Neural TTS with varied voices and modulation presets,
and applies brutal Cyberchad DSP audio filters via ffmpeg for Telegram Voice Notes (.ogg Opus).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CyberchadPreset:
    """
    Audio profile preset defining Edge-TTS voice settings and FFmpeg DSP modulation.
    """
    key: str
    name: str
    description: str
    voice: str
    rate: str
    pitch: str
    ffmpeg_filter: str
    weight: int = 10
    caption_title: str = "🔥 Разъёб от Киберчеда"


# Pool of Cyberchad voice personas and DSP modulation presets
CYBERCHAD_PRESETS: Dict[str, CyberchadPreset] = {
    "classic": CyberchadPreset(
        key="classic",
        name="Cyberchad Classic",
        description="Классический басовитый низкий голос Киберчеда",
        voice="ru-RU-DmitryNeural",
        rate="+20%",
        pitch="-5Hz",
        ffmpeg_filter="asetrate=24000*0.90,atempo=1.11,bass=g=8:f=100,aresample=48000",
        weight=25,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "heavy_bass": CyberchadPreset(
        key="heavy_bass",
        name="Heavy Bass Boss",
        description="Экстремальный суб-бас босса качалки",
        voice="ru-RU-DmitryNeural",
        rate="+15%",
        pitch="-10Hz",
        ffmpeg_filter="asetrate=24000*0.82,atempo=1.22,bass=g=13:f=80,treble=g=-2:f=3000,aresample=48000",
        weight=20,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "cyborg": CyberchadPreset(
        key="cyborg",
        name="Cybernetic Borg",
        description="Киборг с металлическим эхо-резонатором",
        voice="ru-RU-DmitryNeural",
        rate="+25%",
        pitch="-5Hz",
        ffmpeg_filter="asetrate=24000*0.92,atempo=1.08,aecho=0.8:0.7:12:0.6,bass=g=7:f=110,aresample=48000",
        weight=15,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "intercom": CyberchadPreset(
        key="intercom",
        name="Toxic Megaphone",
        description="Перегруженная рация / токсичный мегафон",
        voice="ru-RU-DmitryNeural",
        rate="+30%",
        pitch="+0Hz",
        ffmpeg_filter="highpass=f=350,lowpass=f=3400,volume=2.2,bass=g=6:f=200,aresample=48000",
        weight=10,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "fast_aggressive": CyberchadPreset(
        key="fast_aggressive",
        name="Fast Aggressive Roast",
        description="Скоростной пулемётный темп разъёба",
        voice="ru-RU-DmitryNeural",
        rate="+15%",
        pitch="-5Hz",
        ffmpeg_filter="atempo=1.18,asetrate=24000*0.93,atempo=1.07,bass=g=9:f=110,aresample=48000",
        weight=12,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "overdrive": CyberchadPreset(
        key="overdrive",
        name="Cyberchad Overdrive",
        description="Овердрайв с плотной компрессией и сатурацией",
        voice="ru-RU-DmitryNeural",
        rate="+25%",
        pitch="-5Hz",
        ffmpeg_filter="volume=2.2,compand=0|0:1|1:-60/-60|-20/-10|0/-3:6:0:-90:0.2,bass=g=10:f=100,treble=g=4:f=3500,aresample=48000",
        weight=15,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "infernal": CyberchadPreset(
        key="infernal",
        name="Infernal Titan",
        description="Глубокий демонический голос бездны",
        voice="ru-RU-DmitryNeural",
        rate="+10%",
        pitch="-20Hz",
        ffmpeg_filter="asetrate=24000*0.80,atempo=1.25,bass=g=15:f=75,treble=g=-3:f=3000,aresample=48000",
        weight=10,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "drill_sergeant": CyberchadPreset(
        key="drill_sergeant",
        name="Drill Sergeant",
        description="Командный голос армейского инструктора",
        voice="ru-RU-DmitryNeural",
        rate="+28%",
        pitch="-6Hz",
        ffmpeg_filter="highpass=f=85,equalizer=f=2800:width_type=q:w=1.2:g=3.5,aresample=48000",
        weight=12,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "bunker": CyberchadPreset(
        key="bunker",
        name="Bunker PA",
        description="Громкая связь подземного бункера",
        voice="ru-RU-DmitryNeural",
        rate="+20%",
        pitch="-8Hz",
        ffmpeg_filter="highpass=f=80,aecho=0.8:0.4:40:0.25,aresample=48000",
        weight=10,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
    "studio_radio": CyberchadPreset(
        key="studio_radio",
        name="Studio Broadcaster",
        description="Чистый студийный FM-диктор",
        voice="ru-RU-DmitryNeural",
        rate="+24%",
        pitch="-5Hz",
        ffmpeg_filter="highpass=f=100,lowpass=f=7500,equalizer=f=2500:width_type=q:w=1.5:g=3,aresample=48000",
        weight=10,
        caption_title="🔥 Разъёб от Киберчеда"
    ),
}






# Backward compatibility constants
DEFAULT_VOICE = "ru-RU-DmitryNeural"
CYBERCHAD_FFMPEG_FILTER = CYBERCHAD_PRESETS["classic"].ffmpeg_filter


def list_presets() -> List[CyberchadPreset]:
    """Returns all available Cyberchad voice presets."""
    return list(CYBERCHAD_PRESETS.values())


def get_random_preset() -> CyberchadPreset:
    """Selects a random preset based on predefined weights."""
    presets = list(CYBERCHAD_PRESETS.values())
    weights = [p.weight for p in presets]
    return random.choices(presets, weights=weights, k=1)[0]


def get_preset(key_or_name: Optional[str | CyberchadPreset] = None) -> CyberchadPreset:
    """
    Finds a preset by key or name. If None or not found, falls back to a random preset or classic.
    """
    if isinstance(key_or_name, CyberchadPreset):
        return key_or_name
    if not key_or_name:
        return get_random_preset()

    query = str(key_or_name).strip().lower()
    if query in CYBERCHAD_PRESETS:
        return CYBERCHAD_PRESETS[query]

    for p in CYBERCHAD_PRESETS.values():
        if p.name.lower() == query or p.key.lower() == query:
            return p

    return CYBERCHAD_PRESETS.get("classic", get_random_preset())


def clean_tts_text(text: str) -> str:
    """Cleans text of HTML tags, extra whitespace, emojis, and limits length."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    # Remove emoji spam or special characters that sound awkward in TTS
    clean = re.sub(r'[💩🔥📝🎵🎧👠💥✨👑❌✅⚠️🤖🛸📻⚡👺😈💪]', '', clean).strip()
    # Clean spaces before punctuation
    clean = re.sub(r'\s+([,.\?!;:])', r'\1', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 1000:
        clean = clean[:1000] + "..."
    return clean


async def synthesize_cyberchad_voice_with_meta(
    text: str,
    voice: Optional[str] = None,
    preset: Optional[str | CyberchadPreset] = None,
    apply_dsp: bool = True,
    timeout: float = 25.0
) -> Tuple[Optional[bytes], CyberchadPreset]:
    """
    Synthesizes speech from text using Edge-TTS with DSP modulation,
    returning both the audio bytes and the preset that was applied.

    :param text: Text to speak.
    :param voice: Override Edge TTS neural voice.
    :param preset: Specific preset name/key, or None for randomized selection.
    :param apply_dsp: Apply preset FFmpeg DSP filter.
    :param timeout: Maximum time allowed for synthesis.
    :return: Tuple of (audio_bytes or None, used CyberchadPreset).
    """
    active_preset = get_preset(preset) if preset is not None else get_random_preset()
    active_voice = voice if voice is not None else active_preset.voice

    clean_text = clean_tts_text(text)
    if not clean_text:
        return None, active_preset

    tmp_dir = tempfile.mkdtemp(prefix="cyberchad_tts_")
    raw_mp3 = os.path.join(tmp_dir, "raw_tts.mp3")
    final_ogg = os.path.join(tmp_dir, "cyberchad_voice.ogg")

    try:
        # Step 1: Cloud Neural TTS via edge-tts (with 2-attempt retry loop)
        edge_success = False
        try:
            import edge_tts
            for attempt in range(1, 3):
                try:
                    communicate = edge_tts.Communicate(
                        clean_text,
                        active_voice,
                        rate=active_preset.rate,
                        pitch=active_preset.pitch,
                        connect_timeout=7,
                        receive_timeout=20
                    )
                    attempt_timeout = min(timeout, 12.0 if attempt == 1 else timeout)
                    await asyncio.wait_for(communicate.save(raw_mp3), timeout=attempt_timeout)
                    if os.path.exists(raw_mp3) and os.path.getsize(raw_mp3) > 0:
                        edge_success = True
                        break
                except (asyncio.TimeoutError, TimeoutError, Exception) as attempt_err:
                    if attempt == 1:
                        logger.info(f"🔄 [TTS] Edge-TTS attempt 1 timed out ({attempt_err}), retrying with fresh connection...")
                        await asyncio.sleep(0.4)
                    else:
                        raise attempt_err
        except Exception as edge_err:
            err_desc = f"{type(edge_err).__name__}: {edge_err}" if str(edge_err).strip() else type(edge_err).__name__
            logger.warning(f"⚠️ [TTS] edge-tts error ({err_desc}), falling back to gTTS...")
            try:
                from gtts import gTTS
                loop = asyncio.get_running_loop()

                def run_gtts():
                    tts = gTTS(text=clean_text, lang='ru', slow=False)
                    tts.save(raw_mp3)

                await loop.run_in_executor(None, run_gtts)
            except Exception as gtts_err:
                logger.error(f"❌ [TTS] gTTS fallback failed: {gtts_err}")
                return None, active_preset

        if not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) == 0:
            logger.warning("⚠️ [TTS] Raw TTS file was empty or missing.")
            return None, active_preset

        # Step 2: Apply Preset DSP & convert to OGG Opus via ffmpeg if available
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        if apply_dsp and ffmpeg_bin:
            cmd = [
                ffmpeg_bin, "-y",
                "-i", raw_mp3,
                "-af", active_preset.ffmpeg_filter,
                "-c:a", "libopus",
                "-b:a", "64k",
                final_ogg
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.communicate(), timeout=8.0)
                if os.path.exists(final_ogg) and os.path.getsize(final_ogg) > 0:
                    with open(final_ogg, "rb") as f:
                        return f.read(), active_preset
            except Exception as dsp_err:
                logger.warning(f"⚠️ [TTS] FFmpeg Cyberchad DSP error ({dsp_err}), using raw audio...")

        # Fallback to raw MP3 bytes if ffmpeg is unavailable or failed
        with open(raw_mp3, "rb") as f:
            return f.read(), active_preset

    except Exception as e:
        logger.error(f"❌ [TTS] Unexpected error in synthesize_cyberchad_voice_with_meta: {e}", exc_info=True)
        return None, active_preset
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def synthesize_cyberchad_voice(
    text: str,
    voice: Optional[str] = None,
    preset: Optional[str | CyberchadPreset] = None,
    apply_dsp: bool = True,
    timeout: float = 15.0
) -> Optional[bytes]:
    """
    Synthesizes speech from text using Microsoft Edge Neural TTS with Cyberchad DSP modulation.
    Randomizes voice preset if not explicitly specified.

    :param text: Text to speak.
    :param voice: Override Edge TTS neural voice (default: preset voice).
    :param preset: CyberchadPreset instance, preset key string, or None for randomized selection.
    :param apply_dsp: Apply Cyberchad DSP filter via ffmpeg.
    :param timeout: Maximum time allowed for synthesis.
    :return: Bytes of the synthesized audio (.ogg or .mp3), or None if synthesis failed.
    """
    audio_bytes, _ = await synthesize_cyberchad_voice_with_meta(
        text=text,
        voice=voice,
        preset=preset,
        apply_dsp=apply_dsp,
        timeout=timeout
    )
    return audio_bytes
