# -*- coding: utf-8 -*-
"""
market_event.py — Black Market Dynamic Economy & News Generator for ТГАЧ
Generates authentic, cynical, imageboard-themed market news and dynamically shifts
item multipliers across /shop, /wardrobe, and /work.
"""

import asyncio
import time
import json
import random
from summarize import summarize_text_with_hf
from shared_state import (
    market_state, runtime_logger, BOARDS, GLOBAL_BOTS,
    enqueue_board_message, post_to_messages, messages_storage, state
)

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


async def market_event_generator():
    """Фоновая задача: периодически обновляет экономическую сводку и мультипликаторы черного рынка"""
    await asyncio.sleep(30)  # Старт через 30 сек после запуска
    while True:
        try:
            # 1. Выбираем реалистичное событие или генерируем через LLM со строгим промптом
            event_obj = random.choice(CURATED_MARKET_EVENTS)
            event_text = event_obj["text"]
            base_mults = event_obj.get("mults", {})

            # Попробуем сгенерировать уникальную вариацию, если доступна LLM
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

            # 2. Формируем множители цен (в пределах 0.75 – 1.45)
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
            market_state['last_update'] = time.time()

            # 3. Рассылаем новость в треды
            bot_instance = None
            if GLOBAL_BOTS:
                bot_instance = list(GLOBAL_BOTS.values())[0]

            if bot_instance:
                from common.database import create_post
                for board_id in BOARDS:
                    msg_text = f"📉 <b>ТОРГОВАЯ СВОДКА ЧЕРНОГО РЫНКА (/shop)</b> 📈\n\n{event_text}\n\n<i>Цены на снаряжение и услуги обновлены.</i>"
                    content = {'type': 'text', 'text': msg_text}
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
                        state['post_counter'] = max(state.get('post_counter', 0), post_num)
                        post_to_messages[post_num] = {}
                        messages_storage[post_num] = {
                            'board_id': board_id,
                            'author_id': -1,
                            'content': content,
                            'timestamp': time.time()
                        }
                        await enqueue_board_message(board_id, {
                            'board_id': board_id,
                            'post_num': post_num,
                            'author_id': -1,
                            'author_name': 'Black Market',
                            'content': content,
                            'reply_to': None,
                            'is_op': False
                        })

            runtime_logger.info(f"Market event generated: {event_text}")

        except Exception as e:
            runtime_logger.error(f"Error in market_event_generator: {e}")

        # Ждем 24 часа
        await asyncio.sleep(86400)
