# -*- coding: utf-8 -*-
"""
market_engine.py — P2P Flea Market / Bazaar (Барахолка Двача) for DvachBot.
Handles item classification, atomic item escrow from active_items, listing cancellation,
instant purchases with 5% Abu market fee, catalog browsing with pagination and price sorting,
interactive sell wizard, and seller PM notifications.
"""

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from aiogram import F, Router, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.db_pool import db_lock, db_transaction, get_pool
from common.database import (
    add_to_abu_fund,
    add_user_global_balance,
    deduct_user_global_balance,
    get_user_global_balance,
    record_user_transaction,
)
from wardrobe_engine import CLOTHING_CATALOG

logger = logging.getLogger("market_engine")

market_router = Router(name="market_router")
router = market_router  # Alias for backward compatibility

# -----------------------------------------------------------------------------
# Item Metacatalog & Categories
# -----------------------------------------------------------------------------

WEAPONS_CATALOG: Dict[str, Dict[str, Any]] = {
    "knife": {"id": "knife", "name": "🔪 Заточка", "gun_key": "knife_gun"},
    "knife_gun": {"id": "knife", "name": "🔪 Заточка", "gun_key": "knife_gun"},
    "pepperspray": {"id": "pepperspray", "name": "🧯 Перцовый баллончик", "gun_key": "pepperspray_gun"},
    "pepperspray_gun": {"id": "pepperspray", "name": "🧯 Перцовый баллончик", "gun_key": "pepperspray_gun"},
    "mute": {"id": "mute", "name": "🤐 Мьют-Ган", "gun_key": "mute_gun"},
    "mute_gun": {"id": "mute", "name": "🤐 Мьют-Ган", "gun_key": "mute_gun"},
    "partyvan": {"id": "partyvan", "name": "🚔 Пативэн-Ган", "gun_key": "partyvan_gun"},
    "partyvan_gun": {"id": "partyvan", "name": "🚔 Пативэн-Ган", "gun_key": "partyvan_gun"},
    "shit": {"id": "shit", "name": "🐒 Кусок говна", "gun_key": "shit_gun"},
    "shit_gun": {"id": "shit", "name": "🐒 Кусок говна", "gun_key": "shit_gun"},
    "vomit": {"id": "vomit", "name": "🤮 Блевотный баллончик", "gun_key": "vomit_gun"},
    "vomit_gun": {"id": "vomit", "name": "🤮 Блевотный баллончик", "gun_key": "vomit_gun"},
    "laxative": {"id": "laxative", "name": "🚽 Слабительное", "gun_key": "laxative_gun"},
    "laxative_gun": {"id": "laxative", "name": "🚽 Слабительное", "gun_key": "laxative_gun"},
    "schizopill": {"id": "schizopill", "name": "💊 Шизо-Таблетка", "gun_key": "schizopill_gun"},
    "schizopill_gun": {"id": "schizopill", "name": "💊 Шизо-Таблетка", "gun_key": "schizopill_gun"},
    "flag_ru": {"id": "flag_ru", "name": "🇷🇺 Флаг РФ", "gun_key": "flag_ru_gun"},
    "flag_ru_gun": {"id": "flag_ru", "name": "🇷🇺 Флаг РФ", "gun_key": "flag_ru_gun"},
    "flag_ua": {"id": "flag_ua", "name": "🇺🇦 Флаг Украины", "gun_key": "flag_ua_gun"},
    "flag_ua_gun": {"id": "flag_ua", "name": "🇺🇦 Флаг Украины", "gun_key": "flag_ua_gun"},
    "megaphone": {"id": "megaphone", "name": "📢 Мегафон", "gun_key": "megaphone_gun"},
    "megaphone_gun": {"id": "megaphone", "name": "📢 Мегафон", "gun_key": "megaphone_gun"},
    "janitor": {"id": "janitor", "name": "🧹 Метла Дворника", "gun_key": "janitor_broom"},
    "janitor_broom": {"id": "janitor", "name": "🧹 Метла Дворника", "gun_key": "janitor_broom"},
}

PHARMA_CATALOG: Dict[str, Dict[str, Any]] = {
    "pills": {"id": "pills", "name": "💊 Аминазин", "desc": "Успокоительное против шизы."},
    "pills_gun": {"id": "pills", "name": "💊 Аминазин", "desc": "Успокоительное против шизы."},
    "shield": {"id": "shield", "name": "🔰 Зеркальный Щит", "desc": "Отражает атаки и выстрелы."},
    "shield_gun": {"id": "shield", "name": "🔰 Зеркальный Щит", "desc": "Отражает атаки и выстрелы."},
    "bribe": {"id": "bribe", "name": "📜 Взятка", "desc": "Индульгенция от пативэна и бана."},
    "tinfoil": {"id": "tinfoil", "name": "👽 Шапочка из фольги", "desc": "Защита от 5G и грабежа."},
    "tinfoil_hat": {"id": "tinfoil", "name": "👽 Шапочка из фольги", "desc": "Защита от 5G и грабежа."},
}

LOOTBOXES_CATALOG: Dict[str, Dict[str, Any]] = {
    "lootbox_trash": {"id": "lootbox_trash", "name": "🗑️ Мусорный Лутбокс", "desc": "Бюджетный кейс со случайным лутом."},
    "trash_lootbox": {"id": "lootbox_trash", "name": "🗑️ Мусорный Лутбокс", "desc": "Бюджетный кейс со случайным лутом."},
    "lootbox_gold": {"id": "lootbox_gold", "name": "👑 Золотой Сейф", "desc": "Элитный кейс с шансом на вечный шмот."},
    "gold_safe": {"id": "lootbox_gold", "name": "👑 Золотой Сейф", "desc": "Элитный кейс с шансом на вечный шмот."},
}

MARKET_CATEGORIES: Dict[str, str] = {
    "weapon": "⚔️ Оружие",
    "clothing": "👗 Шмот",
    "pharma": "💊 Аптека",
    "lootbox": "📦 Лутбоксы",
}


def classify_item(item_id: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Определяет категорию (item_type), каноническое имя и метаданные предмета по его идентификатору.
    Возвращает (item_type, item_name, default_meta).
    """
    clean_id = item_id.lower().strip()

    if clean_id in CLOTHING_CATALOG:
        info = CLOTHING_CATALOG[clean_id]
        return "clothing", info["name"], {
            "tier": info.get("tier", 1),
            "slot": info.get("slot", "torso"),
            "duration_hours": info.get("duration_hours", 168),
            "defense": info.get("defense", 0),
            "toxicity": info.get("toxicity", 0),
            "sanity": info.get("sanity", 0),
        }

    if clean_id in WEAPONS_CATALOG:
        info = WEAPONS_CATALOG[clean_id]
        return "weapon", info["name"], {"canonical_id": info["id"], "gun_key": info.get("gun_key")}

    if clean_id in PHARMA_CATALOG:
        info = PHARMA_CATALOG[clean_id]
        return "pharma", info["name"], {"canonical_id": info["id"], "desc": info.get("desc", "")}

    if clean_id in LOOTBOXES_CATALOG:
        info = LOOTBOXES_CATALOG[clean_id]
        return "lootbox", info["name"], {"canonical_id": info["id"], "desc": info.get("desc", "")}

    # Попытка определить по префиксу
    if clean_id.startswith(("hat_", "body_", "face_", "feet_")):
        return "clothing", f"👗 {clean_id}", {}
    if clean_id.endswith("_gun") or clean_id.endswith("_weapon"):
        return "weapon", f"⚔️ {clean_id}", {}
    if "lootbox" in clean_id or "safe" in clean_id:
        return "lootbox", f"📦 {clean_id}", {}

    return "pharma", f"📦 {clean_id}", {}


def find_item_by_name_or_id(query: str) -> Optional[Tuple[str, str, str]]:
    """
    Находит (item_id, item_type, item_name) по пользовательскому вводу.
    """
    clean = query.lower().strip().replace(" ", "_")

    # Direct match in catalogs
    if clean in CLOTHING_CATALOG:
        return clean, "clothing", CLOTHING_CATALOG[clean]["name"]
    if clean in WEAPONS_CATALOG:
        return WEAPONS_CATALOG[clean]["id"], "weapon", WEAPONS_CATALOG[clean]["name"]
    if clean in PHARMA_CATALOG:
        return PHARMA_CATALOG[clean]["id"], "pharma", PHARMA_CATALOG[clean]["name"]
    if clean in LOOTBOXES_CATALOG:
        return LOOTBOXES_CATALOG[clean]["id"], "lootbox", LOOTBOXES_CATALOG[clean]["name"]

    # Partial / substring match
    for k, v in WEAPONS_CATALOG.items():
        if clean in k.lower() or clean in v["name"].lower():
            return v["id"], "weapon", v["name"]

    for k, v in CLOTHING_CATALOG.items():
        if clean in k.lower() or clean in v["name"].lower():
            return k, "clothing", v["name"]

    for k, v in PHARMA_CATALOG.items():
        if clean in k.lower() or clean in v["name"].lower():
            return v["id"], "pharma", v["name"]

    for k, v in LOOTBOXES_CATALOG.items():
        if clean in k.lower() or clean in v["name"].lower():
            return v["id"], "lootbox", v["name"]

    # Fuzzy matches
    fuzzy_map = {
        "заточка": ("knife", "weapon", "🔪 Заточка"),
        "нож": ("knife", "weapon", "🔪 Заточка"),
        "перцовка": ("pepperspray", "weapon", "🧯 Перцовый баллончик"),
        "баллончик": ("pepperspray", "weapon", "🧯 Перцовый баллончик"),
        "мьют": ("mute", "weapon", "🤐 Мьют-Ган"),
        "мутган": ("mute", "weapon", "🤐 Мьют-Ган"),
        "пативэн": ("partyvan", "weapon", "🚔 Пативэн-Ган"),
        "говно": ("shit", "weapon", "🐒 Кусок говна"),
        "блевота": ("vomit", "weapon", "🤮 Блевотный баллончик"),
        "слабительное": ("laxative", "weapon", "🚽 Слабительное"),
        "шизо": ("schizopill", "weapon", "💊 Шизо-Таблетка"),
        "таблетки": ("pills", "pharma", "💊 Аминазин"),
        "аминазин": ("pills", "pharma", "💊 Аминазин"),
        "щит": ("shield", "pharma", "🔰 Зеркальный Щит"),
        "взятка": ("bribe", "pharma", "📜 Взятка"),
        "фольга": ("tinfoil", "pharma", "👽 Шапочка из фольги"),
        "шапочка": ("tinfoil", "pharma", "👽 Шапочка из фольги"),
        "мусор": ("lootbox_trash", "lootbox", "🗑️ Мусорный Лутбокс"),
        "трэш": ("lootbox_trash", "lootbox", "🗑️ Мусорный Лутбокс"),
        "сейф": ("lootbox_gold", "lootbox", "👑 Золотой Сейф"),
        "голд": ("lootbox_gold", "lootbox", "👑 Золотой Сейф"),
        "метла": ("janitor", "weapon", "🧹 Метла Дворника"),
        "дворник": ("janitor", "weapon", "🧹 Метла Дворника"),
    }
    for alias, entry in fuzzy_map.items():
        if alias in clean:
            return entry

    return None


# -----------------------------------------------------------------------------
# Escrow & Active Items Helpers
# -----------------------------------------------------------------------------

async def _load_user_active_items_for_update(db, user_id: int, board_id: str) -> Dict[str, Any]:
    """
    Загружает active_items пользователя из БД для обновления под транзакцией.
    """
    async with db.execute("SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id)) as c:
        row = await c.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return {}
    return {}


async def _save_user_active_items(db, user_id: int, board_id: str, items: Dict[str, Any]):
    """
    Сохраняет active_items пользователя в БД.
    """
    await db.execute(
        "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
        (user_id, board_id, json.dumps(items, ensure_ascii=False))
    )


def extract_item_for_escrow(active_items: Dict[str, Any], item_id: str, item_type: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    Извлекает (лочит) предмет из active_items пользователя.
    Возвращает (успех, item_data, текст_ошибки).
    """
    clean_id = item_id.lower().strip()
    now = int(time.time())
    item_data: Dict[str, Any] = {}

    if item_type == "clothing":
        has_owned = active_items.get(f"owned_{clean_id}") or active_items.get(clean_id)
        if not has_owned:
            return False, {}, "У вас нет этого предмета гардероба в инвентаре."

        for slot_key in ["equipped_head", "equipped_torso", "equipped_face", "equipped_feet"]:
            if active_items.get(slot_key) == clean_id:
                active_items[slot_key] = None

        is_perm = bool(active_items.pop(f"{clean_id}_is_permanent", False))
        exp_ts = active_items.pop(f"{clean_id}_expires", None)

        rem_sec = 0
        if is_perm:
            item_data["is_permanent"] = True
        elif exp_ts is not None:
            rem_sec = max(0, int(exp_ts - now))
            if rem_sec <= 0:
                active_items.pop(f"owned_{clean_id}", None)
                active_items.pop(clean_id, None)
                return False, {}, "Срок действия этого предмета уже истёк."
            item_data["remaining_seconds"] = rem_sec
            item_data["original_duration_hours"] = int(rem_sec / 3600)
        else:
            cat_dur = CLOTHING_CATALOG.get(clean_id, {}).get("duration_hours", 168)
            item_data["remaining_seconds"] = cat_dur * 3600

        active_items.pop(f"owned_{clean_id}", None)
        active_items.pop(clean_id, None)
        return True, item_data, ""

    elif item_type == "weapon":
        gun_info = WEAPONS_CATALOG.get(clean_id, {})
        gun_key = gun_info.get("gun_key", f"{clean_id}_gun")
        raw_key = gun_info.get("id", clean_id)

        has_gun = active_items.get(gun_key) or active_items.get(raw_key) or active_items.get(clean_id)
        if not has_gun:
            return False, {}, "У вас нет этого оружия в инвентаре."

        active_items.pop(gun_key, None)
        active_items.pop(raw_key, None)
        active_items.pop(clean_id, None)
        item_data["canonical_id"] = raw_key
        return True, item_data, ""

    elif item_type == "pharma":
        if clean_id in ("pills", "pills_gun"):
            cnt = active_items.get("pills_count", 0)
            if cnt > 1:
                active_items["pills_count"] = cnt - 1
            elif cnt == 1:
                active_items.pop("pills_count", None)
                active_items.pop("pills", None)
                active_items.pop("pills_gun", None)
            elif active_items.get("pills") or active_items.get("pills_gun"):
                active_items.pop("pills", None)
                active_items.pop("pills_gun", None)
            else:
                return False, {}, "У вас нет таблеток Аминазина."
            item_data["count"] = 1
            return True, item_data, ""

        elif clean_id in ("shield", "shield_gun"):
            exp_ts = active_items.get("shield_until")
            if exp_ts:
                rem_sec = max(0, int(exp_ts - now))
                if rem_sec <= 0:
                    active_items.pop("shield_until", None)
                    active_items.pop("shield_gun", None)
                    active_items.pop("shield", None)
                    return False, {}, "Срок действия щита уже истёк."
                active_items.pop("shield_until", None)
                active_items.pop("shield_gun", None)
                active_items.pop("shield", None)
                item_data["remaining_seconds"] = rem_sec
                return True, item_data, ""
            elif active_items.get("shield_gun") or active_items.get("shield"):
                active_items.pop("shield_gun", None)
                active_items.pop("shield", None)
                item_data["remaining_seconds"] = 86400
                return True, item_data, ""
            return False, {}, "У вас нет Зеркального Щита."

        elif clean_id in ("bribe", "bribe_count"):
            cnt = active_items.get("bribes_count", 0)
            if cnt > 1:
                active_items["bribes_count"] = cnt - 1
            elif cnt == 1:
                active_items.pop("bribes_count", None)
                active_items.pop("bribe", None)
            elif active_items.get("bribe"):
                active_items.pop("bribe", None)
            else:
                return False, {}, "У вас нет Взятки."
            item_data["count"] = 1
            return True, item_data, ""

        elif clean_id in ("tinfoil", "tinfoil_hat"):
            exp_ts = active_items.get("tinfoil_until") or active_items.get("tinfoil_hat")
            if isinstance(exp_ts, (int, float)):
                rem_sec = max(0, int(exp_ts - now))
                if rem_sec <= 0:
                    active_items.pop("tinfoil_until", None)
                    active_items.pop("tinfoil_hat", None)
                    return False, {}, "Срок действия шапочки из фольги истёк."
                active_items.pop("tinfoil_until", None)
                active_items.pop("tinfoil_hat", None)
                item_data["remaining_seconds"] = rem_sec
                return True, item_data, ""
            elif active_items.get("tinfoil"):
                active_items.pop("tinfoil", None)
                item_data["remaining_seconds"] = 21600
                return True, item_data, ""
            return False, {}, "У вас нет Шапочки из фольги."

        if active_items.get(clean_id):
            active_items.pop(clean_id, None)
            return True, item_data, ""
        return False, {}, "У вас нет этого предмета."

    elif item_type == "lootbox":
        canonical_key = "lootbox_trash" if clean_id in ("lootbox_trash", "trash_lootbox") else "lootbox_gold"
        val = active_items.get(canonical_key) or active_items.get(clean_id)
        if isinstance(val, int) and val > 1:
            active_items[canonical_key] = val - 1
        elif isinstance(val, int) and val == 1:
            active_items.pop(canonical_key, None)
            active_items.pop(clean_id, None)
        elif val:
            active_items.pop(canonical_key, None)
            active_items.pop(clean_id, None)
        else:
            return False, {}, "У вас нет этого кейса в инвентаре."
        item_data["canonical_id"] = canonical_key
        item_data["count"] = 1
        return True, item_data, ""

    if active_items.get(clean_id):
        active_items.pop(clean_id, None)
        return True, item_data, ""

    return False, {}, "Предмет не найден в вашем инвентаре."


def restore_item_to_active_items(active_items: Dict[str, Any], item_id: str, item_type: str, item_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Восстанавливает (или начисляет покупателю) предмет в active_items.
    """
    clean_id = item_id.lower().strip()
    now = int(time.time())

    if item_type == "clothing":
        active_items[f"owned_{clean_id}"] = True
        if item_data.get("is_permanent"):
            active_items[f"{clean_id}_is_permanent"] = True
        else:
            rem_sec = item_data.get("remaining_seconds", 168 * 3600)
            cur_exp = active_items.get(f"{clean_id}_expires")
            if cur_exp and cur_exp > now:
                active_items[f"{clean_id}_expires"] = cur_exp + rem_sec
            else:
                active_items[f"{clean_id}_expires"] = now + rem_sec

    elif item_type == "weapon":
        gun_info = WEAPONS_CATALOG.get(clean_id, {})
        gun_key = gun_info.get("gun_key", f"{clean_id}_gun")
        active_items[gun_key] = True

    elif item_type == "pharma":
        if clean_id in ("pills", "pills_gun"):
            active_items["pills_count"] = active_items.get("pills_count", 0) + item_data.get("count", 1)
            active_items["pills_gun"] = True
        elif clean_id in ("shield", "shield_gun"):
            rem_sec = item_data.get("remaining_seconds", 86400)
            cur_exp = active_items.get("shield_until", 0)
            base = max(cur_exp, now)
            active_items["shield_until"] = base + rem_sec
            active_items["shield_gun"] = True
            active_items["shield"] = True
        elif clean_id in ("bribe", "bribe_count"):
            active_items["bribes_count"] = active_items.get("bribes_count", 0) + item_data.get("count", 1)
            active_items["bribe"] = True
        elif clean_id in ("tinfoil", "tinfoil_hat"):
            rem_sec = item_data.get("remaining_seconds", 21600)
            cur_exp = max(active_items.get("tinfoil_until", 0), active_items.get("tinfoil_hat", 0))
            base = max(cur_exp, now)
            active_items["tinfoil_until"] = base + rem_sec
            active_items["tinfoil_hat"] = base + rem_sec
        else:
            active_items[clean_id] = True

    elif item_type == "lootbox":
        canonical_key = item_data.get("canonical_id", "lootbox_trash" if "trash" in clean_id else "lootbox_gold")
        curr = active_items.get(canonical_key, 0)
        if isinstance(curr, int):
            active_items[canonical_key] = curr + item_data.get("count", 1)
        else:
            active_items[canonical_key] = 1

    else:
        active_items[clean_id] = True

    return active_items


# -----------------------------------------------------------------------------
# Core Market Business Logic & Database Functions
# -----------------------------------------------------------------------------

async def create_market_listing(
    db,
    seller_id: int,
    seller_board_id: Optional[str],
    item_id: str,
    price: float,
    custom_item_data: Optional[Dict[str, Any]] = None,
    item_type: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Атомарно выставляет предмет на Базар:
    1. Проверяет и извлекает предмет из active_items продавца (escrow/lock).
    2. Создает запись в таблице MarketListings со статусом 'active'.
    Возвращает (success: bool, listing_dict: Optional[dict], error_msg: str).
    """
    if not isinstance(price, (int, float)) or math.isnan(price) or math.isinf(price) or price <= 0:
        return False, None, "Цена должна быть положительным числом больше 0 ₪."
    if price > 100_000_000:
        return False, None, "Максимальная цена предмета на Базаре — 100 000 000 ₪."

    board_id = seller_board_id or "b"
    price = round(float(price), 2)

    detected_type, item_name, default_meta = classify_item(item_id)
    final_type = item_type or detected_type

    async with db_transaction(db):
        active_items = await _load_user_active_items_for_update(db, seller_id, board_id)

        ok, extracted_meta, err = extract_item_for_escrow(active_items, item_id, final_type)
        if not ok:
            return False, None, err

        merged_meta = {**default_meta, **extracted_meta, **(custom_item_data or {})}

        await _save_user_active_items(db, seller_id, board_id, active_items)

        now = time.time()
        cursor = await db.execute(
            """
            INSERT INTO MarketListings (
                seller_id, seller_board_id, item_id, item_type, item_name,
                item_data, price, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                seller_id,
                board_id,
                item_id,
                final_type,
                item_name,
                json.dumps(merged_meta, ensure_ascii=False),
                price,
                now,
            )
        )
        lot_id = cursor.lastrowid

        listing_record = {
            "id": lot_id,
            "seller_id": seller_id,
            "seller_board_id": board_id,
            "item_id": item_id,
            "item_type": final_type,
            "item_name": item_name,
            "item_data": merged_meta,
            "price": price,
            "status": "active",
            "created_at": now,
        }

        return True, listing_record, ""


async def cancel_market_listing(
    db,
    lot_id: int,
    user_id: int,
    board_id: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Отменяет активный лот на Базаре и возвращает предмет продавцу в active_items.
    Возвращает (success: bool, item_dict: Optional[dict], error_msg: str).
    """
    b_id = board_id or "b"

    async with db_transaction(db):
        async with db.execute(
            "SELECT id, seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status "
            "FROM MarketListings WHERE id = ?",
            (lot_id,)
        ) as c:
            row = await c.fetchone()

        if not row:
            return False, None, "Лот не найден на Базаре."

        l_id, s_id, s_board, item_id, item_type, item_name, raw_data, price, status = row

        if s_id != user_id:
            return False, None, "Вы не являетесь владельцем этого лота."

        if status != "active":
            return False, None, f"Лот уже не активен (текущий статус: {status})."

        item_data = {}
        if raw_data:
            try:
                item_data = json.loads(raw_data)
            except Exception:
                pass

        active_items = await _load_user_active_items_for_update(db, user_id, s_board or b_id)
        active_items = restore_item_to_active_items(active_items, item_id, item_type, item_data)
        await _save_user_active_items(db, user_id, s_board or b_id, active_items)

        now = time.time()
        await db.execute(
            "UPDATE MarketListings SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
            (now, lot_id)
        )

        item_dict = {
            "lot_id": lot_id,
            "item_id": item_id,
            "item_type": item_type,
            "item_name": item_name,
            "item_data": item_data,
            "price": price,
        }

        return True, item_dict, ""


async def buy_market_listing(
    db,
    lot_id: int,
    buyer_id: int,
    buyer_board_id: Optional[str] = None
) -> Tuple[bool, int, float, float, float, Optional[Dict[str, Any]], str]:
    """
    Атомарно покупает лот на Базаре:
    1. Проверяет активность лота и невозможность покупки собственного лота.
    2. Списывает шекели с покупателя.
    3. Рассчитывает 5% налог Абу (минимальная комиссия 1 ₪ при цене >= 1 ₪).
    4. Зачисляет выплату продавцу и комиссию в Фонд Яхты Абу.
    5. Передает предмет в active_items покупателя.
    6. Записывает транзакции в леджер UserTransactions.
    Возвращает (success: bool, seller_id: int, price: float, payout: float, fee: float, item: Optional[dict], error_msg: str).
    """
    b_id = buyer_board_id or "b"

    async with db_transaction(db):
        async with db.execute(
            "SELECT id, seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status "
            "FROM MarketListings WHERE id = ?",
            (lot_id,)
        ) as c:
            row = await c.fetchone()

        if not row:
            return False, 0, 0.0, 0.0, 0.0, None, "Лот не найден на Базаре."

        l_id, seller_id, seller_board_id, item_id, item_type, item_name, raw_data, price, status = row

        if status != "active":
            return False, 0, 0.0, 0.0, 0.0, None, "Этот лот уже продан или снят с продажи."

        if seller_id == buyer_id:
            return False, 0, 0.0, 0.0, 0.0, None, "Нельзя покупать свой собственный лот, хитрец."

        price = float(price)

        ok, _ = await deduct_user_global_balance(db, buyer_id, b_id, price)
        if not ok:
            return False, 0, 0.0, 0.0, 0.0, None, f"Недостаточно шекелей для покупки лота ({price:,.0f} ₪)."

        raw_fee = price * 0.05
        fee = max(1.0, round(raw_fee, 2)) if price >= 1.0 else round(raw_fee, 2)
        if fee > price:
            fee = price
        payout = round(price - fee, 2)

        await add_user_global_balance(db, seller_id, seller_board_id or "b", payout)
        if fee > 0:
            await add_to_abu_fund(db, fee, donor_id=buyer_id, reason=f"Комиссия Базара: лот #{lot_id} ({item_name})")

        item_data = {}
        if raw_data:
            try:
                item_data = json.loads(raw_data)
            except Exception:
                pass

        buyer_items = await _load_user_active_items_for_update(db, buyer_id, b_id)
        buyer_items = restore_item_to_active_items(buyer_items, item_id, item_type, item_data)
        await _save_user_active_items(db, buyer_id, b_id, buyer_items)

        now = time.time()
        await db.execute(
            "UPDATE MarketListings SET status = 'sold', buyer_id = ?, buyer_board_id = ?, sold_at = ? WHERE id = ?",
            (buyer_id, b_id, now, lot_id)
        )

        await record_user_transaction(db, buyer_id, -price, "shop", f"Покупка на Базаре: {item_name} (лот #{lot_id})")
        await record_user_transaction(db, seller_id, payout, "market", f"Продажа на Базаре: {item_name} (лот #{lot_id}, -5% налог Абу)")

        item_dict = {
            "lot_id": lot_id,
            "item_id": item_id,
            "item_type": item_type,
            "item_name": item_name,
            "item_data": item_data,
            "price": price,
            "fee": fee,
            "payout": payout,
        }

        return True, seller_id, price, payout, fee, item_dict, ""


# -----------------------------------------------------------------------------
# Catalog Querying, Pagination, Filtering & Sorting
# -----------------------------------------------------------------------------

async def get_market_catalog(
    db,
    category: Optional[str] = None,
    sort_order: str = "price_asc",
    page: int = 1,
    per_page: int = 5
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Возвращает страницу каталога активных лотов с фильтрацией и сортировкой:
    - category: 'weapon', 'clothing', 'pharma', 'lootbox' (или None / 'all' для всех)
    - sort_order: 'price_asc', 'price_desc', 'newest'
    - page: номер страницы (1-indexed)
    - per_page: количество лотов на странице
    Возвращает (items: list[dict], total_pages: int, total_count: int).
    """
    page = max(1, page)
    per_page = max(1, min(per_page, 20))
    offset = (page - 1) * per_page

    where_clauses = ["status = 'active'"]
    params: List[Any] = []

    # Map category aliases
    cat_canon = category
    if category in ("weapons", "weapon"):
        cat_canon = "weapon"
    elif category in ("clothes", "clothing", "wardrobe"):
        cat_canon = "clothing"
    elif category in ("pharma", "drugs"):
        cat_canon = "pharma"
    elif category in ("lootbox", "lootboxes", "boxes"):
        cat_canon = "lootbox"
    elif category in ("all", "none", None):
        cat_canon = None

    if cat_canon and cat_canon in MARKET_CATEGORIES:
        where_clauses.append("item_type = ?")
        params.append(cat_canon)

    where_sql = " AND ".join(where_clauses)

    if sort_order == "price_desc":
        order_sql = "price DESC, created_at DESC"
    elif sort_order == "newest":
        order_sql = "created_at DESC"
    else:  # price_asc
        order_sql = "price ASC, created_at DESC"

    async with db.execute(f"SELECT COUNT(*) FROM MarketListings WHERE {where_sql}", tuple(params)) as c:
        row = await c.fetchone()
        total_count = int(row[0]) if row and row[0] else 0

    total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 1

    query = f"""
        SELECT id, seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at
        FROM MarketListings
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    fetch_params = params + [per_page, offset]

    items: List[Dict[str, Any]] = []
    async with db.execute(query, tuple(fetch_params)) as c:
        rows = await c.fetchall()
        for r in rows:
            data = {}
            if r[6]:
                try:
                    data = json.loads(r[6])
                except Exception:
                    pass
            items.append({
                "id": r[0],
                "seller_id": r[1],
                "seller_board_id": r[2],
                "item_id": r[3],
                "item_type": r[4],
                "item_name": r[5],
                "item_data": data,
                "price": float(r[7]),
                "status": r[8],
                "created_at": float(r[9]),
            })

    return items, total_pages, total_count


async def get_user_listings(db, user_id: int, status: str = "active") -> List[Dict[str, Any]]:
    """
    Возвращает список лотов конкретного пользователя.
    """
    query = """
        SELECT id, seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at
        FROM MarketListings
        WHERE seller_id = ? AND status = ?
        ORDER BY created_at DESC
    """
    items: List[Dict[str, Any]] = []
    async with db.execute(query, (user_id, status)) as c:
        rows = await c.fetchall()
        for r in rows:
            data = {}
            if r[6]:
                try:
                    data = json.loads(r[6])
                except Exception:
                    pass
            items.append({
                "id": r[0],
                "seller_id": r[1],
                "seller_board_id": r[2],
                "item_id": r[3],
                "item_type": r[4],
                "item_name": r[5],
                "item_data": data,
                "price": float(r[7]),
                "status": r[8],
                "created_at": float(r[9]),
            })
    return items


async def get_market_listing(db, lot_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает информацию по конкретному лоту.
    """
    query = """
        SELECT id, seller_id, seller_board_id, item_id, item_type, item_name, item_data, price, status, created_at, buyer_id, sold_at
        FROM MarketListings
        WHERE id = ?
    """
    async with db.execute(query, (lot_id,)) as c:
        r = await c.fetchone()
        if not r:
            return None
        data = {}
        if r[6]:
            try:
                data = json.loads(r[6])
            except Exception:
                pass
        return {
            "id": r[0],
            "seller_id": r[1],
            "seller_board_id": r[2],
            "item_id": r[3],
            "item_type": r[4],
            "item_name": r[5],
            "item_data": data,
            "price": float(r[7]),
            "status": r[8],
            "created_at": float(r[9]),
            "buyer_id": r[10],
            "sold_at": float(r[11]) if r[11] else None,
        }


# -----------------------------------------------------------------------------
# Seller PM Notification Helper
# -----------------------------------------------------------------------------

async def notify_seller_lot_sold(
    bot,
    seller_id: int,
    item_name: str,
    price: float,
    payout: float,
    fee: float
) -> bool:
    """
    Отправляет прямое личное сообщение продавцу о продаже его лота в Telegram.
    Подавляет ошибки Telegram API (если бот заблокирован или ЛС закрыты).
    """
    if not bot or not seller_id:
        return False

    msg_text = (
        f"🛒 <b>ТВОЙ ЛОТ ПРОДАН НА БАЗАРЕ!</b>\n\n"
        f"📦 <b>Товар:</b> <b>{item_name}</b>\n"
        f"💰 <b>Цена продажи:</b> <code>{price:,.2f} ₪</code>\n"
        f"💸 <b>Налог Абу (5%):</b> <code>-{fee:,.2f} ₪</code>\n"
        f"💵 <b>Зачислено на баланс:</b> <code>+{payout:,.2f} ₪</code>\n\n"
        f"<i>Шекели уже упали в твой кошелек! Можешь потратить их в /shop или положить в /bank.</i>"
    )

    try:
        await bot.send_message(chat_id=seller_id, text=msg_text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление о продаже лота продавцу {seller_id}: {e}")
        return False


# -----------------------------------------------------------------------------
# UI Builders & Keyboards
# -----------------------------------------------------------------------------

def build_market_main_menu_kb() -> InlineKeyboardMarkup:
    """Генерирует клавиатуру главного меню Барахолки."""
    kb = [
        [
            InlineKeyboardButton(text="⚔️ Оружие", callback_data="market_cat:weapon:price_asc:1"),
            InlineKeyboardButton(text="👗 Шмот", callback_data="market_cat:clothing:price_asc:1"),
        ],
        [
            InlineKeyboardButton(text="💊 Аптека", callback_data="market_cat:pharma:price_asc:1"),
            InlineKeyboardButton(text="📦 Лутбоксы", callback_data="market_cat:lootbox:price_asc:1"),
        ],
        [
            InlineKeyboardButton(text="📋 Все лоты", callback_data="market_cat:all:price_asc:1"),
        ],
        [
            InlineKeyboardButton(text="📦 Мои лоты", callback_data="market_my_lots:1"),
            InlineKeyboardButton(text="🏷 Продать предмет (/sell)", callback_data="market_sell_menu"),
        ],
        [
            InlineKeyboardButton(text="⬅️ В Магазин (/shop)", callback_data="shop_main_hub"),
            InlineKeyboardButton(text="🏦 Банк Абу (/bank)", callback_data="bank_main_hub"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def build_market_catalog_kb(
    category: str,
    sort_order: str,
    page: int,
    total_pages: int,
    items: List[Dict[str, Any]]
) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру каталога Барахолки с пагинацией и сортировкой."""
    kb: List[List[InlineKeyboardButton]] = []

    # Кнопки каждого лота
    for item in items:
        price_str = f"{int(item['price']):,} ₪" if item['price'].is_integer() else f"{item['price']:,.2f} ₪"
        kb.append([
            InlineKeyboardButton(
                text=f"{item['item_name']} — {price_str}",
                callback_data=f"market_lot:{item['id']}"
            )
        ])

    # Строка переключения сортировки
    sort_btn_asc = "🔹 🔼 Дешевле" if sort_order == "price_asc" else "🔼 Дешевле"
    sort_btn_desc = "🔹 🔽 Дороже" if sort_order == "price_desc" else "🔽 Дороже"
    sort_btn_new = "🔹 🆕 Новые" if sort_order == "newest" else "🆕 Новые"
    kb.append([
        InlineKeyboardButton(text=sort_btn_asc, callback_data=f"market_cat:{category}:price_asc:1"),
        InlineKeyboardButton(text=sort_btn_desc, callback_data=f"market_cat:{category}:price_desc:1"),
        InlineKeyboardButton(text=sort_btn_new, callback_data=f"market_cat:{category}:newest:1"),
    ])

    # Пагинация
    nav_row: List[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"market_cat:{category}:{sort_order}:{page-1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data="market_noop"))

    nav_row.append(InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data=f"market_cat:{category}:{sort_order}:{page}"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"market_cat:{category}:{sort_order}:{page+1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data="market_noop"))

    kb.append(nav_row)

    # Категории и действия
    kb.append([
        InlineKeyboardButton(text="📦 Мои лоты", callback_data="market_my_lots:1"),
        InlineKeyboardButton(text="🏷 Продать (/sell)", callback_data="market_sell_menu"),
    ])
    kb.append([
        InlineKeyboardButton(text="📋 Все категории", callback_data="market_main_hub"),
        InlineKeyboardButton(text="🏬 Торговый Хаб", callback_data="shop_main_hub"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb)


async def _render_market_view(
    target: types.Message | types.CallbackQuery,
    text: str,
    kb: InlineKeyboardMarkup,
    category: str = "shop"
):
    """Универсально отображает или обновляет представление Базара."""
    try:
        if isinstance(target, types.CallbackQuery):
            if target.message.caption is not None or target.message.photo:
                await target.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            elif target.message.text is not None:
                await target.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                from banner_manager import send_banner_message
                await send_banner_message(bot=target.bot, chat_id=target.message.chat.id, caption=text, reply_markup=kb, category=category, parse_mode="HTML")
        else:
            from banner_manager import send_banner_message
            await send_banner_message(bot=target.bot, chat_id=target.chat.id, caption=text, reply_markup=kb, category=category, parse_mode="HTML")
            try:
                await target.delete()
            except Exception:
                pass
    except Exception:
        try:
            if isinstance(target, types.CallbackQuery):
                await target.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.answer(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


# -----------------------------------------------------------------------------
# User Sellable Items Scanner
# -----------------------------------------------------------------------------

def get_user_sellable_items_list(active_items: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Сканирует active_items пользователя и возвращает список доступных для продажи предметов:
    [(item_id, item_type, item_name), ...]
    """
    found: List[Tuple[str, str, str]] = []
    seen = set()

    # 1. Weapons
    for key, info in WEAPONS_CATALOG.items():
        cid = info["id"]
        if cid in seen:
            continue
        gkey = info.get("gun_key", f"{cid}_gun")
        if active_items.get(gkey) or active_items.get(cid):
            found.append((cid, "weapon", info["name"]))
            seen.add(cid)

    # 2. Wardrobe / Clothes
    for key, info in CLOTHING_CATALOG.items():
        if key in seen:
            continue
        if active_items.get(f"owned_{key}") or active_items.get(key):
            found.append((key, "clothing", info["name"]))
            seen.add(key)

    # 3. Pharma
    for key, info in PHARMA_CATALOG.items():
        cid = info["id"]
        if cid in seen:
            continue
        if cid == "pills" and (active_items.get("pills_count", 0) > 0 or active_items.get("pills") or active_items.get("pills_gun")):
            found.append(("pills", "pharma", info["name"]))
            seen.add(cid)
        elif cid == "shield" and (active_items.get("shield_until") or active_items.get("shield") or active_items.get("shield_gun")):
            found.append(("shield", "pharma", info["name"]))
            seen.add(cid)
        elif cid == "bribe" and (active_items.get("bribes_count", 0) > 0 or active_items.get("bribe")):
            found.append(("bribe", "pharma", info["name"]))
            seen.add(cid)
        elif cid == "tinfoil" and (active_items.get("tinfoil_until") or active_items.get("tinfoil_hat") or active_items.get("tinfoil")):
            found.append(("tinfoil", "pharma", info["name"]))
            seen.add(cid)

    # 4. Lootboxes
    for key, info in LOOTBOXES_CATALOG.items():
        cid = info["id"]
        if cid in seen:
            continue
        if active_items.get(cid, 0) or active_items.get(key, 0):
            found.append((cid, "lootbox", info["name"]))
            seen.add(cid)

    return found


# -----------------------------------------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------------------------------------

@market_router.message(Command("market", "bazar", "рынок", "базар", "барахолка", ignore_case=True, ignore_mention=True))
async def cmd_market(message: types.Message, board_id: str | None = None, stream: str = 'ru') -> None:
    """Главный экран каталога Барахолки."""
    b_id = board_id or "b"
    user_id = message.from_user.id if message.from_user else message.chat.id
    db = await get_pool()
    wallet_balance = await get_user_global_balance(db, user_id)

    text = (
        "🛒 <b>P2P БАРАХОЛКА / ЧЁРНЫЙ РЫНОК ДВАЧА</b>\n\n"
        "Здесь аноны продают и покупают редкое оружие, шмот, кейсы и аптеку без посредников.\n\n"
        f"💰 <b>Твой кошелек:</b> <code>{wallet_balance:,.2f} ₪</code>\n"
        "🛡️ <b>Безопасность:</b> Эскроу-депонирование (предмет блокируется до покупки)\n"
        "💸 <b>Налог Абу:</b> 5% с продавца при успешной сделке\n\n"
        "<i>Выбери категорию товаров ниже или выстави свой лот командой /sell:</i>"
    )
    kb = build_market_main_menu_kb()
    await _render_market_view(message, text, kb, category="shop")


@market_router.message(Command("sell", "продать", "лот", "выставить", ignore_case=True, ignore_mention=True))
async def cmd_sell(message: types.Message, board_id: str | None = None, stream: str = 'ru') -> None:
    """Команда выставления предмета на продажу или интерактивный визард."""
    b_id = board_id or "b"
    user_id = message.from_user.id if message.from_user else message.chat.id
    db = await get_pool()

    parts = (message.text or "").split()[1:]

    # Если переданы аргументы: /sell <предмет> <цена>
    if len(parts) >= 2:
        raw_price = parts[-1].lower().replace("к", "k").replace("₪", "").replace(",", ".")
        raw_item = " ".join(parts[:-1])

        try:
            if raw_price.endswith("k"):
                price = float(raw_price[:-1]) * 1000
            elif raw_price.endswith("m"):
                price = float(raw_price[:-1]) * 1000000
            else:
                price = float(raw_price)
        except ValueError:
            await message.answer("❌ Неверный формат цены. Пример: <code>/sell заточка 500</code>", parse_mode="HTML")
            return

        resolved = find_item_by_name_or_id(raw_item)
        if not resolved:
            await message.answer(
                f"❌ Не удалось опознать предмет «{raw_item}».\n"
                "Используй /sell без параметров, чтобы выбрать предмет из инвентаря.",
                parse_mode="HTML"
            )
            return

        item_id, item_type, item_name = resolved
        ok, listing, err = await create_market_listing(db, user_id, b_id, item_id, price, item_type=item_type)
        if not ok:
            await message.answer(f"❌ Ошибка выставления: {err}", parse_mode="HTML")
            return

        fee_est = max(1.0, round(price * 0.05, 2)) if price >= 1.0 else round(price * 0.05, 2)
        payout_est = round(price - fee_est, 2)

        resp = (
            f"🏷 <b>ЛОТ #{listing['id']} УСПЕШНО ВЫСТАВЛЕН НА БАЗАР!</b>\n\n"
            f"📦 <b>Предмет:</b> {item_name}\n"
            f"💰 <b>Цена продажи:</b> <code>{price:,.2f} ₪</code>\n"
            f"💸 <b>Налог Абу (5%):</b> <code>-{fee_est:,.2f} ₪</code>\n"
            f"💵 <b>Ты получишь при покупке:</b> <code>+{payout_est:,.2f} ₪</code>\n\n"
            f"<i>Предмет перемещен на эскроу-склад Базара. Ты можешь снять его в /market в разделе «Мои лоты».</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Мои лоты", callback_data="market_my_lots:1")],
            [InlineKeyboardButton(text="🛒 В Барахолку", callback_data="market_main_hub")],
        ])
        await message.answer(resp, reply_markup=kb, parse_mode="HTML")
        return

    # Интерактивный режим: /sell без параметров
    active_items = await _load_user_active_items_for_update(db, user_id, b_id)
    sellable = get_user_sellable_items_list(active_items)

    if not sellable:
        text = (
            "🎒 <b>ПРОДАЖА ПРЕДМЕТОВ НА БАЗАРЕ</b>\n\n"
            "Твой инвентарь пуст, нищеброд! Тебе нечего выставить на продажу.\n"
            "Купи лут в /shop, выбей из кейсов или добудь в грабежах /rob."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏬 В Магазин (/shop)", callback_data="shop_main_hub")],
            [InlineKeyboardButton(text="🛒 В Барахолку", callback_data="market_main_hub")],
        ])
        await _render_market_view(message, text, kb, category="shop")
        return

    text = (
        "🎒 <b>ВЫБЕРИ ПРЕДМЕТ ДЛЯ ПРОДАЖИ:</b>\n\n"
        "Нажми на предмет из твоего инвентаря, чтобы выбрать цену лота:\n"
        "<i>(Или укажи сразу: <code>/sell &lt;название&gt; &lt;цена&gt;</code>)</i>"
    )
    buttons = []
    for s_id, s_type, s_name in sellable:
        buttons.append([InlineKeyboardButton(text=f"🏷 {s_name}", callback_data=f"market_sell_item:{s_id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад на Базар", callback_data="market_main_hub")])
    await _render_market_view(message, text, InlineKeyboardMarkup(inline_keyboard=buttons), category="shop")


# -----------------------------------------------------------------------------
# Telegram Callback Query Handlers
# -----------------------------------------------------------------------------

@market_router.callback_query(F.data == "market_noop")
async def cb_market_noop(callback: types.CallbackQuery):
    """Заглушка для неактивных кнопок пагинации."""
    await callback.answer()


@market_router.callback_query(F.data == "market_main_hub")
async def cb_market_main_hub(callback: types.CallbackQuery, board_id: str | None = None):
    """Возврат в главное меню Барахолки."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()
    wallet_balance = await get_user_global_balance(db, user_id)

    text = (
        "🛒 <b>P2P БАРАХОЛКА / ЧЁРНЫЙ РЫНОК ДВАЧА</b>\n\n"
        "Здесь аноны продают и покупают редкое оружие, шмот, кейсы и аптеку без посредников.\n\n"
        f"💰 <b>Твой кошелек:</b> <code>{wallet_balance:,.2f} ₪</code>\n"
        "🛡️ <b>Безопасность:</b> Эскроу-депонирование (предмет блокируется до покупки)\n"
        "💸 <b>Налог Абу:</b> 5% с продавца при успешной сделке\n\n"
        "<i>Выбери категорию товаров ниже или выстави свой лот командой /sell:</i>"
    )
    kb = build_market_main_menu_kb()
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_cat:") | F.data.startswith("market_cat_"))
async def cb_market_cat(callback: types.CallbackQuery, board_id: str | None = None):
    """Просмотр категории каталога с пагинацией и сортировкой."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    raw = callback.data

    # Разбираем формат: market_cat:<category>:<sort>:<page> или market_cat_<category>
    if ":" in raw:
        parts = raw.split(":")
        category = parts[1] if len(parts) > 1 else "all"
        sort_order = parts[2] if len(parts) > 2 else "price_asc"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    else:
        category = raw.replace("market_cat_", "")
        sort_order = "price_asc"
        page = 1

    db = await get_pool()
    cat_filter = None if category == "all" else category
    items, total_pages, total_count = await get_market_catalog(db, category=cat_filter, sort_order=sort_order, page=page, per_page=5)

    cat_name = MARKET_CATEGORIES.get(category, "Все лоты")
    sort_labels = {"price_asc": "Дешевле", "price_desc": "Дороже", "newest": "Новые"}
    sort_label = sort_labels.get(sort_order, "По цене")

    lines = [
        f"🛒 <b>КАТАЛОГ БАРАХОЛКИ — {cat_name}</b>",
        f"Сортировка: <b>{sort_label}</b> | Лотов: <b>{total_count}</b> (Стр. {page}/{total_pages})",
        "<code>────────────────────────</code>",
    ]

    if not items:
        lines.append("\n<i>В этой категории сейчас нет активных лотов.</i>")
        lines.append("<i>Будь первым — продай что-нибудь через /sell!</i>")
    else:
        for it in items:
            p_str = f"{int(it['price']):,} ₪" if it['price'].is_integer() else f"{it['price']:,.2f} ₪"
            is_own = " <i>(твой лот)</i>" if it["seller_id"] == user_id else ""
            lines.append(f"• <b>{it['item_name']}</b> — <code>{p_str}</code>{is_own}")

    text = "\n".join(lines)
    kb = build_market_catalog_kb(category, sort_order, page, total_pages, items)
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_lot:"))
async def cb_market_lot(callback: types.CallbackQuery, board_id: str | None = None):
    """Детальный просмотр лота на Базаре."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    raw_id = callback.data.split(":", 1)[1]
    lot_id = int(raw_id) if raw_id.isdigit() else 0

    db = await get_pool()
    lot = await get_market_listing(db, lot_id)

    if not lot or lot["status"] != "active":
        await callback.answer("❌ Этот лот уже продан или снят с продажи.", show_alert=True)
        return

    price = lot["price"]
    price_str = f"{int(price):,} ₪" if price.is_integer() else f"{price:,.2f} ₪"
    is_seller = (lot["seller_id"] == user_id)

    meta = lot.get("item_data", {})
    desc_lines = []
    if meta.get("is_permanent"):
        desc_lines.append("✨ <b>Статус:</b> <code>ВЕЧНЫЙ ПРЕДМЕТ (Permanent)</code>")
    elif meta.get("remaining_seconds"):
        rem_h = int(meta["remaining_seconds"] / 3600)
        desc_lines.append(f"⏳ <b>Остаток срока:</b> <code>{rem_h} часов</code>")

    if meta.get("defense"):
        desc_lines.append(f"🛡 <b>Защита:</b> +{meta['defense']}")
    if meta.get("toxicity"):
        desc_lines.append(f"☣ <b>Токсичность:</b> +{meta['toxicity']}")

    desc_text = "\n".join(desc_lines)
    if desc_text:
        desc_text = f"\n{desc_text}\n"

    text = (
        f"🏷 <b>ЛОТ #{lot['id']}: {lot['item_name']}</b>\n\n"
        f"📁 <b>Категория:</b> {MARKET_CATEGORIES.get(lot['item_type'], lot['item_type'])}\n"
        f"💰 <b>Цена:</b> <code>{price_str}</code>\n"
        f"{desc_text}\n"
        f"🏛 <i>Включает 5% сбор Абу при покупке. Товар передается мгновенно.</i>"
    )

    kb_rows = []
    if is_seller:
        kb_rows.append([InlineKeyboardButton(text=f"❌ Снять с продажи #{lot['id']}", callback_data=f"market_cancel:{lot['id']}")])
    else:
        kb_rows.append([InlineKeyboardButton(text=f"💰 Купить за {price_str}", callback_data=f"market_buy:{lot['id']}")])

    kb_rows.append([
        InlineKeyboardButton(text="⬅️ Назад в каталог", callback_data=f"market_cat:{lot['item_type']}:price_asc:1"),
        InlineKeyboardButton(text="🛒 Главная Базара", callback_data="market_main_hub"),
    ])

    await _render_market_view(callback, text, InlineKeyboardMarkup(inline_keyboard=kb_rows), category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_buy:") | F.data.startswith("market_buy_"))
async def cb_market_buy(callback: types.CallbackQuery, board_id: str | None = None):
    """Покупка лота на Базаре."""
    b_id = board_id or "b"
    buyer_id = callback.from_user.id
    raw = callback.data
    raw_id = raw.split(":", 1)[1] if ":" in raw else raw.replace("market_buy_", "")
    lot_id = int(raw_id) if raw_id.isdigit() else 0

    db = await get_pool()
    ok, seller_id, price, payout, fee, item_dict, err = await buy_market_listing(db, lot_id, buyer_id, b_id)

    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    # Отправляем уведомление продавцу
    item_name = item_dict.get("item_name", "Предмет") if item_dict else "Предмет"
    await notify_seller_lot_sold(callback.bot, seller_id, item_name, price, payout, fee)

    price_str = f"{int(price):,} ₪" if price.is_integer() else f"{price:,.2f} ₪"
    text = (
        f"🎉 <b>ПОКУПКА УСПЕШНО СОВЕРШЕНА!</b>\n\n"
        f"📦 <b>Куплен предмет:</b> <b>{item_name}</b>\n"
        f"💸 <b>Списано с кошелька:</b> <code>{price_str}</code>\n"
        f"🏛 <b>Комиссия Абу (5%):</b> <code>{fee:,.2f} ₪</code>\n\n"
        f"<i>Предмет зачислен в твой инвентарь и готов к использованию!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎒 Мой Инвентарь (/inv)", callback_data="avatar_view")],
        [InlineKeyboardButton(text="🛒 Назад на Базар", callback_data="market_main_hub")],
    ])
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer("✅ Предмет успешно куплен!", show_alert=False)


@market_router.message(Command("my_lots", "мои_лоты", "mylots", ignore_case=True, ignore_mention=True))
async def cmd_my_lots(message: types.Message, board_id: str | None = None):
    """Slash command to view user's active market listings."""
    b_id = board_id or "b"
    user_id = message.from_user.id
    db = await get_pool()
    listings = await get_user_listings(db, user_id, status="active")

    if not listings:
        text = (
            "📦 <b>МОИ АКТИВНЫЕ ЛОТЫ</b>\n\n"
            "У тебя пока нет активных лотов на Базаре.\n"
            "Выстави ненужный шмот командой /sell!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Продать предмет (/sell)", callback_data="market_sell_menu")],
            [InlineKeyboardButton(text="🛒 На Базар (/market)", callback_data="market_main_hub")],
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    lines = ["📦 <b>ТВОИ АКТИВНЫЕ ЛОТЫ НА БАЗАРЕ:</b>\n"]
    kb_rows = []
    for lot in listings:
        p_str = f"{int(lot['price']):,} ₪" if lot['price'].is_integer() else f"{lot['price']:,.2f} ₪"
        lines.append(f"• Лот <b>#{lot['id']}</b>: {lot['item_name']} — <code>{p_str}</code>")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"❌ Снять #{lot['id']} ({lot['item_name'][:12]})",
                callback_data=f"market_cancel:{lot['id']}"
            )
        ])
    kb_rows.append([
        InlineKeyboardButton(text="🏷 Продать еще (/sell)", callback_data="market_sell_menu"),
        InlineKeyboardButton(text="⬅️ Назад на Базар", callback_data="market_main_hub"),
    ])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@market_router.callback_query(F.data.startswith("market_my_lots") | F.data.startswith("market_my_lots:"))
async def cb_market_my_lots(callback: types.CallbackQuery, board_id: str | None = None):
    """Список активных лотов пользователя."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()
    listings = await get_user_listings(db, user_id, status="active")

    if not listings:
        text = (
            "📦 <b>МОИ АКТИВНЫЕ ЛОТЫ</b>\n\n"
            "У тебя пока нет активных лотов на Базаре.\n"
            "Выстави ненужный шмот, пушки или кейсы командой /sell!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Продать предмет (/sell)", callback_data="market_sell_menu")],
            [InlineKeyboardButton(text="⬅️ Назад на Базар", callback_data="market_main_hub")],
        ])
        await _render_market_view(callback, text, kb, category="shop")
        await callback.answer()
        return

    lines = [
        "📦 <b>ТВОИ АКТИВНЫЕ ЛОТЫ НА БАЗАРЕ:</b>\n",
    ]
    kb_rows = []
    for lot in listings:
        p_str = f"{int(lot['price']):,} ₪" if lot['price'].is_integer() else f"{lot['price']:,.2f} ₪"
        lines.append(f"• Лот <b>#{lot['id']}</b>: {lot['item_name']} — <code>{p_str}</code>")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"❌ Снять #{lot['id']} ({lot['item_name'][:12]})",
                callback_data=f"market_cancel:{lot['id']}"
            )
        ])

    kb_rows.append([
        InlineKeyboardButton(text="🏷 Продать еще (/sell)", callback_data="market_sell_menu"),
        InlineKeyboardButton(text="⬅️ Назад на Базар", callback_data="market_main_hub"),
    ])

    text = "\n".join(lines)
    await _render_market_view(callback, text, InlineKeyboardMarkup(inline_keyboard=kb_rows), category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_cancel:") | F.data.startswith("market_cancel_"))
async def cb_market_cancel(callback: types.CallbackQuery, board_id: str | None = None):
    """Снятие лота с продажи и возврат предмета владельцу."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    raw = callback.data
    raw_id = raw.split(":", 1)[1] if ":" in raw else raw.replace("market_cancel_", "")
    lot_id = int(raw_id) if raw_id.isdigit() else 0

    db = await get_pool()
    ok, item_dict, err = await cancel_market_listing(db, lot_id, user_id, b_id)

    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    item_name = item_dict.get("item_name", "Предмет") if item_dict else "Предмет"
    text = (
        f"✅ <b>ЛОТ #{lot_id} СНЯТ С ПРОДАЖИ</b>\n\n"
        f"📦 Предмет <b>{item_name}</b> возвращен в твой инвентарь."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Мои лоты", callback_data="market_my_lots:1")],
        [InlineKeyboardButton(text="🛒 Главная Базара", callback_data="market_main_hub")],
    ])
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer("✅ Лот снят с продажи", show_alert=False)


@market_router.callback_query(F.data == "market_sell_menu")
async def cb_market_sell_menu(callback: types.CallbackQuery, board_id: str | None = None):
    """Интерактивное меню выбора предмета для продажи."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    db = await get_pool()
    active_items = await _load_user_active_items_for_update(db, user_id, b_id)
    sellable = get_user_sellable_items_list(active_items)

    if not sellable:
        text = (
            "🎒 <b>ПРОДАЖА ПРЕДМЕТОВ НА БАЗАРЕ</b>\n\n"
            "Твой инвентарь пуст, нищеброд! Тебе нечего выставить на продажу.\n"
            "Купи лут в /shop, выбей из кейсов или добудь в грабежах /rob."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏬 В Магазин (/shop)", callback_data="shop_main_hub")],
            [InlineKeyboardButton(text="🛒 В Барахолку", callback_data="market_main_hub")],
        ])
        await _render_market_view(callback, text, kb, category="shop")
        await callback.answer()
        return

    text = (
        "🎒 <b>ВЫБЕРИ ПРЕДМЕТ ДЛЯ ПРОДАЖИ:</b>\n\n"
        "Нажми на предмет ниже, чтобы установить цену лота:\n"
        "<i>(Или введи: <code>/sell &lt;предмет&gt; &lt;цена&gt;</code>)</i>"
    )
    buttons = []
    for s_id, s_type, s_name in sellable:
        buttons.append([InlineKeyboardButton(text=f"🏷 {s_name}", callback_data=f"market_sell_item:{s_id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад на Базар", callback_data="market_main_hub")])
    await _render_market_view(callback, text, InlineKeyboardMarkup(inline_keyboard=buttons), category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_sell_item:"))
async def cb_market_sell_item(callback: types.CallbackQuery, board_id: str | None = None):
    """Выбор цены для выставления выбранного предмета с пресетами."""
    item_id = callback.data.split(":", 1)[1]
    detected_type, item_name, _ = classify_item(item_id)

    text = (
        f"🏷 <b>ВЫСТАВЛЕНИЕ НА ПРОДАЖУ: {item_name}</b>\n\n"
        f"Выбери готовую цену из кнопок ниже или отправь в чат точную сумму:\n"
        f"<code>/sell {item_id} [цена]</code>\n\n"
        f"<i>Налог Абу 5% будет удержан с покупателя при покупке.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50 ₪", callback_data=f"market_do_sell:{item_id}:50"),
            InlineKeyboardButton(text="100 ₪", callback_data=f"market_do_sell:{item_id}:100"),
            InlineKeyboardButton(text="250 ₪", callback_data=f"market_do_sell:{item_id}:250"),
        ],
        [
            InlineKeyboardButton(text="500 ₪", callback_data=f"market_do_sell:{item_id}:500"),
            InlineKeyboardButton(text="1000 ₪", callback_data=f"market_do_sell:{item_id}:1000"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Отмена", callback_data="market_sell_menu"),
        ]
    ])
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer()


@market_router.callback_query(F.data.startswith("market_do_sell:"))
async def cb_market_do_sell(callback: types.CallbackQuery, board_id: str | None = None):
    """Создание лота по нажатию кнопки готового пресета цены."""
    b_id = board_id or "b"
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    item_id = parts[1]
    price = float(parts[2])

    db = await get_pool()
    ok, listing, err = await create_market_listing(db, user_id, b_id, item_id, price)

    if not ok:
        await callback.answer(f"❌ {err}", show_alert=True)
        return

    item_name = listing["item_name"]
    fee_est = max(1.0, round(price * 0.05, 2)) if price >= 1.0 else round(price * 0.05, 2)
    payout_est = round(price - fee_est, 2)

    text = (
        f"🏷 <b>ЛОТ #{listing['id']} ВЫСТАВЛЕН НА БАЗАР!</b>\n\n"
        f"📦 <b>Товар:</b> {item_name}\n"
        f"💰 <b>Цена:</b> <code>{price:,.2f} ₪</code>\n"
        f"💵 <b>Выплата продавцу:</b> <code>+{payout_est:,.2f} ₪</code> (за вычетом 5% Абу)\n\n"
        f"<i>Предмет перемещен на эскроу-склад Базара.</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Мои лоты", callback_data="market_my_lots:1")],
        [InlineKeyboardButton(text="🛒 Главная Базара", callback_data="market_main_hub")],
    ])
    await _render_market_view(callback, text, kb, category="shop")
    await callback.answer("✅ Лот успешно выставлен!", show_alert=False)
