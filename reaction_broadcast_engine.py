# -*- coding: utf-8 -*-
"""
reaction_broadcast_engine.py — Motivational Reaction Engagement Broadcast for ТГАЧ

Broadcasts cynical, authentic 2ch motivational messages with banners directly
to users (Direct Messages / PM) urging them to actively react to posts in the feed.
Explains the economic and social mechanics:
- Likes / Fire / Base: +15-30 ₪ shekels to author balance, 5+ likes elevates to "Best" channel.
- Dislikes / Poop / Vomit: -8-16 ₪ penalty deducted from author balance, drowned in sewage.
- Clown: marks clown posters, tears off masks.
"""

import os
import json
import time
import random
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from aiogram import Bot, types
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from banner_manager import get_banner_file, is_video_banner, send_banner_message
from common.database import get_pool

logger = logging.getLogger("reaction_broadcast")

PROJECT_ROOT = Path(__file__).resolve().parent
STATE_FILE = PROJECT_ROOT / "data" / "reaction_broadcast_state.json"

# Default scheduler interval: 12 hours (43200 seconds)
DEFAULT_BROADCAST_INTERVAL_SECONDS = 43200
PACING_DELAY_BETWEEN_USERS = 0.05  # Safe rate limit pacing (20 msgs/sec max)

# 32 unique, cynical, toxic, board-authentic motivational texts
REACTION_MOTIVATION_TEXTS: List[str] = [
    (
        "👀 <b>Анон, ты опять сидишь и молча скроллишь ленту как куколд?</b>\n\n"
        "Напоминаем базовые законы борды:\n"
        "🔥 <b>Лайк / Огонь / База</b> — ты насыпаешь автору <b>+15–30 ₪</b> шекелей в карман, а от 5 лайков пост взлетает в канал <b>«Лучшее»</b>.\n"
        "💩 <b>Говно / Дизлайк / Рвота</b> — ты сдираешь с высерка <b>-8–16 ₪</b> и смываешь его в парашу.\n"
        "🤡 <b>Клоун</b> — вешает на дебила несмываемое клеймо.\n\n"
        "Твой палец решает, кто король треда, а кто опущенный. <b>Ставь реакции на посты — суди этот биомусор!</b>"
    ),
    (
        "⚡️ <b>Хватит жрать контент в одну харю, анонимус!</b>\n\n"
        "Борда — это не телевизор, здесь каждый высер оценивается шекелями:\n"
        "• Увидел годную пасту или разъёб? Влепи <b>👍</b> или <b>🔥</b> — автор поднимет шекелей на новый шмот в <code>/shop</code>.\n"
        "• Увидел унылый соевый высер? Залепи <b>👎</b> или <b>💩</b> — спиши с клоуна бабки на балансе.\n\n"
        "<i>Не оставляй посты без оценки. Голодный автор постит хуйню, сытый — базу!</i>"
    ),
    (
        "⚖️ <b>Судилище ТГАЧА: Твой палец — твой приговор</b>\n\n"
        "Каждый раз, когда ты лениво пропускаешь пост без реакции, где-то ликует бездарь:\n"
        "💰 <b>Лайкнул</b> — задонатил автору шекелей прямо из воздуха (+15–30 ₪).\n"
        "🪓 <b>Обосрал (💩 / 🤮 / 👎)</b> — загнал ничтожество в долговую яму и минуса (-8–16 ₪).\n"
        "🎪 <b>Влепил клоуна (🤡)</b> — сорвал маску с циркового уебана.\n\n"
        "<b>Жми на эмодзи под постами. Управляй балансом и судьбами аборигенов!</b>"
    ),
    (
        "💸 <b>Перераспределение шекелей на борде: Анон, рули экономикой!</b>\n\n"
        "Ты думал, реакции тут просто картинки для зумеров? Хуй там плавал!\n"
        "• Лайк/Огонь — это <b>прямой кэш</b> автору (+15..30 ₪). Дай нормальному пацану подняться.\n"
        "• Дизлайк/Говно — это <b>жестокий штраф</b> (-8..16 ₪) за засорение ленты твоей драгоценной борды.\n\n"
        "Видишь годноту? Поддержи шекелем. Видишь шизофазию? Накорми говном с лопаты. <b>Ставь реакции, не будь овощем!</b>"
    ),
    (
        "🚨 <b>Внимание, сыч! Обнаружен пассивный скроллинг!</b>\n\n"
        "Ты пролистал уже сотню постов и не нажал ни одной реакции?\n"
        "Ты вообще живой там или тебя парализовало от сычевания?\n\n"
        "1. За <b>5 лайков</b> пост попадает на доску почёта в канал «Лучшее».\n"
        "2. За <b>дизлайки и говно</b> автор теряет кровно заработанные шекели.\n"
        "3. Реакция 🤡 опускает статус постироника до уровня биоотходов.\n\n"
        "<i>Включи пальцы, ставь реакции на посты в ленте! Карай и милуй!</i>"
    ),
    (
        "🎪 <b>Цирк уродов требует судейства!</b>\n\n"
        "Пока ты молчишь, графоманы чувствуют безнаказанность. Напоминаем инструмент карателя:\n"
        "💩 <b>Кусок говна</b> — лучший ответ на шизопостинг. Минус шекели автору гарантированы.\n"
        "🤡 <b>Клоунский нос</b> — публичная порка в прямом эфире.\n"
        "🔥 <b>База / Огонь</b> — насыпать шекелей тому, кто реально выдал базу.\n\n"
        "<b>Ткни в реакцию прямо сейчас. Не дай долбоёбам захватить ленту!</b>"
    ),
    (
        "🩸 <b>Шекелевая резня в ленте: Сделай богатым брата или раздень врага!</b>\n\n"
        "Твой клик по реакции — это финансовый перевод:\n"
        "• Палец вверх (👍/🔥) = <b>+15..30 ₪</b> на счёт постера. Скинься на пиво автору шедевра.\n"
        "• Палец вниз (👎/💩) = <b>-8..16 ₪</b> с баланса бездаря. Ограбь обоссанного нытика без суда и следствия.\n\n"
        "<i>Зачем молчать, если можно раскулачивать или обогащать? Реагируй!</i>"
    ),
    (
        "🏆 <b>Канал «Лучшее» пустует без твоего голоса, анон!</b>\n\n"
        "Знаешь, как посты попадают в пантеон славы ТГАЧА?\n"
        "Всего <b>5 честных лайков</b> от анонов — и пост навсегда улетает в золотой фонд борды!\n\n"
        "Увидел разъёб? Не жлобись, влепи <b>👍 / 🔥 / ❤️</b>.\n"
        "Увидел рак, убивающий /b/? Закидай <b>💩 / 🤮 / 🤡</b> и утопи в параше.\n\n"
        "<b>Твой голос строит повестку. Голосуй реакциями!</b>"
    ),
    (
        "🪓 <b>Увидел говно? Не терпи — опусти автора на шекели!</b>\n\n"
        "Хватит молча кривиться от сопливых историй про невзаимную любовь и прочую хуету.\n"
        "Каждый твой <b>👎 / 💩 / 🤮</b> снимает с нытика шекели и приближает его к банкротству.\n\n"
        "А если кто-то запостил концентрированный вин — навали <b>🔥</b> и сделай его богачом.\n"
        "<b>Борда — это дарвинизм. Очищай генофонд реакциями!</b>"
    ),
    (
        "💡 <b>Урок финансовой грамотности от Киберчеда:</b>\n\n"
        "«Анон, который не ставит реакции — хуже опущенного куколда».\n\n"
        "Каждое нажатие на эмодзи запускает транзакцию:\n"
        "🟢 Лайк: автор богатеет на <b>+15–30 ₪</b>.\n"
        "🔴 Дизлайк/Говно: автор беднеет на <b>-8–16 ₪</b>.\n"
        "🟡 Клоун: автор обтекает при всем честном народе.\n\n"
        "<b>Открой ленту, найди свежий пост и влепи реакцию по справедливости!</b>"
    ),
    (
        "🎯 <b>Ты — палач, судья и спонсор этой борды</b>\n\n"
        "Пока ты ленишься тыкнуть в экран:\n"
        "— Годный тред тонет без шекелей и внимания.\n"
        "— Шитпостер-копрофил безнаказанно плодит уныние.\n\n"
        "Исправь это: поставь <b>🔥</b> базе и вмажь <b>💩</b> тухлому высеру.\n"
        "<i>Одно движение пальца меняет баланс сил. Действуй!</i>"
    ),
    (
        "📉 <b>Загони тупого автора в кредитное рабство одним дизлайком!</b>\n\n"
        "Ты знал, что при отрицательном балансе анон даже <code>/shop</code> открыть не может?\n"
        "Видишь графоманию без тени юмора? Влепи <b>👎</b> или <b>💩</b>.\n"
        "Баланс уйдёт в минус, а спесь слетит в секунду.\n\n"
        "А тех, кто тащит ламповость и угар — осыпай <b>👍 / 🔥</b>.\n"
        "<b>Власть в твоих руках. Раздавай по заслугам!</b>"
    ),
    (
        "🛡 <b>Хватит быть призраком тредов!</b>\n\n"
        "Читать посты и ничего не нажимать — удел пассивных зрителей.\n"
        "Ты здесь не зритель, ты полноправный житель ТГАЧА.\n\n"
        "⚡️ Поддержи автора шекелями через <b>👍/🔥</b>.\n"
        "💀 Отрежь кислород тупорылым через <b>👎/💩/🤡</b>.\n\n"
        "<b>Оставь свой след под каждым постом в ленте!</b>"
    ),
    (
        "🎰 <b>Эмодзи-казино ТГАЧА: Раскрути автора на шекели!</b>\n\n"
        "Твоя реакция — это прямой спин в кармане постера:\n"
        "💎 Джекпот (👍/🔥/❤️) — начисление солидных шекелей автору.\n"
        "💣 Скам (👎/💩/🤮) — мгновенный штраф и списывание баланса.\n"
        "🤡 Зеро (🤡) — позор на всю деревню.\n\n"
        "<b>Испытай посты на прочность — влепи реакцию на последний высер!</b>"
    ),
    (
        "💀 <b>Молчаливый анон хуже мента и модератора</b>\n\n"
        "Если ты не ставишь реакции, алгоритм не понимает, что есть база, а что кал.\n"
        "• Навали <b>🔥</b> за годноту — выведи тред в топ.\n"
        "• Навали <b>💩</b> за шлак — отправь автора мыть парашу.\n\n"
        "<i>Шекели сами себя не распределят. Реагируй на каждый прочитанный пост!</i>"
    ),
    (
        "👑 <b>Сделай анона олигархом или нищим бродягой!</b>\n\n"
        "Механика реакций работает прямо сейчас:\n"
        "Нажал <b>👍</b> — пополнил кошелёк автора на 15–30 ₪.\n"
        "Нажал <b>💩</b> — оштрафовал на 8–16 ₪ за бездарность.\n"
        "Собрал <b>5 лайков</b> — пост улетает в элитный канал «Лучшее»!\n\n"
        "<b>Кому дать денег, а у кого отобрать — решаешь ты. Кликай реакции!</b>"
    ),
    (
        "🧤 <b>Раздавай лещей и подарки не выходя из ленты!</b>\n\n"
        "Зачем писать простыню текста с оскорблениями, если есть кнопка <b>💩</b>?\n"
        "Она бьёт прямо по кошельку обидчика, списывая шекели.\n"
        "А для братьев по разуму держи наготове <b>🔥</b> и <b>⚡️</b>.\n\n"
        "<b>Экономь буквы — выражай мнение эмодзи-ударами!</b>"
    ),
    (
        "🧨 <b>Разъеби шитпостера финансово!</b>\n\n"
        "Каждый раз, когда кто-то постит тухлый баян или сопливый высер:\n"
        "Не спорь в реплаях. Просто нажми <b>👎</b> или <b>💩</b>.\n"
        "Шекели испарятся с его счета быстрее, чем остатки его интеллекта.\n\n"
        "<i>А если пост заставил хрюкнуть сучарой — жми 👍. Корми таланты!</i>"
    ),
    (
        "⚔️ <b>Бордовая дуэль в один клик</b>\n\n"
        "Ты можешь не стрелять из Мут-Гана и не вызывать на нож.\n"
        "Достаточно одной меткой реакции:\n"
        "— <b>💩/🤮</b> сжигает шекели автора.\n"
        "— <b>🤡</b> выставляет на посмешище.\n"
        "— <b>🔥/👍</b> прокачивает братишку.\n\n"
        "<b>Твой палец — заряженный револьвер. Стреляй реакциями по постам!</b>"
    ),
    (
        "📈 <b>Криптономика ТГАЧА: Инвестируй шекели в годных авторов!</b>\n\n"
        "Лайк под постом — это не пустое сердечко, это реальная валюта ₪.\n"
        "Поддержал автора → автор купил пистолет в <code>/shop</code> → пристрелил спамера.\n"
        "Круговорот справедливости начинается с твоего лайка!\n\n"
        "<b>Не жадничай: годным постам — лайки, унылым — говно!</b>"
    ),
    (
        "🧠 <b>Тест на IQ для обитателя борды:</b>\n\n"
        "1. Увидел хороший пост — поставил <b>👍 / 🔥</b> (+15–30 ₪ автору).\n"
        "2. Увидел хуйню — поставил <b>👎 / 💩</b> (-8–16 ₪ автору).\n"
        "3. Прочитал и пролистал мимо — диагноз: одноклеточное.\n\n"
        "<b>Докажи, что у тебя есть мозги и вкус. Реагируй на посты!</b>"
    ),
    (
        "🔥 <b>База или параша? Решать только тебе, анон!</b>\n\n"
        "Пока ты пассивно втыкаешь в экран, другие решают судьбу ленты.\n"
        "• Хочешь видеть больше годного контента? Наваливай <b>👍 и 🔥</b>.\n"
        "• Хочешь утопить нытьё и сопли? Жми <b>💩 и 🤮</b>.\n\n"
        "<i>5 лайков — и пост в канале «Лучшее». Выведи своих кумиров в топ!</i>"
    ),
    (
        "💰 <b>Бесплатный способ стать меценатом или грабителем</b>\n\n"
        "Тебе не нужно тратить свои шекели, чтобы наказать или наградить:\n"
        "Система начисляет автору шекели за твои лайки из воздуха!\n"
        "И система же списывает с него шекели за твои дизлайки!\n\n"
        "<b>Ты распоряжаешься чужими деньгами бесплатно. Пользуйся властью — ставь реакции!</b>"
    ),
    (
        "🎪 <b>Объявляется охота на клоунов!</b>\n\n"
        "Заметил в ленте персонажа, который строит из себя сверхразума?\n"
        "Лепи <b>🤡</b> без колебаний. Клоунский нос не отмоешь.\n"
        "А если человек выдал фундаментальную аналитику — <b>🔥</b> и только <b>🔥</b>.\n\n"
        "<b>Очисти борду от клоунады. Ставь правильные эмодзи!</b>"
    ),
    (
        "⚡️ <b>Хватит экономить клики, анон! Они бесплатные!</b>\n\n"
        "За каждый твой лайк автор получает до <b>+30 ₪</b> шекелей.\n"
        "За каждый дизлайк — теряет до <b>-16 ₪</b>.\n"
        "Ты буквально управляешь благосостоянием всех, кто пишет в боте.\n\n"
        "<i>Зайди в ленту и раздай всем по заслугам прямо сейчас!</i>"
    ),
    (
        "🧊 <b>Не будь холодным бревном — согрей автора огоньком!</b>\n\n"
        "Анон пыхтел, рожал пасту, придумывал панчи, а ты прочитал и зевнул?\n"
        "Влепи <b>🔥</b> или <b>❤️</b> — накорми голодного творца шекелями.\n"
        "Ну а если высер тухлый — не стесняйся, <b>💩</b> всегда под рукой.\n\n"
        "<b>Живая борда требует живых реакций. Жми эмодзи!</b>"
    ),
    (
        "🔨 <b>Кувалда правосудия в твоих руках</b>\n\n"
        "У нас тут прямая демократия шекелей:\n"
        "Нравится пост → <b>👍 / 🔥</b> (автор богатеет).\n"
        "Бесит автор → <b>👎 / 💩</b> (автор нищает).\n"
        "Пост шедевр → 5 лайков выводят его в <b>«Лучшее»</b> на века.\n\n"
        "<b>Не сиди сложа руки. Суди авторов прямо в ленте!</b>"
    ),
    (
        "☠️ <b>Твой дизлайк может стать фатальным для баланса шпиона!</b>\n\n"
        "Когда автор уходит в глубокий минус из-за дизлайков, он теряет права на плюшки магазина.\n"
        "Очисти ленту от чуханов и калоедов: видишь чушь — дави <b>👎/💩</b>.\n"
        "Своих пацанов с базы — поддерживай щедрыми <b>👍/🔥</b>.\n\n"
        "<b>Включай режим цензора. Ставь реакции!</b>"
    ),
    (
        "🪞 <b>Зеркало борды: Каков поп, таков и приход</b>\n\n"
        "Если в ленте уныло — это потому, что ты не топишь дерьмо дизлайками\n"
        "и не поднимаешь годных авторов шекелями за лайки!\n\n"
        "Всё просто:\n"
        "— Корми годных шекелями (<b>👍/🔥</b>).\n"
        "— Топи унылых в параше (<b>💩/👎</b>).\n\n"
        "<b>Формируй ленту сам — ставь реакции на каждый пост!</b>"
    ),
    (
        "💎 <b>Открой охоту за сокровищами в канале «Лучшее»!</b>\n\n"
        "Только лучшие посты попадают в зал славы, набрав <b>5+ положительных реакций</b>.\n"
        "Увидел алмаз среди кучи навоза? Влепи <b>👍</b> или <b>❤️</b>!\n"
        "Помоги шедевру добраться до канала «Лучшее» и одари автора шекелями.\n\n"
        "<b>Твой лайк может стать решающим пятым голосом. Не зевай!</b>"
    ),
    (
        "🚀 <b>Включай турбо-судейство в ленте!</b>\n\n"
        "Быстрый гайд для тех, кто в танке:\n"
        "1. <b>👍 / 🔥</b> = +15..30 ₪ автору (заслужил уважение пацанов).\n"
        "2. <b>👎 / 💩</b> = -8..16 ₪ автору (оплати утилизацию твоего высера).\n"
        "3. <b>🤡</b> = публичный позор без права на помилование.\n\n"
        "<b>Тыкай по эмодзи под постами. Управляй хаосом борды!</b>"
    ),
    (
        "🍻 <b>Шекели за базу, сажа за парашу: Закон ТГАЧА</b>\n\n"
        "Никакой цензуры, только естественный отбор через эмодзи:\n"
        "• Поставил лайк — поддержал брата монетой ₪.\n"
        "• Поставил какашку — обнулил тупорылого чухана.\n"
        "• Набралось 5 лайков — весь ТГАЧ видит шедевр в «Лучшем».\n\n"
        "<b>Хватит быть зрителем. Ставь реакции — верши историю доски!</b>"
    )
]


def _load_state() -> Dict[str, Any]:
    """Loads broadcast state (timestamp, counts, index, blocked users) from disk."""
    default_state = {
        "last_broadcast_timestamp": 0.0,
        "total_broadcasts": 0,
        "last_text_index": -1,
        "total_delivered": 0,
        "total_failed": 0,
        "total_forbidden": 0,
        "blocked_user_ids": []
    }
    if not STATE_FILE.exists():
        return default_state
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for k, v in default_state.items():
                    data.setdefault(k, v)
                return data
    except Exception as e:
        logger.warning(f"[reaction_broadcast] Failed to read state file: {e}")
    return default_state


def _save_state(state: Dict[str, Any]) -> bool:
    """Atomically saves broadcast state to disk."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp_file.replace(STATE_FILE)
        return True
    except Exception as e:
        logger.warning(f"[reaction_broadcast] Failed to save state file: {e}")
        return False


def get_next_motivation_text() -> Tuple[int, str]:
    """
    Selects the next motivational text using pseudo-random rotation
    without immediate repeating.
    """
    state = _load_state()
    last_idx = state.get("last_text_index", -1)
    total_texts = len(REACTION_MOTIVATION_TEXTS)
    
    candidates = [i for i in range(total_texts) if i != last_idx]
    chosen_idx = random.choice(candidates) if candidates else 0
    
    return chosen_idx, REACTION_MOTIVATION_TEXTS[chosen_idx]


async def get_reaction_broadcast_recipients(limit: Optional[int] = None, exclude_blocked: bool = True) -> List[int]:
    """
    Fetches active direct message recipients from the Users table.
    Filters:
    - user_id > 0 (valid personal Telegram user ID, strictly Direct Messages / PM)
    - Excludes known blocked_user_ids (users who deleted chat or blocked bot)
    - Orders by recent activity or posts count to prioritize engaged users.
    """
    try:
        db = await get_pool()
        query = """
            SELECT user_id 
            FROM Users 
            WHERE user_id > 0 
            GROUP BY user_id 
            ORDER BY MAX(COALESCE(posts_count, 0)) DESC, MAX(COALESCE(created_at, 0)) DESC
        """
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"
            
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            recipients = [int(row[0]) for row in rows if row and row[0] and int(row[0]) > 0]
            
            if exclude_blocked:
                state = _load_state()
                blocked_set = set(state.get("blocked_user_ids", []))
                if blocked_set:
                    before_cnt = len(recipients)
                    recipients = [uid for uid in recipients if uid not in blocked_set]
                    logger.info(f"[reaction_broadcast] Filtered out {before_cnt - len(recipients)} previously blocked users")
                    
            logger.info(f"[reaction_broadcast] Fetched {len(recipients)} eligible recipients from database")
            return recipients
    except Exception as e:
        logger.error(f"[reaction_broadcast] Failed to query recipients from DB: {e}")
        return []


async def send_single_reaction_motivation(
    bot: Bot,
    user_id: int,
    text: str,
    category: str = "all"
) -> str:
    """
    Sends a motivational message with banner to a single user in PM.
    Resiliently handles Telegram exceptions without raising errors to caller.
    
    Returns:
    - 'delivered': message delivered successfully
    - 'forbidden': user blocked bot or deleted chat (no retries)
    - 'bad_request': chat not found or invalid user
    - 'retry_failed': flood wait / rate limit exceeded after retry
    - 'error': generic exception
    """
    max_retries = 2
    for attempt in range(max_retries):
        try:
            msg = await send_banner_message(
                bot=bot,
                chat_id=user_id,
                caption=text,
                category=category,
                parse_mode="HTML"
            )
            if msg:
                return "delivered"
            # send_banner_message returns None when user blocked bot, chat not found, or deactivated
            return "forbidden"
        except TelegramRetryAfter as e:
            wait_time = float(getattr(e, "retry_after", 3) or 3) + 1.0
            logger.warning(f"[reaction_broadcast] TelegramRetryAfter {wait_time}s for user {user_id} (attempt {attempt+1})")
            if attempt < max_retries - 1 and wait_time <= 60.0:
                await asyncio.sleep(wait_time)
                continue
            return "retry_failed"
        except TelegramForbiddenError:
            logger.debug(f"[reaction_broadcast] User {user_id} blocked bot (TelegramForbiddenError)")
            return "forbidden"
        except TelegramBadRequest as e:
            err_str = str(e).lower()
            if any(term in err_str for term in ("chat not found", "user is deactivated", "bot was blocked", "deactivated")):
                return "forbidden"
            logger.debug(f"[reaction_broadcast] BadRequest for user {user_id}: {e}")
            return "bad_request"
        except TelegramNetworkError as e:
            logger.warning(f"[reaction_broadcast] Network error for {user_id} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5)
                continue
            return "network_error"
        except Exception as e:
            logger.warning(f"[reaction_broadcast] Unexpected error delivering to {user_id}: {e}")
            return "error"
            
    return "failed"


async def send_reaction_motivation_broadcast(
    bot: Bot,
    force: bool = False,
    max_recipients: Optional[int] = None,
    specific_user_ids: Optional[List[int]] = None,
    category: str = "all"
) -> Dict[str, Any]:
    """
    Executes a motivational reaction broadcast to all bot users in PM.
    
    Args:
        bot: aiogram Bot instance
        force: If True, ignores the 12-hour cooldown (e.g. for manual admin command)
        max_recipients: Optional upper bound on users to message (e.g. for testing)
        specific_user_ids: Optional explicit recipient list (for dry runs or tests)
        category: Banner category to pick from (default 'all' or 'motivation')
        
    Returns:
        Structured result dict with delivery metrics and status.
    """
    now = time.time()
    state = _load_state()
    last_ts = state.get("last_broadcast_timestamp", 0.0)
    elapsed = now - last_ts
    
    if not force and elapsed < DEFAULT_BROADCAST_INTERVAL_SECONDS:
        rem_sec = int(DEFAULT_BROADCAST_INTERVAL_SECONDS - elapsed)
        logger.info(f"[reaction_broadcast] Skipped: cooldown active, {rem_sec}s remaining")
        return {
            "status": "cooldown",
            "message": f"Кулдаун активен. Осталось: {rem_sec // 3600}ч {(rem_sec % 3600) // 60}м.",
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": rem_sec
        }
        
    # Pick next motivational text
    text_idx, broadcast_text = get_next_motivation_text()
    
    # Resolve recipients
    if specific_user_ids is not None:
        recipients = [uid for uid in specific_user_ids if uid > 0]
    else:
        recipients = await get_reaction_broadcast_recipients(limit=max_recipients)
        
    if not recipients:
        logger.warning("[reaction_broadcast] No recipients found for broadcast")
        return {
            "status": "no_recipients",
            "message": "Нет активных пользователей для рассылки.",
            "delivered": 0,
            "failed": 0
        }
        
    logger.info(f"[reaction_broadcast] Starting broadcast of text #{text_idx+1} to {len(recipients)} users...")
    
    delivered = 0
    forbidden = 0
    failed = 0
    blocked_ids_set = set(state.get("blocked_user_ids", []))
    
    for i, user_id in enumerate(recipients):
        res = await send_single_reaction_motivation(
            bot=bot,
            user_id=user_id,
            text=broadcast_text,
            category=category
        )
        
        if res == "delivered":
            delivered += 1
            if user_id in blocked_ids_set:
                blocked_ids_set.discard(user_id)
        elif res == "forbidden":
            forbidden += 1
            blocked_ids_set.add(user_id)
        else:
            failed += 1
            
        # Pacing between messages to prevent Telegram rate limits
        if (i + 1) % 25 == 0:
            logger.info(f"[reaction_broadcast] Progress: {i+1}/{len(recipients)} (delivered: {delivered}, forbidden: {forbidden}, failed: {failed})")
            
        await asyncio.sleep(PACING_DELAY_BETWEEN_USERS)
        
    # Update and persist state
    state["last_broadcast_timestamp"] = now
    state["total_broadcasts"] = state.get("total_broadcasts", 0) + 1
    state["last_text_index"] = text_idx
    state["total_delivered"] = state.get("total_delivered", 0) + delivered
    state["total_failed"] = state.get("total_failed", 0) + failed
    state["total_forbidden"] = state.get("total_forbidden", 0) + forbidden
    state["blocked_user_ids"] = sorted(list(blocked_ids_set))
    _save_state(state)
    
    logger.info(
        f"[reaction_broadcast] Completed! Delivered: {delivered}, "
        f"Forbidden/Blocked: {forbidden}, Failed: {failed} out of {len(recipients)}"
    )
    
    return {
        "status": "success",
        "delivered": delivered,
        "forbidden": forbidden,
        "failed": failed,
        "total_recipients": len(recipients),
        "text_index": text_idx,
        "text_preview": broadcast_text[:120] + "...",
        "timestamp": now
    }


async def reaction_motivation_broadcast_loop(
    bot_provider: Any,
    interval_seconds: int = DEFAULT_BROADCAST_INTERVAL_SECONDS
):
    """
    Background daemon loop that periodically triggers the motivational broadcast
    every 12 hours (43200 seconds). Survives restarts by reading last timestamp from state file.
    
    bot_provider can be an aiogram.Bot instance or a callable returning an aiogram.Bot.
    """
    logger.info(f"[reaction_broadcast] Background daemon initialized (interval: {interval_seconds}s)")
    
    # Wait 60 seconds on initial startup before first check to let bot finish initialization
    await asyncio.sleep(60)
    
    while True:
        try:
            bot = bot_provider() if callable(bot_provider) else bot_provider
            if not bot:
                await asyncio.sleep(60)
                continue
                
            now = time.time()
            state = _load_state()
            last_ts = state.get("last_broadcast_timestamp", 0.0)
            elapsed = now - last_ts
            
            if elapsed >= interval_seconds:
                logger.info("[reaction_broadcast] Scheduled interval reached. Triggering broadcast...")
                res = await send_reaction_motivation_broadcast(bot=bot, force=False)
                logger.info(f"[reaction_broadcast] Auto-broadcast completed: {res.get('status')}")
                # Sleep interval after broadcast
                await asyncio.sleep(interval_seconds)
            else:
                sleep_need = max(60.0, float(interval_seconds - elapsed))
                logger.info(f"[reaction_broadcast] Next scheduled run in {int(sleep_need // 3600)}h {int((sleep_need % 3600) // 60)}m (sleeping {int(sleep_need)}s)")
                await asyncio.sleep(sleep_need)
                
        except asyncio.CancelledError:
            logger.info("[reaction_broadcast] Loop cancelled. Exiting.")
            raise
        except Exception as e:
            logger.exception(f"[reaction_broadcast] Exception in background loop: {e}")
            await asyncio.sleep(300)


async def handle_broadcast_reactions_command(
    message: types.Message,
    is_admin_check_func=None
) -> None:
    """
    Admin command handler for /broadcast_reactions.
    Allows administrators to manually fire the reaction motivation broadcast.
    Supports optional parameter:
    - /broadcast_reactions test -> sends only to the admin themselves as a test preview.
    - /broadcast_reactions force -> forces broadcast to all users bypassing cooldown.
    """
    uid = message.from_user.id if message.from_user else 0
    if not uid:
        return
        
    # Admin verification
    is_adm = False
    if is_admin_check_func:
        is_adm = is_admin_check_func(uid)
    else:
        try:
            from common.config import ADMIN_IDS
            is_adm = uid in ADMIN_IDS
        except Exception:
            pass
            
    if not is_adm:
        await message.reply("❌ <b>Доступ запрещен.</b> Команда только для администрации ТГАЧА.", parse_mode="HTML")
        return
        
    cmd_args = (message.text or "").strip().split()
    subcmd = cmd_args[1].lower() if len(cmd_args) > 1 else ""
    
    if subcmd == "test":
        await message.reply("⏳ <b>Тестовая отправка в ваш ЛС...</b>", parse_mode="HTML")
        res = await send_reaction_motivation_broadcast(
            bot=message.bot,
            force=True,
            specific_user_ids=[uid]
        )
        await message.reply(
            f"✅ <b>Тестовый баннер и мотивация доставлены!</b>\n"
            f"Статус: <code>{res.get('status')}</code>\n"
            f"Текст #{res.get('text_index', 0) + 1}:\n<i>{res.get('text_preview', '')}</i>",
            parse_mode="HTML"
        )
        return
        
    force_run = (subcmd == "force") or True  # Admin command defaults to force=True
    
    await message.reply(
        "🚀 <b>Запуск мотивационной рассылки реакций по всем пользователям бота (ЛС)...</b>\n"
        "<i>Пожалуйста, подождите, идёт отправка баннеров с контролем флуда...</i>",
        parse_mode="HTML"
    )
    
    res = await send_reaction_motivation_broadcast(
        bot=message.bot,
        force=force_run
    )
    
    if res.get("status") == "cooldown":
        await message.reply(
            f"⚠️ <b>Рассылка отклонена по кулдауну:</b>\n{res.get('message')}\n\n"
            f"<i>Для принудительного запуска используйте:</i> <code>/broadcast_reactions force</code>",
            parse_mode="HTML"
        )
        return
        
    report = (
        f"🏁 <b>Мотивационная рассылка реакций завершена!</b>\n\n"
        f"📊 <b>Результаты доставки:</b>\n"
        f"• Всего получателей: <b>{res.get('total_recipients', 0)}</b>\n"
        f"• Успешно доставлено: <b>{res.get('delivered', 0)}</b>\n"
        f"• Заблокировали бота (Forbidden): <b>{res.get('forbidden', 0)}</b>\n"
        f"• Ошибки доставки: <b>{res.get('failed', 0)}</b>\n\n"
        f"📝 <b>Текст вызова #{res.get('text_index', 0) + 1}:</b>\n"
        f"<i>{res.get('text_preview', '')}</i>"
    )
    await message.reply(report, parse_mode="HTML")
