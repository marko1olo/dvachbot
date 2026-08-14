# -*- coding: utf-8 -*-
"""
banner_manager.py — Centralized Banner Management & Telegram CDN Cache for ТГАЧ
Handles 51+ high-resolution generated banners with instant file_id caching,
smart non-repeating Shuffle-Bag rotation (Anti-Repeat), and balanced category pools.
"""

import os
import json
import random
import logging
from collections import deque
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Union, Set, Any
from aiogram import Bot, types
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
BANNERS_DIR = PROJECT_ROOT / "assets" / "banners"
CACHE_FILE = PROJECT_ROOT / "data" / "banners_cache.json"

# Detailed categorization ensuring every single banner is actively utilized across multiple features
CATEGORY_PATTERNS = {
    "start": [], # All 51 banners
    "night": [
        "vampiric", "cathedral", "graveyard", "tokyo_alleyway", "moon", "rain", "cyberpunk", "fantasy_field"
    ],
    "maid": [
        "maid", "retro_desktop", "purple_hair", "pop-art", "sunflowers", "anime_style_scene"
    ],
    "schizo": [
        "scissor", "floating_tools", "study", "classroom", "empty_classroom", "vaporwave",
        "digital", "surreal_space"
    ],
    "calm": [
        "clubroom_with_tea", "cozy", "library", "coffee_shop", "ocean", "zen_garden",
        "concert", "grassy_hill", "snowy", "sunflower", "mountain_lands", "sunny_park"
    ],
    "shop": [
        "vampiric", "graveyard", "floating_tools", "scissor", "cyberpunk_room",
        "tokyo_alleyway", "digital", "alien_sky"
    ],
    "newspaper": [
        "library", "sketch_studio", "cozy", "study", "illustration", "vinyl_record_store",
        "colorful_paint", "snowy", "fashion_runway"
    ],
    "digest": [
        "shinjuku", "sunset", "vaporwave", "ocean", "alien_sky", "fashion_runway",
        "fantasy_field", "surreal_space", "concert"
    ],
    "summary": [
        "retro_desktop", "maid", "rain", "empty_classroom", "sketch_studio",
        "colorful_paint", "cathedral", "study"
    ],
    "stats": [
        "sunset", "ocean", "shinjuku", "concert", "grassy_hill", "sunny_park",
        "vortex", "mountain_lands", "digital"
    ],
    "wallet": [
        "vortex", "sunflower", "coffee_shop", "vinyl_record_store", "sunny_park",
        "cyberpunk_room", "cozy", "zen_garden"
    ],
    "roulette": [
        "vortex", "cyberpunk", "anime_style_scene", "pop-art", "fantasy_field",
        "scissor", "floating_tools"
    ]
}

_BANNER_CACHE: Dict[str, str] = {}
_CATEGORIZED_BANNERS: Dict[str, List[str]] = {}
_CATEGORY_DECKS: Dict[str, deque] = {}
_USER_RECENT_BANNERS: Dict[int, deque] = {}


def _init_banners():
    """Initializes banner lists, category pools, and shuffle bags."""
    global _BANNER_CACHE, _CATEGORIZED_BANNERS, _CATEGORY_DECKS
    
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
        "start": all_files.copy(),
        "night": [],
        "maid": [],
        "schizo": [],
        "calm": [],
        "shop": [],
        "newspaper": [],
        "digest": [],
        "summary": [],
        "stats": [],
        "wallet": [],
        "roulette": []
    }

    for fname in all_files:
        fn_lower = fname.lower()
        for cat, keywords in CATEGORY_PATTERNS.items():
            if cat == "start":
                continue
            if any(kw in fn_lower for kw in keywords):
                _CATEGORIZED_BANNERS[cat].append(fname)

    # Ensure no empty categories and populate initial shuffle decks
    for cat in _CATEGORIZED_BANNERS:
        if not _CATEGORIZED_BANNERS[cat]:
            _CATEGORIZED_BANNERS[cat] = all_files.copy()
        deck = _CATEGORIZED_BANNERS[cat].copy()
        random.shuffle(deck)
        _CATEGORY_DECKS[cat] = deque(deck)


_init_banners()


def save_cache():
    """Saves the current file_id cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_BANNER_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[banner_manager] Failed to save banner cache: {e}")


def get_banner_file(
    category: Optional[str] = None,
    banner_name: Optional[str] = None,
    user_id: Optional[int] = None
) -> Tuple[str, Union[str, FSInputFile]]:
    """
    Returns (banner_filename, photo_payload).
    Uses a Shuffle-Bag (Anti-Repeat) algorithm to cycle through all banners evenly.
    photo_payload is either a cached Telegram file_id (str) or FSInputFile for upload.
    """
    if not _CATEGORIZED_BANNERS.get("all"):
        _init_banners()

    cat_key = category if (category and category in _CATEGORIZED_BANNERS) else "start"
    pool = _CATEGORIZED_BANNERS.get(cat_key, _CATEGORIZED_BANNERS["all"])
    
    if not pool:
        return "", ""

    if banner_name and banner_name in _CATEGORIZED_BANNERS["all"]:
        chosen_file = banner_name
    else:
        # Shuffle Bag: Pop from non-repeating deck
        deck = _CATEGORY_DECKS.get(cat_key)
        if not deck or len(deck) == 0:
            shuffled_pool = pool.copy()
            random.shuffle(shuffled_pool)
            deck = deque(shuffled_pool)
            _CATEGORY_DECKS[cat_key] = deck

        # Check user recent history if available to avoid immediate repeats
        chosen_file = deck.popleft()
        if user_id and user_id in _USER_RECENT_BANNERS and len(pool) > 3:
            recent = _USER_RECENT_BANNERS[user_id]
            attempts = 0
            while chosen_file in recent and attempts < 3 and len(deck) > 0:
                deck.append(chosen_file)
                chosen_file = deck.popleft()
                attempts += 1

        # Record into user recent history
        if user_id:
            if user_id not in _USER_RECENT_BANNERS:
                _USER_RECENT_BANNERS[user_id] = deque(maxlen=8)
            _USER_RECENT_BANNERS[user_id].append(chosen_file)

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
    fname, photo_payload = get_banner_file(category=category, banner_name=banner_name, user_id=chat_id)
    
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


def get_all_banners_summary() -> Dict[str, Any]:
    """Returns summary count of banners per category and cache stats."""
    return {
        "total_banners": len(_CATEGORIZED_BANNERS.get("all", [])),
        "cached_file_ids": len(_BANNER_CACHE),
        "categories": {cat: len(files) for cat, files in _CATEGORIZED_BANNERS.items() if cat != "all"}
    }
