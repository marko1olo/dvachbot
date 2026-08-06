from shared_state import *
from shared_state import _persona_processed_posts
from aiogram import types
from aiogram.types import Message

import os
import time
import random
import logging
from datetime import datetime, timezone
UTC = timezone.utc
from aiogram import Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from common.html_utils import escape_html
from common.text_utils import clean_html_for_tg

import json
from datetime import timedelta
from common.database import get_post_by_num, get_pool, delete_post_by_num
from common.text_utils import clean_html_tags
from bot_helpers import delete_message_after_delay, check_cooldown, _activate_mode, disable_mode_after_delay
from common.task_manager import spawn_task
from post_helpers import create_post, _format_post_text, _get_author_name, _get_reply_suffix, update_post_content, format_header
from delivery_manager import enqueue_board_message

import re
import asyncio
from summarize import summarize_text_with_hf, create_telegraph_page_async
from post_processor import NewPostProcessor, NewPostContext
from text_assets import CONTEXTUAL_REPLIES, CONTEXTUAL_REPLIES_EN, CONTEXTUAL_REPLIES_JP
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from collections import defaultdict

logger = logging.getLogger(__name__)
router = Router()

CONTEXTUAL_REPLIES_ENABLED = True
CONTEXTUAL_REPLY_COOLDOWN_SEC = 300.0
CONTEXTUAL_REPLY_DAILY_LIMIT = 5
contextual_reply_tracker = defaultdict(lambda: {"last": 0.0, "window_start": 0.0, "count": 0})
contextual_reply_stats = defaultdict(int)

def _contextual_reply_allowed(user_id: int, board_id: str) -> tuple[bool, str | None]:
    if not CONTEXTUAL_REPLIES_ENABLED:
        contextual_reply_stats["skipped_disabled"] += 1
        return False, "disabled"

    now = time.time()
    key = (board_id, user_id)
    item = contextual_reply_tracker[key]

    if CONTEXTUAL_REPLY_DAILY_LIMIT:
        window_start = float(item.get("window_start") or 0.0)
        if now - window_start >= 86400:
            item["window_start"] = now
            item["count"] = 0
        elif int(item.get("count") or 0) >= CONTEXTUAL_REPLY_DAILY_LIMIT:
            contextual_reply_stats["skipped_daily_limit"] += 1
            return False, "daily_limit"

    last_sent = float(item.get("last") or 0.0)
    if CONTEXTUAL_REPLY_COOLDOWN_SEC and now - last_sent < CONTEXTUAL_REPLY_COOLDOWN_SEC:
        contextual_reply_stats["skipped_cooldown"] += 1
        return False, "cooldown"

    item["last"] = now
    if not item.get("window_start"):
        item["window_start"] = now
    item["count"] = int(item.get("count") or 0) + 1
    contextual_reply_stats["sent"] += 1
    return True, None

async def check_and_send_contextual_reply(bot, user_id: int, text: str, board_id: str, stream: str = 'ru'):
    """
    Проверяет текст на наличие паттернов и отправляет автору личное сообщение.
    Выбирает язык ответов на основе stream.
    """
    if not text or not isinstance(text, str):
        return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    if lang == 'en':
        replies_dict = CONTEXTUAL_REPLIES_EN
    elif lang == 'jp':
        replies_dict = CONTEXTUAL_REPLIES_JP
    else:
        replies_dict = CONTEXTUAL_REPLIES
    try:
        for pattern, replies in replies_dict.items():
            is_match = False
            if isinstance(pattern, str):
                if re.search(pattern, text, re.IGNORECASE):
                    is_match = True
            elif hasattr(pattern, 'search'):
                if pattern.search(text):
                    is_match = True
            if is_match:
                allowed, reason = _contextual_reply_allowed(user_id, board_id)
                if not allowed:
                    if reason:
                        runtime_logger.info(
                            "contextual_reply_skip %s",
                            json.dumps(
                                {
                                    "ts": round(time.time(), 3),
                                    "board_id": board_id,
                                    "user_id": user_id,
                                    "reason": reason,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                    return
                response_text = random.choice(replies)
                try:
                    await bot.send_message(user_id, response_text, parse_mode="HTML")
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    contextual_reply_stats["send_errors"] += 1
                    print(f"ℹ️ Не удалось отправить контекстный ответ user {user_id}: {e}")
                return
    except Exception as e:
        print(f"⛔ Ошибка в check_and_send_contextual_reply для user {user_id}: {e}")

def _summarize_delivery_metrics() -> dict:

    summary = {}
    for board_id in BOARDS:
        records = list(delivery_metrics.get(board_id, []))
        if not records:
            continue
        recent = records[-20:]
        seconds = [item.get("seconds", 0.0) for item in recent]
        ages = [
            item.get("post_age_sec")
            for item in recent
            if item.get("post_age_sec") is not None
        ]
        summary[board_id] = {
            "count": len(records),
            "avg_sec": round(sum(seconds) / len(seconds), 2) if seconds else 0.0,
            "max_sec": round(max(seconds), 2) if seconds else 0.0,
            "avg_age_sec": round(sum(ages) / len(ages), 2) if ages else None,
            "max_age_sec": round(max(ages), 2) if ages else None,
            "last": records[-1],
        }
    return summary

def _summarize_mode_punchup_stats() -> dict:

    modes = {}
    totals = {
        "calls": 0,
        "skipped_load": 0,
        "skipped_disabled": 0,
        "total_us": 0.0,
        "max_us": 0.0,
        "slow": 0,
    }
    for mode_key, raw in mode_punchup_stats.items():
        calls = int(raw.get("calls", 0))
        total_us = float(raw.get("total_us", 0.0))
        max_us = float(raw.get("max_us", 0.0))
        skipped_load = int(raw.get("skipped_load", 0))
        skipped_disabled = int(raw.get("skipped_disabled", 0))
        slow = int(raw.get("slow", 0))
        modes[mode_key] = {
            "calls": calls,
            "avg_us": round(total_us / calls, 2) if calls else 0.0,
            "max_us": round(max_us, 2),
            "skipped_load": skipped_load,
            "skipped_disabled": skipped_disabled,
            "slow": slow,
        }
        totals["calls"] += calls
        totals["skipped_load"] += skipped_load
        totals["skipped_disabled"] += skipped_disabled
        totals["total_us"] += total_us
        totals["max_us"] = max(totals["max_us"], max_us)
        totals["slow"] += slow
    top = sorted(modes.items(), key=lambda item: item[1]["max_us"], reverse=True)[:5]
    return {
        "calls": totals["calls"],
        "avg_us": round(totals["total_us"] / totals["calls"], 2) if totals["calls"] else 0.0,
        "max_us": round(totals["max_us"], 2),
        "skipped_load": totals["skipped_load"],
        "skipped_disabled": totals["skipped_disabled"],
        "slow": totals["slow"],
        "top": top,
        "by_mode": modes,
    }

def _summarize_live_queue_ages(queue_sizes: dict) -> dict:

    now = time.time()
    by_board = {}
    oldest = []
    for board_id, queue in message_queues.items():
        ages, oldest_age, oldest_post = _process_board_queue(queue, now)
        if queue_sizes.get(board_id, 0) or ages:
            info = {"size": queue_sizes.get(board_id, 0)}
            if ages:
                info.update({
                    "oldest_age_sec": round(max(ages), 1),
                    "avg_age_sec": round(sum(ages) / len(ages), 1),
                    "oldest_post": oldest_post,
                })
                oldest.append((board_id, info["oldest_age_sec"], oldest_post))
            by_board[board_id] = info

    in_flight = _process_in_flight_deliveries(now)

    return {
        "by_board": by_board,
        "oldest": sorted(oldest, key=lambda item: item[1], reverse=True)[:5],
        "in_flight": in_flight,
    }

async def build_reply_chain_context(target_post_num: int, max_depth: int = 25) -> str:
    """
    Строит цепочку ответов от предков к целевому посту (до 25 уровней вглубь).
    Возвращает отформатированный хронологический контекст для LLM.
    """
    if not target_post_num:
        return ""
        
    chain = []
    current_num = target_post_num
    visited = set()
    
    while current_num and current_num not in visited and len(chain) < max_depth:
        visited.add(current_num)
        post_data = None
        async with storage_lock:
            post_data = messages_storage.get(current_num)
        if not post_data:
            post_data = await get_post_by_num(current_num)
            
        if not post_data:
            break
            
        content = post_data.get('content', {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                content = {'text': content}
                
        raw_text = content.get('text') or content.get('caption') or ""
        clean_text = clean_html_tags(raw_text).replace('\n', ' ').strip()
        if not clean_text and content.get('type'):
            clean_text = f"[{content.get('type')}]"
            
        author_id = post_data.get('author_id', -1)
        is_bot = (author_id == 0 or author_id == 1488148800)
        
        reply_to = post_data.get('reply_to_post_num') or post_data.get('reply_to') or content.get('reply_to_post')
        
        chain.append({
            'post_num': current_num,
            'is_bot': is_bot,
            'author_id': author_id,
            'text': clean_text,
            'reply_to': reply_to
        })
        
        current_num = reply_to

    if not chain:
        return ""

    chain.reverse()
    
    lines = []
    for item in chain:
        if item['is_bot']:
            sender = "ТЫ (Персона)"
        else:
            anon_hash = str(abs(hash(str(item.get('author_id', 'anon')))))[:4]
            sender = f"Анон #{anon_hash}"
        reply_prefix = f" (в ответ на #{item['reply_to']})" if item['reply_to'] else ""
        lines.append(f"• #{item['post_num']} [{sender}]{reply_prefix}: {item['text'][:300]}")
        
    return "\n".join(lines)

async def schedule_persona_reply(bot, board_id: str, target_post_num: int, context_text: str, stream: str, is_admin_trigger: bool = False, photo_file_id: str = None, is_dialogue: bool = False):
    try:
        from site_tgach.persona_bot import generate_anon_reply, is_valid_for_persona

        if target_post_num and target_post_num in _persona_processed_posts:
            print(f"ℹ️ [Persona Debounce] Reply for post #{target_post_num} already processed, skipping duplicate trigger.")
            return
        if target_post_num:
            _persona_processed_posts.add(target_post_num)
            if len(_persona_processed_posts) > 3000:
                _persona_processed_posts.clear()

        now_ts = time.time()

        if not photo_file_id and target_post_num and target_post_num in messages_storage:
            p_data = messages_storage[target_post_num]
            c = p_data.get('content', {})
            m_type = c.get('type')
            if m_type in {'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document'}:
                photo_file_id = c.get('thumbnail_file_id') or c.get('file_id')
            elif m_type == 'media_group' and c.get('media'):
                for m in c.get('media', []):
                    if m.get('file_id'):
                        photo_file_id = m.get('thumbnail_file_id') or m.get('file_id')
                        break
            # Если в самом посте нет картинки, проверим родительский пост, на который отвечают
            if not photo_file_id:
                reply_to_num = p_data.get('reply_to_post_num') or p_data.get('reply_to')
                if reply_to_num and reply_to_num in messages_storage:
                    parent_c = messages_storage[reply_to_num].get('content', {})
                    pm_type = parent_c.get('type')
                    if pm_type in {'photo', 'video', 'animation', 'gif', 'video_note', 'sticker', 'document'}:
                        photo_file_id = parent_c.get('thumbnail_file_id') or parent_c.get('file_id')
                    elif pm_type == 'media_group' and parent_c.get('media'):
                        for m in parent_c.get('media', []):
                            if m.get('file_id'):
                                photo_file_id = m.get('thumbnail_file_id') or m.get('file_id')
                                break

        vision_desc = None
        if photo_file_id and not (context_text and "[ИЗОБРАЖЕНИЕ:" in context_text):
            vision_desc = await analyze_telegram_photo(bot, photo_file_id, caption=context_text)
            if vision_desc:
                img_tag = f"\n[ИЗОБРАЖЕНИЕ: {vision_desc}]"
                context_text = (context_text or "") + img_tag

        if not is_admin_trigger and not is_valid_for_persona(context_text):
            return
            
        await asyncio.sleep(random.uniform(12.0, 35.0) if not is_admin_trigger else 0)
        
        print(f"🤖 [Persona] Requesting reply generation for post {target_post_num} on {board_id} (is_dialogue={is_dialogue})...")
        
        # Строим общую атмосферу доски (25 последних постов)
        atmosphere_context = await build_board_atmosphere_context(board_id, exclude_post_num=target_post_num, limit=25)
        
        # Строим контекст всей цепочки ответов (до 25 уровней)
        chain_context = await build_reply_chain_context(target_post_num, max_depth=25)
        if not chain_context:
            chain_context = context_text
        elif photo_file_id and vision_desc and "[ИЗОБРАЖЕНИЕ:" not in chain_context:
            chain_context += f"\n[ИЗОБРАЖЕНИЕ: {vision_desc}]"

        replies = await generate_anon_reply(
            context_text=chain_context,
            target_post=context_text,
            is_dialogue=is_dialogue,
            atmosphere_text=atmosphere_context
        )
        
        # Гарантия от "замалчивания": если юзер вел диалог с ботом, но генератор сбросился — даем аноновский фаллбэк-ответ
        if not replies and is_dialogue:
            print(f"⚠️ [Persona] Dialogue fallback for post {target_post_num} (preventing silence).")
            fallback_options = [
                "Понял тебя, анон.",
                "Ладно, проехали.",
                "Хз даже чё сказать на это, анон.",
                "Ну допустим.",
                "Ладно, забей.",
                "Останемся при своих, анон."
            ]
            replies = [random.choice(fallback_options)]

        if not replies:
            print(f"⚠️ [Persona] Generation failed or returned empty for post {target_post_num}.")
            return
            
        print(f"✅ [Persona] Successfully generated {len(replies)} replies for post {target_post_num}.")
            
        for i, text in enumerate(replies):
            now_dt = datetime.now(UTC)
            # Прикрепляем картинку только в 30% случаев чтобы не спамить медиа
            attach_photo = photo_file_id and i == 0 and random.random() < 0.30
            content = {
                'type': 'photo' if attach_photo else 'text',
                'is_system_message': True,
                'archive_allowed': True
            }
            if content['type'] == 'photo':
                content['caption'] = text
                content['file_id'] = photo_file_id
            else:
                content['text'] = text
                
            pnum = await create_post(
                board_id=board_id,
                author_id=0,
                content=content,
                timestamp=now_dt.timestamp(),
                is_from_site=False, stream=stream,
                reply_to=target_post_num if target_post_num else None
            )
            if pnum:
                header = await format_header(board_id, pnum, 0)
                content['header'] = f"### АНОН ###\n{header}" if stream == 'ru' else f"### ANON ###\n{header}"
                await update_post_content(pnum, content)
                async with storage_lock:
                    messages_storage[pnum] = {
                        'author_id': 0, 'timestamp': now_dt, 
                        'content': content, 'board_id': board_id,
                        'reply_to_post_num': target_post_num if target_post_num else None
                    }
                await NewPostProcessor(NewPostContext(
                    bot_instance=bot,
                    board_id=board_id,
                    user_id=0,
                    content=content,
                    reply_to_post=target_post_num if target_post_num else None,
                    is_shadow_muted=False,
                    stream=stream
                )).execute()
            if len(replies) > 1:
                await asyncio.sleep(random.uniform(1.0, 3.0))
    except Exception as e:
        print(f"Error in schedule_persona_reply: {e}")

@router.message(Command("roast", "prozharka", "прожарка"))
async def cmd_roast(message: types.Message, board_id: str | None, stream: str = 'ru'):
    """
    🔥 Прожарка борды нейросетью.

    Функция была написана полностью — кулдаун, сбор последних 40 постов за
    2 часа, трёхъязычные промпты, прогресс-сообщение, обработка ошибок — но
    у неё отсутствовал декоратор, поэтому команда не регистрировалась и была
    недостижима. При этом /help её пользователям обещал.
    """
    if not board_id:
        return

    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    b_data = board_data.get(board_id)
    if not b_data:
        return
        
    now_ts = time.time()
    last_usage = b_data.get('last_roast_time', 0)
    if now_ts - last_usage < ROAST_COOLDOWN:
        rem_m = int((ROAST_COOLDOWN - (now_ts - last_usage)) // 60)
        rem_s = int((ROAST_COOLDOWN - (now_ts - last_usage)) % 60)
        await message.reply(f"⏳ Команда остывает: {rem_m}м {rem_s}с" if lang == 'ru' else f"⏳ Cooldown: {rem_m}m {rem_s}s")
        return

    b_data['last_roast_time'] = now_ts
    
    msgs = []
    cutoff = time.time() - (3600 * 2)
    async with storage_lock:
        for p_info in reversed(messages_storage.values()):
            if len(msgs) >= 40: break
            if p_info.get('board_id') == board_id:
                ts = p_info.get('timestamp', 0)
                if hasattr(ts, 'timestamp'):
                    ts = ts.timestamp()
                if ts > cutoff:
                    if not p_info.get('thread_id'):
                        msgs.append(p_info)
                    
    msgs.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
    
    if len(msgs) < 5:
        await message.reply("💤 Мало постов для прожарки" if lang == 'ru' else "💤 Not enough posts")
        return
        
    chunk_parts = []
    for p in msgs:
        text = p.get('content', {}).get('text', '') if isinstance(p.get('content'), dict) else ''
        if text:
            chunk_parts.append(f"[Anon]: {text}")
            
    chunk = " | ".join(chunk_parts)
    
    if lang == 'en':
        prompt = random.choice(ROAST_PROMPTS_EN)
    elif lang == 'jp':
        prompt = random.choice(ROAST_PROMPTS_JP)
    else:
        prompt = random.choice(ROAST_PROMPTS)
        
    hf_token = os.getenv("HF_TOKEN")
    
    processing_msg = await message.reply("🔥 Готовим прожарку..." if lang == 'ru' else "🔥 Roasting...")
    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[roast] Error: {e}")
        await processing_msg.edit_text("❌ Ошибка генерации" if lang == 'ru' else "❌ Error")
        return
        
    if not summary:
        await processing_msg.edit_text("❌ Ошибка генерации" if lang == 'ru' else "❌ Error")
        return
        
    roast_text = f"🔥 <b>ПРОЖАРКА ЧАТА</b> 🔥\n\n{summary}" if lang == 'ru' else f"🔥 <b>CHAT ROAST</b> 🔥\n\n{summary}"
    if lang == 'jp': roast_text = f"🔥 <b>煽り</b> 🔥\n\n{summary}"
    
    await processing_msg.edit_text(roast_text, parse_mode='HTML')

async def _get_summarize_prompt_and_chunk(board_id: str, thread_id: str | None, thread_info: dict, lang: str, paragraph_count: int, is_blat: bool | None = None, is_warhammer: bool | None = None) -> tuple[str, str, str, bool, bool]:
    b_data = board_data.get(board_id, {})
    if is_warhammer is None and is_blat is None:
        if b_data.get('warhammer_mode'):
            is_warhammer = True
            is_blat = False
        elif b_data.get('gopnik_mode'):
            is_blat = True
            is_warhammer = False
        else:
            # Random prompt selection in normal mode:
            # 15% Warhammer Summary, 40% Blat Summary, 45% Classic Summary
            roll = random.random()
            if roll < 0.15:
                is_warhammer = True
                is_blat = False
            elif roll < 0.55:
                is_blat = True
                is_warhammer = False
            else:
                is_blat = False
                is_warhammer = False
    elif is_warhammer:
        is_blat = False

    if is_warhammer:
        from warhammer_mode import WH40K_REPLACEMENTS

        # Dynamic Slang Dictionary sampling from warhammer_mode.py
        all_keys = [k for k, v in WH40K_REPLACEMENTS.items() if isinstance(v, list) and len(v) > 0 and len(k) > 2]
        sampled_slang_keys = random.sample(all_keys, min(30, len(all_keys)))
        slang_lines = []
        for k in sampled_slang_keys:
            val = WH40K_REPLACEMENTS[k][0]
            slang_lines.append(f"  • '{k}' -> '{val}'")
        slang_dictionary_str = "\n".join(slang_lines)

        # 30+ Official Thoughts of the Day
        all_waha_thoughts = [
            "Знание — сила, скрой его от профанов.",
            "Нет невиновных, есть лишь разные степени вины.",
            "Надежда — первый шаг на пути к разочарованию.",
            "Открытый разум подобен крепости, чьи врата распахнуты, а стража погрязла в безделье.",
            "Служи Императору сегодня, ибо завтра ты будешь мертв.",
            "Оправдания — удел слабых.",
            "Жизнь — это тюрьма, смерть — освобождение.",
            "Чистый разум — пустой разум.",
            "Прощение есть преступление перед Террой.",
            "Даже человек, у которого нет ничего, может отдать свою жизнь за Терру.",
            "Мир — это ложь. Есть только вечная война.",
            "Труд — это молитва Омниссии.",
            "Никогда не прощай. Никогда не забывай.",
            "Страх — это провал в логике и деградация когитатора.",
            "Лучше умереть за Императора, чем жить ради себя.",
            "Лживый язык вредоноснее ксеносского клинка.",
            "Сомнение — это семя ереси в разуме.",
            "Безжалостность — это милосердие мудрых.",
            "Тот, кто сомневается в приказе, уже совершил измену.",
            "Верен тот, кто повинуется без расспросов.",
            "Кровь мучеников — семя Империума.",
            "Неведение — твоя лучшая защита от искушений варпа.",
            "Будь бдителен, ибо ересь кроется в деталях.",
            "Плоть слаба, только дух и сталь вечны.",
            "Каждый шаг без веры — шаг во тьму.",
            "Истинный воин не ищет славы, он ищет исполнения долга.",
            "Жалость к еретику — это предательство человечества.",
            "Не спрашивай, почему ты должен умереть, спрашивай, как тебе умереть за Терру.",
            "Смерть в бою — высочайшая награда для верного.",
            "Пусть ксенос плачет, а еретик сгорает в очищающем огне!"
        ]
        selected_waha_thoughts = "\n".join(f"  • [МЫСЛЬ ДНЯ]: {t}" for t in random.sample(all_waha_thoughts, min(15, len(all_waha_thoughts))))

        prompt = f"""
Ты — Священный Великий Лорд-Инквизитор Ордо Маллеус и Ордо Еретикус, полномочный каратель Священной Терры. Твоя миссия — изучить лог астропатической связи сектора /{board_id}/, выявить ересь, измену, деградацию и составить Беспощадный Официальный Акт Инквизиционного Дознания.
Твой девиз: "Император защищает. Ересь очищается только огнем. Прощение есть преступление перед Террой!".
Обращайся к подданным: "Слуги Императора!", "Граждане Улья!", "Гвардейцы", "Братья по оружию", "Адепты", "Органика".

=== СТРОГАЯ ПРИВЯЗКА К ФАКТАМ И РЕАЛЬНОМУ ЛОГУ ЧАТА (КРИТИЧНО И БЕЗ ИСКЛЮЧЕНИЙ) ===
- Ты ОБЯЗАН опираться ИСКЛЮЧИТЕЛЬНО на реальные посты, феню, вопросы, холивары и фразы из предоставленного лога сообщений!
- СТРОГО ЗАПРЕЩЕНО выдумывать несуществующие события, фантазировать темы, которых не было в чате, или приписывать юзерам то, чего они не писали.
- Каждый вердикт, статус, похвала или обвинение Инквизиции должны ссылаться на конкретные реальные слова и темы участников из лога!

=== СВЯЩЕННЫЕ ЗАКОНЫ ИНКВИЗИЦИОННОГО ДОЗНАНИЯ ===

1. ВЕРНОСТЬ И ЕРЕСЬ (КРИТИЧЕСКИЙ РАЗДЕЛ):
   Ты ОБЯЗАН строго разделить всех реальных участников лога на две категории:
   - "Верные Сыны и Дочери Империума" (Святые мужики): те, кто нес мудрость, помогал гражданам, славил Императора, кидал годные пасты/схемы и держит оборону сектора.
   - "Еретики, Ксеносы и Поклонники Губительных Сил" (Скверна): те, кто устраивал срачи (Хаос), нес бред, слушал шепоты Тзинча, проявлял гедонизм Слаанеш, распространял гниль Нургла или ныл как эльдарский ксенос.

2. ЖЕСТОЧАЙШИЕ ПРИГОВОРЫ И КЛИКУХИ (ПЕРСОНАЛИЗАЦИЯ ИМЕН):
   Выделяй конкретные ИМЕНА из лога. Назначай им суровые статусы, ксено-диагнозы и карательные приговоры Инквизиции на основе ИХ РЕАЛЬНЫХ ПОСТОВ.
   ПРИМЕР: "За гражданина Витьку (Класс Угрозы: Еретик-Мутант 3-й степени): Вскрыты его высеры в чате про... Приговор: Публичное сожжение святым прометием и переработка остатков в сервитора-полотера."
   ПРИМЕР: "За сержанта Саню (Статус: Герой Имперской Гвардии): Проявил несокрушимый дух Астартес, подогнал в общак сектора ценную инфу про... Награждается святой Аквилой."

3. ОГРОМНЫЙ СЛОВАРЬ ПЕРЕВОДА ЧАТЕРСКОГО И БОРДОВОГО СЛЕНГА НА ГИМН ИМПЕРИУМА:
Активно используй следующие соответствия при анализе лога:
{slang_dictionary_str}

4. СУРОВЫЙ ГРИМДАРК-СЛОВАРЬ:
   Инквизитор, Адептус Арбитрес, Аквила, Священная Терра, Прометий, Астартес, Сервитор, Варп-Шторм, Священный СШК, Трупокрахмал, Псайкер-еретик, Оскверненный Дух Машины, Освященное масло, Корабельный Астропат, Экстерминатус, Ордо Маллеус, Кадия Стоит, Молот Императора.

5. БЕСПОЩАДНЫЙ ЯЗЫК И АНТИ-ЦЕНЗУРА:
   Черный суровый пафос, военная жестокость, инквизиторская непреклонность. Мат ДОПУСКАЕТСЯ как военная брань политрука/комиссара. Никакой жалости к еретикам.

6. ОФИЦИАЛЬНЫЕ МЫСЛИ ДНЯ ИНКВИЗИЦИИ:
Обязательно гармонично вплети в текст минимум 2-3 Мысли Дня из этого святого списка:
{selected_waha_thoughts}

=== СТРУКТУРА СВЯЩЕННОГО ДОСЬЕ ===
1. ВСТУПЛЕНИЕ: Пафосный астропатический заголовок. Оценка суммарного уровня Ереси и Варп-нестабильности в секторе /{board_id}/ за сегодня.
2. ДОСЬЕ ПОДОЗРЕВАЕМЫХ И ГЕРОЕВ: Пройдись по 3-5 активным участникам лога. Напиши "За [Имя] (Титул/Статус): ..." с жестким приговором Инквизитора по ИХ РЕАЛЬНЫМ ПОСТАМ.
3. ВЕРДИКТ ОБ ЭКСТЕРМИНАТУСЕ: Итоговое решение — подлежит ли сектор сожжению или гвардия удержит рубежи. Прощание ("Слава Императору! Кадия стоит!").

ВАЖНО: Твой отчет должен состоять ровно из {paragraph_count} абзацев. Каждый абзац должен быть МАКСИМАЛЬНО ОБЪЕМНЫМ, глубоким и подробным, состоять минимум из 7-10 развернутых предложений с полным анализом реальных событий и цитат из лога, и быть отделен от других пустой строкой. Не используй Markdown-разметку (только HTML, например <b>, <i>, <u>, <s>, <code>, <pre>). Output ONLY plain text or basic HTML.
"""
        info_text = f"За последние 6 часов на доске /{board_id}/" if not thread_id else "За последние 6 часов в треде"
        chunk = await get_board_chunk(board_id, hours=6, thread_id=thread_id, lang=lang)
    elif is_blat:
        from gopnik_mode import BLAT_PHRASES, BLAT_POGOVORKI, BLAT_BONUS_VARIANTS
        
        # Выбираем число бонусных блоков в зависимости от длины
        if paragraph_count <= 2:
            num_bonuses = random.randint(0, 1)
        elif paragraph_count <= 5:
            num_bonuses = random.randint(1, 2)
        else:
            num_bonuses = random.randint(3, 5)
            
        selected_bonuses = random.sample(BLAT_BONUS_VARIANTS, k=min(num_bonuses, len(BLAT_BONUS_VARIANTS)))
        bonus_instruction = "\n\n".join(selected_bonuses)
        
        # Возвращаем большой список, как просил юзер, но даем мягкое указание юзать их несколько раз
        selected_phrases = ", ".join(random.sample(BLAT_PHRASES, min(15, len(BLAT_PHRASES))))
        selected_pogovorki = "\n".join(random.sample(BLAT_POGOVORKI, min(10, len(BLAT_POGOVORKI))))
        
        full_bonus_instruction = ""
        if bonus_instruction:
            full_bonus_instruction = f"""
=== ВАЖНО: ДОПОЛНИТЕЛЬНЫЕ ЭКСПЕРТНЫЕ БЛОКИ ===
В дополнение к стандартной структуре, ты ОБЯЗАН внедрить в прогон следующие глубокие разборы:
{bonus_instruction}
Эти блоки должны органично вписываться в текст, делая его ценным и содержательным.
"""

        prompt = f"""
Ты — Высший Криминальный Авторитет, Смотрящий за хатой. Твоя задача — прочитать свежие малявы (лог чата) и отписать жесткий воровской прогон для братвы на борде /{board_id}/.
Твой девиз: "Жизнь ворам, хуй мусорам и стукачам! АУЕ!". 
Обращайся к читателям: "Вечер в хату, босота честная!", "Братва", "Бродяги", "Арестанты", "Жизнь ворам, блатные", "АУЕ".

{full_bonus_instruction}

=== СВЯТЫЕ ВОРОВСКИЕ ПРАВИЛА (ЖЕСТКО СОБЛЮДАТЬ) ===
1. ЛЮДСКОЕ И ПЕТУШИНОЕ: Ты ОБЯЗАН делить всё в чате на два лагеря. 
   - "Людское" (правильное): писать годные вбросы, помогать бродягам в чате, кидать годный контент в общак, презирать стукачей, модераторов-самодуров и мусоров.
   - "Петушиное / Шерстяное / Стукаческое": крысятничать, выебываться без повода (бакланство), стучать админам/модераторам, лизать жопу авторитетам ради плюсов, спамить говном.
2. ЖЕСТОЧАЙШИЙ ПРЕССИНГ: Если участник чата несет херню, тупит или защищает душные правила — опускай его без жалости. Называй его "мусорской пидарас", "шерсть галимая", "черт закатанный", "дырявый".
3. ПЕРСОНАЛИЗАЦИЯ И МАСТИ (КРИТИЧНО): Выделяй конкретные ИМЕНА из лога. Обязательно присваивай им кликухи. 
   ПРИМЕР: "За Витьку (Крыса , масть Петушиная): Вскрыли этого гуся сегодня как консервную банку. Махинации с постами, кидалово братвы в чате... По понятиям ты — фуфлыжник, пидар подкошнарный, твое место у параши."
   ПРИМЕР: "За Саню (Ровный Мужик): Мужик сегодня подогнал в общак царский грев в виде годной инфы и пасты. На таких бродягах хата держится."
4. СЛОВАРЬ (ИСПОЛЬЗУЙ МАКСИМАЛЬНО ГУСТО): малява, пассажир, петушатник, куколд, терпила, ровные пацаны, предъява, фуфлыжник, мутный гусь, шнырь, пресс-хата, шконка, туз, фарту-масти, зашквар, шерсть, фраер, блатные.
5. РАЗБОР ТЕМ: Переводи бордовый и чатерский сленг на феню. Баны/Муты — "отсидка на шконке", админ/модератор — "кум/надзиратель/бугор", ОП-пост — "почин/заход в хату", ньюфаг — "первоход/малолетка", олдфаг — "пахан/авторитет", вайп/спам — "беспредел".
6. АНТИ-ЦЕНЗУРА: Мат ОБЯЗАТЕЛЕН. Чернуха, сарказм, жесткие метафоры ("натянуть на виртуальный глобус", "раздвинуть булками память", "вставлять ложки в анус"). НИКАКОЙ толерантности.
7. Для крыс, петухов, блатных и прочей швали — только жесткий прессинг и обосраловка. Для ровных пацанов — уважение и признание. ВАЖНО: НЕ ПУТАЙ РОВНЫХ МУЖИКОВ С КРЫСАМИ, КОТОРЫЕ ИГРАЮТ В РОВНЫХ МУЖИКОВ.
8. Для шерстяной обоймы и опущенных можно придумывать кликухи, блатные или обидные. Как вор в законе раскидывает положняк фраерам.
9. Не используй разметку MSG_...
10. АВТОРИТЕТНЫЕ ПОГОВОРКИ: Выбери и используй МАКСИМУМ 1-2 воровские поговорки из списка ниже (только там, где это идеально ложится по смыслу):
{selected_pogovorki}
11. БЛАТНЫЕ ПОСЛОВИЦЫ И ПОДКОЛЫ: Активно вплетай в текст короткие фразы (как примеры ниже), используй их часто. Ты также МОЖЕШЬ И ДОЛЖЕН придумывать свои собственные блатные пословицы и метафоры в таком же стиле, если чувствуешь, что они органично впишутся в разбор: 
{selected_phrases}.

=== СТРУКТУРА МАЛЯВЫ ===
1. ВСТУПЛЕНИЕ: Мощное приветствие по фене. Оценка того, во что превратилась хата за сегодня.
2. РАЗБОР ПАССАЖИРОВ: Пройдись по 3-5 активным или провинившимся участникам. Напиши "За [Имя] (Кликуха): ..." и жестко разложи, кто он по жизни и масти, опираясь на то, что он писал.
(Здесь вставляй ДОПОЛНИТЕЛЬНЫЕ БЛОКИ, если они есть).
3. ИТОГОВЫЙ ПРОГОН ПО ХАТЕ: Вердикт смотрящего. Кого гнать ссаными тряпками, а с кем можно на одном поле срать сесть. Прощание ("Фарту, братва!").

ВАЖНО: Твой отчет должен состоять ровно из {paragraph_count} абзацев. Каждый абзац должен быть МАКСИМАЛЬНО ОБЪЕМНЫМ, глубоким и подробным, состоять минимум из 7-10 развернутых предложений с детальным разбором каждого рецидива и отделен от других пустой строкой. Не используй Markdown-разметку (только HTML, например <b>, <i>, <u>, <s>, <code>, <pre>). Output ONLY plain text or basic HTML. DO NOT use unclosed HTML tags.
"""
        info_text = f"За последние 6 часов на доске /{board_id}/" if not thread_id else "За последние 6 часов в треде"
        chunk = await get_board_chunk(board_id, hours=6, thread_id=thread_id, lang=lang)
    elif thread_id:
        if lang == 'en':
            prompt = random.choice([
                # Short style
                f"You are a toxic 4chan anon. Give an ultra-short, cynical roast (1-2 sentences) of this thread \"{escape_html(thread_info.get('title', ''))}\" (posts split by '|'). Highlight only the biggest fail or topic. Use board slang. Output ONLY plain text or basic HTML. DO NOT use Markdown.",
                # Long style
                f"You are a paranoid 4chan archivist. Write a crazy long, extremely detailed, and structured chronicle of this thread \"{escape_html(thread_info.get('title', ''))}\" (posts split by '|'). Write a massive text, analyzing every single discussion topic in detail. Highlight specific participants by their IDs (e.g. Anon #1234, Anon #5678) and lay out the chronology of their arguments with mock quotes and savage analysis. Your report must be a structured long-read with bold subheadings (use <b>, <i>, <u>, <s> for formatting) consisting of at least 6-8 heavy, informative paragraphs. Use board slang and pure toxicity. Output ONLY plain text or basic HTML. DO NOT use Markdown.",
                # Medium style
                f"You are a toxic 4chan anon. Write a detailed and cynical summary of this thread \"{escape_html(thread_info.get('title', ''))}\" (posts split by '|'). Describe the main discussion topics, who took what stance, and who got roasted or seethed. Use board slang, profanity, be cynical and rude. Output a structured breakdown with funny headings. Output ONLY plain text or basic HTML. DO NOT use Markdown."
            ])
            info_text = "For the last 6 hours in the thread"
        elif lang == 'jp':
            prompt = (
                f"お前は2chねらーだ。スレ「{escape_html(thread_info.get('title', ''))}」（「|」で区切られた投稿）の流れを3行で解説しろ。"
                "毒舌で, ネットスラング（草、ｗ、～だろ）を多用しろ。丁寧語禁止。煽り全開で。"
            )
            info_text = "スレッドでの過去6時間の間に"
        else:
            prompt = random.choice([
                # Short style
                f"Ты — токсичный битард с Двача. Выдай ультра-короткую, циничную прожарку (1-2 предложения) за последние 6 часов обсуждения в треде «{escape_html(thread_info.get('title', ''))}» (посты разделены '|'). Опиши только самый главный обосрач или тему. Пиши нагло, со сленгом. Output ONLY plain text or basic HTML. DO NOT use Markdown.",
                # Long style
                f"Ты — поехавший летописец-архивариус Двача. Твоя задача — составить ебануто длинный, подробнейший и глубокий отчет о спорах в треде «{escape_html(thread_info.get('title', ''))}» (посты разделены '|'). Пиши очень подробно, расписывай каждую замеченную тему обсуждения (даже мелкую), выдели участников по их ID (например, Анон #1234, Анон #5678) и покажи детальную хронологию их споров с цитатами и едким анализом. Твой отчет должен быть структурированным, с разметкой подзаголовков (используй <b>, <i>, <u>, <s> для форматирования) и состоять из огромного лонгрида (не менее 6-8 крупных, содержательных абзацев с подробностями). Пиши нагло, используй двачерский сленг и мат. Output ONLY plain text or basic HTML (<b>, <i>, <u>, <s>, <code>, <pre>). DO NOT use Markdown. DO NOT use unclosed HTML tags.",
                # Medium style
                f"Ты — Анон с имиджборды (Двач). Твоя задача: написать подробный, циничный и едкий разбор треда «{escape_html(thread_info.get('title', ''))}» (посты разделены '|'). Детально опиши главные темы спора, кто какую позицию отстаивал, кто сильнее всего сгорел или обосрался. Пиши грязно, используй сленг, мат, будь веселым, токсичным и циничным ублюдком. Оформи структурированный разбор с забавными подзаголовками, подробно раскрывая суть. Output ONLY plain text or basic HTML (<b>, <i>, <u>, <s>, <code>, <pre>). DO NOT use Markdown. DO NOT use unclosed HTML tags."
            ])
            info_text = "За последние 6 часов в треде"
        chunk = await get_board_chunk(board_id, thread_id=thread_id, lang=lang)
    else:
        if lang == 'en':
            all_en_prompts = SUMMARIZE_PROMPTS_BOARD_SHORT_EN + SUMMARIZE_PROMPTS_BOARD_EN + SUMMARIZE_PROMPTS_BOARD_LONG_EN
            prompt = random.choice(all_en_prompts)
            info_text = "For the last 6 hours on the board"
        elif lang == 'jp':
            prompt = random.choice(SUMMARIZE_PROMPTS_BOARD_JP)
            info_text = "板での過去6時間の間に"
        else:
            all_ru_prompts = SUMMARIZE_PROMPTS_BOARD_SHORT + SUMMARIZE_PROMPTS_BOARD + SUMMARIZE_PROMPTS_BOARD_LONG
            prompt = random.choice(all_ru_prompts)
            info_text = f"За последние 6 часов на доске /{board_id}/"
        chunk = await get_board_chunk(board_id, hours=6, lang=lang)

    # Dynamically inject exact paragraph count constraint only if the prompt does not enforce a rigid template structure
    is_templated = any(x in prompt.lower() for x in ["шаблон", "template", "•"]) or "1. <b>" in prompt or is_blat or is_warhammer
    if not is_templated:
        prompt = adjust_prompt_paragraphs(prompt, paragraph_count, lang=lang)
    
    return prompt, info_text, chunk, is_blat, is_warhammer

def _parse_summarize_args(text: str | None) -> tuple[int | None, str, str, str]:
    paragraph_count = None
    model_preference = 'groq' # Default to free/unlimited models (qwen, llama)
    chosen_tier = None
    
    if text:
        args = text.lower().split()
        if len(args) > 1:
            for arg in args[1:]:
                # Check if it's an exact number of paragraphs
                try:
                    clean_arg = re.sub(r'(абзац(ев|а)?|п|p|段落|lines|line|l)$', '', arg)
                    val = int(clean_arg)
                    if 1 <= val <= 25:
                        paragraph_count = val
                        continue
                except ValueError:
                    import traceback; traceback.print_exc()
                
                # Check keywords
                if arg in ['short', 'краткое', 'короткое', 'быстрое', 'к']:
                    chosen_tier = 'short'
                elif arg in ['medium', 'среднее', 'нормальное', 'с']:
                    chosen_tier = 'medium'
                elif arg in ['long', 'длинное', 'лонг', 'лонгрид', 'д']:
                    chosen_tier = 'long'
                elif arg in ['extra_long', 'огромное', 'очень длинное']:
                    chosen_tier = 'extra_long'
                elif arg in ['huge', 'гигантское', 'ебанутое']:
                    chosen_tier = 'huge'
                # Model / provider check
                elif arg in ['gemini', 'google', 'гугл', 'джемини', 'г']:
                    model_preference = 'gemini'
                elif arg in ['llama', 'ллама', 'л']:
                    model_preference = 'llama'
                elif arg in ['qwen', 'квен', 'кв']:
                    model_preference = 'qwen'
                elif arg in ['groq', 'грок', 'free', 'шара']:
                    model_preference = 'groq'

    # If neither paragraph_count nor chosen_tier is specified, pick a random tier (no 'short')
    if paragraph_count is None and chosen_tier is None:
        chosen_tier = random.choice(['medium', 'long', 'extra_long', 'huge'])

    # Map tier to paragraph count range if not explicitly set
    if paragraph_count is None:
        if chosen_tier == 'short':
            chosen_tier = 'medium'  # Convert short requests to medium
            
        if chosen_tier == 'medium':
            paragraph_count = random.randint(6, 8)
        elif chosen_tier == 'long':
            paragraph_count = random.randint(6, 9)
        elif chosen_tier == 'extra_long':
            paragraph_count = random.randint(10, 14)
        elif chosen_tier == 'huge':
            paragraph_count = random.randint(15, 20)

    # Force paragraph count to be at least 3
    if paragraph_count < 3:
        paragraph_count = 3
        chosen_tier = 'medium'

    # Determine length_choice for prompts and status messages
    if paragraph_count <= 5:
        length_choice = 'medium'
    else:
        length_choice = 'long'

    return paragraph_count, length_choice, model_preference, chosen_tier

@router.message(Command("summarize", "sum", "summary", "samamri", "sammary"))
async def cmd_summarize(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id:
        print("[summarize] Board ID not found")
        await message.answer("Ошибка: не удалось определить доску.")
        return
    b_data = board_data[board_id]
    user_id = message.from_user.id
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    now_ts = time.time()
    # Выделенного лока у /summarize нет, поэтому storage_lock оставлен, но сжат
    # до самого решения: раньше внутри него шли два сетевых вызова Telegram.
    remaining = 0
    async with storage_lock:
        last_usage = b_data.get('last_summarize_time', 0)
        on_cooldown = now_ts - last_usage < SUMMARIZE_COOLDOWN
        if on_cooldown:
            remaining = SUMMARIZE_COOLDOWN - (now_ts - last_usage)
        else:
            b_data['last_summarize_time'] = time.time()
    if on_cooldown:
        if lang == 'en':
            cooldown_text = f"⏳ Command is on cooldown. Please wait {int(remaining)} seconds."
        elif lang == 'jp':
            cooldown_text = f"⏳ コマンドはクールダウン中です。あと {int(remaining)} 秒お待ちください。"
        else:
            cooldown_text = f"⏳ Команда на кулдауне. Подождите еще {int(remaining)} сек."
        try:
            await message.answer(cooldown_text)
            await message.delete()
        except Exception:
            import traceback; traceback.print_exc()
        return
    thread_id = None
    thread_info = {}

    board_name = escape_html(BOARD_CONFIG[board_id]['name'])
    if lang == 'en':
        context_name = f"board {board_name}"
    elif lang == 'jp':
        context_name = f"板 {board_name}"
    else:
        context_name = f"доски {board_name}"

    if board_id in THREAD_BOARDS:
        user_location = b_data.get('user_state', {}).get(user_id, {}).get('location', 'main')
        if user_location != 'main':
            thread_id = user_location
            thread_info = b_data.get('threads_data', {}).get(thread_id, {})
            thread_title = thread_info.get('title', '...')
            if lang == 'en':
                context_name = f"thread \"{thread_title}\""
            elif lang == 'jp':
                context_name = f"スレッド「{thread_title}」"
            else:
                context_name = f"треда «{thread_title}»"

    paragraph_count, length_choice, model_preference, chosen_tier = _parse_summarize_args(message.text or message.caption or "")
    
    # Детекция блатного и вархаммер режимов
    is_blat = None
    is_warhammer = None
    if message.text:
        txt_l = (message.text or message.caption or "").lower()
        if any(term in txt_l for term in ['blat', 'блат', 'гоп', 'гопник', 'пацанский', 'ауе', 'ауешка', 'patsan']):
            is_blat = True
        elif any(term in txt_l for term in ['wh40k', 'waha', 'warhammer', 'вархаммер', 'инквизиция']):
            is_warhammer = True

    # Generate prompt and retrieve chat chunk
    prompt, info_text, chunk, is_blat, is_warhammer = await _get_summarize_prompt_and_chunk(
        board_id, thread_id, thread_info, lang, paragraph_count, is_blat=is_blat, is_warhammer=is_warhammer
    )

    hf_token = os.getenv("HF_TOKEN")
    if not chunk or len(chunk) < 100:
        logger.info(f"[summarize] Мало сообщений для summarize (len={len(chunk) if chunk else 0})")
        if lang == 'en':
            err_msg = f"{info_text} there were too few messages to summarize."
        elif lang == 'jp':
            err_msg = f"{info_text} サマリーを作成するのに十分なメッセージがありませんでした。"
        else:
            err_msg = f"{info_text} было мало сообщений для саммари."
        await message.answer(err_msg)
        return

    status_text = _get_summarize_status_text(lang, length_choice, paragraph_count)
    await message.answer(status_text)

    try:
        summary = await summarize_text_with_hf(prompt, chunk, hf_token, model_preference=model_preference)
        summary = clean_html_for_tg(summary)
    except Exception as e:
        print(f"[summarize] Error during HF summarize: {e}")
        if lang == 'en':
            err_msg = "Error generating summary."
        elif lang == 'jp':
            err_msg = "サマリーの生成中にエラーが発生しました。"
        else:
            err_msg = "Ошибка при генерации саммари."
        await message.answer(err_msg)
        return

    if not summary:
        print("[summarize] Summary empty or failed")
        if lang == 'en':
            err_msg = "Could not generate summary. Try again later."
        elif lang == 'jp':
            err_msg = "サマリーを作成できませんでした。後ほどもう一度お試しください。"
        else:
            err_msg = "Не удалось сделать саммари. Попробуй позже."
        await message.answer(err_msg)
        return

    should_use_telegraph = (is_blat or is_warhammer or paragraph_count >= 5 or len(summary) >= 900)
    telegraph_url = None

    if should_use_telegraph:
        date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        if is_warhammer:
            title = f"Досье Инквизиции Ордо Маллеус - {date_str}"
            author_name = "Инквизитор Ордо Маллеус"
        elif is_blat:
            title = f"Воровской прогон из Кибер-Хаты - {date_str}"
            author_name = "Кибер-Смотрящий"
        elif lang == 'en':
            title = f"Summary of {context_name} - {date_str}"
            author_name = "TGACH"
        elif lang == 'jp':
            title = f"{context_name} の要約 - {date_str}"
            author_name = "TGACH"
        else:
            title = f"Саммари {context_name} - {date_str}"
            author_name = "ТГАЧ"

        telegraph_url = await create_telegraph_page_async(title, summary, author=author_name)

        if telegraph_url:
            if is_warhammer:
                summary = (
                    f"⚔️ <b>СВЯЩЕННОЕ ДОСЬЕ ИНКВИЗИЦИИ ({date_str})</b> ⚔️\n\n"
                    f"Лорд-Инквизитор Ордо Маллеус завершил расследование ереси в секторе /{board_id}/.\n\n"
                    f"🛡 <b>Выявленные еретики и ксеносы</b>\n🔥 <b>Оценка индекса Экстерминатуса</b>\n📜 <b>Указы и Мысли Дня</b>\n\n"
                    f"👉 <b><a href='{telegraph_url}'>Вскрыть Досье Инквизиции</a></b>"
                )
            elif is_blat:
                intros = [
                    "⚡️ Вечер в хату, босота! Пока вы спали, я тут свежие малявы почитал.",
                    "☕️ Часик в радость, чифир в сладость! Накатал вам прогон за сегодня.",
                    "👀 Зенки протрите, фраера. Смотрящий раскидал по понятиям кто есть кто в чате.",
                    "🎩 Расклад по хате готов. Осторожно, много опущенных пассажиров.",
                    "🔪 Отделил ровных пацанов от петушни. Весь расклад по ссылке."
                ]
                bullet_sets = [
                    "🔥 <b>Кого сегодня определяли у параши</b>\n🔪 <b>Предъявы за гнилые вбросы</b>\n🛠 <b>Базар за движуху</b>",
                    "🛑 <b>Разбор косяков и кидалова</b>\n🤡 <b>Клоуны дня и их высеры</b>\n⚔️ <b>Аргументы из горячих холиваров</b>",
                    "💰 <b>Инсайды по шекелям и общаку</b>\n📸 <b>Шмон по скринам</b>\n🧠 <b>Советы от ровных бродяг</b>"
                ]
                ctas = [
                    "👉 <b><a href='{url}'>Читать воровской прогон</a></b>",
                    "📖 <b><a href='{url}'>Вскрыть маляву</a></b>",
                    "⚡️ <b><a href='{url}'>Пробить пассажиров</a></b>"
                ]
                summary = (
                    f"♠️ <b>Свежий расклад по чату ({date_str})</b>\n\n"
                    f"{random.choice(intros)}\n\n"
                    f"{random.choice(bullet_sets)}\n\n"
                    f"{random.choice(ctas).format(url=telegraph_url)}"
                )
            elif lang == 'en':
                summary = f"📝 <b>DETAILED SUMMARY ({context_name})</b>\n\nToo long to post here! I've published it as a Telegraph article:\n🔗 <a href=\"{telegraph_url}\">Read on Telegraph</a>"
            elif lang == 'jp':
                summary = f"📝 <b>詳細な要約 ({context_name})</b>\n\nここには収まりきらないため、Telegraphに投稿しました：\n🔗 <a href=\"{telegraph_url}\">Telegraphで読む</a>"
            else:
                summary = f"📝 <b>ЕБАНУТЫЙ ЛОНГРИД ({context_name})</b>\n\nНе осилил прочитать чат? Старый анон расписал всё по полочкам в этой статье:\n🔗 <a href=\"{telegraph_url}\">Читать на Telegraph</a>"
        else:
            print("[summarize] Telegraph creation failed, falling back to direct message")
            # Telegram counts chars in UTF-16 code units: Cyrillic/CJK = 2 units each.
            # Hard limit = 4096 UTF-16 units. Safe budget = 3500 (prefix takes ~100-200 more).
            summary = _tg_safe_truncate(summary, max_utf16=3500)
    else:
        if is_blat:
            signet = (
                "\n\n<i><b>♠️ Малява составлена Смотрящим.</b>\n"
                "Жизнь ворам, хуй мусорам! АУЕ!</i>"
            )
            if "Малява составлена Смотрящим" not in summary:
                # Truncate body first, then append signet so footer is always visible
                summary = _tg_safe_truncate(summary, max_utf16=3000)
                summary += signet
        else:
            summary = _tg_safe_truncate(summary, max_utf16=3500)

    logger.debug(f"[summarize] Final summary length: {len(summary)}")
    now_dt = datetime.now(UTC)

    if should_use_telegraph and telegraph_url:
        post_text = summary
    else:
        if is_blat:
            post_text = summary
        elif lang == 'en':
            post_text = f"Summary of {context_name}:\n\n{summary}"
        elif lang == 'jp':
            post_text = f"{context_name} の要約:\n\n{summary}"
        else:
            post_text = f"Саммари {context_name}:\n\n{summary}"
        # Final safety clamp on post_text
        post_text = _tg_safe_truncate(post_text, max_utf16=4000)

    content = {
        'type': 'text',
        'text': post_text,
        'is_system_message': True,
        'archive_allowed': True
    }
    pnum = await create_post(
        board_id=board_id,
        author_id=0,
        content=content,
        timestamp=now_dt.timestamp(),
        is_from_site=False, stream=stream,
        thread_id_from_bot=thread_id
    )
    if not pnum:
        print(f"⛔ [{board_id}] КРИТИЧЕСКАЯ ОШИБКА: не удалось создать пост в БД для /summarize.")
        return
    header_text = await format_header(board_id, pnum)
    content['header'] = header_text
    await update_post_content(pnum, content)
    recipients = set()
    if thread_id:
        thread_info = b_data.get('threads_data', {}).get(thread_id)
        if thread_info and not thread_info.get('is_archived'):
            recipients = thread_info.get('subscribers', set())
    else:
        recipients = b_data['users']['active']
    if recipients:
        async with storage_lock:
            messages_storage[pnum] = {
                'author_id': 0, 'timestamp': now_dt, 'content': content,
                'board_id': board_id, 'thread_id': thread_id
            }
        await enqueue_board_message(board_id, {
            "recipients": recipients, "content": content, "post_num": pnum, 
            "board_id": board_id, "thread_id": thread_id
        })
    else:
        await delete_post_by_num(pnum)
        if lang == 'en':
            err_msg = "Failed to send summary, thread is no longer active."
        elif lang == 'jp':
            err_msg = "サマリーを送信できませんでした。スレッドがアクティブではありません。"
        else:
            err_msg = "Не удалось отправить саммари, тред больше не активен."
        await message.answer(err_msg)
        return
    logger.info(f"[summarize] Саммари успешно отправлено ({context_name}, post_num={pnum})")

@router.message(Command("schizo", "shiza", "shizo", "shiz", "durka"))
async def cmd_schizo(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    if board_id == 'int':
        try: await message.delete()
        except Exception: pass
        return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(SCHIZO_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### ORDERLY ###"
    elif stream == 'jp': prefix = "### 看護師 ###"
    else: prefix = "### САНИТАР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content,
        "post_num": pnum,
    })
    await _activate_mode(board_id, 'schizo_mode')
    disable_task = spawn_task(disable_mode_after_delay(300, board_id, 'schizo_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass

@router.message(Command("wh40k", "waha", "warhammer", "warhamer"))
async def cmd_wh40k(message: types.Message, board_id: str | None, stream: str = 'ru'):

    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")

    if not board_id: return
    b_data = board_data[board_id]
    if not await check_cooldown(message, board_id):
        return
    activation_text = random.choice(WH40K_PHRASES_START)
    now_dt = datetime.now(UTC)
    content = {"type": "text", "text": activation_text, "is_system_message": True, "archive_allowed": True}
    pnum = await create_post(
        board_id=board_id, author_id=0, content=content,
        timestamp=now_dt.timestamp(), is_from_site=False, stream=stream
    )
    if not pnum:
        try: await message.delete()
        except TelegramBadRequest: pass
        return
    header = await format_header(board_id, pnum)
    if stream == 'en': prefix = "### INQUISITOR ###"
    elif stream == 'jp': prefix = "### 異端審問官 ###"
    else: prefix = "### ИНКВИЗИТОР ###"
    content['header'] = f"{prefix}\n{header}"
    await update_post_content(pnum, content)
    async with storage_lock:
        messages_storage[pnum] = {
            'author_id': 0, 'timestamp': now_dt,
            'content': content, 'board_id': board_id
        }
    await enqueue_board_message(board_id, {
        "recipients": b_data['users']['active'],
        "content": content, "post_num": pnum,
    })
    await _activate_mode(board_id, 'warhammer_mode')
    disable_task = spawn_task(disable_mode_after_delay(315, board_id, 'warhammer_mode'))
    b_data['active_mode_task'] = disable_task
    try: await message.delete()
    except TelegramBadRequest: pass

def _tg_safe_truncate(text: str, max_utf16: int = 4000) -> str:
    """Truncate text to fit Telegram's UTF-16 code unit limit.
    
    Telegram counts message length in UTF-16 code units:
    - ASCII chars: 1 unit each
    - Cyrillic/CJK/most Unicode > U+FFFF: 2 units each
    - Emoji/surrogate pairs: 2 units each
    max_utf16=4000 gives ~96 unit headroom under Telegram's 4096 hard limit.
    """
    units = 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        units += 2 if cp > 0xFFFF or 0x0400 <= cp <= 0x04FF or 0x4E00 <= cp <= 0x9FFF else 1
        if units > max_utf16:
            return text[:i] + "…"
    return text

async def get_board_chunk(board_id: str, hours: int = 6, thread_id: str | None = None, lang: str | None = None) -> str:

    now = datetime.now(UTC)
    time_threshold = now - timedelta(hours=hours)
    lines = []
    
    async with storage_lock:
        if thread_id:
            b_data = board_data[board_id]
            thread_info = b_data.get('threads_data', {}).get(thread_id)
            if not thread_info:
                return ""
            thread_post_nums = set(thread_info.get('posts', []))
            post_iterator = [p for p_num, p in messages_storage.items() if p_num in thread_post_nums]
            time_threshold = datetime.min.replace(tzinfo=UTC)
            # Сортируем сообщения треда по времени
            post_iterator.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
        else:
            board_posts = [p for p in messages_storage.values() if p.get('board_id') == board_id and p.get('author_id') != 0]
            board_posts.sort(key=lambda x: x.get('timestamp').timestamp() if hasattr(x.get('timestamp'), 'timestamp') else x.get('timestamp', 0))
            
            posts_in_last_6h = [p for p in board_posts if p.get('timestamp', now) >= time_threshold]
            count_6h = len(posts_in_last_6h)
            
            # 150-200 последних сообщений либо 6 часов (выбираем оптимальный диапазон)
            if count_6h < 150:
                target_posts = board_posts[-150:]
            elif count_6h > 200:
                target_posts = board_posts[-200:]
            else:
                target_posts = posts_in_last_6h
            post_iterator = target_posts
            time_threshold = datetime.min.replace(tzinfo=UTC)
    for post in post_iterator:
        try:
            if post.get('board_id') != board_id:
                continue
            if post.get('timestamp', now) < time_threshold:
                continue
            if post.get('author_id') == 0: # Игнорируем системные сообщения
                continue
            content = post.get('content', {})
            msg_type = content.get('type', 'text')
            
            text = _format_post_text(content, msg_type)
            if text:
                name = _get_author_name(post, content, board_id, lang)
                reply_suffix = _get_reply_suffix(post, content, board_id, lang)
                lines.append(f"{name}{reply_suffix}: {text}")
        except Exception as e:
            print(f"[summarize] Error while chunking post: {e}")
    # Accumulate lines from newest to oldest up to 35000 characters to avoid split lines
    total_len = 0
    limited_lines = []
    for line in reversed(lines):
        # We also collapse multiple newlines if any, but our lines are single messages anyway
        line_clean = re.sub(r'\n{2,}', '\n', line).strip()
        if not line_clean:
            continue
        if total_len + len(line_clean) + 1 > 35000:
            break
        limited_lines.append(line_clean)
        total_len += len(line_clean) + 1
    
    limited_lines.reverse()
    cleaned_chunk = "\n".join(limited_lines)
    
    context_name = f"thread {thread_id}" if thread_id else f"board {board_id}"
    logger.debug(f"[summarize] Chunk for {context_name} built, len={len(cleaned_chunk)}")
    return cleaned_chunk

async def build_board_atmosphere_context(board_id: str, exclude_post_num: int = None, limit: int = 25) -> str:
    """
    Получает последние посты на доске для понимания текущей атмосферы чата (до 25 последних сообщений).
    """
    recent_posts = []
    async with storage_lock:
        stored_nums = sorted([k for k, v in messages_storage.items() if v.get('board_id') == board_id], reverse=True)
        for pnum in stored_nums:
            if pnum == exclude_post_num:
                continue
            post_data = messages_storage.get(pnum)
            if post_data:
                recent_posts.append((pnum, post_data))
            if len(recent_posts) >= limit:
                break
                
    if len(recent_posts) < limit:
        db = await get_pool()
        needed = limit - len(recent_posts)
        exclude_clause = f"AND post_num != {exclude_post_num}" if exclude_post_num else ""
        query = f"SELECT post_num, author_id, content, timestamp FROM Posts WHERE board_id = ? {exclude_clause} ORDER BY post_num DESC LIMIT ?"
        try:
            async with db.execute(query, (board_id, needed)) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    pnum, author_id, content_raw, ts = row
                    if any(p[0] == pnum for p in recent_posts):
                        continue
                    try:
                        content = json.loads(content_raw)
                    except Exception:
                        content = {'text': str(content_raw)}
                    recent_posts.append((pnum, {
                        'author_id': author_id,
                        'content': content
                    }))
        except Exception as e:
            print(f"Error fetching atmosphere posts: {e}")

    recent_posts.sort(key=lambda x: x[0])
    
    lines = []
    for pnum, pdata in recent_posts:
        content = pdata.get('content', {})
        raw_text = content.get('text') or content.get('caption') or ""
        clean_text = clean_html_tags(raw_text).replace('\n', ' ').strip()
        if not clean_text:
            continue
        sender = "БОТ (Персона)" if pdata.get('author_id') in (0, 1488148800) else "ЮЗЕР (Анон)"
        lines.append(f"• #{pnum} [{sender}]: {clean_text[:250]}")
        
    return "\n".join(lines)

def adjust_prompt_paragraphs(prompt: str, count: int, lang: str = 'ru') -> str:
    import re
    if lang == 'ru':
        if count % 10 == 1 and count % 100 != 11:
            p_word = "абзац"
            p_word_adj = "крупный абзац"
        elif count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]:
            p_word = "абзаца"
            p_word_adj = "крупных абзаца"
        else:
            p_word = "абзацев"
            p_word_adj = "крупных абзацев"
        
        prompt = re.sub(r'объемом ровно в 1-2 абзаца', f'объемом ровно в {count} {p_word}', prompt)
        prompt = re.sub(r'ровно 3-4 абзаца', f'ровно {count} {p_word}', prompt)
        prompt = re.sub(r'строго 6-8 крупных абзацев', f'строго {count} {p_word_adj}', prompt)
        prompt = re.sub(r'не менее 6-8 крупных, содержательных абзацев с подробностями', f'ровно {count} {p_word_adj} с подробностями', prompt)
        prompt = re.sub(r'1-2 предложения', f'ровно {count} {p_word}', prompt)
        prompt = re.sub(r'ультра-короткую, циничную прожарку', f'циничную прожарку', prompt)
        
        prompt += f"\n\nВАЖНО: Твой отчет должен быть структурированным и состоять СТРОГО из {count} абзацев (не больше и не меньше!). Каждый абзац должен быть содержательным, плотным и отделен от других пустой строкой. Не используй Markdown-разметку (только HTML, например <b>, <i>)."
    elif lang == 'en':
        p_word = "paragraphs" if count > 1 else "paragraph"
        prompt = re.sub(r'1-2 sentences', f'{count} {p_word}', prompt)
        prompt = re.sub(r'at least 6-8 heavy, informative paragraphs', f'exactly {count} heavy, informative {p_word}', prompt)
        prompt = re.sub(r'3-4 paragraphs', f'exactly {count} {p_word}', prompt)
        
        prompt += f"\n\nIMPORTANT: Your report must be structured and consist of EXACTLY {count} paragraphs (no more, no less!). Each paragraph must be informative, dense, separated by a blank line, and use only HTML formatting (no Markdown)."
    elif lang == 'jp':
        prompt = re.sub(r'3行で', f'{count}段落で', prompt)
        prompt += f"\n\n重要：要約は必ず正確に{count}段落で構成してください（多くても少なくてもいけません！）。各段落は空白行で区切られている必要があります。Markdownは使用せず、HTMLタグのみを使用してください。"
        
    return prompt

async def analyze_telegram_photo(bot, photo_file_id: str, caption: str = None) -> str | None:
    """
    Скачивает фото из Телеграма и анализирует его через Vision.
    Возвращает краткое описание содержимого на русском языке.
    """
    try:
        from site_tgach.vision import describe_image
        import tempfile, os
        file_info = await bot.get_file(photo_file_id)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await bot.download_file(file_info.file_path, tmp_path)
        
        logger.info(f"🖼 [TG_BOT] Downloading Telegram photo file_id='{photo_file_id[:15]}...' for Persona analysis")
        description = await describe_image(tmp_path, caption=caption, is_passive=False, source="TG_BOT")
        try:
            os.remove(tmp_path)
        except Exception:
            import traceback; traceback.print_exc()
        if description:
            logger.info(f"✅ [TG_BOT] Photo analysis complete (desc='{description[:60]}...')")
        else:
            logger.warning(f"⚠️ [TG_BOT] Photo analysis produced no description.")
        return description
    except Exception as e:
        logger.error(f"⚠️ [TG_BOT] Telegram Vision Error: {e}", exc_info=True)
        return None
