# -*- coding: utf-8 -*-
"""
event_push_engine.py — Система пуш-уведомлений об игровых событиях ТГАЧ.

Рассылает ЛС-уведомления активным пользователям доски при старте:
  - открытой дуэли (/duel)
  - открытой русской рулетки (/rr)
  - рейда на олигарха (/raid_oligarch)
  - события черного рынка (market_event_generator)

Каждый пуш содержит:
  - Форматированное сообщение HTML о событии
  - InlineKeyboardButton с deeplink → переход в чат бота

Анти-спам:
  - Кулдаун 5 минут per-user per-event-type (in-memory)
  - Не более 300 уведомлений за одно событие (защита от DM-флуда)
  - Задержка 50ms между отправками (Telegram rate limit)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("runtime")

# ──────────────────────────────────────────────────────────────────────────────
# Кулдауны: {(user_id, event_type): timestamp_last_push}
# Живут в памяти процесса — достаточно для защиты от спама в рамках сессии.
# ──────────────────────────────────────────────────────────────────────────────
_user_event_cooldowns: dict[tuple[int, str], float] = {}
_COOLDOWN_SEC = 300        # 5 минут между пушами одного типа на одного юзера
_MAX_RECIPIENTS = 300      # макс. ЛС за одно событие
_SEND_DELAY_SEC = 0.05     # 50 ms между отправками


def _can_push(user_id: int, event_type: str) -> bool:
    """Проверяет, прошёл ли кулдаун для данного юзера и типа ивента."""
    key = (user_id, event_type)
    now = time.monotonic()
    last = _user_event_cooldowns.get(key, 0.0)
    if now - last >= _COOLDOWN_SEC:
        _user_event_cooldowns[key] = now
        return True
    return False


def _build_deeplink(bot_username: str, event_type: str) -> str:
    """Строит deeplink для кнопки перехода в бот."""
    clean = bot_username.lstrip("@")
    return f"https://t.me/{clean}"


def _build_push_message(event_type: str, headline: str, body_lines: list[str]) -> str:
    """Собирает HTML-текст пуш-уведомления."""
    lines = [f"<b>{headline}</b>", ""]
    lines.extend(body_lines)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Главная точка входа
# ──────────────────────────────────────────────────────────────────────────────

async def push_event_to_board(
    bot: Any,
    board_id: str,
    event_type: str,
    headline: str,
    body_lines: list[str],
    exclude_uid: Optional[int] = None,
    user_ids: Optional[list[int]] = None,
) -> int:
    """
    Рассылает пуш-уведомление активным юзерам доски в ЛС.

    Args:
        bot:         Telegram Bot-инстанс (aiogram Bot).
        board_id:    ID доски ('b', 'a', 'sex', ...).
        event_type:  Тип ивента — 'duel_open', 'rr_open', 'raid_oligarch', 'market_event'.
        headline:    Заголовок пуша (будет обёрнут в <b>).
        body_lines:  Строки тела сообщения (HTML-разметка допустима).
        exclude_uid: user_id который инициировал ивент (не шлём ему пуш).
        user_ids:    Явный список user_id для рассылки (иначе берём из board_data).

    Returns:
        Количество успешно отправленных уведомлений.
    """
    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from common.board_config import BOARD_CONFIG

    # Получаем username бота для этой доски
    board_cfg = BOARD_CONFIG.get(board_id, {})
    bot_username = board_cfg.get("username", "@dvach_chatbot")
    deeplink_url = _build_deeplink(bot_username, event_type)

    # Формируем кнопку перехода в бот
    button_labels = {
        "duel_open":     "⚔️ Принять дуэль!",
        "rr_open":       "🔫 Сыграть в рулетку!",
        "raid_oligarch": "🚩 Участвовать в рейде!",
        "market_event":  "🛒 В чёрный рынок (/shop)",
        "wealth_tax":    "🏛 Посмотреть итоги",
    }
    btn_text = button_labels.get(event_type, "🎮 Перейти в бот")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, url=deeplink_url)]
    ])

    push_text = _build_push_message(event_type, headline, body_lines)

    # Получаем список получателей
    if user_ids is None:
        try:
            from shared_state import board_data
            b_data = board_data.get(board_id, {})
            active = set(b_data.get("users", {}).get("active", set()))
            banned = set(b_data.get("users", {}).get("banned", set()))
            candidates = list(active - banned)
        except Exception as e:
            logger.warning(f"[event_push] Не удалось получить юзеров доски {board_id}: {e}")
            candidates = []
    else:
        candidates = list(user_ids)

    if exclude_uid:
        candidates = [uid for uid in candidates if uid != exclude_uid]

    # Фильтруем по кулдауну
    eligible = [uid for uid in candidates if _can_push(uid, event_type)]

    # Ограничиваем количество получателей
    eligible = eligible[:_MAX_RECIPIENTS]

    if not eligible:
        return 0

    sent_count = 0
    for uid in eligible:
        try:
            await bot.send_message(
                chat_id=uid,
                text=push_text,
                parse_mode="HTML",
                reply_markup=kb,
            )
            sent_count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            # Юзер заблокировал бота или чат не найден — нормально
            pass
        except Exception as e:
            logger.debug(f"[event_push] Не удалось отправить пуш user {uid}: {e}")
        await asyncio.sleep(_SEND_DELAY_SEC)

    logger.info(
        f"[event_push] Ивент '{event_type}' на доске '{board_id}': "
        f"отправлено {sent_count}/{len(eligible)} уведомлений."
    )
    return sent_count


# ──────────────────────────────────────────────────────────────────────────────
# Готовые хелперы для каждого типа ивента
# ──────────────────────────────────────────────────────────────────────────────

async def push_duel_open(
    bot: Any,
    board_id: str,
    challenger_anon_id: str,
    amount: int,
    exclude_uid: Optional[int] = None,
) -> int:
    """Пуш при открытом вызове на классическую дуэль."""
    return await push_event_to_board(
        bot=bot,
        board_id=board_id,
        event_type="duel_open",
        headline="⚔️ ОТКРЫТЫЙ ВЫЗОВ НА ДУЭЛЬ!",
        body_lines=[
            f"👤 Аноним <b>[{challenger_anon_id}]</b> бросил открытый вызов!",
            f"💰 Ставка: <code>{amount:,} ₪</code>",
            "",
            "<i>Кто первый нажмёт — тот и соперник. Победитель забирает куш.</i>",
            "<i>Вызов активен 2 минуты.</i>",
        ],
        exclude_uid=exclude_uid,
    )


async def push_rr_open(
    bot: Any,
    board_id: str,
    challenger_anon_id: str,
    bet: int,
    exclude_uid: Optional[int] = None,
) -> int:
    """Пуш при открытом вызове на русскую рулетку."""
    return await push_event_to_board(
        bot=bot,
        board_id=board_id,
        event_type="rr_open",
        headline="🔫 РУССКАЯ РУЛЕТКА — ОТКРЫТЫЙ СТОЛ!",
        body_lines=[
            f"🎰 Аноним <b>[{challenger_anon_id}]</b> зарядил барабан!",
            f"💀 Ставка: <code>{bet:,} ₪</code>",
            "",
            "<i>6 камер, 1 пуля, 2 игрока. Кто рискнёт?</i>",
            "<i>Стол открыт 3 минуты.</i>",
        ],
        exclude_uid=exclude_uid,
    )


async def push_raid_oligarch(
    bot: Any,
    board_id: str,
    oligarch_anon_id: str,
    oligarch_balance: int,
    potential_loot: int,
    exclude_uid: Optional[int] = None,
) -> int:
    """Пуш при запуске рейда на олигарха."""
    return await push_event_to_board(
        bot=bot,
        board_id=board_id,
        event_type="raid_oligarch",
        headline="🚩 РЕЙД ПРОЛЕТАРИАТА! РАСКУЛАЧИВАЕМ ОЛИГАРХА!",
        body_lines=[
            f"🐳 Цель: Олигарх <b>[{oligarch_anon_id}]</b>",
            f"💎 Состояние жертвы: <code>{oligarch_balance:,} ₪</code>",
            f"🪙 Дележ рабочим: <code>~{potential_loot:,} ₪</code> на 5 человек",
            "",
            "🛠 Нужно <b>5 пролетариев</b> (баланс &lt; 5,000 ₪, постов ≥ 25).",
            "<i>Напиши /raid_oligarch чтобы участвовать!</i>",
        ],
        exclude_uid=exclude_uid,
    )


async def push_market_event(
    bot: Any,
    board_id: str,
    event_text: str,
) -> int:
    """Пуш при смене конъюнктуры чёрного рынка (00:00 MSK)."""
    # Обрезаем HTML-теги из event_text для краткого превью
    import re
    clean_preview = re.sub(r"<[^>]+>", "", event_text)[:120]

    return await push_event_to_board(
        bot=bot,
        board_id=board_id,
        event_type="market_event",
        headline="📉 СВОДКА ЧЁРНОГО РЫНКА ОБНОВЛЕНА",
        body_lines=[
            f"<i>{clean_preview}...</i>",
            "",
            "Цены на снаряжение в <b>/shop</b> изменились!",
        ],
    )
