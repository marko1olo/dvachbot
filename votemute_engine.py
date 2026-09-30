# -*- coding: utf-8 -*-
"""
votemute_engine.py — Democratic Vote-Mute Engine (Народный Вотум / Шизо-Мут) for ТГАЧ
===================================================================================
Allows community to vote-mute toxic spammers/waifu-wipers via 5 unique votes within 10 minutes.
Once passed, applies an UNBRIBABLE 30-minute iron mute that CANNOT be removed via shop bribes or regular un-mutes.

Key Features:
1. Command /votemute (or /вотум, /шизомут) as a reply to a post or by post number.
2. Interactive voting card with inline button '⚖️ Замутить шиза [1/5]' (5 unique anons within 10 minutes).
3. Upon reaching 5 votes — applies 30-minute IRON FOLK MUTE (ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ).
4. UNBRIBABLE FLAG (unbribable_votemute_until) — blocks bribes in /shop and admin unmutes.
5. Juicy public verdict broadcast to the whole board via process_new_post.
6. Full aiogram 3.x Router and menu integration helpers.
"""

import time
import asyncio
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any, Set, Union

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from common.db_pool import get_pool, db_lock, db_transaction
from common.anon_identity import get_anon_id

logger = logging.getLogger("runtime")

VOTES_REQUIRED = 5
VOTE_WINDOW_SEC = 600.0  # 10 minutes voting window
MUTE_DURATION_SEC = 1800  # 30 minutes iron mute
UNBRIBABLE_FLAG_KEY = "unbribable_votemute_until"

UNBRIBABLE_MUTE_ERROR_TEXT = (
    "❌ <b>Этот мут наложен народом борды и не продается за взятки!</b>\n"
    "🔒 Воля анонов несокрушима. До окончания срока осталось <b>{minutes} мин.</b>"
)

active_votemutes: Dict[str, Dict[str, Any]] = {}
votemute_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# Phrase Pools — публичные приговоры, карточки, отказы
# -----------------------------------------------------------------------------
VOTEMUTE_ANNOUNCEMENTS = [
    "⚖️ <b>НАРОДНЫЙ ПРИГОВОР ВЫНЕСЕН И ПРИВЕДЕН В ИСПОЛНЕНИЕ!</b>\n\n👨‍⚖️ По итогам Народного Вотума (5 голосов анонов) за пост <b>#{post_num}</b>:\n🤐 <b>Анон <code>[ID:{target_anon}]</code></b> признан злостным шизо-вайпером и отправлен в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>!\n\n🔒 <i>Мут наложен волей народа борды: его НЕ СНЯТЬ взятками в /shop!</i>",
    "🔨 <b>МОЛОТ НАРОДНОГО ПРАВОСУДИЯ ОПУСТИЛСЯ!</b>\n\n📜 Пять анонов борды единогласно приговорили <b>Анона <code>[ID:{target_anon}]</code></b> (пост <b>#{post_num}</b>) к <b>ЖЕЛЕЗНОМУ МОЛЧАНИЮ на 30 минут</b>!\n\n🔒 <i>Взятки не принимаются. Адвокаты не нужны. Касса закрыта.</i>",
    "🚨 <b>СИРЕНЫ БОРДЫ ВОЮТ — ШИЗ ИЗОЛИРОВАН!</b>\n\n🫵 Анон <code>[ID:{target_anon}]</code> за пост <b>#{post_num}</b> набрал 5 голосов недоверия!\n🔒 <b>ПАРАША НА ЗАМКЕ. МУТ 30 МИНУТ. БЕСПОВОРОТНО.</b>\n\n<i>Бор-да сказала своё слово. Шиз — молчи.</i>",
    "🏛️ <b>НАРОДНЫЙ СУД БОРДЫ ЗАСЕДАНИЕ ЗАВЕРШЕНО!</b>\n\n⚖️ Подсудимый Анон <code>[ID:{target_anon}]</code> признан ВИНОВНЫМ по статье «Злостный вайп треда» (пост #{post_num}).\n📋 <b>Приговор: 30 минут образцово-показательного молчания.</b>\n🔒 Приговор обжалованию не подлежит. Взятки не работают.",
    "🧟 <b>САНИТАРЫ ЗАФИКСИРОВАЛИ ПАЦИЕНТА!</b>\n\n🚑 Анон <code>[ID:{target_anon}]</code> из поста <b>#{post_num}</b> признан общественно опасным. Пять санитаров провели фиксацию.\n😷 <b>Смирительная рубаха надета. Рот заклеен скотчем. 30 минут тишины.</b>\n<i>Галоперидол уже в системе.</i>",
    "🪣 <b>БОЧКА С ГОВНОМ ЗАКРЫТА НА ЗАМОК!</b>\n\n💩 Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) был признан главным источником вони в треде.\n🔒 <b>КРЫШКА ОПЕЧАТАНА. МУТ 30 МИНУТ.</b>\nПять носов борды не выдержали — вотум состоялся!",
    "⚡ <b>ВАТНЫЙ/ШИЗОИДНЫЙ ПАРАЛИЧ АКТИВИРОВАН!</b>\n\n🔇 Анон <code>[ID:{target_anon}]</code> за пост <b>#{post_num}</b> подвергся коллективному электрошоку от 5 анонов борды.\n💀 <b>Речевые центры отключены на 30 минут. Клавиатура заблокирована народом.</b>",
    "🐒 <b>АБУ ЛИЧНО ОДОБРИЛ ПРИГОВОР НАРОДА!</b>\n\n📜 Пять голосов анонов за пост <b>#{post_num}</b> и Анон <code>[ID:{target_anon}]</code> идёт в ЖЕЛЕЗНЫЙ МУТ!\n💰 <b>Взятки Абу в данном случае не котируются. Народная воля превыше.</b>\n🔒 30 минут тишины. Вотум исполнен.",
    "🔗 <b>СЫЧА СПЕЛЕНАЛИ В СМИРИТЕЛЬНУЮ РУБАХУ!</b>\n\nПять усталых анонов объединились против Анона <code>[ID:{target_anon}]</code> из поста <b>#{post_num}</b>.\n🏥 <b>Диагноз: хронический вайпер. Лечение: 30 минут ЖЕЛЕЗНОГО МОЛЧАНИЯ.</b>\n<i>Рецепт выписан. Галоперидол введён внутривенно.</i>",
    "🗡️ <b>ЛИНЧ СОСТОЯЛСЯ. ПРИГОВОР ИСПОЛНЕН.</b>\n\n🔥 Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) был публично осуждён пятью гражданами борды за злостный шизо-вайп!\n⚔️ <b>Казнь: 30 минут железного молчания без права на помилование.</b>\n<i>Труп убирать некому. Пусть лежит тихо.</i>",
    "📯 <b>ГЛАШАТАЙ БОРДЫ ОБЪЯВЛЯЕТ ПРИГОВОР!</b>\n\nОйе! Анон <code>[ID:{target_anon}]</code> за пост <b>#{post_num}</b> осуждён народным вотумом (5/5 голосов)!\n🔒 <b>ЖЕЛЕЗНЫЙ МУТ НА 30 МИНУТ. ВЗЯТКИ НЕ ПРИНИМАЕМ. АПЕЛЛЯЦИЙ НЕТ.</b>",
    "🧊 <b>КРИОКАМЕРА ЗАПЕЧАТАНА!</b>\n\n❄️ Анон <code>[ID:{target_anon}]</code> из поста <b>#{post_num}</b> заморожен волей народа борды на 30 минут.\n🔒 <b>Размораживание только после истечения срока. Взятки — в мусор.</b>\n<i>Нечего было вайпать тред, ублюдок.</i>",
    "🎪 <b>ЦИРК ЗАКРЫВАЕТСЯ — КЛОУН ИЗОЛИРОВАН!</b>\n\n🤡 Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) устроил несанкционированное шоу в треде. 5 анонов поддержали вотум.\n🎭 <b>Антракт 30 минут. Клоун в клетке. Взятки не работают.</b>",
    "💀 <b>РОТ ЗАТКНУТ НАРОДОМ БОРДЫ!</b>\n\n🗳️ Пять анонов выразили волю коллектива: Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) — злостный вайпер.\n🔒 <b>30 минут абсолютной тишины. ЖЕЛЕЗНЫЙ МУТ. Непродаваем.</b>",
    "🏴‍☠️ <b>ПИРАТСКИЙ ТРИБУНАЛ БОРДЫ ЗАСЕДАНИЕ ЗАВЕРШЕНО!</b>\n\n⚓ Анон <code>[ID:{target_anon}]</code> за пост <b>#{post_num}</b> приговорён к хождению по доске!\n🌊 <b>30 минут в пучине молчания. Вотум исполнен. Выкуп не принимается.</b>",
    "🦠 <b>КАРАНТИН ОБЪЯВЛЕН. ИСТОЧНИК ЗАРАЗЫ ИЗОЛИРОВАН!</b>\n\n😷 Пять санитарных инспекторов борды признали Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) биологически опасным для треда.\n🔬 <b>КАРАНТИН 30 МИНУТ. ВАКЦИНЫ ОТ ВОТУМА НЕТ.</b>",
    "🎯 <b>ОХОТА УДАЛАСЬ — ЦЕЛЬ ПОРАЖЕНА!</b>\n\n🔫 Пять охотников борды вычислили и нейтрализовали вайпера Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n🏆 <b>Трофей: 30 минут тишины в треде. МУТ НЕОБРАТИМ.</b>",
    "⚗️ <b>АЛХИМИКИ БОРДЫ ПРЕВРАТИЛИ ВАЙПЕРА В МОЛЧАНИЕ!</b>\n\n🧪 Народный реагент (5 голосов) вступил в реакцию с Аноном <code>[ID:{target_anon}]</code> из поста <b>#{post_num}</b>.\n💥 <b>Результат реакции: 30 минут ЖЕЛЕЗНОГО МОЛЧАНИЯ. Антидота нет.</b>",
    "🔔 <b>НАБАТ! ВАЙПЕР ОБЕЗВРЕЖЕН!</b>\n\n📣 Колокола борды возвестили: Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) осуждён пятью голосами народа!\n⛪ <b>Приговор: 30 минут тишины. Исповедь не принимается. Взятки — ересь.</b>",
    "🚔 <b>МАЙОР ДОИГРАЛЕС ОДОБРЯЕТ АРЕСТ!</b>\n\n👮 По итогам гражданского вотума Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) задержан силами самоорганизации борды.\n🔒 <b>Срок: 30 минут административного молчания. Взятки переданы в Казну Абу. Смотри не шали.</b>",
    "🌋 <b>ВУЛКАН НАРОДНОГО ГНЕВА НАКРЫЛ ВАЙПЕРА!</b>\n\n🔥 Пять анонов не выдержали — вотум прошёл! Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) погребён под лавой народного правосудия.\n💀 <b>30 минут в пепле молчания. Воскрешение за взятки недоступно.</b>",
    "🗺️ <b>ИНКВИЗИЦИЯ БОРДЫ ВЫНЕСЛА ВЕРДИКТ!</b>\n\nПо доносу пяти праведных анонов еретик Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) отправлен на аутодафе!\n🕯️ <b>30 минут публичного молчания. Индульгенции в /shop сгорели вместе с еретиком.</b>",
    "🧲 <b>НАРОДНЫЙ МАГНИТ ПРИТЯНУЛ ВАЙПЕРА К ЗЕМЛЕ!</b>\n\n⬇️ Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) накрыт общественной гравитацией (5 голосов).\n🔒 <b>ПРИДАВЛЕН. ЗАМОЛЧАН. 30 МИНУТ НЕОТВРАТИМО.</b>",
    "🪖 <b>ВОЕННО-ПОЛЕВОЙ СУД БОРДЫ ПОСТАНОВИЛ!</b>\n\nЗа дезертирство от нормального общения: расстрел речевых центров Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) по вотуму 5 анонов.\n🔇 <b>30 минут посмертного молчания. Помилования нет.</b>",
    "🌑 <b>ЧЁРНАЯ МЕТКА ПОЛУЧЕНА!</b>\n\n☠️ Пять пиратов борды передали чёрную метку Анону <code>[ID:{target_anon}]</code> (пост #{post_num}).\n⚓ <b>Приговор капитана народа: 30 минут в трюме молчания. Выкуп не принимается.</b>",
    "🤖 <b>СИСТЕМА САМООЧИЩЕНИЯ БОРДЫ АКТИВИРОВАНА!</b>\n\n⚙️ Алгоритм народного вотума (5/5 голосов) идентифицировал Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) как ТОКСИЧНЫЙ ЭЛЕМЕНТ.\n🔒 <b>НЕЙТРАЛИЗАЦИЯ: 30 МИНУТ ЖЕЛЕЗНОГО МОЛЧАНИЯ. ОБХОД НЕВОЗМОЖЕН.</b>",
    "🎻 <b>РЕКВИЕМ ПО СВОБОДЕ СЛОВА ВАЙПЕРА!</b>\n\n🎶 Пять анонов борды сыграли похоронный марш по болтовне Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n⚰️ <b>Упокоился в тишине на 30 минут. Воскрешение взятками запрещено религией Абу.</b>",
    "🦅 <b>ОРЁЛ НАРОДНОГО ПРАВОСУДИЯ ПОЙМАЛ МЫШЬ!</b>\n\n🦅 Пять зорких анонов засекли вайпера Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) и нажали вотум.\n🔒 <b>Добыча в когтях закона: 30 минут железного молчания. Выкуп у орла не работает.</b>",
    "🧠 <b>КОЛЛЕКТИВНЫЙ РАЗУМ БОРДЫ РЕШИЛ!</b>\n\n🤯 Пять нейронов народной сети единогласно: Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) — нейронный мусор.\n🔒 <b>ДЕФРАГМЕНТАЦИЯ ТРЕКА: 30 МИНУТ ТИШИНЫ. /shop НЕ ПОМОЖЕТ.</b>",
    "🏰 <b>ЗАМОК БОРДЫ ОПУСТИЛ РЕШЁТКУ НА ВАЙПЕРА!</b>\n\n⚔️ Пять рыцарей анонов провели успешный штурм болтовни Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n🔒 <b>В застенках: 30 минут. Золото на выкуп сгорело в топке вотума.</b>",
    "🩸 <b>КРОВАВЫЙ ЧЕТВЕРГ ДЛЯ ВАЙПЕРА — ВОТУМ ПРОШЁЛ!</b>\n\n💉 Пять анонов вонзили коллективный нож в болтовню Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n🔒 <b>30 минут кровоточащего молчания. Перевязка за взятки не предусмотрена.</b>",
    "🎩 <b>ФОКУСНИК ИСЧЕЗ — МУТ ПРИМЕНЁН!</b>\n\n🪄 Пять волшебников борды взмахнули палочками народного вотума и стёрли болтовню Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n✨ <b>30 минут магического молчания. Антизаклинание за шекели недоступно.</b>",
    "🐍 <b>ЗМЕЯ УКУШЕНА МАНГУСТАМИ БОРДЫ!</b>\n\n🦴 Пять мангустов (анонов) загнали Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) в нору молчания вотумом 5/5!\n🔒 <b>Нора запечатана на 30 минут. Выход за шекели заварен цементом.</b>",
    "🎬 <b>СТОП-КАДР! ВАЙПЕР ЗАМОРОЖЕН НАРОДОМ!</b>\n\n📽️ Режиссёры борды (5 анонов) остановили нежелательную сцену с участием Анона <code>[ID:{target_anon}]</code> (пост #{post_num}).\n✂️ <b>Вырезано в монтаже: 30 минут. Права на восстановление кадра выкупить нельзя.</b>",
    "🌪️ <b>ВИХРЬ НАРОДНОГО ГНЕВА УНЁС ВАЙПЕРА!</b>\n\n💨 Торнадо из 5 голосов смёл Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) в безмолвную пустыню!\n🏜️ <b>30 минут в тишине Сахары. Оазис взяток не существует.</b>",
    "🥊 <b>НОКАУТ ПЕРВОГО РАУНДА НАРОДНОГО БОКСЁРСТВА!</b>\n\n🏆 Пять боксёров-анонов отправили Анона <code>[ID:{target_anon}]</code> (пост #{post_num}) в нокаут вотумом!\n💫 <b>В отключке: 30 минут. Нашатырь за шекели недоступен.</b>",
    "🗳️ <b>СУД ЛИНЧА СОСТОЯЛСЯ — ПРИГОВОР ИСПОЛНЕН!</b>\n\n⚖️ Аноны решили, что Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) слишком громко хрюкал.\n🤐 <b>5 голосов собрано: нарушитель отправлен в мут на 30 минут без права откупа!</b>",
    "🗳️ <b>ГОЛОСОВАНИЕ ЗА ОБОССЫВАНИЕ ЗАВЕРШЕНО!</b>\n\n🍾 Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) заебал всех своим кринжом.\n🔒 <b>5 анонов проголосовали ЗА: 30 минут на бутылке молчания без взяток!</b>",
    "🗳️ <b>МУТ-РЕФЕРЕНДУМ УСПЕШНО ЗАКРЫТ!</b>\n\n📌 Анон <code>[ID:{target_anon}]</code> (пост #{post_num}) открыл помойку не в том районе.\n🤐 <b>5 подписей собрано — пасть зашита на 30 минут! /shop бессилен.</b>"
]

VOTEMUTE_CARD_DESCRIPTIONS = [
    (
        "🗳️ <b>НАРОДНЫЙ ВОТУМ НЕДОВЕРИЯ / ШИЗО-МУТ</b>\n\n"
        "🎯 <b>Выдвинут пост:</b> #{post_num}\n"
        "👤 <b>Автор поста:</b> <code>[ID:{anon_tag}]</code>\n"
        "📊 <b>Проголосовало:</b> <b>{votes_count}/{votes_req}</b> анонов\n"
        "⏳ <b>Осталось времени:</b> ~{time_left_min} мин.\n\n"
        "<i>Нажми кнопку ниже, если считаешь, что автор — злостный шиз/вайпер. "
        "При наборе 5 голосов на него наложится ЖЕЛЕЗНЫЙ МУТ на 30 минут, который нельзя снять за взятки!</i>"
    ),
    (
        "⚖️ <b>ШИЗО-ТРИБУНАЛ ОТКРЫТ</b>\n\n"
        "📝 <b>Дело №{post_num}:</b> предполагаемый вайпер треда\n"
        "🤐 <b>Обвиняемый:</b> <code>[ID:{anon_tag}]</code>\n"
        "🗳️ <b>Голосов собрано:</b> {votes_count} из {votes_req}\n"
        "⏱️ <b>До закрытия трибунала:</b> ~{time_left_min} мин.\n\n"
        "<i>Дай свой голос за мут. Пять анонов — и шиз идёт под железный замок на 30 минут без права взятки!</i>"
    ),
    (
        "🔨 <b>МОЛОТ НАРОДНОГО ПРАВОСУДИЯ</b>\n\n"
        "📌 <b>Пост №{post_num}</b> выдвинут на суд анонов\n"
        "👺 <b>Подсудимый:</b> <code>[ID:{anon_tag}]</code>\n"
        "✅ <b>Голосов:</b> <b>{votes_count}/{votes_req}</b>\n"
        "⏳ <b>Сессия открыта ещё:</b> ~{time_left_min} мин.\n\n"
        "<i>Ударь по кнопке — добавь свой голос. При 5/5 молот опускается: ЖЕЛЕЗНЫЙ МУТ без взяток!</i>"
    ),
    (
        "🧟 <b>САНИТАРНАЯ ИНСПЕКЦИЯ БОРДЫ</b>\n\n"
        "🔬 <b>Исследуемый объект:</b> Пост №{post_num}\n"
        "🦠 <b>Источник заразы:</b> <code>[ID:{anon_tag}]</code>\n"
        "📋 <b>Диагностика:</b> {votes_count}/{votes_req} санитаров подтверждают патоген\n"
        "⏱️ <b>Карантинный протокол активен:</b> ещё ~{time_left_min} мин.\n\n"
        "<i>Нажми кнопку — подтверди карантин! 5 голосов = 30 минут изоляции без права на взятку.</i>"
    ),
    (
        "💀 <b>НАРОДНЫЙ РАССТРЕЛЬНЫЙ СПИСОК</b>\n\n"
        "🗡️ <b>Цель:</b> Пост №{post_num} / Анон <code>[ID:{anon_tag}]</code>\n"
        "🔫 <b>Расстрельных команд:</b> {votes_count}/{votes_req}\n"
        "⌛ <b>Приговор можно исполнить ещё:</b> ~{time_left_min} мин.\n\n"
        "<i>Нажми курок — добавь голос. При 5/5 — 30-минутный ЖЕЛЕЗНЫЙ МУТ. /shop бессилен.</i>"
    ),
    (
        "🏴‍☠️ <b>ПИРАТСКИЙ СУД БОРДЫ</b>\n\n"
        "⚓ <b>Обвинение:</b> Злостный вайп поста №{post_num}\n"
        "🦜 <b>Подсудимый:</b> <code>[ID:{anon_tag}]</code>\n"
        "🗳️ <b>Пиратский кворум:</b> {votes_count}/{votes_req}\n"
        "⌛ <b>До закрытия суда:</b> ~{time_left_min} мин.\n\n"
        "<i>Дай свой голос. Пять пиратов = хождение по доске: ЖЕЛЕЗНЫЙ МУТ 30 минут. Выкуп не принимается!</i>"
    ),
    (
        "🚔 <b>ГРАЖДАНСКАЯ ОБЛАВА НА ВАЙПЕРА</b>\n\n"
        "📍 <b>Место преступления:</b> Пост №{post_num}\n"
        "🎯 <b>Разыскивается:</b> Анон <code>[ID:{anon_tag}]</code>\n"
        "👮 <b>Гражданских охотников:</b> {votes_count}/{votes_req}\n"
        "⏱️ <b>Облава продлится:</b> ещё ~{time_left_min} мин.\n\n"
        "<i>Нажми — помоги поймать шиза! 5 голосов = 30-минутный ЖЕЛЕЗНЫЙ МУТ без права взятки.</i>"
    ),
    (
        "🪣 <b>БОЧКА С ГОВНОМ ПЕРЕПОЛНЕНА</b>\n\n"
        "💩 <b>Главный загрязнитель:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "👃 <b>Жалоб от анонов:</b> {votes_count}/{votes_req}\n"
        "⏳ <b>Крышка открыта ещё:</b> ~{time_left_min} мин.\n\n"
        "<i>Зажми нос и нажми кнопку! 5 жалоб = бочка закрыта: ЖЕЛЕЗНЫЙ МУТ 30 минут. Выдохни.</i>"
    ),
    (
        "🎪 <b>КЛОУН ВЫСТУПАЕТ БЕЗ РАЗРЕШЕНИЯ</b>\n\n"
        "🤡 <b>Нарушитель порядка:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "🎭 <b>Зрителей, требующих удалить клоуна:</b> {votes_count}/{votes_req}\n"
        "⌛ <b>Шоу можно остановить:</b> ещё ~{time_left_min} мин.\n\n"
        "<i>Нажми кнопку — убери клоуна со сцены! 5 голосов = занавес: МУТ 30 минут. Взятки не работают.</i>"
    ),
    (
        "🌋 <b>НАРОДНЫЙ ВУЛКАН ГОТОВ К ИЗВЕРЖЕНИЮ</b>\n\n"
        "🔥 <b>Лавина направлена на:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "⚡ <b>Давление народного гнева:</b> {votes_count}/{votes_req}\n"
        "⏱️ <b>До взрыва (дедлайн):</b> ~{time_left_min} мин.\n\n"
        "<i>Добавь своей лавы! 5/5 = извержение: ЖЕЛЕЗНЫЙ МУТ 30 минут. /shop сгорит в пепле.</i>"
    ),
    (
        "⚗️ <b>НАРОДНЫЙ РЕАКТОР БОРДЫ</b>\n\n"
        "☢️ <b>Токсичный элемент:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "🔬 <b>Реакция запущена:</b> {votes_count}/{votes_req} анонов\n"
        "⌛ <b>Реакция активна:</b> ещё ~{time_left_min} мин.\n\n"
        "<i>Добавь свой нейтрон! 5 голосов = ядерный распад вайпера: МУТ 30 минут. Антидота нет.</i>"
    ),
    (
        "🏰 <b>ОСАДА ЗАМКА ШИЗО-ВАЙПЕРА</b>\n\n"
        "⚔️ <b>Обороняемая крепость пала в посте:</b> №{post_num}\n"
        "🛡️ <b>Осаждаемый:</b> <code>[ID:{anon_tag}]</code>\n"
        "⚔️ <b>Рыцарей борды под стенами:</b> {votes_count}/{votes_req}\n"
        "⌛ <b>Осада продлится:</b> ~{time_left_min} мин.\n\n"
        "<i>Бросай камень со стены! 5 рыцарей = замок взят: МУТ 30 минут. Золото не спасёт.</i>"
    ),
    (
        "🎯 <b>ОХОТНИЧИЙ СЕЗОН ОТКРЫТ</b>\n\n"
        "🦆 <b>Добыча:</b> Пост №{post_num} / Анон <code>[ID:{anon_tag}]</code>\n"
        "🔫 <b>Выстрелов засчитано:</b> {votes_count}/{votes_req}\n"
        "🌲 <b>Охота продолжается:</b> ~{time_left_min} мин.\n\n"
        "<i>Нажми — выстрели! 5 попаданий = трофей: ЖЕЛЕЗНЫЙ МУТ 30 минут. Откупиться нельзя.</i>"
    ),
    (
        "🧊 <b>ОПЕРАЦИЯ «ЗАМОРОЗКА ВАЙПЕРА»</b>\n\n"
        "❄️ <b>Объект заморозки:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "🌡️ <b>Температура опускается:</b> {votes_count}/{votes_req} анонов охлаждают тред\n"
        "⏱️ <b>Окно криокамеры открыто:</b> ~{time_left_min} мин.\n\n"
        "<i>Добавь льда! 5 голосов = криосон: МУТ 30 минут. Разморозка за шекели недоступна.</i>"
    ),
    (
        "🦠 <b>ВСПЫШКА ШИЗО-ЭПИДЕМИИ В ТРЕДЕ</b>\n\n"
        "⚠️ <b>Источник заражения:</b> Пост №{post_num} / <code>[ID:{anon_tag}]</code>\n"
        "💊 <b>Анонов-эпидемиологов:</b> {votes_count}/{votes_req}\n"
        "⏳ <b>Карантин можно ввести:</b> ещё ~{time_left_min} мин.\n\n"
        "<i>Подпиши санитарное предписание! 5 голосов = карантин 30 минут. Прививка от шизо-вотума не существует.</i>"
    ),
    (
        "🗳️ <b>СУД ЛИНЧА: СКИДЫВАЕМСЯ ГОЛОСАМИ</b>\n\n"
        "🎯 <b>Пост:</b> #{post_num}\n"
        "👤 <b>Нарушитель:</b> <code>[ID:{anon_tag}]</code>\n"
        "📊 <b>Голосов:</b> <b>{votes_count}/{votes_req}</b>\n"
        "⏳ <b>До конца голосования:</b> ~{time_left_min} мин.\n\n"
        "<i>Очередной говноед заебал тред. Нажми кнопку, чтобы отправить его в мут на 30 минут без права взятки!</i>"
    ),
    (
        "🗳️ <b>ГОЛОСОВАНИЕ ЗА ОБОССЫВАНИЕ ВАЙПЕРА</b>\n\n"
        "🎯 <b>Кринж-пост:</b> #{post_num}\n"
        "👤 <b>Пациент:</b> <code>[ID:{anon_tag}]</code>\n"
        "📊 <b>Собрано голосов:</b> <b>{votes_count}/{votes_req}</b>\n"
        "⏳ <b>Осталось времени:</b> ~{time_left_min} мин.\n\n"
        "<i>Этот персонаж порвался и несёт хуйню. Отправим его под шконку молчания? Голосуй кнопкой ниже!</i>"
    ),
    (
        "🗳️ <b>МУТ-РЕФЕРЕНДУМ: ДВАЧЕРСКОЕ ПРАВОСУДИЕ</b>\n\n"
        "🎯 <b>Обвинение по посту:</b> #{post_num}\n"
        "👤 <b>Фигурант:</b> <code>[ID:{anon_tag}]</code>\n"
        "📊 <b>Подписей анонов:</b> <b>{votes_count}/{votes_req}</b>\n"
        "⏳ <b>Сессия открыта:</b> ~{time_left_min} мин.\n\n"
        "<i>Открыл помойку не в том районе? Затыкаем вонючую пасть демократично — жми кнопку!</i>"
    )
]

VOTEMUTE_REJECT_TEXTS = [
    "🤡 Ты пытаешься объявить вотум сам на себя? Омежка-саморезка. Так не работает.",
    "😂 Сам на себя вотум? У тебя батя тоже сам себе пиздюлей давал? Пошёл нахуй.",
    "🤦 Сам на себя голосуешь? Это новый уровень аутизма. Вотум не создан.",
    "💀 Ты пытаешься замутить бота? Мразь, у меня нет голосовых связок, я не могу молчать сильнее.",
    "🔇 Замутить меня? Хуй тебе в рот. Я сервер, я работаю пока ты спишь.",
    "🤖 Попытка вотума на бота зафиксирована. Анон [ID:{anon_tag}] записан в чёрный список шизов.",
    "😴 Ты сейчас в муте, а значит голосовать за вотум — как стрелять из пушки в воду. Вотум не создан.",
    "🔒 Сам замучен — сам хочет мутить других? Хуй тебе, не твой ход сейчас.",
    "⚰️ Ты в муте, сиди тихо и думай о своём поведении. Вотум для свободных анонов.",
    "❌ Нельзя начинать вотум, находясь в муте. Отбудь срок, потом пи*ди.",
    "🚫 Попытка вотума на замученного? Он уже молчит, в чём смысл? Лудоман от вотума.",
    "💤 Тот, на кого ты тычешь, уже замучен. Дай ему отсидеть и не паясничай.",
    "⚠️ Цель уже в муте! Не добивай лежачего. Тред не одобряет.",
    "🤦 Уже замутили. Ещё раз вотумировать одного и того же за то же — двойное слабоумие.",
    "🙄 Вотум на замученного — это как добавлять соль в утопленника. Смысла ноль, вотум не создан.",
    "🛑 Нет реплая и нет номера поста — как ты вообще собрался мутить? Аргументов нет.",
    "🫠 Ты написал /votemute в воздух? Умник. Реплай на пост или номер поста, чудо природы.",
    "🐒 Команда принята. Цель: никто. Результат: ничего. Попробуй ещё раз, но с мозгом.",
    "❓ Вотум на кого? Реплай на пост вайпера или укажи номер поста. Телепатии нет.",
    "🤷 Не могу найти автора поста. Либо пост удалён, либо ты промахнулся. Вотум не создан.",
]

votemute_router = Router(name="votemute_router")


def generate_votemute_key(target_id: int, post_num: int) -> str:
    """Internal memory key for dedup — uses IDs, never exposed to Telegram."""
    return f"vm_{target_id}_{post_num}"


def get_votemute_callback_token(target_id: int, post_num: int) -> str:
    """
    Safe opaque token for InlineKeyboardButton callback_data.
    Uses existing anon_id hash (e.g. 'Шолтер5') — deterministic, no raw ID exposed,
    survives bot restarts since get_anon_id is keyed on a fixed secret salt.
    Format: '<anon_tag>_<post_num>'
    """
    return f"{get_anon_id(target_id)}_{post_num}"


def resolve_votemute_token(token: str) -> Optional[Tuple[int, int]]:
    """
    Resolves callback token '<anon_tag>_<post_num>' back to (target_id, post_num)
    by scanning active_votemutes for a matching entry.
    Returns None if not found or session expired.
    """
    # Token format: '<anon_tag>_<post_num>'  e.g. 'Шолтер5_12345'
    try:
        # Split from right once to get post_num
        last_sep = token.rfind("_")
        if last_sep == -1:
            return None
        anon_tag = token[:last_sep]
        post_num = int(token[last_sep + 1:])
    except (ValueError, IndexError):
        return None

    for vm in active_votemutes.values():
        t_id = vm.get("target_id")
        p_num = vm.get("post_num")
        if p_num == post_num and t_id and get_anon_id(t_id) == anon_tag:
            return t_id, post_num
    return None



def clean_expired_votemutes():
    """Removes unexecuted votemute sessions older than VOTE_WINDOW_SEC from memory."""
    now = time.time()
    expired_keys = [
        k for k, vm in active_votemutes.items()
        if (now - vm.get("created_ts", 0)) > VOTE_WINDOW_SEC and not vm.get("executed", False)
    ]
    for k in expired_keys:
        active_votemutes.pop(k, None)


def get_votemute_status(target_id: int, post_num: int) -> Optional[Dict[str, Any]]:
    """Returns current active votemute state dictionary if present."""
    vm_key = generate_votemute_key(target_id, post_num)
    return active_votemutes.get(vm_key)


def get_votemute_keyboard(target_id: int, post_num: int, votes_count: int, is_executed: bool = False) -> InlineKeyboardMarkup:
    """Builds inline keyboard for active or completed votemute. callback_data uses opaque token only."""
    token = get_votemute_callback_token(target_id, post_num)
    if is_executed or votes_count >= VOTES_REQUIRED:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔒 ЗАМУЧЕН НАРОДОМ (30 мин)",
                    callback_data=f"vm_info:{token}"
                )
            ]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⚖️ Замутить шиза [{votes_count}/{VOTES_REQUIRED}]",
                callback_data=f"vm_vote:{token}"
            )
        ]
    ])


def get_votemute_card_text(post_num: int, target_id: int, votes_count: int, created_ts: float, is_executed: bool = False) -> str:
    """Formats HTML text for the votemute message card."""
    now = time.time()
    time_left_sec = max(0, int(VOTE_WINDOW_SEC - (now - created_ts)))
    time_left_min = (time_left_sec + 59) // 60

    anon_tag = get_anon_id(target_id) if target_id else "???"
    if is_executed or votes_count >= VOTES_REQUIRED:
        return (
            f"⚖️ <b>НАРОДНЫЙ ВОТУМ ЗАВЕРШЕН!</b>\n\n"
            f"🎯 <b>Пост:</b> #{post_num}\n"
            f"🤐 <b>Нарушитель:</b> <code>[ID:{anon_tag}]</code>\n"
            f"📊 <b>Итог:</b> Собрано {VOTES_REQUIRED}/{VOTES_REQUIRED} голосов анонов!\n\n"
            f"🔒 <b>Приговор:</b> <b>ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ на 30 минут</b>.\n"
            f"<i>Этот мут не снимается взятками в /shop и защищен от помилований.</i>"
        )

    template = random.choice(VOTEMUTE_CARD_DESCRIPTIONS)
    return template.format(
        post_num=post_num,
        anon_tag=anon_tag,
        votes_count=votes_count,
        votes_req=VOTES_REQUIRED,
        time_left_min=time_left_min,
    )


async def broadcast_votemute_announcement(bot, board_id: str, text: str, reply_to_post: Optional[int] = None):
    """
    Broadcasts public announcement to the whole board via process_new_post.
    """
    try:
        from post_processor import process_new_post
        import shared_state
        params = shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content={'type': 'text', 'text': text, 'is_system_message': True},
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        logger.error(f"Error broadcasting votemute announcement: {e}", exc_info=True)


def is_user_under_unbribable_mute(active_items: Optional[Union[dict, str]]) -> bool:
    """
    Checks if target user active_items contains an unexpired unbribable_votemute_until timestamp.
    """
    if not active_items:
        return False
    if isinstance(active_items, str):
        try:
            active_items = json.loads(active_items)
        except Exception:
            return False
    if not isinstance(active_items, dict):
        return False
    now = int(time.time())
    unbribable_until = active_items.get(UNBRIBABLE_FLAG_KEY, 0)
    return int(unbribable_until) > now


async def check_user_unbribable_mute(user_id: int, board_id: str) -> Tuple[bool, int]:
    """
    Asynchronously checks if user is currently restricted by unbribable folk mute in DB.
    Returns: (is_muted: bool, remaining_seconds: int)
    """
    now = int(time.time())
    try:
        db = await get_pool()
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
            (user_id, board_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    items = json.loads(row[0])
                    until = int(items.get(UNBRIBABLE_FLAG_KEY, 0))
                    if until > now:
                        return True, until - now
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error checking unbribable mute in DB for user {user_id}: {e}")
    return False, 0


async def start_or_add_vote(
    board_id: str,
    target_id: int,
    post_num: int,
    voter_id: int,
    bot=None
) -> Tuple[bool, str, int, bool]:
    """
    Starts a new votemute session or casts a vote in an existing one.
    Returns: (ok: bool, message: str, current_votes: int, is_executed: bool)
    """
    if not post_num or post_num <= 0:
        return False, "❌ Некорректный номер поста.", 0, False

    if not target_id or target_id <= 0:
        return False, "❌ Нельзя объявить вотум системному аккаунту.", 0, False

    if voter_id == target_id:
        return False, "❌ Нельзя голосовать за мут самого себя, шизик.", 0, False

    vm_key = generate_votemute_key(target_id, post_num)
    now = time.time()

    async with votemute_lock:
        # Check if already under active unbribable iron mute
        is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
        if is_unbribable:
            rem_min = max(1, (remaining_sec + 59) // 60)
            return False, f"⚠️ Этот анон уже отбывает Народный Мут! Осталось: {rem_min} мин.", VOTES_REQUIRED, True

        vm = active_votemutes.get(vm_key)
        if not vm:
            vm = {
                "key": vm_key,
                "board_id": board_id,
                "target_id": target_id,
                "post_num": post_num,
                "created_ts": now,
                "voters": {voter_id},
                "executed": False
            }
            active_votemutes[vm_key] = vm
            current_votes = 1
        else:
            if vm["executed"]:
                return False, "⚖️ Приговор по этому посту уже вынесен и приведен в исполнение!", len(vm["voters"]), True

            if now - vm["created_ts"] > VOTE_WINDOW_SEC:
                # Expired -> reset
                active_votemutes.pop(vm_key, None)
                vm = {
                    "key": vm_key,
                    "board_id": board_id,
                    "target_id": target_id,
                    "post_num": post_num,
                    "created_ts": now,
                    "voters": {voter_id},
                    "executed": False
                }
                active_votemutes[vm_key] = vm
                current_votes = 1
            else:
                if voter_id in vm["voters"]:
                    return False, f"⚠️ Ты уже отдал свой голос! Текущий сбор: [{len(vm['voters'])}/{VOTES_REQUIRED}]", len(vm["voters"]), False

                vm["voters"].add(voter_id)
                current_votes = len(vm["voters"])

        if current_votes >= VOTES_REQUIRED and not vm["executed"]:
            vm["executed"] = True
            asyncio.create_task(_apply_unbribable_iron_mute(board_id, target_id, post_num, bot))
            return True, "⚖️ ГОЛОС ПРИНЯТ! ПОРОГ ДОСТИГНУТ: ШИЗ ОТПРАВЛЯЕТСЯ В ЖЕЛЕЗНЫЙ МУТ НА 30 МИНУТ!", current_votes, True

    return True, f"⚖️ Твой голос учтен! Собрано: [{current_votes}/{VOTES_REQUIRED}]", current_votes, False


async def _apply_unbribable_iron_mute(board_id: str, target_id: int, post_num: int, bot=None):
    """
    Applies the unbribable 30-minute iron folk mute in DB, in-memory state, and broadcasts verdict.
    """
    now = int(time.time())
    mute_until = now + MUTE_DURATION_SEC

    # 1. Update SQLite database
    db = await get_pool()
    try:
        async with db_transaction(db):
            # Update user's active_items with unbribable_votemute_until and cursed_until
            await db.execute(
                """
                UPDATE Users 
                SET cursed_until = ?, 
                    active_items = json_set(COALESCE(NULLIF(active_items, ''), '{}'), '$.unbribable_votemute_until', ?) 
                WHERE user_id = ? AND board_id = ?
                """,
                (mute_until, mute_until, target_id, board_id)
            )
            # Insert / update Mutes table
            await db.execute(
                "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                (target_id, board_id)
            )
            await db.execute(
                "INSERT INTO Mutes (user_id, board_id, mute_type, expires_at) VALUES (?, ?, 'mute', ?)",
                (target_id, board_id, float(mute_until))
            )
    except Exception as e:
        logger.error(f"Error persisting unbribable mute for user {target_id}: {e}", exc_info=True)

    # 2. Update in-memory state
    try:
        import shared_state
        b_data = shared_state.board_data.get(board_id)
        if b_data is not None:
            b_data.setdefault('mutes', {})[target_id] = datetime.now(timezone.utc) + timedelta(seconds=MUTE_DURATION_SEC)
    except Exception as e:
        logger.error(f"Error updating in-memory mutes for user {target_id}: {e}")

    # 3. Publish public verdict across the board
    target_anon = get_anon_id(target_id) if target_id else "???"
    announcement = random.choice(VOTEMUTE_ANNOUNCEMENTS).format(
        post_num=post_num, target_anon=target_anon
    )

    if bot:
        asyncio.create_task(broadcast_votemute_announcement(bot, board_id, announcement, reply_to_post=post_num))


# ============================================================================
# AIOGRAM ROUTER & HANDLERS
# ============================================================================

async def _resolve_target_from_message(message: types.Message) -> Tuple[Optional[int], Optional[int]]:
    """
    Resolves (target_post_num, target_author_id) from reply or arguments.
    """
    post_num = None
    target_id = None

    if message.reply_to_message:
        target_chat_id = message.reply_to_message.chat.id
        reply_mid = message.reply_to_message.message_id
        
        # 1. Try memory
        try:
            import shared_state
            async with shared_state.storage_lock:
                lookup_key = (target_chat_id, reply_mid)
                post_num = shared_state.message_to_post.get(lookup_key)
                if post_num and post_num in shared_state.messages_storage:
                    target_id = shared_state.messages_storage[post_num].get("author_id")
        except Exception:
            pass

        # 2. Try DB copy lookup
        if not post_num or not target_id:
            try:
                from common.database import get_post_info_by_copy
                info = await get_post_info_by_copy(target_chat_id, reply_mid)
                if info:
                    post_num, target_id = info
            except Exception:
                pass

        # 3. Try get post by num from DB if author missing
        if post_num and not target_id:
            try:
                from common.database import get_post_by_num
                db_p = await get_post_by_num(post_num)
                if db_p:
                    target_id = db_p.get("author_id")
            except Exception:
                pass

    # 4. Check explicit post_num argument: /votemute 12345
    if not post_num:
        parts = (message.text or message.caption or "").split()
        if len(parts) >= 2 and parts[1].isdigit():
            post_num = int(parts[1])
            try:
                from common.database import get_post_by_num
                db_p = await get_post_by_num(post_num)
                if db_p:
                    target_id = db_p.get("author_id")
            except Exception:
                pass

    return post_num, target_id


@votemute_router.message(Command("votemute", "вотум", "шизомут", "vm"))
async def cmd_votemute(message: types.Message, board_id: Optional[str] = None):
    """
    Handles /votemute command.
    """
    if not board_id:
        board_id = "b"

    voter_id = message.from_user.id
    post_num, target_id = await _resolve_target_from_message(message)

    if not post_num or not target_id:
        await message.answer(
            "⚠️ <b>Как использовать Народный Вотум (/votemute):</b>\n\n"
            "1. Ответь командой <code>/votemute</code> на пост нарушителя (реплаем).\n"
            "2. Или напиши <code>/votemute &lt;номер_поста&gt;</code>.\n\n"
            "⚖️ При сборе <b>5 голосов анонов за 10 минут</b> нарушитель отправляется в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b> "
            "(не продается за взятки в /shop!).",
            parse_mode="HTML"
        )
        return

    if voter_id == target_id:
        await message.answer("❌ Ты не можешь запустить вотум недоверия против самого себя, шизик.", parse_mode="HTML")
        return

    if target_id <= 0:
        await message.answer("❌ Нельзя объявить вотум системному сообщению.", parse_mode="HTML")
        return

    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    db = await get_pool()
    if await check_db_shadow_muted(voter_id, board_id, db=db) or await check_user_is_muted(db, voter_id, board_id):
        await message.answer("🔇 Замученным нельзя запускать народный вотум.", parse_mode="HTML")
        return

    # Check if already in unbribable mute
    is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
    if is_unbribable:
        rem_min = max(1, (remaining_sec + 59) // 60)
        await message.answer(
            f"🔒 <b>Анон <code>[ID:{get_anon_id(target_id)}]</code> уже отбывает Железный Народный Мут!</b>\n"
            f"Осталось сидеть: ~<b>{rem_min} мин.</b> Повторный вотум не требуется.",
            parse_mode="HTML"
        )
        return

    # Cast initial vote
    ok, msg, current_votes, is_executed = await start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=voter_id,
        bot=message.bot
    )

    card_text = get_votemute_card_text(
        post_num=post_num,
        target_id=target_id,
        votes_count=current_votes,
        created_ts=time.time(),
        is_executed=is_executed
    )
    keyboard = get_votemute_keyboard(target_id, post_num, current_votes, is_executed)

    sent = await message.answer(card_text, reply_markup=keyboard, parse_mode="HTML")
    vm_key = generate_votemute_key(target_id, post_num)
    if sent:
        async with votemute_lock:
            vm_rec = active_votemutes.get(vm_key)
            if vm_rec:
                vm_rec.setdefault("broadcast_msgs", []).append((sent.chat.id, sent.message_id))

    # Рассылаем интерактивную карточку народного вотума активным юзерам борда
    if ok and not is_executed:
        async def _do_votemute_broadcast():
            try:
                import shared_state
                from banner_manager import broadcast_banner_to_users
                b_data = shared_state.board_data.get(board_id, {})
                active_users = list(b_data.get('users', {}).get('active', []))

                # Исключаем инициатора (уже получил карточку) и цель
                exclude_ids = {voter_id, target_id}
                recipients = [uid for uid in active_users if uid not in exclude_ids]

                async def _on_sent(uid, mid):
                    async with votemute_lock:
                        vm_record = active_votemutes.get(vm_key)
                        if vm_record:
                            vm_record.setdefault("broadcast_msgs", []).append((uid, mid))

                await broadcast_banner_to_users(
                    bot=message.bot,
                    user_ids=recipients,
                    exclude_uid=voter_id,
                    caption=card_text,
                    reply_markup=keyboard,
                    category="schizo",
                    parse_mode="HTML",
                    on_sent=_on_sent,
                )
            except Exception as e:
                logger.warning(f"Error in _do_votemute_broadcast: {e}")

        asyncio.create_task(_do_votemute_broadcast())

        # Пуш-уведомление в ЛС активным пользователям через event_push_engine
        try:
            from event_push_engine import push_votemute_open
            target_tag = get_anon_id(target_id)
            asyncio.create_task(push_votemute_open(
                bot=message.bot,
                board_id=board_id,
                post_num=post_num,
                target_anon_id=target_tag,
                votes_count=current_votes,
                votes_req=VOTES_REQUIRED,
                exclude_uid=voter_id,
            ))
        except Exception as e:
            logger.debug(f"Error triggering push_votemute_open: {e}")


@votemute_router.callback_query(F.data.startswith("vm_vote:"))
async def callback_votemute_vote(callback: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Handles button click '⚖️ Замутить шиза [x/5]'.
    """
    if not board_id:
        board_id = "b"

    voter_id = callback.from_user.id
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    db = await get_pool()
    if await check_db_shadow_muted(voter_id, board_id, db=db) or await check_user_is_muted(db, voter_id, board_id):
        await callback.answer("🔇 Замученным нельзя голосовать в народном вотуме.", show_alert=True)
        return

    token = callback.data.split(":", 1)[1]

    # Resolve opaque token -> (target_id, post_num)
    ids = resolve_votemute_token(token)
    if not ids:
        await callback.answer("⏳ Срок действия этого голосования истек.", show_alert=True)
        return
    target_id, post_num = ids

    # Get board_id from in-memory state if available
    vm_key = generate_votemute_key(target_id, post_num)
    async with votemute_lock:
        vm = active_votemutes.get(vm_key)
        if vm:
            board_id = vm.get("board_id", board_id)

    ok, msg, current_votes, is_executed = await start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=voter_id,
        bot=callback.bot
    )

    await callback.answer(msg, show_alert=not ok or is_executed)

    # Refresh message card UI
    async with votemute_lock:
        vm_data = active_votemutes.get(vm_key, {})
        created_ts = vm_data.get("created_ts", time.time())
        executed = vm_data.get("executed", is_executed)

    new_text = get_votemute_card_text(post_num, target_id, current_votes, created_ts, executed)
    new_kb = get_votemute_keyboard(target_id, post_num, current_votes, executed)

    try:
        await callback.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    except Exception as e:
        logger.error(f"Error updating votemute message card: {e}")

    # При исполнении приговора обновляем все разосланные копии карточки
    if executed:
        async with votemute_lock:
            all_bcast = list(vm_data.get("broadcast_msgs", []))
        if all_bcast:
            async def _update_broadcast_cards():
                for chat_id, msg_id in all_bcast:
                    if callback.message and chat_id == callback.message.chat.id and msg_id == callback.message.message_id:
                        continue
                    try:
                        await callback.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=new_text,
                            reply_markup=new_kb,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            asyncio.create_task(_update_broadcast_cards())


@votemute_router.callback_query(F.data.startswith("vm_info:"))
async def callback_votemute_info(callback: types.CallbackQuery):
    """
    Handles click on completed mute info button.
    """
    await callback.answer(
        "🔒 Этот шиз уже отправлен в ЖЕЛЕЗНЫЙ МУТ на 30 минут решением народного вотума!",
        show_alert=True
    )


@votemute_router.callback_query(F.data == "menu_votemute")
async def callback_menu_votemute(callback: types.CallbackQuery):
    """
    Displays quick info about votemute in menu.
    """
    info_text = (
        "🗳️ <b>НАРОДНЫЙ ВОТУМ / ШИЗО-МУТ (/votemute)</b>\n\n"
        "Демократический инструмент саморегуляции борды:\n"
        "• Ответь <code>/votemute</code> на пост любого вайпера или токсичного шиза.\n"
        "• Если <b>5 уникальных анонов</b> нажмут кнопку голосования в течение 10 минут — нарушитель получит "
        "<b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>.\n"
        "• 🚫 <b>Особенность:</b> Этот мут НЕЛЬЗЯ снять за шекели через /shop (взятки заблокированы) и админские команды!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_help")]
    ])
    try:
        await callback.message.edit_text(info_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.answer()
