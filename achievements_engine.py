# -*- coding: utf-8 -*-
"""
achievements_engine.py — Dvach Achievements, Quests & Trophy System
Tracks board milestones, gear sets, work progress, PvP victories, and awards cash & titles.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger("runtime")

_ACHIEVEMENT_LOCK = asyncio.Lock()
_IN_FLIGHT_ACHIEVEMENT_CLAIMS: Set[Tuple[int, str]] = set()

ACHIEVEMENTS_CATALOG = {
    "ach_work_10": {
        "id": "ach_work_10",
        "name": "💼 Первая получка",
        "desc": "Закрыть 10 смен на бирже труда (/work).",
        "reward_cash": 100,
        "icon": "💼",
        "category": "work"
    },
    "ach_work_50": {
        "id": "ach_work_50",
        "name": "⚙️ Ударник Пятилетки",
        "desc": "Закрыть 50 смен на бирже труда.",
        "reward_cash": 500,
        "icon": "⚙️",
        "category": "work"
    },
    "ach_work_100": {
        "id": "ach_work_100",
        "name": "🏆 Герой Капитализма",
        "desc": "Закрыть 100 смен на бирже труда.",
        "reward_cash": 1500,
        "icon": "🏆",
        "category": "work"
    },
    "ach_work_150": {
        "id": "ach_work_150",
        "name": "💄 Эскортный Магнат",
        "desc": "Закрыть 150 смен на бирже труда.",
        "reward_cash": 2500,
        "icon": "💄",
        "category": "work"
    },
    "ach_work_250": {
        "id": "ach_work_250",
        "name": "🪙 Король Пампа & Дампа",
        "desc": "Закрыть 250 смен на бирже труда.",
        "reward_cash": 4000,
        "icon": "🪙",
        "category": "work"
    },
    "ach_work_400": {
        "id": "ach_work_400",
        "name": "👑 Правая Рука Абу",
        "desc": "Закрыть 400 смен на бирже труда.",
        "reward_cash": 7500,
        "icon": "👑",
        "category": "work"
    },
    "ach_work_600": {
        "id": "ach_work_600",
        "name": "👁️ Архитектор Бытия",
        "desc": "Закрыть 600 смен на бирже труда.",
        "reward_cash": 15000,
        "icon": "👁️",
        "category": "work"
    },
    "ach_work_800": {
        "id": "ach_work_800",
        "name": "🎖️ Ветеран Трудового Фронта",
        "desc": "Закрыть 800 смен на бирже труда.",
        "reward_cash": 25000,
        "icon": "🎖️",
        "category": "work"
    },
    "ach_work_1000": {
        "id": "ach_work_1000",
        "name": "👑 Бессмертный Стахановец",
        "desc": "Закрыть 1000 смен на бирже труда.",
        "reward_cash": 50000,
        "icon": "👑",
        "category": "work"
    },
    "ach_work_1337": {
        "id": "ach_work_1337",
        "name": "⚡ Абсолютный Демиург Завода",
        "desc": "Закрыть 1337 смен на бирже труда.",
        "reward_cash": 100000,
        "icon": "⚡",
        "category": "work"
    },
    "ach_set_wasserman": {
        "id": "ach_set_wasserman",
        "name": "🦺 Истинный Онотоле",
        "desc": "Собрать и надеть Сет Вассермана (Жилетка + Очки).",
        "reward_cash": 400,
        "icon": "🦺",
        "category": "wardrobe"
    },
    "ach_set_riot": {
        "id": "ach_set_riot",
        "name": "🪖 Силовик Борды",
        "desc": "Собрать и надеть Сет ОМОНа (Шлем + Берцы).",
        "reward_cash": 600,
        "icon": "🪖",
        "category": "wardrobe"
    },
    "ach_set_anime": {
        "id": "ach_set_anime",
        "name": "👘 Главный Вайфувед",
        "desc": "Собрать и надеть Сет Анимешника (Ушки + Худи).",
        "reward_cash": 350,
        "icon": "👘",
        "category": "wardrobe"
    },
    "ach_set_skuf": {
        "id": "ach_set_skuf",
        "name": "🩲 Повелитель Пивнухи",
        "desc": "Собрать и надеть Сет Подъездного Сыча (Корона + Треники).",
        "reward_cash": 300,
        "icon": "🩲",
        "category": "wardrobe"
    },
    "ach_set_ward6": {
        "id": "ach_set_ward6",
        "name": "🥼 Пациент №1",
        "desc": "Собрать и надеть Сет Палаты №6 (Смирительная рубашка + Фольга).",
        "reward_cash": 450,
        "icon": "🥼",
        "category": "wardrobe"
    },
    "ach_set_neo": {
        "id": "ach_set_neo",
        "name": "🕶️ Избранный Матрицы",
        "desc": "Собрать и надеть Сет Нео (Плащ Нео + Маска Анонимуса).",
        "reward_cash": 700,
        "icon": "🕶️",
        "category": "wardrobe"
    },
    "ach_wardrobe_enthusiast": {
        "id": "ach_wardrobe_enthusiast",
        "name": "👔 Модник Борды",
        "desc": "Собрать 5+ вещей в своем гардеробе.",
        "reward_cash": 500,
        "icon": "👔",
        "category": "wardrobe"
    },
    "ach_wardrobe_collector": {
        "id": "ach_wardrobe_collector",
        "name": "🎩 Шмоточный Олигарх",
        "desc": "Собрать 15+ вещей в своем гардеробе.",
        "reward_cash": 1500,
        "icon": "🎩",
        "category": "wardrobe"
    },
    "ach_fashion_demon": {
        "id": "ach_fashion_demon",
        "name": "👑 Икона Стиля Двача",
        "desc": "Собрать 30+ вещей в своем гардеробе.",
        "reward_cash": 5000,
        "icon": "👑",
        "category": "wardrobe"
    },
    "ach_slots_jackpot": {
        "id": "ach_slots_jackpot",
        "name": "🎰 Король Азарта 777",
        "desc": "Сорвать Джекпот x50 в Слотах 777.",
        "reward_cash": 1000,
        "icon": "🎰",
        "category": "casino"
    },
    "ach_robber": {
        "id": "ach_robber",
        "name": "🔪 Джентльмен Удачи",
        "desc": "Успешно ограбить другого анона с заточкой (/rob).",
        "reward_cash": 500,
        "icon": "🔪",
        "category": "pvp"
    },
    "ach_pepperspray": {
        "id": "ach_pepperspray",
        "name": "🧯 Глаз за Глаз",
        "desc": "Ослепить нападающего грабителя Перцовым баллончиком.",
        "reward_cash": 300,
        "icon": "🧯",
        "category": "pvp"
    },
    "ach_first_work": {
        "id": "ach_first_work",
        "name": "💼 Первый рабочий день",
        "desc": "Выйти на первую смену на бирже труда (/work).",
        "reward_cash": 50,
        "icon": "💼",
        "category": "work"
    },
    "ach_duel_win": {
        "id": "ach_duel_win",
        "name": "⚔️ Дуэлянт Борды",
        "desc": "Одержать победу в дуэли со ставкой (/duel).",
        "reward_cash": 200,
        "icon": "⚔️",
        "category": "pvp"
    },
    "ach_tinfoil_protect": {
        "id": "ach_tinfoil_protect",
        "name": "👽 Защита от Рептилоидов",
        "desc": "Отразить нападение с помощью Шапочки из фольги.",
        "reward_cash": 250,
        "icon": "👽",
        "category": "pvp"
    },
    "ach_mutegun_sniper": {
        "id": "ach_mutegun_sniper",
        "name": "🔇 Снайпер Двача",
        "desc": "Успешно выстрелить из Мут-Гана (/shoot) и отправить рака в мут.",
        "reward_cash": 300,
        "icon": "🔇",
        "category": "pvp"
    },
    "ach_partyvan_called": {
        "id": "ach_partyvan_called",
        "name": "🚔 Донос Года",
        "desc": "Вызвать Пативэн с ОМОНом на тред (/partyvan).",
        "reward_cash": 500,
        "icon": "🚔",
        "category": "pvp"
    },
    "ach_blackjack_21": {
        "id": "ach_blackjack_21",
        "name": "🃏 Настоящий Блэкджек",
        "desc": "Собрать 21 очко с раздачи в Блэкджеке (/bj).",
        "reward_cash": 400,
        "icon": "🃏",
        "category": "casino"
    },
    "ach_coin_streak": {
        "id": "ach_coin_streak",
        "name": "🪙 Мастер Монетки",
        "desc": "Выиграть в Коинфлип со ставкой (/coinflip).",
        "reward_cash": 200,
        "icon": "🪙",
        "category": "casino"
    },
    "ach_janitor_clean": {
        "id": "ach_janitor_clean",
        "name": "🧹 Чистильщик Борды",
        "desc": "Удалить мусорный пост с помощью Билета Дворника (/del).",
        "reward_cash": 200,
        "icon": "🧹",
        "category": "work"
    },
    "ach_cases_10": {
        "id": "ach_cases_10",
        "name": "📦 Кейсовый Олигарх",
        "desc": "Открыть 10 лутбоксов или сейфов.",
        "reward_cash": 750,
        "icon": "📦",
        "category": "lootbox"
    },
    "ach_mmm_investor": {
        "id": "ach_mmm_investor",
        "name": "🎖️ Инвестор МММ",
        "desc": "Попал под Великую Стрижку Абу депозитов свыше 500,000 ₪.",
        "reward_cash": 0,
        "icon": "🎖️",
        "category": "bank"
    }
}


def check_and_unlock_achievement(
    active_items: Optional[Dict[str, Any]],
    ach_id: str
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Unlocks an achievement if not already unlocked.
    Includes anti-exploit protection against duplicate reward claims,
    and handles malformed unlocked_achievements types cleanly.
    Returns: (was_unlocked_now, achievement_info)
    """
    if not isinstance(active_items, dict):
        return False, None

    if not ach_id or ach_id not in ACHIEVEMENTS_CATALOG:
        return False, None

    raw_unlocked = active_items.get("unlocked_achievements")
    if not isinstance(raw_unlocked, list):
        if isinstance(raw_unlocked, (set, tuple)):
            unlocked_list = list(raw_unlocked)
        elif isinstance(raw_unlocked, str):
            unlocked_list = [raw_unlocked] if raw_unlocked else []
        else:
            unlocked_list = []
        active_items["unlocked_achievements"] = unlocked_list
    else:
        unlocked_list = raw_unlocked

    # Anti-exploit: check claimed rewards registry in active_items
    claimed_list = active_items.get("claimed_achievement_rewards")
    if isinstance(claimed_list, (list, set, tuple)) and ach_id in claimed_list:
        if ach_id not in unlocked_list:
            unlocked_list.append(ach_id)
        return False, None

    if ach_id in unlocked_list:
        return False, None  # Already unlocked

    unlocked_list.append(ach_id)

    # Persist in claimed rewards list to prevent double-claiming even if unlocked_achievements is wiped
    if not isinstance(active_items.get("claimed_achievement_rewards"), list):
        active_items["claimed_achievement_rewards"] = list(unlocked_list)
    else:
        if ach_id not in active_items["claimed_achievement_rewards"]:
            active_items["claimed_achievement_rewards"].append(ach_id)

    return True, ACHIEVEMENTS_CATALOG[ach_id]


async def atomic_claim_achievement_reward(
    db,
    user_id: int,
    board_id: str,
    ach_id: str
) -> Tuple[bool, int, Optional[Dict[str, Any]]]:
    """
    Safely and atomically verifies eligibility, marks achievement as claimed,
    and credits reward_cash to the user balance in SQLite inside a transaction.
    Guarantees zero double-payouts under concurrent requests.
    Returns: (was_claimed_now: bool, reward_amount: int, ach_info: Optional[Dict])
    """
    if not ach_id or ach_id not in ACHIEVEMENTS_CATALOG:
        return False, 0, None
    if not user_id or user_id <= 0:
        return False, 0, None

    claim_key = (user_id, ach_id)
    async with _ACHIEVEMENT_LOCK:
        if claim_key in _IN_FLIGHT_ACHIEVEMENT_CLAIMS:
            return False, 0, None
        _IN_FLIGHT_ACHIEVEMENT_CLAIMS.add(claim_key)

    try:
        from common.db_pool import db_transaction
        async with db_transaction(db):
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, board_id)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return False, 0, None

            raw_items = row[0]
            items = {}
            if raw_items:
                try:
                    items = json.loads(raw_items) if isinstance(raw_items, str) else dict(raw_items)
                except Exception:
                    items = {}

            unlocked, ach_info = check_and_unlock_achievement(items, ach_id)
            if not unlocked or not ach_info:
                return False, 0, None

            reward = int(ach_info.get("reward_cash", 0))

            # Atomic DB update: save active_items and credit reward_cash
            await db.execute(
                "UPDATE Users SET active_items = ?, balance = balance + ? WHERE user_id = ? AND board_id = ?",
                (json.dumps(items), reward, user_id, board_id)
            )

            # Record ledger transaction if reward > 0
            if reward > 0:
                try:
                    from common.database import record_user_transaction
                    await record_user_transaction(
                        db, user_id, reward, 'achievement',
                        f"Награда за ачивку: {ach_info.get('name', ach_id)}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record achievement tx: {e}")

            return True, reward, ach_info
    finally:
        async with _ACHIEVEMENT_LOCK:
            _IN_FLIGHT_ACHIEVEMENT_CLAIMS.discard(claim_key)


def get_user_achievements(active_items: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns list of all achievements with their unlocked status.
    Auto-checks any equipped wardrobe sets to retroactively award trophies.
    """
    if not isinstance(active_items, dict):
        active_items = {}

    try:
        import wardrobe_engine
        wardrobe_engine.check_wardrobe_set_achievements(active_items)
        wardrobe_engine.check_wardrobe_collection_achievements(active_items)
    except Exception:
        pass

    raw_unlocked = active_items.get("unlocked_achievements", [])
    if isinstance(raw_unlocked, list):
        unlocked_list = set(raw_unlocked)
    elif isinstance(raw_unlocked, (set, tuple)):
        unlocked_list = set(raw_unlocked)
    elif isinstance(raw_unlocked, str):
        unlocked_list = {raw_unlocked} if raw_unlocked else set()
    else:
        unlocked_list = set()

    result = []
    for ach_id, ach_info in ACHIEVEMENTS_CATALOG.items():
        info = dict(ach_info)
        info["is_unlocked"] = (ach_id in unlocked_list)
        result.append(info)
    return result


def build_achievements_content(user_id: int, active_items: Optional[Dict[str, Any]]) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Renders achievements view text and keyboard within Telegram photo caption limits.
    """
    all_ach = get_user_achievements(active_items)
    unlocked = [a for a in all_ach if a["is_unlocked"]]
    locked = [a for a in all_ach if not a["is_unlocked"]]
    unlocked_count = len(unlocked)
    total_count = len(all_ach)
    pct = int((unlocked_count / total_count) * 100)
    total_reward = sum(a["reward_cash"] for a in unlocked)

    lines = [
        "🏆 <b>ДОСТИЖЕНИЯ И ТРОФЕИ АНОНА</b>",
        f"📊 Прогресс: <b>{unlocked_count}/{total_count} ({pct}%)</b> | Заработано: <b>+{total_reward:,} ₪</b>\n",
    ]

    if unlocked:
        lines.append("🎖️ <b>Полученные трофеи:</b>")
        for a in unlocked[:6]:
            lines.append(f"  ✅ <b>{a['name']}</b>")
        if len(unlocked) > 6:
            lines.append(f"  <i>...и еще {len(unlocked) - 6} ачивок</i>")
        lines.append("")

    if locked:
        lines.append("🎯 <b>Ближайшие цели для выполнения:</b>")
        for a in locked[:6]:
            lines.append(f"  🔒 <b>{a['name']}</b> <i>(+{a['reward_cash']} ₪)</i>\n     └ {a['desc']}")
        if len(locked) > 6:
            lines.append(f"\n<i>Всего закрыто {unlocked_count} из {total_count} ачивок.</i>")

    lines.append("\n💡 <i>Выполняй задания на борде для получения наград!</i>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎭 Мой Персонаж RPG", callback_data="avatar_view"),
            InlineKeyboardButton(text="🎽 Гардероб", callback_data="wardrobe_dressing_room")
        ],
        [InlineKeyboardButton(text="⬅️ В Торговый Хаб", callback_data="shop_main_hub")]
    ])

    return "\n".join(lines), kb
