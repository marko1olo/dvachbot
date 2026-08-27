# -*- coding: utf-8 -*-
"""
work_alerts.py — Automatic notification engine when /work cooldowns expire.
Sends high-resolution banners with authentic 2ch black-humor alerts and quick-action buttons.
"""

import time
import random
import asyncio
import logging
from typing import Dict
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

# Tracks the latest scheduled notification timestamp per user: {user_id: target_finish_ts}
_scheduled_work_alerts: Dict[int, float] = {}

WORK_ALERT_PHRASES = [
    (
        "🔔 <b>ПОДЪЁМ, СЫЧ! ХВАТИТ ДРОЧИТЬ В ПОТОЛОК!</b>\n\n"
        "Твои руки снова готовы к физическому и моральному унижению. "
        "Все кулдауны на заводе вышли, лопата и стеклотара ждут своего героя.\n\n"
        "<i>Иди фарми шекели, пока тебя не раскулачили бомжи:</i>"
    ),
    (
        "⏰ <b>ПЕРЕРЫВ ОКОНЧЕН, СКОТИНА! ТРУБА ЗОВЁТ!</b>\n\n"
        "Ты пролежал на диване достаточно, чтобы проветрить пролежни. "
        "Смены на заводе и в эскорте снова доступны.\n\n"
        "<i>Хватай мешок и пиздуй батрачить на благо Абу:</i>"
    ),
    (
        "📢 <b>АБУ ТРЕБУЕТ ТВОЕГО РАБСКОГО ТРУДА!</b>\n\n"
        "Кулдауны смен откатились. Яхта Абу сама себя не заправит, "
        "а шекели в карман сами не прыгнут.\n\n"
        "<i>Жми кнопку и пиздуй на смену:</i>"
    ),
    (
        "🚨 <b>ВНИМАНИЕ! ОБНАРУЖЕН ПРИСТУП ЛЕНИ!</b>\n\n"
        "Срок твоего перекура истёк. Бутылки в канаве снова накопились, "
        "на заводе не хватает мяса у станка.\n\n"
        "<i>Вставай с колен и зарабатывай на доширак:</i>"
    ),
    (
        "🦴 <b>КУЛДАУНЫ СБРОШЕНЫ, ДАРМОЕД!</b>\n\n"
        "Хватит скроллить борду бесплатно. Время менять своё здоровье "
        "на виртуальные шекели.\n\n"
        "<i>Быстро на завод, смена началась:</i>"
    ),
    (
        "⚡️ <b>СМЕНА ГОТОВА! ХВАТИТ КОРМИТЬ ВШЕЙ!</b>\n\n"
        "Таймеры обнулились. Тебя ждут на всех вакансиях — от сортировки стеклотары "
        "до теневого скама мамонтов.\n\n"
        "<i>Забирай шекели, пока конкуренты спят:</i>"
    ),
]


async def _work_cooldown_alert_task(bot: Bot, user_id: int, board_id: str, finish_ts: float):
    """Background worker that waits for cooldown expiry and sends the notification."""
    now = time.time()
    wait_time = max(0.5, finish_ts - now + 1.0)
    await asyncio.sleep(wait_time)

    # If user took another shift with later cooldown, skip this outdated trigger
    latest_target = _scheduled_work_alerts.get(user_id, 0)
    if latest_target > finish_ts + 1.0:
        return

    # Check database to ensure no active future cooldowns remain
    try:
        from common.db_pool import get_pool
        from common.bot_helpers import _get_user_active_items
        db = await get_pool()
        items = await _get_user_active_items(db, user_id, board_id)
        current_time = int(time.time())
        work_timers = items.get("work_cooldowns", {})

        # If any cooldown is still running in the future, don't alert yet
        if any(cd > current_time for cd in work_timers.values()):
            return

        from banner_manager import send_banner_message

        text = random.choice(WORK_ALERT_PHRASES)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔨 Пиздовать на работу (/work)", callback_data="work_hub")],
            [
                InlineKeyboardButton(text="🏪 Торговый Хаб (/shop)", callback_data="shop_main_hub"),
                InlineKeyboardButton(text="🏦 Банк Абу (/bank)", callback_data="bank_main_hub")
            ]
        ])

        categories = ["schizo", "shop", "night"]
        cat = random.choice(categories)

        await send_banner_message(
            bot=bot,
            chat_id=user_id,
            caption=text,
            reply_markup=kb,
            category=cat,
            parse_mode="HTML"
        )
        logger.info(f"🔔 [WorkAlert] Sent cooldown expiration alert to user {user_id}")
    except Exception as e:
        logger.warning(f"⚠️ [WorkAlert] Failed to send alert to user {user_id}: {e}")
    finally:
        _scheduled_work_alerts.pop(user_id, None)


def schedule_work_cooldown_alert(bot: Bot, user_id: int, board_id: str, cd_sec: int):
    """Schedules a cooldown alert for a user after cd_sec seconds."""
    from shared_state import spawn_task
    finish_ts = time.time() + cd_sec
    _scheduled_work_alerts[user_id] = finish_ts
    spawn_task(_work_cooldown_alert_task(bot, user_id, board_id, finish_ts))
