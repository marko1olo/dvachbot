# -*- coding: utf-8 -*-
"""
weekly_airdrop_engine.py — Еженедельный пропорциональный аирдроп активным анонам.

Каждое воскресенье в 21:00 MSK (плюс первый проверочный запуск через 15 минут после старта):
1. Подсчитывает активность всех авторов за последние 7 дней (таблица Posts).
2. Формирует призовой фонд: базовый минимум (200 000 ₪) + 30 ₪ за каждый созданный пост недели (~500k ₪ при 10k постов).
3. Распределяет шекели пропорционально активности по сублинейной степенной формуле (posts ** 0.65)
   с верхним капом не более 15% в одни руки (защита от монополизации фонда 1-2 гипер-спамерами).
4. Атомарно начисляет шекели через add_user_global_balance и пишет проводку в UserTransactions.
5. Публикует черный циничный анонс в треды /b/ и /thread/, а также рассылает личные уведомления в ЛС.
"""

import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from aiogram import Bot

logger = logging.getLogger("weekly_airdrop")

MSK = timezone(timedelta(hours=3))

# Конфигурация экономики аирдропа
MIN_WEEKLY_POOL = 200_000.0      # Минимальный гарантированный фонд недели в шекелях
POST_BONUS_RATE = 30.0           # Дополнительно шекелей в пул за каждый пост недели (~500k при 10k постов)
MIN_POSTS_REQUIRED = 3           # Минимальный порог постов за неделю для участия
POWER_EXPONENT = 0.65            # Сублинейный коэффициент сглаживания (Diminishing returns)
MAX_USER_SHARE = 0.15            # Максимум 15% пула в одни руки


def seconds_until_next_sunday_2100(now_msk: datetime) -> tuple[datetime, float]:
    """
    Возвращает (целевое время MSK, сколько секунд спать) до ближайшего воскресенья 21:00 MSK.
    Monday == 0 ... Sunday == 6.
    """
    days_ahead = 6 - now_msk.weekday()
    if days_ahead < 0 or (days_ahead == 0 and (now_msk.hour > 21 or (now_msk.hour == 21 and now_msk.minute >= 0))):
        days_ahead += 7
    target_time = (now_msk + timedelta(days=days_ahead)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    sleep_seconds = max(1.0, (target_time - now_msk).total_seconds())
    return target_time, sleep_seconds


async def fetch_weekly_contributors(db, days: int = 7, min_posts: int = MIN_POSTS_REQUIRED) -> list[dict]:
    """
    Извлекает из базы список авторов за последние `days` дней с числом постов >= `min_posts`.
    Исключает системные аккаунты (author_id <= 0) и теневые посты.
    """
    since_ts = time.time() - (days * 86400)
    query = """
        SELECT
            author_id,
            COUNT(*) as total_posts,
            SUM(CASE WHEN content LIKE '%file_id%' OR content LIKE '%photo%' OR content LIKE '%video%' THEN 1 ELSE 0 END) as media_posts
        FROM Posts
        WHERE timestamp >= ?
          AND author_id > 0
          AND IFNULL(is_shadow, 0) = 0
        GROUP BY author_id
        HAVING total_posts >= ?
        ORDER BY total_posts DESC
    """
    results = []
    async with db.execute(query, (since_ts, min_posts)) as cur:
        rows = await cur.fetchall()
        for row in rows:
            results.append({
                "user_id": int(row[0]),
                "posts_count": int(row[1]),
                "media_count": int(row[2] or 0)
            })
    return results


def calculate_weekly_pool(total_posts_week: int) -> float:
    """Рассчитывает суммарный размер недельного пула шекелей."""
    dynamic_bonus = max(0, total_posts_week) * POST_BONUS_RATE
    return round(MIN_WEEKLY_POOL + dynamic_bonus, 2)


def compute_airdrop_allocations(
    contributors: list[dict],
    total_pool: float,
    exponent: float = POWER_EXPONENT,
    max_share: float = MAX_USER_SHARE
) -> list[dict]:
    """
    Распределяет total_pool между contributors пропорционально (posts_count ** exponent)
    с ограничением доли одного участника не более max_share.
    Возвращает дополненный список contributors с полями 'weight', 'payout', 'share_pct'.
    """
    if not contributors or total_pool <= 0:
        return []

    # 1. Считаем базовые веса по сублинейной формуле
    weights = []
    for c in contributors:
        w = float(c["posts_count"]) ** exponent
        weights.append(w)

    total_weight = sum(weights)
    if total_weight <= 0:
        return []

    max_payout_per_user = round(total_pool * max_share, 2)
    allocations = []
    remaining_pool = total_pool
    remaining_weights = total_weight
    unconstrained_indices = set(range(len(contributors)))

    # Итеративное применение капа (до 5 итераций на случай каскадного насыщения)
    payouts = [0.0] * len(contributors)
    for _ in range(5):
        capped_this_round = False
        for idx in list(unconstrained_indices):
            share = (weights[idx] / remaining_weights) if remaining_weights > 0 else 0
            tentative = share * remaining_pool
            if tentative >= max_payout_per_user:
                payouts[idx] = max_payout_per_user
                remaining_pool -= max_payout_per_user
                remaining_weights -= weights[idx]
                unconstrained_indices.remove(idx)
                capped_this_round = True
        if not capped_this_round or remaining_weights <= 0:
            break

    # Распределяем оставшийся пул среди не упершихся в кап
    if remaining_weights > 0 and unconstrained_indices:
        for idx in unconstrained_indices:
            share = weights[idx] / remaining_weights
            payouts[idx] = round(share * remaining_pool, 2)

    # Нормализация округления
    sum_allocated = sum(payouts)
    diff = round(total_pool - sum_allocated, 2)
    if abs(diff) > 0 and contributors:
        target_idx = next(iter(unconstrained_indices)) if unconstrained_indices else 0
        payouts[target_idx] = round(payouts[target_idx] + diff, 2)

    for i, c in enumerate(contributors):
        p = max(1.0, round(payouts[i], 0))  # Выплата в целых шекелях, минимум 1 ₪
        allocations.append({
            "user_id": c["user_id"],
            "posts_count": c["posts_count"],
            "media_count": c.get("media_count", 0),
            "payout": int(p),
            "share_pct": round((p / total_pool) * 100, 2),
        })

    # Сортировка по размеру выплаты
    allocations.sort(key=lambda x: x["payout"], reverse=True)
    return allocations


# -----------------------------------------------------------------------------
# Черный юмор и ебанутые фразочки Абустана
# -----------------------------------------------------------------------------

AIRDROP_BOARD_TEMPLATES = [
    {
        "title": "💸 <b>ПОСОБИЕ ПО БЕЗРАБОТИЦЕ И ШИТПОСТИНГУ АБУСТАНА</b> 💸",
        "intro": (
            "Товарищи дегенераты, омежки и ноулайферы!\n"
            "Вы успешно проебали очередные 7 дней своей никчемной жизни, высрав <b>{total_posts_week:,}</b> постов в треды "
            "вместо того, чтобы найти работу, завести бабу или хотя бы помыться.\n\n"
            "Абу сжалился над вашим экзистенциальным убожеством и производит еженедельную инъекцию казенных шекелей из Фонда Яхты!"
        ),
        "footer": "💡 <i>Шекели упали на счета. Бегом в /shop скупать мут-ганы и сводить счеты с обидчиками. Чем больше срёте — тем жирнее куш!</i>"
    },
    {
        "title": "💉 <b>ВЕРТОЛЕТНЫЕ ШЕКЕЛИ ИЗ ПСИХДИСПАНСЕРА ТГАЧА</b> 💉",
        "intro": (
            "Срочное обращение главврача дурдома!\n"
            "За прошедшие 7 дней в палатах зафиксировано <b>{total_posts_week:,}</b> приступов шизофазии, вайпов и параноидального бреда.\n\n"
            "Фармацевтический комитет выделил стимулирующую субсидию на покупку галоперидола и пива для самых буйных пациентов:"
        ),
        "footer": "💡 <i>Казна выплатила всё до копейки. Если недоволен — пиздуй на завод (/work) или крути рулетку в казино.</i>"
    },
    {
        "title": "🏦 <b>РОСПИЛ КАЗНЫ ИМЕНИ ВЕЛИКОГО АБУ</b> 🏦",
        "intro": (
            "Пока за окном рушится нормисный мир, наши диванные войска напердели в /b/ целых <b>{total_posts_week:,}</b> постов.\n\n"
            "ОБЭП закрыл глаза, налоговая получила откат, и мы расчехляем печатный станок шекелей для ударников клавиатурного станка:"
        ),
        "footer": "💡 <i>Шекели на балансах. Иди в /shop, купи заточку (/rob) и ограбь соседа, пока он спит.</i>"
    },
    {
        "title": "⚰️ <b>ЕЖЕНЕДЕЛЬНЫЕ ДИВИДЕНДЫ ИЗ ЦИФРОВОГО МОРГА</b> ⚰️",
        "intro": (
            "Неделя подошла к концу, а ты всё ещё сидишь перед монитором в тёмной комнате.\n"
            "За 7 дней коллективный разум сычей выдал <b>{total_posts_week:,}</b> криков о помощи и токсичных высеров.\n\n"
            "За верность борде и абсолютную социальную смерть администрация отсыпает пособие на выживание:"
        ),
        "footer": "💡 <i>Деньги в кармане. Не проеби всё в рулетку за 5 минут, хотя кого мы обманываем...</i>"
    }
]

RANK_TITLES = {
    1: "👑 <b>ГЛАВНЫЙ СЫЧ ВСЕЛЕННОЙ</b> <i>(абсолютный ноулайфер недели)</i>",
    2: "🥈 <b>СЕРЕБРЯНЫЙ ШИТПОСТЕР</b> <i>(клавиатура уже дымится)</i>",
    3: "🥉 <b>ПОЧЕТНЫЙ ШИЗОИД</b> <i>(третье место в палате)</i>",
    4: "🎖 <i>Ударник клавиатурного станка</i>",
    5: "🎖 <i>Мастер спорта по диванным боям</i>",
    6: "🎖 <i>Штатный генератор кринжа</i>",
    7: "🎖 <i>Скуф на удаленке</i>",
    8: "🎖 <i>Агент диванных войск</i>",
    9: "🎖 <i>Претендент на путевку в ПНД</i>",
    10: "🎖 <i>Замыкающий палаты №6</i>",
}

AIRDROP_PM_TEMPLATES = [
    (
        "💊 <b>ПОСОБИЕ НА ГАЛОПЕРИДОЛ НАЧИСЛЕНО!</b> 💊\n\n"
        "Товарищ анон! ПНД и Абу высоко ценят твой непрерывный бред.\n\n"
        "📊 Твой вклад в безумие за 7 дней: <b>{posts_count}</b> постов\n"
        "🏅 Место в палате: <b>#{rank}</b> из {total_recipients}\n"
        "💵 Капнуло на сберкнижку: +<code>{payout:,} ₪</code>\n\n"
        "<i>Бегом в /shop закупать Мут-Ган или Заточку, пока инфляция не сожрала!</i>\n"
        "Проверить баланс: /wallet"
    ),
    (
        "🍕 <b>СТИМУЛ-ЧЕК НА ПИВО И ДОШИРАК</b> 🍕\n\n"
        "Абу посмотрел на твои <b>{posts_count}</b> постов и пустил скупую слезу.\n\n"
        "📊 Активность за неделю: <b>{posts_count}</b> постов\n"
        "🏅 Ранг среди сычей: <b>#{rank}</b> из {total_recipients}\n"
        "💵 Выплата за деградацию: +<code>{payout:,} ₪</code>\n\n"
        "<i>Не благодари. Можешь слить всё в казино или вызвать Пативэн неугодным: /shop</i>\n"
        "Кошелек: /wallet"
    ),
    (
        "☠️ <b>КОМПЕНСАЦИЯ ЗА УБИТУЮ МОЛОДОСТЬ</b> ☠️\n\n"
        "Ты потратил ещё одну неделю своей бесценной жизни на Тгач.\n\n"
        "📊 Настрочил: <b>{posts_count}</b> высеров\n"
        "🏅 Место на социальном дне: <b>#{rank}</b> из {total_recipients}\n"
        "💵 Компенсация за деградацию: +<code>{payout:,} ₪</code>\n\n"
        "<i>Иди приоденься в бутике /wardrobe или купи шапочку из фольги в /shop!</i>\n"
        "Проверить заначку: /wallet"
    ),
    (
        "🚔 <b>ГОНОРАР ОТ ТОВАРИЩА МАЙОРА</b> 🚔\n\n"
        "За добросовестное засорение каналов связи (<b>{posts_count}</b> постов) тебе выписан закрытый чек.\n\n"
        "📊 Зафиксировано сигналов: <b>{posts_count}</b>\n"
        "🏅 Твой номер в личном деле: <b>#{rank}</b> из {total_recipients}\n"
        "💵 Выручка осведомителя: +<code>{payout:,} ₪</code>\n\n"
        "<i>Трать аккуратно, чтобы не привлечь внимание ОБЭПа: /shop</i>\n"
        "Баланс: /wallet"
    )
]


def format_airdrop_board_announcement(
    total_pool: float,
    total_recipients: int,
    total_posts_week: int,
    top_allocations: list[dict]
) -> str:
    """Формирует черный ебанутый пост для тредов /b/ и /thread/."""
    tmpl = random.choice(AIRDROP_BOARD_TEMPLATES)
    lines = [
        tmpl["title"] + "\n",
        tmpl["intro"].format(total_posts_week=total_posts_week) + "\n",
        f"🏦 <b>Общий фонд распила:</b> <code>{int(total_pool):,} ₪</code>",
        f"👥 <b>Награждено стахановцев:</b> <code>{total_recipients}</code>\n",
        "🏆 <b>ТОП-10 ГЛАВНЫХ ЗАДРОТОВ БОРДЫ:</b>"
    ]
    for rank, item in enumerate(top_allocations[:10], 1):
        title = RANK_TITLES.get(rank, f"🎖 <i>Анон #{rank}</i>")
        lines.append(
            f"{rank}. {title} [ID <code>{item['user_id']}</code>]: "
            f"+<b>{item['payout']:,} ₪</b> <i>({item['posts_count']} шт.)</i>"
        )

    lines.append("\n" + tmpl["footer"])
    return "\n".join(lines)


def format_airdrop_pm_notification(payout: int, posts_count: int, rank: int, total_recipients: int) -> str:
    """Формирует персональное уведомление с черным юмором для пользователя в ЛС."""
    tmpl = random.choice(AIRDROP_PM_TEMPLATES)
    return tmpl.format(
        payout=payout,
        posts_count=posts_count,
        rank=rank,
        total_recipients=total_recipients
    )


async def execute_weekly_airdrop(db, bots: dict[str, Bot]) -> dict:
    """
    Выполняет полный цикл начисления еженедельного аирдропа:
    - Защита от двойного запуска через GlobalStats (5 дней).
    - Транзакционное начисление шекелей и запись в UserTransactions.
    - Анонс в треды и ЛС получателям.
    """
    from common.database import add_user_global_balance, record_user_transaction, create_post
    from common.db_pool import db_lock

    now_ts = time.time()
    now_msk = datetime.now(timezone.utc).astimezone(MSK)

    # 1. Проверяем, не выполнялась ли раздача в последние 5 дней (защита от дублей)
    last_run_ts = 0.0
    async with db_lock:
        async with db.execute("SELECT value FROM GlobalStats WHERE key = 'last_weekly_airdrop_run'") as cur:
            row = await cur.fetchone()
            if row and row[0]:
                try:
                    last_run_ts = float(row[0])
                except ValueError:
                    last_run_ts = 0.0

    if (now_ts - last_run_ts) < (5 * 86400):
        logger.info(f"Weekly airdrop skipped: already executed recently at {last_run_ts}")
        return {"status": "skipped", "reason": "already_ran_recently"}

    # 2. Собираем авторов за 7 дней
    contributors = await fetch_weekly_contributors(db, days=7, min_posts=MIN_POSTS_REQUIRED)
    if not contributors:
        logger.warning("Weekly airdrop: no qualifying contributors found.")
        return {"status": "skipped", "reason": "no_contributors"}

    total_posts_week = sum(c["posts_count"] for c in contributors)
    total_pool = calculate_weekly_pool(total_posts_week)
    allocations = compute_airdrop_allocations(contributors, total_pool)

    # 3. Транзакционно начисляем баланс
    total_credited = 0
    credited_count = 0

    async with db_lock:
        for item in allocations:
            uid = item["user_id"]
            payout = item["payout"]
            if payout <= 0:
                continue
            try:
                await add_user_global_balance(db, uid, "b", float(payout))
                await record_user_transaction(
                    db=db,
                    user_id=uid,
                    amount=float(payout),
                    category="airdrop",
                    description=f"Еженедельный аирдроп за {item['posts_count']} постов"
                )
                credited_count += 1
                total_credited += payout
            except Exception as e:
                logger.error(f"Failed to credit airdrop for user {uid}: {e}")

        # Фиксируем дату успешного выполнения
        await db.execute(
            """
            INSERT INTO GlobalStats (key, value) VALUES ('last_weekly_airdrop_run', ?)
            ON CONFLICT(key) DO UPDATE SET value = ?
            """,
            (str(now_ts), str(now_ts))
        )
        await db.commit()

    logger.info(f"✅ [AIRDROP] Успешно начислено {total_credited:,} ₪ ({credited_count} получателей).")

    # 4. Публикация анонса в треды /b/ и /thread/
    announcement_text = format_airdrop_board_announcement(
        total_pool=total_credited,
        total_recipients=credited_count,
        total_posts_week=total_posts_week,
        top_allocations=allocations
    )
    b_bot = bots.get('b') or (next(iter(bots.values())) if bots else None)
    if b_bot:
        for target_board in ["b", "thread"]:
            try:
                content = {
                    "type": "text",
                    "text": announcement_text,
                    "is_system_message": True,
                    "archive_allowed": True
                }
                await create_post(
                    author_id=0,
                    board_id=target_board,
                    content=content,
                    timestamp=time.time(),
                    stream="ru"
                )
            except Exception as post_err:
                logger.error(f"Failed to post airdrop announcement to {target_board}: {post_err}")

    # 5. Рассылка уведомлений в ЛС получателям (фоном)
    if b_bot:
        total_recipients = len(allocations)
        async def _send_pm_notifications():
            for rank, item in enumerate(allocations, 1):
                uid = item["user_id"]
                pm_text = format_airdrop_pm_notification(
                    payout=item["payout"],
                    posts_count=item["posts_count"],
                    rank=rank,
                    total_recipients=total_recipients
                )
                try:
                    await b_bot.send_message(chat_id=uid, text=pm_text, parse_mode="HTML")
                except Exception:
                    pass
                await asyncio.sleep(0.1)

        asyncio.create_task(_send_pm_notifications())

    return {
        "status": "success",
        "total_pool": total_credited,
        "recipients_count": credited_count,
        "total_posts": total_posts_week,
    }


async def weekly_airdrop_loop(bots: dict[str, Bot]):
    """
    Фоновый воркер еженедельного аирдропа:
    - При первом старте (если не запускался за последние 5 дней) ждет 15 минут (900 сек) и проводит раздачу.
    - В дальнейшем засыпает до ближайшего воскресенья 21:00 MSK и раздает строго раз в неделю.
    """
    from common.db_pool import get_pool, db_lock

    await asyncio.sleep(30)  # Пауза на старт бота и соединений

    try:
        db = await get_pool()
        now_ts = time.time()
        last_run_ts = 0.0
        async with db_lock:
            async with db.execute("SELECT value FROM GlobalStats WHERE key = 'last_weekly_airdrop_run'") as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    try:
                        last_run_ts = float(row[0])
                    except ValueError:
                        last_run_ts = 0.0

        # Если за последние 5 дней аирдропа еще не было — запускаем ровно через 15 минут!
        if (now_ts - last_run_ts) > (5 * 86400):
            print("🎁 [AIRDROP] Первичный запуск аирдропа назначен через 15 минут (900 сек)...")
            await asyncio.sleep(900)
            print("🎁 [AIRDROP] Старт первичного еженедельного аирдропа...")
            res = await execute_weekly_airdrop(db, bots)
            print(f"🎁 [AIRDROP] Результат первого запуска: {res}")
            await asyncio.sleep(300)
    except Exception as e:
        logger.error(f"Error in initial airdrop trigger: {e}")

    # Основной еженедельный цикл (воскресенье 21:00 MSK)
    while True:
        try:
            now_msk = datetime.now(timezone.utc).astimezone(MSK)
            target_time, sleep_seconds = seconds_until_next_sunday_2100(now_msk)

            print(
                f"🎁 [AIRDROP] Следующая еженедельная выплата активным анонам запланирована на "
                f"{target_time.strftime('%Y-%m-%d %H:%M:%S')} MSK (через {sleep_seconds / 3600:.1f} ч)"
            )

            await asyncio.sleep(sleep_seconds)

            # Проснулись ровно в воскресенье в 21:00 MSK!
            print("🎁 [AIRDROP] Время еженедельной раздачи шекелей! Запуск процедуры...")
            db = await get_pool()
            result = await execute_weekly_airdrop(db, bots)
            print(f"🎁 [AIRDROP] Результат раздачи: {result}")

            # Спим 1 час, чтобы гарантированно выйти из слота 21:00 MSK
            await asyncio.sleep(3600)

        except Exception as e:
            logger.error(f"Error in weekly_airdrop_loop: {e}")
            await asyncio.sleep(60)
