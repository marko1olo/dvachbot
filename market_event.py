import asyncio
import time
import json
import random
from summarize import summarize_text_with_hf
from shared_state import market_state, runtime_logger, BOARDS, GLOBAL_BOTS, enqueue_board_message, post_to_messages, messages_storage, state

async def market_event_generator():
    """Фоновая задача, которая раз в сутки генерирует рыночное событие через ИИ и меняет цены"""
    await asyncio.sleep(60) # отложенный старт 1 мин
    while True:
        try:
            # 1. Генерируем событие
            prompt = "Ты — ебанутый аналитик черного рынка на Дваче. Придумай одно короткое (1-2 предложения), абсолютно безумное событие, которое обрушило или подняло цены на нелегальные товары (щиты, проклятия, оружие). Например: 'Фура с Аминазином перевернулась под Мухосранском, цены на щиты упали!'. Используй черный юмор, мат, шизофрению. Только текст события."
            try:
                event_text = await summarize_text_with_hf(prompt, "Генерируй", model_preference="llama")
            except Exception:
                event_text = "Биржа черного рынка упала, все цены рандомизированы, пиздец."
                
            # 2. Рандомизируем цены (множители от 0.5 до 2.5)
            new_multipliers = {
                'janitor': round(random.uniform(0.5, 2.5), 2),
                'mute': round(random.uniform(0.5, 2.5), 2),
                'shield': round(random.uniform(0.5, 2.5), 2),
                'prefix': round(random.uniform(0.5, 2.5), 2),
                'partyvan': round(random.uniform(0.5, 2.5), 2),
                'shit': round(random.uniform(0.5, 2.5), 2),
                'pills': round(random.uniform(0.5, 2.5), 2),
                'knife': round(random.uniform(0.5, 2.5), 2),
                'tinfoil': round(random.uniform(0.5, 2.5), 2),
                'bribe': round(random.uniform(0.5, 2.5), 2),
                'laxative': round(random.uniform(0.5, 2.5), 2),
                'megaphone': round(random.uniform(0.5, 2.5), 2),
            }
            
            market_state['event_text'] = event_text
            market_state['multipliers'] = new_multipliers
            market_state['last_update'] = time.time()
            
            # 3. Рассылаем новость на борды
            bot_instance = None
            if GLOBAL_BOTS:
                bot_instance = list(GLOBAL_BOTS.values())[0]
            
            if bot_instance:
                for board_id in BOARDS:
                    msg_text = f"📉 <b>НОВОСТИ ЧЕРНОГО РЫНКА (/shop)</b> 📈\n\n{event_text}\n\n<i>Цены на товары изменились!</i>"
                    state['post_counter'] += 1
                    post_num = state['post_counter']
                    content = {'type': 'text', 'text': msg_text}
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
            
        # Ждем сутки (24 часа)
        await asyncio.sleep(86400)
