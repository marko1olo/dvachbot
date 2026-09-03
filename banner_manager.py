# -*- coding: utf-8 -*-
"""
banner_manager.py — Centralized Banner Management & Telegram CDN Cache for ТГАЧ
Handles 51+ high-resolution generated banners with instant file_id caching,
smart non-repeating Shuffle-Bag rotation (Anti-Repeat), and balanced category pools.
"""

import os
import re
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
    "start": [],  # All 383 banners
    "night": [
        "vampiric", "cathedral", "graveyard", "tokyo_alleyway", "moon", "rain", "cyberpunk", "fantasy_field",
        "twilight", "dark", "rooftop", "crimson", "witch", "dark_purple", "night", "midnight", "rainy_city",
        "shinjuku", "standing_on_rooftop", "standing_on_red_rooftop"
    ],
    "maid": [
        "maid", "retro_desktop", "purple_hair", "pop-art", "sunflowers", "anime_style_scene",
        "heart", "peace", "pajamas", "soap", "smiling", "finger_heart", "heart_shape", "heart_sign",
        "peace_signs", "winking_in_maid", "maid_outfit"
    ],
    "schizo": [
        "scissor", "floating_tools", "study", "classroom", "empty_classroom", "vaporwave",
        "digital", "surreal_space", "tongue", "code", "fire_vortex", "vortex", "cyber",
        "sticking_out_tongue", "tongue_out", "turning_head_with_code", "glowing", "matrix"
    ],
    "calm": [
        "clubroom_with_tea", "cozy", "library", "coffee_shop", "ocean", "zen_garden",
        "concert", "grassy_hill", "snowy", "sunflower", "mountain_lands", "sunny_park",
        "garden", "curled", "rug", "floor", "sitting", "looking_over_shoulder", "cushion",
        "barefoot", "pajamas_hugging_knees", "curled_up"
    ],
    "shop": [
        "vampiric", "graveyard", "floating_tools", "scissor", "cyberpunk_room",
        "tokyo_alleyway", "digital", "alien_sky", "arcade", "record_store", "print", "graphic",
        "canister", "crystal", "soap", "apple", "tool", "desktop", "market", "store", "shop",
        "box", "layout", "poster", "retro", "album_cover", "string", "grid", "witch_hat",
        "purple_outfit", "dark_purple", "holding_apples", "holding_canisters", "holding_purple_crystal",
        "holding_red_canisters", "holding_soap_dispensers", "holding_string", "two_soap", "pigtails_graph"
    ],
    "newspaper": [
        "library", "sketch_studio", "cozy", "study", "illustration", "vinyl_record_store",
        "colorful_paint", "snowy", "fashion_runway", "editorial", "poster", "layout", "album_cover",
        "text", "typography", "bold_text", "print_layout", "framing_shot_with_typo", "editorial_design"
    ],
    "digest": [
        "shinjuku", "sunset", "vaporwave", "ocean", "alien_sky", "fashion_runway",
        "fantasy_field", "surreal_space", "concert", "school_hallway", "tokyo", "arcade",
        "runway", "city_design", "retro_arcade", "vaporwave_grid", "twilight"
    ],
    "summary": [
        "retro_desktop", "maid", "rain", "empty_classroom", "sketch_studio",
        "colorful_paint", "cathedral", "study", "classroom", "framing", "turning_head",
        "adjusting_glasses", "glasses_winking", "winking_and_framing", "framing_gesture",
        "winking_inside_classroom", "school_hallway"
    ],
    "stats": [
        "sunset", "ocean", "shinjuku", "concert", "grassy_hill", "sunny_park",
        "vortex", "mountain_lands", "digital", "glasses", "adjusting", "winking",
        "glasses_print_layout", "adjusting_glasses", "winking_in_glasses", "frame_gesture"
    ],
    "wallet": [
        "vortex", "sunflower", "coffee_shop", "vinyl_record_store", "sunny_park",
        "cyberpunk_room", "cozy", "zen_garden", "gold", "heart_shape", "witch_hat", "arcade",
        "crystal", "apple", "canister", "grid", "vaporwave", "glasses", "winking",
        "shinjuku", "sunset", "ocean", "desktop", "pajamas", "wealth", "bank", "cash",
        "money", "card", "adjusting", "holding", "frame", "peace", "finger_heart", "heart_sign",
        "holding_purple_crystal", "holding_apples", "record_store"
    ],
    "roulette": [
        "vortex", "fire_vortex", "cyberpunk", "anime_style_scene", "pop-art", "fantasy_field",
        "scissor", "floating_tools", "witch", "tongue", "crimson", "arcade", "dark",
        "red", "crystal", "canister", "twilight", "code", "matrix", "duel", "game",
        "card", "shinjuku", "surreal", "rooftop", "alien_sky", "cathedral", "graveyard",
        "danger", "action", "rain", "blood", "bold_text", "print_with_red", "dark_purple",
        "before_fire_vortex", "against_fire_vortex", "fire_vortex_poster", "sticking_out_tongue"
    ],
    "cyberpunk": [
        "cyberpunk", "cyber", "grid", "matrix", "code", "digital", "neon", "shinjuku",
        "tokyo_alleyway", "vaporwave", "vaporwave_grid", "turning_head_with_code", "glowing"
    ],
    "retro": [
        "retro", "arcade", "retro_arcade", "record_store", "vinyl", "vaporwave", "retro_desktop",
        "80s", "90s", "album_cover", "sketch_studio", "pop-art"
    ],
    "matrix": [
        "matrix", "code", "digital", "grid", "cyber", "turning_head_with_code", "glowing_c",
        "surreal_space", "floating_tools"
    ],
    "anime": [
        "anime", "anime_style_scene", "maid", "pigtails", "braided_hair", "braids", "winking",
        "pajamas", "witch_hat", "school_hallway", "classroom", "finger_heart", "heart_shape"
    ],
    "gothic": [
        "vampiric", "cathedral", "graveyard", "dark", "crimson", "witch", "witch_hat",
        "moon", "dark_purple", "rainy_city", "blood"
    ],
    "chill": [
        "cozy", "tea", "clubroom_with_tea", "coffee_shop", "zen_garden", "sunny_park",
        "garden", "curled", "rug", "floor", "cushion", "sitting", "barefoot", "snowy", "ocean"
    ],
    "market": [
        "shop", "store", "market", "arcade", "record_store", "canister", "apple", "crystal",
        "soap", "tool", "floating_tools", "box", "print", "layout"
    ],
    "games": [
        "arcade", "retro_arcade", "game", "card", "roulette", "duel", "dice", "pop-art",
        "floating_tools", "scissor"
    ],
    "cards": [
        "card", "deck", "album_cover", "print", "poster", "layout", "editorial", "typography",
        "print_layout", "graphic_design"
    ],
    "duel": [
        "duel", "vortex", "fire_vortex", "scissor", "tongue", "witch", "crimson", "danger",
        "action", "red", "bold_text", "blood"
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
    _BANNER_CACHE.clear()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _BANNER_CACHE.update(loaded)
        except Exception as e:
            logger.warning(f"[banner_manager] Failed to load cache file: {e}")

    # Scan banners directory
    if not BANNERS_DIR.exists():
        os.makedirs(BANNERS_DIR, exist_ok=True)
        
    all_files = [f.name for f in BANNERS_DIR.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
    all_files.sort()

    _CATEGORIZED_BANNERS.clear()
    _CATEGORIZED_BANNERS["all"] = all_files.copy()
    _CATEGORIZED_BANNERS["start"] = all_files.copy()
    for cat in CATEGORY_PATTERNS:
        _CATEGORIZED_BANNERS[cat] = []

    CATEGORIES_FILE = PROJECT_ROOT / "data" / "banner_categories.json"
    loaded_from_file = False

    if CATEGORIES_FILE.exists():
        try:
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                saved_categories = json.load(f)
            if isinstance(saved_categories, dict) and "start" in saved_categories:
                for cat in CATEGORY_PATTERNS:
                    _CATEGORIZED_BANNERS[cat] = [
                        fn for fn in saved_categories.get(cat, [])
                        if (BANNERS_DIR / fn).exists()
                    ]
                _CATEGORIZED_BANNERS["all"] = all_files.copy()
                _CATEGORIZED_BANNERS["start"] = all_files.copy()
                loaded_from_file = True
                logger.info(f"[banner_manager] Loaded {len(all_files)} visually audited banners across {len(_CATEGORIZED_BANNERS)} categories from banner_categories.json")
        except Exception as e:
            logger.warning(f"[banner_manager] Failed to load banner_categories.json: {e}")

    if not loaded_from_file:
        for fname in all_files:
            fn_lower = fname.lower()
            for cat, keywords in CATEGORY_PATTERNS.items():
                if cat == "start":
                    continue
                if any(kw in fn_lower for kw in keywords):
                    if fname not in _CATEGORIZED_BANNERS[cat]:
                        _CATEGORIZED_BANNERS[cat].append(fname)

    # Ensure no empty categories and populate initial shuffle decks
    _CATEGORY_DECKS.clear()
    for cat in _CATEGORIZED_BANNERS:
        if not _CATEGORIZED_BANNERS[cat]:
            _CATEGORIZED_BANNERS[cat] = all_files.copy()
        deck = _CATEGORIZED_BANNERS[cat].copy()
        random.shuffle(deck)
        _CATEGORY_DECKS[cat] = deque(deck)


_init_banners()


def save_cache():
    """Saves the current file_id cache to disk atomically."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = CACHE_FILE.with_suffix(".tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(_BANNER_CACHE, f, ensure_ascii=False, indent=2)
        tmp_file.replace(CACHE_FILE)
    except Exception as e:
        logger.warning(f"[banner_manager] Failed to save banner cache: {e}")


def get_banner_file(
    category: Optional[str] = None,
    banner_name: Optional[str] = None,
    user_id: Optional[int] = None,
    bot_id: Optional[int] = None
) -> Tuple[str, Union[str, FSInputFile]]:
    """
    Returns (banner_filename, photo_payload).
    Uses a Shuffle-Bag (Anti-Repeat) algorithm to cycle through all banners evenly.
    photo_payload is either a cached Telegram file_id (str) or FSInputFile for upload.
    Cached file_ids are scoped per bot_id to ensure cross-bot compatibility.
    """
    if not _CATEGORIZED_BANNERS.get("all"):
        _init_banners()

    cat_key = category if (category and category in _CATEGORIZED_BANNERS) else "start"
    pool = _CATEGORIZED_BANNERS.get(cat_key, _CATEGORIZED_BANNERS["all"])
    
    if not pool:
        return "", ""

    if banner_name:
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

    # Check if we have a cached file_id from Telegram CDN for this specific bot
    if bot_id:
        cached_fid = _BANNER_CACHE.get(f"{bot_id}:{chosen_file}")
        if cached_fid:
            return chosen_file, cached_fid

    cached_fid = _BANNER_CACHE.get(chosen_file)
    if cached_fid:
        return chosen_file, cached_fid

    # Fallback to local FSInputFile
    local_path = BANNERS_DIR / chosen_file
    if local_path.exists():
        return chosen_file, FSInputFile(str(local_path))
    return chosen_file, ""


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
    Sends a photo message with banner, caching the file_id automatically per bot.
    Falls back to text message if photo sending fails, and plain text if HTML parsing fails.
    """
    bot_id = getattr(bot, "id", None)
    fname, photo_payload = get_banner_file(category=category, banner_name=banner_name, user_id=chat_id, bot_id=bot_id)
    
    # Telegram photo captions are limited to 1024 characters.
    # If no photo available, send as text.
    if not photo_payload:
        return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode)

    # If caption exceeds 1024 chars, send photo first (no caption), then reply with text.
    if len(caption) > 1024:
        try:
            photo_msg = await bot.send_photo(
                chat_id=chat_id,
                photo=photo_payload
            )
            # Cache file_id from the photo message
            if photo_msg.photo and fname:
                fid = photo_msg.photo[-1].file_id
                if bot_id:
                    _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                _BANNER_CACHE[fname] = fid
                save_cache()
            # Reply to the photo with the full text
            return await _send_text_with_fallback(
                bot=bot,
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                reply_to_message_id=photo_msg.message_id
            )
        except Exception as e:
            logger.warning(f"[banner_manager] Photo+reply failed for {fname}: {e}. Retrying local file...")
            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(photo_payload, FSInputFile):
                try:
                    photo_msg = await bot.send_photo(chat_id=chat_id, photo=FSInputFile(str(local_path)))
                    if photo_msg.photo:
                        fid = photo_msg.photo[-1].file_id
                        if bot_id:
                            _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        _BANNER_CACHE[fname] = fid
                        save_cache()
                    return await _send_text_with_fallback(
                        bot=bot,
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        reply_to_message_id=photo_msg.message_id
                    )
                except Exception as e2:
                    logger.warning(f"[banner_manager] Local photo retry failed: {e2}")
            return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode)

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=photo_payload,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        
        # Cache file_id if this was an initial upload
        if msg.photo and fname:
            fid = msg.photo[-1].file_id
            if bot_id:
                _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
            _BANNER_CACHE[fname] = fid
            save_cache()
            
        return msg
    except Exception as e:
        err_text = str(e).lower()
        # If cached file_id was rejected (wrong file identifier, unparseable, wrong bot token)
        if fname:
            if bot_id and f"{bot_id}:{fname}" in _BANNER_CACHE:
                _BANNER_CACHE.pop(f"{bot_id}:{fname}", None)
            if fname in _BANNER_CACHE:
                _BANNER_CACHE.pop(fname, None)
            save_cache()

            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(photo_payload, FSInputFile):
                try:
                    msg = await bot.send_photo(
                        chat_id=chat_id,
                        photo=FSInputFile(str(local_path)),
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                    if msg.photo:
                        fid = msg.photo[-1].file_id
                        if bot_id:
                            _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        _BANNER_CACHE[fname] = fid
                        save_cache()
                    return msg
                except Exception as retry_e:
                    logger.warning(f"[banner_manager] Local file retry also failed for {fname}: {retry_e}")

        logger.warning(f"[banner_manager] send_photo failed for {fname}, falling back to text: {e}")
        return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode)


async def _send_text_with_fallback(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    reply_to_message_id: Optional[int] = None
) -> Optional[types.Message]:
    """Helper to send text message with graceful fallback from HTML to plain text."""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=True
        )
    except Exception as e1:
        if parse_mode is not None:
            # HTML parse error or entity mismatch: retry without parse mode (plain text)
            try:
                # Strip basic tags for cleaner plain text
                clean_text = re.sub(r'<[^>]+>', '', text)
                return await bot.send_message(
                    chat_id=chat_id,
                    text=clean_text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    reply_to_message_id=reply_to_message_id,
                    disable_web_page_preview=True
                )
            except Exception as e2:
                err_msg = str(e2).lower()
                if not any(ign in err_msg for ign in ["forbidden", "blocked", "deactivated", "not found"]):
                    logger.error(f"[banner_manager] Text fallback without parse_mode failed for {chat_id}: {e2}")
        return None


def get_all_banners_summary() -> Dict[str, Any]:
    """Returns summary count of banners per category and cache stats."""
    return {
        "total_banners": len(_CATEGORIZED_BANNERS.get("all", [])),
        "cached_file_ids": len(_BANNER_CACHE),
        "categories": {cat: len(files) for cat, files in _CATEGORIZED_BANNERS.items() if cat != "all"}
    }
