# -*- coding: utf-8 -*-
"""
votemute_engine.py — Democratic Vote-Mute Engine (Народный Вотум / Шизо-Мут) for ТГАЧ
===================================================================================
Allows community to vote-mute toxic spammers/waifu-wipers via 5 unique votes within 10 minutes.
Once passed, applies an UNBRIBABLE 30-minute iron mute that CANNOT be removed via shop bribes or regular un-mutes.

Key Features:
1. Commands: /votemute, /voteban, /вотум, /шизомут, /вотебан, /vm, /vb (reply or post number).
2. Deduplication: One active votemute per target on a board. Duplicate commands link/update active voting.
3. Persistent SQLite storage: Votemutes and VotemuteVotes tables survive bot restarts without losing state.
4. Interactive dual-choice buttons: [🔨 За: {yes_votes}/5] [🕊️ Против: {no_votes}].
5. Real-time visual synchronization: Updates all broadcast card copies across active users.
6. Upon reaching 5 votes — applies 30-minute IRON FOLK MUTE (ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ).
7. UNBRIBABLE FLAG (unbribable_votemute_until) — blocks bribes in /shop and admin unmutes.
8. Juicy public verdict broadcast to the whole board via process_new_post.
"""

import time
import asyncio
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any, Union, List

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from common.db_pool import get_pool, db_transaction, LazyLock
from common.anon_identity import get_anon_id
from common.bot_helpers import safe_callback_answer

logger = logging.getLogger("runtime")

VOTES_REQUIRED = 5
VOTE_WINDOW_SEC = 600.0  # 10 minutes voting window
MUTE_DURATION_SEC = 1800  # 30 minutes iron mute
UNBRIBABLE_FLAG_KEY = "unbribable_votemute_until"

UNBRIBABLE_MUTE_ERROR_TEXT = (
    "❌ <b>Этот мут наложен народом борды и не продается за взятки!</b>\n"
    "🔒 Воля анонов несокрушима. До окончания срока осталось <b>{minutes} мин.</b>"
)
ENABLE_VOTEMUTE_PM_BROADCAST: bool = False  # Disabled: prevent mass PM spam to all users on every votemute

# In-memory L1 cache for rapid token resolution and event dispatch
active_votemutes: Dict[str, Dict[str, Any]] = {}
votemute_lock = LazyLock()


async def ensure_votemute_tables(db=None) -> None:
    """Idempotently ensures Votemutes and VotemuteVotes tables and indices exist in SQLite."""
    if db is None:
        db = await get_pool()
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Votemutes (
        vote_id TEXT PRIMARY KEY,
        board_id TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        post_num INTEGER NOT NULL,
        initiator_id INTEGER NOT NULL,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        yes_votes INTEGER NOT NULL DEFAULT 1,
        no_votes INTEGER NOT NULL DEFAULT 0,
        required_votes INTEGER NOT NULL DEFAULT 5,
        card_chat_id INTEGER,
        card_message_id INTEGER,
        broadcast_msgs TEXT DEFAULT '[]'
    );
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS VotemuteVotes (
        vote_id TEXT NOT NULL,
        voter_id INTEGER NOT NULL,
        vote_type TEXT NOT NULL,
        voted_at REAL NOT NULL,
        PRIMARY KEY (vote_id, voter_id),
        FOREIGN KEY (vote_id) REFERENCES Votemutes(vote_id) ON DELETE CASCADE
    );
    """)
    try:
        await db.execute("CREATE INDEX IF NOT EXISTS idx_votemutes_target_status ON Votemutes(board_id, target_id, status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_votemutes_post_status ON Votemutes(post_num, status);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_votemute_votes_voter ON VotemuteVotes(voter_id);")
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Phrase Pools — публичные приговоры и отказы
# -----------------------------------------------------------------------------
VOTEMUTE_ANNOUNCEMENTS = [
    "⚖️ <b>НАРОДНЫЙ ПРИГОВОР ВЫНЕСЕН И ПРИВЕДЕН В ИСПОЛНЕНИЕ!</b>\n\n👨‍⚖️ По итогам Народного Вотума (5 голосов анонов) за пост <b>#{post_num}</b>:\n🤐 <b>Автор поста <b>#{post_num}</b></b> признан злостным шизо-вайпером и отправлен в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>!\n\n🔒 <i>Мут наложен волей народа борды: его НЕ СНЯТЬ взятками в /shop!</i>",
    "🔨 <b>МОЛОТ НАРОДНОГО ПРАВОСУДИЯ ОПУСТИЛСЯ!</b>\n\n📜 Пять анонов борды единогласно приговорили <b>Автора поста <b>#{post_num}</b></b> (пост <b>#{post_num}</b>) к <b>ЖЕЛЕЗНОМУ МОЛЧАНИЮ на 30 минут</b>!\n\n🔒 <i>Взятки не принимаются. Адвокаты не нужны. Касса закрыта.</i>",
    "🚨 <b>СИРЕНЫ БОРДЫ ВОЮТ — ШИЗ ИЗОЛИРОВАН!</b>\n\n🫵 Автор поста <b>#{post_num}</b> за пост <b>#{post_num}</b> набрал 5 голосов недоверия!\n🔒 <b>ПАРАША НА ЗАМКЕ. МУТ 30 МИНУТ. БЕСПОВОРОТНО.</b>\n\n<i>Бор-да сказала своё слово. Шиз — молчи.</i>",
    "🏛️ <b>НАРОДНЫЙ СУД БОРДЫ ЗАСЕДАНИЕ ЗАВЕРШЕНО!</b>\n\n⚖️ Подсудимый Автор поста <b>#{post_num}</b> признан ВИНОВНЫМ по статье «Злостный вайп треда» (пост #{post_num}).\n📋 <b>Приговор: 30 минут образцово-показательного молчания.</b>\n🔒 Приговор обжалованию не подлежит. Взятки не работают.",
    "🧟 <b>САНИТАРЫ ЗАФИКСИРОВАЛИ ПАЦИЕНТА!</b>\n\n🚑 Автор поста <b>#{post_num}</b> из поста <b>#{post_num}</b> признан общественно опасным. Пять санитаров провели фиксацию.\n😷 <b>Смирительная рубаха надета. Рот заклеен скотчем. 30 минут тишины.</b>\n<i>Галоперидол уже в системе.</i>",
    "⚖️ <b>ТРИБУНАЛ БОРДЫ ЗАКРЫТ НА ЗАМОК!</b>\n\n🔨 Автор поста <b>#{post_num}</b> (пост #{post_num}) признан виновным в злостном вайпе треда.\n🔒 <b>ПРИГОВОР ИСПОЛНЕН: ЖЕЛЕЗНЫЙ МУТ 30 МИНУТ.</b>\nПять голосов анонов решили судьбу треда — вотум состоялся!",
    "⚡ <b>ВАТНЫЙ/ШИЗОИДНЫЙ ПАРАЛИЧ АКТИВИРОВАН!</b>\n\n🔇 Автор поста <b>#{post_num}</b> за пост <b>#{post_num}</b> подвергся коллективному электрошоку от 5 анонов борды.\n💀 <b>Речевые центры отключены на 30 минут. Клавиатура заблокирована народом.</b>",
    "🐒 <b>АБУ ЛИЧНО ОДОБРИЛ ПРИГОВОР НАРОДА!</b>\n\n📜 Пять голосов анонов за пост <b>#{post_num}</b> и Автор поста <b>#{post_num}</b> идёт в ЖЕЛЕЗНЫЙ МУТ!\n💰 <b>Взятки Абу в данном случае не котируются. Народная воля превыше.</b>\n🔒 30 минут тишины. Вотум исполнен.",
    "🔗 <b>СЫЧА СПЕЛЕНАЛИ В СМИРИТЕЛЬНУЮ РУБАХУ!</b>\n\nПять усталых анонов объединились против Автора поста <b>#{post_num}</b> из поста <b>#{post_num}</b>.\n🏥 <b>Диагноз: хронический вайпер. Лечение: 30 минут ЖЕЛЕЗНОГО МОЛЧАНИЯ.</b>\n<i>Рецепт выписан. Галоперидол введён внутривенно.</i>",
    "🗡️ <b>ЛИНЧ СОСТОЯЛСЯ. ПРИГОВОР ИСПОЛНЕН.</b>\n\n🔥 Автор поста <b>#{post_num}</b> (пост #{post_num}) был публично осуждён пятью гражданами борды за злостный шизо-вайп!\n⚔️ <b>Казнь: 30 минут железного молчания без права на помилование.</b>\n<i>Труп убирать некому. Пусть лежит тихо.</i>",
    "📯 <b>ГЛАШАТАЙ БОРДЫ ОБЪЯВЛЯЕТ ПРИГОВОР!</b>\n\nОйе! Автор поста <b>#{post_num}</b> за пост <b>#{post_num}</b> осуждён народным вотумом (5/5 голосов)!\n🔒 <b>ЖЕЛЕЗНЫЙ МУТ НА 30 МИНУТ. ВЗЯТКИ НЕ ПРИНИМАЕМ. АПЕЛЛЯЦИЙ НЕТ.</b>",
    "🧊 <b>КРИОКАМЕРА ЗАПЕЧАТАНА!</b>\n\n❄️ Автор поста <b>#{post_num}</b> из поста <b>#{post_num}</b> заморожен волей народа борды на 30 минут.\n🔒 <b>Размораживание только после истечения срока. Взятки — в мусор.</b>\n<i>Нечего было вайпать тред, ублюдок.</i>",
    "🎪 <b>ЦИРК ЗАКРЫВАЕТСЯ — КЛОУН ИЗОЛИРОВАН!</b>\n\n🤡 Автор поста <b>#{post_num}</b> (пост #{post_num}) устроил несанкционированное шоу в треде. 5 анонов поддержали вотум.\n🎭 <b>Антракт 30 минут. Клоун в клетке. Взятки не работают.</b>",
    "💀 <b>РОТ ЗАТКНУТ НАРОДОМ БОРДЫ!</b>\n\n🗳️ Пять анонов выразили волю коллектива: Автор поста <b>#{post_num}</b> (пост #{post_num}) — злостный вайпер.\n🔒 <b>30 минут абсолютной тишины. ЖЕЛЕЗНЫЙ МУТ. Непродаваем.</b>",
    "🏴‍☠️ <b>ПИРАТСКИЙ ТРИБУНАЛ БОРДЫ ЗАСЕДАНИЕ ЗАВЕРШЕНО!</b>\n\n⚓ Автор поста <b>#{post_num}</b> за пост <b>#{post_num}</b> приговорён к хождению по доске!\n🌊 <b>30 минут в пучине молчания. Вотум исполнен. Выкуп не принимается.</b>",
    "🦠 <b>КАРАНТИН ОБЪЯВЛЕН. ИСТОЧНИК ЗАРАЗЫ ИЗОЛИРОВАН!</b>\n\n😷 Пять санитарных инспекторов борды признали Автора поста <b>#{post_num}</b> (пост #{post_num}) биологически опасным для треда.\n🔬 <b>КАРАНТИН 30 МИНУТ. ВАКЦИНЫ ОТ ВОТУМА НЕТ.</b>",
    "🎯 <b>ОХОТА УДАЛАСЬ — ЦЕЛЬ ПОРАЖЕНА!</b>\n\n🔫 Пять охотников борды вычислили и нейтрализовали вайпера Автора поста <b>#{post_num}</b> (пост #{post_num}).\n🏆 <b>Трофей: 30 минут тишины в треде. МУТ НЕОБРАТИМ.</b>",
    "⚗️ <b>АЛХИМИКИ БОРДЫ ПРЕВРАТИЛИ ВАЙПЕРА В МОЛЧАНИЕ!</b>\n\n🧪 Народный реагент (5 голосов) вступил в реакцию с Автором поста <b>#{post_num}</b> из поста <b>#{post_num}</b>.\n💥 <b>Результат реакции: 30 минут ЖЕЛЕЗНОГО МОЛЧАНИЯ. Антидота нет.</b>",
    "🔔 <b>НАБАТ! ВАЙПЕР ОБЕЗВРЕЖЕН!</b>\n\n📣 Колокола борды возвестили: Автор поста <b>#{post_num}</b> (пост #{post_num}) осуждён пятью голосами народа!\n⛪ <b>Приговор: 30 минут тишины. Исповедь не принимается. Взятки — ересь.</b>",
    "🚔 <b>МАЙОР ДОИГРАЛЕС ОДОБРЯЕТ АРЕСТ!</b>\n\n👮 По итогам гражданского вотума Автор поста <b>#{post_num}</b> (пост #{post_num}) задержан силами самоорганизации борды.\n🔒 <b>Срок: 30 минут административного молчания. Взятки переданы в Казну Абу. Смотри не шали.</b>",
    "🌋 <b>ВУЛКАН НАРОДНОГО ГНЕВА НАКРЫЛ ВАЙПЕРА!</b>\n\n🔥 Пять анонов не выдержали — вотум прошёл! Автор поста <b>#{post_num}</b> (пост #{post_num}) погребён под лавой народного правосудия.\n💀 <b>30 минут в пепле молчания. Воскрешение за взятки недоступно.</b>",
    "🗺️ <b>ИНКВИЗИЦИЯ БОРДЫ ВЫНЕСЛА ВЕРДИКТ!</b>\n\nПо доносу пяти праведных анонов еретик Автор поста <b>#{post_num}</b> (пост #{post_num}) отправлен на аутодафе!\n🕯️ <b>30 минут публичного молчания. Индульгенции в /shop сгорели вместе с еретиком.</b>",
    "🧲 <b>НАРОДНЫЙ МАГНИТ ПРИТЯНУЛ ВАЙПЕРА К ЗЕМЛЕ!</b>\n\n⬇️ Автор поста <b>#{post_num}</b> (пост #{post_num}) накрыт общественной гравитацией (5 голосов).\n🔒 <b>ПРИДАВЛЕН. ЗАМОЛЧАН. 30 МИНУТ НЕОТВРАТИМО.</b>",
    "🪖 <b>ВОЕННО-ПОЛЕВОЙ СУД БОРДЫ ПОСТАНОВИЛ!</b>\n\nЗа дезертирство от нормального общения: расстрел речевых центров Автора поста <b>#{post_num}</b> (пост #{post_num}) по вотуму 5 анонов.\n🔇 <b>30 минут посмертного молчания. Помилования нет.</b>",
    "🌑 <b>ЧЁРНАЯ МЕТКА ПОЛУЧЕНА!</b>\n\n☠️ Пять пиратов борды передали чёрную метку Автору поста <b>#{post_num}</b> (пост #{post_num}).\n⚓ <b>Приговор капитана народа: 30 минут в трюме молчания. Выкуп не принимается.</b>",
    "🤖 <b>СИСТЕМА САМООЧИЩЕНИЯ БОРДЫ АКТИВИРОВАНА!</b>\n\n⚙️ Алгоритм народного вотума (5/5 голосов) идентифицировал Автора поста <b>#{post_num}</b> (пост #{post_num}) как ТОКСИЧНЫЙ ЭЛЕМЕНТ.\n🔒 <b>НЕЙТРАЛИЗАЦИЯ: 30 МИНУТ ЖЕЛЕЗНОГО МОЛЧАНИЯ. ОБХОД НЕВОЗМОЖЕН.</b>",
    "🎻 <b>РЕКВИЕМ ПО СВОБОДЕ СЛОВА ВАЙПЕРА!</b>\n\n🎶 Пять анонов борды сыграли похоронный марш по болтовне Автора поста <b>#{post_num}</b> (пост #{post_num}).\n⚰️ <b>Упокоился в тишине на 30 минут. Воскрешение взятками запрещено религией Абу.</b>",
    "🦅 <b>ОРЁЛ НАРОДНОГО ПРАВОСУДИЯ ПОЙМАЛ МЫШЬ!</b>\n\n🦅 Пять зорких анонов засекли вайпера Автора поста <b>#{post_num}</b> (пост #{post_num}) и нажали вотум.\n🔒 <b>Добыча в когтях закона: 30 минут железного молчания. Выкуп у орла не работает.</b>",
    "🧠 <b>КОЛЛЕКТИВНЫЙ РАЗУМ БОРДЫ РЕШИЛ!</b>\n\n🤯 Пять нейронов народной сети единогласно: Автор поста <b>#{post_num}</b> (пост #{post_num}) — нейронный мусор.\n🔒 <b>ДЕФРАГМЕНТАЦИЯ ТРЕКА: 30 МИНУТ ТИШИНЫ. /shop НЕ ПОМОЖЕТ.</b>",
    "🏰 <b>ЗАМОК БОРДЫ ОПУСТИЛ РЕШЁТКУ НА ВАЙПЕРА!</b>\n\n⚔️ Пять рыцарей анонов провели успешный штурм болтовни Автора поста <b>#{post_num}</b> (пост #{post_num}).\n🔒 <b>В застенках: 30 минут. Золото на выкуп сгорело в топке вотума.</b>",
    "🩸 <b>КРОВАВЫЙ ЧЕТВЕРГ ДЛЯ ВАЙПЕРА — ВОТУМ ПРОШЁЛ!</b>\n\n💉 Пять анонов вонзили коллективный нож в болтовню Автора поста <b>#{post_num}</b> (пост #{post_num}).\n🔒 <b>30 минут кровоточащего молчания. Перевязка за взятки не предусмотрена.</b>",
    "🎩 <b>ФОКУСНИК ИСЧЕЗ — МУТ ПРИМЕНЁН!</b>\n\n🪄 Пять волшебников борды взмахнули палочками народного вотума и стёрли болтовню Автора поста <b>#{post_num}</b> (пост #{post_num}).\n✨ <b>30 минут магического молчания. Антизаклинание за шекели недоступно.</b>",
    "🐍 <b>ЗМЕЯ УКУШЕНА МАНГУСТАМИ БОРДЫ!</b>\n\n🦴 Пять мангустов (анонов) загнали Автора поста <b>#{post_num}</b> (пост #{post_num}) в нору молчания вотумом 5/5!\n🔒 <b>Нора запечатана на 30 минут. Выход за шекели заварен цементом.</b>",
    "🎬 <b>СТОП-КАДР! ВАЙПЕР ЗАМОРОЖЕН НАРОДОМ!</b>\n\n📽️ Режиссёры борды (5 анонов) остановили нежелательную сцену с участием Автора поста <b>#{post_num}</b> (пост #{post_num}).\n✂️ <b>Вырезано в монтаже: 30 минут. Права на восстановление кадра выкупить нельзя.</b>",
    "🌪️ <b>ВИХРЬ НАРОДНОГО ГНЕВА УНЁС ВАЙПЕРА!</b>\n\n💨 Торнадо из 5 голосов смёл Автора поста <b>#{post_num}</b> (пост #{post_num}) в безмолвную пустыню!\n🏜️ <b>30 минут в тишине Сахары. Оазис взяток не существует.</b>",
    "🥊 <b>НОКАУТ ПЕРВОГО РАУНДА НАРОДНОГО БОКСЁРСТВА!</b>\n\n🏆 Пять боксёров-анонов отправили Автора поста <b>#{post_num}</b> (пост #{post_num}) в нокаут вотумом!\n💫 <b>В отключке: 30 минут. Нашатырь за шекели недоступен.</b>",
    "🗳️ <b>СУД ЛИНЧА СОСТОЯЛСЯ — ПРИГОВОР ИСПОЛНЕН!</b>\n\n⚖️ Аноны решили, что Автор поста <b>#{post_num}</b> (пост #{post_num}) слишком громко хрюкал.\n🤐 <b>5 голосов собрано: нарушитель отправлен в мут на 30 минут без права откупа!</b>",
    "🗳️ <b>ГОЛОСОВАНИЕ ЗА ОБОССЫВАНИЕ ЗАВЕРШЕНО!</b>\n\n🍾 Автор поста <b>#{post_num}</b> (пост #{post_num}) заебал всех своим тухлым калом.\n🔒 <b>5 анонов проголосовали ЗА: 30 минут на бутылке молчания без взяток!</b>",
    "🗳️ <b>МУТ-РЕФЕРЕНДУМ УСПЕШНО ЗАКРЫТ!</b>\n\n📌 Автор поста <b>#{post_num}</b> (пост #{post_num}) открыл помойку не в том районе.\n🤐 <b>5 подписей собрано — пасть зашита на 30 минут! /shop бессилен.</b>"
]

votemute_router = Router(name="votemute_router")


def generate_votemute_key(target_id: int, post_num: int) -> str:
    """Internal memory key for dedup — uses IDs, never exposed to Telegram."""
    return f"vm_{target_id}_{post_num}"


def get_votemute_callback_token(target_id: int, post_num: int) -> str:
    """
    Safe opaque token for InlineKeyboardButton callback_data.
    Uses existing anon_id hash (e.g. 'Шолтер5') — deterministic, no raw ID exposed.
    Format: '<anon_tag>_<post_num>'
    """
    return f"{get_anon_id(target_id)}_{post_num}"


async def resolve_votemute_token(token: str) -> Optional[Tuple[int, int]]:
    """
    Resolves callback token '<anon_tag>_<post_num>' back to (target_id, post_num).
    Checks memory cache, then Votemutes table in DB, and finally Posts table fallback.
    """
    clean_expired_votemutes()
    try:
        last_sep = token.rfind("_")
        if last_sep == -1:
            return None
        anon_tag = token[:last_sep]
        post_num = int(token[last_sep + 1:])
    except (ValueError, IndexError):
        return None

    # 1. Check in-memory cache
    for vm in list(active_votemutes.values()):
        t_id = vm.get("target_id")
        p_num = vm.get("post_num")
        if p_num == post_num and t_id and (get_anon_id(t_id) == anon_tag or anon_tag in (get_anon_id(t_id, "ru"), get_anon_id(t_id, "en"))):
            return t_id, post_num

    # 2. Check Votemutes in DB
    try:
        db = await get_pool()
        await ensure_votemute_tables(db)
        async with db.execute(
            """SELECT vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, broadcast_msgs
               FROM Votemutes
               WHERE post_num = ?
               ORDER BY created_at DESC LIMIT 1""",
            (post_num,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                t_id = row[2]
                if t_id and (get_anon_id(t_id) == anon_tag or anon_tag in (get_anon_id(t_id, "ru"), get_anon_id(t_id, "en"))):
                    vm_key = generate_votemute_key(t_id, post_num)
                    voters = set()
                    try:
                        async with db.execute("SELECT voter_id FROM VotemuteVotes WHERE vote_id = ?", (row[0],)) as vcur:
                            for vrow in await vcur.fetchall():
                                voters.add(vrow[0])
                    except Exception:
                        pass
                    bcast = []
                    try:
                        bcast = json.loads(row[11]) if row[11] else []
                    except Exception:
                        pass
                    async with votemute_lock:
                        active_votemutes[vm_key] = {
                            "key": vm_key,
                            "vote_id": row[0],
                            "board_id": row[1],
                            "target_id": t_id,
                            "post_num": post_num,
                            "initiator_id": row[4],
                            "created_ts": row[5],
                            "expires_at": row[6],
                            "status": row[7],
                            "yes_votes": row[8],
                            "no_votes": row[9],
                            "required_votes": row[10],
                            "voters": voters,
                            "executed": row[7] == 'executed',
                            "rejected": row[7] == 'rejected',
                            "broadcast_msgs": bcast
                        }
                    return t_id, post_num
    except Exception as e:
        logger.warning(f"Error checking Votemutes in DB for resolve_votemute_token: {e}")

    # 3. Resilient DB fallback: recover from Posts table if bot was restarted and Votemutes was not recorded
    try:
        from common.database import get_post_by_num
        db_post = await get_post_by_num(post_num)
        if db_post:
            t_id = db_post.get("author_id")
            if t_id and (get_anon_id(t_id) == anon_tag or anon_tag in (get_anon_id(t_id, "ru"), get_anon_id(t_id, "en"))):
                vm_key = generate_votemute_key(t_id, post_num)
                async with votemute_lock:
                    if vm_key not in active_votemutes:
                        active_votemutes[vm_key] = {
                            "key": vm_key,
                            "board_id": db_post.get("board_id", "b"),
                            "target_id": t_id,
                            "post_num": post_num,
                            "created_ts": db_post.get("timestamp", time.time()),
                            "voters": set(),
                            "executed": False,
                            "broadcast_msgs": []
                        }
                return t_id, post_num
    except Exception as e:
        logger.warning(f"Error in DB fallback for resolve_votemute_token: {e}")

    return None


def clean_expired_votemutes():
    """Removes expired votemute sessions from memory to prevent memory leaks."""
    now = time.time()
    cutoff_unexecuted = now - VOTE_WINDOW_SEC
    cutoff_executed = now - (VOTE_WINDOW_SEC + MUTE_DURATION_SEC)
    expired_keys = [
        k for k, vm in active_votemutes.items()
        if (vm.get("executed") and vm.get("created_ts", 0) <= cutoff_executed)
        or (not vm.get("executed") and vm.get("created_ts", 0) <= cutoff_unexecuted)
    ]
    for k in expired_keys:
        active_votemutes.pop(k, None)

    try:
        loop = asyncio.get_running_loop()
        if loop and loop.is_running():
            loop.create_task(sweep_expired_votemutes())
    except (RuntimeError, Exception):
        pass


async def sweep_expired_votemutes(db=None) -> int:
    """
    Finds all active votemutes in SQLite where expires_at <= now,
    and updates their status to 'expired'. Also updates in-memory cache.
    Returns count of updated rows.
    """
    now = time.time()
    count = 0
    try:
        if db is None:
            db = await get_pool()
        await ensure_votemute_tables(db)
        async with db_transaction(db):
            cursor = await db.execute(
                "UPDATE Votemutes SET status = 'expired' WHERE status = 'active' AND expires_at <= ?",
                (now,)
            )
            count = cursor.rowcount if hasattr(cursor, 'rowcount') else 0

        async with votemute_lock:
            for vm in active_votemutes.values():
                if vm.get("status") == "active" and vm.get("expires_at", 0) <= now:
                    vm["status"] = "expired"
                    vm["expired"] = True
    except Exception as e:
        logger.error(f"Error sweeping expired votemutes: {e}")
    return count


async def get_active_votemute_for_target(board_id: str, target_id: int, db=None) -> Optional[Dict[str, Any]]:
    """
    Returns active votemute dict if there is an ongoing voting against target_id on board_id.
    Prevents duplicate votemutes against the same user across different posts/threads.
    """
    clean_expired_votemutes()
    now = time.time()
    # 1. Check in-memory cache
    async with votemute_lock:
        for vm in active_votemutes.values():
            if (vm.get("target_id") == target_id
                and vm.get("board_id") == board_id
                and not vm.get("executed")
                and not vm.get("rejected")):
                created_ts = vm.get("created_ts", 0)
                if now - created_ts <= VOTE_WINDOW_SEC:
                    return vm

    # 2. Check DB
    try:
        if db is None:
            db = await get_pool()
        await ensure_votemute_tables(db)
        await sweep_expired_votemutes(db=db)
        async with db.execute(
            """SELECT vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, card_chat_id, card_message_id, broadcast_msgs
               FROM Votemutes
               WHERE board_id = ? AND target_id = ? AND status = 'active' AND expires_at > ?
               ORDER BY created_at DESC LIMIT 1""",
            (board_id, target_id, now)
        ) as cur:
            row = await cur.fetchone()
            if row:
                bcast = []
                try:
                    bcast = json.loads(row[13]) if row[13] else []
                except Exception:
                    pass
                vm_dict = {
                    "key": generate_votemute_key(row[2], row[3]),
                    "vote_id": row[0],
                    "board_id": row[1],
                    "target_id": row[2],
                    "post_num": row[3],
                    "initiator_id": row[4],
                    "created_ts": row[5],
                    "expires_at": row[6],
                    "status": row[7],
                    "yes_votes": row[8],
                    "no_votes": row[9],
                    "required_votes": row[10],
                    "card_chat_id": row[11],
                    "card_message_id": row[12],
                    "broadcast_msgs": bcast,
                    "executed": False,
                    "rejected": False
                }
                return vm_dict
    except Exception as e:
        logger.error(f"Error checking active votemute in DB: {e}")

    return None


def get_votemute_status(target_id: int, post_num: int) -> Optional[Dict[str, Any]]:
    """Returns current active votemute state dictionary if present."""
    vm_key = generate_votemute_key(target_id, post_num)
    return active_votemutes.get(vm_key)


def get_votemute_keyboard(
    target_id: int,
    post_num: int,
    votes_count: int,
    is_executed: bool = False,
    no_votes: int = 0,
    is_rejected: bool = False,
    is_expired: bool = False
) -> InlineKeyboardMarkup:
    """Builds inline keyboard for active, completed, or expired votemute."""
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
    if is_rejected:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕊️ ОПРАВДАН НАРОДОМ",
                    callback_data=f"vm_info:{token}"
                )
            ]
        ])
    if is_expired:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏳ ВОТУМ ИСТЁК (НЕТ КВОРУМА)",
                    callback_data=f"vm_info:{token}"
                )
            ]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"🔨 За: [{votes_count}/{VOTES_REQUIRED}]",
                callback_data=f"vm_vote:yes:{token}"
            ),
            InlineKeyboardButton(
                text=f"🕊️ Против: [{no_votes}]",
                callback_data=f"vm_vote:no:{token}"
            )
        ]
    ])


def get_votemute_card_text(
    post_num: int,
    target_id: int,
    votes_count: int,
    created_ts: float,
    is_executed: bool = False,
    no_votes: int = 0,
    is_rejected: bool = False,
    is_expired: bool = False
) -> str:
    """Formats 2ch-style HTML text for the votemute card oriented strictly by post number."""
    now = time.time()
    time_left_sec = max(0, int(VOTE_WINDOW_SEC - (now - created_ts)))
    time_left_min = (time_left_sec + 59) // 60

    if is_executed or votes_count >= VOTES_REQUIRED:
        return (
            "⚖️ <b>НАРОДНЫЙ ВОТУМ ЗАВЕРШЕН — ПРИГОВОР ИСПОЛНЕН!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Пост:</b> <code>#{post_num}</code>\n"
            f"📊 <b>Итог:</b> Собрано <b>{VOTES_REQUIRED}/{VOTES_REQUIRED}</b> голосов анонов!\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔒 <b>Вердикт:</b> <b>ЖЕЛЕЗНЫЙ НАРОДНЫЙ МУТ на 30 минут</b>.\n"
            "<i>Этот мут не снимается взятками в /shop и защищен от помилований.</i>"
        )

    if is_rejected:
        return (
            "🕊️ <b>НАРОДНЫЙ СУД: АНОН ОПРАВДАН!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Пост:</b> <code>#{post_num}</code>\n"
            f"📊 <b>Итог:</b> 🕊️ Отклонено большинством анонов ({no_votes} против).\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✨ <i>Претензии сняты, вотум закрыт. Нарушений не выявлено.</i>"
        )

    if is_expired:
        return (
            "⏳ <b>НАРОДНЫЙ ВОТУМ ОТКЛОНЕН — ВРЕМЯ ВЫШЛО!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Пост:</b> <code>#{post_num}</code>\n"
            f"📊 <b>Итог:</b> Кворум не набран за отведенное время ({votes_count}/{VOTES_REQUIRED} за, {no_votes} против).\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🕊️ <i>Голосование закрыто, претензии аннулированы.</i>"
        )

    return (
        "⚖️ <b>НАРОДНЫЙ ВОТУМ НЕДОВЕРИЯ / ШИЗО-МУТ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Выдвинут пост:</b> <code>#{post_num}</code>\n"
        f"📊 <b>Голосование:</b> 🔨 За: <b>{votes_count}/{VOTES_REQUIRED}</b> | 🕊️ Против: <b>{no_votes}</b>\n"
        f"⏳ <b>Осталось времени:</b> ~<b>{time_left_min} мин.</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Нажми кнопку ниже, чтобы решить судьбу автора поста. При наборе 5 голосов «ЗА» на него наложится "
        "ЖЕЛЕЗНЫЙ МУТ на 30 минут, который нельзя снять за взятки в /shop!</i>"
    )


async def broadcast_votemute_announcement(bot, board_id: str, text: str, reply_to_post: Optional[int] = None):
    """Broadcasts public announcement to the whole board via process_new_post."""
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
    """Checks if target user active_items contains an unexpired unbribable_votemute_until timestamp."""
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
                    items = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
                    until = int(items.get(UNBRIBABLE_FLAG_KEY, 0))
                    if until > now:
                        return True, until - now
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error checking unbribable mute in DB for user {user_id}: {e}")
    return False, 0


async def lift_unbribable_folk_mute(user_id: int, board_id: str, db=None) -> bool:
    """
    Administratively pardons / lifts an unbribable folk mute for target user.
    Clears unbribable_votemute_until flag from Users active_items, removes iron mute
    from Mutes table, clears in-memory state, and marks any active/executed Votemutes as pardoned.
    """
    if not user_id:
        return False
    if db is None:
        db = await get_pool()
    try:
        async with db_transaction(db):
            # 1. Clear unbribable flag from Users.active_items
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (user_id, board_id)
            ) as cur:
                row = await cur.fetchone()
            if row and row[0]:
                try:
                    items = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
                    if UNBRIBABLE_FLAG_KEY in items:
                        del items[UNBRIBABLE_FLAG_KEY]
                        await db.execute(
                            "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                            (json.dumps(items), user_id, board_id)
                        )
                except Exception as ex:
                    logger.warning(f"Error updating active_items in lift_unbribable_folk_mute: {ex}")

            # 2. Delete Mutes entry
            await db.execute(
                "DELETE FROM Mutes WHERE user_id = ? AND board_id = ? AND mute_type = 'mute'",
                (user_id, board_id)
            )

            # 3. Update Votemutes status to 'pardoned'
            await db.execute(
                "UPDATE Votemutes SET status = 'pardoned' WHERE board_id = ? AND target_id = ? AND status IN ('active', 'executed')",
                (board_id, user_id)
            )
            # 4. Grant 1-hour victim immunity after pardoning/mute lifting
            try:
                from shared_state import set_partyvan_victim_immunity
                set_partyvan_victim_immunity(user_id, int(time.time()) + 3600)
            except Exception:
                pass

        # 4. Clear in-memory caches
        try:
            import shared_state
            b_data = shared_state.board_data.get(board_id)
            if b_data and 'mutes' in b_data:
                b_data['mutes'].pop(user_id, None)
        except Exception:
            pass

        async with votemute_lock:
            for vm in list(active_votemutes.values()):
                if vm.get("target_id") == user_id and vm.get("board_id") == board_id:
                    vm["status"] = "pardoned"
                    vm["executed"] = False
                    vm["rejected"] = True

        return True
    except Exception as e:
        logger.error(f"Error lifting unbribable mute for user {user_id} on /{board_id}/: {e}", exc_info=True)
        return False


MIN_POSTS_REQUIRED_FOR_QUORUM = 5  # User must have >= 5 posts
QUORUM_ACTIVITY_WINDOW_SEC = 7 * 86400.0  # 7 days
QUORUM_ELIGIBILITY_ERROR = (
    "❌ В Народном Вотуме могут участвовать только активные аноны борды "
    "(не менее 5 постов за последние 7 дней)!"
)


async def check_voter_eligibility(voter_id: int, board_id: str, db=None) -> Tuple[bool, str]:
    """
    Ensures voter has >= 5 non-shadow posts on this board in the last 7 days.
    Admins are exempt.
    """
    if not voter_id:
        return False, "❌ Некорректный ID пользователя."

    try:
        from admin_manager import is_admin
        if is_admin(voter_id):
            return True, ""
    except Exception:
        pass

    try:
        if db is None:
            db = await get_pool()
        cutoff_ts = time.time() - QUORUM_ACTIVITY_WINDOW_SEC
        async with db.execute(
            """SELECT COUNT(*) FROM Posts
               WHERE author_id = ? AND board_id = ? AND timestamp >= ? AND is_shadow = 0""",
            (voter_id, board_id, cutoff_ts)
        ) as cur:
            row = await cur.fetchone()
            count = int(row[0]) if row and row[0] is not None else 0
            if count < MIN_POSTS_REQUIRED_FOR_QUORUM:
                return False, QUORUM_ELIGIBILITY_ERROR
            return True, ""
    except Exception as e:
        logger.error(f"Error checking voter eligibility for {voter_id} on /{board_id}/: {e}")
        return False, "❌ Ошибка проверки активности на борде."


class VoteResult(tuple):
    """
    Subclass of 4-tuple (ok, message, current_yes_votes, is_executed)
    preserving 100% backward compatibility with all 4-tuple unpacking
    while carrying the `is_new` flag for cmd_votemute deduplication.
    """
    def __new__(cls, ok: bool, message: str, current_yes_votes: int, is_executed: bool, is_new: bool = False):
        inst = super().__new__(cls, (ok, message, current_yes_votes, is_executed))
        inst.is_new = is_new
        return inst

    @property
    def ok(self) -> bool:
        return self[0]

    @property
    def message(self) -> str:
        return self[1]

    @property
    def current_yes_votes(self) -> int:
        return self[2]

    @property
    def is_executed(self) -> bool:
        return self[3]


async def start_or_add_vote(
    board_id: str,
    target_id: int,
    post_num: int,
    voter_id: int,
    bot=None,
    vote_type: str = "yes",
    check_eligibility: bool = True
) -> Tuple[bool, str, int, bool]:
    """
    Starts a new votemute session or casts/switches a vote in an existing one.
    Guarantees atomic recording in SQLite and memory cache.
    Returns: (ok: bool, message: str, current_yes_votes: int, is_executed: bool)
    """
    clean_expired_votemutes()

    if not post_num or post_num <= 0:
        return False, "❌ Некорректный номер поста.", 0, False

    if not target_id or target_id <= 0:
        return False, "❌ Нельзя объявить вотум системному аккаунту.", 0, False

    if not voter_id or voter_id <= 0:
        return False, "❌ Некорректный ID голосующего.", 0, False

    vote_type = (vote_type or "yes").lower()
    if vote_type not in ("yes", "no"):
        vote_type = "yes"

    if voter_id == target_id and vote_type == "yes":
        return False, "❌ Нельзя голосовать за мут самого себя, шизик.", 0, False

    if bot and target_id == getattr(bot, "id", None):
        return False, "❌ Ты пытаешься замутить бота? У меня нет голосовых связок.", 0, False

    # Check if target has victim immunity from recent votemute/partyvan
    try:
        from shared_state import get_partyvan_victim_immunity
        victim_immunity = get_partyvan_victim_immunity(target_id)
        if victim_immunity > time.time():
            rem_min = max(1, int((victim_immunity - time.time() + 59) // 60))
            return False, f"🛡 У этого анона временный иммунитет от травли и вотемута (осталось {rem_min} мин.)!", 0, False
    except Exception:
        pass

    # Check if target is already serving an iron mute
    is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
    if is_unbribable:
        rem_min = max(1, (remaining_sec + 59) // 60)
        return False, f"⚠️ Этот анон уже отбывает Народный Мут! Осталось: {rem_min} мин.", VOTES_REQUIRED, True

    db = await get_pool()
    await ensure_votemute_tables(db)

    if check_eligibility:
        is_eligible, elig_reason = await check_voter_eligibility(voter_id, board_id, db=db)
        if not is_eligible:
            return False, elig_reason, 0, False

    now = time.time()
    is_new_session = False

    async with votemute_lock:
        async with db_transaction(db):
            # Check for existing session in DB by vote_id or (board_id, target_id, active)
            primary_key = generate_votemute_key(target_id, post_num)
            row = None
            async with db.execute(
                """SELECT vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, broadcast_msgs
                   FROM Votemutes
                   WHERE vote_id = ? OR (board_id = ? AND target_id = ? AND status = 'active')
                   ORDER BY created_at DESC LIMIT 1""",
                (primary_key, board_id, target_id)
            ) as cur:
                row = await cur.fetchone()

            if row:
                vote_id = row[0]
                session_board_id = row[1]
                session_post_num = row[3]
                initiator_id = row[4]
                created_at = row[5]
                expires_at = row[6]
                status = row[7]
                yes_votes = row[8]
                no_votes = row[9]
                required_votes = row[10]

                if status == 'executed':
                    return VoteResult(False, "⚖️ Приговор по этому посту уже вынесен и приведен в исполнение!", yes_votes, True, is_new=False)

                if status == 'rejected':
                    return VoteResult(False, "🕊️ Этот анон уже оправдан народом борды!", yes_votes, False, is_new=False)

                if now > expires_at or status == 'expired':
                    await db.execute("UPDATE Votemutes SET status = 'expired' WHERE vote_id = ?", (vote_id,))
                    if vote_id == primary_key:
                        if primary_key in active_votemutes:
                            active_votemutes[primary_key]["status"] = "expired"
                            active_votemutes[primary_key]["expired"] = True
                        return VoteResult(False, "⏳ Срок действия этого голосования истек. Кворум не набран.", yes_votes, False, is_new=False)
                    # Old session for different post expired -> allow fresh session on new post to start cleanly
                    row = None

            if not row:
                if voter_id == target_id:
                    return VoteResult(False, "❌ Нельзя объявлять вотум против самого себя.", 0, False)
                is_new_session = True
                vote_id = primary_key
                session_board_id = board_id
                session_post_num = post_num
                initiator_id = voter_id
                created_at = now
                expires_at = now + VOTE_WINDOW_SEC
                yes_votes = 0
                no_votes = 0
                required_votes = VOTES_REQUIRED
                status = 'active'
                await db.execute(
                    """INSERT INTO Votemutes (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, status, yes_votes, no_votes, required_votes, broadcast_msgs)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, 0, ?, '[]')
                       ON CONFLICT(vote_id) DO UPDATE SET
                           board_id = excluded.board_id,
                           target_id = excluded.target_id,
                           post_num = excluded.post_num,
                           initiator_id = excluded.initiator_id,
                           created_at = excluded.created_at,
                           expires_at = excluded.expires_at,
                           status = 'active',
                           yes_votes = 0,
                           no_votes = 0,
                           required_votes = excluded.required_votes,
                           broadcast_msgs = '[]'""",
                    (vote_id, board_id, target_id, post_num, initiator_id, created_at, expires_at, required_votes)
                )
                await db.execute("DELETE FROM VotemuteVotes WHERE vote_id = ?", (vote_id,))

            # Check previous vote by voter in this session
            prev_vote_row = None
            async with db.execute(
                "SELECT vote_type FROM VotemuteVotes WHERE vote_id = ? AND voter_id = ?",
                (vote_id, voter_id)
            ) as vcur:
                prev_vote_row = await vcur.fetchone()

            if prev_vote_row:
                prev_vote = prev_vote_row[0]
                if prev_vote == vote_type:
                    return VoteResult(False, f"⚠️ Ты уже отдал свой голос! Текущий сбор: [{yes_votes}/{VOTES_REQUIRED}]", yes_votes, False, is_new=False)

                # Vote switch!
                if prev_vote == "yes" and vote_type == "no":
                    yes_votes = max(0, yes_votes - 1)
                    no_votes += 1
                elif prev_vote == "no" and vote_type == "yes":
                    no_votes = max(0, no_votes - 1)
                    yes_votes += 1

                await db.execute(
                    "UPDATE VotemuteVotes SET vote_type = ?, voted_at = ? WHERE vote_id = ? AND voter_id = ?",
                    (vote_type, now, vote_id, voter_id)
                )
                await db.execute(
                    "UPDATE Votemutes SET yes_votes = ?, no_votes = ? WHERE vote_id = ?",
                    (yes_votes, no_votes, vote_id)
                )
                resp_msg = (
                    f"🔄 Твой голос изменен на ПРОТИВ! [🔨 {yes_votes}/{VOTES_REQUIRED} | 🕊️ {no_votes}]"
                    if vote_type == "no" else
                    f"🔄 Твой голос изменен на ЗА! [🔨 {yes_votes}/{VOTES_REQUIRED} | 🕊️ {no_votes}]"
                )
            else:
                # First vote by voter
                if vote_type == "yes":
                    yes_votes += 1
                else:
                    no_votes += 1

                await db.execute(
                    """INSERT INTO VotemuteVotes (vote_id, voter_id, vote_type, voted_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(vote_id, voter_id) DO UPDATE SET
                           vote_type = excluded.vote_type,
                           voted_at = excluded.voted_at""",
                    (vote_id, voter_id, vote_type, now)
                )
                await db.execute(
                    "UPDATE Votemutes SET yes_votes = ?, no_votes = ? WHERE vote_id = ?",
                    (yes_votes, no_votes, vote_id)
                )
                resp_msg = f"⚖️ Твой голос учтен! Собрано: [{yes_votes}/{VOTES_REQUIRED}]"

            # Sync in-memory cache
            vm_mem = active_votemutes.get(vote_id)
            if not vm_mem:
                vm_mem = {
                    "key": vote_id,
                    "vote_id": vote_id,
                    "board_id": board_id,
                    "target_id": target_id,
                    "post_num": session_post_num,
                    "created_ts": created_at,
                    "voters": set(),
                    "executed": False,
                    "rejected": False,
                    "broadcast_msgs": []
                }
                active_votemutes[vote_id] = vm_mem

            vm_mem["yes_votes"] = yes_votes
            vm_mem["no_votes"] = no_votes
            vm_mem["voters"].add(voter_id)

            # Check Quorum
            if yes_votes >= VOTES_REQUIRED and not vm_mem.get("executed"):
                vm_mem["executed"] = True
                await db.execute("UPDATE Votemutes SET status = 'executed' WHERE vote_id = ?", (vote_id,))
                asyncio.create_task(_apply_unbribable_iron_mute(board_id, target_id, session_post_num, bot))
                return VoteResult(True, "⚖️ ГОЛОС ПРИНЯТ! ПОРОГ ДОСТИГНУТ: ШИЗ ОТПРАВЛЯЕТСЯ В ЖЕЛЕЗНЫЙ МУТ НА 30 МИНУТ!", yes_votes, True, is_new=is_new_session)

            if no_votes >= VOTES_REQUIRED and not vm_mem.get("rejected"):
                vm_mem["rejected"] = True
                await db.execute("UPDATE Votemutes SET status = 'rejected' WHERE vote_id = ?", (vote_id,))
                return VoteResult(True, "🕊️ ГОЛОС ПРИНЯТ! АНОН ОПРАВДАН НАРОДОМ: ДЕЛО ЗАКРЫТО!", yes_votes, False, is_new=is_new_session)

            return VoteResult(True, resp_msg, yes_votes, False, is_new=is_new_session)


async def _apply_unbribable_iron_mute(board_id: str, target_id: int, post_num: int, bot=None):
    """Applies the unbribable 30-minute iron folk mute in DB, in-memory state, and broadcasts verdict."""
    now = int(time.time())
    mute_until = now + MUTE_DURATION_SEC

    # 1. Update SQLite database
    db = await get_pool()
    try:
        async with db_transaction(db):
            async with db.execute(
                "SELECT cursed_until, active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (target_id, board_id)
            ) as cur:
                row = await cur.fetchone()

            if row:
                current_cursed = row[0] or 0
                new_cursed = max(current_cursed, mute_until)
                raw_items = row[1]
                items_dict = {}
                if raw_items:
                    try:
                        items_dict = json.loads(raw_items) if isinstance(raw_items, str) else dict(raw_items)
                    except Exception:
                        items_dict = {}
                items_dict[UNBRIBABLE_FLAG_KEY] = mute_until
                await db.execute(
                    "UPDATE Users SET cursed_until = ?, active_items = ? WHERE user_id = ? AND board_id = ?",
                    (new_cursed, json.dumps(items_dict), target_id, board_id)
                )
            else:
                items_dict = {UNBRIBABLE_FLAG_KEY: mute_until}
                await db.execute(
                    """INSERT INTO Users (user_id, board_id, cursed_until, active_items) VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id, board_id) DO UPDATE SET
                           cursed_until = excluded.cursed_until,
                           active_items = excluded.active_items""",
                    (target_id, board_id, mute_until, json.dumps(items_dict))
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
    target_anon = f"#{post_num}"
    announcement = random.choice(VOTEMUTE_ANNOUNCEMENTS).format(
        post_num=post_num, target_anon=target_anon
    )

    if bot:
        asyncio.create_task(broadcast_votemute_announcement(bot, board_id, announcement, reply_to_post=post_num))

    # 4. Log to GlobalLogs and alert admins via Auto-Snitch
    try:
        from common.database import log_global_event
        from extreme_defense_engine import send_auto_snitch_alert
        asyncio.create_task(log_global_event(
            'bot',
            f"🗳️ VOTEMUTE: Народный мут 30 мин юзера {target_id} на /{board_id}/ (пост #{post_num})"
        ))
        if bot:
            asyncio.create_task(send_auto_snitch_alert(
                bot=bot,
                user_id=target_id,
                board_id=board_id,
                post_num=post_num,
                reason="Народный вотемут (кворум 5/5 голосов)",
                details=f"Автор поста #{post_num} получил 30-минутный народный мут.",
                extra_info="Вы можете отменить вотемут одной кнопкой [🔓 Ошибка! Размутить] или ужесточить наказание."
            ))
    except Exception as vm_alert_err:
        logger.warning(f"Failed to log/alert votemute: {vm_alert_err}")

    # 5. Grant 1-hour victim immunity after votemute to prevent repeated harassment
    try:
        from shared_state import set_partyvan_victim_immunity
        set_partyvan_victim_immunity(target_id, now + 3600)
    except Exception as imm_err:
        logger.error(f"Error setting victim immunity for user {target_id}: {imm_err}")


# ============================================================================
# AIOGRAM ROUTER & HANDLERS
# ============================================================================

async def _resolve_target_from_message(message: types.Message) -> Tuple[Optional[int], Optional[int]]:
    """Resolves (target_post_num, target_author_id) from reply or command arguments."""
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


@votemute_router.message(Command("votemute", "voteban", "вотум", "шизомут", "вотебан", "vm", "vb"))
async def cmd_votemute(message: types.Message, board_id: Optional[str] = None):
    """Handles /votemute and /voteban commands with deduplication and active card linking."""
    if not board_id:
        board_id = "b"

    voter_id = message.from_user.id
    post_num, target_id = await _resolve_target_from_message(message)

    if not post_num or not target_id:
        await message.answer(
            "⚠️ <b>Как использовать Народный Вотум (/votemute, /voteban):</b>\n\n"
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

    if message.bot and target_id == getattr(message.bot, "id", None):
        reject_text = random.choice([
            "💀 Ты пытаешься замутить бота? Мразь, у меня нет голосовых связок, я не могу молчать сильнее.",
            "🔇 Замутить меня? Хуй тебе в рот. Я сервер, я работаю пока ты спишь.",
            "🤖 Попытка вотума на бота зафиксирована. Анон записан в чёрный список шизов."
        ])
        await message.answer(reject_text, parse_mode="HTML")
        return

    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    db = await get_pool()
    if await check_db_shadow_muted(voter_id, board_id, db=db) or await check_user_is_muted(db, voter_id, board_id):
        await message.answer("🔇 Замученным нельзя запускать народный вотум.", parse_mode="HTML")
        return

    # Quorum activity check: > 1 post in last 2 days on this board
    is_eligible, elig_reason = await check_voter_eligibility(voter_id, board_id, db=db)
    if not is_eligible:
        await message.answer(elig_reason, parse_mode="HTML")
        return

    # Check if target has victim immunity
    try:
        from shared_state import get_partyvan_victim_immunity
        victim_immunity = get_partyvan_victim_immunity(target_id)
        if victim_immunity > time.time():
            rem_min = max(1, int((victim_immunity - time.time() + 59) // 60))
            await message.answer(
                f"🛡 <b>Автор поста <code>#{post_num}</code> имеет временный иммунитет от травли и вотемута!</b>\n"
                f"Осталось действия иммунитета: ~<b>{rem_min} мин.</b>",
                parse_mode="HTML"
            )
            return
    except Exception:
        pass

    # Check if already in unbribable mute
    is_unbribable, remaining_sec = await check_user_unbribable_mute(target_id, board_id)
    if is_unbribable:
        rem_min = max(1, (remaining_sec + 59) // 60)
        target_reply_id = message.reply_to_message.message_id if message.reply_to_message else None
        await message.answer(
            f"🔒 <b>Автор поста <code>#{post_num}</code> уже отбывает Железный Народный Мут!</b>\n"
            f"Осталось сидеть: ~<b>{rem_min} мин.</b> Повторный вотум не требуется.",
            parse_mode="HTML",
            reply_to_message_id=target_reply_id
        )
        return

    # Anti-duplication check: Is there already an active votemute on this target?
    existing_vm = await get_active_votemute_for_target(board_id, target_id, db=db)
    if existing_vm:
        # Cast voter's vote in existing active session without spawning duplicate cards
        active_post = existing_vm.get("post_num", post_num)
        ok, msg, current_votes, is_executed = await start_or_add_vote(
            board_id=board_id,
            target_id=target_id,
            post_num=active_post,
            voter_id=voter_id,
            bot=message.bot,
            vote_type="yes"
        )
        if ok:
            status_note = "✅ <b>Твой голос 'ЗА' добавлен в активный вотум!</b>"
        else:
            status_note = f"⚠️ <i>{msg}</i>"

        target_reply_id = message.reply_to_message.message_id if message.reply_to_message else None
        await message.answer(
            f"⚖️ <b>Голосование по посту <code>#{active_post}</code> уже активно!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Текущий сбор:</b> 🔨 <b>{current_votes}/{VOTES_REQUIRED}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_note}",
            parse_mode="HTML",
            reply_to_message_id=target_reply_id
        )

        # Update all active cards in background
        vm_key = generate_votemute_key(target_id, active_post)
        asyncio.create_task(_sync_all_votemute_cards(message.bot, vm_key, target_id, active_post))
        return

    # Fresh session: cast initial vote
    vote_res = await start_or_add_vote(
        board_id=board_id,
        target_id=target_id,
        post_num=post_num,
        voter_id=voter_id,
        bot=message.bot,
        vote_type="yes"
    )
    ok, msg, current_votes, is_executed = vote_res

    # Concurrency guard: if another concurrent /votemute just created this session,
    # do NOT spawn a duplicate card or duplicate broadcast!
    if not getattr(vote_res, "is_new", True) and ok:
        status_note = "✅ <b>Твой голос 'ЗА' добавлен в активный вотум!</b>"
        target_reply_id = message.reply_to_message.message_id if message.reply_to_message else None
        await message.answer(
            f"⚖️ <b>Голосование по посту <code>#{post_num}</code> уже активно!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Текущий сбор:</b> 🔨 <b>{current_votes}/{VOTES_REQUIRED}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_note}",
            parse_mode="HTML",
            reply_to_message_id=target_reply_id
        )
        vm_key = generate_votemute_key(target_id, post_num)
        if message.bot:
            asyncio.create_task(_sync_all_votemute_cards(message.bot, vm_key, target_id, post_num))
        return

    card_text = get_votemute_card_text(
        post_num=post_num,
        target_id=target_id,
        votes_count=current_votes,
        created_ts=time.time(),
        is_executed=is_executed,
        no_votes=0
    )
    keyboard = get_votemute_keyboard(target_id, post_num, current_votes, is_executed, no_votes=0)

    # Determine post message_id to send the votemute card strictly as a reply
    target_reply_id = None
    if message.reply_to_message:
        target_reply_id = message.reply_to_message.message_id
    elif post_num:
        try:
            async with db.execute(
                "SELECT message_id FROM ChannelCopies WHERE channel_id = ? AND post_num = ? LIMIT 1",
                (message.chat.id, post_num)
            ) as ccur:
                cc_row = await ccur.fetchone()
                if cc_row and cc_row[0]:
                    target_reply_id = cc_row[0]
        except Exception:
            pass

    # Send exactly 1 voting card with fresh banner photo as a direct reply to the post
    banner_fname = ""
    photo_payload = None
    try:
        from banner_manager import get_banner_file
        bot_id = message.bot.id if message.bot else None
        banner_fname, photo_payload = get_banner_file(
            category=["schizo", "duel", "gothic", "cyberpunk", "matrix"],
            user_id=message.chat.id,
            bot_id=bot_id
        )
    except Exception as e:
        logger.debug(f"Could not load banner file for votemute: {e}")

    sent = None
    if photo_payload:
        try:
            from banner_manager import is_video_banner
            if is_video_banner(banner_fname) and hasattr(message, "answer_video"):
                sent = await message.answer_video(
                    video=photo_payload,
                    caption=card_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    reply_to_message_id=target_reply_id,
                    supports_streaming=True
                )
            else:
                sent = await message.answer_photo(
                    photo=photo_payload,
                    caption=card_text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    reply_to_message_id=target_reply_id
                )
        except Exception as ex:
            logger.warning(f"Error sending photo votemute card, falling back to text: {ex}")
            sent = await message.answer(
                card_text,
                reply_markup=keyboard,
                parse_mode="HTML",
                reply_to_message_id=target_reply_id
            )
    else:
        sent = await message.answer(
            card_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            reply_to_message_id=target_reply_id
        )

    vm_key = generate_votemute_key(target_id, post_num)
    if sent:
        async with votemute_lock:
            vm_rec = active_votemutes.get(vm_key)
            if vm_rec:
                vm_rec.setdefault("broadcast_msgs", []).append((sent.chat.id, sent.message_id))
        try:
            async with db_transaction(db):
                await db.execute(
                    "UPDATE Votemutes SET card_chat_id = ?, card_message_id = ? WHERE vote_id = ?",
                    (sent.chat.id, sent.message_id, vm_key)
                )
        except Exception:
            pass

    # Broadcast interactive voting card to active board subscribers (single source of truth with banner)
    if ok and not is_executed:
        async def _do_votemute_broadcast():
            try:
                if not ENABLE_VOTEMUTE_PM_BROADCAST:
                    logger.info("Votemute PM banner broadcast is disabled to prevent user spam.")
                    return
                import shared_state
                from banner_manager import broadcast_banner_to_users
                b_data = shared_state.board_data.get(board_id, {})
                active_users = list(b_data.get('users', {}).get('active', []))
                banned_users = set(b_data.get('users', {}).get('banned', []))

                # Exclude initiator, target, origin chat, and banned users to prevent duplicate/unwanted broadcast
                exclude_ids = {voter_id, target_id, message.chat.id} | banned_users
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
                    category=["schizo", "duel", "gothic", "cyberpunk", "matrix"],
                    banner_name=banner_fname,
                    parse_mode="HTML",
                    on_sent=_on_sent,
                )

                # Persist updated broadcast_msgs so they survive bot restarts
                async with votemute_lock:
                    vm_record = active_votemutes.get(vm_key)
                    bcast_list = list(vm_record.get("broadcast_msgs", [])) if vm_record else []
                if bcast_list:
                    try:
                        async with db_transaction(db):
                            await db.execute(
                                "UPDATE Votemutes SET broadcast_msgs = ? WHERE vote_id = ?",
                                (json.dumps(bcast_list), vm_key)
                            )
                    except Exception as bcast_err:
                        logger.warning(f"Error persisting broadcast_msgs: {bcast_err}")
            except Exception as e:
                logger.warning(f"Error in _do_votemute_broadcast: {e}")

        asyncio.create_task(_do_votemute_broadcast())
async def _sync_all_votemute_cards(bot, vm_key: str, target_id: int, post_num: int, skip_msg: Optional[Tuple[int, int]] = None, is_expired: bool = False):
    """Synchronizes UI and button counters across all broadcast copies of a votemute card."""
    if not bot:
        return
    async with votemute_lock:
        vm = active_votemutes.get(vm_key)
        if not vm:
            # Resilient DB fallback if bot was restarted or in-memory cache evicted
            try:
                db = await get_pool()
                async with db.execute(
                    "SELECT yes_votes, no_votes, status, created_at, broadcast_msgs FROM Votemutes WHERE vote_id = ?",
                    (vm_key,)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        bcast = []
                        try:
                            bcast = json.loads(row[4]) if row[4] else []
                        except Exception:
                            pass
                        vm = {
                            "created_ts": row[3],
                            "yes_votes": row[0],
                            "no_votes": row[1],
                            "executed": row[2] == 'executed',
                            "rejected": row[2] == 'rejected',
                            "expired": row[2] == 'expired',
                            "status": row[2],
                            "broadcast_msgs": bcast,
                        }
            except Exception:
                pass
        if not vm:
            vm = {}
        created_ts = vm.get("created_ts", time.time())
        yes_votes = vm.get("yes_votes", 0)
        no_votes = vm.get("no_votes", 0)
        executed = vm.get("executed", False)
        rejected = vm.get("rejected", False)
        expired = is_expired or vm.get("expired", False) or vm.get("status") == "expired" or (time.time() - created_ts > VOTE_WINDOW_SEC and not executed and not rejected)
        all_bcast = list(vm.get("broadcast_msgs", []))

    new_text = get_votemute_card_text(post_num, target_id, yes_votes, created_ts, executed, no_votes, rejected, is_expired=expired)
    new_kb = get_votemute_keyboard(target_id, post_num, yes_votes, executed, no_votes, rejected, is_expired=expired)

    for chat_id, msg_id in all_bcast:
        if skip_msg and chat_id == skip_msg[0] and msg_id == skip_msg[1]:
            continue
        try:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption=new_text,
                    reply_markup=new_kb,
                    parse_mode="HTML"
                )
            except TelegramBadRequest as tbe:
                if "message is not modified" in str(tbe).lower():
                    continue
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=new_text,
                    reply_markup=new_kb,
                    parse_mode="HTML"
                )
        except Exception:
            pass
        await asyncio.sleep(0.035)


@votemute_router.callback_query(F.data.startswith("vm_vote:"))
async def callback_votemute_vote(callback: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Handles button click '🔨 За' / '🕊️ Против'.
    Supports 'vm_vote:yes:{token}', 'vm_vote:no:{token}' and legacy 'vm_vote:{token}'.
    """
    if not board_id:
        board_id = "b"

    voter_id = callback.from_user.id
    from common.database import is_shadow_muted as check_db_shadow_muted
    from common.bot_helpers import check_user_is_muted
    db = await get_pool()
    if await check_db_shadow_muted(voter_id, board_id, db=db) or await check_user_is_muted(db, voter_id, board_id):
        await safe_callback_answer(callback, "🔇 Замученным нельзя голосовать в народном вотуме.", show_alert=True)
        return

    # Quorum activity check: > 1 post in last 2 days on this board
    is_eligible, elig_reason = await check_voter_eligibility(voter_id, board_id, db=db)
    if not is_eligible:
        await safe_callback_answer(callback, elig_reason, show_alert=True)
        return

    raw_data = callback.data or ""
    parts = raw_data.split(":")
    if len(parts) == 2:
        # Legacy callback format: "vm_vote:{token}" -> default vote_type = "yes"
        vote_type = "yes"
        token = parts[1]
    elif len(parts) >= 3:
        # Dual choice: "vm_vote:yes:{token}" or "vm_vote:no:{token}"
        vote_type = parts[1].lower()
        token = ":".join(parts[2:])
    else:
        await safe_callback_answer(callback, "❌ Ошибка данных голосования.", show_alert=True)
        return

    # Resolve opaque token -> (target_id, post_num)
    ids = await resolve_votemute_token(token)
    if not ids:
        await safe_callback_answer(callback, "⏳ Срок действия этого голосования истек.", show_alert=True)
        return
    target_id, post_num = ids

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
        bot=callback.bot,
        vote_type=vote_type
    )

    await safe_callback_answer(callback, msg, show_alert=not ok or is_executed)

    # Refresh message card UI
    async with votemute_lock:
        vm_data = active_votemutes.get(vm_key, {})
        created_ts = vm_data.get("created_ts", time.time())
        yes_votes = vm_data.get("yes_votes", current_votes)
        no_votes = vm_data.get("no_votes", 0)
        executed = vm_data.get("executed", is_executed)
        rejected = vm_data.get("rejected", False)
        expired = vm_data.get("expired", False) or vm_data.get("status") == "expired" or (not ok and "истек" in str(msg).lower())

    new_text = get_votemute_card_text(post_num, target_id, yes_votes, created_ts, executed, no_votes, rejected, is_expired=expired)
    new_kb = get_votemute_keyboard(target_id, post_num, yes_votes, executed, no_votes, rejected, is_expired=expired)

    skip_pair = None
    if callback.message:
        skip_pair = (callback.message.chat.id, callback.message.message_id)
        try:
            if callback.message.caption is not None or callback.message.photo:
                await callback.message.edit_caption(caption=new_text, reply_markup=new_kb, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=new_kb, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                try:
                    await callback.message.edit_reply_markup(reply_markup=new_kb)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error updating votemute message card: {e}")

    # Synchronize all other broadcast cards in background
    if callback.bot:
        asyncio.create_task(_sync_all_votemute_cards(callback.bot, vm_key, target_id, post_num, skip_msg=skip_pair))


@votemute_router.callback_query(F.data.startswith("vm_info:"))
async def callback_votemute_info(callback: types.CallbackQuery):
    """Handles click on completed mute info button."""
    token = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    ids = await resolve_votemute_token(token) if token else None
    if ids:
        target_id, post_num = ids
        vm_key = generate_votemute_key(target_id, post_num)
        async with votemute_lock:
            vm = active_votemutes.get(vm_key, {})
        if vm.get("rejected"):
            await safe_callback_answer(callback, "🕊️ Этот анон был полностью оправдан народным судом!", show_alert=True)
            return

    await safe_callback_answer(
        callback,
        "🔒 Этот шиз уже отправлен в ЖЕЛЕЗНЫЙ МУТ на 30 минут решением народного вотума!",
        show_alert=True
    )


@votemute_router.callback_query(F.data == "menu_votemute")
async def callback_menu_votemute(callback: types.CallbackQuery):
    """Displays quick info about votemute in menu."""
    info_text = (
        "🗳️ <b>НАРОДНЫЙ ВОТУМ / ШИЗО-МУТ (/votemute, /voteban)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Демократический инструмент саморегуляции борды:\n"
        "• Ответь <code>/votemute</code> или <code>/voteban</code> на пост нарушителя.\n"
        "• Если <b>5 уникальных анонов</b> нажмут «За» в течение 10 минут — нарушитель получит "
        "<b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b>.\n"
        "• 🚫 <b>Особенность:</b> Этот мут НЕЛЬЗЯ снять за шекели через /shop (взятки заблокированы) и админские команды!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_help")]
    ])
    try:
        await callback.message.edit_text(info_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await safe_callback_answer(callback)
