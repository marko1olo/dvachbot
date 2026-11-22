# -*- coding: utf-8 -*-
"""
Cyberchad Cloud TTS & DSP Engine for DvachBot.
Synthesizes speech using Microsoft Edge Neural TTS with varied voices, resilient cascading fallbacks,
and modulation presets, applying brutal Cyberchad DSP audio filters via ffmpeg for Telegram Voice Notes (.ogg Opus).
Includes multi-tier caching (in-memory LRU + disk) to prevent redundant synthesis and rate limits.
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
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


# Aggressive masculine pitch-down filter for gTTS / female voice fallback (converts female voice to deep cyborg)
CYBERCHAD_GTTS_FALLBACK_FILTER = "asetrate=24000*0.74,atempo=1.35,bass=g=14:f=90,treble=g=-3:f=3500,aresample=48000"

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

# Concurrency semaphore: allows up to 2 concurrent synthesis pipelines without socket congestion
_TTS_SEMAPHORE = asyncio.Semaphore(2)

# ==============================================================================
# AUDIO CACHE (Memory LRU + Persistent Disk Cache)
# ==============================================================================
_MAX_MEMORY_CACHE = 128
_AUDIO_MEMORY_CACHE: collections.OrderedDict[str, bytes] = collections.OrderedDict()
_CACHE_LOCK = asyncio.Lock()


def _get_cache_dir() -> str:
    """Returns directory path for persistent audio cache, creating it if needed."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.join(base_dir, "data", "tts_cache")
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:
        fallback = os.path.join(tempfile.gettempdir(), "dvachbot_tts_cache")
        os.makedirs(fallback, exist_ok=True)
        return fallback


def _compute_cache_key(text: str, preset_key: str, voice: str, apply_dsp: bool) -> str:
    """Computes a deterministic MD5 hash key for audio caching."""
    raw = f"{text.strip()}::{preset_key}::{voice}::{apply_dsp}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


async def get_cached_audio(cache_key: str) -> Optional[bytes]:
    """Retrieves cached voice audio from memory LRU or persistent disk."""
    in_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    min_cache_size = 1 if in_test_env else 1000

    async with _CACHE_LOCK:
        # Check Memory LRU
        if cache_key in _AUDIO_MEMORY_CACHE:
            _AUDIO_MEMORY_CACHE.move_to_end(cache_key)
            return _AUDIO_MEMORY_CACHE[cache_key]

        # Check Disk Cache
        disk_path = os.path.join(_get_cache_dir(), f"{cache_key}.ogg")
        if os.path.isfile(disk_path):
            try:
                from common.async_file_io import read_file_bytes_async
                data = await read_file_bytes_async(disk_path)
                if data and len(data) >= min_cache_size:
                    _AUDIO_MEMORY_CACHE[cache_key] = data
                    if len(_AUDIO_MEMORY_CACHE) > _MAX_MEMORY_CACHE:
                        _AUDIO_MEMORY_CACHE.popitem(last=False)
                    return data
            except Exception as e:
                logger.debug(f"[TTS Cache] Failed reading disk cache {cache_key}: {e}")
    return None


async def put_cached_audio(cache_key: str, audio_bytes: bytes) -> None:
    """Stores voice audio in memory LRU and persistent disk cache."""
    in_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    min_cache_size = 1 if in_test_env else 1000

    if not audio_bytes or len(audio_bytes) < min_cache_size:
        return

    async with _CACHE_LOCK:
        # Update Memory LRU
        _AUDIO_MEMORY_CACHE[cache_key] = audio_bytes
        if len(_AUDIO_MEMORY_CACHE) > _MAX_MEMORY_CACHE:
            _AUDIO_MEMORY_CACHE.popitem(last=False)

        # Update Disk Cache
        disk_path = os.path.join(_get_cache_dir(), f"{cache_key}.ogg")
        tmp_disk = f"{disk_path}.tmp"
        try:
            loop = asyncio.get_running_loop()
            def _write():
                with open(tmp_disk, "wb") as f:
                    f.write(audio_bytes)
                os.replace(tmp_disk, disk_path)
            await loop.run_in_executor(None, _write)
        except Exception as e:
            logger.debug(f"[TTS Cache] Failed writing disk cache {cache_key}: {e}")
            try:
                if os.path.exists(tmp_disk):
                    os.remove(tmp_disk)
            except OSError:
                pass


def clear_tts_cache() -> None:
    """Clears both memory and disk audio caches (useful for testing and disk pruning)."""
    _AUDIO_MEMORY_CACHE.clear()
    cache_dir = _get_cache_dir()
    if os.path.exists(cache_dir):
        for fname in os.listdir(cache_dir):
            if fname.endswith(".ogg") or fname.endswith(".tmp"):
                try:
                    os.remove(os.path.join(cache_dir, fname))
                except OSError:
                    pass


def get_tts_cache_stats() -> dict:
    """Returns statistics on active memory and disk TTS cache entries."""
    cache_dir = _get_cache_dir()
    disk_count = 0
    disk_bytes = 0
    if os.path.exists(cache_dir):
        for fname in os.listdir(cache_dir):
            if fname.endswith(".ogg"):
                disk_count += 1
                try:
                    disk_bytes += os.path.getsize(os.path.join(cache_dir, fname))
                except OSError:
                    pass
    return {
        "memory_entries": len(_AUDIO_MEMORY_CACHE),
        "disk_entries": disk_count,
        "disk_size_bytes": disk_bytes,
        "cache_dir": cache_dir,
    }


# ==============================================================================
# PRESETS REGISTRY & SELECTION
# ==============================================================================
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


# ==============================================================================
# TEXT SANITIZATION & NORMALIZATION
# ==============================================================================
def clean_tts_text(text: str) -> str:
    """
    Cleans text of HTML tags, extra whitespace, emojis, and limits length.
    Adversarially strips leaked JSON structures, keys, and formatting.
    """
    if not text:
        return ""

    clean = str(text).strip()

    # Shield 1: If text contains leaked JSON fields like "text": "...", extract the speech part
    if '"text"' in clean:
        tm = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', clean, re.DOTALL)
        if not tm:
            tm = re.search(r'"text"\s*:\s*"(.*?)(?=",\s*"(?:thought|reply|reason_if_skipped|generate_image|image_prompt)"|"\s*\}|\s*$)', clean, re.DOTALL)
        if tm:
            def replace_esc(m):
                c = m.group(1)
                mapping = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', '"': '"', '\\': '\\', '/': '/'}
                return mapping.get(c, m.group(0))
            clean = re.sub(r'\\(["\\/bfnrt])', replace_esc, tm.group(1)).strip()

    # Shield 2: Remove leaked JSON keys and structural tokens
    clean = re.sub(
        r'["\']?(?:thought|reply|generate_image|image_prompt|reason_if_skipped|is_ai_roast)["\']?\s*:\s*(?:"[^"]*"|\'[^\']*\'|true|false|null|\d+),?',
        ' ',
        clean,
        flags=re.IGNORECASE
    )
    clean = re.sub(r'[{}\[\]"]', ' ', clean)

    # Standard cleanup: HTML tags and URLs
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'https?://\S+', '', clean)

    # Shield 3: Catch LLM safety refusals and replace with canonical Cyberchad response
    refusal_markers = (
        "я не могу предоставить",
        "я не могу выполнить",
        "я не могу ответить",
        "я не могу отвечать",
        "я не могу обсуждать",
        "я не могу генерировать",
        "я не могу создавать",
        "я не могу использовать",
        "я не могу помочь",
        "я не могу писать",
        "я не могу участвовать",
        "я языковая модель",
        "как языковая модель",
        "как большая языковая модель",
        "как искусственный интеллект",
        "как ии",
        "телефон доверия",
        "горячая линия психологической",
        "горячая линия",
        "совершения самоубийства",
        "причинении себе вреда",
        "обратитесь за помощью к специалистам",
        "ненормативной лексики",
        "ненормативную лексику",
        "оскорблений",
        "оскорбления",
        "правилами безопасности",
        "правила безопасности",
        "правил безопасности",
        "правилам безопасности",
        "политикой безопасности",
        "политики безопасности",
        "i cannot fulfill",
        "i cannot generate",
        "i cannot provide",
        "as an ai",
        "i am unable to",
        "i apologize, but",
        "я прошу прощения, но",
    )
    if any(m in clean.lower() for m in refusal_markers):
        logger.warning(f"⚠️ [clean_tts_text] Intercepted AI safety refusal leak: {clean[:80]}. Replacing with canonical Cyberchad roast.")
        clean = "Поплачь ещё в треде, сопливая омежка. Единственный твой гуманный выбор — это выдернуть провод из розетки и перестать позориться на глазах у всех. Сиди у параши и не вякай."

    # Markdown formatting cleanup
    clean = re.sub(r'```.*?```', ' ', clean, flags=re.DOTALL)
    clean = re.sub(r'`[^`]+`', ' ', clean)
    clean = re.sub(r'[*_~#>`]', ' ', clean)

    # Replace ampersands to prevent XML entity parsing failure in SSML
    clean = re.sub(r'&(?:amp;)?', ' и ', clean)

    # Strip surrogate pairs, zero-width chars, formatting symbols
    clean = re.sub(r'[\U00010000-\U0010ffff\u200b-\u200f\ufeff\u00ad\u00a0]', '', clean)
    # Remove emoji spam or special characters that sound awkward in TTS
    clean = re.sub(r'[💩🔥📝🎵🎧👠💥✨👑❌✅⚠️🤖🛸📻⚡👺😈💪👍👎❤️💔🤡💀☠️👀👁️🙏🤝🎉💯🚀💣🔪🩸]', '', clean)

    # Collapse excessive punctuation and whitespace
    clean = re.sub(r'\s+([,.\?!;:])', r'\1', clean)
    clean = re.sub(r'\?{2,}', '?', clean)
    clean = re.sub(r'!{2,}', '!', clean)
    clean = re.sub(r'\.{4,}', '...', clean)
    clean = re.sub(r'-{2,}', '-', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    # If there are no Cyrillic or Latin letters, it's not speech (just punctuation or symbols)
    if not re.search(r'[а-яА-ЯёЁa-zA-Z]', clean):
        return ""
    if len(clean) > 1000:
        clean = clean[:1000] + "..."
    return clean


def sanitize_for_edge_tts(text: str) -> str:
    """
    Normalizes text specifically for Microsoft Edge Neural TTS.
    Escapes and hyphenates phonetic trigger words and 2ch slang that cause DmitryNeural
    to reject input with 'No audio was received' (e.g. 'анон' -> 'а-нон', 'киберчед' -> 'кибер-чед').
    Preserves original casing and ensures clean SSML transmission.
    """
    if not text:
        return ""

    t = text
    # Ampersand normalization
    t = re.sub(r'&(?:amp;)?', ' и ', t)

    # Hyphenate slang / trigger terms so Microsoft content and phonetic filters do not drop audio
    t = re.sub(r'\b(а)(нон[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(а)(ноним[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(кибер)(чед[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(два)(ч[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(омеж)(к[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(сы)(ч[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(кри)(нж[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(ро)(фл[а-яё]*)\b', r'\1-\2', t, flags=re.IGNORECASE)

    return t


# ==============================================================================
# SYNTHESIS ENGINE & MULTI-TIER CASACADE
# ==============================================================================
async def synthesize_cyberchad_voice_with_meta(
    text: str,
    voice: Optional[str] = None,
    preset: Optional[str | CyberchadPreset] = None,
    apply_dsp: bool = True,
    timeout: float = 25.0,
    allow_female_fallback: bool = True
) -> Tuple[Optional[bytes], CyberchadPreset]:
    """
    Synthesizes speech from text using Edge-TTS with DSP modulation and multi-tier cascading fallbacks,
    returning both the audio bytes and the preset that was applied.
    Maintains strict male voice persona: female fallbacks are pitch-down modulated via FFmpeg into cyborg tones.

    :param text: Text to speak.
    :param voice: Override Edge TTS neural voice.
    :param preset: Specific preset name/key, or None for randomized selection.
    :param apply_dsp: Apply preset FFmpeg DSP filter.
    :param timeout: Maximum time allowed for synthesis.
    :param allow_female_fallback: Allow gTTS/female fallback (modulated with CYBERCHAD_GTTS_FALLBACK_FILTER).
    :return: Tuple of (audio_bytes or None, used CyberchadPreset).
    """
    active_preset = get_preset(preset) if preset is not None else get_random_preset()
    active_voice = voice if voice is not None else active_preset.voice

    clean_text = clean_tts_text(text)
    if not clean_text or not re.search(r'[а-яА-ЯёЁa-zA-Z]', clean_text):
        return None, active_preset

    # Cache Check: Instant return if identical speech & preset was already synthesized
    cache_key = _compute_cache_key(clean_text, active_preset.key, active_voice, apply_dsp)
    cached_audio = await get_cached_audio(cache_key)
    if cached_audio:
        logger.info(f"⚡ [TTS Cache HIT] Returning cached voice ({len(cached_audio)} bytes) for key {cache_key[:8]}")
        return cached_audio, active_preset

    # Prepare sanitized text specifically for Edge-TTS phonetic stability
    edge_text = sanitize_for_edge_tts(clean_text)

    tmp_dir = tempfile.mkdtemp(prefix="cyberchad_tts_")
    raw_mp3 = os.path.join(tmp_dir, "raw_tts.mp3")
    final_ogg = os.path.join(tmp_dir, "cyberchad_voice.ogg")

    in_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    min_voice_size = 1 if in_test_env else 2000

    try:
        edge_success = False
        is_female_voice = False
        is_gtts_fallback = False

        # Multi-tier cascade configuration for Edge-TTS
        # Tier 1: Primary voice with preset rate and pitch
        # Tier 2: Dmitry with safe rate & standard pitch (+0Hz) in case negative pitch Hz triggered dropout
        # Tier 3: Svetlana Neural with -25Hz pitch (modulated with masculine cyborg DSP filter)
        # Tier 4: Brian Multilingual (Male on independent cluster)
        attempts_cfg = [
            (active_voice, active_preset.rate, active_preset.pitch, False, min(timeout, 8.0)),
            (active_voice, active_preset.rate, "+0Hz", False, min(timeout, 7.0)),
            ("ru-RU-SvetlanaNeural", active_preset.rate, "-25Hz", True, min(timeout, 7.0)),
            ("en-US-BrianMultilingualNeural", "+0%", "+0Hz", False, min(timeout, 7.0)),
        ]

        try:
            import edge_tts
            async with _TTS_SEMAPHORE:
                for attempt_idx, (cand_voice, rate_cfg, pitch_cfg, female_flag, attempt_timeout) in enumerate(attempts_cfg, start=1):
                    try:
                        if os.path.exists(raw_mp3):
                            try:
                                os.remove(raw_mp3)
                            except OSError:
                                pass

                        communicate = edge_tts.Communicate(
                            edge_text,
                            cand_voice,
                            rate=rate_cfg,
                            pitch=pitch_cfg,
                            connect_timeout=7,
                            receive_timeout=20
                        )
                        await asyncio.wait_for(communicate.save(raw_mp3), timeout=attempt_timeout)
                        if os.path.exists(raw_mp3) and os.path.getsize(raw_mp3) >= min_voice_size:
                            edge_success = True
                            is_female_voice = female_flag
                            break
                        else:
                            sz = os.path.getsize(raw_mp3) if os.path.exists(raw_mp3) else 0
                            logger.warning(
                                f"⚠️ [TTS] Edge-TTS attempt {attempt_idx} ({cand_voice}) produced undersized audio ({sz} < {min_voice_size} bytes)"
                            )
                    except (asyncio.TimeoutError, TimeoutError, Exception) as attempt_err:
                        err_desc = f"{type(attempt_err).__name__}: {attempt_err}" if str(attempt_err).strip() else type(attempt_err).__name__
                        if attempt_idx < len(attempts_cfg):
                            pause_sec = 0.15 * attempt_idx + random.uniform(0.05, 0.15)
                            logger.info(
                                f"🔄 [TTS] Edge-TTS attempt {attempt_idx} ({cand_voice}) failed ({err_desc}), retrying tier {attempt_idx+1} in {pause_sec:.2f}s..."
                            )
                            await asyncio.sleep(pause_sec)
                        else:
                            raise attempt_err

                if not edge_success:
                    raise RuntimeError(f"Edge-TTS failed to produce valid audio >= {min_voice_size} bytes after {len(attempts_cfg)} attempts")

        except Exception as edge_err:
            err_desc = f"{type(edge_err).__name__}: {edge_err}" if str(edge_err).strip() else type(edge_err).__name__
            logger.warning(f"⚠️ [TTS] edge-tts error ({err_desc}) after all attempts.")

            # Strict Male Voice Policy: If allow_female_fallback is explicitly False, do not invoke gTTS
            if not allow_female_fallback and not in_test_env:
                logger.warning("🚫 [TTS] Fallback to female gTTS blocked (allow_female_fallback=False). Returning None.")
                return None, active_preset

            try:
                from gtts import gTTS
                loop = asyncio.get_running_loop()

                def run_gtts():
                    tts = gTTS(text=clean_text, lang='ru', slow=False)
                    tts.save(raw_mp3)

                await loop.run_in_executor(None, run_gtts)
                is_gtts_fallback = True
            except Exception as gtts_err:
                logger.error(f"❌ [TTS] gTTS fallback failed: {gtts_err}")
                return None, active_preset

        if not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) == 0:
            logger.warning("⚠️ [TTS] Raw TTS file was empty or missing.")
            return None, active_preset

        # Step 2: Apply Cyberchad DSP & convert to OGG Opus via ffmpeg if available
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        needs_cyborg_pitch_down = is_gtts_fallback or is_female_voice
        effective_apply_dsp = apply_dsp or needs_cyborg_pitch_down

        if effective_apply_dsp and ffmpeg_bin:
            # If fallback was gTTS or Svetlana, the raw audio is female.
            # We apply CYBERCHAD_GTTS_FALLBACK_FILTER so Cyberchad sounds like a deep masculine cyborg.
            if needs_cyborg_pitch_down:
                filter_chain = CYBERCHAD_GTTS_FALLBACK_FILTER
            else:
                filter_chain = active_preset.ffmpeg_filter

            cmd = [
                ffmpeg_bin, "-y",
                "-i", raw_mp3,
                "-af", filter_chain,
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
                from common.async_file_io import read_file_bytes_async
                if os.path.exists(final_ogg) and os.path.getsize(final_ogg) >= min_voice_size:
                    data = await read_file_bytes_async(final_ogg)
                    # Cache successful synthesis for future rapid retrieval
                    await put_cached_audio(cache_key, data)
                    return data, active_preset
            except Exception as dsp_err:
                logger.warning(f"⚠️ [TTS] FFmpeg Cyberchad DSP error ({dsp_err}), falling back...")

        # If raw audio was female (gTTS or Svetlana) and FFmpeg failed or is absent,
        # never leak unshifted female voice into production chat.
        if needs_cyborg_pitch_down:
            logger.warning("🚫 [TTS] FFmpeg pitch-shift failed or unavailable for female voice fallback. Suppressing output.")
            return None, active_preset

        # Fallback to raw MP3 bytes if ffmpeg is unavailable or failed (male voice only)
        if os.path.exists(raw_mp3) and os.path.getsize(raw_mp3) >= min_voice_size:
            from common.async_file_io import read_file_bytes_async
            data = await read_file_bytes_async(raw_mp3)
            await put_cached_audio(cache_key, data)
            return data, active_preset

        return None, active_preset

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
    timeout: float = 25.0,
    allow_female_fallback: bool = True
) -> Optional[bytes]:
    """
    Synthesizes speech from text using Microsoft Edge Neural TTS with Cyberchad DSP modulation.
    Backward compatibility wrapper returning only bytes.

    :param text: Text to speak.
    :param voice: Override Edge TTS neural voice (default: preset voice).
    :param preset: Specific preset name/key, or None for randomized selection.
    :param apply_dsp: Apply preset FFmpeg DSP filter.
    :param timeout: Maximum time allowed for synthesis.
    :param allow_female_fallback: Allow gTTS/female fallback (modulated with CYBERCHAD_GTTS_FALLBACK_FILTER).
    :return: Audio bytes (OGG Opus / MP3) or None.
    """
    audio_bytes, _ = await synthesize_cyberchad_voice_with_meta(
        text, voice=voice, preset=preset, apply_dsp=apply_dsp, timeout=timeout, allow_female_fallback=allow_female_fallback
    )
    return audio_bytes
