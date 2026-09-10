# -*- coding: utf-8 -*-
"""
Daily Work Quests Engine (Ежедневные наряды ТГАЧА).
Генерирует 3 ежедневных наряда на смену, отслеживает прогресс и выдает Премию от Абу (+7,500 ₪ + Мусорный Лутбокс).
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional


QUEST_POOL = [
    {"id": "work_shifts", "title": "💼 Отработать 2 смены на любой карьере", "target": 2},
    {"id": "side_hustle", "title": "🍾 Выполнить 1 любую шабашку (бутылки/помойка/стикеры)", "target": 1},
    {"id": "risk_action", "title": "🚪 Расклеить солевые стикеры или порыться в помойке", "target": 1},
]

DAILY_REWARD_CASH = 7500
DAILY_REWARD_ITEM = "trash_lootbox"


def _get_current_date_str(ts: Optional[int] = None) -> str:
    # Use MSK date (UTC+3)
    t = ts if ts is not None else int(time.time())
    dt = datetime.fromtimestamp(t + 3 * 3600, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def get_or_create_daily_quests(user_items: dict, now: Optional[int] = None) -> Dict[str, Any]:
    """
    Returns current daily quests dict. If day rolled over, generates fresh daily quests.
    """
    date_str = _get_current_date_str(now)
    dq = user_items.get("daily_quests")
    if not dq or dq.get("date") != date_str:
        quests = [
            {"id": "work_shifts", "title": "💼 Отработать 2 смены на любой карьере", "target": 2, "progress": 0},
            {"id": "side_hustle", "title": "🍾 Выполнить 1 любую шабашку (бутылки/помойка/стикеры)", "target": 1, "progress": 0},
            {"id": "risk_action", "title": "🚪 Расклеить стикеры или порыться в помойке", "target": 1, "progress": 0},
        ]
        dq = {
            "date": date_str,
            "quests": quests,
            "claimed": False,
            "reward_cash": DAILY_REWARD_CASH,
            "reward_item": DAILY_REWARD_ITEM,
        }
        user_items["daily_quests"] = dq
    return dq


def record_quest_progress(user_items: dict, event_type: str, count: int = 1, now: Optional[int] = None) -> bool:
    """
    Records progress for the given event type.
    Event types:
    - 'work': increments 'work_shifts'
    - 'side_hustle': increments 'side_hustle'
    - 'risk_action': increments 'risk_action' and 'side_hustle'
    """
    dq = get_or_create_daily_quests(user_items, now=now)
    if dq.get("claimed"):
        return False

    changed = False
    for q in dq.get("quests", []):
        qid = q["id"]
        if (event_type == "work" and qid == "work_shifts") or \
           (event_type in ["side_hustle", "risk_action"] and qid == "side_hustle") or \
           (event_type == "risk_action" and qid == "risk_action"):
            old_p = q.get("progress", 0)
            target = q.get("target", 1)
            new_p = min(target, old_p + count)
            if new_p != old_p:
                q["progress"] = new_p
                changed = True
    return changed


def are_all_quests_completed(user_items: dict, now: Optional[int] = None) -> bool:
    dq = get_or_create_daily_quests(user_items, now=now)
    quests = dq.get("quests", [])
    if not quests:
        return False
    return all(q.get("progress", 0) >= q.get("target", 1) for q in quests)


def claim_daily_quests_reward(user_items: dict, now: Optional[int] = None) -> Tuple[bool, int, str, Optional[str]]:
    """
    Claims the daily reward.
    Returns: (is_success, reward_cash, text_message, reward_item)
    """
    dq = get_or_create_daily_quests(user_items, now=now)
    if dq.get("claimed"):
        return False, 0, "❌ Ты уже забрал премию от Абу за сегодня! Приходи завтра.", None

    if not are_all_quests_completed(user_items, now=now):
        return False, 0, "❌ Не все наряды смены выполнены! Закрой все 3 пункта.", None

    dq["claimed"] = True
    cash = dq.get("reward_cash", DAILY_REWARD_CASH)
    item = dq.get("reward_item", DAILY_REWARD_ITEM)

    msg = (
        f"🎖 <b>ПРЕМИЯ ОТ АБУ ПОЛУЧЕНА!</b>\n\n"
        f"Ты честно выполнил все 3 наряда дня и принес пользу борде!\n"
        f"💰 Премия: <b>+{cash:,} ₪</b>\n"
        f"📦 Бонус: <b>Мусорный Лутбокс</b> добавлен в инвентарь!\n\n"
        f"<i>«Молодец, работяга. Не всё же тебе в /b/ говно постить.» — Абу</i>"
    )
    return True, cash, msg, item


def render_quests_text(user_items: dict, now: Optional[int] = None) -> Tuple[str, bool]:
    """
    Renders human-readable status for quests modal.
    Returns: (text, can_claim)
    """
    dq = get_or_create_daily_quests(user_items, now=now)
    date_str = dq.get("date", "")
    claimed = dq.get("claimed", False)
    all_done = are_all_quests_completed(user_items, now=now)

    lines = [
        f"📋 <b>ЕЖЕДНЕВНЫЙ НАРЯД НА СМЕНУ [{date_str}]</b>",
        f"<code>{'—'*28}</code>",
        "Выполняй ежедневные задачи Двачера и забирай премию от Абу:\n"
    ]

    for idx, q in enumerate(dq.get("quests", []), 1):
        p = q.get("progress", 0)
        t = q.get("target", 1)
        status_icon = "✅" if p >= t else f"⏳ <b>[{p}/{t}]</b>"
        lines.append(f"{idx}. {q['title']}\n   Статус: {status_icon}")

    lines.append(f"<code>{'—'*28}</code>")
    if claimed:
        lines.append("🎁 <b>Статус:</b> Премия за сегодня уже получена! Жди 00:00 МСК.")
        can_claim = False
    elif all_done:
        lines.append("🎉 <b>Все наряды закрыты!</b> Нажми кнопку ниже, чтобы забрать награду!")
        can_claim = True
    else:
        lines.append("💡 <i>Закрой все пункты, чтобы забрать +7,500 ₪ и лутбокс.</i>")
        can_claim = False

    return "\n".join(lines), can_claim
