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
from typing import Dict, Any, List, Optional, Tuple

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
        "name": "👑 Корона VIP-Скуфа",
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
        "desc": "Толстовка на 14 дней. +25 к Рассудку и олдфажный вайб."
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
        "name": "👟 Тяги бархатные (Подкрадули)",
        "price": 400,
        "duration_days": 30,
        "duration_hours": 720,
        "defense": 15,
        "toxicity": 10,
        "sanity": 20,
        "desc": "Подкрадули на 30 дней. 30% шанс успешно сбежать при облаве пативэна /partyvan."
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
        "lootbox_2x_chance": True,
        "bonus_sanity": 50,
        "bonus_toxicity": -15
    },
    "set_gop_skuf": {
        "id": "set_gop_skuf",
        "name": "🩲 Сет «Подъездный Скуф»",
        "items": ["hat_crown", "body_tracksuit"],
        "bonus_desc": "40% шанс отпугнуть грабителя в /rob и +35% к чаевым на работе.",
        "rob_fear_chance": 0.40,
        "tips_mult": 1.35,
        "bonus_toxicity": 25
    },
    "set_ward6": {
        "id": "set_ward6",
        "name": "🥼 Сет «Палата №6 / Шизофреник»",
        "items": ["body_straitjacket", "hat_tinfoil"],
        "bonus_desc": "Абсолютная невосприимчивость к Слабительному и Шизо-таблеткам.",
        "laxative_immunity": True,
        "schizo_immunity": True,
        "bonus_toxicity": 40
    },
    "set_neo": {
        "id": "set_neo",
        "name": "🕶️ Сет «Избранный / Нео»",
        "items": ["body_cloak", "face_anon_mask"],
        "bonus_desc": "+50 к Защите, скрытность баланса от налётов и +20% к выигрышу в казино.",
        "casino_bonus_pct": 20,
        "stealth": True,
        "bonus_defense": 50,
        "bonus_sanity": 30
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


def get_equipped_gear(active_items: Dict[str, Any]) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Extracts currently equipped wardrobe items from active_items dictionary across all slots.
    """
    now = int(time.time())
    equipped = {
        "head": None,
        "torso": None,
        "face": None,
        "feet": None
    }

    for slot in equipped.keys():
        eq_id = active_items.get(f"equipped_{slot}")
        if eq_id and eq_id in CLOTHING_CATALOG:
            is_perm = active_items.get(f"{eq_id}_is_permanent", False)
            expires = active_items.get(f"{eq_id}_expires", 0)
            if is_perm or expires == 0 or expires > now:
                equipped[slot] = CLOTHING_CATALOG[eq_id]

    return equipped


def get_active_set_bonuses(active_items: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Checks if equipped gear forms any complete sets and returns active bonuses.
    """
    equipped = get_equipped_gear(active_items)
    equipped_ids = {item["id"] for item in equipped.values() if item}

    active_sets = []
    for set_id, set_info in SET_BONUSES.items():
        if all(req_item in equipped_ids for req_item in set_info["items"]):
            active_sets.append(set_info)
    return active_sets


def get_owned_wardrobe_items(active_items: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Returns a list of all unexpired/permanent clothing items owned by the user.
    """
    now = int(time.time())
    owned = []
    for item_id, item_info in CLOTHING_CATALOG.items():
        is_owned = active_items.get(f"owned_{item_id}", False)
        is_perm = active_items.get(f"{item_id}_is_permanent", False)
        expires = active_items.get(f"{item_id}_expires", 0)

        # Check active ownership
        if is_owned and (is_perm or expires > now):
            info = dict(item_info)
            info["is_equipped"] = (
                active_items.get(f"equipped_{item_info['slot']}") == item_id
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


def equip_item(active_items: Dict[str, Any], item_id: str) -> Tuple[bool, str]:
    """
    Equips an owned item into its respective slot.
    """
    item = CLOTHING_CATALOG.get(item_id)
    if not item:
        return False, "Предмет не найден в каталоге."

    slot = item["slot"]
    now = int(time.time())
    is_perm = active_items.get(f"{item_id}_is_permanent", False)
    expires = active_items.get(f"{item_id}_expires", 0)

    if not is_perm and expires > 0 and expires <= now:
        return False, "Срок действия этого предмета истек! Продли его в Бутике одежды."

    if not active_items.get(f"owned_{item_id}") and not is_perm and expires <= now:
        return False, "У тебя нет этого предмета в гардеробе."

    active_items[f"equipped_{slot}"] = item_id

    # Check if a set bonus was activated
    sets = get_active_set_bonuses(active_items)
    set_note = ""
    for s in sets:
        if item_id in s["items"]:
            set_note = f"\n✨ <b>АКТИВИРОВАН СЕТ-БОНУС:</b> {s['name']}!\n<i>{s['bonus_desc']}</i>"
            
            # Unlock set achievement
            target_ach = SET_ACHIEVEMENT_MAP.get(s["id"])
            if target_ach:
                import achievements_engine
                unlocked, ach_info = achievements_engine.check_and_unlock_achievement(active_items, target_ach)
                if unlocked and ach_info:
                    set_note += f"\n🏆 <b>НОВОЕ ДОСТИЖЕНИЕ:</b> {ach_info['name']} (+{ach_info['reward_cash']} ₪)!"

    return True, f"Ты успешно надел <b>{item['name']}</b>!{set_note}"


def unequip_slot(active_items: Dict[str, Any], slot: str) -> Tuple[bool, str]:
    """
    Unequips whatever is in the specified slot ('head', 'torso', 'face', 'feet').
    """
    if slot not in ("head", "torso", "face", "feet"):
        return False, "Неверный слот экипировки."

    current = active_items.pop(f"equipped_{slot}", None)
    if current and current in CLOTHING_CATALOG:
        return True, f"Ты снял <b>{CLOTHING_CATALOG[current]['name']}</b>."
    return True, "Слот очищен."


def check_wardrobe_set_achievements(active_items: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Checks all active set bonuses and unlocks corresponding wardrobe achievements.
    Returns list of newly unlocked achievements.
    """
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
