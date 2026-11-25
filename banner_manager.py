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
import asyncio
import atexit
import random
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Union, Set, Any
from aiogram import Bot, types
from aiogram.exceptions import TelegramRetryAfter
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

MAX_TELEGRAM_PHOTO_DIMENSION = 10000
MAX_TELEGRAM_PHOTO_RATIO = 20.0
QUARANTINED_BANNERS: Set[str] = {"sample_b8d5a566f74cc07816a3635c6ef08a2a.jpg"}

def validate_banner_dimensions(file_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    Validates whether an image meets Telegram's strict photo dimension requirements:
    1. Maximum single dimension <= 10000px.
    2. Aspect ratio max(w/h, h/w) <= 20.0.
    3. File must be readable and uncorrupted.
    Returns (is_valid, error_reason).
    """
    p = Path(file_path)
    if p.name in QUARANTINED_BANNERS:
        return False, f"Quarantined corrupt banner: {p.name}"
    if not p.exists():
        return False, f"File not found: {p.name}"
    if is_video_banner(p.name):
        return True, None
    try:
        from PIL import Image
        with Image.open(p) as img:
            w, h = img.size
            if w <= 0 or h <= 0:
                return False, f"Invalid zero dimension: {w}x{h}"
            if max(w, h) > MAX_TELEGRAM_PHOTO_DIMENSION:
                return False, f"Dimension exceeds {MAX_TELEGRAM_PHOTO_DIMENSION}px: {w}x{h}"
            ratio = max(w / h, h / w)
            if ratio > MAX_TELEGRAM_PHOTO_RATIO:
                return False, f"Aspect ratio {ratio:.2f} exceeds max {MAX_TELEGRAM_PHOTO_RATIO}:1 ({w}x{h})"
            return True, None
    except Exception as e:
        return False, f"Image verify failed: {e}"


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
        "banner_roulette", "roulette", "vortex", "fire_vortex", "cyberpunk", "anime_style_scene", "pop-art", "fantasy_field",
        "scissor", "floating_tools", "witch", "tongue", "crimson", "arcade", "dark",
        "red", "crystal", "canister", "twilight", "code", "matrix", "duel", "game",
        "card", "shinjuku", "surreal", "rooftop", "alien_sky", "cathedral", "graveyard",
        "danger", "action", "rain", "blood", "bold_text", "print_with_red", "dark_purple",
        "before_fire_vortex", "against_fire_vortex", "fire_vortex_poster", "sticking_out_tongue"
    ],
    "cyberpunk": [
        "banner_tictactoe", "banner_roulette", "cyberpunk", "cyber", "grid", "matrix", "code", "digital", "neon", "shinjuku",
        "tokyo_alleyway", "vaporwave", "vaporwave_grid", "turning_head_with_code", "glowing"
    ],
    "retro": [
        "banner_tictactoe", "retro", "arcade", "retro_arcade", "record_store", "vinyl", "vaporwave", "retro_desktop",
        "80s", "90s", "album_cover", "sketch_studio", "pop-art"
    ],
    "matrix": [
        "banner_tictactoe", "matrix", "code", "digital", "grid", "cyber", "turning_head_with_code", "glowing_c",
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
        "banner_tictactoe", "banner_roulette", "tictactoe", "arcade", "retro_arcade", "game", "card", "roulette", "duel", "dice", "pop-art",
        "floating_tools", "scissor"
    ],
    "cards": [
        "card", "deck", "album_cover", "print", "poster", "layout", "editorial", "typography",
        "print_layout", "graphic_design"
    ],
    "duel": [
        "banner_roulette", "duel", "vortex", "fire_vortex", "scissor", "tongue", "witch", "crimson", "danger",
        "action", "red", "bold_text", "blood"
    ]
}

_BANNER_CACHE: Dict[str, str] = {}
_CACHE_BY_FILENAME: Dict[str, str] = {}
_CATEGORIZED_BANNERS: Dict[str, List[str]] = {}
_CATEGORY_DECKS: Dict[str, deque] = {}
_USER_RECENT_BANNERS: Dict[int, deque] = {}

_LAST_CACHE_SAVE_TIME: float = 0.0
_CACHE_DIRTY: bool = False
_CACHE_DEBOUNCE_INTERVAL: float = 5.0
_SAVE_CACHE_LOCK = threading.RLock()


def _init_banners():
    """Initializes banner lists, category pools, and shuffle bags."""
    global _BANNER_CACHE, _CATEGORIZED_BANNERS, _CATEGORY_DECKS, _CACHE_DIRTY
    _CACHE_DIRTY = False

    # Load cache from disk
    _BANNER_CACHE.clear()
    _CACHE_BY_FILENAME.clear()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _BANNER_CACHE.update(loaded)
                for k, fid in loaded.items():
                    if isinstance(fid, str) and fid:
                        fn = k.split(":", 1)[1] if ":" in k else (k.split("_", 1)[1] if "_" in k and k.split("_", 1)[0].isdigit() else k)
                        if fn not in _CACHE_BY_FILENAME:
                            _CACHE_BY_FILENAME[fn] = fid
        except Exception as e:
            logger.warning(f"[banner_manager] Failed to load cache file: {e}")

    # Scan banners directory
    if not BANNERS_DIR.exists():
        os.makedirs(BANNERS_DIR, exist_ok=True)

    all_files = []
    for f in BANNERS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in SUPPORTED_BANNER_EXTENSIONS:
            if f.name in QUARANTINED_BANNERS:
                continue
            is_valid, err = validate_banner_dimensions(f)
            if not is_valid:
                logger.warning(f"[banner_manager] Quarantining invalid banner {f.name}: {err}")
                QUARANTINED_BANNERS.add(f.name)
                continue
            all_files.append(f.name)
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
                        if fn not in QUARANTINED_BANNERS
                        and (BANNERS_DIR / fn).exists()
                        and validate_banner_dimensions(BANNERS_DIR / fn)[0]
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
    Thread-safe and immune to Windows [WinError 32] / [WinError 5] file locking.

    When force=True (used in unit tests, test suites, or explicit sync flush):
        Immediately writes atomically to disk and sets _CACHE_DIRTY = False.
    When force=False (called in send_banner_message):
        If more than 5.0 seconds have elapsed since _LAST_CACHE_SAVE_TIME (or if cache
        file doesn't exist on disk), writes to disk atomically and sets _CACHE_DIRTY = False;
        otherwise sets _CACHE_DIRTY = True so it will be flushed on next threshold or shutdown.
    """
    global _LAST_CACHE_SAVE_TIME, _CACHE_DIRTY
    with _SAVE_CACHE_LOCK:
        now = time.time()

        if not force:
            elapsed = now - _LAST_CACHE_SAVE_TIME
            if CACHE_FILE.exists() and 0 <= elapsed < _CACHE_DEBOUNCE_INTERVAL:
                _CACHE_DIRTY = True
                return False

        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CACHE_FILE.parent / f"banners_cache_{os.getpid()}_{time.time_ns()}.tmp"
        try:
            # Sanitize cache so only pure strings are persisted (defends against Mocks/corrupt keys in test runs)
            clean_cache = {
                str(k): str(v) for k, v in list(_BANNER_CACHE.items())
                if isinstance(v, str) and not hasattr(v, "_mock_return_value")
            }
            # Enforce hard upper bound (2500 entries) to prevent unbounded disk growth
            if len(clean_cache) > 2500:
                excess = len(clean_cache) - 2000
                for k in list(clean_cache.keys())[:excess]:
                    clean_cache.pop(k, None)
                    _BANNER_CACHE.pop(k, None)
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(clean_cache, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Windows-resilient retry loop for atomic replace
            max_retries = 8
            for attempt in range(max_retries):
                try:
                    tmp_file.replace(CACHE_FILE)
                    break
                except (PermissionError, OSError) as pe:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(0.015 * (attempt + 1))

            _LAST_CACHE_SAVE_TIME = now
            _CACHE_DIRTY = False
            return True
        except Exception as e:
            logger.warning(f"[banner_manager] Failed to save banner cache: {e}")
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass
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
    "votemute": ["schizo", "gothic", "duel", "matrix", "cyberpunk", "night"],
    "judgment": ["gothic", "schizo", "duel", "matrix", "night"],
    "crime": ["cyberpunk", "matrix", "gothic", "night", "duel"],
    "heist": ["cyberpunk", "matrix", "night", "duel", "games"],
    "syndicate": ["cyberpunk", "matrix", "gothic", "duel", "cards"],
    "event": ["duel", "schizo", "games", "roulette", "cyberpunk"],
    "reaction": ["calm", "chill", "maid", "retro", "anime"],
    "reactions": ["calm", "chill", "maid", "retro", "anime"],
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


MAX_TELEGRAM_PHOTO_SIZE = 10485760  # 10 MB limit for sendPhoto

def _get_safe_fs_input_file(path: Path) -> Optional[FSInputFile]:
    if not path.exists():
        return None
    if path.name in QUARANTINED_BANNERS:
        return None
    try:
        suffix = path.suffix.lower()
        if suffix in ('.jpg', '.jpeg', '.png', '.webp'):
            from PIL import Image
            needs_normalization = False
            file_size = path.stat().st_size
            if file_size > MAX_TELEGRAM_PHOTO_SIZE:
                needs_normalization = True

            try:
                with Image.open(path) as probe_img:
                    pw, ph = probe_img.size
                    ratio = max(pw / max(1, ph), ph / max(1, pw))
                    if (pw + ph) > 9500 or max(pw, ph) > 9500 or ratio > 18:
                        needs_normalization = True
            except Exception as probe_err:
                logger.warning(f"[banner_manager] Image probe failed for {path.name}: {probe_err}")
                QUARANTINED_BANNERS.add(path.name)
                return None

            if needs_normalization:
                compressed_dir = path.parent / ".compressed"
                compressed_dir.mkdir(exist_ok=True)
                compressed_file = compressed_dir / f"{path.stem}_norm.jpg"
                if not compressed_file.exists() or compressed_file.stat().st_mtime < path.stat().st_mtime:
                    with Image.open(path) as img:
                        w, h = img.size
                        # Safe crop extreme banner strips to max 5:1 ratio
                        if max(w / max(1, h), h / max(1, w)) > 18:
                            if h > w:
                                img = img.crop((0, 0, w, min(h, w * 5)))
                            else:
                                img = img.crop((0, 0, min(w, h * 5), h))
                        # Scale down if max dimension or sum of dimensions exceeds limit
                        if max(img.size) > 4000 or (img.size[0] + img.size[1]) > 8000:
                            img.thumbnail((3840, 2160), Image.Resampling.LANCZOS)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        img.save(compressed_file, "JPEG", quality=88, optimize=True)
                if compressed_file.exists():
                    is_valid, _ = validate_banner_dimensions(compressed_file)
                    if is_valid:
                        return FSInputFile(str(compressed_file))
                    return None
            is_valid, _ = validate_banner_dimensions(path)
            if not is_valid:
                QUARANTINED_BANNERS.add(path.name)
                return None
    except Exception as e:
        logger.warning(f"[banner_manager] Failed to normalize/compress banner {path.name}: {e}")
        QUARANTINED_BANNERS.add(path.name)
        return None
    return FSInputFile(str(path))


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

        # Record into user recent history (bounded to 5000 users for 1GB VPS memory ceiling)
        if user_id and chosen_file:
            if user_id not in _USER_RECENT_BANNERS:
                if len(_USER_RECENT_BANNERS) > 5000:
                    for old_uid in list(_USER_RECENT_BANNERS.keys())[:1000]:
                        _USER_RECENT_BANNERS.pop(old_uid, None)
                _USER_RECENT_BANNERS[user_id] = deque(maxlen=8)
            _USER_RECENT_BANNERS[user_id].append(chosen_file)

    if not chosen_file:
        return "", ""

    # Check if we have a cached file_id from Telegram CDN (strictly scoped to bot_id when provided)
    cached_fid = None
    if bot_id:
        cached_fid = (
            _BANNER_CACHE.get(f"{bot_id}:{chosen_file}")
            or _BANNER_CACHE.get(f"{bot_id}_{chosen_file}")
        )
    else:
        cached_fid = _BANNER_CACHE.get(chosen_file) or _CACHE_BY_FILENAME.get(chosen_file)
    if cached_fid:
        return chosen_file, cached_fid

    # Fallback to local FSInputFile
    local_path = BANNERS_DIR / chosen_file
    if local_path.exists():
        safe_fs = _get_safe_fs_input_file(local_path)
        if safe_fs is not None:
            return chosen_file, safe_fs
        # If safe_fs is None (failed dimension/corrupt), quarantine and fallback
        QUARANTINED_BANNERS.add(chosen_file)
        logger.warning(f"[banner_manager] Banner {chosen_file} failed validation, choosing fallback.")
        fallback_deck = _CATEGORY_DECKS.get("start")
        while fallback_deck and len(fallback_deck) > 0:
            fb_file = fallback_deck.popleft()
            if fb_file not in QUARANTINED_BANNERS and (BANNERS_DIR / fb_file).exists():
                fb_fs = _get_safe_fs_input_file(BANNERS_DIR / fb_file)
                if fb_fs is not None:
                    return fb_file, fb_fs
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


async def get_banner_delivery_payload_async(
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = "start",
    bot_id: Optional[int] = None,
    banner_name: Optional[str] = None
) -> Tuple[str, Optional[str], Optional[bytes]]:
    """
    Non-blocking async version of get_banner_delivery_payload that runs disk I/O in worker thread.
    """
    return await asyncio.to_thread(get_banner_delivery_payload, category=category, bot_id=bot_id, banner_name=banner_name)


def _truncate_html_caption(text: str, limit: int = 950) -> str:
    """
    Безопасно обрезает HTML-текст для Telegram caption (макс 1024),
    не разрывая теги посредине и закрывая все открытые теги, чтобы избежать
    ошибки "can't parse entities".
    """
    if not text or len(text) <= limit:
        return text
    truncated = text[:limit]
    last_open = truncated.rfind('<')
    last_close = truncated.rfind('>')
    if last_open > last_close:
        truncated = truncated[:last_open]
    tag_pattern = re.compile(r'<(/?)([a-zA-Z0-9\-]+)(?:\s+[^>]*)?>')
    stack = []
    for match in tag_pattern.finditer(truncated):
        is_closing, tag_name = match.group(1), match.group(2).lower()
        if tag_name in ('b', 'i', 's', 'u', 'code', 'pre', 'a', 'tg-spoiler'):
            if is_closing:
                if stack and stack[-1] == tag_name:
                    stack.pop()
            else:
                stack.append(tag_name)
    closing_tags = ''.join(f"</{tag}>" for tag in reversed(stack))
    return truncated + closing_tags + "...\n<i>[Текст сокращен]</i>"


async def send_banner_message(
    bot: Bot,
    chat_id: int,
    caption: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    category: Optional[Union[str, List[str], Tuple[str, ...], Set[str]]] = "start",
    banner_name: Optional[str] = None,
    parse_mode: str = "HTML",
    strict: bool = False,
    reply_to_message_id: Optional[int] = None
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
        return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode, reply_to_message_id=reply_to_message_id)

    is_vid = is_video_banner(fname)

    def _extract_media_file_id(m: Optional[types.Message]) -> Optional[str]:
        if not m:
            return None
        fid = None
        if getattr(m, "video", None):
            fid = getattr(m.video, "file_id", None)
        elif getattr(m, "animation", None):
            fid = getattr(m.animation, "file_id", None)
        elif getattr(m, "photo", None):
            photos = m.photo
            if isinstance(photos, (list, tuple)) and len(photos) > 0:
                fid = getattr(photos[-1], "file_id", None)
        if isinstance(fid, str) and not hasattr(fid, "_mock_return_value"):
            return fid
        return None

    # Telegram photo/video captions are strictly capped at 1024 UTF-16 code units.
    # We NEVER butcher text with truncation or [Текст сокращен].
    # If text exceeds 1024 code units or characters, we send the media first,
    # then immediately send the complete text with the interactive inline keyboard attached.
    caption_utf16_len = len(caption.encode('utf-16-le')) // 2 if caption else 0
    if len(caption) > 1024 or caption_utf16_len > 1024:
        media_msg = None
        try:
            if is_vid:
                media_msg = await bot.send_video(chat_id=chat_id, video=media_payload, supports_streaming=True)
            else:
                media_msg = await bot.send_photo(chat_id=chat_id, photo=media_payload)
            fid = _extract_media_file_id(media_msg)
            if fid and fname:
                _CACHE_BY_FILENAME[fname] = fid
                if bot_id:
                    _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                save_cache()
        except Exception as e:
            err_text_long = str(e).lower()
            is_broken_id_long = any(term in err_text_long for term in (
                "wrong remote file identifier", "wrong file identifier", "can't unserialize",
                "media_invalid", "file_id_invalid", "wrong file_id", "invalid file id",
                "file reference expired", "file is temporarily unavailable", "failed to get http url content"
            )) or "file identifier" in err_text_long or ("file_id" in err_text_long and ("invalid" in err_text_long or "wrong" in err_text_long))
            if fname and is_broken_id_long:
                keys_to_pop = [
                    k for k in list(_BANNER_CACHE.keys())
                    if k == fname or k.endswith(f":{fname}") or k.endswith(f"_{fname}")
                ]
                for k in keys_to_pop:
                    _BANNER_CACHE.pop(k, None)
                _CACHE_BY_FILENAME.pop(fname, None)
                save_cache(force=True)
            logger.warning(f"[banner_manager] Initial media send failed for {fname}: {e}. Retrying local file...")
            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(media_payload, FSInputFile):
                try:
                    if is_vid:
                        media_msg = await bot.send_video(chat_id=chat_id, video=FSInputFile(str(local_path)), supports_streaming=True)
                    else:
                        media_msg = await bot.send_photo(chat_id=chat_id, photo=_get_safe_fs_input_file(local_path))
                    fid = _extract_media_file_id(media_msg)
                    if fid and bot_id:
                        _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        save_cache()
                except Exception as e2:
                    logger.warning(f"[banner_manager] Local media retry failed: {e2}")

        if media_msg:
            # Media was sent. Now send text + keyboard attached
            try:
                return await _send_text_with_fallback(
                    bot=bot,
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    reply_to_message_id=media_msg.message_id
                )
            except Exception as e_reply:
                logger.warning(f"[banner_manager] Reply to media failed: {e_reply}, retrying without reply_to")
                try:
                    return await _send_text_with_fallback(
                        bot=bot,
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                except Exception as e_plain:
                    logger.error(f"[banner_manager] Failed to send text after media: {e_plain}")
                    return media_msg
        else:
            # Media failed completely, deliver pure text message with keyboard intact
            return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode, reply_to_message_id=reply_to_message_id)

    try:
        if is_vid:
            msg = await bot.send_video(
                chat_id=chat_id,
                video=media_payload,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                supports_streaming=True,
                reply_to_message_id=reply_to_message_id
            )
        else:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=media_payload,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to_message_id
            )

        fid = _extract_media_file_id(msg)
        if fid and fname and bot_id:
            _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
            save_cache()

        return msg
    except TelegramRetryAfter:
        raise
    except Exception as e:
        err_text = str(e).lower()

        # Immediate FloodWait propagation: never retry with text while Telegram is flood-limiting
        if any(fl in err_text for fl in ["flood", "too many requests", "retry after"]):
            m = re.search(r"retry in (\d+)", err_text) or re.search(r"retry after (\d+)", err_text)
            retry_sec = int(m.group(1)) if m else 5
            raise TelegramRetryAfter(method=None, message=str(e), retry_after=retry_sec)

        # If user blocked bot, chat deleted, or deactivated, do NOT fallback to text!
        if any(term in err_text for term in ("forbidden", "blocked", "chat not found", "user is deactivated", "deactivated")):
            return None

        # Handle Telegram PHOTO_INVALID_DIMENSIONS gracefully without unhandled crash
        if "photo_invalid_dimensions" in err_text or "invalid dimensions" in err_text:
            if fname:
                QUARANTINED_BANNERS.add(fname)
                logger.warning(f"[banner_manager] Telegram rejected {fname} for PHOTO_INVALID_DIMENSIONS, quarantining.")
                for k in list(_BANNER_CACHE.keys()):
                    if k == fname or k.endswith(f":{fname}") or k.endswith(f"_{fname}"):
                        _BANNER_CACHE.pop(k, None)
                _CACHE_BY_FILENAME.pop(fname, None)
                save_cache(force=True)
            return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode, reply_to_message_id=reply_to_message_id)

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
                        parse_mode=None,
                        supports_streaming=True,
                        reply_to_message_id=reply_to_message_id
                    )
                else:
                    msg = await bot.send_photo(
                        chat_id=chat_id,
                        photo=media_payload,
                        caption=plain_cap,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        reply_to_message_id=reply_to_message_id
                    )
                return msg
            except TelegramRetryAfter:
                raise
            except Exception as pe_err:
                logger.warning(f"[banner_manager] Plain caption retry failed for {fname}: {pe_err}")

        # 2. Only evict cached file_id if the file_id itself was rejected
        is_broken_id = any(term in err_text for term in (
            "wrong remote file identifier", "wrong file identifier", "can't unserialize",
            "media_invalid", "file_id_invalid", "wrong file_id", "invalid file id",
            "file reference expired", "file is temporarily unavailable", "failed to get http url content"
        )) or "file identifier" in err_text or ("file_id" in err_text and ("invalid" in err_text or "wrong" in err_text))

        if fname and is_broken_id:
            # Thorough eviction across all bot_id prefixes and unscoped entries
            keys_to_pop = [
                k for k in list(_BANNER_CACHE.keys())
                if k == fname or k.endswith(f":{fname}") or k.endswith(f"_{fname}")
            ]
            for k in keys_to_pop:
                _BANNER_CACHE.pop(k, None)
            _CACHE_BY_FILENAME.pop(fname, None)
            save_cache(force=True)

            local_path = BANNERS_DIR / fname
            if local_path.exists() and not isinstance(media_payload, FSInputFile):
                try:
                    if is_vid:
                        msg = await bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(str(local_path)),
                            caption=caption,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            supports_streaming=True,
                            reply_to_message_id=reply_to_message_id
                        )
                    else:
                        msg = await bot.send_photo(
                            chat_id=chat_id,
                            photo=_get_safe_fs_input_file(local_path),
                            caption=caption,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                            reply_to_message_id=reply_to_message_id
                        )
                    fid = _extract_media_file_id(msg)
                    if fid and fname:
                        _CACHE_BY_FILENAME[fname] = fid
                        if bot_id:
                            _BANNER_CACHE[f"{bot_id}:{fname}"] = fid
                        save_cache()
                    return msg
                except TelegramRetryAfter:
                    raise
                except Exception as retry_e:
                    logger.warning(f"[banner_manager] Local media retry also failed for {fname}: {retry_e}")

        logger.warning(f"[banner_manager] send_media failed for {fname}, falling back to text: {e}")
        return await _send_text_with_fallback(bot, chat_id, caption, reply_markup, parse_mode, reply_to_message_id=reply_to_message_id)


async def _send_text_with_fallback(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    reply_to_message_id: Optional[int] = None
) -> Optional[types.Message]:
    # Telegram hard limit is 4096 chars. Truncate safely so reply_markup is never lost.
    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>[Сообщение сокращено из-за лимита длины]</i>"

    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=True
        )
    except TelegramRetryAfter:
        raise
    except Exception as e1:
        err_msg1 = str(e1).lower()
        if any(ign in err_msg1 for ign in ["forbidden", "blocked", "chat not found", "user is deactivated", "deactivated"]):
            return None
        if any(fl in err_msg1 for fl in ["flood", "too many requests", "retry after"]):
            m = re.search(r"retry in (\d+)", err_msg1)
            retry_sec = int(m.group(1)) if m else 5
            raise TelegramRetryAfter(method=None, message=str(e1), retry_after=retry_sec)
        # If reply target was deleted/not found, retry without reply_to_message_id
        if reply_to_message_id and "reply" in err_msg1 and ("not found" in err_msg1 or "specified" in err_msg1):
            try:
                return await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    reply_to_message_id=None,
                    disable_web_page_preview=True
                )
            except TelegramRetryAfter:
                raise
            except Exception:
                pass

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
            except TelegramRetryAfter:
                raise
            except Exception as e2:
                err_msg2 = str(e2).lower()
                if reply_to_message_id and "reply" in err_msg2 and ("not found" in err_msg2 or "specified" in err_msg2):
                    try:
                        clean_text = re.sub(r'<[^>]+>', '', text)
                        return await bot.send_message(
                            chat_id=chat_id,
                            text=clean_text,
                            reply_markup=reply_markup,
                            parse_mode=None,
                            reply_to_message_id=None,
                            disable_web_page_preview=True
                        )
                    except Exception:
                        pass
                if not any(ign in err_msg2 for ign in ["forbidden", "blocked", "deactivated", "not found", "too many requests", "retry after", "flood"]):
                    logger.error(f"[banner_manager] Text fallback without parse_mode failed for {chat_id}: {e2}")
        return None


def get_all_banners_summary() -> Dict[str, Any]:
    """Returns summary count of banners per category and cache stats."""
    return {
        "total_banners": len(_CATEGORIZED_BANNERS.get("all", [])),
        "cached_file_ids": len(_BANNER_CACHE),
        "categories": {cat: len(files) for cat, files in _CATEGORIZED_BANNERS.items() if cat != "all"}
    }


async def broadcast_banner_to_users(
    bot: Bot,
    user_ids: list,
    exclude_uid: int,
    caption: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    category: Union[str, List[str], Tuple[str, ...], Set[str]] = "start",
    parse_mode: str = "HTML",
    on_sent=None,
    banner_name: Optional[str] = None,
) -> List[Tuple[int, int]]:
    """
    High-performance throttled broadcast: sends banner to each user in user_ids (skipping exclude_uid).
    Uses bounded concurrency (Semaphore=8) and reuses banner_name file_id across all recipients.
    Respects Telegram rate limits, skips dead/blocked chats.
    on_sent(uid, message_id) — optional async callback per successful send.
    Returns list of (chat_id, message_id) pairs.
    """
    import asyncio
    import random
    user_list = [uid for uid in user_ids if uid != exclude_uid]
    random.shuffle(user_list)
    results: List[Tuple[int, int]] = []
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(8)

    async def _send_one(uid: int):
        async with sem:
            try:
                sent = await send_banner_message(
                    bot=bot,
                    chat_id=uid,
                    caption=caption,
                    reply_markup=reply_markup,
                    category=category,
                    banner_name=banner_name,
                    parse_mode=parse_mode,
                )
                if not sent:
                    sent = await _send_text_with_fallback(bot, uid, caption, reply_markup, parse_mode)
                if sent:
                    async with lock:
                        results.append((uid, sent.message_id))
                    if on_sent:
                        await on_sent(uid, sent.message_id)
            except TelegramRetryAfter as e:
                backoff = max(1.0, float(getattr(e, "retry_after", 3))) + random.uniform(0.3, 1.2)
                await asyncio.sleep(backoff)
                try:
                    sent = await send_banner_message(
                        bot=bot, chat_id=uid, caption=caption,
                        reply_markup=reply_markup, category=category,
                        banner_name=banner_name, parse_mode=parse_mode,
                    )
                    if sent:
                        async with lock:
                            results.append((uid, sent.message_id))
                        if on_sent:
                            await on_sent(uid, sent.message_id)
                except Exception:
                    pass
            except Exception as e:
                err_s = str(e).lower()
                if any(x in err_s for x in ["forbidden", "blocked", "chat not found", "deactivated", "kicked"]):
                    return
            await asyncio.sleep(0.04)

    tasks = [_send_one(uid) for uid in user_list]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    return results


async def _send_banners_page(*args, **kwargs):
    """Bridge forwarder to main._send_banners_page for backward compatibility and resilience."""
    import main
    return await main._send_banners_page(*args, **kwargs)

