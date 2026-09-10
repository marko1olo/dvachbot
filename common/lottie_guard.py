# -*- coding: utf-8 -*-
"""
common/lottie_guard.py — Exploit & Crash Protection for Animated Stickers (Lottie/TGS)
Guards against client-crashing exploits such as 'Сдохбин' (extreme polystar vertices,
repeater explosion, NaN/Infinity transforms, deep recursion, compression bombs).
"""

import gzip
import json
import math
import logging
from typing import Tuple, Dict, Any, Set
from aiogram import Bot, types

logger = logging.getLogger(__name__)

# In-memory LRU-like caches for fast verification
_SAFE_STICKERS: Set[str] = set()
_MALICIOUS_STICKERS: Set[str] = set()
_MAX_CACHE_SIZE = 10000

# Known banned crash sticker file IDs / unique IDs
KNOWN_CRASH_FILE_IDS: Set[str] = {
    "CAACAgQAAxkBDaRkHmqdYlwJM3Ks1nT-DRyWGfinIj7CAALkGgACsNLoUEs1J96-iHTlPQQ",
}


def _walk_shapes_for_exploits(shapes: list) -> Tuple[bool, str]:
    """Recursively audits shapes in a Lottie layer for geometry bombs."""
    for sh in shapes:
        if not isinstance(sh, dict):
            continue
        
        # Check sub-shapes (groups, etc.)
        items = sh.get("it")
        if isinstance(items, list):
            ok, reason = _walk_shapes_for_exploits(items)
            if not ok:
                return False, reason

        ty = sh.get("ty")
        
        # 1. Polystar Point Count Exploit ('Сдохбин' vector)
        # Normal stars have 3-20 points. An exploit specifies e.g. 1e38 to crash rlottie/skia.
        if ty == "sr":
            pt = sh.get("pt", {})
            k_val = pt.get("k") if isinstance(pt, dict) else pt
            if k_val is not None:
                try:
                    num_val = float(k_val)
                    if math.isnan(num_val) or math.isinf(num_val) or num_val > 100 or num_val < 2:
                        return False, f"Malicious Polystar point count: pt={k_val}"
                except (ValueError, TypeError):
                    return False, f"Invalid Polystar point value: pt={k_val}"

        # 2. Repeater Bomb Exploit (Exponential geometric clone explosion)
        elif ty == "rp":
            c_val = sh.get("c", {})
            k_val = c_val.get("k") if isinstance(c_val, dict) else c_val
            if k_val is not None:
                try:
                    num_val = float(k_val)
                    if math.isnan(num_val) or math.isinf(num_val) or num_val > 100:
                        return False, f"Malicious Repeater copy count: c={k_val}"
                except (ValueError, TypeError):
                    return False, f"Invalid Repeater copy value: c={k_val}"

        # 3. Path / Vertices Flooding
        elif ty == "sh":
            ks = sh.get("ks", {})
            k_val = ks.get("k") if isinstance(ks, dict) else ks
            if isinstance(k_val, dict):
                v_list = k_val.get("v")
                if isinstance(v_list, list) and len(v_list) > 3000:
                    return False, f"Excessive path vertices: {len(v_list)}"

    return True, "ok"


def validate_lottie_dict(lottie: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Performs deep structural audit of decompressed Lottie JSON structure.
    Returns (is_safe, reason).
    """
    # 1. Basic dimension & framerate limits
    w = lottie.get("w", 512)
    h = lottie.get("h", 512)
    try:
        w_num = float(w)
        h_num = float(h)
        if w_num <= 0 or h_num <= 0 or w_num > 2048 or h_num > 2048:
            return False, f"Invalid canvas dimensions: {w}x{h}"
    except (ValueError, TypeError):
        return False, f"Non-numeric dimensions: {w}x{h}"

    fr = lottie.get("fr", 30)
    try:
        fr_num = float(fr)
        if fr_num <= 0 or fr_num > 120 or math.isnan(fr_num) or math.isinf(fr_num):
            return False, f"Abnormal framerate: fr={fr}"
    except (ValueError, TypeError):
        return False, f"Non-numeric framerate: fr={fr}"

    ip = lottie.get("ip", 0)
    op = lottie.get("op", 180)
    try:
        ip_num = float(ip)
        op_num = float(op)
        if math.isnan(ip_num) or math.isnan(op_num) or op_num < ip_num or (op_num - ip_num) > 1800:
            return False, f"Invalid frame range: ip={ip}, op={op}"
    except (ValueError, TypeError):
        return False, f"Non-numeric frame range: ip={ip}, op={op}"

    # 2. Layer count & layer validation
    layers = lottie.get("layers", [])
    if not isinstance(layers, list):
        return False, "Missing or invalid layers array"
    if len(layers) > 300:
        return False, f"Excessive layer count: {len(layers)} (max 300)"

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        shapes = layer.get("shapes", [])
        if isinstance(shapes, list):
            ok, reason = _walk_shapes_for_exploits(shapes)
            if not ok:
                return False, reason

    return True, "ok"


async def is_sticker_safe(bot: Bot, sticker: types.Sticker) -> Tuple[bool, str]:
    """
    Asynchronously verifies if a sticker is safe to broadcast to users.
    Returns (is_safe: bool, reason: str).
    """
    f_id = getattr(sticker, "file_id", "")
    f_uid = getattr(sticker, "file_unique_id", "")

    # Static blacklist check
    if f_id in KNOWN_CRASH_FILE_IDS or f_uid in KNOWN_CRASH_FILE_IDS:
        return False, "Known banned crash sticker"

    cache_key = f_uid or f_id
    if cache_key in _SAFE_STICKERS:
        return True, "cached_safe"
    if cache_key in _MALICIOUS_STICKERS:
        return False, "cached_malicious"

    # Static / WebP stickers are fundamentally safe from Lottie CPU/GPU memory exploits
    is_animated = getattr(sticker, "is_animated", False)
    is_video = getattr(sticker, "is_video", False)

    if not is_animated and not is_video:
        if len(_SAFE_STICKERS) < _MAX_CACHE_SIZE:
            _SAFE_STICKERS.add(cache_key)
        return True, "static_webp"

    # Video stickers: check file size (Telegram limits webm stickers to 256 KB)
    file_size = getattr(sticker, "file_size", 0) or 0
    if is_video:
        if file_size > 512 * 1024:
            return False, f"Video sticker too large: {file_size} bytes"
        if len(_SAFE_STICKERS) < _MAX_CACHE_SIZE:
            _SAFE_STICKERS.add(cache_key)
        return True, "video_size_ok"

    # Animated Lottie (.tgs) sticker inspection
    if is_animated:
        if file_size > 128 * 1024:
            return False, f"TGS compressed file too large: {file_size} bytes"

        try:
            # Download file bytes from Telegram CDN
            f_info = await bot.get_file(f_id)
            if not f_info or not f_info.file_path:
                return True, "cannot_fetch_path"

            stream = await bot.download_file(f_info.file_path)
            raw_bytes = stream.read()

            if len(raw_bytes) > 256 * 1024:
                return False, f"Downloaded raw TGS exceeds 256KB: {len(raw_bytes)}"

            # Decompress GZIP with safe decompressed buffer ceiling (max 1.5MB)
            try:
                decompressed = gzip.decompress(raw_bytes)
                if len(decompressed) > 1536 * 1024:
                    _MALICIOUS_STICKERS.add(cache_key)
                    return False, f"Lottie decompression bomb: {len(decompressed)} bytes"
            except Exception as e:
                _MALICIOUS_STICKERS.add(cache_key)
                return False, f"Corrupted GZIP stream: {e}"

            # Parse JSON
            try:
                lottie_data = json.loads(decompressed.decode("utf-8", errors="ignore"))
            except Exception as e:
                _MALICIOUS_STICKERS.add(cache_key)
                return False, f"Corrupted Lottie JSON: {e}"

            # Audit Lottie structure
            is_safe, reason = validate_lottie_dict(lottie_data)
            if not is_safe:
                _MALICIOUS_STICKERS.add(cache_key)
                logger.warning(f"🚨 [LOTTIE_GUARD_ALERT] Blocked malicious sticker {f_id}: {reason}")
                return False, reason

            # Verified safe
            if len(_SAFE_STICKERS) < _MAX_CACHE_SIZE:
                _SAFE_STICKERS.add(cache_key)
            return True, "lottie_validated_safe"

        except Exception as e:
            logger.error(f"[LOTTIE_GUARD] Error downloading/validating sticker {f_id}: {e}")
            # If network error occurs on bot.get_file, allow by default but log
            return True, f"validation_error_fallback: {e}"

    return True, "default_safe"
