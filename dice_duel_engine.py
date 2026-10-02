# -*- coding: utf-8 -*-
"""
dice_duel_engine.py — High-Performance PvP Dice Duel (Кости / Дайс-Дуэль на Шекели) for ТГАЧ
=============================================================================================
Features:
- Pure Custom Fair 2d6 / 3d6 RNG Engine (NO native Telegram send_dice!).
- Authentic Unicode dice faces: ⚀ ⚁ ⚂ ⚃ ⚄ ⚅ with combo detection (Doubles, Triples, Snake Eyes, etc.).
- Animated suspenseful rolling frames with round-by-round and sudden-death overtime support.
- Full Escrow balance integration with atomic database locks and transaction logging.
- Authentic 2ch imageboard broadcast via process_new_post with greentext and payout notices.
- Deep integration into /casino, /duel, and /help menus with interactive inline lobbies.
"""

import time
import re
import asyncio
import random
import secrets
import math
from typing import Dict, Optional, Tuple, Any, List
from aiogram import types, F, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import shared_state
from common.db_pool import get_pool, db_lock, db_transaction
from common.database import (
    get_user_global_balance,
    add_user_global_balance,
    deduct_user_global_balance,
    add_to_abu_fund,
    record_user_transaction
)
from common.anon_identity import get_anon_id
from common.task_manager import spawn_task

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
MIN_DICE_BET = 50
MAX_DICE_BET = 50_000_000
DICE_CHALLENGE_TIMEOUT_SEC = 600.0  # 10 minutes waiting for opponent to accept
DICE_TURN_TIMEOUT_SEC = 120.0  # 2 minutes per roll
DICE_RAKE_PERCENT = 0.05  # 5% house rake to Abu fund
DICE_TIE_RAKE_PERCENT = 0.02  # 2% nominal rake on tied refund

# Unicode Dice Glyphs
DICE_GLYPHS = {
    1: "⚀",
    2: "⚁",
    3: "⚂",
    4: "⚃",
    5: "⚄",
    6: "⚅"
}

# -----------------------------------------------------------------------------
# In-Memory State & Concurrency Locks
# -----------------------------------------------------------------------------
active_dice_games: Dict[str, Dict[str, Any]] = {}
user_active_dice_game: Dict[int, str] = {}
dice_engine_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# Phrase Pools — финальные объявления дайс-дуэлей
# -----------------------------------------------------------------------------
DICE_TIMEOUT_ANNOUNCEMENTS = [
    "⏱️ <b>PvP ДАЙС-ДУЭЛЬ: ТЕХНИЧЕСКИЙ НОКАУТ!</b>\n\n>сыч испугался бросать кости и убежал в слезах\n😴 Анон <code>[ID:{loser_anon}]</code> пропустил таймер хода (120 сек)!\n👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code> забирает весь банк <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🐔 <b>PvP ДАЙС: БОЯГУЗ СЛИЛСЯ ПО ТАЙМАУТУ!</b>\n\n>руки тряслись 120 секунд и так и не бросил\n😂 Анон <code>[ID:{loser_anon}]</code> обосрался и не решился кинуть кости!\n🏆 <b>Победа техническая:</b> Анон <code>[ID:{winner_anon}]</code> берёт <b>+{win_payout:,} ₪</b> за трусость оппонента!\n{rake_label}",
    "💤 <b>PvP ДАЙС: УСНУЛ НА ХОДУ!</b>\n\n>120 секунд ждали броска — дождались только храпа\n🛌 Анон <code>[ID:{loser_anon}]</code> отрубился прямо на игровом сукне!\n💰 <b>Победитель не спит:</b> Анон <code>[ID:{winner_anon}]</code> уносит <b>+{win_payout:,} ₪</b> пока соперник дрыхнет.\n{rake_label}",
    "🤦 <b>PvP ДАЙС: 120 СЕКУНД ПОЗОРА!</b>\n\n>сидел и смотрел на кости как баран на новые ворота\n😤 Анон <code>[ID:{loser_anon}]</code> не шевельнул и пальцем за 120 секунд!\n⚡ Анон <code>[ID:{winner_anon}]</code> не такой — берёт <b>+{win_payout:,} ₪</b> за активную жизненную позицию.\n{rake_label}",
    "🏃 <b>PvP ДАЙС: ПОБЕГ С ПОЛЯ БОЯ!</b>\n\n>выбросил кости и побежал вместо того чтобы их бросить\n🐢 Анон <code>[ID:{loser_anon}]</code> ретировался по таймауту 120 сек!\n💎 <b>Победитель остался:</b> Анон <code>[ID:{winner_anon}]</code> получает <b>+{win_payout:,} ₪</b> за стойкость духа!\n{rake_label}",
    "⌛ <b>PvP ДАЙС: ВРЕМЯ ВЫШЛО — ШЕКЕЛИ УШЛИ!</b>\n\n>120 секунд тишины вместо звона костей\n🔕 Анон <code>[ID:{loser_anon}]</code> игнорировал свой ход и проиграл по дефолту!\n💸 Анон <code>[ID:{winner_anon}]</code> получает <b>+{win_payout:,} ₪</b> ни за что!\n{rake_label}",
    "😱 <b>PvP ДАЙС: ПАНИКА И БЕГСТВО!</b>\n\n>увидел банк и обосрался — не рискнул бросить\nАнон <code>[ID:{loser_anon}]</code> слился через 120 сек без броска!\n👑 Анон <code>[ID:{winner_anon}]</code> победил одним своим присутствием: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🥱 <b>PvP ДАЙС: СКУЧНЕЙШИЙ ТАЙМАУТ В ИСТОРИИ!</b>\n\n>все ждали, никто так и не дождался броска\n💤 Анон <code>[ID:{loser_anon}]</code> продемонстрировал максимальную неспособность принять решение за 120 сек.\n🎯 Анон <code>[ID:{winner_anon}]</code> уходит с <b>+{win_payout:,} ₪</b> пока сыч медитировал.\n{rake_label}",
    "🚨 <b>PvP ДАЙС: ТРЕВОГА — ИГРОК ПОТЕРЯН!</b>\n\n>120 секунд поиска — найден только след от испуганных ягодиц\n🔦 Анон <code>[ID:{loser_anon}]</code> куда-то испарился вместо броска!\n💰 Анон <code>[ID:{winner_anon}]</code> единственный живой — забирает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🗑️ <b>PvP ДАЙС: ПОЗОРНЫЙ ТАЙМАУТ ДЛЯ ИСТОРИИ!</b>\n\n>этот проигрыш запомнят дети и внуки\nАнон <code>[ID:{loser_anon}]</code> вошёл в летопись борды как самый нерешительный сыч за 120 сек без броска.\n🏆 Анон <code>[ID:{winner_anon}]</code> выигрывает <b>+{win_payout:,} ₪</b> за наличие яиц.\n{rake_label}",
    "🎪 <b>PvP ДАЙС: КЛОУН УБЕЖАЛ С АРЕНЫ!</b>\n\n>публика ждала броска, клоун убежал за кулисы\n🤡 Анон <code>[ID:{loser_anon}]</code> пропустил 120 секунд своего звёздного часа!\n🎩 Анон <code>[ID:{winner_anon}]</code> поклоняется пустому залу и уносит <b>+{win_payout:,} ₪</b>.\n{rake_label}",
    "🔇 <b>PvP ДАЙС: НЕМАЯ СЦЕНА 120 СЕКУНД!</b>\n\n>тишина, только тикают часы и воет ветер в треде\n📵 Анон <code>[ID:{loser_anon}]</code> онемел и окаменел на своём ходу!\n⚡ Анон <code>[ID:{winner_anon}]</code> пользуется этим и уводит <b>+{win_payout:,} ₪</b> из-под носа.\n{rake_label}",
    "🏚️ <b>PvP ДАЙС: ХАТА ПУСТА — ИГРОКА НЕТ!</b>\n\n>постучали 120 раз — никто не открыл\n🚪 Анон <code>[ID:{loser_anon}]</code> не вернулся к своим костям — технический нокаут!\n💰 Анон <code>[ID:{winner_anon}]</code> вламывается и забирает <b>+{win_payout:,} ₪</b> как полноправный хозяин.\n{rake_label}",
    "🌡️ <b>PvP ДАЙС: ХОЛОДНЫЙ ДУШ ОТ ТАЙМАУТА!</b>\n\n>вместо горячего броска — ледяное молчание 120 сек\n❄️ Анон <code>[ID:{loser_anon}]</code> остыл прямо перед броском и проиграл по умолчанию!\n🔥 Анон <code>[ID:{winner_anon}]</code> остался горячим и получает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🧊 <b>PvP ДАЙС: ЗАМОРОЗКА ОППОНЕНТА!</b>\n\n>страх сковал руки — кости так и не полетели\nАнон <code>[ID:{loser_anon}]</code> превратился в ледяную статую на 120 секунд.\n🌋 Анон <code>[ID:{winner_anon}]</code> один остался горячим — <b>+{win_payout:,} ₪</b> законных шекелей!\n{rake_label}",
    "📻 <b>PvP ДАЙС: РАДИОМОЛЧАНИЕ 120 СЕКУНД!</b>\n\n>всё что слышали — помехи и тишину\n📡 Анон <code>[ID:{loser_anon}]</code> отключился от реальности вместо броска!\n✅ Анон <code>[ID:{winner_anon}]</code> на связи и получает <b>+{win_payout:,} ₪</b> за присутствие духа.\n{rake_label}",
    "🚁 <b>PvP ДАЙС: ЭВАКУАЦИЯ БЕЗ ПРЕДУПРЕЖДЕНИЯ!</b>\n\n>за 120 сек успел испугаться и улететь на вертолёте\nАнон <code>[ID:{loser_anon}]</code> покинул зону комфорта прямо во время своего хода!\n🎁 Анон <code>[ID:{winner_anon}]</code> получает брошенный банк: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "💔 <b>PvP ДАЙС: СЕРДЦЕ НЕ ВЫДЕРЖАЛО — СБЕЖАЛ!</b>\n\n>пульс 200 — кости не брошены — таймаут\nАнон <code>[ID:{loser_anon}]</code> рассыпался от напряжения за 120 секунд без действий!\n🏆 Анон <code>[ID:{winner_anon}]</code> из камня — и <b>+{win_payout:,} ₪</b> тоже его!\n{rake_label}",
    "🧟 <b>PvP ДАЙС: ЗОМБИ НА ХОДУ!</b>\n\n>живой по документам, но явно уже не функционирует\nАнон <code>[ID:{loser_anon}]</code> стоит над костями 120 секунд, не шевелясь!\n⚡ Анон <code>[ID:{winner_anon}]</code> экзорцирует зомби и уносит <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎭 <b>PvP ДАЙС: ТЕАТРАЛЬНАЯ ПАУЗА ЗАТЯНУЛАСЬ!</b>\n\n>пауза 120 секунд — режиссёр уснул — занавес\nАнон <code>[ID:{loser_anon}]</code> так и не подал реплику на своём ходу!\n🏅 Анон <code>[ID:{winner_anon}]</code> единственный актёр в зале — <b>+{win_payout:,} ₪</b> ему!\n{rake_label}",
    "🦗 <b>PvP ДАЙС: СЛЫШНО КАК СВЕРЧКИ ПОЮТ!</b>\n\n>120 секунд тишины — только сверчки и отчаяние\nАнон <code>[ID:{loser_anon}]</code> безмолвно созерцал кости весь таймаут!\n💰 Анон <code>[ID:{winner_anon}]</code> устал ждать и просто забирает <b>+{win_payout:,} ₪</b>.\n{rake_label}",
    "🪦 <b>PvP ДАЙС: УПОКОИЛСЯ НА ХОД РАНЬШЕ СРОКА!</b>\n\n>время жизни истекло не дождавшись броска\nАнон <code>[ID:{loser_anon}]</code> скончался от нерешительности за 120 секунд!\n⚰️ Анон <code>[ID:{winner_anon}]</code> наследует банк покойного: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "📉 <b>PvP ДАЙС: АКЦИИ ИГРОКА УПАЛИ ДО НУЛЯ!</b>\n\n>рынок ждал новостей 120 секунд — новостей нет\nАнон <code>[ID:{loser_anon}]</code> обанкротился прямо на ходу без единого броска!\n📈 Анон <code>[ID:{winner_anon}]</code> скупает всё по дешёвке: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🌑 <b>PvP ДАЙС: ТЁМНАЯ МАТЕРИЯ ПОГЛОТИЛА ИГРОКА!</b>\n\n>сигнала нет, сыча нет, броска нет\nАнон <code>[ID:{loser_anon}]</code> ушёл в небытие на своём ходу — 120 сек без движения!\n✨ Анон <code>[ID:{winner_anon}]</code> остался во вселенной и получает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🥱 <b>PvP ДАЙС: ЛЕТАРГИЧЕСКИЙ СОН ПРЯМО НА КУБИКАХ!</b>\n\n>заснул и не проснулся за всё время хода\nАнон <code>[ID:{loser_anon}]</code> впал в кому на 120 секунд вместо броска!\n🔔 Анон <code>[ID:{winner_anon}]</code> будить не стал — просто забрал <b>+{win_payout:,} ₪</b>.\n{rake_label}",
    "🚽 <b>PvP ДАЙС: УШЁЛ В ТУАЛЕТ И НЕ ВЕРНУЛСЯ!</b>\n\n>120 секунд без броска — только звук смываемой воды\nАнон <code>[ID:{loser_anon}]</code> справил нужду и потерял право на ход!\n💩 Анон <code>[ID:{winner_anon}]</code> дождался, не зашёл в туалет и взял <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🤖 <b>PvP ДАЙС: СИСТЕМА ПЕРЕЗАГРУЗИЛАСЬ В ТАЙМАУТ!</b>\n\n>критическая ошибка принятия решений — 120 секунд перезагрузки\n⚙️ Анон <code>[ID:{loser_anon}]</code> завис и не кинул кости за всё отведённое время!\n✅ Анон <code>[ID:{winner_anon}]</code> без глюков берёт <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🦥 <b>PvP ДАЙС: ЛЕНИВЕЦ ПРОИГРАЛ ТАЙМАУТ!</b>\n\n>даже ленивец успел бы кинуть за 120 секунд — этот нет\nАнон <code>[ID:{loser_anon}]</code> побил рекорд ленивца по нерешительности!\n🏃 Анон <code>[ID:{winner_anon}]</code> шустрее и получает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎲 <b>PvP ДАЙС: КОСТИ ОБИДЕЛИСЬ НА ИГНОР!</b>\n\n>120 секунд — кости ждали, кости не дождались\n😤 Кости Анона <code>[ID:{loser_anon}]</code> самостоятельно ушли к победителю!\n🎯 Анон <code>[ID:{winner_anon}]</code> принял их с распростёртыми объятиями и <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🏔️ <b>PvP ДАЙС: ГОРА РОДИЛА МЫШЬ, А ПОТОМ И ТУ НЕ РОДИЛА!</b>\n\n>120 секунд ожидания грандиозного броска — пшик\nАнон <code>[ID:{loser_anon}]</code> ничем не разродился — технический нокаут!\n🦅 Анон <code>[ID:{winner_anon}]</code> парит высоко: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
]

DICE_SURRENDER_ANNOUNCEMENTS = [
    "🏳️ <b>PvP ДАЙС-ДУЭЛЬ: КАПИТУЛЯЦИЯ!</b>\n\n>выкинул белый флаг прямо на игровое сукно\n👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code>\n💰 Выигрыш: <b>+{win_payout:,} ₪</b> (Ставка: {bet:,} ₪).",
    "🙈 <b>PvP ДАЙС: СДАЛСЯ КАК КРЫСА!</b>\n\n>не смог вынести накал страстей и нажал /surrender\nАнон <code>[ID:{loser_anon}]</code> позорно слился!\n🎉 Анон <code>[ID:{winner_anon}]</code> ликует и получает <b>+{win_payout:,} ₪</b> от труса!",
    "✌️ <b>PvP ДАЙС: «СТОП, Я БОЛЬШЕ НЕ ХОЧУ»!</b>\n\n>не наигрался — или наигрался слишком\nАнон <code>[ID:{loser_anon}]</code> добровольно отказался от борьбы!\n💸 Анон <code>[ID:{winner_anon}]</code> получает отказной банк: <b>+{win_payout:,} ₪</b>!",
    "🐓 <b>PvP ДАЙС: ПЕТУХ СЛИЛСЯ!</b>\n\n>закукарекал и убежал с игрового стола\nАнон <code>[ID:{loser_anon}]</code> капитулировал не дождавшись конца!\n🦅 Анон <code>[ID:{winner_anon}]</code> орёл — берёт <b>+{win_payout:,} ₪</b>!",
    "😭 <b>PvP ДАЙС: РЁВ ПОРАЖЁННОГО — СДАЧА ПРИНЯТА!</b>\n\n>слёзы на клавиатуре — ввёл /surrender дрожащими руками\nАнон <code>[ID:{loser_anon}]</code> сдался, не выдержав психологического давления!\n💰 Анон <code>[ID:{winner_anon}]</code> сух и спокоен: <b>+{win_payout:,} ₪</b>!",
    "🛑 <b>PvP ДАЙС: СТОП-ИГРА! КАПИТУЛЯЦИЯ!</b>\n\n>поднял руки вверх прямо над игровым столом\nАнон <code>[ID:{loser_anon}]</code> добровольно сложил полномочия игрока!\n🏆 Анон <code>[ID:{winner_anon}]</code> единственный боец: <b>+{win_payout:,} ₪</b>!",
    "🤡 <b>PvP ДАЙС: КЛОУН СДАЛСЯ!</b>\n\n>и смешно, и грустно — и всё равно проиграл\nАнон <code>[ID:{loser_anon}]</code> признал поражение раньше времени!\n🎯 Анон <code>[ID:{winner_anon}]</code> берёт приз клоуна: <b>+{win_payout:,} ₪</b>!",
    "🪂 <b>PvP ДАЙС: КАТАПУЛЬТИРОВАЛСЯ ПРЯМО ИЗ ИГРЫ!</b>\n\n>вместо броска — прыжок с парашютом\nАнон <code>[ID:{loser_anon}]</code> покинул борт первым!\n🛫 Анон <code>[ID:{winner_anon}]</code> в кресле командира и получает <b>+{win_payout:,} ₪</b>!",
    "🏚️ <b>PvP ДАЙС: СДАЛ ПОЗИЦИИ БЕЗ БОЯ!</b>\n\n>отдал всё добровольно как настоящий омежка\nАнон <code>[ID:{loser_anon}]</code> капитулировал как последний доходяга!\n💎 Анон <code>[ID:{winner_anon}]</code> входит в пустой замок и берёт <b>+{win_payout:,} ₪</b>!",
    "🎪 <b>PvP ДАЙС: ARTISTA ПОКИНУЛ АРЕНУ!</b>\n\n>шоу не получилось — артист ушёл через чёрный ход\nАнон <code>[ID:{loser_anon}]</code> капитулировал, не закончив выступление!\n👏 Анон <code>[ID:{winner_anon}]</code> аплодирует и забирает <b>+{win_payout:,} ₪</b>!",
    "🐢 <b>PvP ДАЙС: ЧЕРЕПАХА СПРЯТАЛАСЬ В ПАНЦИРЬ!</b>\n\n>угроза слишком велика — нырнул под защитную оболочку\nАнон <code>[ID:{loser_anon}]</code> втянул голову и капитулировал!\n🦅 Анон <code>[ID:{winner_anon}]</code> хватает черепаху: <b>+{win_payout:,} ₪</b>!",
    "💣 <b>PvP ДАЙС: САПЁР СДАЛСЯ — НЕ РАЗМИНИРОВАЛ!</b>\n\n>мина слишком страшная — лучше отступить\nАнон <code>[ID:{loser_anon}]</code> предпочёл бегство разминированию банка!\n🏆 Анон <code>[ID:{winner_anon}]</code> смелее: <b>+{win_payout:,} ₪</b>!",
    "📜 <b>PvP ДАЙС: ПАКТ О КАПИТУЛЯЦИИ ПОДПИСАН!</b>\n\n>официально и по всем правилам — сдача оформлена\nАнон <code>[ID:{loser_anon}]</code> пошёл на мировую, потеряв всё!\n⚔️ Анон <code>[ID:{winner_anon}]</code> принял безоговорочную сдачу: <b>+{win_payout:,} ₪</b>!",
    "🌊 <b>PvP ДАЙС: ТОНУЩИЙ ПРИНЯЛ РЕШЕНИЕ ПЕРВЫМ!</b>\n\n>прыгнул в шлюпку до того как корабль пошёл ко дну\nАнон <code>[ID:{loser_anon}]</code> благоразумно сдался чуть раньше краха!\n⚓ Анон <code>[ID:{winner_anon}]</code> остался на капитанском мостике: <b>+{win_payout:,} ₪</b>!",
    "🪦 <b>PvP ДАЙС: ПОХОРОНИЛ СЕБЯ ДОБРОВОЛЬНО!</b>\n\n>сам лёг в гроб и попросил закрыть крышку\nАнон <code>[ID:{loser_anon}]</code> капитулировал с достоинством обречённого!\n💰 Анон <code>[ID:{winner_anon}]</code> читает панихиду и берёт <b>+{win_payout:,} ₪</b>!",
    "🔔 <b>PvP ДАЙС: ЗВОНОК ОБ ОКОНЧАНИИ БОЯ — СДАЧА!</b>\n\n>первым прекратил бой добровольно\nАнон <code>[ID:{loser_anon}]</code> отступил до гонга!\n🥊 Анон <code>[ID:{winner_anon}]</code> побеждает по очкам: <b>+{win_payout:,} ₪</b>!",
    "🏁 <b>PvP ДАЙС: ФИНИШ ДОСРОЧНО — СДАЧА!</b>\n\n>не доехал до финиша — съехал на обочину\nАнон <code>[ID:{loser_anon}]</code> не завершил гонку!\n🏎️ Анон <code>[ID:{winner_anon}]</code> пересёк финишную черту: <b>+{win_payout:,} ₪</b>!",
    "🎯 <b>PvP ДАЙС: СТРЕЛА ПОПАЛА — И ОН СДАЛСЯ!</b>\n\n>до попадания хватило одного взгляда на банк\nАнон <code>[ID:{loser_anon}]</code> психически сломлен и слился!\n🏹 Анон <code>[ID:{winner_anon}]</code> меткий: <b>+{win_payout:,} ₪</b>!",
    "🌪️ <b>PvP ДАЙС: УНЕСЛО УРАГАНОМ СТРАХА!</b>\n\n>вихрь паники накрыл игрока и унёс из игры\nАнон <code>[ID:{loser_anon}]</code> капитулировал под давлением атмосферных явлений!\n🌤️ Анон <code>[ID:{winner_anon}]</code> погода нормальная: <b>+{win_payout:,} ₪</b>!",
    "🧸 <b>PvP ДАЙС: МИШКА ПОШЁЛ ДОМОЙ!</b>\n\n>надул губы и ушёл к маме с игрушками\nАнон <code>[ID:{loser_anon}]</code> капитулировал по-детски!\n🔞 Анон <code>[ID:{winner_anon}]</code> играет по-взрослому: <b>+{win_payout:,} ₪</b>!",
    "🦴 <b>PvP ДАЙС: ОТДАЛ КОСТЬ СОПЕРНИКУ БЕЗ БОЯ!</b>\n\n>испугался кусать и сам протянул добычу\nАнон <code>[ID:{loser_anon}]</code> сдался добровольно и без условий!\n🐶 Анон <code>[ID:{winner_anon}]</code> принял кость с удовольствием: <b>+{win_payout:,} ₪</b>!",
    "🧊 <b>PvP ДАЙС: ЗАМЁРЗ НА МЕСТЕ И СДАЛСЯ!</b>\n\n>руки примёрзли к столу — не смог продолжать\nАнон <code>[ID:{loser_anon}]</code> превратился в лёд страха!\n🔥 Анон <code>[ID:{winner_anon}]</code> в огне победы: <b>+{win_payout:,} ₪</b>!",
    "😤 <b>PvP ДАЙС: ПЫХ — И СДАЛСЯ!</b>\n\n>выдохнул, надул щёки и нажал /surrender\nАнон <code>[ID:{loser_anon}]</code> сдался с максимальным недовольством!\n😎 Анон <code>[ID:{winner_anon}]</code> спокоен и богаче: <b>+{win_payout:,} ₪</b>!",
    "🎻 <b>PvP ДАЙС: РЕКВИЕМ ПО НАДЕЖДАМ — СДАЧА!</b>\n\n>музыка поражения заиграла раньше конца партии\nАнон <code>[ID:{loser_anon}]</code> услышал похоронный марш и сдался!\n🥁 Анон <code>[ID:{winner_anon}]</code> бьёт в барабаны победы: <b>+{win_payout:,} ₪</b>!",
    "🔓 <b>PvP ДАЙС: ВСКРЫЛСЯ КАК КОНСЕРВА — СДАЧА!</b>\n\n>давление внешней среды оказалось слишком высоким\nАнон <code>[ID:{loser_anon}]</code> не выдержал и сдался!\n🥫 Анон <code>[ID:{winner_anon}]</code> вскрыл банк ключом победы: <b>+{win_payout:,} ₪</b>!",
]

DICE_WIN_ANNOUNCEMENTS = [
    "🎲 <b>PvP ДАЙС-ДУЭЛЬ: РАЗНОС НА КОСТЯХ!</b>\n\n>сошлись два анона на сукне у параши\n>кости брошены, удача улыбнулась сильнейшему\n\n👑 <b>Победитель:</b> Анон <code>[ID:{winner_anon}]</code>\n🎲 Выкинул: {w_vis} — <i>{w_combo}</i>\n\n💀 <b>Проигравший:</b> Анон <code>[ID:{loser_anon}]</code>\n🎲 Выкинул: {l_vis} — <i>{l_combo}</i>\n\n💰 <b>Банк игры:</b> <code>{total_pot:,} ₪</code>\n🏆 <b>Чистый выигрыш:</b> <code>+{win_payout:,} ₪</code> отправлен чемпиону!\n{rake_label}",
    "🎯 <b>PvP ДАЙС: ТОЧНОЕ ПОПАДАНИЕ — ШЕКЕЛИ ВЗЯТЫ!</b>\n\n>кости решили всё за один бросок\n\n🏆 Анон <code>[ID:{winner_anon}]</code> бросил {w_vis} ({w_combo}) и вынес соперника!\n💀 Анон <code>[ID:{loser_anon}]</code> выкинул жалкие {l_vis} ({l_combo})!\n\n💸 Банк <code>{total_pot:,} ₪</code> → победителю <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🔥 <b>PvP ДАЙС: ОГОНЬ КОСТЕЙ — ЧЕМПИОН ОПРЕДЕЛЁН!</b>\n\n>раскалённые кубики решили судьбу двух анонов\n\n👑 Анон <code>[ID:{winner_anon}]</code>: {w_vis} — <i>{w_combo}</i> 🔥\n💀 Анон <code>[ID:{loser_anon}]</code>: {l_vis} — <i>{l_combo}</i> 🥀\n\n🏦 Куш <code>{total_pot:,} ₪</code>, чемпиону <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "⚔️ <b>PvP ДАЙС: БИТВА КУБИКОВ ЗАВЕРШЕНА!</b>\n\n>два анона скрестили дайсы и один вышел победителем\n\n🥇 Анон <code>[ID:{winner_anon}]</code> выкинул {w_vis}! Комбо: <i>{w_combo}</i>\n🥈 Анон <code>[ID:{loser_anon}]</code> проиграл с {l_vis} ({l_combo})!\n\n💰 Победитель уносит <b>+{win_payout:,} ₪</b> из банка {total_pot:,} ₪!\n{rake_label}",
    "💎 <b>PvP ДАЙС: БРИЛЛИАНТОВЫЙ БРОСОК — ПОБЕДА!</b>\n\n>сукно в блёстках от идеального результата\n\n💍 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — шедевр!\n💩 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — провал!\n\n🏆 <b>+{win_payout:,} ₪</b> уходят победителю из общего котла {total_pot:,} ₪!\n{rake_label}",
    "🎰 <b>PvP ДАЙС: ДЖЕКПОТ КУБИКОВ!</b>\n\n>барабаны остановились — и не в пользу одного из двух\n\n🃏 Анон <code>[ID:{winner_anon}]</code> сорвал куш: {w_vis} ({w_combo})!\n❌ Анон <code>[ID:{loser_anon}]</code> пролетел: {l_vis} ({l_combo})!\n\n💸 Выплата победителю: <b>+{win_payout:,} ₪</b>! Банк был: {total_pot:,} ₪!\n{rake_label}",
    "🧨 <b>PvP ДАЙС: ВЗРЫВ — ПОБЕДИТЕЛЬ НАЙДЕН!</b>\n\n>бабах — кости разлетелись и один анон остался богаче\n\n💥 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — ВЗРЫВ МОЩИ!\n😵 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — осколки судьбы!\n\n🏆 Победитель покидает поле боя с <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🌊 <b>PvP ДАЙС: ЦУНАМИ УДАЧИ — ОДИН СМЫТ!</b>\n\n>волна рандома накрыла одного и возвысила другого\n\n🏄 Анон <code>[ID:{winner_anon}]</code> оседлал волну: {w_vis} ({w_combo})!\n🌀 Анон <code>[ID:{loser_anon}]</code> утонул: {l_vis} ({l_combo})!\n\n💰 Сёрфер уносит <b>+{win_payout:,} ₪</b> из банка {total_pot:,} ₪!\n{rake_label}",
    "🦁 <b>PvP ДАЙС: ЦАРЬ ГОРЫ ОПРЕДЕЛЁН!</b>\n\n>за трон костей сразился и один стал Царём\n\n👑 Лев Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo})!\n🐁 Мышь Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo})!\n\n🏔️ Царь горы собирает дань: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎯 <b>PvP ДАЙС: ХЕДШОТ КУБИКОМ!</b>\n\n>прямое попадание по кошельку соперника\n\n🎯 Анон <code>[ID:{winner_anon}]</code>: {w_vis} — хедшот! ({w_combo})\n💀 Анон <code>[ID:{loser_anon}]</code>: {l_vis} — мимо! ({l_combo})\n\n💸 Хедшот обходится в <b>+{win_payout:,} ₪</b> для победителя!\n{rake_label}",
    "🌋 <b>PvP ДАЙС: ИЗВЕРЖЕНИЕ — ЛАВА УДАЧИ НАКРЫЛА!</b>\n\n>расплавленный рандом вынес вердикт\n\n🔥 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — лава победы!\n❄️ Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — застыл в пепле!\n\n🏆 Победитель откопал <b>+{win_payout:,} ₪</b> из вулкана!\n{rake_label}",
    "⚡ <b>PvP ДАЙС: МОЛНИЯ В КУБИК — ОДИН УБИТ!</b>\n\n>небеса указали пальцем\n\n⚡ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — благословлён молнией!\n🌧️ Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — под дождём поражения!\n\n💰 Небесная выплата: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎪 <b>PvP ДАЙС: ШОУ ЗАКОНЧЕНО — ЗВЕЗДА НАЙДЕНА!</b>\n\n>публика ждала — и получила имя победителя\n\n⭐ Звезда Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo})!\n🎭 Статист Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo})!\n\n💎 Гонорар звезды: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🏆 <b>PvP ДАЙС: КУБОК ВЗЯТ — ЛЕГЕНДА ВПИСАНА!</b>\n\n>имя победителя выгравировано на серебряном кубке\n\n🥇 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — ЛЕГЕНДА!\n🥉 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — просто участник!\n\n🏅 Легенда получает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🧠 <b>PvP ДАЙС: ИНТЕЛЛЕКТ КУБИКОВ — МУДРЕЙШИЙ ПОБЕДИЛ!</b>\n\n>удача любит подготовленных (или просто везучих)\n\n🎓 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — гений броска!\n🤡 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — слабоумие рандома!\n\n💰 IQ победителя оценивается в <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎸 <b>PvP ДАЙС: РОК-Н-РОЛЛ КУБИКОВ — РИФ ПОБЕДЫ!</b>\n\n>тяжёлый рандом сыграл для одного из двух\n\n🎵 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — хит сезона!\n🎵 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — b-side никому не нужен!\n\n🎤 Рокер уходит с <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🌠 <b>PvP ДАЙС: ЗВЕЗДА УПАЛА — ЖЕЛАНИЕ ИСПОЛНЕНО!</b>\n\n>рандом исполнил мечту одного и растоптал другого\n\n✨ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — звезда зажглась!\n🌑 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — звезда угасла!\n\n💫 Желание стоит <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🐲 <b>PvP ДАЙС: ДРАКОН ВЫБРАЛ СВОЕГО!</b>\n\n>огнедышащий рандом дохнул на одного\n\n🔥 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — избранник дракона!\n🐣 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — зажаренный цыплёнок!\n\n💰 Дракон доволен: <b>+{win_payout:,} ₪</b> победителю!\n{rake_label}",
    "🎲 <b>PvP ДАЙС: СВЯЩЕННЫЙ БРОСОК — ОРАКУЛ ОБЪЯВИЛ!</b>\n\n>боги рандома вынесли приговор\n\n🏛️ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — благословлён богами!\n⚡ Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — проклят Зевсом!\n\n🏺 Дары богов: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🏴‍☠️ <b>PvP ДАЙС: ПИРАТСКИЙ КУШ — СОКРОВИЩА ВЗЯТЫ!</b>\n\n>карта сокровищ указала правильное направление\n\n☠️ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — нашёл сундук!\n🌊 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — утонул без карты!\n\n💰 Пиратское золото: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎖️ <b>PvP ДАЙС: ОРДЕН ЗА ХРАБРОСТЬ ВРУЧЁН!</b>\n\n>самый смелый бросок принёс победу\n\n🏅 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — герой борды!\n💔 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — ранен в самолюбие!\n\n💰 Орден + <b>+{win_payout:,} ₪</b> победителю!\n{rake_label}",
    "🌀 <b>PvP ДАЙС: ВИХРЬ РАНДОМА — ОДИН ВЫЖИЛ!</b>\n\n>из двух только один оказался в безопасной зоне\n\n🌪️ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — в глазу бури!\n⚡ Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — унесён вихрём!\n\n💸 Выживший берёт <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎓 <b>PvP ДАЙС: ЭКЗАМЕН СДАН — ПРОВАЛИВШИЙСЯ ИЗВЕСТЕН!</b>\n\n>билет судьбы оказался лёгким только для одного\n\n✅ Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — отлично сдал!\n❌ Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — двоечник года!\n\n📚 Стипендия за отличную учёбу: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🥩 <b>PvP ДАЙС: МЯСНИК КУБИКОВ ПРОШЁЛСЯ ПО ИГРОКАМ!</b>\n\n>один ушёл с мясом, другой без костей\n\n🔪 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — шашлык из соперника!\n🩸 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — нарублен в фарш!\n\n🏆 Мясник получает <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🧲 <b>PvP ДАЙС: МАГНИТ УДАЧИ СРАБОТАЛ!</b>\n\n>шекели потянулись к сильнейшему\n\n🔵 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — притянул удачу!\n🔴 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — оттолкнул!\n\n💰 Магнит собрал <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎭 <b>PvP ДАЙС: ТРАГЕДИЯ И КОМЕДИЯ В ОДНОМ БРОСКЕ!</b>\n\n>судьба двух анонов разошлась в одну секунду\n\n😂 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — комедия!\n😢 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — трагедия!\n\n🎬 Главная роль стоит <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🚀 <b>PvP ДАЙС: ЗАПУСК УСПЕШЕН — ДРУГОЙ ОСТАЛСЯ НА ЗЕМЛЕ!</b>\n\n>один взлетел, другой смотрит в спину улетающему\n\n🛸 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — на орбите!\n🌍 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — в грязи на земле!\n\n🌌 Космический приз: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "⚗️ <b>PvP ДАЙС: АЛХИМИЯ КУБИКОВ — ЗОЛОТО ПОЛУЧЕНО!</b>\n\n>реакция рандома прошла успешно только для одного\n\n🧪 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — синтезировал золото!\n💀 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — взрыв в лаборатории!\n\n💰 Алхимическое золото: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
    "🎣 <b>PvP ДАЙС: РЫБАЛКА НА ШЕКЕЛИ — КРУПНАЯ РЫБА ПОЙМАНА!</b>\n\n>один закинул удочку, другой оказался на крючке\n\n🐟 Анон <code>[ID:{winner_anon}]</code>: {w_vis} ({w_combo}) — щука!\n🪱 Анон <code>[ID:{loser_anon}]</code>: {l_vis} ({l_combo}) — червяк на крючке!\n\n🏆 Улов дня: <b>+{win_payout:,} ₪</b>!\n{rake_label}",
]

DICE_DRAW_ANNOUNCEMENTS = [
    "🤝 <b>PvP ДАЙС: МЁРТВАЯ НИЧЬЯ!</b>\n\n>кости брошены трижды, победитель не выявлен\n⚖️ Анон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> сошлись на равных на <b>{bet:,} ₪</b>!\n\n💰 Ставки возвращены за вычетом 2% в Казну Абу.",
    "☯️ <b>PvP ДАЙС: РАВНОВЕСИЕ КУБИКОВ — НИЧЬЯ!</b>\n\n>вселенная не выбрала победителя\nДва анона — <code>[ID:{p1_anon}]</code> и <code>[ID:{p2_anon}]</code> — выбросили одинаково!\n💸 Бесполезная ничья. Ставка {bet:,} ₪ возвращается минус 2% Абу.",
    "🤡 <b>PvP ДАЙС: ДВА КЛОУНА — ОДИН РЕЗУЛЬТАТ!</b>\n\n>оба кинули одно и то же — феерический провал\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> одинаково плохи (ставка: {bet:,} ₪)!\n🎪 Ничья. Абу берёт 2% за цирк.",
    "😐 <b>PvP ДАЙС: СКУЧНЕЙШАЯ НИЧЬЯ В ИСТОРИИ БОРДЫ!</b>\n\n>никто не победил, все проиграли немного\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ — одинаковый результат!\n💤 2% в Казну Абу за потраченное время всей борды.",
    "⚖️ <b>PvP ДАЙС: ВЕСЫ РАНДОМА ЗАМЕРЛИ — НИЧЬЯ!</b>\n\n>судьба не выбрала чемпиона — оба одинаково убоги\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> разделили поражение пополам!\n💰 Возврат ставки {bet:,} ₪ минус 2% тупого рандома.",
    "🔄 <b>PvP ДАЙС: БЕСКОНЕЧНЫЙ ЦИКЛ — НИЧЬЯ!</b>\n\n>система зациклилась — победитель не найден\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: одинаковые кости, {bet:,} ₪ ставка!\n♾️ Бесконечная ничья завершена. 2% Абу за его терпение.",
    "🤷 <b>PvP ДАЙС: РАНДОМ ПОЖАЛ ПЛЕЧАМИ — НИЧЬЯ!</b>\n\n>даже боги не решили чей бросок круче\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> одинаково посредственны!\n💸 Возвращено {bet:,} ₪ каждому минус 2% за бессмысленность.",
    "🌀 <b>PvP ДАЙС: ВИХРЬ ЗАКОНЧИЛСЯ НИЧЬЕЙ!</b>\n\n>буря утихла, а победителя нет\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ сгорели в атмосфере ничьей!\n❄️ Тишина и 2% Абу за вихрь.",
    "🙃 <b>PvP ДАЙС: МИР ПЕРЕВЁРНУТ НИЧЬЕЙ!</b>\n\n>когда никто не побеждает — все проигрывают\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> перевернули логику на {bet:,} ₪!\n💡 Философская ничья. Абу доволен 2%.",
    "🤝 <b>PvP ДАЙС: ДЖЕНТЛЬМЕНСКОЕ СОГЛАШЕНИЕ — НИЧЬЯ!</b>\n\n>оба слишком вежливы чтобы победить\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> раскланялись над {bet:,} ₪!\n🎩 По одному поклону и 2% Абу за этикет.",
    "🌑 <b>PvP ДАЙС: ТЁМНАЯ МАТЕРИЯ ПОГЛОТИЛА ПОБЕДУ!</b>\n\n>победа исчезла в квантовой неопределённости\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> одинаково провалились на {bet:,} ₪!\n⭐ 2% Абу за космическую глупость.",
    "🎭 <b>PvP ДАЙС: ТРАГИКОМЕДИЯ — НИЧЬЯ!</b>\n\n>грустно, смешно, бесполезно — вот ничья\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ на кону, результат одинаков!\n🎪 Занавес, аплодисменты и 2% Абу.",
    "🏁 <b>PvP ДАЙС: ФОТОФИНИШ — НИЧЬЯ!</b>\n\n>судьи смотрели фото и не нашли победителя\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> финишировали вместе с {bet:,} ₪!\n📷 Ничья. 2% Абу за фотоматериалы.",
    "🔮 <b>PvP ДАЙС: ХРУСТАЛЬНЫЙ ШАР НЕ ОТВЕТИЛ — НИЧЬЯ!</b>\n\n>гадалка посмотрела в шар — победителя не видит\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: судьба {bet:,} ₪ неясна!\n🌫️ Туманная ничья. 2% Абу за предсказание.",
    "💫 <b>PvP ДАЙС: ЗВЁЗДЫ НЕ СОШЛИСЬ — НИЧЬЯ!</b>\n\n>астрология не помогла ни тому ни другому\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> равно несчастливы на {bet:,} ₪!\n🌙 Ничья по гороскопу. 2% Абу за астрологическую консультацию.",
    "🧩 <b>PvP ДАЙС: ПАЗЗЛ НЕ СЛОЖИЛСЯ — НИЧЬЯ!</b>\n\n>кусочки рандома встали одинаково для обоих\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ застряли в ничьей!\n🎯 Паззл завершён без победителя. 2% Абу за сложность.",
    "🎵 <b>PvP ДАЙС: ДУЭТ БЕЗ СОЛИСТА — НИЧЬЯ!</b>\n\n>оба пели одну ноту, никто не солировал\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> исполнили дуэт ничьей на {bet:,} ₪!\n🎸 Концерт окончен. 2% Абу за бэк-вокал.",
    "📐 <b>PvP ДАЙС: ГЕОМЕТРИЯ ПРОВАЛА — НИЧЬЯ!</b>\n\n>два вектора сложились в ноль\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ в точке симметрии!\n📏 Идеально симметричная ничья. 2% Абу за математику.",
    "🌊 <b>PvP ДАЙС: ВОЛНА РАЗБИЛАСЬ В НИЧЬЮ!</b>\n\n>прилив рандома одинаково накрыл обоих\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> мокрые и без денег ({bet:,} ₪ ставка)!\n💧 2% Абу за жидкий результат.",
    "🤖 <b>PvP ДАЙС: СИСТЕМА ЗАВИСЛА — НИЧЬЯ!</b>\n\n>процессор рандома выдал одинаковое значение для обоих\nАнон <code>[ID:{p1_anon}]</code> vs Анон <code>[ID:{p2_anon}]</code>: {bet:,} ₪ застряли в кэше!\n⚙️ Системная ничья. 2% Абу за дебаггинг.",
    "🏔️ <b>PvP ДАЙС: ДВА АЛЬПИНИСТА НА ВЕРШИНЕ — НИЧЬЯ!</b>\n\n>оба добрались до одной точки одновременно\nАнон <code>[ID:{p1_anon}]</code> и Анон <code>[ID:{p2_anon}]</code> делят вершину на {bet:,} ₪!\n🌄 Горная ничья. 2% Абу за высотные работы.",
]



# -----------------------------------------------------------------------------
# Core Dice Mathematics & RNG Logic
# -----------------------------------------------------------------------------
def generate_game_id() -> str:
    """Generates a unique identifier for a dice duel session."""
    return f"dice_{int(time.time()*1000)}_{secrets.randbelow(900) + 100}"


def roll_single_die() -> int:
    """Cryptographically secure single 6-sided die roll (1-6)."""
    return secrets.randbelow(6) + 1


def roll_dice_set(num_dice: int = 2) -> List[int]:
    """Rolls N fair 6-sided dice."""
    return [roll_single_die() for _ in range(num_dice)]


def format_dice_visual(dice: List[int]) -> str:
    """Formats list of dice values into unicode representation: [ ⚄ ⚅ ] (11)."""
    if not dice:
        return "[ 🎲 🎲 ]"
    glyphs = " ".join(DICE_GLYPHS.get(d, "🎲") for d in dice)
    total = sum(dice)
    return f"<b>[ {glyphs} ]</b> (<code>{total}</code>)"


def evaluate_roll_combo(dice: List[int]) -> Tuple[int, str, str]:
    """
    Evaluates dice roll score and flavor combo commentary.
    Returns: (total_score, combo_title, flavor_desc)
    """
    if not dice:
        return 0, "Пусто", "Кости не брошены"
    total = sum(dice)
    n = len(dice)

    if n == 2:
        d1, d2 = dice[0], dice[1]
        if d1 == d2 == 6:
            return total, "👑 ДУБЛЬ ШЕСТЁРОК (12)", "Абсолютный куш! Чистая база и максимальный разнос!"
        if d1 == d2 == 1:
            return total, "🐍 ЗМЕИНЫЕ ГЛАЗКИ (2)", "Критический фейл! Глаза змеи смотрят прямо в душу сыча."
        if d1 == d2:
            return total, f"🎲 ДУБЛЬ ({d1}+{d2})", f"Синхронный дубль на {DICE_GLYPHS.get(d1, '')}! Удача благоволит."
        if total == 11:
            return total, "🔥 ПОЧТИ МАКСИМУМ (11)", "Мощнейший бросок, кости раскалились докрасна!"
        if total == 3:
            return total, "💩 ПОДЛИВА (3)", "Хуже некуда, одна нога на параше."
        if total >= 8:
            return total, f"✨ ХОРОШИЙ БРОСОК ({total})", "Уверенная сумма очков на сукне."
        return total, f"🎲 ОБЫЧНЫЙ БРОСОК ({total})", "Рядовой результат в подпольной костильне."

    elif n == 3:
        if dice[0] == dice[1] == dice[2] == 6:
            return total, "👑 ТРИ ШЕСТЁРКИ (18)", "ДЬЯВОЛЬСКИЙ ТРИПЛ! Казна Абу трещит по швам!"
        if dice[0] == dice[1] == dice[2] == 1:
            return total, "💀 ТРИ ЕДИНИЦЫ (3)", "Тотальное фиаско! Судьба втоптала в грязь."
        if len(set(dice)) == 1:
            return total, f"💎 ТРИПЛ НА {dice[0]} ({total})", "Редчайшая комбинация трех одинаковых костей!"
        if total >= 15:
            return total, f"🔥 БОЛЬШОЙ КУШ ({total})", "Сокрушительный результат 3d6!"
        if total <= 6:
            return total, f"💩 НИЗКИЙ БРОСОК ({total})", "Грустная сумма, пахнет проигрышем."
        return total, f"🎲 СУММА 3d6 ({total})", "Кости легли как предначертано."

    return total, f"🎲 СУММА ({total})", "Результат зафиксирован."


# -----------------------------------------------------------------------------
# Keyboards & Interactive UI Components
# -----------------------------------------------------------------------------
def get_dice_challenge_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Keyboard attached to the public challenge message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Принять вызов на кости!", callback_data=f"dice_accept:{game_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dice_decline:{game_id}")
        ]
    ])


def get_dice_roll_keyboard(
    game_id: str,
    is_my_turn: bool = True,
    is_shared_chat: bool = False,
    turn_anon: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Keyboard displayed during active rolling turns."""
    if is_shared_chat:
        tag = f" (Анон [{turn_anon}])" if turn_anon else ""
        roll_btn = InlineKeyboardButton(text=f"🎲 БРОСИТЬ КОСТИ!{tag}", callback_data=f"dice_roll:{game_id}")
    elif is_my_turn:
        roll_btn = InlineKeyboardButton(text="🎲 БРОСИТЬ КОСТИ! (Твой ход)", callback_data=f"dice_roll:{game_id}")
    else:
        roll_btn = InlineKeyboardButton(text="⏳ Очередь соперника...", callback_data=f"dice_wait:{game_id}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [roll_btn],
        [
            InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"dice_surrender:{game_id}"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"dice_refresh:{game_id}")
        ]
    ])


def get_dice_finished_keyboard(game_id: str, bet: int) -> InlineKeyboardMarkup:
    """Keyboard displayed when a game finishes."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🔄 Реванш ({bet:,} ₪)", callback_data=f"dice_rematch:{game_id}"),
            InlineKeyboardButton(text="🎰 Меню Казино", callback_data="cas:hub")
        ]
    ])


def format_dice_bet_amount(amount: int) -> str:
    if amount >= 1_000_000:
        if amount % 1_000_000 == 0:
            return f"{amount // 1_000_000}M ₪"
        return f"{amount / 1_000_000:.1f}M ₪"
    elif amount >= 1000:
        if amount % 1000 == 0:
            return f"{amount // 1000}k ₪"
        return f"{amount / 1000:.1f}k ₪"
    return f"{amount} ₪"


def get_adaptive_dice_bet_presets(balance: int, current_bet: int = 100) -> List[int]:
    """Generates affordable bet presets based on player's current balance."""
    ALL_PRESETS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
    eff_bal = max(0, int(balance))
    if eff_bal < MIN_DICE_BET:
        return [MIN_DICE_BET]
    affordable = [p for p in ALL_PRESETS if p <= eff_bal and p <= MAX_DICE_BET]
    if not affordable:
        return [max(MIN_DICE_BET, min(eff_bal, MAX_DICE_BET))]
    if len(affordable) <= 5:
        return affordable
    indices = [0, len(affordable) // 4, len(affordable) // 2, (len(affordable) * 3) // 4, len(affordable) - 1]
    return sorted(list(set(affordable[i] for i in indices)))


def get_dice_lobby_keyboard(balance: int = 1000, current_bet: int = 100, target_id: int = 0) -> InlineKeyboardMarkup:
    """Interactive quick lobby keyboard for /casino or /duel menu."""
    current_bet = max(MIN_DICE_BET, min(MAX_DICE_BET, current_bet))
    presets = get_adaptive_dice_bet_presets(balance, current_bet)
    t_tag = f":{target_id}" if target_id else ":0"
    preset_row = [
        InlineKeyboardButton(text=format_dice_bet_amount(p), callback_data=f"dice_lobby_bet:{p}{t_tag}")
        for p in presets
    ]

    half_bet = max(MIN_DICE_BET, current_bet // 2)
    double_bet = min(MAX_DICE_BET, min(int(balance), current_bet * 2)) if balance >= current_bet * 2 else current_bet
    max_bet = max(MIN_DICE_BET, min(MAX_DICE_BET, int(balance)))
    ctrl_row = [
        InlineKeyboardButton(text="/2", callback_data=f"dice_lobby_bet:{half_bet}{t_tag}"),
        InlineKeyboardButton(text="x2", callback_data=f"dice_lobby_bet:{double_bet}{t_tag}"),
        InlineKeyboardButton(text="💰 ВА-БАНК", callback_data=f"dice_lobby_bet:{max_bet}{t_tag}"),
    ]

    buttons = [
        [
            InlineKeyboardButton(text=f"🎲 Дуэль 2d6 ({format_dice_bet_amount(current_bet)})", callback_data=f"dice_create_fast:2d6:{current_bet}{t_tag}"),
            InlineKeyboardButton(text=f"🔥 Дуэль 3d6 ({format_dice_bet_amount(current_bet)})", callback_data=f"dice_create_fast:3d6:{current_bet}{t_tag}")
        ],
        preset_row,
        ctrl_row,
        [
            InlineKeyboardButton(text="⚔️ Меню Дуэлей (/duel)", callback_data="menu_duel"),
            InlineKeyboardButton(text="🔙 Меню Казино", callback_data="cas:hub")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# -----------------------------------------------------------------------------
# Public Board Broadcast via process_new_post
# -----------------------------------------------------------------------------
async def broadcast_dice_announcement(bot, board_id: str, text: str):
    """
    Asynchronously broadcasts finished duel outcome to the board feed via process_new_post.
    """
    try:
        from post_processor import process_new_post
        import shared_state
        params = shared_state.NewPostParams(
            bot_instance=bot,
            board_id=board_id,
            user_id=0,
            content={'type': 'text', 'text': text, 'is_system_message': True, 'archive_allowed': True},
            reply_to_post=None,
            is_shadow_muted=False,
            stream='ru'
        )
        await process_new_post(params)
    except Exception as e:
        shared_state.runtime_logger.warning(f"Failed to broadcast dice duel post: {e}")


async def send_pvp_direct_notification(bot: Any, user_id: int, text: str) -> bool:
    """
    Safely sends a private notification DM to a user on Telegram with full error suppression.
    """
    if not bot or not user_id:
        return False
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML"
        )
        return True
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        shared_state.runtime_logger.debug(f"Direct notification suppressed for user {user_id}: {e}")
        return False
    except Exception as e:
        shared_state.runtime_logger.warning(f"Direct notification failed for user {user_id}: {e}")
        return False


# -----------------------------------------------------------------------------
# Session Lifecycle Handlers
# -----------------------------------------------------------------------------
async def create_dice_challenge(
    board_id: str,
    challenger_id: int,
    bet: int,
    target_id: Optional[int] = None,
    num_dice: int = 2
) -> Tuple[bool, str, Optional[str]]:
    """
    Creates a new PvP Dice challenge with bet escrow verification.
    """
    try:
        bet_val = float(bet)
        if math.isnan(bet_val) or math.isinf(bet_val):
            return False, "❌ Некорректная сумма ставки.", None
        bet = int(bet_val)
    except (ValueError, TypeError, OverflowError):
        return False, "❌ Некорректная сумма ставки.", None

    if bet < MIN_DICE_BET:
        return False, f"❌ Минимальная ставка в Дайс-Дуэль: <b>{MIN_DICE_BET} ₪</b>.", None
    if bet > MAX_DICE_BET:
        return False, f"❌ Максимальная ставка в Дайс-Дуэль: <b>{MAX_DICE_BET:,} ₪</b>.", None

    db = await get_pool()
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(challenger_id, board_id, db=db) or await check_user_is_muted(db, challenger_id, board_id):
        return False, "🔇 Замученным нельзя создавать дайс-дуэли.", None

    async with db_lock:
        bal = await get_user_global_balance(db, challenger_id)
    
    if bal < bet:
        return False, f"❌ Недостаточно шекелей! Ставка: <b>{bet:,} ₪</b>, на балансе: <b>{int(bal):,} ₪</b>.", None

    async with dice_engine_lock:
        if challenger_id in user_active_dice_game:
            old_gid = user_active_dice_game[challenger_id]
            if old_gid in active_dice_games and not active_dice_games[old_gid].get("finished"):
                return False, "⚠️ У тебя уже есть активная партия в кости! Заверши её или дождись таймаута.", None

        game_id = generate_game_id()
        active_dice_games[game_id] = {
            "game_id": game_id,
            "board_id": board_id,
            "player_1": challenger_id,
            "player_2": target_id,
            "target_id": target_id,
            "bet": bet,
            "num_dice": num_dice,
            "round": 1,
            "state": "pending",
            "p1_rolls": {},   # round_num -> List[int]
            "p2_rolls": {},   # round_num -> List[int]
            "current_turn": None,
            "turn_deadline_ts": time.time() + DICE_CHALLENGE_TIMEOUT_SEC,
            "created_ts": time.time(),
            "finished": False,
            "chat_id": None,
            "msg_id": None,
            "player_msgs": {},
            "broadcast_msgs": []
        }
        user_active_dice_game[challenger_id] = game_id

    return True, "✅ Вызов на кости создан!", game_id


async def accept_dice_challenge(
    game_id: str,
    acceptor_id: int
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Accepts pending challenge, performs atomic escrow deduction for both players,
    and initializes the first rolling turn.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена или время вызова истекло.", None
        if game["state"] not in ("pending",):
            return False, "❌ Этот вызов уже принят или закрыт!", None
        if game["player_1"] == acceptor_id:
            return False, "❌ Нельзя играть в кости с самим собой, шизофреник.", None
        if game.get("target_id") and game["target_id"] != acceptor_id:
            return False, "❌ Этот вызов адресован персонально другому анону!", None
        # Prevent acceptor from joining two games simultaneously
        existing_gid = user_active_dice_game.get(acceptor_id)
        if existing_gid and existing_gid in active_dice_games and not active_dice_games[existing_gid].get("finished"):
            return False, "⚠️ У тебя уже есть активная партия в кости! Заверши её или дождись таймаута.", None

        bet = game["bet"]
        board_id = game["board_id"]
        challenger_id = game["player_1"]
        # Mark 'accepting' immediately to prevent double-accept race condition
        game["state"] = "accepting"

    def _rollback_state():
        g = active_dice_games.get(game_id)
        if g and g.get("state") == "accepting":
            g["state"] = "pending"

    db = await get_pool()
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    if await check_db_shadow_muted(acceptor_id, board_id, db=db) or await check_user_is_muted(db, acceptor_id, board_id):
        async with dice_engine_lock: _rollback_state()
        return False, "🔇 Замученным нельзя принимать дайс-дуэли.", None
    if await check_db_shadow_muted(challenger_id, board_id, db=db) or await check_user_is_muted(db, challenger_id, board_id):
        async with dice_engine_lock: _rollback_state()
        return False, "🔇 Создатель дуэли находится в муте. Игра отменена.", None

    async with db_lock:
        async with db_transaction(db):
            bal_c = await get_user_global_balance(db, challenger_id)
            bal_a = await get_user_global_balance(db, acceptor_id)

            if bal_c < bet:
                async with dice_engine_lock: _rollback_state()
                return False, "❌ У создателя вызова уже не хватает шекелей на балансе!", None
            if bal_a < bet:
                async with dice_engine_lock: _rollback_state()
                return False, f"❌ У тебя не хватает шекелей! Ставка: <b>{bet:,} ₪</b>, твой баланс: <b>{int(bal_a):,} ₪</b>.", None

            # Atomic Escrow deduction with safe rollback
            ok_c, _ = await deduct_user_global_balance(db, challenger_id, board_id, bet)
            ok_a, _ = await deduct_user_global_balance(db, acceptor_id, board_id, bet)

            if not (ok_c and ok_a):
                if ok_c:
                    await add_user_global_balance(db, challenger_id, board_id, bet)
                if ok_a:
                    await add_user_global_balance(db, acceptor_id, board_id, bet)
                async with dice_engine_lock: _rollback_state()
                return False, "❌ Ошибка списания средств. У одного из игроков изменился баланс.", None

            await record_user_transaction(db, challenger_id, -bet, 'dice_duel', f'Ставка в Дайс-Дуэль #{game_id}')
            await record_user_transaction(db, acceptor_id, -bet, 'dice_duel', f'Ставка в Дайс-Дуэль #{game_id}')

    async with dice_engine_lock:
        game["player_2"] = acceptor_id
        game["state"] = "playing"
        # First turn is randomized
        game["current_turn"] = challenger_id if secrets.randbelow(2) == 0 else acceptor_id
        game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
        user_active_dice_game[acceptor_id] = game_id

    return True, "✅ Вызов принят! Кости на столе!", game


async def cancel_dice_challenge(
    game_id: str,
    user_id: int,
    bot: Any = None
) -> Tuple[bool, str]:
    """Cancels a pending challenge before it is accepted."""
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Вызов не найден."
        if game["state"] != "pending":
            return False, "❌ Нельзя отменить уже начавшуюся дуэль!"
        if user_id != game["player_1"] and (not game.get("target_id") or user_id != game.get("target_id")):
            return False, "❌ Только участники вызова могут его отменить."

        p1 = game["player_1"]
        game["state"] = "cancelled"
        game["finished"] = True
        game["finished_ts"] = time.time()
        user_active_dice_game.pop(game["player_1"], None)
        if game.get("target_id"):
            user_active_dice_game.pop(game["target_id"], None)

    if user_id == p1:
        return True, "🗑 Вызов успешно отменен."
    else:
        if bot and p1:
            dec_dm = (
                f"⚔️ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ОТКЛОНЕН</b>\n\n"
                f"Анон [ID:{get_anon_id(user_id)}] отклонил твой вызов на кости."
            )
            asyncio.create_task(send_pvp_direct_notification(bot, p1, dec_dm))
        return True, f"❌ Вызов на дуэль отклонен Аноном [ID:{get_anon_id(user_id)}]."


decline_or_cancel_dice_challenge = cancel_dice_challenge


# -----------------------------------------------------------------------------
# Rolling & Animated Execution Engine
# -----------------------------------------------------------------------------
async def execute_player_roll(
    game_id: str,
    user_id: int,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes a dice roll for the active player with animated suspense,
    advances the turn or resolves the game if both rolled.
    """
    current_round = None
    resolve_round = False

    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Партия не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game
        if game["state"] not in ("playing", "rolling"):
            return False, "❌ Игра не готова к броску.", game
        if user_id not in (game["player_1"], game["player_2"]):
            return False, "❌ Ты не участвуешь в этой дуэли!", game
        if user_id != game.get("current_turn"):
            return False, "⏳ Сейчас ход твоего соперника! Жди броска.", game

        current_round = game["round"]
        num_dice = game.get("num_dice", 2)
        rolled_values = roll_dice_set(num_dice)

        if user_id == game["player_1"]:
            game["p1_rolls"][current_round] = rolled_values
        else:
            game["p2_rolls"][current_round] = rolled_values

        p1_done = current_round in game["p1_rolls"]
        p2_done = current_round in game["p2_rolls"]

        other_player = game["player_2"] if user_id == game["player_1"] else game["player_1"]

        if not (p1_done and p2_done):
            # Advance turn to the second player
            game["state"] = "playing"
            game["current_turn"] = other_player
            game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
            return True, "✅ Бросок зафиксирован! Ход переходит к сопернику.", game

        # If both players have completed the current round, transition state to resolving
        game["state"] = "resolving"
        resolve_round = True

    if resolve_round:
        return await _evaluate_and_finish_round(game_id, current_round, bot)

    return True, "✅ Бросок зафиксирован!", game


async def _evaluate_and_finish_round(
    game_id: str,
    round_num: int,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Compares roll scores for the current round. Triggers sudden death overtime if tied,
    or finalizes the game with payouts.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game

        p1 = game["player_1"]
        p2 = game["player_2"]
        r1 = game["p1_rolls"].get(round_num)
        r2 = game["p2_rolls"].get(round_num)

        if not r1 or not r2:
            return False, "❌ Ошибка раунда: не все броски совершены.", game

        score1, combo1, flavor1 = evaluate_roll_combo(r1)
        score2, combo2, flavor2 = evaluate_roll_combo(r2)

        # Tie Breaker / Overtime check
        if score1 == score2:
            if round_num < 3:
                game["round"] += 1
                next_round = game["round"]
                game["current_turn"] = p1 if secrets.randbelow(2) == 0 else p2
                game["turn_deadline_ts"] = time.time() + DICE_TURN_TIMEOUT_SEC
                game["state"] = "playing"
                return True, f"⚖️ <b>НИЧЬЯ В РАУНДЕ {round_num} ({score1}:{score2})!</b> Назначается овертайм (Раунд {next_round})!", game
            else:
                # Absolute max rounds tie -> Refund minus nominal tie rake
                winner_id = None
                loser_id = None
                finish_reason = "draw"
        else:
            winner_id = p1 if score1 > score2 else p2
            loser_id = p2 if score1 > score2 else p1
            finish_reason = "win"

    return await _finish_dice_game(game_id, winner_id, loser_id, finish_reason, bot)


async def _finish_dice_game(
    game_id: str,
    winner_id: Optional[int],
    loser_id: Optional[int],
    reason: str,
    bot: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Finalizes dice duel, distributes winnings/refunds, pays Abu fund rake,
    sends direct user notifications, and publishes the board announcement post.
    """
    async with dice_engine_lock:
        game = active_dice_games.get(game_id)
        if not game:
            return False, "❌ Игра не найдена.", {}
        if game.get("finished"):
            return False, "❌ Игра уже завершена.", game

        game["finished"] = True
        game["state"] = "finished"
        game["finished_ts"] = time.time()
        bet = game["bet"]
        board_id = game["board_id"]
        p1 = game["player_1"]
        p2 = game["player_2"]

        user_active_dice_game.pop(p1, None)
        if p2:
            user_active_dice_game.pop(p2, None)

    db = await get_pool()

    if reason == "draw":
        rake = max(1, int(bet * DICE_TIE_RAKE_PERCENT))
        refund_amt = bet - rake
        async with db_lock:
            async with db_transaction(db):
                await add_user_global_balance(db, p1, board_id, refund_amt)
                if p2:
                    await add_user_global_balance(db, p2, board_id, refund_amt)
                await add_to_abu_fund(db, rake * 2)
                await record_user_transaction(db, p1, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')
                if p2:
                    await record_user_transaction(db, p2, refund_amt, 'dice_duel', f'Возврат ничьей в Кости #{game_id}')

        game["outcome"] = "draw"
        game["payout"] = refund_amt

        draw_notify_text = (
            f"🤝 <b>НИЧЬЯ В ДАЙС-ДУЭЛИ #{game_id}</b>\n\n"
            f"💰 Твоя ставка возвращена: <b>+{refund_amt:,} ₪</b> (за вычетом 2% в Казну Абу)."
        )
        if bot:
            asyncio.create_task(send_pvp_direct_notification(bot, p1, draw_notify_text))
            if p2:
                asyncio.create_task(send_pvp_direct_notification(bot, p2, draw_notify_text))
        
        p1_anon_ann = get_anon_id(p1) if p1 else "???"
        p2_anon_ann = get_anon_id(p2) if p2 else "???"
        announcement = random.choice(DICE_DRAW_ANNOUNCEMENTS).format(
            p1_anon=p1_anon_ann, p2_anon=p2_anon_ann, bet=bet, refund_amt=refund_amt
        )
        if bot:
            asyncio.create_task(broadcast_dice_announcement(bot, board_id, announcement))
            await sync_dice_screens(bot, game)
        return True, "🤝 Ничья в дайс-дуэли!", game

    else:
        total_pot = bet * 2
        is_burn_rake = total_pot > 50000
        if is_burn_rake:
            rake = max(5, int(total_pot * 0.10))
            rake_label = f"🔥 <b>Сжигаемый рейк (10%):</b> <code>{rake:,} ₪</code> навсегда выведены из экономики!"
        else:
            rake = max(5, int(total_pot * DICE_RAKE_PERCENT))
            rake_label = f"🐒 <b>Налог Абу (5%):</b> <code>{rake:,} ₪</code>"

        win_payout = total_pot - rake

        async with db_lock:
            async with db_transaction(db):
                if winner_id:
                    await add_user_global_balance(db, winner_id, board_id, win_payout)
                    tx_desc = f'Выигрыш в Дайс-Дуэль #{game_id}' + (f' (сожжён рейк 10%: -{rake:,} ₪)' if is_burn_rake else '')
                    await record_user_transaction(db, winner_id, win_payout, 'dice_duel', tx_desc)
                if not is_burn_rake:
                    await add_to_abu_fund(db, rake)

        game["outcome"] = "win"
        game["winner"] = winner_id
        game["loser"] = loser_id
        game["payout"] = win_payout

        last_round = game["round"]
        w_rolls = game["p1_rolls"].get(last_round) if winner_id == p1 else game["p2_rolls"].get(last_round)
        l_rolls = game["p2_rolls"].get(last_round) if winner_id == p1 else game["p1_rolls"].get(last_round)

        w_vis = format_dice_visual(w_rolls) if w_rolls else "Бросок"
        l_vis = format_dice_visual(l_rolls) if l_rolls else "Фейл"
        
        winner_anon = get_anon_id(winner_id) if winner_id else "???"
        loser_anon = get_anon_id(loser_id) if loser_id else "???"

        if bot:
            if winner_id:
                win_notify_text = (
                    f"👑 <b>ПОБЕДА В ДАЙС-ДУЭЛИ #{game_id}!</b>\n\n"
                    f"💰 Твой чистый выигрыш: <b>+{win_payout:,} ₪</b> зачислен на баланс!"
                )
                asyncio.create_task(send_pvp_direct_notification(bot, winner_id, win_notify_text))
            if loser_id:
                if reason == "timeout":
                    lose_reason_str = "Таймаут броска (120 сек)"
                elif reason == "surrender":
                    lose_reason_str = "Капитуляция"
                else:
                    lose_reason_str = "Меньшая сумма очков на костях"
                lose_notify_text = (
                    f"💀 <b>ПОРАЖЕНИЕ В ДАЙС-ДУЭЛИ #{game_id}</b>\n\n"
                    f"Причина: {lose_reason_str}.\n"
                    f"💸 Списано: <b>-{bet:,} ₪</b>."
                )
                asyncio.create_task(send_pvp_direct_notification(bot, loser_id, lose_notify_text))

        if reason == "timeout":
            announcement = random.choice(DICE_TIMEOUT_ANNOUNCEMENTS).format(
                loser_anon=loser_anon, winner_anon=winner_anon,
                win_payout=win_payout, rake_label=rake_label
            )
        elif reason == "surrender":
            announcement = random.choice(DICE_SURRENDER_ANNOUNCEMENTS).format(
                loser_anon=loser_anon, winner_anon=winner_anon,
                win_payout=win_payout, bet=bet, rake_label=rake_label
            )
        else:
            w_score, w_combo, w_flavor = evaluate_roll_combo(w_rolls) if w_rolls else (0, "", "")
            l_score, l_combo, l_flavor = evaluate_roll_combo(l_rolls) if l_rolls else (0, "", "")
            announcement = random.choice(DICE_WIN_ANNOUNCEMENTS).format(
                winner_anon=winner_anon, loser_anon=loser_anon,
                w_vis=w_vis, w_combo=w_combo,
                l_vis=l_vis, l_combo=l_combo,
                total_pot=total_pot, win_payout=win_payout,
                rake_label=rake_label
            )

        if bot:
            dice_mult = round(win_payout / max(1, bet), 2)
            if win_payout >= 100000 and dice_mult >= 5.0:
                asyncio.create_task(broadcast_dice_announcement(bot, board_id, announcement))
            if win_payout >= 300000 and winner_id:
                try:
                    from news_channel_publisher import publish_casino_jackpot_news
                    asyncio.create_task(publish_casino_jackpot_news(
                        bot=bot,
                        user_id=winner_id,
                        game_type="dice",
                        bet_amount=bet,
                        win_amount=win_payout,
                        multiplier=dice_mult,
                        symbols=f"{w_vis} vs {l_vis}",
                        board_id=board_id
                    ))
                except Exception:
                    pass
            await sync_dice_screens(bot, game)
        return True, "👑 Победа в дайс-дуэли!", game


# -----------------------------------------------------------------------------
# Message Formatters & UI Presentation
# -----------------------------------------------------------------------------
def format_dice_game_message(game: Dict[str, Any]) -> str:
    """Formats live duel status message for Telegram chat."""
    p1 = game["player_1"]
    p2 = game.get("player_2")
    bet = game["bet"]
    mode = f"{game.get('num_dice', 2)}d6"
    round_num = game.get("round", 1)
    state = game["state"]

    p1_anon = get_anon_id(p1) if p1 else "Анон"
    p2_anon = get_anon_id(p2) if p2 else "Анон"

    if state == "pending":
        rem = max(0, int(game["turn_deadline_ts"] - time.time()))
        target_str = f"Анону <code>[ID:{get_anon_id(game['target_id'])}]</code>" if game.get("target_id") else "Любому желающему анону"
        return (
            f"🎲 <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ({mode})</b>\n\n"
            f"👤 <b>Создатель:</b> Анон <code>[ID:{p1_anon}]</code>\n"
            f"🎯 <b>Кому:</b> {target_str}\n"
            f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code> | <b>Банк:</b> <code>{bet*2:,} ₪</code>\n"
            f"⏳ <b>Время на принятие:</b> <code>{rem}с</code>\n\n"
            f"<i>Жми кнопку ниже или напиши <code>/dice accept</code> в ответ на это сообщение!</i>"
        )

    p1_rolls = game["p1_rolls"].get(round_num)
    p2_rolls = game["p2_rolls"].get(round_num)

    p1_status = format_dice_visual(p1_rolls) if p1_rolls else "⏳ <i>Ожидает броска...</i>"
    p2_status = format_dice_visual(p2_rolls) if p2_rolls else "⏳ <i>Ожидает броска...</i>"

    turn_user = game.get("current_turn")
    turn_anon = get_anon_id(turn_user) if turn_user else "???"
    turn_rem = max(0, int(game["turn_deadline_ts"] - time.time()))

    header = f"🎲 <b>PvP ДАЙС-ДУЭЛЬ ({mode}) — РАУНД {round_num}</b>\n\n"
    body = (
        f"💰 <b>Банк:</b> <code>{bet*2:,} ₪</code> (Ставка: <code>{bet:,} ₪</code>)\n\n"
        f"🔴 <b>Игрок 1 [ID:{p1_anon}]:</b> {p1_status}\n"
        f"🔵 <b>Игрок 2 [ID:{p2_anon}]:</b> {p2_status}\n\n"
    )

    if game.get("finished"):
        outcome = game.get("outcome")
        if outcome == "draw":
            footer = f"🤝 <b>Игра завершена вничью!</b> Ставки возвращены."
        else:
            w = game.get("winner")
            w_anon = get_anon_id(w) if w else "???"
            payout = game.get("payout", 0)
            footer = f"👑 <b>Победитель: Анон [ID:{w_anon}]!</b> Забрал <code>+{payout:,} ₪</code>!"
    else:
        footer = (
            f"👉 <b>Сейчас бросает:</b> Анон <code>[ID:{turn_anon}]</code>\n"
            f"⏱️ <b>Таймер на бросок:</b> <code>{turn_rem}с</code>\n\n"
            f"<i>Нажми кнопку «🎲 Бросить кости!» ниже, чтобы бросить кубики.</i>"
        )

    return header + body + footer


async def safe_edit_dice_message(
    bot: Any,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """
    Safely edits a Telegram message: tries edit_message_text first (which satisfies
    standard unit tests mocking edit_message_text). If it fails with 'there is no text'
    or caption error, falls back to edit_message_caption for photo/video banners.
    Silently ignores 'message is not modified', catches TelegramRetryAfter and network errors.
    """
    if not bot or not chat_id or not message_id:
        return False
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return True
    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        if "there is no text" in err_str or "message to edit not found" in err_str or "caption" in err_str:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                return True
            except TelegramBadRequest as e2:
                if "message is not modified" in str(e2).lower():
                    return True
                shared_state.runtime_logger.debug(f"[DiceDuel] safe_edit caption failed for {chat_id}/{message_id}: {e2}")
            except Exception as e2:
                shared_state.runtime_logger.debug(f"[DiceDuel] safe_edit caption error for {chat_id}/{message_id}: {e2}")
        else:
            shared_state.runtime_logger.debug(f"[DiceDuel] safe_edit text failed for {chat_id}/{message_id}: {e}")
    except TelegramRetryAfter as e:
        shared_state.runtime_logger.warning(f"[DiceDuel] Flood control hit: retry after {e.retry_after}s")
    except Exception as e:
        shared_state.runtime_logger.debug(f"[DiceDuel] safe_edit unexpected error for {chat_id}/{message_id}: {e}")
    return False


async def safe_edit_callback_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """Safely edits the message associated with a CallbackQuery."""
    if not callback or not callback.message:
        return False
    return await safe_edit_dice_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=text,
        reply_markup=reply_markup
    )


async def start_active_dice_game_screens(
    bot: Any,
    game: Dict[str, Any],
    opponent_chat_id: Optional[int] = None,
    opponent_msg_id: Optional[int] = None
) -> None:
    """
    Transitions Dice Duel game to active playing state:
    1. Neutralizes old challenge cards for spectators: 'ВЫЗОВ ПРИНЯТ'.
    2. Neutralizes old challenge cards for both players: 'ДАЙС-ДУЭЛЬ НАЧАЛАСЬ, листайте вниз'.
    3. Sends a FRESH interactive game banner to the bottom of the chat for BOTH players.
    4. Records new message IDs in game['player_msgs'].
    """
    from banner_manager import send_banner_message

    p1 = game.get("player_1")
    p2 = game.get("player_2")
    if not p1 or not p2:
        return

    player_msgs = game.setdefault("player_msgs", {})
    broadcast_msgs = game.setdefault("broadcast_msgs", [])

    # Identify old message locations
    p1_old = player_msgs.get(p1) or ((game["chat_id"], game["msg_id"]) if game.get("chat_id") and game.get("msg_id") else None)
    p2_old = (opponent_chat_id, opponent_msg_id) if opponent_chat_id and opponent_msg_id else player_msgs.get(p2)

    anon_1 = get_anon_id(p1)
    anon_2 = get_anon_id(p2)

    # 1. Neutralize broadcast messages for spectators
    if broadcast_msgs:
        spectator_text = (
            f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: ВЫЗОВ ПРИНЯТ!</b>\n\n"
            f"Дуэль на <code>{game.get('bet', 0):,} ₪</code> уже началась между Аноном [{anon_1}] и Аноном [{anon_2}].\n"
            f"Мест за столом больше нет."
        )
        for chat_id, msg_id in list(broadcast_msgs):
            if p1_old and (chat_id, msg_id) == p1_old:
                continue
            if p2_old and (chat_id, msg_id) == p2_old:
                continue
            await safe_edit_dice_message(bot, chat_id, msg_id, spectator_text, reply_markup=None)
        game["broadcast_msgs"] = []

    # 2. Update players' old challenge messages so they know to look at the new message below
    player_old_text = "🎲 <b>ДАЙС-ДУЭЛЬ НАЧАЛАСЬ!</b>\n\nСвежие кости отправлены новым сообщением вниз чата ⬇️"
    if p1_old:
        await safe_edit_dice_message(bot, p1_old[0], p1_old[1], player_old_text, reply_markup=None)
    if p2_old and p2_old != p1_old:
        await safe_edit_dice_message(bot, p2_old[0], p2_old[1], player_old_text, reply_markup=None)

    # 3. Send new fresh banner message(s) to the bottom of the chat
    game_text = format_dice_game_message(game)
    game_id = game.get("game_id", "")
    current_turn = game.get("current_turn")
    turn_anon = get_anon_id(current_turn) if current_turn else None

    # If both players are in the same chat (e.g. group):
    if p1_old and p2_old and p1_old[0] == p2_old[0]:
        target_chat = p1_old[0]
        kb = get_dice_roll_keyboard(game_id, is_my_turn=True, is_shared_chat=True, turn_anon=turn_anon)
        sent_msg = await send_banner_message(
            bot=bot,
            chat_id=target_chat,
            caption=game_text,
            reply_markup=kb,
            category="dice",
            parse_mode="HTML"
        )
        if not sent_msg:
            try:
                sent_msg = await bot.send_message(
                    chat_id=target_chat,
                    text=game_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        if sent_msg:
            player_msgs[p1] = (target_chat, sent_msg.message_id)
            player_msgs[p2] = (target_chat, sent_msg.message_id)
            game["chat_id"] = target_chat
            game["msg_id"] = sent_msg.message_id
    else:
        # Separate direct chats (DMs)
        # P1
        kb_p1 = get_dice_roll_keyboard(game_id, is_my_turn=(p1 == current_turn))
        sent_p1 = await send_banner_message(
            bot=bot,
            chat_id=p1,
            caption=game_text,
            reply_markup=kb_p1,
            category="dice",
            parse_mode="HTML"
        )
        if not sent_p1:
            try:
                sent_p1 = await bot.send_message(
                    chat_id=p1,
                    text=game_text,
                    reply_markup=kb_p1,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        if sent_p1:
            player_msgs[p1] = (p1, sent_p1.message_id)

        # P2
        kb_p2 = get_dice_roll_keyboard(game_id, is_my_turn=(p2 == current_turn))
        sent_p2 = await send_banner_message(
            bot=bot,
            chat_id=p2,
            caption=game_text,
            reply_markup=kb_p2,
            category="dice",
            parse_mode="HTML"
        )
        if not sent_p2:
            try:
                sent_p2 = await bot.send_message(
                    chat_id=p2,
                    text=game_text,
                    reply_markup=kb_p2,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        if sent_p2:
            player_msgs[p2] = (p2, sent_p2.message_id)


async def sync_dice_screens(bot: Any, game: Dict[str, Any]):
    """
    Simultaneously edits active game messages for BOTH players in their personal chats,
    ensuring each player gets the updated roll statuses, turn indicator, and appropriate buttons.
    Avoids duplicate edits when both players are in the same chat.
    Also clears buttons for third-party broadcast viewers when challenge is accepted or finished.
    """
    if not bot or not game:
        return

    p1 = game.get("player_1")
    p2 = game.get("player_2")
    game_id = game.get("game_id", "")
    player_msgs = game.setdefault("player_msgs", {})
    broadcast_msgs = game.setdefault("broadcast_msgs", [])

    # Fallback for p1
    if p1 and p1 not in player_msgs and game.get("chat_id") and game.get("msg_id"):
        player_msgs[p1] = (game["chat_id"], game["msg_id"])

    rendered_text = format_dice_game_message(game)
    is_finished = game.get("finished", False) or game.get("state") in ("finished", "expired", "cancelled")
    current_turn = game.get("current_turn")

    is_shared = False
    if p1 in player_msgs and p2 in player_msgs:
        is_shared = (player_msgs[p1][0] == player_msgs[p2][0])

    turn_anon = get_anon_id(current_turn) if current_turn else None

    # 1. Update active players' messages without duplicate edits for same location
    updated_locations = set()
    for uid in (p1, p2):
        if not uid or uid not in player_msgs:
            continue
        loc = player_msgs[uid]
        if loc in updated_locations:
            continue
        updated_locations.add(loc)
        chat_id, msg_id = loc
        if is_finished:
            kb = get_dice_finished_keyboard(game_id, game.get("bet", 0))
        else:
            is_turn = (uid == current_turn)
            kb = get_dice_roll_keyboard(
                game_id,
                is_my_turn=is_turn,
                is_shared_chat=is_shared,
                turn_anon=turn_anon
            )

        await safe_edit_dice_message(bot, chat_id, msg_id, rendered_text, kb)

    # 2. If game started or finished, neutralize other broadcast copies
    if p2 and broadcast_msgs:
        anon_1 = get_anon_id(p1)
        anon_2 = get_anon_id(p2)
        other_text = (
            f"🎲 <b>PvP ДАЙС-ДУЭЛЬ: ВЫЗОВ ПРИНЯТ!</b>\n\n"
            f"Дуэль на <code>{game.get('bet', 0):,} ₪</code> уже началась между Аноном [{anon_1}] и Аноном [{anon_2}].\n"
            f"Мест за столом больше нет."
        )
        remaining_bcast = []
        for chat_id, msg_id in list(broadcast_msgs):
            if any((chat_id, msg_id) == player_msgs.get(p) for p in (p1, p2) if p in player_msgs):
                remaining_bcast.append((chat_id, msg_id))
                continue
            await safe_edit_dice_message(bot, chat_id, msg_id, other_text, reply_markup=None)
        game["broadcast_msgs"] = remaining_bcast


# -----------------------------------------------------------------------------
# Background Watchdog & Live Dynamic Updates for Dice Duel
# -----------------------------------------------------------------------------
async def dice_watchdog_step(bot=None):
    """
    Single iteration step of background watchdog checking expired dice turns,
    updating live countdowns dynamically, and cleaning expired challenges.
    """
    now = time.time()
    expired_games = []
    expired_pending = []
    live_tick_games = []

    async with dice_engine_lock:
        for gid, game in list(active_dice_games.items()):
            if game.get("finished") or game.get("state") in ("finished", "expired", "cancelled"):
                fin_ts = game.get("finished_ts")
                if fin_ts is None:
                    game["finished_ts"] = now
                elif now - fin_ts > 60:
                    active_dice_games.pop(gid, None)
                continue
            if game["state"] in ("playing", "rolling"):
                if now > game["turn_deadline_ts"]:
                    expired_games.append(gid)
                else:
                    # Live countdown auto-update every 15 seconds (prevents Telegram flood rate limit)
                    last_tick = game.get("last_tick_ts", game["turn_deadline_ts"] - DICE_TURN_TIMEOUT_SEC)
                    if now - last_tick >= 15.0:
                        game["last_tick_ts"] = now
                        live_tick_games.append(gid)
            elif game["state"] == "pending":
                if now > (game["created_ts"] + DICE_CHALLENGE_TIMEOUT_SEC):
                    # Expire unaccepted challenge
                    game["finished"] = True
                    game["state"] = "expired"
                    game["finished_ts"] = now
                    ch_id = game["player_1"]
                    user_active_dice_game.pop(ch_id, None)
                    if game.get("target_id"):
                        user_active_dice_game.pop(game["target_id"], None)
                    expired_pending.append(gid)

    # 1. Live countdown updates (playing)
    for gid in live_tick_games:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game or game.get("finished"):
                continue

        if bot and game:
            if game["state"] in ("playing", "rolling"):
                await sync_dice_screens(bot, game)
            else:
                updated_text = format_dice_game_message(game)
                kb = get_dice_challenge_keyboard(gid)
                bcast_list = list(game.get("broadcast_msgs", []))
                if not bcast_list and game.get("chat_id") and game.get("msg_id"):
                    bcast_list = [(game["chat_id"], game["msg_id"])]
                for chat_id, msg_id in bcast_list:
                    await safe_edit_dice_message(bot, chat_id, msg_id, updated_text, kb)

    # 2. Expired turn games (timeout forfeit)
    for gid in expired_games:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game or game.get("finished"):
                continue
            loser_id = game.get("current_turn")
            winner_id = game["player_2"] if loser_id == game["player_1"] else game["player_1"]

        await _finish_dice_game(gid, winner_id, loser_id, "timeout", bot)

    # 3. Expired pending challenges
    for gid in expired_pending:
        async with dice_engine_lock:
            game = active_dice_games.get(gid)
            if not game:
                continue
            p1 = game.get("player_1")
            bet = game.get("bet", 0)
            bcast_list = list(game.get("broadcast_msgs", []))
            if not bcast_list and game.get("chat_id") and game.get("msg_id"):
                bcast_list = [(game["chat_id"], game["msg_id"])]

        if bot and p1:
            exp_dm_text = (
                f"⏳ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ИСТЕК</b>\n\n"
                f"Ни один анон не принял твой вызов на дуэль в кости (<b>{bet:,} ₪</b>) за 10 минут.\n"
                f"Вызов аннулирован, ставка не списывалась."
            )
            spawn_task(send_pvp_direct_notification(bot, p1, exp_dm_text), name="pvp_notify_dice_expired")

        if bot and bcast_list:
            exp_text = (
                "⏳ <b>ВЫЗОВ НА PvP ДАЙС-ДУЭЛЬ ИСТЕК!</b>\n\n"
                "Ни один анон не принял вызов на кости за 10 минут.\n"
                "Вызов аннулирован, ставка не списана."
            )
            for chat_id, msg_id in bcast_list:
                await safe_edit_dice_message(bot, chat_id, msg_id, exp_text, reply_markup=None)


async def start_dice_watchdog_loop(bot):
    """
    Continuous background watchdog loop for Dice Duel timeouts and live countdowns.
    """
    shared_state.runtime_logger.info("Dice Duel PvP watchdog loop started.")
    while True:
        try:
            await dice_watchdog_step(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            shared_state.runtime_logger.error(f"Error in dice_watchdog_loop: {e}")
        await asyncio.sleep(2.5)


# -----------------------------------------------------------------------------
# Aiogram Handlers & Command Router Registration
# -----------------------------------------------------------------------------
router = Router(name="dice_duel_router")

def register_dice_duel_handlers(dp: Any):
    """
    Registers all commands, shortcuts, and callback query handlers into aiogram dispatcher.
    """
    global cmd_dice_duel_entry, cmd_dice_duel

    @dp.message(F.text.regexp(r"^/(?:dice|diceduel|кости|дайсы)(\d+[kк]?|all|всё|все)(?:\s+.*)?$", flags=re.IGNORECASE))
    async def cmd_dice_duel_shorthand(message: Message, board_id: str | None = None, stream: str = 'ru'):
        if not message.text:
            return
        m = re.match(r"^/(?:dice|diceduel|кости|дайсы)(\d+[kк]?|all|всё|все)(?:\s+(.*))?$", message.text.strip(), re.IGNORECASE)
        if not m:
            return
        amt = m.group(1)
        rest = m.group(2)
        message.text = f"/dice {amt}" + (f" {rest}" if rest else "")
        return await cmd_dice_duel_entry(message, board_id=board_id, stream=stream)

    @dp.message(Command("dice", "dice_duel", "diceduel", "дайс_дуэль", "кости_дуэль", "дайсдуэль", "костидуэль", "dices", "дайс", "дайсы", "кости", ignore_case=True, ignore_mention=True))
    async def cmd_dice_duel_entry(message: Message, board_id: str | None = None, stream: str = 'ru'):
        if not board_id:
            board_id = getattr(message.chat, 'id', 'b')
            board_id = str(board_id)

        user_id = message.from_user.id
        raw_text = message.text or message.caption or ""
        tokens = raw_text.strip().split()

        # Check for subcommands: /dice accept, /dice decline, /dice cancel
        if len(tokens) > 1:
            sub = tokens[1].lower()
            if sub in ("accept", "принять", "+", "yes", "ок"):
                await handle_dice_accept_command(message, board_id)
                return
            if sub in ("decline", "отклонить", "cancel", "отмена", "-"):
                await handle_dice_cancel_command(message, board_id)
                return

        # Parse stake amount
        bet_amount = None
        target_user_id = None

        if message.reply_to_message:
            try:
                from common.bot_helpers import get_author_id_by_reply
                target_user_id = await get_author_id_by_reply(message)
            except Exception:
                target_user_id = message.reply_to_message.from_user.id if (message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot) else None
            if target_user_id == user_id or target_user_id == 0:
                target_user_id = None

        db = await get_pool()
        from common.database import is_shadow_muted as check_db_shadow_muted
        from common.bot_helpers import check_user_is_muted
        if await check_db_shadow_muted(user_id, board_id, db=db) or await check_user_is_muted(db, user_id, board_id):
            await message.answer("🔇 Замученным нельзя играть в дайс-дуэли.")
            return

        async with db_lock:
            user_bal = await get_user_global_balance(db, user_id)

        if len(tokens) > 1:
            arg = tokens[1].lower().strip().replace(" ", "").replace(",", ".")
            for suffix in ["₪", "шекелей", "шекеля", "шекель", "рублей", "рубля", "руб", "р", "rub", "$", "usd"]:
                if arg.endswith(suffix):
                    arg = arg[:-len(suffix)].strip()
                    break

            if arg in ("all", "вабанк", "ва-банк", "всё", "все", "макс", "max"):
                bet_amount = int(user_bal)
            else:
                multiplier = 1
                if arg.endswith(("kk", "кк")):
                    multiplier = 1_000_000
                    arg = arg[:-2]
                elif arg.endswith(("k", "к")):
                    multiplier = 1_000
                    arg = arg[:-1]
                elif arg.endswith(("m", "м")):
                    multiplier = 1_000_000
                    arg = arg[:-1]

                try:
                    val = float(arg) * multiplier
                    if not math.isnan(val) and not math.isinf(val) and val > 0:
                        bet_amount = int(val)
                except Exception:
                    pass

        if bet_amount is None:
            # Show interactive lobby menu
            default_bet = 100 if user_bal >= 100 else (50 if user_bal >= 50 else MIN_DICE_BET)
            lobby_kb = get_dice_lobby_keyboard(balance=int(user_bal), current_bet=default_bet, target_id=target_user_id or 0)
            target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{target_user_id}]</code>\n" if target_user_id else ""
            await message.answer(
                f"🎲 <b>PvP КОСТИ / ДАЙС-ДУЭЛЬ НА ШЕКЕЛИ</b>\n\n"
                f"💰 <b>Твой баланс:</b> <code>{int(user_bal):,} ₪</code>\n"
                f"💰 <b>Ставка:</b> <code>{default_bet:,} ₪</code>\n"
                f"{target_str}\n"
                f"Правила честной игры:\n"
                f"• Бросаем 2d6 (или 3d6) на честном генераторе с визуалом костей (⚀ ⚁ ⚂ ⚃ ⚄ ⚅).\n"
                f"• Побеждает тот, у кого сумма очков выше. При ничьей — переброс!\n"
                f"• Победитель забирает банк за вычетом 5% налога Абу.\n\n"
                f"<b>Команды:</b>\n"
                f"• <code>/dice &lt;ставка&gt;</code> — Бросить вызов всем в треде\n"
                f"• <code>/dice 500</code> (ответом на пост) — Вызвать конкретного анона\n"
                f"• <code>/dice accept</code> — Принять вызов",
                reply_markup=lobby_kb,
                parse_mode="HTML"
            )
            return

        ok, err_or_msg, game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet_amount,
            target_id=target_user_id,
            num_dice=2
        )

        if not ok:
            await message.answer(err_or_msg, parse_mode="HTML")
            return

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                return
            msg_text = format_dice_game_message(game)
            kb = get_dice_challenge_keyboard(game_id)

        sent_msg = await message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
        async with dice_engine_lock:
            if game_id in active_dice_games:
                g = active_dice_games[game_id]
                g["msg_id"] = sent_msg.message_id
                g["chat_id"] = sent_msg.chat.id
                g.setdefault("player_msgs", {})[user_id] = (sent_msg.chat.id, sent_msg.message_id)
                g.setdefault("broadcast_msgs", []).append((sent_msg.chat.id, sent_msg.message_id))

        # Рассылаем карточку активным юзерам борда (throttled background task)
        async def _do_broadcast():
            try:
                from shared_state import board_data as _board_data
                from banner_manager import broadcast_banner_to_users
                active_users = list(_board_data.get(board_id, {}).get('users', {}).get('active', []))
                if target_user_id is not None:
                    active_users = [uid for uid in active_users if uid == target_user_id]
                async def _on_sent(uid, mid):
                    async with dice_engine_lock:
                        if game_id in active_dice_games:
                            active_dice_games[game_id]["broadcast_msgs"].append((uid, mid))
                await broadcast_banner_to_users(
                    bot=message.bot,
                    user_ids=active_users,
                    exclude_uid=user_id,
                    caption=msg_text,
                    reply_markup=kb,
                    category="games",
                    parse_mode="HTML",
                    on_sent=_on_sent,
                )
            except Exception:
                pass
        import asyncio
        asyncio.create_task(_do_broadcast())

    async def handle_dice_accept_command(message: Message, board_id: str):
        user_id = message.from_user.id
        found_gid = None

        # If replying to a challenge message
        async with dice_engine_lock:
            if message.reply_to_message:
                reply_mid = message.reply_to_message.message_id
                for gid, g in active_dice_games.items():
                    if g.get("msg_id") == reply_mid and g.get("state") == "pending":
                        found_gid = gid
                        break

            if not found_gid:
                # Find any open pending challenge for this board
                for gid, g in active_dice_games.items():
                    if g.get("board_id") == board_id and g.get("state") == "pending":
                        if g.get("player_1") != user_id and (not g.get("target_id") or g.get("target_id") == user_id):
                            found_gid = gid
                            break

        if not found_gid:
            await message.answer("❌ Нет активных вызовов на кости для принятия!", parse_mode="HTML")
            return

        ok, msg_text, game = await accept_dice_challenge(found_gid, user_id)
        if not ok:
            await message.answer(msg_text, parse_mode="HTML")
            return

        opp_msg_id = message.reply_to_message.message_id if message.reply_to_message else None
        await start_active_dice_game_screens(
            bot=message.bot,
            game=game,
            opponent_chat_id=message.chat.id,
            opponent_msg_id=opp_msg_id
        )

    async def handle_dice_cancel_command(message: Message, board_id: str):
        user_id = message.from_user.id
        found_gid = user_active_dice_game.get(user_id)
        if not found_gid:
            await message.answer("❌ У тебя нет активных созданных вызовов.", parse_mode="HTML")
            return

        ok, msg = await cancel_dice_challenge(found_gid, user_id)
        await message.answer(msg, parse_mode="HTML")

    # -------------------------------------------------------------------------
    # Callbacks Handlers
    # -------------------------------------------------------------------------
    @dp.callback_query(F.data.startswith("dice_accept:"))
    async def cb_dice_accept(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        ok, msg_text, game = await accept_dice_challenge(game_id, user_id)
        if not ok:
            shared_state.runtime_logger.warning(
                f"[DiceDuel] accept FAILED gid={game_id} uid={user_id}: {msg_text}"
            )
            await callback.answer(msg_text, show_alert=True)
            return

        opp_chat_id = callback.message.chat.id if callback.message else None
        opp_msg_id = callback.message.message_id if callback.message else None
        await start_active_dice_game_screens(
            bot=callback.bot,
            game=game,
            opponent_chat_id=opp_chat_id,
            opponent_msg_id=opp_msg_id
        )
        await callback.answer("⚔️ Вызов принят! Свежие кости отправлены вниз чата ⬇️")

    @dp.callback_query(F.data.startswith("dice_decline:") | F.data.startswith("dice_cancel:"))
    async def cb_dice_decline(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                await callback.answer("❌ Игра уже неактивна.", show_alert=True)
                return

            if user_id != game["player_1"] and (not game.get("target_id") or user_id != game.get("target_id")):
                await callback.answer("❌ Ты не можешь отменить чужой вызов!", show_alert=True)
                return
            bcast_list = list(game.get("broadcast_msgs", []))

        ok, msg = await cancel_dice_challenge(game_id, user_id, bot=callback.bot)
        cancel_text = "🗑 <b>Вызов на кости отменен.</b>"
        await safe_edit_callback_message(callback, cancel_text, reply_markup=None)
        for chat_id, msg_id in bcast_list:
            if callback.message and chat_id == callback.message.chat.id and msg_id == callback.message.message_id:
                continue
            await safe_edit_dice_message(callback.bot, chat_id, msg_id, cancel_text, reply_markup=None)
        await callback.answer(msg)

    @dp.callback_query(F.data.startswith("dice_wait:"))
    async def cb_dice_wait(callback: CallbackQuery):
        await callback.answer("⏳ Сейчас ход соперника! Жди пока он бросит кости.", show_alert=False)

    @dp.callback_query(F.data.startswith("dice_roll:"))
    async def cb_dice_roll(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                await callback.answer("❌ Игра не найдена.", show_alert=True)
                return
            if game.get("finished"):
                await callback.answer("❌ Игра уже завершена.", show_alert=True)
                return
            if game.get("state") != "playing":
                if game.get("state") == "rolling":
                    await callback.answer("⏳ Кости уже бросаются...", show_alert=False)
                elif game.get("state") == "resolving":
                    await callback.answer("⏳ Раунд завершается...", show_alert=False)
                else:
                    await callback.answer("❌ Сейчас нельзя бросить кости.", show_alert=True)
                return
            if user_id not in (game["player_1"], game["player_2"]):
                await callback.answer("❌ Ты не участвуешь в этой дуэли!", show_alert=True)
                return
            if user_id != game.get("current_turn"):
                await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
                return

            # Atomically lock this roll by transitioning to rolling
            game["state"] = "rolling"

        # Visual roll animation frames
        anim_frames = ["🎲 <i>Трясем стакан с костями...</i>", "🌀 <i>Кости крутятся на сукне...</i>"]
        for f_text in anim_frames:
            try:
                await callback.message.edit_text(
                    format_dice_game_message(game) + f"\n\n{f_text}",
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.4)
            except Exception:
                pass

        ok, msg_text, updated_game = await execute_player_roll(game_id, user_id, callback.bot)
        if not ok:
            await callback.answer(msg_text, show_alert=True)
            return

        await callback.answer("🎲 Бросок сделан!")
        await sync_dice_screens(callback.bot, updated_game)

    @dp.callback_query(F.data.startswith("dice_surrender:"))
    async def cb_dice_surrender(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game or game.get("finished"):
                await callback.answer("❌ Игра уже завершена.", show_alert=True)
                return
            if user_id not in (game["player_1"], game["player_2"]):
                await callback.answer("❌ Ты не игрок этой партии.", show_alert=True)
                return

            winner_id = game["player_2"] if user_id == game["player_1"] else game["player_1"]

        ok, msg, res_game = await _finish_dice_game(game_id, winner_id, user_id, "surrender", callback.bot)
        if not ok:
            await callback.answer("❌ Игра уже завершена.", show_alert=True)
            return

        await callback.answer("🏳️ Ты сдался.")

    @dp.callback_query(F.data.startswith("dice_refresh:"))
    async def cb_dice_refresh(callback: CallbackQuery):
        """Refreshes remaining turn time and dice duel status."""
        game_id = callback.data.split(":", 1)[1]
        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
        if not game:
            await callback.answer("Дуэль завершена", show_alert=False)
            return

        p1 = game.get("player_1")
        p2 = game.get("player_2")
        p_msgs = game.get("player_msgs", {})
        is_shared = False
        if p1 in p_msgs and p2 in p_msgs:
            is_shared = (p_msgs[p1][0] == p_msgs[p2][0])

        current_turn = game.get("current_turn")
        turn_anon = get_anon_id(current_turn) if current_turn else None
        is_my_turn = (callback.from_user.id == current_turn)

        is_finished = game.get("finished", False) or game.get("state") in ("finished", "expired", "cancelled")
        if is_finished:
            kb = get_dice_finished_keyboard(game_id, game.get("bet", 0))
        else:
            kb = get_dice_roll_keyboard(
                game_id,
                is_my_turn=is_my_turn,
                is_shared_chat=is_shared,
                turn_anon=turn_anon
            )

        await safe_edit_callback_message(
            callback,
            text=format_dice_game_message(game),
            reply_markup=kb
        )
        rem = max(0, int(game.get("turn_deadline_ts", 0) - time.time()))
        turn_str = "Твой ход!" if is_my_turn else f"Ход: [{turn_anon}]"
        await callback.answer(f"⏳ Осталось: {rem}с ({turn_str})", show_alert=False)

    @dp.callback_query(F.data.startswith("dice_rematch:"))
    async def cb_dice_rematch(callback: CallbackQuery):
        game_id = callback.data.split(":", 1)[1]
        user_id = callback.from_user.id

        async with dice_engine_lock:
            old_game = active_dice_games.get(game_id)
            if not old_game:
                await callback.answer("❌ Данные прошлой дуэли не найдены.", show_alert=True)
                return

            if user_id not in (old_game["player_1"], old_game.get("player_2")):
                await callback.answer("❌ Ты не участвовал в этой дуэли!", show_alert=True)
                return

            bet = old_game["bet"]
            num_dice = old_game.get("num_dice", 2)
            board_id = old_game["board_id"]
            other_player = old_game["player_2"] if user_id == old_game["player_1"] else old_game["player_1"]

        ok, err_or_msg, new_game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet,
            target_id=other_player,
            num_dice=num_dice
        )
        if not ok:
            await callback.answer(err_or_msg, show_alert=True)
            return

        await callback.answer("⚔️ Вызов на реванш создан!")
        async with dice_engine_lock:
            new_game = active_dice_games.get(new_game_id)
            if not new_game:
                return
            msg_text = format_dice_game_message(new_game)
            kb = get_dice_challenge_keyboard(new_game_id)

        try:
            sent_msg = await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            async with dice_engine_lock:
                if new_game_id in active_dice_games:
                    g = active_dice_games[new_game_id]
                    g["msg_id"] = sent_msg.message_id
                    g["chat_id"] = sent_msg.chat.id
                    g.setdefault("player_msgs", {})[user_id] = (sent_msg.chat.id, sent_msg.message_id)
                    g.setdefault("broadcast_msgs", []).append((sent_msg.chat.id, sent_msg.message_id))
            if other_player:
                try:
                    bcast_sent = await callback.bot.send_message(
                        chat_id=other_player,
                        text=msg_text,
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                    async with dice_engine_lock:
                        if new_game_id in active_dice_games:
                            active_dice_games[new_game_id].setdefault("broadcast_msgs", []).append((other_player, bcast_sent.message_id))
                except Exception:
                    pass
        except Exception:
            pass

    @dp.callback_query(F.data.startswith("dice_lobby_bet:"))
    async def cb_dice_lobby_bet(callback: CallbackQuery):
        # Format: dice_lobby_bet:<bet>:<target_id>
        parts = callback.data.split(":")
        bet = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) > 0 else 0
        user_id = callback.from_user.id

        db = await get_pool()
        async with db_lock:
            user_bal = await get_user_global_balance(db, user_id)

        bet = max(MIN_DICE_BET, min(MAX_DICE_BET, min(int(user_bal), bet) if user_bal >= MIN_DICE_BET else MIN_DICE_BET))
        lobby_kb = get_dice_lobby_keyboard(balance=int(user_bal), current_bet=bet, target_id=target_id)
        target_str = f"🎯 <b>Цель:</b> Анон <code>[ID:{target_id}]</code>\n" if target_id else ""
        try:
            await callback.message.edit_text(
                f"🎲 <b>PvP КОСТИ / ДАЙС-ДУЭЛЬ НА ШЕКЕЛИ</b>\n\n"
                f"💳 <b>Твой баланс:</b> <code>{int(user_bal):,} ₪</code>\n"
                f"💰 <b>Ставка:</b> <code>{bet:,} ₪</code>\n"
                f"{target_str}\n"
                f"Выбери ставку и режим броска:",
                reply_markup=lobby_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
        try: await callback.answer()
        except Exception: pass

    @dp.callback_query(F.data.startswith("dice_create_fast:"))
    async def cb_dice_create_fast(callback: CallbackQuery):
        # Format: dice_create_fast:<mode>:<bet>:<target_id>
        parts = callback.data.split(":")
        mode_str = parts[1] if len(parts) > 1 else "2d6"
        num_dice = 3 if mode_str == "3d6" else 2
        bet = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
        target_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() and int(parts[3]) > 0 else None
        user_id = callback.from_user.id
        board_id = getattr(callback.message.chat, 'id', 'b')
        board_id = str(board_id)

        ok, err_or_msg, game_id = await create_dice_challenge(
            board_id=board_id,
            challenger_id=user_id,
            bet=bet,
            target_id=target_id,
            num_dice=num_dice
        )
        if not ok:
            await callback.answer(err_or_msg, show_alert=True)
            return

        await callback.answer("✅ Вызов создан!")
        async with dice_engine_lock:
            game = active_dice_games.get(game_id)
            if not game:
                return
            msg_text = format_dice_game_message(game)
            kb = get_dice_challenge_keyboard(game_id)

        try:
            sent_msg = await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            async with dice_engine_lock:
                if game_id in active_dice_games:
                    g = active_dice_games[game_id]
                    g["msg_id"] = sent_msg.message_id
                    g["chat_id"] = sent_msg.chat.id
                    g.setdefault("player_msgs", {})[user_id] = (sent_msg.chat.id, sent_msg.message_id)
                    g.setdefault("broadcast_msgs", []).append((sent_msg.chat.id, sent_msg.message_id))

            # Рассылаем карточку активным юзерам борда (throttled background task)
            async def _do_broadcast():
                try:
                    from shared_state import board_data as _board_data
                    from banner_manager import broadcast_banner_to_users
                    active_users = list(_board_data.get(board_id, {}).get('users', {}).get('active', []))
                    if target_id is not None:
                        active_users = [uid for uid in active_users if uid == target_id]
                    async def _on_sent(uid, mid):
                        async with dice_engine_lock:
                            if game_id in active_dice_games:
                                active_dice_games[game_id].setdefault("broadcast_msgs", []).append((uid, mid))
                    await broadcast_banner_to_users(
                        bot=callback.bot,
                        user_ids=active_users,
                        exclude_uid=user_id,
                        caption=msg_text,
                        reply_markup=kb,
                        category="games",
                        parse_mode="HTML",
                        on_sent=_on_sent,
                    )
                except Exception:
                    pass
            import asyncio
            asyncio.create_task(_do_broadcast())
        except Exception:
            pass

# Auto-register handlers into module-level router
register_dice_duel_handlers(router)
