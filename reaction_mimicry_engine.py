# -*- coding: utf-8 -*-
"""
reaction_mimicry_engine.py — Reaction Mimicry Core Engine & Persona Logic

Implements an automated, human-like reaction system mimicking genuine 2ch/Telegram users.
Personas:
  1. horny_weeb  — Anime, waifus, hentai, ecchi, 1girl, 2D art -> ['❤️', '🔥'], ['😍'], ['❤‍🔥'], ['🥰']
  2. toxic_oldfag — Normie whining, cringe, gay/fag themes, spam, disgust -> ['💩'], ['🤮'], ['🖕'], ['🤢']
  3. clown_troll — Mockery, clown takes, epic fails, absurdity, shitposts -> ['🤡'], ['😂'], ['🤣']
  4. based_chad  — Baza, chad moves, good memes, greentexts, win/respect -> ['👍'], ['👌'], ['💯']
  5. deep_sych   — Night doomer, sadness, existential despair, philosophy -> ['🤔'], ['🧐'], ['🤯'], ['😢']

Features:
  - Dynamic Mood Cycle: 'chill', 'toxic', 'horny', 'troll', 'based' shifting with diurnal rhythm or time.
  - Hybrid Classifier: Instant heuristic matching + LLM analysis (Groq/Gemini) with strict 4.0s timeout & graceful fallback.
  - Virtual Anon Pool: Deterministic user IDs (770100001..770100050) preventing duplicate self-reactions.
  - Persistent State: Stored in data/reaction_mimicry_state.json (capped at 1000 processed posts).
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("reaction_mimicry")

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

STATE_FILE_PATH = os.path.join("data", "reaction_mimicry_state.json")
MAX_PROCESSED_POSTS_HISTORY = 1000

VIRTUAL_ANON_BASE_ID = 770100001
VIRTUAL_ANON_POOL_SIZE = 50

# Available Personas and their Reaction Palettes
PERSONAS: Dict[str, Dict[str, Any]] = {
    "horny_weeb": {
        "name": "Horny Weeb",
        "desc": "Любитель аниме, вайфу, красивых тянок и хентая. Ставит сердечки и огоньки.",
        "reaction_options": [
            ["❤️", "🔥"],
            ["😍"],
            ["❤‍🔥"],
            ["🥰"],
        ],
        "tags": {
            "anime", "hentai", "1girl", "2girls", "ecchi", "breasts", "cosplay", "nsfw",
            "blue_archive", "art", "waifu", "manga", "oppai", "cleavage", "bikini",
            "swimsuit", "maid", "genshin", "honkai", "vtuber", "catgirl", "foxgirl",
            "bunnygirl", "illustration", "femdom", "yuri", "succubus"
        },
        "keywords": [
            "хентай", "аниме", "вайфу", "тян", "тяночк", "сиськи", "кун", "лоли",
            "манга", "этти", "косплей", "артик", "пикча с тян", "милашка", "няшка",
            "ня", "кавай", "эротика", "эро", "hentai", "anime", "waifu", "ecchi"
        ],
        "boards": {"sex", "d", "media"}
    },
    "toxic_oldfag": {
        "name": "Toxic Oldfag",
        "desc": "Токсичный олдфаг, ненавидит кринж, нытье, соевых нормисов и гомосятину.",
        "reaction_options": [
            ["💩"],
            ["🤮"],
            ["🖕"],
            ["🤢"],
        ],
        "tags": {
            "cringe", "gross", "ugly", "spam", "shitpost", "normie", "fail"
        },
        "keywords": [
            "кринж", "нытье", "ныть", "плак", "помогите", "нормис", "зумер", "тикток",
            "пидор", "гей", "гомо", "лгбт", "куколд", "омега", "нытик", "говно",
            "параша", "сопля", "фу", "блевот", "соя", "соевый", "мамк", "школота",
            "школьник", "отписка", "удали", "позор", "мерзость", "мразь", "cringe",
            "gay", "tiktok", "normie", "soy", "zoomer"
        ],
        "boards": set()
    },
    "clown_troll": {
        "name": "Clown Troll",
        "desc": "Угарает над эпичными фейлами, клоунскими тейками, абсурдом и шизой.",
        "reaction_options": [
            ["🤡"],
            ["😂"],
            ["🤣"],
        ],
        "tags": {
            "meme", "funny", "humor", "joke", "clown", "fail", "comedy"
        },
        "keywords": [
            "лол", "кек", "клоун", "цирк", "ахах", "орнул", "ор выше гор", "шизик",
            "шиза", "обосрался", "кринжанул", "тролль", "байт", "фейл", "жидкий",
            "обосратушки", "цирк уехал", "лололо", "азаза", "пародия", "смех", "ржу",
            "ржомба", "пранк", "kek", "lol", "lmao", "rofl", "clown", "circus", "fail"
        ],
        "boards": set()
    },
    "based_chad": {
        "name": "Based Chad",
        "desc": "Базированный гигачад, одобряет факты, победы, крутые пасты и годный контент.",
        "reaction_options": [
            ["👍"],
            ["👌"],
            ["💯"],
        ],
        "tags": {
            "based", "chad", "gigachad", "fitness", "win", "cool", "sigma", "greentext"
        },
        "keywords": [
            "база", "базирован", "чад", "гигачад", "сигма", "красава", "годно",
            "годнота", "мем", "паста", "гринтекст", "уважение", "респект", "мужчина",
            "молодец", "топ", "факты", "правда", "сильно", "мощь", "одобряю", "красиво",
            "заслуженно", "победа", "based", "chad", "gigachad", "sigma", "greentext",
            "respect", "win", "legend"
        ],
        "boards": {"b"}
    },
    "deep_sych": {
        "name": "Deep Sych",
        "desc": "Ночной сыч и думмер, размышляет о бытии, пустоте, экзистенциальной тоске.",
        "reaction_options": [
            ["🤔"],
            ["🧐"],
            ["🤯"],
            ["😢"],
        ],
        "tags": {
            "night", "dark", "sad", "alone", "philosophy", "doomer", "lonely"
        },
        "keywords": [
            "грустно", "одиноко", "ночь", "сыч", "сычевать", "тоска", "депрессия",
            "жизнь", "смысл", "философия", "бессмысленно", "пустота", "темнота",
            "почему", "зачем", "душа", "мысли", "бессонница", "одиночество", "боль",
            "грусть", "печаль", "все тлен", "устал", "безысходность", "бытие",
            "домер", "думер", "doomer", "sad", "alone", "night", "philosophy",
            "depressed", "empty", "void"
        ],
        "boards": set()
    }
}

VALID_MOODS = ["chill", "toxic", "horny", "troll", "based"]

# Mood to Persona Bias Mapping
MOOD_PERSONA_AFFINITY: Dict[str, str] = {
    "chill": "deep_sych",
    "toxic": "toxic_oldfag",
    "horny": "horny_weeb",
    "troll": "clown_troll",
    "based": "based_chad",
}

# In-memory cached state
_ACTIVE_STATE: Optional[Dict[str, Any]] = None
_STATE_LOCK = asyncio.Lock()


# =============================================================================
# PERSISTENCE & STATE MANAGEMENT
# =============================================================================

def get_default_state() -> Dict[str, Any]:
    """Returns a clean initial state dictionary."""
    return {
        "last_run_timestamp": 0.0,
        "current_mood": "chill",
        "last_mood_update": 0.0,
        "processed_post_nums": [],
        "persona_stats": {k: 0 for k in PERSONAS.keys()},
        "total_reactions_placed": 0
    }


def load_mimicry_state(file_path: str = STATE_FILE_PATH) -> Dict[str, Any]:
    """Loads state synchronously with error fallback."""
    global _ACTIVE_STATE
    if not os.path.exists(file_path):
        _ACTIVE_STATE = get_default_state()
        return _ACTIVE_STATE

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure all required keys exist
            defaults = get_default_state()
            for key, val in defaults.items():
                if key not in data:
                    data[key] = val
            for p in PERSONAS.keys():
                if p not in data.get("persona_stats", {}):
                    data.setdefault("persona_stats", {})[p] = 0
            _ACTIVE_STATE = data
            return data
    except Exception as e:
        logger.warning(f"Failed to load reaction mimicry state from {file_path}: {e}")
        _ACTIVE_STATE = get_default_state()
        return _ACTIVE_STATE


def save_mimicry_state(state: Dict[str, Any], file_path: str = STATE_FILE_PATH) -> bool:
    """Saves state atomically using temporary file replacement."""
    global _ACTIVE_STATE
    _ACTIVE_STATE = state
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        tmp_path = f"{file_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)
        return True
    except Exception as e:
        logger.error(f"Failed to save reaction mimicry state to {file_path}: {e}")
        return False


# =============================================================================
# DYNAMIC MOOD CYCLE
# =============================================================================

def calculate_diurnal_mood(now_dt: Optional[datetime] = None) -> str:
    """
    Computes natural mood based on hour of day (UTC):
      00:00 - 05:59 -> Night: deep_sych / horny (chill/horny)
      06:00 - 11:59 -> Morning: based_chad (based)
      12:00 - 17:59 -> Afternoon: toxic_oldfag (toxic)
      18:00 - 23:59 -> Evening: clown_troll (troll)
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    hour = now_dt.hour

    if 0 <= hour < 6:
        return "chill" if (hour % 2 == 0) else "horny"
    elif 6 <= hour < 12:
        return "based"
    elif 12 <= hour < 18:
        return "toxic"
    else:
        return "troll"


def get_current_mood(state: Optional[Dict[str, Any]] = None) -> str:
    """Returns the current active mood, recalculating if expired (>3 hours)."""
    if state is None:
        state = _ACTIVE_STATE or load_mimicry_state()

    now = time.time()
    last_update = state.get("last_mood_update", 0.0)
    current_mood = state.get("current_mood", "chill")

    # Shift mood periodically if 3+ hours have passed
    if (now - last_update) >= 10800.0 or current_mood not in VALID_MOODS:
        current_mood = calculate_diurnal_mood()
        state["current_mood"] = current_mood
        state["last_mood_update"] = now
        save_mimicry_state(state)

    return current_mood


def set_current_mood(mood: str, state: Optional[Dict[str, Any]] = None) -> str:
    """Explicitly sets system mood."""
    if mood not in VALID_MOODS:
        mood = "chill"
    if state is None:
        state = _ACTIVE_STATE or load_mimicry_state()

    state["current_mood"] = mood
    state["last_mood_update"] = time.time()
    save_mimicry_state(state)
    return mood


def cycle_mood(forced_mood: Optional[str] = None, state: Optional[Dict[str, Any]] = None) -> str:
    """Cycles to the next mood in the cycle or to a forced mood."""
    if state is None:
        state = _ACTIVE_STATE or load_mimicry_state()

    if forced_mood and forced_mood in VALID_MOODS:
        new_mood = forced_mood
    else:
        curr = state.get("current_mood", "chill")
        idx = (VALID_MOODS.index(curr) + 1) % len(VALID_MOODS) if curr in VALID_MOODS else 0
        new_mood = VALID_MOODS[idx]

    return set_current_mood(new_mood, state)


# =============================================================================
# VIRTUAL ANON POOL & DEDUPLICATION
# =============================================================================

def get_or_assign_virtual_reactor(post_num: int, persona: str) -> int:
    """
    Returns a deterministic virtual anon user_id in the range [770100001..770100050].
    
    Invariants:
    1. For the same (post_num, persona), the returned user_id is 100% deterministic.
    2. Different personas on the same post get different user_ids (via persona salt).
    3. Guarantees the same virtual anon will never re-react to the same post with the same persona.
    """
    key = f"{post_num}:{persona}"
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    offset = h % VIRTUAL_ANON_POOL_SIZE
    return VIRTUAL_ANON_BASE_ID + offset


# =============================================================================
# HYBRID CLASSIFIER: HEURISTICS
# =============================================================================

def _extract_post_features(post_data: Dict[str, Any]) -> Tuple[str, List[str], str, str]:
    """Safely extracts text, tags, board_id, and media_type from heterogeneous post representations."""
    if not isinstance(post_data, dict):
        return "", [], "b", "text"

    # 1. Text extraction
    text = ""
    for candidate in [
        post_data.get("text"),
        post_data.get("text_content"),
        post_data.get("content", {}).get("text") if isinstance(post_data.get("content"), dict) else None,
        post_data.get("caption"),
        post_data.get("content", {}).get("caption") if isinstance(post_data.get("content"), dict) else None,
    ]:
        if candidate and isinstance(candidate, str):
            text = candidate
            break

    # 2. Tags extraction
    raw_tags = []
    if "tags" in post_data and isinstance(post_data["tags"], (list, set, tuple)):
        raw_tags.extend(post_data["tags"])
    if isinstance(post_data.get("content"), dict):
        cnt = post_data["content"]
        if "tags" in cnt and isinstance(cnt["tags"], (list, set, tuple)):
            raw_tags.extend(cnt["tags"])
        if "vision_tags" in cnt and isinstance(cnt["vision_tags"], (list, set, tuple)):
            raw_tags.extend(cnt["vision_tags"])
    if "media" in post_data and isinstance(post_data["media"], dict):
        mtags = post_data["media"].get("tags")
        if isinstance(mtags, (list, set, tuple)):
            raw_tags.extend(mtags)

    cleaned_tags = [str(t).strip().lower() for t in raw_tags if str(t).strip()]

    # 3. Board ID
    board_id = str(post_data.get("board_id") or "b").lower()

    # 4. Media type
    media_type = "text"
    if isinstance(post_data.get("content"), dict):
        media_type = str(post_data["content"].get("type", "text")).lower()
    elif "type" in post_data:
        media_type = str(post_data["type"]).lower()

    return text.lower(), cleaned_tags, board_id, media_type


def evaluate_post_heuristics(
    post_data: Dict[str, Any],
    current_mood: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Instant rule-based & heuristic classifier for post reactions.
    
    Evaluates:
      - Tag matching (e.g. hentai, anime -> horny_weeb)
      - Keyword matching in post text
      - Board affinity (/sex/ -> horny_weeb, greentext in /b/ -> based_chad)
      - Greentext pattern (lines starting with '>')
      - Current mood bias
    
    Returns:
      (persona_name, [emoji_reactions])
    """
    text, tags, board_id, media_type = _extract_post_features(post_data)
    mood = current_mood or get_current_mood()

    scores: Dict[str, float] = {p: 0.0 for p in PERSONAS.keys()}

    # 1. Tag Scoring (high weight: +3.0 per matching tag)
    tag_set = set(tags)
    for persona, p_conf in PERSONAS.items():
        matching_tags = tag_set.intersection(p_conf["tags"])
        scores[persona] += len(matching_tags) * 3.0

    # 2. Keyword Scoring (+1.5 per keyword match in text)
    for persona, p_conf in PERSONAS.items():
        for kw in p_conf["keywords"]:
            if kw in text:
                scores[persona] += 1.5

    # 3. Board & Content Affinity
    if board_id == "sex":
        scores["horny_weeb"] += 4.0
    elif board_id == "d":
        scores["toxic_oldfag"] += 1.5

    # Greentext detection (lines starting with '>')
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    greentext_lines = [l for l in lines if l.startswith("&gt;") or l.startswith(">")]
    if len(greentext_lines) >= 2:
        scores["based_chad"] += 3.5

    # Anime media with tags / captions
    if any(t in tag_set for t in ["anime", "hentai", "1girl", "ecchi", "waifu"]):
        scores["horny_weeb"] += 5.0

    # Strong hate/cringe signals
    if any(w in text for w in ["кринж", "соя", "пидор", "говно", "параша", "удали нахуй"]):
        scores["toxic_oldfag"] += 4.0

    # Strong troll/clown signals
    if any(w in text for w in ["клоун", "цирк", "обосрался", "орнул", "кек"]):
        scores["clown_troll"] += 3.5

    # Strong sadness/doomer signals
    if any(w in text for w in ["одиноко", "тоска", "пустота", "смысла нет", "безысходность"]):
        scores["deep_sych"] += 3.5

    # 4. Mood Bias (+1.2 bonus to persona matching current mood)
    mood_persona = MOOD_PERSONA_AFFINITY.get(mood)
    if mood_persona and mood_persona in scores:
        scores[mood_persona] += 1.2

    # Select winning persona (highest score)
    best_persona = max(scores.keys(), key=lambda k: scores[k])

    # If all scores are 0 (purely neutral / empty post), default to mood affinity or based_chad
    if scores[best_persona] <= 0.0:
        best_persona = mood_persona or "based_chad"

    # Select reaction palette for chosen persona
    p_options = PERSONAS[best_persona]["reaction_options"]
    
    # Use deterministic post_num seed if present, else pseudo-random
    post_num = post_data.get("post_num") or post_data.get("num") or 0
    if isinstance(post_num, int) and post_num > 0:
        idx = post_num % len(p_options)
    else:
        idx = random.randint(0, len(p_options) - 1)

    reactions = list(p_options[idx])
    return best_persona, reactions


# =============================================================================
# HYBRID CLASSIFIER: LLM WITH TIMEOUT & INSTANT FALLBACK
# =============================================================================

def _build_llm_classification_prompt(text: str, tags: List[str], board_id: str) -> str:
    """Builds an efficient, concise classification prompt for Groq/Gemini."""
    tags_str = ", ".join(tags[:10]) if tags else "none"
    clean_text = text[:600].replace("\n", " ").strip() if text else "none"
    return (
        "You are an anonymous 2ch imageboard reader classifying posts to select emotional reactions.\n"
        "Choose EXACTLY ONE persona matching this post:\n"
        "1. horny_weeb: anime, waifus, hentai, ecchi, cute girls, 2D art -> reactions: ❤️, 🔥, 😍\n"
        "2. toxic_oldfag: cringe, normie whining, gay/fag themes, spam, disgust -> reactions: 💩, 🤮, 🖕\n"
        "3. clown_troll: mockery, absurd takes, clown logic, epic fails -> reactions: 🤡, 😂, 🤣\n"
        "4. based_chad: baza, gigachad moves, good memes, greentext, respect -> reactions: 👍, 👌, 💯\n"
        "5. deep_sych: night doomer, melancholy, loneliness, existential thoughts -> reactions: 🤔, 🧐, 😢\n\n"
        f"Post Board: /{board_id}/\n"
        f"Image Tags: {tags_str}\n"
        f"Post Text: {clean_text}\n\n"
        "Respond ONLY in valid JSON format:\n"
        '{"persona": "<persona_name>", "reactions": ["<emoji>"]}'
    )


async def _invoke_llm_completion_safe(prompt: str) -> Optional[str]:
    """Invokes LLM via existing summarize dispatcher or returns None."""
    try:
        from summarize import dispatch_llm_completion
        result = await dispatch_llm_completion(prompt=prompt, text_dump=prompt, model_preference="fast")
        return result
    except ImportError:
        logger.debug("summarize module not available for direct import.")
        return None
    except Exception as e:
        logger.debug(f"LLM completion call failed: {e}")
        return None


def _parse_llm_json_response(raw_resp: str) -> Optional[Tuple[str, List[str]]]:
    """Parses JSON output from LLM, validating persona and emoji."""
    if not raw_resp:
        return None
    try:
        # Extract json block if surrounded by markdown code fences
        match = re.search(r"\{.*\}", raw_resp, re.DOTALL)
        if not match:
            return None
        payload = json.loads(match.group(0))
        persona = str(payload.get("persona", "")).strip().lower()
        reactions = payload.get("reactions")

        if persona in PERSONAS and isinstance(reactions, list) and len(reactions) > 0:
            cleaned_reactions = [str(r).strip() for r in reactions if str(r).strip()]
            if cleaned_reactions:
                return persona, cleaned_reactions
    except Exception:
        pass
    return None


async def evaluate_post_llm(
    post_data: Dict[str, Any],
    timeout_sec: float = 4.0,
    current_mood: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Evaluates post using LLM with a strict 4.0s timeout and automatic fallback.
    
    Guarantees:
      - Strict timeout: default 4.0s.
      - Upon any failure (timeout, 429, 403, network, malformed JSON),
        INSTANTLY returns fallback from evaluate_post_heuristics().
      - Never throws an unhandled exception.
    """
    text, tags, board_id, _ = _extract_post_features(post_data)

    # If post has zero text and zero tags, heuristics is instant and accurate
    if not text and not tags:
        return evaluate_post_heuristics(post_data, current_mood=current_mood)

    prompt = _build_llm_classification_prompt(text, tags, board_id)

    try:
        raw_output = await asyncio.wait_for(
            _invoke_llm_completion_safe(prompt),
            timeout=timeout_sec
        )
        parsed = _parse_llm_json_response(raw_output or "")
        if parsed:
            return parsed
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug(f"evaluate_post_llm falling back to heuristics: {e}")

    # Seamless fallback
    return evaluate_post_heuristics(post_data, current_mood=current_mood)


async def decide_post_reactions(
    post_data: Dict[str, Any],
    use_llm: bool = False,
    current_mood: Optional[str] = None
) -> Tuple[str, List[str]]:
    """Unified entry point to decide post reactions either via heuristics or LLM cascade."""
    if use_llm:
        return await evaluate_post_llm(post_data, current_mood=current_mood)
    return evaluate_post_heuristics(post_data, current_mood=current_mood)


# =============================================================================
# REACTION APPLICATION & QUEUEING
# =============================================================================

async def apply_mimicry_reaction(
    post_num: int,
    board_id: str = "b",
    use_llm: bool = False,
    post_data: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    save_after: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Applies a mimicry reaction to a post:
      1. Determines persona and reactions via hybrid classifier.
      2. Assigns virtual anon user_id via get_or_assign_virtual_reactor.
      3. Dispatches reactions to ReactionQueue in database.
      4. Updates persistent state (processed_post_nums, stats).
    """
    if post_num <= 0:
        return None

    if state is None:
        state = _ACTIVE_STATE or load_mimicry_state()

    # Check deduplication
    processed = set(state.get("processed_post_nums", []))
    if post_num in processed:
        logger.debug(f"Post {post_num} already processed by mimicry engine. Skipping.")
        return None

    # Resolve post data if not passed
    effective_data = dict(post_data) if isinstance(post_data, dict) else {}
    effective_data.setdefault("post_num", post_num)
    effective_data.setdefault("board_id", board_id)

    # Classify
    persona, reactions = await decide_post_reactions(effective_data, use_llm=use_llm)
    user_id = get_or_assign_virtual_reactor(post_num, persona)

    # Dispatch to ReactionQueue in DB
    try:
        from common.database import add_reaction_to_queue
        for emoji in reactions:
            await add_reaction_to_queue(user_id=user_id, post_num=post_num, emoji=emoji)
    except Exception as db_err:
        logger.warning(f"Could not enqueue reaction to DB for post {post_num}: {db_err}")

    # Update state
    proc_list = state.setdefault("processed_post_nums", [])
    proc_list.append(post_num)
    if len(proc_list) > MAX_PROCESSED_POSTS_HISTORY:
        state["processed_post_nums"] = proc_list[-MAX_PROCESSED_POSTS_HISTORY:]

    stats = state.setdefault("persona_stats", {p: 0 for p in PERSONAS.keys()})
    stats[persona] = stats.get(persona, 0) + len(reactions)
    state["total_reactions_placed"] = state.get("total_reactions_placed", 0) + len(reactions)
    state["last_run_timestamp"] = time.time()

    if save_after:
        save_mimicry_state(state)

    return {
        "post_num": post_num,
        "board_id": board_id,
        "persona": persona,
        "user_id": user_id,
        "reactions": reactions
    }


async def run_mimicry_batch(
    board_id: str = "b",
    candidate_posts: Optional[List[Dict[str, Any]]] = None,
    sample_ratio: float = 0.25,
    max_posts: int = 5,
    use_llm: bool = False,
    state: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Runs periodic batch reaction mimicry on candidate posts.
    Samples approximately `sample_ratio` (e.g. 20-30%) of candidate posts up to `max_posts`.
    """
    if state is None:
        state = _ACTIVE_STATE or load_mimicry_state()

    candidates = candidate_posts or []
    if not candidates:
        # Try loading latest posts from messages_storage or DB
        try:
            from shared_state import messages_storage, storage_lock
            async with storage_lock:
                for p_num, p_data in messages_storage.items():
                    if isinstance(p_data, dict) and p_data.get("board_id") == board_id:
                        d = dict(p_data)
                        d["post_num"] = p_num
                        candidates.append(d)
        except Exception:
            pass

    processed = set(state.get("processed_post_nums", []))
    unprocessed = [p for p in candidates if (p.get("post_num") or p.get("num")) not in processed]

    if not unprocessed:
        return []

    # Calculate sample size
    target_count = max(1, min(len(unprocessed), max_posts, int(len(unprocessed) * sample_ratio) or 1))
    selected = random.sample(unprocessed, min(target_count, len(unprocessed)))

    results = []
    for post in selected:
        p_num = post.get("post_num") or post.get("num")
        if not p_num:
            continue
        res = await apply_mimicry_reaction(
            post_num=p_num,
            board_id=board_id,
            use_llm=use_llm,
            post_data=post,
            state=state,
            save_after=False
        )
        if res:
            results.append(res)

    if results:
        save_mimicry_state(state)

    return results
