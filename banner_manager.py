# -*- coding: utf-8 -*-
"""
banner_manager.py — Centralized Banner Management & Telegram CDN Cache for ТГАЧ
Handles 51+ high-resolution generated banners with instant file_id caching,
smart non-repeating Shuffle-Bag rotation (Anti-Repeat), and balanced category pools.
"""

import os
import re
import json
import time
import atexit
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

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')
SUPPORTED_BANNER_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

def is_video_banner(filename: str) -> bool:
    """Returns True if the given banner filename has a video extension."""
    if not filename:
        return False
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS

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

_LAST_CACHE_SAVE_TIME: float = 0.0
_CACHE_DIRTY: bool = False
_CACHE_DEBOUNCE_INTERVAL: float = 5.0


def _init_banners():
    """Initializes banner lists, category pools, and shuffle bags."""
    global _BANNER_CACHE, _CATEGORIZED_BANNERS, _CATEGORY_DECKS, _CACHE_DIRTY
    _CACHE_DIRTY = False
    
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
        
    all_files = [f.name for f in BANNERS_DIR.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_BANNER_EXTENSIONS]
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

    # Dynamic categorization for any banners not yet in saved_categories (e.g. freshly dropped banners)
    all_categorized: Set[str] = set()
    for cat, cat_list in _CATEGORIZED_BANNERS.items():
        if cat not in ("all", "start"):
            all_categorized.update(cat_list)
    uncategorized = [fn for fn in all_files if fn not in all_categorized]
    files_to_categorize = all_files if not loaded_from_file else uncategorized

    if files_to_categorize:
        for fname in files_to_categorize:
            fn_lower = fname.lower()
            matched_any = False
            for cat, keywords in CATEGORY_PATTERNS.items():
                if cat == "start":
                    continue
                if any(kw in fn_lower for kw in keywords):
                    if fname not in _CATEGORIZED_BANNERS[cat]:
                        _CATEGORIZED_BANNERS[cat].append(fname)
                        matched_any = True
            # If banner didn't match specific keywords, distribute to versatile baseline pools (anime, calm, chill)
            if not matched_any:
                for fallback_cat in ("anime", "chill", "calm"):
                    if fallback_cat in _CATEGORIZED_BANNERS and fname not in _CATEGORIZED_BANNERS[fallback_cat]:
                        _CATEGORIZED_BANNERS[fallback_cat].append(fname)

        if loaded_from_file and uncategorized:
            try:
                CATEGORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp_cat_file = CATEGORIES_FILE.with_suffix(".tmp")
                with open(tmp_cat_file, "w", encoding="utf-8") as f:
                    json.dump(_CATEGORIZED_BANNERS, f, ensure_ascii=False, indent=2)
                tmp_cat_file.replace(CATEGORIES_FILE)
                logger.info(f"[banner_manager] Dynamically categorized and persisted {len(uncategorized)} new banners into banner_categories.json")
            except Exception as e:
                logger.warning(f"[banner_manager] Failed to persist new banner categories: {e}")

    # Ensure no empty categories and populate initial shuffle decks
    _CATEGORY_DECKS.clear()
    for cat in _CATEGORIZED_BANNERS:
        if not _CATEGORIZED_BANNERS[cat]:
            _CATEGORIZED_BANNERS[cat] = all_files.copy()
        deck = _CATEGORIZED_BANNERS[cat].copy()
        random.shuffle(deck)
        _CATEGORY_DECKS[cat] = deque(deck)


def reload_banners() -> int:
    """Forces rescanning of banners directory and updating category decks."""
    _init_banners()
    return len(_CATEGORIZED_BANNERS.get("all", []))


_init_banners()


def save_cache(force: bool = False) -> bool:
    """
    Saves the current file_id cache to disk atomically with debouncing.

    When force=True (used in unit tests, test suites, or explicit sync flush):
        Immediately writes atomically to disk and sets _CACHE_DIRTY = False.
    When force=False (called in send_banner_message):
        If more than 5.0 seconds have elapsed since _LAST_CACHE_SAVE_TIME (or if cache
        file doesn't exist on disk), writes to disk atomically and sets _CACHE_DIRTY = False;
        otherwise sets _CACHE_DIRTY = True so it will be flushed on next threshold or shutdown.
    """
    global _LAST_CACHE_SAVE_TIME, _CACHE_DIRTY
    now = time.time()

    if not force:
        elapsed = now - _LAST_CACHE_SAVE_TIME
        if CACHE_FILE.exists() and 0 <= elapsed < _CACHE_DEBOUNCE_INTERVAL:
            _CACHE_DIRTY = True
            return False

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = CACHE_FILE.with_suffix(".tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(_BANNER_CACHE, f, ensure_ascii=False, indent=2)
        tmp_file.replace(CACHE_FILE)
        _LAST_CACHE_SAVE_TIME = now
        _CACHE_DIRTY = False
        return True
    except Exception as e:
        logger.warning(f"[banner_manager] Failed to save banner cache: {e}")
        return False


def flush_cache(force: bool = True) -> bool:
    """Explicit sync flush to ensure all pending cache updates are written to disk."""
    return save_cache(force=force)


def sync_cache(force: bool = True) -> bool:
    """Alias for flush_cache()."""
    return flush_cache(force=force)


# Register atexit handler so any dirty cache is always written to disk on program exit
atexit.register(lambda: save_cache(force=True))


# Context expansions for bot subsections: allows each command/handler to draw from a rich, balanced pool of categories
# instead of a tiny repetitive subset. Each section gets 5-6 vibrant categories (~750-1000+ banners pool),
# ensuring all 1064 sexy anime banners rotate dynamically across the bot.
SUBSECTION_CATEGORIES: Dict[str, List[str]] = {
    # Магазин и экипировка
    "shop": ["shop", "market", "maid", "retro", "chill"],
    "wardrobe": ["maid", "chill", "shop", "gothic", "night"],
    "weapons": ["duel", "cyberpunk", "gothic", "shop", "roulette"],
    "clothes": ["maid", "chill", "shop", "retro", "calm"],
    "pharma": ["schizo", "cyberpunk", "matrix", "shop", "gothic"],
    "lootbox": ["games", "cards", "cyberpunk", "roulette", "shop"],
    "market": ["market", "shop", "cards", "retro", "wallet"],
    "wiki": ["newspaper", "summary", "retro", "cards", "stats"],
    "avatar": ["maid", "cyberpunk", "retro", "gothic", "night"],
    
    # Казино, игры и дуэли
    "casino": ["games", "roulette", "cards", "retro", "cyberpunk"],
    "roulette": ["roulette", "games", "cards", "duel", "cyberpunk"],
    "blackjack": ["cards", "games", "roulette", "retro", "duel"],
    "cards": ["cards", "games", "roulette", "retro", "duel"],
    "slots": ["games", "retro", "roulette", "cyberpunk", "cards"],
    "coinflip": ["games", "roulette", "duel", "cards", "retro"],
    "duel": ["duel", "roulette", "games", "cyberpunk", "gothic"],
    "pvp": ["duel", "roulette", "games", "cyberpunk", "gothic"],
    "russian_roulette": ["duel", "roulette", "games", "cyberpunk", "gothic"],
    "dice": ["games", "duel", "roulette", "cards", "retro"],
    "ttt": ["games", "cyberpunk", "matrix", "retro", "cards"],
    
    # Экономика, баланс, работа, дропы
    "economy": ["wallet", "market", "chill", "retro", "stats"],
    "wallet": ["wallet", "market", "chill", "retro", "stats"],
    "inventory": ["wallet", "market", "chill", "retro", "maid"],
    "bank": ["wallet", "market", "matrix", "stats", "cyberpunk", "retro"],
    "work": ["wallet", "cyberpunk", "retro", "market", "stats", "chill"],
    "airdrop": ["wallet", "games", "chill", "maid", "cards"],
    "ledger": ["stats", "summary", "matrix", "wallet", "retro"],
    "rates": ["stats", "matrix", "market", "wallet", "retro", "summary"],
    "daily": ["calm", "chill", "wallet", "maid", "retro"],
    
    # Навигация, меню, старт
    "start": ["cyberpunk", "retro", "maid", "chill", "night", "calm"],
    "menu": ["cyberpunk", "retro", "maid", "chill", "night", "calm"],
    "help": ["newspaper", "retro", "summary", "maid", "calm"],
    "boards": ["newspaper", "summary", "chill", "calm", "retro"],
    "settings": ["matrix", "cyberpunk", "retro", "schizo", "stats"],
    
    # Лента, треды, дайджесты, статистика
    "threads": ["chill", "calm", "retro", "maid", "night"],
    "calm": ["calm", "chill", "retro", "night", "maid"],
    "chill": ["chill", "calm", "retro", "maid", "calm"],
    "digest": ["digest", "newspaper", "summary", "retro", "stats"],
    "newspaper": ["newspaper", "digest", "retro", "summary", "stats"],
    "summary": ["summary", "digest", "newspaper", "stats", "calm"],
    "stats": ["stats", "summary", "matrix", "retro", "cyberpunk"],
    
    # Атмосферные режимы
    "schizo": ["schizo", "matrix", "gothic", "cyberpunk", "night"],
    "night": ["night", "gothic", "calm", "cyberpunk", "retro"],
    "gothic": ["gothic", "night", "duel", "schizo", "cyberpunk"],
    "cyberpunk": ["cyberpunk", "matrix", "retro", "games", "night"],
    "anime": ["maid", "chill", "retro", "calm", "night"],
    "maid": ["maid", "chill", "shop", "retro", "calm"],
    "retro": ["retro", "games", "cards", "shop", "maid"],
    "matrix": ["matrix", "cyberpunk", "schizo", "stats", "retro"],
    "games": ["games", "cards", "roulette", "retro", "cyberpunk"],
    "achievements": ["cards", "games", "retro", "cyberpunk", "stats"],
    "motivation": ["calm", "chill", "maid", "night", "retro"],
}


def resolve_category_candidates(
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = None,
    strict: bool = False
) -> List[str]:
    """
    Resolves a requested category or subsection into a list of available category keys.
    When strict=False, expands the section into a rich multi-category thematic pool
    from SUBSECTION_CATEGORIES, ensuring banners rotate dynamically.
    """
    if not _CATEGORIZED_BANNERS.get("all"):
        _init_banners()

    if category is None or category == "":
        return SUBSECTION_CATEGORIES.get("start", ["start"])

    if isinstance(category, (list, tuple, set)):
        valid = [c for c in category if c in _CATEGORIZED_BANNERS]
        return valid if valid else ["start"]

    if isinstance(category, str):
        cat_clean = category.strip().lower()
        if "," in cat_clean:
            parts = [p.strip() for p in cat_clean.split(",") if p.strip() in _CATEGORIZED_BANNERS]
            return parts if parts else ["start"]
        if strict:
            return [cat_clean] if cat_clean in _CATEGORIZED_BANNERS else ["start"]
        if cat_clean in SUBSECTION_CATEGORIES:
            valid = [c for c in SUBSECTION_CATEGORIES[cat_clean] if c in _CATEGORIZED_BANNERS]
            return valid if valid else ([cat_clean] if cat_clean in _CATEGORIZED_BANNERS else ["start"])
        if cat_clean in _CATEGORIZED_BANNERS:
            return [cat_clean]

    return ["start"]


def get_banner_file(
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = None,
    banner_name: Optional[str] = None,
    user_id: Optional[int] = None,
    bot_id: Optional[int] = None,
    strict: bool = False
) -> Tuple[str, Union[str, FSInputFile]]:
    """
    Returns (banner_filename, photo_payload).
    Uses a Shuffle-Bag (Anti-Repeat) algorithm across candidate categories.
    photo_payload is either a cached Telegram file_id (str) or FSInputFile for upload.
    Cached file_ids are scoped per bot_id to ensure cross-bot compatibility.
    """
    if not _CATEGORIZED_BANNERS.get("all"):
        _init_banners()

    if banner_name:
        chosen_file = banner_name
    else:
        candidates = resolve_category_candidates(category, strict=strict)
        
        # Shuffle candidates to balance rotation across all constituent categories
        shuffled_candidates = candidates.copy()
        random.shuffle(shuffled_candidates)
        
        chosen_file = None
        for cat_cand in shuffled_candidates:
            deck = _CATEGORY_DECKS.get(cat_cand)
            pool = _CATEGORIZED_BANNERS.get(cat_cand, _CATEGORIZED_BANNERS.get("all", []))
            
            if not deck or len(deck) == 0:
                shuffled_pool = pool.copy()
                random.shuffle(shuffled_pool)
                deck = deque(shuffled_pool)
                _CATEGORY_DECKS[cat_cand] = deck
                
            if len(deck) == 0:
                continue
                
            candidate_file = deck.popleft()
            if user_id and user_id in _USER_RECENT_BANNERS and len(pool) > 3:
                recent = _USER_RECENT_BANNERS[user_id]
                attempts = 0
                while candidate_file in recent and attempts < 3 and len(deck) > 0:
                    deck.append(candidate_file)
                    candidate_file = deck.popleft()
                    attempts += 1
                    
            chosen_file = candidate_file
            break

        if not chosen_file:
            cat_fallback = "start"
            fallback_deck = _CATEGORY_DECKS.get(cat_fallback)
            if not fallback_deck or len(fallback_deck) == 0:
                shuffled_pool = _CATEGORIZED_BANNERS.get(cat_fallback, []).copy()
                random.shuffle(shuffled_pool)
                fallback_deck = deque(shuffled_pool)
                _CATEGORY_DECKS[cat_fallback] = fallback_deck
            chosen_file = fallback_deck.popleft() if fallback_deck else ""

        # Record into user recent history
        if user_id and chosen_file:
            if user_id not in _USER_RECENT_BANNERS:
                _USER_RECENT_BANNERS[user_id] = deque(maxlen=8)
            _USER_RECENT_BANNERS[user_id].append(chosen_file)

    if not chosen_file:
        return "", ""

    # Check if we have a cached file_id from Telegram CDN (scoped to bot_id, or unscoped if no bot_id)
    cached_fid = None
    if bot_id:
        cached_fid = _BANNER_CACHE.get(f"{bot_id}:{chosen_file}") or _BANNER_CACHE.get(f"{bot_id}_{chosen_file}")
    else:
        cached_fid = _BANNER_CACHE.get(chosen_file)
    if cached_fid:
        return chosen_file, cached_fid

    # Fallback to local FSInputFile
    local_path = BANNERS_DIR / chosen_file
    if local_path.exists():
        return chosen_file, FSInputFile(str(local_path))
    return chosen_file, ""


def get_banner_delivery_payload(
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = "start",
    bot_id: Optional[int] = None,
    banner_name: Optional[str] = None
) -> Tuple[str, Optional[str], Optional[bytes]]:
    """
    Returns (chosen_file, file_id, image_bytes) for delivering a banner in system posts / broadcasters.
    If a valid cached file_id exists for bot_id (or unscoped), returns (chosen_file, file_id, None).
    Otherwise reads bytes from the local banners directory and returns (chosen_file, None, image_bytes).
    """
    fname, payload = get_banner_file(category=category, bot_id=bot_id, banner_name=banner_name)
    if isinstance(payload, str) and payload:
        return fname, payload, None

    img_bytes = None
    if hasattr(payload, 'path') and os.path.exists(payload.path):
        try:
            with open(payload.path, 'rb') as bf:
                img_bytes = bf.read()
        except Exception:
            pass
    elif fname:
        local_path = BANNERS_DIR / fname
        if local_path.exists():
            try:
                with open(local_path, 'rb') as bf:
                    img_bytes = bf.read()
            except Exception:
                pass

    return fname, None, img_bytes


async def send_banner_message(
    bot: Bot,
    chat_id: int,
    caption: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = "start",
    banner_name: Optional[str] = None,
    parse_mode: str = "HTML",
    strict: bool = False
) -> Optional[types.Message]:
    """
    Sends a photo or video message with banner, caching the file_id automatically per bot.
    Falls back to text message if media sending fails, and plain text if HTML parsing fails.
    """
    bot_id = getattr(bot, "id", None)
    fname, media_payload = get_banner_file(
        category=category,
        banner_name=banner_name,
        user_id=chat_id,
        bot_id=bot_id,
        strict=strict
    )
    
    # Telegram photo and video captions are limited to 1024 characters.
    # If no media available, send as text.
    if not media_payload:
        return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode)

    is_vid = is_video_banner(fname)

    def _extract_media_file_id(m: Optional[types.Message]) -> Optional[str]:
        if not m:
            return None
        if getattr(m, "video", None):
            return m.video.file_id
        if getattr(m, "animation", None):
            return m.animation.file_id
        if getattr(m, "photo", None) and len(m.photo) > 0:
            return m.photo[-1].file_id
        return None

    # If caption exceeds 1024 chars, send media first (no caption), then reply with text.
    if len(caption) > 1024:
        try:
            if is_vid:
                media_msg = await bot.send_video(chat_id=chat_id, video=media_payload)
            else:
                media_msg = await bot.send_photo(chat_id=chat_id, photo=media_payload)
            fid = _extract_media_file_id(media_msg)
            if fid and fname and bot_id:
                _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                save_cache()
            # Reply to the media with the full text
            return await _send_text_with_fallback(
                bot=bot,
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                reply_to_message_id=media_msg.message_id
            )
        except Exception as e:
            logger.warning(f"[banner_manager] Media+reply failed for {fname}: {e}. Retrying local file...")
            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(media_payload, FSInputFile):
                try:
                    if is_vid:
                        media_msg = await bot.send_video(chat_id=chat_id, video=FSInputFile(str(local_path)))
                    else:
                        media_msg = await bot.send_photo(chat_id=chat_id, photo=FSInputFile(str(local_path)))
                    fid = _extract_media_file_id(media_msg)
                    if fid and bot_id:
                        _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        save_cache()
                    return await _send_text_with_fallback(
                        bot=bot,
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        reply_to_message_id=media_msg.message_id
                    )
                except Exception as e2:
                    logger.warning(f"[banner_manager] Local media retry failed: {e2}")
            return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode)

    try:
        if is_vid:
            msg = await bot.send_video(
                chat_id=chat_id,
                video=media_payload,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=media_payload,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        
        fid = _extract_media_file_id(msg)
        if fid and fname and bot_id:
            _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
            save_cache()
            
        return msg
    except Exception as e:
        err_text = str(e).lower()

        # 1. If Telegram failed due to unclosed HTML tag in caption, retry with plain text caption
        if "can't parse entities" in err_text and parse_mode:
            try:
                import re
                plain_cap = re.sub(r'<[^>]+>', '', caption) if caption else ""
                if is_vid:
                    msg = await bot.send_video(
                        chat_id=chat_id,
                        video=media_payload,
                        caption=plain_cap,
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                else:
                    msg = await bot.send_photo(
                        chat_id=chat_id,
                        photo=media_payload,
                        caption=plain_cap,
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                return msg
            except Exception as pe_err:
                logger.warning(f"[banner_manager] Plain caption retry failed for {fname}: {pe_err}")

        # 2. Only evict cached file_id if the file_id itself was rejected
        is_broken_id = any(term in err_text for term in (
            "wrong remote file identifier", "wrong file identifier", "can't unserialize",
            "media_invalid", "file_id_invalid"
        ))

        if fname and is_broken_id:
            if bot_id and f"{bot_id}:{fname}" in _BANNER_CACHE:
                _BANNER_CACHE.pop(f"{bot_id}:{fname}", None)
            if fname in _BANNER_CACHE:
                _BANNER_CACHE.pop(fname, None)
            save_cache()

            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(media_payload, FSInputFile):
                try:
                    if is_vid:
                        msg = await bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(str(local_path)),
                            caption=caption,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                    else:
                        msg = await bot.send_photo(
                            chat_id=chat_id,
                            photo=FSInputFile(str(local_path)),
                            caption=caption,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                    fid = _extract_media_file_id(msg)
                    if fid and bot_id:
                        _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        save_cache()
                    return msg
                except Exception as retry_e:
                    logger.warning(f"[banner_manager] Local media retry also failed for {fname}: {retry_e}")

        logger.warning(f"[banner_manager] send_media failed for {fname}, falling back to text: {e}")
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


async def _send_banners_page(*args, **kwargs):
    """Bridge forwarder to main._send_banners_page for backward compatibility and resilience."""
    import main
    return await main._send_banners_page(*args, **kwargs)
