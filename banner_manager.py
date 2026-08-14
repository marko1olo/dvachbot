# -*- coding: utf-8 -*-
"""
banner_manager.py — Centralized Banner Management & Telegram CDN Cache for ТГАЧ
Handles 51+ high-resolution generated banners with instant file_id caching,
smart categorization, and fallback to local file uploads.
"""

import os
import json
import random
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Union
from aiogram import Bot, types
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
BANNERS_DIR = PROJECT_ROOT / "assets" / "banners"
CACHE_FILE = PROJECT_ROOT / "data" / "banners_cache.json"

# Categorization mapping based on filename keywords
CATEGORY_PATTERNS = {
    # start pool includes wide variety of high-impact banners (Mugi, Shinobu, Senjougahara, Landscapes, Cyberpunk)
    "start": [
        "sunset", "shinjuku", "alien_sky", "sketch_studio", "illustration", "vortex",
        "sunny_park", "ocean", "clubroom_with_tea", "cozy", "grassy_hill", "library",
        "cyberpunk_room", "fashion_runway", "sunflower", "snowy", "zen_garden",
        "pop-art", "vaporwave"
    ],
    "night": [
        "vampiric", "cathedral", "graveyard", "tokyo_alleyway", "moon", "rain", "cyberpunk"
    ],
    "maid": [
        "maid", "retro_desktop", "purple_hair", "pop-art", "sunflowers"
    ],
    "schizo": [
        "scissor", "floating_tools", "study", "classroom", "empty_classroom", "vaporwave"
    ],
    "calm": [
        "clubroom_with_tea", "cozy", "library", "coffee_shop", "ocean", "zen_garden", "concert", "grassy_hill", "snowy"
    ]
}

_BANNER_CACHE: Dict[str, str] = {}
_CATEGORIZED_BANNERS: Dict[str, List[str]] = {}


def _init_banners():
    """Initializes banner lists and loads cached file_ids."""
    global _BANNER_CACHE, _CATEGORIZED_BANNERS
    
    # Load cache from disk
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _BANNER_CACHE = json.load(f)
        except Exception as e:
            logger.warning(f"[banner_manager] Failed to load cache file: {e}")
            _BANNER_CACHE = {}

    # Scan banners directory
    if not BANNERS_DIR.exists():
        os.makedirs(BANNERS_DIR, exist_ok=True)
        
    all_files = [f.name for f in BANNERS_DIR.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
    all_files.sort()

    _CATEGORIZED_BANNERS = {
        "all": all_files,
        "start": [],
        "night": [],
        "maid": [],
        "schizo": [],
        "calm": []
    }

    for fname in all_files:
        fn_lower = fname.lower()
        matched = False
        for cat, keywords in CATEGORY_PATTERNS.items():
            if any(kw in fn_lower for kw in keywords):
                _CATEGORIZED_BANNERS[cat].append(fname)
                matched = True
        if not matched:
            _CATEGORIZED_BANNERS["start"].append(fname)

    # Ensure start pool has the vast majority of all banners for rich diversity
    if len(_CATEGORIZED_BANNERS["start"]) < 30:
        _CATEGORIZED_BANNERS["start"] = all_files.copy()

    # Ensure no empty categories
    for cat in _CATEGORIZED_BANNERS:
        if not _CATEGORIZED_BANNERS[cat]:
            _CATEGORIZED_BANNERS[cat] = all_files


_init_banners()


def save_cache():
    """Saves the current file_id cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_BANNER_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[banner_manager] Failed to save banner cache: {e}")


def get_banner_file(category: Optional[str] = None, banner_name: Optional[str] = None) -> Tuple[str, Union[str, FSInputFile]]:
    """
    Returns (banner_filename, photo_payload).
    photo_payload is either a cached Telegram file_id (str) or FSInputFile for upload.
    """
    if not _CATEGORIZED_BANNERS.get("all"):
        _init_banners()

    pool = _CATEGORIZED_BANNERS.get(category, _CATEGORIZED_BANNERS["all"]) if category else _CATEGORIZED_BANNERS["all"]
    if not pool:
        pool = _CATEGORIZED_BANNERS.get("all", [])

    if banner_name and banner_name in _CATEGORIZED_BANNERS["all"]:
        chosen_file = banner_name
    elif pool:
        chosen_file = random.choice(pool)
    else:
        return "", ""

    # Check if we have a cached file_id from Telegram CDN
    cached_fid = _BANNER_CACHE.get(chosen_file)
    if cached_fid:
        return chosen_file, cached_fid

    # Fallback to local FSInputFile
    local_path = BANNERS_DIR / chosen_file
    return chosen_file, FSInputFile(str(local_path))


async def send_banner_message(
    bot: Bot,
    chat_id: int,
    caption: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    category: Optional[str] = "start",
    banner_name: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Optional[types.Message]:
    """
    Sends a photo message with banner, caching the file_id automatically on first upload.
    Falls back to text message if photo sending fails.
    """
    fname, photo_payload = get_banner_file(category=category, banner_name=banner_name)
    
    if not photo_payload:
        # No banners found, send text
        return await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=photo_payload,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        # Cache file_id if this was an initial upload
        if msg.photo and fname and fname not in _BANNER_CACHE:
            largest_photo = msg.photo[-1]
            _BANNER_CACHE[fname] = largest_photo.file_id
            save_cache()
            
        return msg
    except Exception as e:
        logger.warning(f"[banner_manager] send_photo failed for {fname}, falling back to text: {e}")
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
        except Exception as inner_e:
            logger.error(f"[banner_manager] Fallback send_message failed: {inner_e}")
            return None


def get_all_banners_summary() -> Dict[str, int]:
    """Returns summary count of banners per category and cache stats."""
    return {
        "total_banners": len(_CATEGORIZED_BANNERS.get("all", [])),
        "cached_file_ids": len(_BANNER_CACHE),
        "categories": {cat: len(files) for cat, files in _CATEGORIZED_BANNERS.items() if cat != "all"}
    }
