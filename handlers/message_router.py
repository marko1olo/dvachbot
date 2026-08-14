import shared_state
from aiogram.types import Message
from aiogram import Router, types
from aiogram.filters import Command

message_router = Router()

import asyncio
from datetime import datetime, timedelta, timezone, UTC
import logging
import random
import re
import time
from typing import Optional
from aiogram import Bot, F, types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

logger = logging.getLogger(__name__)

import itertools
from common.config import *
from common.board_config import BOARD_CONFIG
from common.html_utils import escape_html
from common.text_utils import clean_html_tags, sanitize_html
from common.database import get_post_by_num, update_post_content, get_pool, get_max_post_num, add_or_activate_user, update_shadow_mute
from common.db_pool import db_lock
from common.spam_filter import _check_cross_board_spam, check_rate_limit as _check_rate_limit
from post_helpers import _quote_info_from_content
from media_utils import extract_msg_media_file_id
from shared_state import *
from shared_state import _media_group_state_key, _active_duels, _DUEL_TIMEOUT

from common.task_manager import spawn_task
from delivery_manager import execute_delayed_edit, complete_media_group_after_delay
from broadcaster import send_message_to_users
from post_helpers import format_header
from common.thread_manager import get_thread_info
from common.bot_helpers import _get_user_active_items
from common.bot_helpers import delete_message_after_delay
from common.database import get_post_info_by_copy
from common.bot_helpers import process_new_post
from common.bot_helpers import accept_duel_logic, decline_duel_logic
from bot_helpers import is_admin, _get_msg_content_and_type
from common.spam_filter import analyze_message_for_spam, SpamResult, is_spam_filtered, acquire_spam_lock, get_spam_violation_level, SPAM_RULES, _check_repeats
from text_assets import (
    EARNING_NOTIFICATIONS, REACTION_NOTIFY_PHRASES, ALBUM_EDUCATION_PHRASES, 
    CASINO_FUCK_OFF_PHRASES, CASINO_FUCK_OFF_PHRASES_EN, CASINO_FUCK_OFF_PHRASES_JP
)
from ai_manager import schedule_persona_reply, check_and_send_contextual_reply, transcribe_and_roast_voice_note
import __main__ as main

# Some functions like `spawn_task` and `execute_delayed_edit` are in main.py, 
# but they might cause cyclic imports if imported directly. We will try importing them.




# Duel logic


# Anime state



# Reactions


@message_router.message_reaction()
async def handle_message_reaction(reaction: types.MessageReactionUpdated, board_id: str | None, bot_instance: Optional[Bot] = None):
    """
    Обрабатывает реакции: уведомления автору и репост в канал "Лучшее".
    Исправлено: теперь ищет пост в БД, если он выгружен из RAM.
    """
    try:
        # reaction.user — необязательное поле Telegram API: оно приходит только
        # для неанонимного пользователя, иначе заполняется actor_chat (реакция
        # от имени канала или анонимного админа). Раньше на таком апдейте
        # user.id давал AttributeError, его проглатывал внешний except, и в лог
        # уходила невнятная «Ошибка в handle_message_reaction».
        if reaction.user is None:
            return
        user_id = reaction.user.id
        now = time.time()
        if now - reaction_ratelimit[user_id] < 0.5:
            return
        reaction_ratelimit[user_id] = now
        chat_id = reaction.chat.id
        message_id = reaction.message_id
        if not board_id: return
        b_data = board_data[board_id]
        
        is_shadow_muted = (user_id in b_data.get('shadow_mutes', {}) and 
                           b_data['shadow_mutes'][user_id] > datetime.now(UTC))
        if is_shadow_muted or user_id in b_data.get('reaction_banned_users', set()):
            return
        post_num = None
        async with storage_lock:
            post_num = message_to_post.get((chat_id, message_id))
        if not post_num:
            db_info = await get_post_info_by_copy(chat_id, message_id)
            if db_info:
                post_num, _ = db_info
                db_post = await get_post_by_num(post_num)
                if db_post:
                    content_dict = db_post['content'] if isinstance(db_post['content'], dict) else {}
                    reactions_dict = content_dict.get('reactions', {'users': {}})
                    async with storage_lock:
                        messages_storage[post_num] = {
                            'author_id': db_post['author_id'],
                            'timestamp': datetime.fromtimestamp(db_post['timestamp'], UTC) if isinstance(db_post['timestamp'], (int, float)) else db_post['timestamp'],
                            'content': content_dict,
                            'reactions': reactions_dict,
                            'board_id': db_post['board_id'],
                            'thread_id': db_post.get('thread_id')
                        }
                        message_to_post[(chat_id, message_id)] = post_num

        if not post_num:
            return

        author_message_id_for_reply = None
        current_positive_count = 0
        is_already_best = False
        
        async with storage_lock:
            post_data = messages_storage.get(post_num)
            if not post_data:
                return
            
            author_id = post_data.get('author_id')
            if author_id:
                raw_reply = post_to_messages.get(post_num, {}).get(author_id)
                author_message_id_for_reply = raw_reply[0] if isinstance(raw_reply, list) else raw_reply
            
            if 'reactions' not in post_data or not isinstance(post_data.get('reactions'), dict) or 'users' not in post_data['reactions']:
                if isinstance(post_data.get('content'), dict) and 'reactions' in post_data['content']:
                    post_data['reactions'] = post_data['content']['reactions']
                else:
                    post_data['reactions'] = {'users': {}}
            if 'users' not in post_data['reactions'] or not isinstance(post_data['reactions']['users'], dict):
                post_data['reactions']['users'] = {}
            
            reactions_storage = post_data['reactions']['users']
            old_emojis = set(reactions_storage.get(user_id, []) or reactions_storage.get(str(user_id), []))
            new_emojis = [r.emoji for r in reaction.new_reaction if r.type == 'emoji']
            
            if not new_emojis:
                reactions_storage.pop(user_id, None)
                reactions_storage.pop(str(user_id), None)
            else:
                reactions_storage[user_id] = new_emojis[:2]
                reactions_storage.pop(str(user_id), None)
            
            # Синхронизируем реакции в content для сохранения в БД
            if isinstance(post_data.get('content'), dict):
                post_data['content']['reactions'] = post_data['reactions']
            
            for u_emojis in reactions_storage.values():
                for em in u_emojis:
                    if em in POSITIVE_REACTIONS or em in LAUGHING_REACTIONS:
                        current_positive_count += 1
            
            is_already_best = post_data.get('forwarded_to_best', False)
            content_to_save = post_data.get('content', {}).copy()

        # Сохраняем обновленный контент с реакциями в БД (вне lock для производительности)
        if content_to_save:
            await update_post_content(post_num, content_to_save)
            if current_positive_count >= LIKES_THRESHOLD and not is_already_best:
                post_data['forwarded_to_best'] = True
        if current_positive_count >= LIKES_THRESHOLD and not is_already_best:
            final_bot = bot_instance if bot_instance else reaction.bot
            if final_bot:
                try:
                    board_name = BOARD_CONFIG[board_id]['name']
                    bot_uname = BOARD_CONFIG.get(board_id, {}).get('username', 'dvach_chatbot').lstrip('@')
                    caption = f"🔥 <b>Годнота с {board_name}</b> (Пост #{post_num})\n\n👉 <a href=\"https://t.me/{bot_uname}\">Зайти в бота</a>"
                    await final_bot.copy_message(
                        chat_id=BEST_CHANNEL_ID,
                        from_chat_id=chat_id,
                        message_id=message_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    print(f"🌟 Пост #{post_num} отправлен в канал 'Лучшее' ({current_positive_count} лайков).")
                except TelegramForbiddenError as e:
                    logger.warning("TelegramForbiddenError reposting to Best channel: %s", e)
                except TelegramBadRequest as e:
                    logger.warning("TelegramBadRequest reposting to Best channel (original message missing): %s", e)
                except TelegramRetryAfter as e:
                    delay = float(getattr(e, "retry_after", 5) or 5) + 1.0
                    await asyncio.sleep(delay)
                except Exception as e:
                    logger.exception("Failed to repost to Best channel: %s", e)
        if author_id == user_id or author_id == 0: return
        REACTION_LIMIT_PER_MINUTE = 5
        REACTION_WINDOW_SECONDS = 60
        should_trigger_edit = True
        rate_tracker = b_data['reaction_rate_tracker'][user_id]
        now = time.time()
        while rate_tracker and now - rate_tracker[0] > REACTION_WINDOW_SECONDS:
            if isinstance(rate_tracker, list):
                rate_tracker.pop(0)
            else:
                rate_tracker.popleft()
        if len(rate_tracker) >= REACTION_LIMIT_PER_MINUTE:
            should_trigger_edit = False
            if post_num not in b_data['reaction_queue'][user_id]:
                b_data['reaction_queue'][user_id].append(post_num)
        else:
            rate_tracker.append(now)
        # === ENTERPRISE ЛОГИКА НАЧИСЛЕНИЯ (SQLITE ATOMIC + EXPLORE PROTECTION) ===
        if author_id and author_id != user_id and author_id != 0:
            # Проверяем, добавляется ли реакция (а не убирается)
            if len(reaction.new_reaction) > len(reaction.old_reaction):
                
                async with storage_lock:
                    post_data = messages_storage.get(post_num)
                    if not post_data:
                        return # Пост слишком старый или выгружен из памяти
                    
                    # Инициализируем список оплаченных реакторов для этого поста
                    if 'paid_reactors' not in post_data:
                        post_data['paid_reactors'] = set()
                    
                    # ЗАЩИТА ОТ АБУЗА: Если этот юзер уже "платил" за этот пост, выходим
                    if user_id in post_data['paid_reactors']:
                        return
                    
                    # Фиксируем оплату
                    post_data['paid_reactors'].add(user_id)

                
                async with db_lock:
                    db = await get_pool()
                    
                    # Сумма вознаграждения за одну реакцию
                    reward_per_reaction = random.randint(3, 9)
                    
                    # 1. Начисляем деньги (UPSERT)
                    await db.execute(
                        """
                        INSERT INTO Users (user_id, board_id, balance, reaction_reward_counter) 
                        VALUES (?, ?, ?, 1) 
                        ON CONFLICT(user_id, board_id) DO UPDATE SET 
                        balance = balance + ?, 
                        reaction_reward_counter = reaction_reward_counter + 1
                        """,
                        (author_id, board_id, reward_per_reaction, reward_per_reaction)
                    )
                    
                    # 2. Проверяем счетчик для отправки уведомления (каждые 6 реакций)
                    async with db.execute(
                        "SELECT reaction_reward_counter FROM Users WHERE user_id = ? AND board_id = ?",
                        (author_id, board_id)
                    ) as c:
                        row = await c.fetchone()
                    
                    # --- НАЧАЛО ИЗМЕНЕНИЙ (Изменение порога уведомлений) ---
                    if row and row[0] >= 6:
                        # Сбрасываем счетчик уведомлений
                        await db.execute(
                            "UPDATE Users SET reaction_reward_counter = 0 WHERE user_id = ? AND board_id = ?", 
                            (author_id, board_id)
                        )
                    # --- КОНЕЦ ИЗМЕНЕНИЙ ---
                        
                        # Получаем итоговый ГЛОБАЛЬНЫЙ баланс для солидности текста
                        async with db.execute("SELECT SUM(balance) FROM Users WHERE user_id = ?", (author_id,)) as c_sum:
                            sum_row = await c_sum.fetchone()
                            global_balance = sum_row[0] if sum_row and sum_row[0] else 0
                        
                        # 3. Отправляем уведомление (шанс 50%, чтобы не спамить слишком часто)
                        if random.random() < 0.5:
                            # В тексте пишем сумму чуть больше, как будто за "пакет реакций"
                            display_reward = random.randint(15, 28)
                            notif_tpl = random.choice(EARNING_NOTIFICATIONS)
                            notif_text = notif_tpl.format(amount=display_reward, balance=int(global_balance))
                            
                            # Используем bot_instance, переданный в функцию.
                            # Отправляем отдельной задачей, а не await: этот код
                            # выполняется ПОД db_lock, который сериализует весь
                            # доступ к базе в процессе. Ждать здесь сетевой
                            # вызов — значит остановить работу с БД во всём боте
                            # ради необязательного уведомления.
                            final_bot = bot_instance if bot_instance else reaction.bot
                            spawn_task(_send_notification_quietly(
                                final_bot, author_id, notif_text
                            ))
        if should_trigger_edit:
            author_id_for_notify = None
            text_for_notify = None
            newly_added = set(new_emojis) - old_emojis
            if newly_added and author_id:
                async with author_reaction_notify_lock:
                    now_n = time.time()
                    a_timestamps = author_reaction_notify_tracker[author_id]
                    while a_timestamps and a_timestamps[0] <= now_n - 60:
                        if isinstance(a_timestamps, list):
                            a_timestamps.pop(0)
                        else:
                            a_timestamps.popleft()
                    if len(a_timestamps) < AUTHOR_NOTIFY_LIMIT_PER_MINUTE:
                        a_timestamps.append(now_n)
                        author_id_for_notify = author_id
                        lang = 'en' if board_id == 'int' else 'ru'
                        emoji = list(newly_added)[0]
                        category = 'neutral'
                        if emoji in POSITIVE_REACTIONS: category = 'positive'
                        elif emoji in LAUGHING_REACTIONS: category = 'laughing'
                        elif emoji in NEGATIVE_REACTIONS: category = 'negative'
                        elif emoji in CLOWN_REACTION: category = 'clown'
                        elif emoji in THINKING_REACTIONS: category = 'thinking'
                        elif emoji in SHOCK_REACTIONS: category = 'shock'
                        elif emoji in SAD_REACTIONS: category = 'sad'
                        elif emoji in POLITICAL_REACTIONS: category = 'political'
                        elif emoji in SYMBOLIC_REACTIONS: category = 'symbolic'
                        elif emoji in INSULT_REACTIONS: category = 'insult'
                        phrases = REACTION_NOTIFY_PHRASES.get(lang, {}).get(category) or REACTION_NOTIFY_PHRASES.get('ru', {}).get('positive', [])
                        if phrases:
                            phrase_template = random.choice(phrases)
                            try:
                                text_for_notify = phrase_template.format(post_num=post_num)
                            except Exception:
                                text_for_notify = None
            final_bot_instance = bot_instance if bot_instance else reaction.bot
            if not final_bot_instance: return
            async with pending_edit_lock:
                if post_num in pending_edit_tasks: pending_edit_tasks[post_num].cancel()
                new_task = spawn_task(execute_delayed_edit(post_num, final_bot_instance, author_id_for_notify, text_for_notify, reply_to_message_id=author_message_id_for_reply))
                pending_edit_tasks[post_num] = new_task
    except Exception as e:
        print(f"❌ Ошибка в handle_message_reaction: {e}")

@message_router.message(~F.media_group_id)
async def handle_message(message: Message, board_id: str | None, stream: str = 'ru'):
    user_id = message.from_user.id
    print(f"📩 [MSG RECEIVED] user={user_id} chat={message.chat.id} board={board_id} text={repr(message.text or message.caption or message.content_type)}")
    if not board_id:
        print(f"⚠️ [MSG REJECTED] board_id is None for user={user_id} bot={message.bot.id}")
        return
    if board_id in THREAD_BOARDS:
        if await ensure_user_in_valid_thread(message.bot, board_id, user_id):
            try: await message.delete()
            except TelegramBadRequest: pass
            return
    b_data = board_data[board_id]
    
    is_reply_to_bot = False
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == message.bot.id:
        is_reply_to_bot = True

    if is_reply_to_bot:
        if 'persona_favorites' not in b_data:
            b_data['persona_favorites'] = {}
        b_data['persona_favorites'][user_id] = b_data['persona_favorites'].get(user_id, 0) + 1

    if message.content_type in ['photo', 'video', 'document']:
        b_data['single_photo_counter'][user_id]
        if not message.media_group_id:
            b_data['single_photo_counter'][user_id] += 1
            current_count = b_data['single_photo_counter'][user_id]
            if current_count > 5:
                b_data['single_photo_counter'][user_id] = 0
                lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                phrases = ALBUM_EDUCATION_PHRASES.get(lang, ALBUM_EDUCATION_PHRASES['ru'])
                edu_text = random.choice(phrases)
                try:
                    sent = await message.answer(edu_text)
                    spawn_task(delete_message_after_delay(sent, 20))
                except Exception: pass
        else:
            b_data['single_photo_counter'][user_id] = 0
    elif message.content_type == 'text':
        b_data['single_photo_counter'][user_id] = 0
    try:
        if message.content_type == 'dice':
            try:
                await message.delete()
            except Exception:
                pass
            last_insult_time = b_data.get('last_roll_time', {}).get(user_id, 0)
            now = time.time()
            if now - last_insult_time > 5:
                lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
                if lang == 'en':
                    phrases = CASINO_FUCK_OFF_PHRASES_EN
                elif lang == 'jp':
                    phrases = CASINO_FUCK_OFF_PHRASES_JP
                else:
                    phrases = CASINO_FUCK_OFF_PHRASES
                fuck_off_text = random.choice(phrases)
                try:
                    sent_msg = await message.answer(fuck_off_text)
                    spawn_task(delete_message_after_delay(sent_msg, 7))
                    b_data.setdefault('last_roll_time', {})[user_id] = now
                except Exception: 
                    pass
            return
        supported_types = ['text', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note'] 
        if message.content_type not in supported_types:
            await message.delete()
            return
        if message.content_type == 'text' and not (message.text and message.text.strip()):
            await message.delete()
            return
        if user_id in b_data['users']['banned']:
            try:
                await message.delete()
            except TelegramBadRequest: pass
            return
        mute_until = b_data['mutes'].get(user_id)
        if mute_until and mute_until > datetime.now(UTC):
            try:
                await message.delete()
            except TelegramBadRequest: pass
            return
        elif mute_until:
            b_data['mutes'].pop(user_id, None)
            
        cursed_text_override = None
        if message.content_type == 'text' or (message.caption and message.content_type in ['photo', 'video', 'document', 'animation', 'audio', 'voice']):
            db_p = await get_pool()
            c_items = await _get_user_active_items(db_p, user_id, board_id)
            if c_items.get("cursed_until", 0) > time.time():
                from summarize import summarize_text_with_hf
                original_text = message.text or message.caption or ""
                prompt = "Перепиши этот текст от лица человека, у которого прямо во время речи начался взрывной понос. Прерывай предложения многоточиями, вставляй крики боли (ААА, БЛЯЯ, УУУФ), звуки бульканья в животе (БУРЛК-БУРЛК) и панику. Обязательно сохрани изначальный смысл текста, но пропусти его через призму невыносимой боли в животе и попыток сдержать кал. Пиши грязно, сыро, без ИИ-шаблонов. Текст жертвы:"
                try:
                    rewritten = await summarize_text_with_hf(prompt, original_text, model_preference="llama")
                    if len(rewritten) > 1000:
                        rewritten = rewritten[:1000]
                except Exception:
                    rewritten = "БУРЛК-БУРЛК... БЛЯЯЯЯ! Я... я обосрался... " + original_text[:50]
                
                try: await message.delete()
                except Exception: pass
                
                cursed_text_override = f"🚽 [ПРОКЛЯТЫЙ ПОНОСОМ]\n{rewritten}"

            if c_items.get("schizo_pill_until", 0) > time.time() and not cursed_text_override:
                from summarize import summarize_text_with_hf
                original_text = message.text or message.caption or ""
                prompt = "Перепиши этот текст от лица абсолютно поехавшего шизофреника, конспиролога и параноика. Везде заговоры, рептилоиды, ЦРУ, излучение от вышек 5G и массоны. Перескакивай с мысли на мысль, пиши капсом случайные СЛОВА, используй много восклицательных знаков и вопросов. Сохрани изначальный смысл текста, но пропусти его через шизофазию и паранойю. Текст пациента:"
                try:
                    rewritten = await summarize_text_with_hf(prompt, original_text, model_preference="llama")
                    if len(rewritten) > 1000:
                        rewritten = rewritten[:1000]
                except Exception:
                    rewritten = "ОНИ СЛЕДЯТ ЗА МНОЙ!! ВЫШКИ ОБЛУЧАЮТ!! " + original_text[:50]
                
                try: await message.delete()
                except Exception: pass
                
                cursed_text_override = f"👽 [ШИЗО-ТАБЛЕТКА]\n{rewritten}"

                
        b_data['last_activity'][user_id] = datetime.now(UTC)
        if user_id not in b_data['users']['active']:
            b_data['users']['active'].add(user_id)
            b_data.setdefault('user_settings', {})[user_id] = {'nsfw': False, 'hide': set()}
            await add_or_activate_user(user_id, board_id)
            print(f"✅ [{board_id}] Добавлен новый пользователь: ID {user_id}")
        if board_id != 'trash' and not await check_spam(user_id, message, board_id):
            try:
                await message.delete()
            except TelegramBadRequest: pass
            msg_type = message.content_type
            if msg_type in ['photo', 'video', 'document'] and message.caption:
                msg_type = 'text'
            await apply_penalty(message.bot, user_id, msg_type, board_id)
            return
            
        import troll_phrases
        if random.random() < 0.0075:
            phrase = troll_phrases.get_random_troll_phrase()
            try:
                spawn_task(message.answer(phrase))
            except Exception:
                pass
                
        is_sage = False 
        h_val = getattr(message, 'html_text', None)
        c_val = getattr(message, 'caption_html_text', None)
        html_text_content = (h_val if isinstance(h_val, str) else None) or (c_val if isinstance(c_val, str) else None) or message.text or message.caption or ""
        plain_text_check = (message.text or message.caption or "").lower().strip()
        if plain_text_check.startswith("sage") or plain_text_check.startswith("сажа"):
            is_sage = True
        def replacer(match):
            plain_text_quote = clean_html_tags(match.group(0))
            return f"↪️ <code>{escape_html(plain_text_quote)}</code>"
        processed_html_text = RE_REPLY_QUOTE_FORMAT.sub(replacer, html_text_content)
    except (TelegramBadRequest, TelegramForbiddenError): return
    except Exception as e:
        print(f"Error in handle_message: {e}")
        return
    # Собираем текст для поиска мульти-ответов из текста или подписи к медиа
    input_text = cursed_text_override if cursed_text_override else (message.text or message.caption or "")
    multi_reply_blocks, limit_hit = _parse_and_split_multi_replies(input_text)
    
    is_shadow_muted = (user_id in b_data['shadow_mutes'] and 
                       b_data['shadow_mutes'][user_id] > datetime.now(UTC))
                       
    if multi_reply_blocks:
        try: await message.delete()
        except TelegramBadRequest: pass
        
        # Предварительно извлекаем данные о медиа, если они есть
        media_type = message.content_type if message.content_type != 'text' else None
        media_file_id = None
        media_meta = {}
        if media_type:
            file_obj = getattr(message, media_type)
            if isinstance(file_obj, list):
                file_obj = file_obj[-1]
            media_file_id = file_obj.file_id
            file_name = getattr(file_obj, 'file_name', None)
            mime_type = getattr(file_obj, 'mime_type', None)
            if file_name:
                media_meta['filename'] = file_name
            if mime_type:
                media_meta['mime_type'] = mime_type

        for i, (post_num_to_reply, text_chunk) in enumerate(multi_reply_blocks):
            # Проверяем существование поста (сначала в RAM, потом в БД)
            post_exists = post_num_to_reply in messages_storage
            if not post_exists:
                if await get_post_by_num(post_num_to_reply):
                    post_exists = True
            
            if not post_exists:
                continue
            
            formatted_chunk = RE_REPLY_QUOTE_FORMAT.sub(replacer, escape_html(text_chunk))
            
            # Прикрепляем медиа к первому посту в цепочке ответов, остальные — текст
            if i == 0 and media_type:
                content = {'type': media_type, 'file_id': media_file_id, 'caption': formatted_chunk}
                content.update(media_meta)
            else:
                content = {'type': 'text', 'text': formatted_chunk}
            quote_info = await build_quick_quote_info(post_num_to_reply)
            if quote_info:
                content['quote_info'] = quote_info
                
            if is_sage: content['is_sage'] = True
            
            if not is_shadow_muted and text_chunk:
                if is_spam_filtered(text_chunk, board_id, user_id):
                    is_shadow_muted = True 
                else:
                    spawn_task(check_and_send_contextual_reply(message.bot, user_id, text_chunk, board_id, stream=stream))
            
            if is_shadow_muted:
                await process_shadow_reject(shared_state.ShadowRejectContext(
                    bot=message.bot,
                    board_id=board_id,
                    user_id=user_id,
                    content=content,
                    reply_to_post=post_num_to_reply,
                    stream=stream
                ))
            else:
                post_num = await process_new_post(shared_state.NewPostParams(
                    bot_instance=message.bot,
                    board_id=board_id,
                    user_id=user_id,
                    content=content,
                    reply_to_post=post_num_to_reply,
                    is_shadow_muted=False,
                    stream=stream
                ))
                if post_num:
                    should_reply = False
                    if is_reply_to_bot:
                        now_t = time.time()
                        last_user_t = last_persona_dialogue_user_ts.get(user_id, 0)
                        if (now_t - last_user_t >= 45.0) and (random.random() < 0.35):
                            should_reply = True
                            last_persona_dialogue_user_ts[user_id] = now_t
                    elif user_id in b_data.get('persona_favorites', {}):
                        now_t_fav = time.time()
                        if (now_t_fav - last_persona_board_ts.get(board_id, 0) >= 90.0) and text_chunk and len(text_chunk) > 5 and random.random() < 0.08:
                            should_reply = True
                    else:
                        # Глобальный пассивный тригер: 4%
                        now_t_glob = time.time()
                        if (now_t_glob - last_persona_board_ts.get(board_id, 0) >= 120.0) and text_chunk and len(text_chunk) > 5 and random.random() < 0.04:
                            should_reply = True
                    if should_reply:
                        last_persona_board_ts[board_id] = time.time()  # race guard
                        text_payload = text_chunk or f"[{message.content_type}]"
                        photo_id = message.photo[-1].file_id if message.photo else None
                        spawn_task(schedule_persona_reply(message.bot, board_id, post_num, text_payload, stream, is_admin_trigger=False, photo_file_id=photo_id, is_dialogue=is_reply_to_bot))
                    # --- THE ANCHOR (Мудрый Чед) ---
                    from anchor_bot import anchor_tick, trigger_anchor_post
                    if anchor_tick(board_id):
                        spawn_task(trigger_anchor_post(message.bot, board_id, stream))
            await asyncio.sleep(0.33)
            
        if limit_hit:
            try:
                await message.bot.send_message(user_id, "Replies limit reached (3 max).", disable_notification=True)
            except TelegramForbiddenError:
                try:
                    import __main__ as main
                    if hasattr(main, 'purge_users_from_board_ram'):
                        await main.purge_users_from_board_ram(board_id, [user_id])
                except Exception:
                    pass
            except TelegramBadRequest as e:
                logger.warning("TelegramBadRequest sending limit_hit to user %s: %s", user_id, e)
            except TelegramRetryAfter as e:
                await asyncio.sleep(float(getattr(e, "retry_after", 5) or 5) + 1.0)
            except Exception as e:
                logger.exception("Failed to send limit_hit message to %s: %s", user_id, e)
        return
    # Проверка текстового ответа на дуэль (без слеша)
    if message.reply_to_message and message.text:
        text_clean = message.text.lower().strip()
        if text_clean in ("accept", "принять", "yes", "да", "ok", "ок", "+"):
            reply_msg_id = message.reply_to_message.message_id
            now = time.time()
            found_ch = None
            for ch_id, duel in list(_active_duels.items()):
                if duel.get("msg_id") == reply_msg_id and duel["board_id"] == board_id and now - duel["ts"] < _DUEL_TIMEOUT:
                    found_ch = ch_id
                    break
            if found_ch:
                try: await message.delete()
                except Exception: pass
                await accept_duel_logic(message, found_ch, board_id)
                return
                
        elif text_clean in ("decl", "отклонить", "no", "нет", "-"):
            reply_msg_id = message.reply_to_message.message_id
            now = time.time()
            found_ch = None
            for ch_id, duel in list(_active_duels.items()):
                if duel.get("msg_id") == reply_msg_id and duel["board_id"] == board_id and now - duel["ts"] < _DUEL_TIMEOUT:
                    found_ch = ch_id
                    break
            if found_ch:
                try: await message.delete()
                except Exception: pass
                await decline_duel_logic(message, found_ch)
                return

    try: await message.delete()
    except TelegramBadRequest: pass
    reply_to_post = None
    if message.reply_to_message:
        async with storage_lock:
            lookup_key = (message.chat.id, message.reply_to_message.message_id)
            reply_to_post = message_to_post.get(lookup_key)
        if not reply_to_post:
            info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
            if info:
                reply_to_post = info[0]
        if not reply_to_post:
            replied_msg = message.reply_to_message
            text_to_scan = replied_msg.text or replied_msg.caption or ""
            match = re.search(r"(?:№|#|Post No\.|Пост №|レス番)\s*(\d+)", text_to_scan, re.IGNORECASE)
            if match:
                potential_id = int(match.group(1))
                if await get_post_by_num(potential_id):
                    reply_to_post = potential_id
                    async with storage_lock:
                        message_to_post[lookup_key] = reply_to_post
                    print(f"👀 ID #{reply_to_post} восстановлен через чтение текста сообщения!")
    content = {'type': message.content_type}
    text_for_corpus = None
    # file_unique_id из апдейта Telegram — основа определения баяна.
    # Ничего не качаем и не хешируем, просто читаем готовое поле.
    _media_unique_id = None
    if message.content_type == 'text':
        text_for_corpus = message.text
        html_val = getattr(message, 'html_text', None)
        raw_text_html = html_val if isinstance(html_val, str) else (message.text or "")
        safe_html_text = sanitize_html(raw_text_html)
        content.update({'text': safe_html_text})
    elif message.content_type in ['photo', 'video', 'animation', 'document', 'audio', 'voice']:
        text_for_corpus = message.caption
        file_id_obj = getattr(message, message.content_type, [])
        if isinstance(file_id_obj, list): file_id_obj = file_id_obj[-1]
        caption_html_val = getattr(message, 'caption_html_text', None)
        raw_caption_html = caption_html_val if isinstance(caption_html_val, str) else (message.caption or "")
        safe_caption_html = sanitize_html(raw_caption_html)
        content.update({'file_id': file_id_obj.file_id, 'caption': safe_caption_html})
        _media_unique_id = getattr(file_id_obj, 'file_unique_id', None)
        file_name = getattr(file_id_obj, 'file_name', None)
        mime_type = getattr(file_id_obj, 'mime_type', None)
        if file_name:
            content['filename'] = file_name
        if mime_type:
            content['mime_type'] = mime_type
    elif message.content_type in ['sticker', 'video_note']:
        file_id_obj = getattr(message, message.content_type)
        content.update({'file_id': file_id_obj.file_id})
        _media_unique_id = getattr(file_id_obj, 'file_unique_id', None)
        if message.content_type == 'sticker' and message.sticker.emoji:
             text_for_corpus = message.sticker.emoji
    if text_for_corpus:
        async with storage_lock: last_messages.append(text_for_corpus)
        if board_id != 'trash':
            spawn_task(check_and_send_contextual_reply(message.bot, user_id, text_for_corpus, board_id, stream=stream))
    elif message.content_type in ('voice', 'video_note'):
        if board_id != 'trash':
            spawn_task(transcribe_and_roast_voice_note(message.bot, message, board_id, stream=stream))
    if not is_shadow_muted and text_for_corpus:
        if is_spam_filtered(text_for_corpus, board_id, user_id):
            is_shadow_muted = True
    user_settings = b_data.get('user_settings', {}).get(user_id, {})
    if (message.content_type == 'animation' and user_settings.get('shadow_gif')) or \
       (message.content_type == 'sticker' and user_settings.get('shadow_sticker')):
        is_shadow_muted = True
    if user_settings.get('shadow_media') and message.content_type != 'text':
        is_shadow_muted = True
    if is_sage: content['is_sage'] = True

    # --- НАЧАЛО ИЗМЕНЕНИЙ (Логика "Быстрой цитаты") ---
    quote_info_for_post = await build_quick_quote_info(reply_to_post)
    content['quote_info'] = quote_info_for_post
    # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # Баян. Шэдоу-мут не считаем: пост никто не увидит, и счётчик бы врал.
    if _media_unique_id and not is_shadow_muted:
        from common.database import register_media_repost
        _times = await register_media_repost(board_id, _media_unique_id)
        if _times > 1:
            content['repost_count'] = _times

    if is_shadow_muted:
        await process_shadow_reject(shared_state.ShadowRejectContext(
            bot=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            stream=stream
        ))
    else:
        post_num = await process_new_post(shared_state.NewPostParams(
            bot_instance=message.bot,
            board_id=board_id,
            user_id=user_id,
            content=content,
            reply_to_post=reply_to_post,
            is_shadow_muted=False,
            stream=stream
        ))
        if post_num:
            should_reply = False
            def extract_msg_media_file_id(msg):
                if not msg: return None
                if getattr(msg, 'photo', None): return msg.photo[-1].file_id
                if getattr(msg, 'video', None):
                    thumb = getattr(msg.video, 'thumbnail', None) or getattr(msg.video, 'thumb', None)
                    return thumb.file_id if thumb else msg.video.file_id
                if getattr(msg, 'animation', None):
                    thumb = getattr(msg.animation, 'thumbnail', None) or getattr(msg.animation, 'thumb', None)
                    return thumb.file_id if thumb else msg.animation.file_id
                if getattr(msg, 'video_note', None):
                    thumb = getattr(msg.video_note, 'thumbnail', None) or getattr(msg.video_note, 'thumb', None)
                    return thumb.file_id if thumb else msg.video_note.file_id
                if getattr(msg, 'sticker', None): return msg.sticker.file_id
                if getattr(msg, 'document', None):
                    thumb = getattr(msg.document, 'thumbnail', None) or getattr(msg.document, 'thumb', None)
                    return thumb.file_id if thumb else msg.document.file_id
                return None
            photo_id = extract_msg_media_file_id(message) or extract_msg_media_file_id(message.reply_to_message)
            if is_reply_to_bot:
                now_t = time.time()
                last_user_t = last_persona_dialogue_user_ts.get(user_id, 0)
                # Уменьшено в 10 раз: 3.5% шанс на ответ, минимальный кулдаун 300 секунд
                if (now_t - last_user_t >= 300.0) and (random.random() < 0.035):
                    should_reply = True
                    last_persona_dialogue_user_ts[user_id] = now_t
                else:
                    print(f"ℹ️ [Persona Dialogue] Ignored dialogue trigger for user {user_id} (cooldown or chance check).")
            elif user_id in b_data.get('persona_favorites', {}):
                text_clean = message.text or message.caption or (f"[фотография]" if photo_id else None)
                now_t_fav = time.time()
                # Уменьшено в 10 раз: шанс 0.8%, кулдаун 600 секунд
                if (now_t_fav - last_persona_board_ts.get(board_id, 0) >= 600.0) and text_clean and len(text_clean) >= 4 and random.random() < 0.008:
                    should_reply = True
            else:
                # Глобальный пассивный тригер: 0.4%
                text_clean2 = message.text or message.caption or None
                now_t_glob = time.time()
                if (now_t_glob - last_persona_board_ts.get(board_id, 0) >= 900.0) and text_clean2 and len(text_clean2) >= 4 and random.random() < 0.004:
                    should_reply = True
            if should_reply:
                last_persona_board_ts[board_id] = time.time()  # race guard
                text_chunk = message.text or message.caption or f"[{message.content_type}]"
                spawn_task(schedule_persona_reply(message.bot, board_id, post_num, text_chunk, stream, is_admin_trigger=False, photo_file_id=photo_id, is_dialogue=is_reply_to_bot))
            # --- THE ANCHOR (Мудрый Чед) ---
            from anchor_bot import anchor_tick, trigger_anchor_post
            if anchor_tick(board_id):
                spawn_task(trigger_anchor_post(message.bot, board_id, stream))

async def check_spam(user_id: int, msg: Message, board_id: str) -> bool:
    if is_admin(user_id, board_id):
        return True
    content, msg_type = _get_msg_content_and_type(msg)
    
    raw_content_type = msg.content_type
    
    result, level = await analyze_message_for_spam(user_id, board_id, content, msg_type, raw_content_type)
    if result == SpamResult.GLOBAL_BAN_REQUIRED:
        msg_str = f"🚨 [GLOBAL] ЭХОДАУН ОБНАРУЖЕН: user {user_id}. Выдан перманентный SHADOWMUTE везде кроме /b/."
        print(msg_str)
        from common.database import update_shadow_mute, log_global_event
        spawn_task(log_global_event('bot', msg_str))
        expires_dt = datetime.now(UTC) + timedelta(days=365)
        for b in BOARD_CONFIG.keys():
            if b != 'b':
                board_data[b].setdefault('shadow_mutes', {})[user_id] = expires_dt
                spawn_task(update_shadow_mute(user_id, b, expires_dt.timestamp()))
        return False
    elif result == SpamResult.BAN_REQUIRED:
        return False

    rules = SPAM_RULES.get(msg_type)
    if not rules:
        return True

    from common.spam_filter import _spam_violations
    now = datetime.now(UTC)
    violations = _spam_violations[board_id].setdefault(user_id, {'level': 0, 'last_reset': now})

    b_data = board_data[board_id]
    if not _check_repeats(user_id, b_data, (content, msg_type), rules, violations):
        return False

    return True

async def apply_penalty(bot_instance: Bot, user_id: int, msg_type: str, board_id: str, stream: str='ru'):
    async with acquire_spam_lock(user_id):
        b_data = board_data[board_id]
        level = get_spam_violation_level(board_id, user_id)
        if level <= 0:
            return
            
        current_smute = b_data.get('shadow_mutes', {}).get(user_id)
        if current_smute and current_smute > datetime.now(UTC):
            return
            
        base_mute_minutes = 5
        multiplier = 2 ** max(0, level - 1)
        mute_seconds = base_mute_minutes * 60 * multiplier
        expires_dt = datetime.now(UTC) + timedelta(seconds=mute_seconds)
        
        b_data.setdefault('shadow_mutes', {})[user_id] = expires_dt
        from common.database import update_shadow_mute, log_global_event
        await update_shadow_mute(user_id, board_id, expires_dt.timestamp())
        
        violation_type = {'text': 'текстовый спам', 'sticker': 'спам стикерами', 'animation': 'спам гифками', 'audio': 'спам аудио'}.get(msg_type, 'спам')
        mute_duration = f"{mute_seconds // 60} мин"
        log_msg = f"👻 [{board_id}] ТИХИЙ SHADOW Мут за спам: user {user_id}, тип: {violation_type}, уровень: {level}, длительность: {mute_duration}"
        print(log_msg)
        spawn_task(log_global_event('bot', log_msg))

async def process_shadow_reject(ctx: shared_state.ShadowRejectContext):

    """
    Эмулирует успешную публикацию поста, но отправляет его ТОЛЬКО автору.
    Не пишет в БД, не увеличивает счетчики.
    """
    shadow_key = (ctx.board_id, ctx.user_id)
    current_floor = state['post_counter'] + random.randint(1, 3)
    last_fake_post_num = shadow_fake_post_counters.get(shadow_key, 0)
    fake_post_num = max(current_floor, last_fake_post_num + random.randint(1, 3))
    shadow_fake_post_counters[shadow_key] = fake_post_num
    header_text = await format_header(ctx.board_id, fake_post_num, ctx.user_id, stream=ctx.stream)
    user_content = ctx.content.copy()
    user_content['header'] = header_text
    user_content['post_num'] = fake_post_num
    user_content['is_shadow_reject'] = True
    user_content['reply_to_post'] = ctx.reply_to_post
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await send_message_to_users(shared_state.BroadcastConfig(
        bot_instance=ctx.bot,
        board_id=ctx.board_id,
        recipients={ctx.user_id}, # Только автор!
        content=user_content,
        reply_info=None
    ))
    print(f"👻 [SHADOW] Теневой отброс медиа от {ctx.user_id} на доске {ctx.board_id}")

async def build_quick_quote_info(reply_to_post: int | None) -> dict | None:
    if not reply_to_post:
        return None
    current_max_post = await get_max_post_num()
    if current_max_post - reply_to_post <= QUICK_QUOTE_POST_DISTANCE:
        return None
    replied_post_data = await get_post_by_num(reply_to_post)
    if not replied_post_data:
        return None
    return _quote_info_from_content(replied_post_data.get('content'))

async def ensure_user_in_valid_thread(bot: Bot, board_id: str, user_id: int) -> bool:
    """
    Проверяет, находится ли пользователь в существующем треде.
    Если тред не существует (удалён), переводит пользователя на main и отправляет уведомление.
    Возвращает True, если перевод был выполнен (user был в невалидном треде).
    """
    b_data = board_data[board_id]
    user_s = b_data['user_state'].setdefault(user_id, {})
    location = user_s.get('location', 'main')
    if location != 'main':
        thread_info = get_thread_info(board_id, location)
        if not thread_info:
            user_s['location'] = 'main'
            notify_text = ("Тред, в котором вы находились, был удалён. Вы возвращены на главную доску."
                           if board_id != 'int' else
                           "Thread you were in has been deleted. You have been returned to the main board.")
            try:
                await bot.send_message(user_id, notify_text)
            except TelegramForbiddenError:
                try:
                    import __main__ as main
                    if hasattr(main, 'purge_users_from_board_ram'):
                        await main.purge_users_from_board_ram(board_id, [user_id])
                except Exception:
                    pass
            except TelegramBadRequest as e:
                logger.warning("TelegramBadRequest in ensure_user_in_valid_thread for user %s: %s", user_id, e)
            except TelegramRetryAfter as e:
                await asyncio.sleep(float(getattr(e, "retry_after", 5) or 5) + 1.0)
            except Exception as e:
                logger.exception("Failed to notify user %s of thread deletion: %s", user_id, e)
            return True
    return False

def _parse_and_split_multi_replies(text: str) -> tuple[list[tuple[int, str]], bool]:
    """
    Парсит текст на предмет мультиответов (>>post_num) и разбивает его на блоки.
    - Игнорирует случаи, когда в тексте меньше двух ссылок >>post_num.
    - Ограничивает количество ответов до 3. 4-й и последующие блоки
      присоединяются к тексту 3-го блока.
    :param text: Исходный текст сообщения.
    :return: Кортеж, где:
             - Первый элемент: список кортежей (post_num, text_chunk).
               Пустой список, если это не мультиответ.
             - Второй элемент: bool флаг, True если сработал лимит в 3 ответа.
    """
    if not text:
        return [], False
    matches = list(itertools.islice(RE_MULTI_REPLY_LOCAL.finditer(text), 4))
    limit_hit = False
    if len(matches) < 2:
        return [], False
    blocks = []
    for i, current_match in enumerate(matches):
        try:
            post_num = int(current_match.group(1))
        except (ValueError, IndexError):
            continue # Пропускаем некорректный паттерн
        text_start = current_match.end()
        is_last_match = (i == len(matches) - 1)
        text_end = len(text) if is_last_match else matches[i + 1].start()
        text_chunk = text[text_start:text_end].strip()
        blocks.append((post_num, text_chunk))
    if len(blocks) > 3:
        limit_hit = True
        third_block_content_start_pos = matches[2].end()
        merged_text_content = text[third_block_content_start_pos:].strip()
        merged_third_block = (blocks[2][0], merged_text_content)
        blocks = blocks[:2] + [merged_third_block]
    return blocks, limit_hit

async def _send_notification_quietly(bot: Bot, chat_id: int, text: str) -> None:
    """
    Необязательное уведомление «в никуда»: юзер мог заблокировать бота.

    Нужна отдельной корутиной, чтобы такую отправку можно было запускать через
    spawn_task из-под db_lock, не удерживая его на время сетевого вызова.
    """
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML", disable_notification=True)
    except TelegramForbiddenError:
        pass
    except TelegramBadRequest as e:
        logger.warning("TelegramBadRequest in _send_notification_quietly for %s: %s", chat_id, e)
    except TelegramRetryAfter as e:
        await asyncio.sleep(float(getattr(e, "retry_after", 5) or 5) + 1.0)
    except Exception as e:
        logger.exception("_send_notification_quietly failed for %s: %s", chat_id, e)

@message_router.message(F.media_group_id)
async def handle_media_group_init(message: Message, board_id: str | None, stream: str = 'ru'):
    """
    (ИСПРАВЛЕННАЯ ВЕРСИЯ)
    Собирает сообщения медиагруппы и НЕМЕДЛЕННО удаляет оригинал для консистентного UX.
    """
    media_group_id = message.media_group_id
    user_id = message.from_user.id
    if not board_id or not media_group_id:
        return
    media_group_key = _media_group_state_key(message.chat.id, media_group_id)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass  # Race condition: another message in the media group already deleted it
        
    if media_group_key in sent_media_groups:
        return
    b_data = board_data[board_id]
    if user_id in b_data['users']['banned'] or \
       (b_data['mutes'].get(user_id) and b_data['mutes'][user_id] > datetime.now(UTC)):
        return
    b_data['last_activity'][user_id] = datetime.now(UTC)
    
    is_leader = False
    async with media_group_creation_lock:
        if media_group_key not in current_media_groups:
            is_leader = True
            current_media_groups[media_group_key] = {
                'is_initializing': True,
                'init_event': asyncio.Event(),
                'media_group_id': media_group_id,
                'media_group_key': media_group_key,
                'chat_id': message.chat.id,
            }
            
    group = current_media_groups.get(media_group_key)
    if not group:
        return
        
    if is_leader:
        try:
            fake_text_message = types.Message(
                message_id=message.message_id, date=message.date, chat=message.chat,
                from_user=message.from_user, content_type='text', text=f"media_group_{media_group_id}"
            )
            if not await check_spam(user_id, fake_text_message, board_id):
                current_media_groups.pop(media_group_key, None)
                await apply_penalty(message.bot, user_id, 'text', board_id)
                if 'init_event' in group:
                    group['init_event'].set()
                return
            reply_to_post = None
            if message.reply_to_message:
                async with storage_lock:
                    lookup_key = (message.chat.id, message.reply_to_message.message_id)
                    reply_to_post = message_to_post.get(lookup_key)
                if not reply_to_post:
                    info = await get_post_info_by_copy(message.chat.id, message.reply_to_message.message_id)
                    if info:
                        reply_to_post = info[0]
            raw_caption_html = getattr(message, 'caption_html_text', message.caption or "")
            safe_caption_html = sanitize_html(raw_caption_html)
            group.update({
                'board_id': board_id, 'author_id': user_id, 'stream': stream,
                'timestamp': datetime.now(UTC), 'raw_messages':[], 'caption': safe_caption_html,
                'reply_to_post': reply_to_post, 'processed_messages': set(),
                'source_message_ids': set()
            })
            group.pop('is_initializing', None)
        finally:
            if 'init_event' in group:
                group['init_event'].set()
    else:
        if 'init_event' in group:
            try:
                await asyncio.wait_for(group['init_event'].wait(), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"⚠️ Таймаут ожидания инициализации для media_group {media_group_key}")
                return
        group = current_media_groups.get(media_group_key)
        if not group or group.get('is_initializing'):
            return
            
    group.get('source_message_ids', set()).add(message.message_id)
    if message.message_id not in group.get('processed_messages', set()):
        group.get('raw_messages',[]).append(message)
        group.get('processed_messages', set()).add(message.message_id)
        
    if media_group_key in media_group_timers:
        media_group_timers[media_group_key].cancel()
    media_group_timers[media_group_key] = spawn_task(
        complete_media_group_after_delay(media_group_key, message.bot, delay=1.5)
    )