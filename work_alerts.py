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
    (
        "🏭 <b>ГУДОК ЗАВОДА ОРЁТ НА ВСЮ УЛИЦУ!</b>\n\n"
        "Хватит пускать слюни на подушку, тунеядец! Станок простаивает, "
        "а план пятилетки горит синим пламенем.\n\n"
        "<i>Бегом за станок, шекели ждут:</i>"
    ),
    (
        "🍾 <b>СТЕКЛОТАРА САМА СЕБЯ НЕ СДАСТ!</b>\n\n"
        "Местные бомжи уже вышли на охоту, а ты всё ещё валяешься. "
        "Кулдауны сброшены, пора лутать помойки.\n\n"
        "<i>Хватай авоську и вперёд:</i>"
    ),
    (
        "💀 <b>ТВОЙ ДОШИРАК САМ СЕБЯ НЕ КУПИТ!</b>\n\n"
        "Таймаут отдыха подошёл к концу. Без работы ты сдохнешь от голода "
        "в своей сычевальне. Абу ждёт твоих страданий.\n\n"
        "<i>Иди отрабатывай долги:</i>"
    ),
    (
        "💼 <b>КАРЬЕРНЫЙ РОСТ В КАНАВЕ ЖДЁТ ТЕБЯ!</b>\n\n"
        "Все смены разблокированы. Пора показать этой борде, "
        "кто здесь главный ударник капиталистического рабства.\n\n"
        "<i>Пиздуй на смену без лишних слов:</i>"
    ),
    (
        "🔥 <b>ХВАТИТ ТЕРЯТЬ ВЫРУЧКУ, НИЩУК!</b>\n\n"
        "Пока ты спал, другие опущенцы уже нафармили на три яхты. "
        "Кулдаун истёк — бегом на завод!\n\n"
        "<i>Работать, негры, солнце ещё высоко:</i>"
    ),
    (
        "🪓 <b>ВРЕМЯ ПАХАТЬ ДО СЕДЬМОГО ПОТА!</b>\n\n"
        "Твои мозоли зажили? Отлично, пора натереть новые. "
        "Все таймеры работы сброшены.\n\n"
        "<i>Жми кнопку и начинай смену:</i>"
    ),
    (
        "🐀 <b>КРЫСИНЫЕ БЕГА ПРОДОЛЖАЮТСЯ!</b>\n\n"
        "Перерыв окончен. Колесо сансары и заводской конвейер снова открыты "
        "для твоего жалкого существования.\n\n"
        "<i>Беги, сыч, беги за шекелями:</i>"
    ),
    (
        "🚜 <b>ТРАКТОР ЗАВЕДЁН, ПОРА В ПОЛЕ!</b>\n\n"
        "Хватит деградировать в /b/. Пора зарабатывать на пропитание "
        "честным (или не очень) трудом.\n\n"
        "<i>Выбирай работу и батрачь:</i>"
    ),
    (
        "🪣 <b>ВЕДРО И ШВАБРА УЖЕ СКУЧАЮТ!</b>\n\n"
        "Санитары дурки выписали тебе трудотерапию. Кулдауны сброшены, "
        "грязь на борде ждёт твоей тряпки.\n\n"
        "<i>Марш на уборку параши:</i>"
    ),
    (
        "💵 <b>ШЕКЕЛЕВЫЙ СТАНОК ЖДЁТ ТВОИ РУКИ!</b>\n\n"
        "Время простоя вышло. Каждый час без работы делает тебя беднее бомжа у вокзала.\n\n"
        "<i>Быстро вкалывать:</i>"
    ),
    (
        "📦 <b>КУРЬЕРСКАЯ СУМКА ЗОВЁТ!</b>\n\n"
        "Таймеры работы обнулились. Тебя ждут заказы, тяжёлые мешки "
        "и копеечная оплата от Абу.\n\n"
        "<i>Хватай заказ и беги:</i>"
    ),
    (
        "🦺 <b>НАДЕВАЙ ЖИЛЕТ И КАСКУ!</b>\n\n"
        "Стройка века простаивает без твоего горба. Кулдаун смен истёк, "
        "кирпичи сами себя не положат.\n\n"
        "<i>Вперёд на баррикады труда:</i>"
    ),
    (
        "⛏ <b>КИРКА В РУКИ И В ШАХТУ!</b>\n\n"
        "Ты отдохнул достаточно. Пора добывать шекели из недр виртуального Двача.\n\n"
        "<i>Марш в забой:</i>"
    ),
    (
        "🍞 <b>ЗАРАБОТАЙ НА КОРКУ ХЛЕБА!</b>\n\n"
        "Кулдауны работы откатились. Хватит клянчить дропы, "
        "иди зарабатывай своими мозолистыми руками.\n\n"
        "<i>За работу, тунеядец:</i>"
    ),
    (
        "🧹 <b>ДВОРНИК, НА ВЫХОД!</b>\n\n"
        "Листья и окурки у подъезда заждались твоего метла. "
        "Смена доступна прямо сейчас.\n\n"
        "<i>Бери метлу и мети:</i>"
    ),
    (
        "🪙 <b>АБУ ПРОВЕРИЛ ТВОЙ БАЛАНС И ЗАПЛАКАЛ!</b>\n\n"
        "С такой нищетой тебе прямая дорога на сверхурочные. "
        "Все таймеры работы обнулены.\n\n"
        "<i>Пиздуй пахать на благо капитала:</i>"
    ),
    (
        "🍺 <b>НА ПИВО НАДО ЕЩЁ НАФАРМИТЬ!</b>\n\n"
        "Таймаут истёк. «Балтика 9» сама себя в ларьке не купит. "
        "Пора идти отрабатывать вечерний запой.\n\n"
        "<i>На старт, внимание, смена:</i>"
    ),
    (
        "🏗 <b>БЕТОНОМЕШАЛКА КРУТИТСЯ!</b>\n\n"
        "Кулдаун на заводе снят. Пора замешивать шекели из пота и слёз.\n\n"
        "<i>Жми и начинай вкалывать:</i>"
    ),
    (
        "🛑 <b>ХВАТИТ ДУМАТЬ — ПОРА РАБОТАТЬ!</b>\n\n"
        "Мыслительные процессы вредны для сыча. Все смены открыты, "
        "ручной труд очистит твой разум.\n\n"
        "<i>Бегом на трудовую смену:</i>"
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
