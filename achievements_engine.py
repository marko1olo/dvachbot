# -*- coding: utf-8 -*-
"""
achievements_engine.py — Dvach Achievements, Quests & Trophy System
Tracks board milestones, gear sets, work progress, PvP victories, and awards cash & titles.
"""

from typing import Dict, Any, List, Optional, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
        "desc": "Собрать и надеть Сет Подъездного Скуфа (Корона + Треники).",
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
    }
}


def check_and_unlock_achievement(
    active_items: Dict[str, Any],
    ach_id: str
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Unlocks an achievement if not already unlocked.
    Returns: (was_unlocked_now, achievement_info)
    """
    if ach_id not in ACHIEVEMENTS_CATALOG:
        return False, None

    unlocked_list = active_items.setdefault("unlocked_achievements", [])
    if ach_id in unlocked_list:
        return False, None  # Already unlocked

    unlocked_list.append(ach_id)
    return True, ACHIEVEMENTS_CATALOG[ach_id]


def get_user_achievements(active_items: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Returns list of all achievements with their unlocked status.
    Auto-checks any equipped wardrobe sets to retroactively award trophies.
    """
    try:
        import wardrobe_engine
        wardrobe_engine.check_wardrobe_set_achievements(active_items)
    except Exception:
        pass

    unlocked_list = active_items.get("unlocked_achievements", [])
    result = []
    for ach_id, ach_info in ACHIEVEMENTS_CATALOG.items():
        info = dict(ach_info)
        info["is_unlocked"] = (ach_id in unlocked_list)
        result.append(info)
    return result


def build_achievements_content(user_id: int, active_items: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
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
        f"🏆 <b>ДОСТИЖЕНИЯ И ТРОФЕИ АНОНА</b>",
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
