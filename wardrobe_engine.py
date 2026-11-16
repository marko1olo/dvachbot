# -*- coding: utf-8 -*-
"""
wardrobe_engine.py — Dvach Boutique, Avatar Wardrobe & Equipment Engine
4-Tiered Durability & Duration System:
- 🥉 Tier 1: Базовый шмот (7 Дней / 168ч)
- 🥈 Tier 2: Элитный шмот (14 Дней / 336ч)
- 🥇 Tier 3: Легендарный шмот (30 Дней / 720ч)
- 🌟 Tier 4: Лутбокс-Эксклюзив (НАВСЕГДА / Permanent)
Includes dynamic duration stacking, set bonuses, stats and dressing room UI.
"""

import time
import json
from typing import Dict, Any, List, Optional, Tuple, Union

# -----------------------------------------------------------------------------
# Apparel & Wardrobe Catalog
# -----------------------------------------------------------------------------
CLOTHING_CATALOG = {

    # === ГОЛОВНЫЕ УБОРЫ (HATS) ===
    "hat_tinfoil": {
        "id": "hat_tinfoil",
        "slot": "head",
        "tier": 0,
        "name": "👽 Шапочка из фольги",
        "price": 450,
        "duration_days": 0,
        "duration_hours": 6,
        "defense": 35,
        "toxicity": 0,
        "sanity": 20,
        "desc": "Защита от 5G-излучения, грабежа (/rob) и говна (/shit) на 6 часов."
    },
    "hat_bag": {
        "id": "hat_bag",
        "slot": "head",
        "tier": 1,
        "name": "📦 Пакет из Пятерочки",
        "price": 120,
        "duration_days": 7,
        "duration_hours": 168,
        "defense": 15,
        "toxicity": 5,
        "sanity": 5,
        "desc": "Пакет с дырками для глаз. Дает 8% шанс выбить бесплатный кейс на работе."
    },
    "hat_crown": {
        "id": "hat_crown",
        "slot": "head",
        "tier": 2,
        "name": "👑 Корона VIP-Сыча",
        "price": 350,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 10,
        "toxicity": 15,
        "sanity": 10,
        "desc": "VIP-статус на 14 дней. Дает +20% к чаевым на всех сменах /work."
    },
    "hat_cat_ears": {
        "id": "hat_cat_ears",
        "slot": "head",
        "tier": 2,
        "name": "🐱 Неко-Ушки (Аниме)",
        "price": 250,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 5,
        "toxicity": -10,
        "sanity": 30,
        "desc": "Пушистые ушки на 14 дней. +30 к Рассудку и стилю в карточке персонажа."
    },
    "hat_helmet": {
        "id": "hat_helmet",
        "slot": "head",
        "tier": 3,
        "name": "🪖 Шлем ОМОНа",
        "price": 600,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 45,
        "toxicity": 20,
        "sanity": 15,
        "desc": "Титановая броня на 30 дней. 0 штрафов на работе и -50% времени мута."
    },
    "hat_tophat": {
        "id": "hat_tophat",
        "slot": "head",
        "tier": 3,
        "name": "🎩 Цилиндр Джентльмена",
        "price": 500,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 10,
        "toxicity": 10,
        "sanity": 25,
        "desc": "Викторианский цилиндр на 30 дней. +25 к Рассудку и аристократичности."
    },
    "hat_golden_foil": {
        "id": "hat_golden_foil",
        "slot": "head",
        "tier": 4,
        "name": "👑 Золотая шапочка из фольги",
        "price": 1000,
        "duration_days": 0,
        "duration_hours": 0,
        "defense": 50,
        "toxicity": 0,
        "sanity": 50,
        "non_buyable": True,
        "desc": "Уникальный мифический артефакт навсегда. Пассивная защита от грабежа (+25%) и шизо-таблеток."
    },
    "hat_cyber_ushanka": {
        "id": "hat_cyber_ushanka",
        "slot": "head",
        "tier": 4,
        "name": "🛸 Кибер-Ушанка",
        "price": 800,
        "duration_days": 0,
        "duration_hours": 0,
        "defense": 30,
        "toxicity": 15,
        "sanity": 30,
        "non_buyable": True,
        "desc": "Неоновая ушанка силовика будущего навсегда. +30 к Защите и Рассудку, иммунитет к поносу /curse."
    },
    "hat_golden_crown": {
        "id": "hat_golden_crown",
        "slot": "head",
        "tier": 5,
        "name": "👑 Золотая Корона Олигарха",
        "price": 50000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 40,
        "toxicity": 10,
        "sanity": 45,
        "desc": "Корона из червонного золота с сапфирами на 30 дней. +40 к Защите, +45 к Рассудку, статус 👑👑 и +30% к чаевым на /work."
    },

    # === ОДЕЖДА И ТОРС (TORSO / BODY) ===
    "body_tracksuit": {
        "id": "body_tracksuit",
        "slot": "torso",
        "tier": 1,
        "name": "🩲 Обоссанные треники",
        "price": 180,
        "duration_days": 7,
        "duration_hours": 168,
        "defense": 10,
        "toxicity": 30,
        "sanity": -10,
        "desc": "Три полоски на 7 дней. x2 шанс дропа лута и 25% шанс испуга грабителя."
    },
    "body_wasserman": {
        "id": "body_wasserman",
        "slot": "torso",
        "tier": 2,
        "name": "🦺 Жилетка Вассермана",
        "price": 400,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 25,
        "toxicity": 5,
        "sanity": 35,
        "desc": "28 карманов на 14 дней. Дает +25% к зарплате во всех сменах /work."
    },
    "body_hoodie": {
        "id": "body_hoodie",
        "slot": "torso",
        "tier": 2,
        "name": "👘 Худи с Аской Лэнгли",
        "price": 350,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 15,
        "toxicity": 10,
        "sanity": 25,
        "desc": "Толстовка на 14 дней. +25 к Рассудку и олдфажный дух борды."
    },
    "body_straitjacket": {
        "id": "body_straitjacket",
        "slot": "torso",
        "tier": 2,
        "name": "🥼 Смирительная рубашка",
        "price": 220,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 20,
        "toxicity": 40,
        "sanity": -25,
        "desc": "Рубашка из дурки на 14 дней. +40 к Токсичности постов."
    },
    "body_cloak": {
        "id": "body_cloak",
        "slot": "torso",
        "tier": 3,
        "name": "🧥 Плащ Нео / Анонима",
        "price": 550,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 30,
        "toxicity": 15,
        "sanity": 20,
        "desc": "Кожаный плащ на 30 дней. +30 к Защите и скрытности в киберпространстве."
    },
    "body_dva_ch_mantle": {
        "id": "body_dva_ch_mantle",
        "slot": "torso",
        "tier": 4,
        "name": "👘 Мантия Олдфага (Балахон /b/)",
        "price": 900,
        "duration_days": 0,
        "duration_hours": 0,
        "defense": 35,
        "toxicity": 20,
        "sanity": 50,
        "non_buyable": True,
        "desc": "Олдфажный балахон двачера навсегда. +50 к Рассудку, скрывает баланс от грабителей."
    },
    "body_padishah_mantle": {
        "id": "body_padishah_mantle",
        "slot": "torso",
        "tier": 4,
        "name": "🦹 Мантия Падишаха",
        "price": 2000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 45,
        "toxicity": 10,
        "sanity": 30,
        "non_buyable": True,
        "desc": "Роскошная мантия из чистого золота. +45 к Защите, 50% шанс отражения грабежей /rob."
    },
    "body_sheikh_mantle": {
        "id": "body_sheikh_mantle",
        "slot": "torso",
        "tier": 5,
        "name": "🦹 Мантия Золотого Падишаха",
        "price": 100000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 60,
        "toxicity": 5,
        "sanity": 50,
        "desc": "Царская мантия из золотой парчи на 30 дней. +60 к Защите, +50 к Рассудку, скрывает баланс и 50% шанс отражения грабежей /rob."
    },
    "body_cyber_suit": {
        "id": "body_cyber_suit",
        "slot": "torso",
        "tier": 5,
        "name": "🦾 Эксклюзивный Кибер-Костюм",
        "price": 125000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 70,
        "toxicity": 20,
        "sanity": 60,
        "desc": "Титановый боевой экзоскелет на 30 дней. +70 к Защите, +60 к Рассудку, 0 штрафов на работе и полный стелс баланса."
    },

    # === ЛИЦО И ОЧКИ (FACE / GLASSES) ===
    "face_clown_nose": {
        "id": "face_clown_nose",
        "slot": "face",
        "tier": 1,
        "name": "🤡 Клоунский Нос",
        "price": 150,
        "duration_days": 7,
        "duration_hours": 168,
        "defense": 0,
        "toxicity": 35,
        "sanity": -15,
        "desc": "Красный нос на 7 дней. +35 к Токсичности и троллингу в тредах."
    },
    "face_thug_glasses": {
        "id": "face_thug_glasses",
        "slot": "face",
        "tier": 1,
        "name": "🕶️ Очки Thug Life (2ch)",
        "price": 200,
        "duration_days": 7,
        "duration_hours": 168,
        "defense": 5,
        "toxicity": 20,
        "sanity": 15,
        "desc": "Пиксельные очки на 7 дней. +5% к выигрышу в казино и слотах 777."
    },
    "face_wasserman_glasses": {
        "id": "face_wasserman_glasses",
        "slot": "face",
        "tier": 2,
        "name": "🥽 Очки Онотоле (Вассермана)",
        "price": 250,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 10,
        "toxicity": 0,
        "sanity": 30,
        "desc": "Очки эрудита на 14 дней. +15% к зарплате в интеллектуальных сменах /work."
    },
    "face_anon_mask": {
        "id": "face_anon_mask",
        "slot": "face",
        "tier": 3,
        "name": "🎭 Маска Анонимуса (Гая Фокса)",
        "price": 300,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 20,
        "toxicity": 10,
        "sanity": 10,
        "desc": "Маска на 30 дней. Скрывает баланс в карточке персонажа от глаз налётчиков."
    },
    "face_monocle": {
        "id": "face_monocle",
        "slot": "face",
        "tier": 4,
        "name": "⚜️ Платиновый Монокль",
        "price": 1500,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 10,
        "toxicity": 0,
        "sanity": 50,
        "non_buyable": True,
        "desc": "Платиновый монокль олигарха. +50 к Рассудку, бейдж [⚜️ Олигарх] в заголовке постов."
    },
    "face_cyber_visor": {
        "id": "face_cyber_visor",
        "slot": "face",
        "tier": 5,
        "name": "🥽 Эксклюзивный Кибер-Визор",
        "price": 35000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 25,
        "toxicity": 15,
        "sanity": 40,
        "desc": "Неоновый визор кибер-синдиката на 30 дней. +25 к Защите, +40 к Рассудку, +15% к победам в казино и бейдж 🥽."
    },

    # === ОБУВЬ И ПЕДАЛИ (FEET / SHOES) ===
    "feet_slippers": {
        "id": "feet_slippers",
        "slot": "feet",
        "tier": 1,
        "name": "🩴 Сланцы с носками",
        "price": 150,
        "duration_days": 7,
        "duration_hours": 168,
        "defense": 5,
        "toxicity": 15,
        "sanity": 5,
        "desc": "Домашний уют на 7 дней. Сокращает кулдаун смен /work на 20%."
    },
    "feet_boots": {
        "id": "feet_boots",
        "slot": "feet",
        "tier": 2,
        "name": "🥾 Берцы ОМОНа",
        "price": 350,
        "duration_days": 14,
        "duration_hours": 336,
        "defense": 25,
        "toxicity": 15,
        "sanity": 10,
        "desc": "Армейские берцы на 14 дней. Полный иммунитет к броскам говна /shit."
    },
    "feet_sneakers": {
        "id": "feet_sneakers",
        "slot": "feet",
        "tier": 3,
        "name": "👟 Стоптанные берцы (Тяги битарда)",
        "price": 400,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 15,
        "toxicity": 10,
        "sanity": 20,
        "desc": "Стоптанные берцы на 30 дней. 30% шанс успешно съебать при облаве пативэна /partyvan."
    }
    ,
    "feet_golden_sneakers": {
        "id": "feet_golden_sneakers",
        "slot": "feet",
        "tier": 5,
        "name": "👟 Золотые Тяги Олигарха",
        "price": 75000,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 30,
        "toxicity": 10,
        "sanity": 35,
        "desc": "Бархатные тяги с позолотой на 30 дней. +30 к Защите, 40% шанс уворота от /partyvan и /shoot, сокращение кулдауна /work на 30%."
    }
}

WARDROBE_CATALOG = CLOTHING_CATALOG

# -----------------------------------------------------------------------------
# SET BONUSES
# -----------------------------------------------------------------------------
SET_BONUSES = {
    "set_wasserman": {
        "id": "set_wasserman",
        "name": "🦺 Сет «Анатолий Вассерман / Онотоле»",
        "items": ["body_wasserman", "face_wasserman_glasses"],
        "bonus_desc": "+40% к зарплате на всех сменах /work и полный иммунитет к проклятию шизы.",
        "short_desc": "+40% ЗП, иммунитет к шизе",
        "salary_mult": 1.40,
        "schizo_immunity": True,
        "bonus_defense": 20,
        "bonus_sanity": 30
    },
    "set_riot_police": {
        "id": "set_riot_police",
        "name": "🪖 Сет «Силовик ОМОНа»",
        "items": ["hat_helmet", "feet_boots"],
        "bonus_desc": "-70% ко времени мута от выстрела, 0 штрафов на работе и иммунитет к говну.",
        "short_desc": "-70% мут, 0 штрафов, иммун к говну",
        "mute_reduction_pct": 70,
        "shit_immunity": True,
        "work_fine_immunity": True,
        "bonus_defense": 35
    },
    "set_anime_hikka": {
        "id": "set_anime_hikka",
        "name": "👘 Сет «Труъ-Хикка Анимешник»",
        "items": ["hat_cat_ears", "body_hoodie"],
        "bonus_desc": "+50 к Рассудку персонажа и 2x шанс выпадения редких лутбоксов на работе.",
        "short_desc": "+50 Рассудок, 2x лутбоксы",
        "lootbox_2x_chance": True,
        "bonus_sanity": 50,
        "bonus_toxicity": -15
    },
    "set_gop_skuf": {
        "id": "set_gop_skuf",
        "name": "🩲 Сет «Подъездный Сыч»",
        "items": ["hat_crown", "body_tracksuit"],
        "bonus_desc": "40% шанс отпугнуть грабителя в /rob и +35% к чаевым на работе.",
        "short_desc": "40% испуг /rob, +35% чаевые",
        "rob_fear_chance": 0.40,
        "tips_mult": 1.35,
        "bonus_toxicity": 25
    },
    "set_ward6": {
        "id": "set_ward6",
        "name": "🥼 Сет «Палата №6 / Шизофреник»",
        "items": ["body_straitjacket", "hat_tinfoil"],
        "bonus_desc": "Абсолютная невосприимчивость к Слабительному и Шизо-таблеткам.",
        "short_desc": "Иммунитет к слабительному и шизе",
        "laxative_immunity": True,
        "schizo_immunity": True,
        "bonus_toxicity": 40
    },
    "set_neo": {
        "id": "set_neo",
        "name": "🕶️ Сет «Избранный / Нео»",
        "items": ["body_cloak", "face_anon_mask"],
        "bonus_desc": "+50 к Защите, скрытность баланса от налётов, +25% к ЗП на работе и +20% к выигрышу в казино.",
        "short_desc": "+50 Защита, скрытность, +25% ЗП, +20% казино",
        "salary_mult": 1.25,
        "casino_bonus_pct": 20,
        "stealth": True,
        "bonus_defense": 50,
        "bonus_sanity": 30
    }
    ,
    "set_oligarch": {
        "id": "set_oligarch",
        "name": "👑 Сет «Шекелевый Олигарх»",
        "items": ["hat_golden_crown", "body_sheikh_mantle"],
        "bonus_desc": "+50 к Защите, скрытность от налётов, 50% шанс отражения /rob, +30% к зарплате /work и королевский статус 👑👑 в постах.",
        "short_desc": "+50 Защита, скрытность, 50% отражение /rob, +30% ЗП",
        "salary_mult": 1.30,
        "stealth": True,
        "bonus_defense": 50,
        "bonus_sanity": 50
    },
    "set_cyber_syndicate": {
        "id": "set_cyber_syndicate",
        "name": "🛸 Сет «Кибер-Синдикат»",
        "items": ["face_cyber_visor", "body_cyber_suit"],
        "bonus_desc": "+50 к Защите, 50% уворот от пативэна, +25% казино, стелс и статус 🛸 в постах.",
        "short_desc": "+50 Защита, 50% уворот, +25% казино, стелс",
        "evasion_chance": 0.50,
        "casino_bonus_pct": 25,
        "stealth": True,
        "bonus_defense": 50,
        "bonus_sanity": 40
    }
}

SET_ACHIEVEMENT_MAP = {
    "set_wasserman": "ach_set_wasserman",
    "set_riot_police": "ach_set_riot",
    "set_anime_hikka": "ach_set_anime",
    "set_gop_skuf": "ach_set_skuf",
    "set_ward6": "ach_set_ward6",
    "set_neo": "ach_set_neo",
}


def get_active_set_bonus(active_items: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns the primary active set bonus or None."""
    sets = get_active_set_bonuses(active_items)
    return sets[0] if sets else None


def add_item_duration(active_items: Dict[str, Any], item_id: str, dur_hours: int, is_permanent: bool = False):
    """
    Stacks duration cleanly onto active_items.
    """
    now = int(time.time())
    active_items[f"owned_{item_id}"] = True

    if is_permanent:
        active_items[f"{item_id}_is_permanent"] = True
        active_items.pop(f"{item_id}_expires", None)
        return

    if active_items.get(f"{item_id}_is_permanent"):
        return  # Already permanent, no need to add timer

    current_exp = active_items.get(f"{item_id}_expires", 0)
    base_start = current_exp if current_exp > now else now
    active_items[f"{item_id}_expires"] = base_start + dur_hours * 3600


def _safe_dict_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """Safely extracts a mutable dictionary from dict or JSON string payload, or returns None."""
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
        return None
    if isinstance(payload, dict):
        return payload
    return None


def get_equipped_gear(active_items: Any, current_time: Optional[int] = None) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Extracts currently equipped wardrobe items from active_items dictionary across all slots.
    """
    equipped = {
        "head": None,
        "torso": None,
        "face": None,
        "feet": None
    }
    items_dict = _safe_dict_payload(active_items)
    if not items_dict:
        return equipped

    now = int(time.time()) if current_time is None else int(current_time)

    for slot in equipped.keys():
        eq_id = items_dict.get(f"equipped_{slot}")
        if eq_id and isinstance(eq_id, str) and eq_id in CLOTHING_CATALOG:
            is_perm = items_dict.get(f"{eq_id}_is_permanent", False)
            expires = items_dict.get(f"{eq_id}_expires", 0)
            has_exp = f"{eq_id}_expires" in items_dict
            if is_perm or (expires > now if has_exp else True):
                equipped[slot] = CLOTHING_CATALOG[eq_id]
            else:
                items_dict.pop(f"equipped_{slot}", None)

    return equipped


def get_wardrobe_total_stats(active_items: Optional[Any], current_time: Optional[int] = None) -> Dict[str, Any]:
    """
    Единый авторитетный расчет всех боевых, экономических и социальных характеристик
    экипированного гардероба с обязательной валидацией срока годности (is_permanent or expires > now).
    """
    default_stats = {
        "total_defense": 0,
        "total_toxicity": 0,
        "total_sanity": 0,
        "rob_deflect_chance": 0.0,
        "rob_stolen_reduction_pct": 0.0,
        "rob_fear_chance": 0.0,
        "evasion_chance": 0.0,
        "mute_reduction_pct": 0,
        "debuff_reduction_pct": 0.0,
        "shit_immunity": False,
        "laxative_immunity": False,
        "schizo_immunity": False,
        "work_fine_immunity": False,
        "salary_mult": 1.0,
        "tips_mult": 1.0,
        "cooldown_mult": 1.0,
        "lootbox_flat_chance": 0.0,
        "lootbox_drop_mult": 1.0,
        "casino_bonus_pct": 0,
        "compact_post_icon": "",
        "stealth_profile": False,
        "active_set_name": None,
        "active_set_desc": None,
        "equipped_items_summary": "(Ничего не надето)"
    }

    items_dict = _safe_dict_payload(active_items)
    if not items_dict:
        return default_stats

    now = int(time.time()) if current_time is None else int(current_time)

    # 1. Determine active equipped items (TTL validation: is_permanent or expires > now)
    equipped: Dict[str, Dict[str, Any]] = {}
    for slot in ("head", "torso", "face", "feet"):
        item_id = items_dict.get(f"equipped_{slot}")
        if item_id and isinstance(item_id, str) and item_id in CLOTHING_CATALOG:
            is_perm = items_dict.get(f"{item_id}_is_permanent", False)
            expires = items_dict.get(f"{item_id}_expires", 0)
            has_exp = f"{item_id}_expires" in items_dict
            if is_perm or (expires > now if has_exp else True):
                equipped[slot] = CLOTHING_CATALOG[item_id]
            else:
                items_dict.pop(f"equipped_{slot}", None)


    # 2. Identify active sets
    equipped_ids = {item["id"] for item in equipped.values()}
    active_sets = []
    for set_id, set_info in SET_BONUSES.items():
        if set_id == "set_neo":
            if "body_cloak" in equipped_ids and bool({"face_anon_mask", "face_thug_glasses"} & equipped_ids):
                active_sets.append(set_info)
        else:
            if all(req in equipped_ids for req in set_info["items"]):
                active_sets.append(set_info)

    primary_set = active_sets[0] if active_sets else None
    active_set_ids = {s.get("id") for s in active_sets}

    # 3. Sum RPG Stats
    tot_def = 0
    for item in equipped.values():
        item_id = item.get("id")
        dur = items_dict.get(f"{item_id}_durability")
        if isinstance(items_dict.get(item_id), dict):
            dur = items_dict[item_id].get("durability", dur)
        is_broken = (
            items_dict.get(f"{item_id}_broken", False)
            or (dur is not None and float(dur) <= 0.0)
            or (isinstance(items_dict.get(item_id), dict) and items_dict[item_id].get("broken", False))
        )
        if not is_broken:
            tot_def += item.get("defense", 0)
    tot_tox = sum(item.get("toxicity", 0) for item in equipped.values())
    tot_san = sum(item.get("sanity", 0) for item in equipped.values())
    for s in active_sets:
        tot_def += s.get("bonus_defense", s.get("defense", 0))
        tot_tox += s.get("bonus_toxicity", s.get("toxicity", 0))
        tot_san += s.get("bonus_sanity", s.get("sanity", 0))

    # 4. Robbery formulas
    has_padishah = bool(equipped.get("torso") and equipped["torso"]["id"] in ("body_padishah_mantle", "body_sheikh_mantle"))
    has_golden_foil = bool(equipped.get("head") and equipped["head"]["id"] == "hat_golden_foil")

    # Scaled deflection formula
    # Deflection scaling: rob_deflect = min(0.75, max(0.0, round(tot_def * 0.005, 4)))
    # If set bonus is active (e.g. bonus_defense > 0 or tier set), allow deflect up to 0.85 (85%)
    has_set_bonus = bool(active_sets and len(active_sets) > 0)
    max_deflect_cap = 0.85 if has_set_bonus else 0.75

    rob_deflect = min(max_deflect_cap, max(0.0, round(tot_def * 0.005, 4)))
    if has_golden_foil:
        rob_deflect = max(rob_deflect, 0.25)
    if has_padishah:
        rob_deflect = max(rob_deflect, 0.50)
    rob_deflect = min(max_deflect_cap, rob_deflect)

    # stolen_reduction = min(0.60, max(0.0, Def / 200.0))
    rob_stolen_red = min(0.60, max(0.0, round(tot_def / 200.0, 4)))
    # fear chance: 40% for set_gop_skuf, 25% for body_tracksuit
    has_skuf_set = bool("set_gop_skuf" in active_set_ids or "set_skuf" in active_set_ids)
    has_tracksuit = bool(equipped.get("torso") and equipped["torso"]["id"] == "body_tracksuit")
    rob_fear = 0.40 if has_skuf_set else (0.25 if has_tracksuit else 0.0)

    # 5. Combat evasion & mute reduction
    has_golden_sneakers = bool(equipped.get("feet") and equipped["feet"]["id"] == "feet_golden_sneakers")
    has_sneakers = bool(equipped.get("feet") and equipped["feet"]["id"] in ("feet_sneakers", "feet_golden_sneakers"))
    evasion = 0.40 if has_golden_sneakers else (0.30 if has_sneakers else 0.0)
    for s in active_sets:
        if s.get("evasion_chance"):
            evasion = max(evasion, s["evasion_chance"])

    has_riot_set = bool("set_riot_police" in active_set_ids or "set_omon" in active_set_ids)
    has_helmet = bool(equipped.get("head") and equipped["head"]["id"] == "hat_helmet")
    mute_red = 70 if has_riot_set else (50 if has_helmet else 0)

    # 6. Debuff reduction & Immunities
    # debuff_reduction_pct = min(0.60, max(0, Sanity) * 0.006)
    debuff_red = min(0.60, round(max(0, tot_san) * 0.006, 4))
    has_boots = bool(equipped.get("feet") and equipped["feet"]["id"] == "feet_boots")
    has_golden_foil = bool(equipped.get("head") and equipped["head"]["id"] == "hat_golden_foil")
    shit_imm = bool(has_boots or has_riot_set or has_golden_foil)

    has_ward6 = bool("set_ward6" in active_set_ids)
    has_wasserman = bool("set_wasserman" in active_set_ids or "set_onotole" in active_set_ids)
    lax_imm = bool(has_ward6)
    schizo_imm = bool(has_ward6 or has_wasserman or has_golden_foil)
    has_cyber_suit = bool(equipped.get("torso") and equipped["torso"]["id"] == "body_cyber_suit")
    work_fine_imm = bool(has_helmet or has_riot_set or has_cyber_suit)

    # 7. Work bonuses
    has_neo = bool("set_neo" in active_set_ids)
    if has_wasserman:
        sal_mult = 1.40
    else:
        bonus = 0.0
        if equipped.get("torso") and equipped["torso"]["id"] == "body_wasserman":
            bonus += 0.25
        if equipped.get("face") and equipped["face"]["id"] == "face_wasserman_glasses":
            bonus += 0.15
        sal_mult = round(1.0 + bonus, 2)

    if has_neo:
        sal_mult = round(sal_mult + 0.25, 2)
    for s in active_sets:
        if s.get("salary_mult") and s.get("id") not in ("set_wasserman", "set_neo"):
            sal_mult = round(sal_mult + (s["salary_mult"] - 1.0), 2)

    has_golden_crown = bool(equipped.get("head") and equipped["head"]["id"] == "hat_golden_crown")
    if has_skuf_set:
        tips_mult = 1.35
    elif has_golden_crown:
        tips_mult = 1.30
    elif equipped.get("head") and equipped["head"]["id"] == "hat_crown":
        tips_mult = 1.20
    else:
        tips_mult = 1.0

    has_golden_sneakers = bool(equipped.get("feet") and equipped["feet"]["id"] == "feet_golden_sneakers")
    has_slippers = bool(equipped.get("feet") and equipped["feet"]["id"] in ("feet_slippers", "feet_golden_sneakers"))
    cool_mult = 0.70 if has_golden_sneakers else (0.80 if has_slippers else 1.0)

    has_bag = bool(equipped.get("head") and equipped["head"]["id"] == "hat_bag")
    loot_flat = 0.08 if has_bag else 0.0

    has_hikka = bool("set_anime_hikka" in active_set_ids or "set_anime" in active_set_ids)
    loot_mult = 2.0 if has_hikka else 1.0

    has_thug = bool(equipped.get("face") and equipped["face"]["id"] == "face_thug_glasses")
    has_visor = bool(equipped.get("face") and equipped["face"]["id"] == "face_cyber_visor")
    casino_bonus = 20 if has_neo else (15 if has_visor else (5 if has_thug else 0))
    for s in active_sets:
        if s.get("casino_bonus_pct"):
            casino_bonus = max(casino_bonus, s["casino_bonus_pct"])

    # 8. Social visibility icon
    set_icons = {
        "set_wasserman": "🦺 ",
        "set_riot_police": "🪖 ",
        "set_anime_hikka": "🐱 ",
        "set_gop_skuf": "👑 ",
        "set_ward6": "🥼 ",
        "set_neo": "🕶️ ",
        "set_oligarch": "👑👑 ",
        "set_cyber_syndicate": "🛸 ",
    }
    head_icons = {
        "hat_tinfoil": "👽 ",
        "hat_crown": "👑 ",
        "hat_golden_crown": "👑👑 ",
        "hat_cat_ears": "🐱 ",
        "hat_helmet": "🪖 ",
        "hat_tophat": "🎩 ",
        "hat_bag": "📦 ",
        "hat_golden_foil": "👑 ",
        "hat_cyber_ushanka": "🛸 ",
        "face_anon_mask": "🎭 ",
        "face_clown_nose": "🤡 ",
        "face_thug_glasses": "🕶️ ",
        "face_monocle": "⚜️ ",
        "face_cyber_visor": "🥽 ",
    }
    compact_icon = ""
    if primary_set and primary_set.get("id") in set_icons:
        compact_icon = set_icons[primary_set["id"]]
    elif equipped.get("head") and equipped["head"]["id"] in head_icons:
        compact_icon = head_icons[equipped["head"]["id"]]
    elif equipped.get("face") and equipped["face"]["id"] in head_icons:
        compact_icon = head_icons[equipped["face"]["id"]]

    has_anon_mask = bool(equipped.get("face") and equipped["face"]["id"] == "face_anon_mask")
    has_mantle = bool(equipped.get("torso") and equipped["torso"]["id"] in ("body_dva_ch_mantle", "body_padishah_mantle", "body_sheikh_mantle", "body_cyber_suit"))
    stealth = bool(has_anon_mask or has_neo or has_mantle or any(s.get("stealth") for s in active_sets))

    eq_summary_parts = [item["name"] for item in equipped.values()]
    eq_summary = ", ".join(eq_summary_parts) if eq_summary_parts else "(Ничего не надето)"

    return {
        "total_defense": tot_def,
        "total_toxicity": tot_tox,
        "total_sanity": tot_san,
        "rob_deflect_chance": rob_deflect,
        "rob_stolen_reduction_pct": rob_stolen_red,
        "rob_fear_chance": rob_fear,
        "evasion_chance": evasion,
        "mute_reduction_pct": mute_red,
        "debuff_reduction_pct": debuff_red,
        "shit_immunity": shit_imm,
        "laxative_immunity": lax_imm,
        "schizo_immunity": schizo_imm,
        "work_fine_immunity": work_fine_imm,
        "salary_mult": sal_mult,
        "tips_mult": tips_mult,
        "cooldown_mult": cool_mult,
        "lootbox_flat_chance": loot_flat,
        "lootbox_drop_mult": loot_mult,
        "casino_bonus_pct": casino_bonus,
        "compact_post_icon": compact_icon,
        "stealth_profile": stealth,
        "active_set_name": primary_set["name"] if primary_set else None,
        "active_set_desc": primary_set.get("bonus_desc") if primary_set else None,
        "equipped_items_summary": eq_summary,
    }


def get_active_set_bonuses(active_items: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Checks if equipped gear forms any complete sets and returns active bonuses.
    """
    equipped = get_equipped_gear(active_items)
    equipped_ids = {item["id"] for item in equipped.values() if item}

    active_sets = []
    for set_id, set_info in SET_BONUSES.items():
        if set_id == "set_neo":
            if "body_cloak" in equipped_ids and bool({"face_anon_mask", "face_thug_glasses"} & equipped_ids):
                active_sets.append(set_info)
        else:
            if all(req_item in equipped_ids for req_item in set_info["items"]):
                active_sets.append(set_info)
    return active_sets


def get_owned_wardrobe_items(active_items: Any) -> List[Dict[str, Any]]:
    """
    Returns a list of all unexpired/permanent clothing items owned by the user.
    """
    items_dict = _safe_dict_payload(active_items)
    if not items_dict:
        return []

    now = int(time.time())
    owned = []
    for item_id, item_info in CLOTHING_CATALOG.items():
        is_owned = items_dict.get(f"owned_{item_id}", False)
        is_perm = items_dict.get(f"{item_id}_is_permanent", False)
        expires = items_dict.get(f"{item_id}_expires", 0)

        # Check active ownership
        if is_owned and (is_perm or expires > now):
            info = dict(item_info)
            info["is_equipped"] = (
                items_dict.get(f"equipped_{item_info['slot']}") == item_id
            )
            info["is_permanent"] = is_perm
            if is_perm:
                info["duration_label"] = "🌟 Навсегда"
            else:
                rem_sec = expires - now
                days = rem_sec // 86400
                hours = (rem_sec % 86400) // 3600
                mins = (rem_sec % 3600) // 60
                if days >= 1:
                    info["duration_label"] = f"{days}д {hours}ч"
                elif hours >= 1:
                    info["duration_label"] = f"{hours}ч {mins}м"
                else:
                    info["duration_label"] = f"{mins} мин"
            owned.append(info)
    return owned


def _normalize_item_text(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _find_clothing_item(query: str) -> Tuple[Optional[str], Optional[dict]]:
    if not query:
        return None, None
    if query in CLOTHING_CATALOG:
        return query, CLOTHING_CATALOG[query]
    q_norm = _normalize_item_text(query)
    for cid, cinfo in CLOTHING_CATALOG.items():
        c_norm = _normalize_item_text(cinfo.get("name", ""))
        cid_norm = _normalize_item_text(cid)
        if q_norm == cid_norm or q_norm == c_norm or (len(q_norm) >= 3 and (q_norm in c_norm or c_norm in q_norm or q_norm in cid_norm)):
            return cid, cinfo
    return None, None


def equip_item(active_items: Any, item_id: str) -> Tuple[bool, str]:
    """
    Equips an owned item into its respective slot.
    """
    if not isinstance(active_items, dict):
        return False, "Неверный формат инвентаря."

    item = CLOTHING_CATALOG.get(item_id)
    if not item:
        resolved_id, resolved_item = _find_clothing_item(item_id)
        if resolved_item:
            item_id = resolved_id
            item = resolved_item
    if not item:
        return False, "Предмет не найден в каталоге."

    slot = item["slot"]
    now = int(time.time())
    is_perm = bool(active_items.get(f"{item_id}_is_permanent", False))
    expires = active_items.get(f"{item_id}_expires", 0)
    has_exp = f"{item_id}_expires" in active_items

    if not is_perm:
        if has_exp and expires <= now:
            return False, "Срок действия этого предмета истек! Продли его в Бутике одежды."
        if not has_exp and item.get("duration_hours", 0) > 0 and not active_items.get(f"owned_{item_id}"):
            return False, "У тебя нет этого предмета в гардеробе."

    if not active_items.get(f"owned_{item_id}") and not is_perm:
        return False, "У тебя нет этого предмета в гардеробе."

    active_items[f"equipped_{slot}"] = item_id

    # Check if a set bonus was activated
    sets = get_active_set_bonuses(active_items)
    set_note = ""
    for s in sets:
        in_set = (item_id in s["items"]) or (s.get("id") == "set_neo" and item_id in ("body_cloak", "face_anon_mask", "face_thug_glasses"))
        if in_set:
            bonus_short = s.get("short_desc") or s.get("bonus_desc", "")
            set_note = f"\n✨ СЕТ: {s['name']}! {bonus_short}"

            # Unlock set achievement
            target_ach = SET_ACHIEVEMENT_MAP.get(s["id"])
            if target_ach:
                import achievements_engine
                unlocked, ach_info = achievements_engine.check_and_unlock_achievement(active_items, target_ach)
                if unlocked and ach_info:
                    set_note += f"\n🏆 Достижение: {ach_info['name']}!"

    msg = f"Ты успешно надел <b>{item['name']}</b>!{set_note}"
    if len(msg) > 190:
        msg = msg[:187] + "..."
    return True, msg


SLOT_SYNONYMS: Dict[str, str] = {
    "head": "head",
    "голова": "head",
    "шапка": "head",
    "шляпа": "head",
    "головной_убор": "head",
    "torso": "torso",
    "торс": "torso",
    "тело": "torso",
    "body": "torso",
    "одежда": "torso",
    "туловище": "torso",
    "face": "face",
    "лицо": "face",
    "очки": "face",
    "маска": "face",
    "feet": "feet",
    "обувь": "feet",
    "ноги": "feet",
    "ботинки": "feet",
    "тапки": "feet",
    "педали": "feet",
    "сапоги": "feet",
    "boots": "feet",
}


def unequip_slot(active_items: Any, slot: str) -> Tuple[bool, str]:
    """
    Unequips whatever is in the specified slot ('head', 'torso', 'face', 'feet') or matching item.
    """
    if not isinstance(active_items, dict):
        return False, "Неверный формат инвентаря."
    target = slot.lower().strip().replace("-", "_").replace(" ", "_")
    if target in SLOT_SYNONYMS:
        slot_key = SLOT_SYNONYMS[target]
    elif target in CLOTHING_CATALOG:
        slot_key = CLOTHING_CATALOG[target]["slot"]
        if active_items.get(f"equipped_{slot_key}") != target:
            return False, f"Предмет <b>{CLOTHING_CATALOG[target]['name']}</b> сейчас не надет."
    else:
        found_id, found_item = _find_clothing_item(slot)
        if found_id and found_item:
            slot_key = found_item["slot"]
            if active_items.get(f"equipped_{slot_key}") != found_id:
                return False, f"Предмет <b>{found_item['name']}</b> сейчас не надет."
        else:
            return False, "Неверный слот или название предмета экипировки."

    current = active_items.pop(f"equipped_{slot_key}", None)
    if current and current in CLOTHING_CATALOG:
        return True, f"Ты снял <b>{CLOTHING_CATALOG[current]['name']}</b>."
    return True, "Слот очищен."


def check_wardrobe_set_achievements(active_items: Any) -> List[Dict[str, Any]]:
    """
    Checks all active set bonuses and unlocks corresponding wardrobe achievements.
    Returns list of newly unlocked achievements.
    """
    if not isinstance(active_items, dict):
        return []
    sets = get_active_set_bonuses(active_items)
    unlocked_achievements = []
    import achievements_engine
    for s in sets:
        target_ach = SET_ACHIEVEMENT_MAP.get(s["id"])
        if target_ach:
            unlocked, ach_info = achievements_engine.check_and_unlock_achievement(active_items, target_ach)
            if unlocked and ach_info:
                unlocked_achievements.append(ach_info)
    return unlocked_achievements


# -----------------------------------------------------------------------------
def check_wardrobe_collection_achievements(active_items: Any) -> List[Dict[str, Any]]:
    """
    Checks wardrobe collection size (5+, 15+, 30+ items) and awards trophies:
    - ach_wardrobe_enthusiast (5+ items)
    - ach_wardrobe_collector (15+ items)
    - ach_fashion_demon (30+ items)
    """
    if not isinstance(active_items, dict):
        return []
    owned = get_owned_wardrobe_items(active_items)
    count = len(owned)
    unlocked_achievements = []
    import achievements_engine

    if count >= 5:
        u, ach_info = achievements_engine.check_and_unlock_achievement(active_items, "ach_wardrobe_enthusiast")
        if u and ach_info:
            unlocked_achievements.append(ach_info)
    if count >= 15:
        u, ach_info = achievements_engine.check_and_unlock_achievement(active_items, "ach_wardrobe_collector")
        if u and ach_info:
            unlocked_achievements.append(ach_info)
    if count >= 30:
        u, ach_info = achievements_engine.check_and_unlock_achievement(active_items, "ach_fashion_demon")
        if u and ach_info:
            unlocked_achievements.append(ach_info)

    return unlocked_achievements


# -----------------------------------------------------------------------------
# Wardrobe Durability & Repair System
# -----------------------------------------------------------------------------

def apply_armor_durability_hit(
    active_items: Dict[str, Any],
    slot: str = "body",
    damage_pct: float = 0.10
) -> Tuple[bool, str]:
    """
    Applies durability damage to the equipped item in the specified slot.
    - slot: 'body'/'torso', 'head', 'face', 'feet' (or direct item_id).
    - damage_pct: fraction or percentage of durability lost (e.g. 0.10 for 10%).
    If item durability reaches 0, it becomes broken and its stat defense is disabled.
    """
    if not isinstance(active_items, dict):
        return False, "Неверный формат инвентаря."

    item_id = None
    if slot in CLOTHING_CATALOG:
        item_id = slot
    else:
        normalized_slot = "torso" if slot == "body" else slot
        item_id = (
            active_items.get(f"equipped_{normalized_slot}")
            or active_items.get(f"equipped_{slot}")
        )
        if not item_id and slot in ("body", "torso"):
            item_id = active_items.get("equipped_torso") or active_items.get("equipped_body")

    if not item_id or item_id not in CLOTHING_CATALOG:
        return False, f"В слоте '{slot}' нет экипированного предмета."

    item_info = CLOTHING_CATALOG[item_id]
    item_name = item_info.get("name", item_id)
    dur_key = f"{item_id}_durability"
    broken_key = f"{item_id}_broken"

    # Current durability
    curr_dur = active_items.get(dur_key)
    if isinstance(active_items.get(item_id), dict):
        curr_dur = active_items[item_id].get("durability", curr_dur)
    if curr_dur is None:
        curr_dur = 100.0
    else:
        try:
            curr_dur = float(curr_dur)
        except (ValueError, TypeError):
            curr_dur = 100.0

    is_already_broken = (
        bool(active_items.get(broken_key, False))
        or curr_dur <= 0.0
        or (isinstance(active_items.get(item_id), dict) and active_items[item_id].get("broken", False))
    )
    if is_already_broken:
        active_items[dur_key] = 0.0
        active_items[broken_key] = True
        if isinstance(active_items.get(item_id), dict):
            active_items[item_id]["durability"] = 0.0
            active_items[item_id]["broken"] = True
        return False, f"Предмет {item_name} уже сломан и требует ремонта!"

    if damage_pct <= 0.0:
        return True, f"Урон по прочности предмета {item_name} не нанесен."

    dmg_points = round(damage_pct * 100.0, 2) if damage_pct <= 1.0 else round(damage_pct, 2)
    new_dur = max(0.0, round(curr_dur - dmg_points, 2))
    active_items[dur_key] = new_dur
    if isinstance(active_items.get(item_id), dict):
        active_items[item_id]["durability"] = new_dur

    if new_dur <= 0.0:
        active_items[dur_key] = 0.0
        active_items[broken_key] = True
        if isinstance(active_items.get(item_id), dict):
            active_items[item_id]["broken"] = True
        return True, f"Предмет {item_name} сломался! Защита отключена до ремонта."

    active_items[broken_key] = False
    if isinstance(active_items.get(item_id), dict):
        active_items[item_id]["broken"] = False
    return True, f"Прочность предмета {item_name} снизилась до {new_dur:.1f}%."


def calculate_item_repair_cost(
    item_id: str,
    current_durability: float,
    user_balance: float = 0.0
) -> int:
    """
    Рассчитывает стоимость ремонта предмета гардероба.
    Стоимость масштабируется от базовой цены предмета и недостающей прочности.
    Для состоятельных пользователей добавляется небольшой налог на ремонт
    (int(user_balance * 0.002), max 10,000 ₪), создавая активный sink валюты.
    """
    item = CLOTHING_CATALOG.get(item_id, {})
    base_price = int(item.get("price", 100))

    if current_durability is None:
        cur_dur = 100.0
    else:
        try:
            cur_dur = float(current_durability)
        except (ValueError, TypeError):
            cur_dur = 100.0

    if cur_dur > 1.0:
        missing_ratio = max(0.0, min(1.0, (100.0 - cur_dur) / 100.0))
    else:
        missing_ratio = max(0.0, min(1.0, 1.0 - cur_dur))

    if missing_ratio <= 0.0001:
        return 0

    base_repair_cost = int(round(base_price * missing_ratio))
    bal = max(0.0, float(user_balance or 0.0))
    repair_tax = min(10000, int(bal * 0.002))

    total_cost = base_repair_cost + repair_tax
    return max(1, total_cost) if base_repair_cost > 0 or repair_tax > 0 else 0


def repair_wardrobe_item(
    active_items: Dict[str, Any],
    item_id: str,
    user_balance: float = 0.0
) -> Tuple[bool, str, int]:
    """
    Восстанавливает прочность предмета гардероба до 100% и возвращает (успех, сообщение, списанную стоимость).
    """
    if not isinstance(active_items, dict):
        return False, "Неверный формат инвентаря.", 0

    if item_id not in CLOTHING_CATALOG:
        return False, f"Предмет '{item_id}' не найден в каталоге гардероба.", 0

    item_info = CLOTHING_CATALOG[item_id]
    item_name = item_info.get("name", item_id)
    slot = item_info.get("slot", "")

    is_owned = (
        active_items.get(f"owned_{item_id}", False)
        or active_items.get(f"{item_id}_is_permanent", False)
        or active_items.get(f"equipped_{slot}") == item_id
        or active_items.get(f"equipped_body") == item_id
        or active_items.get(f"{item_id}_durability") is not None
        or active_items.get(f"{item_id}_expires") is not None
        or (isinstance(active_items.get(item_id), dict))
    )
    if not is_owned:
        return False, f"У тебя нет предмета {item_name} в гардеробе.", 0

    dur_key = f"{item_id}_durability"
    broken_key = f"{item_id}_broken"

    curr_dur = active_items.get(dur_key)
    if isinstance(active_items.get(item_id), dict):
        curr_dur = active_items[item_id].get("durability", curr_dur)

    is_broken = (
        bool(active_items.get(broken_key, False))
        or (isinstance(active_items.get(item_id), dict) and active_items[item_id].get("broken", False))
    )

    if curr_dur is None and not is_broken:
        curr_dur = 100.0
    elif curr_dur is not None:
        try:
            curr_dur = float(curr_dur)
        except (ValueError, TypeError):
            curr_dur = 100.0

    if curr_dur is not None and curr_dur >= 100.0 and not is_broken:
        return False, f"Предмет {item_name} полностью исправен и не требует ремонта.", 0

    bal = float(user_balance or active_items.get("balance", 0.0))
    cost = calculate_item_repair_cost(item_id, curr_dur if curr_dur is not None else 0.0, bal)

    active_items[dur_key] = 100.0
    active_items[broken_key] = False
    if isinstance(active_items.get(item_id), dict):
        active_items[item_id]["durability"] = 100.0
        active_items[item_id]["broken"] = False

    return True, f"Предмет {item_name} успешно отремонтирован до 100% за {cost:,.0f} ₪.", cost
