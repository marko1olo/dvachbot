# -*- coding: utf-8 -*-
"""
daily_abu_airdrop_engine.py — Ежесуточный честный аирдроп Фонда Абу + грант ньюфагам.

Два независимых механизма:
1. DAILY FAIR AIRDROP (run once per 24h):
   - Квалификация: автор написал > 2 постов за последние 24 часа (НЕ теневых).
   - Выбор победителей: random.sample с РАВНЫМИ шансами — ни один спамер не имеет
     преимущества перед тем, кто написал 3 хороших поста.
   - Пул: 5 000 ₪ × N победителей (min 3, max 10), списывается из Фонда Абу.
   - Уведомление: ЛС + алерт в БД + публичный анонс в /b/ и /thread/.

2. NEWBIE FIRST POST GRANT (вызывается при публикации каждого поста):
   - Условие: posts_count <= 3 после текущего поста И грант ещё не выдавался
     (флаг `newbie_abu_grant` в Users.active_items).
   - Награда: 500 ₪ из Фонда Абу.
   - Уведомление: ЛС пользователю.
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot

logger = logging.getLogger("daily_abu_airdrop")

MSK = timezone(timedelta(hours=3))

# ─── Конфиг ───────────────────────────────────────────────────────────────────
DAILY_MIN_POSTS_QUALIFY = 2          # > 2 постов за 24ч для участия в аирдропе
DAILY_WINNER_COUNT_MIN = 3           # Минимум победителей
DAILY_WINNER_COUNT_MAX = 10          # Максимум победителей
DAILY_PRIZE_PER_WINNER = 5_000       # Шекелей на победителя
DAILY_INTERVAL_SECONDS = 86400       # Раз в 24ч
DAILY_FIRST_RUN_DELAY = 900          # 15 минут до первого запуска

NEWBIE_GRANT_AMOUNT = 500            # Шекелей ньюфагу за первые посты
NEWBIE_GRANT_MAX_POSTS = 3           # Грант выдается при posts_count <= этого числа

# ─── Тексты публичных анонсов ──────────────────────────────────────────────────
DAILY_BOARD_TEMPLATES = [
    {
        "title": "🎰 <b>ЕЖЕСУТОЧНЫЙ РАСПИЛ КАЗНЫ ИМ. ВЕЛИКОГО АБУ</b> 🎰",
        "intro": (
            "Товарищи дегенераты! Пока вы проводили очередные сутки в цифровой клоаке,\n"
            "наш беспристрастный генератор случайных чисел выбрал <b>{winner_count}</b> счастливчиков\n"
            "из <b>{pool_size}</b> достойных шитпостеров.\n\n"
            "Абу расчехлил чемодан с шекелями прямо на яхте:"
        ),
        "footer": "💡 <i>Завтра лотерея снова. Пиши посты — повышай шансы. Или нет, шансы всё равно равные, ха!</i>"
    },
    {
        "title": "💸 <b>ВЕРТОЛЁТНЫЕ ДЕНЬГИ ОТ КОРПОРАЦИИ «АБУ И СЫНОВЬЯ»</b> 💸",
        "intro": (
            "Внимание! Ежедневный сброс гуманитарной помощи над территорией борды.\n"
            "Из <b>{pool_size}</b> грамотных анонов, которые не ленились писать сегодня,\n"
            "жребий определил <b>{winner_count}</b> получателей матпомощи:\n"
        ),
        "footer": "💡 <i>Лотерея честная. Напиши хоть 3 поста, хоть 300 — шанс одинаковый. Завтра ещё раз.</i>"
    },
    {
        "title": "🛥️ <b>АБУ БРОСАЕТ ШЕКЕЛИ С ЯХТЫ В ТОЛПУ</b> 🛥️",
        "intro": (
            "Жирный олигарх Абу вышел на палубу яхты и с видом щедрого барина\n"
            "отобрал <b>{winner_count}</b> рандомных работяг из <b>{pool_size}</b> достойных.\n"
            "Равные шансы, никакого блата — чистый рандом:\n"
        ),
        "footer": "💡 <i>Спишем из казны и не заплачем. Пиши посты сегодня — получи свой билет на завтра.</i>"
    },
    {
        "title": "🏦 <b>ДНЕВНОЙ ТРАНШ ИЗ ОФФШОРНОГО СЧЁТА АБУСТАНА</b> 🏦",
        "intro": (
            "ОБЭП не смотрит, налоговая спит, можно распиливать.\n"
            "Из <b>{pool_size}</b> активных анонов суточной борды рандом выбрал\n"
            "<b>{winner_count}</b> нуждающихся в финансовой инъекции:\n"
        ),
        "footer": "💡 <i>Деньги на балансе. Трать умно. Или спусти в /casino — мы понимаем.</i>"
    },
    {
        "title": "🐀 <b>СУТОЧНАЯ ПАЙКА ДЛЯ ЖИТЕЛЕЙ ЦИФРОВЫХ ПОДВАЛОВ</b> 🐀",
        "intro": (
            "Очередные сутки провёл на борде и не умер — молодец, держи паёк.\n"
            "Сегодня из <b>{pool_size}</b> активных нищуков жребий выдал шекели\n"
            "<b>{winner_count}</b> счастливым случайным анонам:\n"
        ),
        "footer": "💡 <i>Казна немного полегчала. Завтра всё начнётся снова. Пиши больше 2 постов — будешь в пуле.</i>"
    },
    {
        "title": "🚨 <b>ЭКСТРЕННАЯ ВЫПЛАТА ПОСОБИЙ ПО БЕЗРАБОТИЦЕ НА ДИВАНЕ</b> 🚨",
        "intro": (
            "МЧС борды фиксирует: очередной день потрачен. Спасибо за участие.\n"
            "Из <b>{pool_size}</b> трудящихся клавиатур рандомайзер облагодетельствовал\n"
            "<b>{winner_count}</b> представителей диванной армии:\n"
        ),
        "footer": "💡 <i>Честный рандом, никаких преимуществ у спамеров. Один анон = один билет. До завтра!</i>"
    },
    {
        "title": "🎪 <b>РОЗЫГРЫШ В ШАПИТО АБУ ПРОДОЛЖАЕТСЯ</b> 🎪",
        "intro": (
            "Арена борды снова собрала достойных. Из <b>{pool_size}</b> сегодняшних клоунов\n"
            "великий жрец рандома назначил <b>{winner_count}</b> победителей суточного кубка по шитпосту:\n"
        ),
        "footer": "💡 <i>Деньги в кармане у избранных. Остальные — до завтра, пишите посты!</i>"
    },
    {
        "title": "⚰️ <b>СТРАХОВАЯ ВЫПЛАТА ЗА УБИТЫЕ СУТКИ</b> ⚰️",
        "intro": (
            "Ещё один день жизни сгорел в треках борды. Абу выплачивает компенсацию.\n"
            "Из <b>{pool_size}</b> ежедневных сычей удача улыбнулась <b>{winner_count}</b> анонам:\n"
        ),
        "footer": "💡 <i>Ритуальные шекели получены. Завтра опять 24ч борды и новый шанс попасть в пул.</i>"
    },
]

DAILY_PM_TEMPLATES = [
    (
        "🎰 <b>ПОЗДРАВЛЯЕМ, АНОН!</b> 🎰\n\n"
        "Ежедневный рандом Фонда Абу выбрал тебя из {pool_size} участников!\n\n"
        "💵 Тебе начислено: <code>+{payout:,} ₪</code>\n"
        "🏆 Ты один из {winner_count} победителей сегодня.\n\n"
        "<i>Трать с умом (или вбухай в /casino — мы не осуждаем).</i>\n"
        "Кошелёк: /wallet"
    ),
    (
        "💸 <b>СУТОЧНАЯ ВЫПЛАТА ОТ АБУ</b> 💸\n\n"
        "Из {pool_size} активных анонов ты попал в {winner_count} победителей!\n"
        "Рандом честный — один анон, один билет, никаких преимуществ.\n\n"
        "💵 Зачислено: <code>+{payout:,} ₪</code>\n\n"
        "<i>Пиши посты завтра — снова будешь в пуле. /wallet</i>"
    ),
    (
        "🛥️ <b>АБУ ЛИЧНО ВЫБРАЛ ТЕБЯ</b> 🛥️\n\n"
        "Ну, не лично. Рандом выбрал. Из {pool_size} кандидатов — тебя.\n\n"
        "💵 Выплата: <code>+{payout:,} ₪</code>\n"
        "👥 Всего победителей сегодня: {winner_count}\n\n"
        "<i>Заслуженная пайка. Проверь /wallet и иди покупай мут-ган.</i>"
    ),
    (
        "🏦 <b>ТРАНШ ИЗ КАЗНЫ АБУСТАНА</b> 🏦\n\n"
        "Ежесуточный розыгрыш отобрал {winner_count} победителей из {pool_size}.\n"
        "Ты оказался в числе счастливчиков!\n\n"
        "💵 На счёт упало: <code>+{payout:,} ₪</code>\n\n"
        "<i>Завтра будет новый розыгрыш. Пиши хотя бы 3 поста — и попадёшь в пул. /wallet</i>"
    ),
    (
        "🎪 <b>ТЫ ВЫИГРАЛ В ЛОТЕРЕЮ БОРДЫ!</b> 🎪\n\n"
        "Честный рандом из {pool_size} участников выбрал {winner_count} анонов.\n"
        "Ты в списке!\n\n"
        "💵 Шекели зачислены: <code>+{payout:,} ₪</code>\n\n"
        "<i>Удача сегодня с тобой. Проверь /wallet и иди в /shop пока везёт.</i>"
    ),
]

NEWBIE_GRANT_MESSAGES = [
    (
        "🎁 <b>ПОДЪЁМНЫЕ ДЛЯ НОВОБРАНЦА!</b> 🎁\n\n"
        "Ты написал свои первые посты на борде — и Фонд Абу отсыпал тебе стартовый капитал.\n\n"
        "💵 Начислено: <code>+500 ₪</code>\n\n"
        "<i>Хватит на несколько инструментов в /shop. Добро пожаловать в яму.</i>\n"
        "Кошелёк: /wallet"
    ),
    (
        "🍺 <b>ПЕРВЫЕ ШЕКЕЛИ ДЛЯ ДЕГЕНЕРАТА</b> 🍺\n\n"
        "Добро пожаловать на борду, свежее мясо!\n"
        "Фонд Яхты Абу выдаёт подъёмные новым анонам.\n\n"
        "💵 Твои первые шекели: <code>+500 ₪</code>\n\n"
        "<i>Загляни в /shop — тут есть интересные предметы.\n"
        "Пиши посты — получишь ещё в ежесуточном розыгрыше!</i>\n"
        "/wallet"
    ),
    (
        "🎰 <b>ГРАНТ НЬЮФАГУ ОТ ФОНДА АБУ</b> 🎰\n\n"
        "Ты сделал первые шаги на борде. Абу видит всё.\n"
        "И даже раскошелился на приветственный паёк.\n\n"
        "💵 Получи: <code>+500 ₪</code>\n\n"
        "<i>Пиши посты каждый день — и участвуй в ежедневном розыгрыше Фонда.</i>\n"
        "/wallet — посмотреть баланс"
    ),
    (
        "🐀 <b>НАЧАЛЬНЫЙ ПАЙОК ДЛЯ НОВОГО ЖИТЕЛЯ ПОДВАЛА</b> 🐀\n\n"
        "Фонд Абу приветствует тебя разовой подачкой.\n"
        "Осваивайся, не облажайся.\n\n"
        "💵 Стартовый капитал: <code>+500 ₪</code>\n\n"
        "<i>В /shop можно купить оружие, защиту и разные дебаффы. Добро пожаловать в клоаку!</i>\n"
        "/wallet"
    ),
]


# ─── Newbie Grant ──────────────────────────────────────────────────────────────

async def check_and_grant_newbie_post_bonus(
    user_id: int,
    board_id: str,
    bot: Optional[Bot] = None,
) -> bool:
    """
    Проверяет, нужно ли выдать приветственный грант ньюфагу (500 ₪).
    Вызывается после успешной публикации поста.
    Возвращает True, если грант был выдан.
    """
    if user_id <= 0:
        return False

    try:
        from common.db_pool import get_pool, db_lock
        from common.database import (
            add_user_global_balance,
            record_user_transaction,
            deduct_from_abu_fund,
            get_abu_fund_total,
        )
        try:
            from common.database import create_alert
        except ImportError:
            create_alert = None

        db = await get_pool()

        async with db_lock:
            # Получаем текущий posts_count и active_items
            async with db.execute(
                "SELECT SUM(posts_count), MAX(active_items) FROM Users WHERE user_id = ?",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return False

            total_posts = int(row[0] or 0)
            raw_items = row[1]

            # Проверяем условие ньюфага
            if total_posts > NEWBIE_GRANT_MAX_POSTS:
                return False

            # Парсим active_items для проверки флага
            try:
                active_items = json.loads(raw_items) if raw_items else {}
            except (json.JSONDecodeError, TypeError):
                active_items = {}

            if active_items.get("newbie_abu_grant"):
                return False  # Уже выдавали

            # Проверяем, нет ли записи в UserTransactions (дополнительная защита)
            async with db.execute(
                "SELECT COUNT(*) FROM UserTransactions WHERE user_id = ? AND category = 'newbie_grant'",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
                if row and int(row[0] or 0) > 0:
                    # Есть транзакция, но флага нет — синхронизируем флаг и выходим
                    active_items["newbie_abu_grant"] = True
                    await db.execute(
                        "UPDATE Users SET active_items = ? WHERE user_id = ?",
                        (json.dumps(active_items, ensure_ascii=False), user_id)
                    )
                    await db.commit()
                    return False

            # Проверяем, хватает ли в Фонде Абу
            fund_total = await get_abu_fund_total(db)
            if fund_total < NEWBIE_GRANT_AMOUNT:
                logger.warning(
                    f"[NewbieGrant] Abu fund too low ({fund_total:.0f} ₪) for user {user_id}"
                )
                return False

            # Выдаём грант
            await add_user_global_balance(db, user_id, board_id, float(NEWBIE_GRANT_AMOUNT))
            await record_user_transaction(
                db=db,
                user_id=user_id,
                amount=float(NEWBIE_GRANT_AMOUNT),
                category="newbie_grant",
                description=f"Приветственный грант ньюфагу от Фонда Абу"
            )

            # Выставляем флаг в active_items
            active_items["newbie_abu_grant"] = True
            await db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ?",
                (json.dumps(active_items, ensure_ascii=False), user_id)
            )
            await db.commit()

        # Списываем из фонда (вне db_lock — у deduct_from_abu_fund есть своя защита)
        await deduct_from_abu_fund(db, float(NEWBIE_GRANT_AMOUNT), reason=f"newbie_grant_{user_id}")

        logger.info(f"[NewbieGrant] Granted {NEWBIE_GRANT_AMOUNT} ₪ to newbie {user_id}")

        # Уведомление в ЛС
        if bot is not None:
            pm_text = random.choice(NEWBIE_GRANT_MESSAGES)
            try:
                await bot.send_message(chat_id=user_id, text=pm_text, parse_mode="HTML")
            except Exception as e:
                logger.debug(f"[NewbieGrant] PM failed for {user_id}: {e}")

        # Персистентный алерт в БД (если бот закрыт)
        if create_alert is not None:
            try:
                db2 = await get_pool()
                await create_alert(
                    user_id=user_id,
                    content=(
                        f"🎁 <b>ПОДЪЁМНЫЕ ОТ АБУ:</b> Тебе начислено <b>+{NEWBIE_GRANT_AMOUNT} ₪</b> "
                        f"как новому участнику борды! Проверь /wallet"
                    ),
                    target_board="all"
                )
            except Exception as e:
                logger.debug(f"[NewbieGrant] Alert failed for {user_id}: {e}")

        return True

    except Exception as e:
        logger.error(f"[NewbieGrant] Error for user {user_id}: {e}", exc_info=True)
        return False


# ─── Daily Airdrop ─────────────────────────────────────────────────────────────

async def fetch_daily_qualified_users(db) -> list[int]:
    """
    Возвращает список user_id, написавших > DAILY_MIN_POSTS_QUALIFY постов за последние 24 часа.
    Исключает системные (author_id <= 0) и теневые посты.
    """
    since_ts = time.time() - 86400.0
    query = """
        SELECT author_id
        FROM Posts
        WHERE timestamp >= ?
          AND author_id > 0
          AND IFNULL(is_shadow, 0) = 0
        GROUP BY author_id
        HAVING COUNT(*) > ?
    """
    async with db.execute(query, (since_ts, DAILY_MIN_POSTS_QUALIFY)) as cur:
        rows = await cur.fetchall()
    return [int(row[0]) for row in rows if row[0]]


def pick_daily_winners(qualified: list[int]) -> list[int]:
    """
    Выбирает победителей с равными шансами (1 билет на юзера, без учёта числа постов).
    Количество победителей: min(len(qualified), DAILY_WINNER_COUNT_MAX), но не менее
    DAILY_WINNER_COUNT_MIN (если квалифицированных меньше — берём всех).
    """
    if not qualified:
        return []
    n = min(len(qualified), DAILY_WINNER_COUNT_MAX)
    n = max(n, min(DAILY_WINNER_COUNT_MIN, len(qualified)))
    return random.sample(qualified, n)


def format_daily_board_announcement(
    winners: list[int],
    pool_size: int,
    payout: int,
) -> str:
    """Формирует публичный анонс аирдропа для тредов /b/ и /thread/."""
    try:
        from common.anon_identity import get_anon_id
        def _hash(uid: int) -> str:
            return get_anon_id(uid, stream="ru")
    except Exception:
        def _hash(uid: int) -> str:
            return f"#{uid % 9999:04d}"

    tmpl = random.choice(DAILY_BOARD_TEMPLATES)
    winner_count = len(winners)

    lines = [
        tmpl["title"] + "\n",
        tmpl["intro"].format(winner_count=winner_count, pool_size=pool_size) + "\n",
        f"🏦 <b>Приз каждому:</b> <code>{payout:,} ₪</code>",
        f"👥 <b>Победителей:</b> {winner_count} из {pool_size} участников\n",
        "🏆 <b>СЧАСТЛИВЧИКИ СЕГОДНЯ:</b>",
    ]

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, uid in enumerate(winners, 1):
        icon = medal.get(i, "🎖")
        lines.append(f"{icon} [{_hash(uid)}]: <code>+{payout:,} ₪</code>")

    lines.append("\n" + tmpl["footer"])
    return "\n".join(lines)


def format_daily_pm(payout: int, winner_count: int, pool_size: int) -> str:
    """Личное уведомление победителю."""
    tmpl = random.choice(DAILY_PM_TEMPLATES)
    return tmpl.format(payout=payout, winner_count=winner_count, pool_size=pool_size)


async def execute_daily_airdrop(db, bots: dict) -> dict:
    """
    Полный цикл ежесуточного честного аирдропа.
    Возвращает словарь с результатом.
    """
    from common.db_pool import db_lock
    from common.database import (
        add_user_global_balance,
        record_user_transaction,
        deduct_from_abu_fund,
        get_abu_fund_total,
    )
    try:
        from common.database import create_alert, create_post
    except ImportError:
        create_alert = None
        create_post = None

    now_ts = time.time()

    # ── 1. Защита от двойного запуска (5-часовое окно) ──────────────────────
    async with db_lock:
        async with db.execute(
            "SELECT value FROM GlobalStats WHERE key = 'last_daily_airdrop_run'"
        ) as cur:
            row = await cur.fetchone()
        last_run_ts = float(row[0]) if row and row[0] else 0.0

    if last_run_ts > 0 and (now_ts - last_run_ts) < 5 * 3600:
        logger.info(f"[DailyAirdrop] Skipped — ran recently at {last_run_ts:.0f}")
        return {"status": "skipped", "reason": "already_ran_recently"}

    # ── 2. Выборка квалифицированных ────────────────────────────────────────
    qualified = await fetch_daily_qualified_users(db)
    if not qualified:
        logger.warning("[DailyAirdrop] No qualified users today.")
        # Обновляем timestamp чтобы не крутиться
        async with db_lock:
            await db.execute(
                "INSERT INTO GlobalStats (key, value) VALUES ('last_daily_airdrop_run', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?",
                (str(now_ts), str(now_ts))
            )
            await db.commit()
        return {"status": "skipped", "reason": "no_qualified_users"}

    # ── 3. Выбор победителей ─────────────────────────────────────────────────
    winners = pick_daily_winners(qualified)
    winner_count = len(winners)
    pool_size = len(qualified)
    payout_per_winner = DAILY_PRIZE_PER_WINNER
    total_payout = winner_count * payout_per_winner

    # ── 4. Проверяем казну Абу ───────────────────────────────────────────────
    current_fund = await get_abu_fund_total(db)
    if current_fund < total_payout:
        # Если фонд маловат — урезаем приз до 50% от фонда, распределяем равномерно
        if current_fund < winner_count * 100:
            logger.warning(f"[DailyAirdrop] Abu fund critically low ({current_fund:.0f} ₪). Skipping.")
            return {"status": "skipped", "reason": "abu_fund_empty"}
        payout_per_winner = max(100, int((current_fund * 0.5) / winner_count))
        total_payout = winner_count * payout_per_winner

    # ── 5. Начисляем шекели ──────────────────────────────────────────────────
    credited_count = 0
    async with db_lock:
        for uid in winners:
            try:
                await add_user_global_balance(db, uid, "b", float(payout_per_winner))
                await record_user_transaction(
                    db=db,
                    user_id=uid,
                    amount=float(payout_per_winner),
                    category="daily_airdrop",
                    description=f"Ежесуточный аирдроп Фонда Абу"
                )
                credited_count += 1
            except Exception as e:
                logger.error(f"[DailyAirdrop] Credit failed for {uid}: {e}")

        # Фиксируем время запуска
        await db.execute(
            "INSERT INTO GlobalStats (key, value) VALUES ('last_daily_airdrop_run', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (str(now_ts), str(now_ts))
        )
        await db.commit()

    # ── 6. Списываем из фонда Абу ────────────────────────────────────────────
    remaining_fund = await deduct_from_abu_fund(
        db, float(total_payout), reason="daily_airdrop"
    )
    logger.info(
        f"[DailyAirdrop] Credited {total_payout:,} ₪ to {credited_count} winners. "
        f"Abu fund remaining: {remaining_fund:,.0f} ₪"
    )

    # ── 7. Публичный анонс в треды ───────────────────────────────────────────
    if create_post is not None:
        announcement_text = format_daily_board_announcement(
            winners=winners,
            pool_size=pool_size,
            payout=payout_per_winner,
        )
        for target_board in ["b", "thread"]:
            try:
                content = {
                    "type": "text",
                    "text": announcement_text,
                    "is_system_message": True,
                    "archive_allowed": True,
                }
                pnum = await create_post(
                    author_id=0,
                    board_id=target_board,
                    content=content,
                    timestamp=time.time(),
                    stream="ru",
                )
                try:
                    from shared_state import (
                        board_data, enqueue_board_message, storage_lock,
                        state, post_to_messages, messages_storage,
                    )
                    b_users = board_data.get(target_board, {}).get("users", {})
                    active_users = set(b_users.get("active", set())) - set(b_users.get("banned", set()))
                    if pnum and active_users:
                        async with storage_lock:
                            state["post_counter"] = max(state.get("post_counter", 0), pnum)
                            post_to_messages[pnum] = {}
                            messages_storage[pnum] = {
                                "board_id": target_board,
                                "author_id": 0,
                                "content": content,
                                "timestamp": time.time(),
                            }
                        await enqueue_board_message(target_board, {
                            "recipients": active_users,
                            "board_id": target_board,
                            "post_num": pnum,
                            "author_id": 0,
                            "author_name": "Абу",
                            "content": content,
                            "reply_to": None,
                            "is_op": False,
                        })
                    if pnum:
                        try:
                            from archive_manager import _forward_post_to_realtime_archive
                            from common.task_manager import spawn_task
                            from shared_state import GLOBAL_BOTS
                            target_bot = (
                                (bots.get(target_board) if bots else None)
                                or (GLOBAL_BOTS.get(target_board) if GLOBAL_BOTS else None)
                                or (bots.get("b") if bots else None)
                            )
                            if target_bot:
                                spawn_task(_forward_post_to_realtime_archive(
                                    bot_instance=target_bot,
                                    board_id=target_board,
                                    post_num=pnum,
                                    content=content,
                                    is_shadow_muted=False,
                                ))
                        except Exception as arc_err:
                            logger.warning(f"[DailyAirdrop] Archive forward failed: {arc_err}")
                except Exception as bc_err:
                    logger.warning(f"[DailyAirdrop] Board broadcast failed for {target_board}: {bc_err}")
            except Exception as post_err:
                logger.error(f"[DailyAirdrop] Announcement post failed for {target_board}: {post_err}")

    # ── 8. ЛС победителям ────────────────────────────────────────────────────
    active_bots_list = list(bots.values()) if bots else []

    async def _send_pm_and_alerts():
        for uid in winners:
            pm_text = format_daily_pm(
                payout=payout_per_winner,
                winner_count=winner_count,
                pool_size=pool_size,
            )
            # ЛС через первого доступного бота
            for b in active_bots_list:
                try:
                    await b.send_message(chat_id=uid, text=pm_text, parse_mode="HTML")
                    break
                except Exception:
                    continue
            # Персистентный алерт в БД
            if create_alert is not None:
                try:
                    db3 = await get_pool()
                    await create_alert(
                        user_id=uid,
                        content=(
                            f"💰 <b>ЕЖЕСУТОЧНЫЙ АИРДРОП:</b> Тебе начислено "
                            f"<b>+{payout_per_winner:,} ₪</b> из Фонда Абу! "
                            f"Ты один из {winner_count} победителей. /wallet"
                        ),
                        target_board="all",
                    )
                except Exception as ae:
                    logger.debug(f"[DailyAirdrop] Alert failed for {uid}: {ae}")
            await asyncio.sleep(0.05)

    if active_bots_list:
        from common.task_manager import spawn_task
        spawn_task(_send_pm_and_alerts())

    return {
        "status": "success",
        "total_payout": total_payout,
        "winner_count": winner_count,
        "pool_size": pool_size,
        "payout_per_winner": payout_per_winner,
        "abu_fund_remaining": remaining_fund,
    }


# ─── Background loop ───────────────────────────────────────────────────────────

async def daily_airdrop_loop(bots: dict) -> None:
    """
    Фоновый воркер ежесуточного аирдропа.
    - Первый запуск: через 15 минут после старта.
    - Далее: каждые 24ч от последнего запуска.
    """
    from common.db_pool import get_pool, db_lock

    await asyncio.sleep(30)  # Прогрев при старте бота

    while True:
        try:
            db = await get_pool()
            now_ts = time.time()

            async with db_lock:
                async with db.execute(
                    "SELECT value FROM GlobalStats WHERE key = 'last_daily_airdrop_run'"
                ) as cur:
                    row = await cur.fetchone()
                last_run_ts = float(row[0]) if row and row[0] else 0.0

            if last_run_ts <= 0:
                sleep_sec = float(DAILY_FIRST_RUN_DELAY)
                target_dt = datetime.fromtimestamp(now_ts + sleep_sec, tz=MSK)
                print(
                    f"🎁 [DailyAirdrop] Первый запуск через 15 минут "
                    f"({target_dt.strftime('%Y-%m-%d %H:%M:%S')} MSK)"
                )
            else:
                next_run_ts = last_run_ts + DAILY_INTERVAL_SECONDS
                sleep_sec = max(0.0, next_run_ts - now_ts)
                target_dt = datetime.fromtimestamp(next_run_ts, tz=MSK)
                print(
                    f"🎁 [DailyAirdrop] Следующий аирдроп: "
                    f"{target_dt.strftime('%Y-%m-%d %H:%M:%S')} MSK "
                    f"(через {sleep_sec / 3600:.1f} ч)"
                )

            if sleep_sec > 0:
                await asyncio.sleep(sleep_sec)

            print("🎁 [DailyAirdrop] Запуск ежесуточного аирдропа...")
            result = await execute_daily_airdrop(db, bots)
            print(f"🎁 [DailyAirdrop] Результат: {result}")

            await asyncio.sleep(300)  # 5-минутный буфер после раздачи

        except Exception as e:
            logger.error(f"[DailyAirdrop] Loop error: {e}", exc_info=True)
            await asyncio.sleep(60)
