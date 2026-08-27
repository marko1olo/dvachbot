# -*- coding: utf-8 -*-
"""
market_event.py — Black Market Dynamic Economy & News Generator for ТГАЧ
Generates authentic, cynical, imageboard-themed market news and dynamically shifts
item multipliers across /shop, /wardrobe, and /work.

Синхронизирован со сменой торговых суток: запускается строго в 00:00 MSK (полночь).
При перезапусках бота состояние биржи восстанавливается из БД, без спама в треды.
"""

import asyncio
import time
import json
import random
from datetime import datetime, timezone, timedelta
from summarize import summarize_text_with_hf
from shared_state import (
    market_state, runtime_logger, BOARDS, GLOBAL_BOTS,
    enqueue_board_message, post_to_messages, messages_storage, state,
    board_data, storage_lock
)

MSK = timezone(timedelta(hours=3))

# -----------------------------------------------------------------------------
# Curated Authentic Imageboard & Crypto-Market Events Pool
# -----------------------------------------------------------------------------

CURATED_MARKET_EVENTS = [
    {
        "text": "🌐 <b>РКН выкатил новый список блокировок:</b> Спрос на Щиты и Маски Анонимуса подскочил на +35%, аноны спешно закупают средства теневой маскировки.",
        "mults": {'shield': 1.35, 'mute': 1.20, 'pepperspray': 1.15, 'janitor': 0.85, 'lootbox': 1.0}
    },
    {
        "text": "🚔 <b>ОБЛАВА НА КРИПТО-МАЙНЕРОВ!</b> Силовики накрыли подпольную ферму в гаражах: цены на Пативэны и Взятки выросли, аноны залегли на дно.",
        "mults": {'partyvan': 1.30, 'bribe': 1.40, 'shield': 1.15, 'knife': 0.90, 'lootbox': 0.85}
    },
    {
        "text": "🍺 <b>СКУФ-КРИЗИС:</b> Подорожание пенного привело к массовой забастовке работяг: спрос на Жилетки Вассермана и Шапочки из фольги бьёт рекорды!",
        "mults": {'tinfoil': 1.30, 'pills': 1.25, 'shit': 1.35, 'janitor': 1.10, 'lootbox': 1.10}
    },
    {
        "text": "📉 <b>ПАМП & ДАМП ШЕКЕЛЕЙ:</b> Крупный кит слил всю котлету на бирже: кейсы и лутбоксы распродаются со скидкой, а цены на Мут-Ганы взлетели!",
        "mults": {'lootbox': 0.80, 'mute': 1.35, 'knife': 1.25, 'shield': 0.90, 'prefix': 1.15}
    },
    {
        "text": "💊 <b>ДЕФИЦИТ В АПТЕКАХ:</b> На складах закончился запас галоперидола: цены на Шизо-таблетки и Проклятия подскочили, в тредах разгул шизофрении.",
        "mults": {'schizopill': 1.45, 'pills': 1.40, 'shit': 1.30, 'tinfoil': 1.25, 'bribe': 0.90}
    },
    {
        "text": "🧹 <b>САНИТАРНЫЙ ДЕНЬ В СПАЛЬНИКАХ:</b> ЖЭК объявил внеплановую аттестацию: Мётлы Дворника и Заточки в дефиците, на помойках ажиотаж.",
        "mults": {'janitor': 1.40, 'knife': 1.30, 'pepperspray': 1.20, 'partyvan': 0.85, 'lootbox': 1.05}
    },
    {
        "text": "🔥 <b>ПОЖАР В ДАТА-ЦЕНТРЕ:</b> Сгорела серверная стойка с логами анонов: цены на Щиты и Перцовые баллончики взлетели до максимума!",
        "mults": {'shield': 1.40, 'pepperspray': 1.30, 'mute': 1.25, 'prefix': 0.85, 'lootbox': 0.90}
    },
    {
        "text": "📦 <b>ТАМОЖЕННЫЙ КОНФИСКАТ:</b> На границе задержали контейнер с японским мерчем: бутики пустеют, а спрос на Золотые Сейфы зашкаливает!",
        "mults": {'lootbox': 1.30, 'badge_color': 1.35, 'prefix': 1.25, 'knife': 0.90, 'janitor': 0.95}
    },
    {
        "text": "🕶️ <b>СЛИВ БАЗЫ СТУКАЧЕЙ:</b> Неизвестные выложили в сеть досье информаторов: цены на Взятки и Пативэны удвоились, в /b/ объявлен режим паранойи.",
        "mults": {'bribe': 1.50, 'partyvan': 1.40, 'tinfoil': 1.35, 'shield': 1.20, 'schizopill': 1.15}
    },
    {
        "text": "💎 <b>СЕЗОН ЛЕГКИХ ДЕНЕГ:</b> Биржа Тгача зафиксировала рекордный приток новых мамонтов: ставки в казино растут, а цены на оружие стабилизировались.",
        "mults": {'lootbox': 0.90, 'mute': 1.15, 'knife': 1.15, 'janitor': 1.0, 'shield': 1.05}
    }
]


def seconds_until_next_midnight_msk(now_msk: datetime) -> tuple[datetime, float]:
    """Возвращает (целевое время MSK, секунды сна) до следующих 00:00:00 MSK."""
    target = (now_msk + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return target, max(1.0, (target - now_msk).total_seconds())


async def restore_market_state_from_db():
    """Восстанавливает сохраненное состояние биржи из БД при старте процесса без спама."""
    try:
        from common.db_pool import get_pool, db_lock
        db = await get_pool()
        async with db_lock:
            async with db.execute("SELECT value FROM GlobalStats WHERE key = 'market_state_json'") as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    data = json.loads(row[0])
                    if isinstance(data, dict):
                        market_state.update(data)
                        runtime_logger.info("Restored market_state from GlobalStats.")
                        return
    except Exception as e:
        runtime_logger.warning(f"Failed to restore market_state: {e}")


async def market_event_generator():
    """
    Фоновая задача: обновляет экономическую сводку и мультипликаторы черного рынка
    строго в полночь (00:00 MSK). При старте бота СПИТ до полуночи, подтянув цены из БД.
    """
    from common.db_pool import get_pool, db_lock
    from common.database import create_post

    # 1. При старте восстанавливаем сохраненные цены из базы без создания постов
    await restore_market_state_from_db()

    while True:
        try:
            now_msk = datetime.now(timezone.utc).astimezone(MSK)
            target_msk, sleep_sec = seconds_until_next_midnight_msk(now_msk)

            print(
                f"🛒 [BLACK MARKET] Следующее обновление черного рынка запланировано на "
                f"{target_msk.strftime('%Y-%m-%d %H:%M:%S')} MSK (через {sleep_sec / 3600:.1f} ч)"
            )

            await asyncio.sleep(sleep_sec)

            # Проснулись в полночь!
            # Проверяем защиту от дубликатов (не обновлялся ли рынок за последние 12 часов)
            db = await get_pool()
            now_ts = time.time()
            last_run_ts = 0.0
            async with db_lock:
                async with db.execute("SELECT value FROM GlobalStats WHERE key = 'last_market_event_run'") as cur:
                    row = await cur.fetchone()
                    if row and row[0]:
                        try:
                            last_run_ts = float(row[0])
                        except ValueError:
                            last_run_ts = 0.0

            if now_ts - last_run_ts < 43200:
                # Уже обновлялся недавно (например, при рестарте в 00:05)
                await asyncio.sleep(120)
                continue

            print("🛒 [BLACK MARKET] Обновление биржи и черного рынка...")

            # 2. Выбираем событие или генерируем через LLM
            event_obj = random.choice(CURATED_MARKET_EVENTS)
            event_text = event_obj["text"]
            base_mults = event_obj.get("mults", {})

            try:
                prompt = (
                    "Напиши одну короткую (1-2 предложения) циничную и смешную новость черного рынка для анонимного имиджборда (Двач/Тгач). "
                    "Темы: блокировки РКН, облавы майнеров, подорожание пива, дефицит таблеток, бунт скуфов, слив баз стукачей. "
                    "Стиль: саркастичный, реалистичный, без бессмысленного бреда и детских сказок. Только 1-2 предложения текста новости."
                )
                generated_text = await summarize_text_with_hf(prompt, "Новости", model_preference="llama")
                if generated_text and len(generated_text.strip()) > 20 and len(generated_text.strip()) < 300:
                    clean_gen = generated_text.strip().replace('"', '')
                    event_text = f"📊 <b>СВОДКА БИРЖИ:</b> {clean_gen}"
            except Exception:
                pass

            # 3. Формируем новые множители цен
            new_multipliers = {
                'janitor': round(base_mults.get('janitor', random.uniform(0.85, 1.30)), 2),
                'mute': round(base_mults.get('mute', random.uniform(0.85, 1.35)), 2),
                'shield': round(base_mults.get('shield', random.uniform(0.85, 1.40)), 2),
                'prefix': round(base_mults.get('prefix', random.uniform(0.90, 1.25)), 2),
                'partyvan': round(base_mults.get('partyvan', random.uniform(0.90, 1.35)), 2),
                'shit': round(base_mults.get('shit', random.uniform(0.85, 1.30)), 2),
                'pills': round(base_mults.get('pills', random.uniform(0.85, 1.35)), 2),
                'knife': round(base_mults.get('knife', random.uniform(0.85, 1.30)), 2),
                'pepperspray': round(base_mults.get('pepperspray', random.uniform(0.85, 1.30)), 2),
                'tinfoil': round(base_mults.get('tinfoil', random.uniform(0.85, 1.35)), 2),
                'bribe': round(base_mults.get('bribe', random.uniform(0.85, 1.40)), 2),
                'laxative': round(base_mults.get('laxative', random.uniform(0.85, 1.25)), 2),
                'badge_color': round(base_mults.get('badge_color', random.uniform(0.90, 1.25)), 2),
                'schizopill': round(base_mults.get('schizopill', random.uniform(0.85, 1.40)), 2),
                'lootbox': round(base_mults.get('lootbox', random.uniform(0.85, 1.25)), 2),
            }

            market_state['event_text'] = event_text
            market_state['multipliers'] = new_multipliers
            market_state['last_update'] = now_ts

            # 4. Сохраняем состояние в GlobalStats
            async with db_lock:
                await db.execute(
                    """
                    INSERT INTO GlobalStats (key, value) VALUES ('market_state_json', ?)
                    ON CONFLICT(key) DO UPDATE SET value = ?
                    """,
                    (json.dumps(dict(market_state)), json.dumps(dict(market_state)))
                )
                await db.execute(
                    """
                    INSERT INTO GlobalStats (key, value) VALUES ('last_market_event_run', ?)
                    ON CONFLICT(key) DO UPDATE SET value = ?
                    """,
                    (str(now_ts), str(now_ts))
                )
                await db.commit()

            # 5. Рассылаем новость в треды (только для досок с активностью >= 60 постов в час)
            one_hour_ago = int(now_ts) - 3600
            for board_id in BOARDS:
                try:
                    async with db.execute(
                        "SELECT COUNT(*) FROM Posts WHERE board_id = ? AND timestamp > ? AND author_id != -1",
                        (board_id, one_hour_ago)
                    ) as cur_act:
                        row_act = await cur_act.fetchone()
                        activity = row_act[0] if row_act else 0
                except Exception:
                    activity = 0

                if activity < 60:
                    continue

                msg_text = f"📉 <b>ТОРГОВАЯ СВОДКА ЧЕРНОГО РЫНКА (/shop)</b> 📈\n\n{event_text}\n\n<i>Цены на снаряжение и услуги обновлены.</i>"
                content = {'type': 'text', 'text': msg_text, 'is_system_message': True, 'archive_allowed': True}
                try:
                    post_num = await create_post(
                        author_id=-1,
                        board_id=board_id,
                        content=content,
                        timestamp=time.time(),
                        stream='ru'
                    )
                except Exception:
                    state['post_counter'] = state.get('post_counter', 0) + 1
                    post_num = state['post_counter']

                if post_num:
                    b_data = board_data.get(board_id, {})
                    recipients = set(b_data.get('users', {}).get('active', set())) - set(b_data.get('users', {}).get('banned', set()))
                    async with storage_lock:
                        state['post_counter'] = max(state.get('post_counter', 0), post_num)
                        post_to_messages[post_num] = {}
                        messages_storage[post_num] = {
                            'board_id': board_id,
                            'author_id': -1,
                            'content': content,
                            'timestamp': time.time()
                        }
                    if recipients:
                        await enqueue_board_message(board_id, {
                            'recipients': recipients,
                            'board_id': board_id,
                            'post_num': post_num,
                            'author_id': -1,
                            'author_name': 'Black Market',
                            'content': content,
                            'reply_to': None,
                            'is_op': False
                        })

            runtime_logger.info(f"Market event generated: {event_text}")
            await asyncio.sleep(120)

        except Exception as e:
            runtime_logger.error(f"Error in market_event_generator: {e}")
            await asyncio.sleep(60)
