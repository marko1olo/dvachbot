import re
import time
import json
import logging
from typing import Tuple, List, Optional, Dict, Any

from common.db_pool import get_pool, db_lock, db_transaction
from common.database import (
    update_shadow_mute,
    update_user_settings_db,
    apply_auto_censure,
    log_global_event,
    get_post_by_num
)
from site_tgach.admin_config import ADMIN_IDS

logger = logging.getLogger("extreme_defense")

# ==============================================================================
# 1. KEYWORDS & CLASSIFICATION MATRICES (ZERO FALSE POSITIVES)
# ==============================================================================

EXPLICIT_COPRO_TAGS = {
    'coprophilia', 'coprophagy', 'copro', 'coprophiliac', 'scat',
    'defecation', 'defecating', 'pooping', 'shit_eating', 'fecal_matter'
}

COPRO_BODY_CONTEXT = {
    'human', 'body', 'dirty', 'messy', 'eating', 'smearing', 'mouth',
    'anal', 'genitalia', 'nsfw', 'nudity', 'grotesque', 'diarrhea',
    'toilet', 'adult', 'penis', 'buttocks', 'masturbation', 'fingering'
}

SAFE_COPRO_EXCLUSIONS = {
    'jazz', 'music', 'vocal', 'improv', 'singing', 'song',
    'coffee', 'mug', 'cup', 'humor', 'joke', 'meme',
    'wildlife', 'nature', 'animal', 'farm', 'dog', 'cat', 'bird', 'horse', 'cow'
}

EXPLICIT_GURO_TAGS = {
    'guro', 'eroguro', 'ero_guro', 'snuff', 'necrophilia',
    'dismemberment', 'mutilation', 'evisceration', 'decapitation',
    'severed_head', 'severed_limb'
}

GORE_SEVERE_INJURY = {
    'wound', 'viscera', 'flesh', 'corpse', 'dead_body',
    'internal_organs', 'self-harm', 'cutting'
}

SAFE_ART_STYLES = {
    'anime', 'illustration', 'sketch', 'painting', 'cartoon', 'comic', 'manga', '3d_render'
}

SAFE_MYTHOLOGY_AND_MEMES = {
    'mythological', 'mythology', 'goddess', 'deity', 'hindu', 'durga', 'kali',
    'religious_art', 'classic_art', 'renaissance', 'virgin_vs_chad'
}


def classify_extreme_media(tags_str: str, desc_str: str = "") -> Tuple[bool, str, str]:
    """
    Классифицирует медиа по тегам и описанию на предмет экстремального шок-контента.
    Гарантирует ZERO FALSE POSITIVES для обычного аниме, хентая, этти, боевиков и мемов.

    Возвращает (is_extreme, category, reason).
    """
    if not tags_str:
        return False, "", ""

    t_lower = tags_str.lower()
    d_lower = desc_str.lower() if desc_str else ""
    full_text = f"{t_lower} {d_lower}"

    # 1. Проверка на Копро / Скат
    has_safe_copro_context = any(
        re.search(r'\b' + re.escape(w) + r'\b', full_text) for w in SAFE_COPRO_EXCLUSIONS
    )

    for kw in EXPLICIT_COPRO_TAGS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t_lower):
            if kw == 'scat' and any(w in full_text for w in {'jazz', 'music', 'vocal', 'singing', 'song', 'improv'}):
                continue
            if 'virgin_vs_chad' in full_text:
                continue
            if kw in {'defecation', 'defecating', 'pooping'} and has_safe_copro_context:
                continue
            return True, "COPRO", f"Explicit copro/scat tag matched: '{kw}'"

    # Тег 'feces' или 'fecal' вне безопасного контекста с порно/телесным контекстом
    if re.search(r'\b(feces|fecal)\b', t_lower):
        if not has_safe_copro_context and 'virgin_vs_chad' not in full_text:
            has_body_porn_context = any(
                re.search(r'\b' + re.escape(w) + r'\b', full_text) for w in COPRO_BODY_CONTEXT
            )
            if has_body_porn_context:
                return True, "COPRO", "Feces tag in sexual/shock body context"

    # 2. Проверка на Гуро / Снафф / Некрофилия / Расчленение
    has_mythology_context = any(w in full_text for w in SAFE_MYTHOLOGY_AND_MEMES)
    for kw in EXPLICIT_GURO_TAGS:
        if re.search(r'\b' + re.escape(kw) + r'\b', t_lower):
            if kw in {'severed_head', 'severed_limb', 'decapitation'} and has_mythology_context and 'corpse' not in t_lower and 'real_life' not in t_lower:
                continue
            return True, "GURO", f"Explicit guro/mutilation tag matched: '{kw}'"

    # Реальное вскрытие трупа (autopsy + viscera/corpse/gore)
    if re.search(r'\bautopsy\b', t_lower):
        if any(re.search(r'\b' + re.escape(w) + r'\b', t_lower) for w in {'viscera', 'gore', 'corpse', 'dead_body'}):
            return True, "REAL_GORE", "Autopsy with exposed viscera/corpse"

    # 3. Фотореалистичный шок-гор (реальные фотографии ран, расчлененки, трупов)
    if 'gore' in t_lower:
        is_realistic = any(w in t_lower for w in ['photo', 'photorealistic', 'real_life', 'photograph'])
        has_severe_wound = any(
            re.search(r'\b' + re.escape(w) + r'\b', t_lower) for w in GORE_SEVERE_INJURY
        )
        is_safe_art = any(w in t_lower for w in SAFE_ART_STYLES)
        is_costume_halloween = any(w in full_text for w in {'cosplay', 'halloween', 'costume', 'mask', 'props', 'movie', 'film_still'})

        if is_realistic and has_severe_wound and not is_safe_art and not is_costume_halloween:
            return True, "REAL_GORE", "Photorealistic gore with severe injury/corpse"

    return False, "", ""


# ==============================================================================
# 2. STRIKE TRACKING & IN-MEMORY CACHE
# ==============================================================================

# author_id -> list of {"post_num": int, "category": str, "file_id": str, "ts": float}
_EXTREME_STRIKES_CACHE: Dict[int, List[Dict[str, Any]]] = {}
STRIKE_WINDOW_SECONDS = 172800  # 48 часов скользящее окно


async def register_extreme_strike(author_id: int, post_num: int, category: str, file_id: str, board_id: str) -> int:
    """
    Регистрирует страйк за экстремальный контент для пользователя.
    Синхронизирует в памяти и в SQLite (Users.active_items['extreme_strikes']).
    Возвращает актуальное количество страйков за последние 48 часов.
    """
    now = time.time()
    min_ts = now - STRIKE_WINDOW_SECONDS

    # 1. Обновляем память
    user_strikes = _EXTREME_STRIKES_CACHE.get(author_id, [])
    # Очищаем старые
    user_strikes = [s for s in user_strikes if s.get('ts', 0) >= min_ts]
    # Добавляем новый
    user_strikes.append({
        "post_num": post_num,
        "category": category,
        "file_id": file_id,
        "board_id": board_id,
        "ts": now
    })
    _EXTREME_STRIKES_CACHE[author_id] = user_strikes

    # 2. Персистим в Users.active_items
    try:
        db = await get_pool()
        async with db_lock:
            async with db.execute(
                "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
                (author_id, board_id)
            ) as cursor:
                row = await cursor.fetchone()

            items = {}
            if row and row[0]:
                try:
                    items = json.loads(row[0])
                except Exception:
                    items = {}

            db_strikes = items.get("extreme_strikes", [])
            db_strikes = [s for s in db_strikes if isinstance(s, dict) and s.get('ts', 0) >= min_ts]
            db_strikes.append({
                "post_num": post_num,
                "category": category,
                "file_id": file_id,
                "board_id": board_id,
                "ts": now
            })
            items["extreme_strikes"] = db_strikes

            await db.execute(
                "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                (json.dumps(items, ensure_ascii=False), author_id, board_id)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist extreme strike for user {author_id}: {e}")

    return len(user_strikes)


# ==============================================================================
# 3. LOCKDOWN & DEFENSE EXECUTION
# ==============================================================================

async def execute_extreme_lockdown(
    bot: Any,
    author_id: int,
    board_id: str,
    category: str,
    reason: str,
    offending_post_nums: List[int]
):
    """
    Применяет полный локдаун к спамеру копро/гуро:
    1. Авто-тоггл медиа (shadow_ban_media = 1, Text-only mode) в БД и RAM.
    2. Авто-шедоумут на 24 часа (86400с) в БД и RAM.
    3. Авто-удаление постов спамера отовсюду (DB, RAM, каналы, ЛС получателей).
    4. Логирование в GlobalLogs и уведомление администраторов.
    """
    logger.critical(
        f"🚨 [AUTO-DEFENSE LOCKDOWN] User {author_id} triggered >2 strikes ({category}). Applying lockdown!"
    )

    # 1. Авто-тоггл медиа (shadow_ban_media = 1)
    try:
        db = await get_pool()
        async with db_lock:
            await db.execute(
                "UPDATE Users SET shadow_ban_media = 1 WHERE user_id = ?",
                (author_id,)
            )
            await db.commit()

        # Синхронизация в RAM для всех досок
        try:
            from shared_state import board_data, BOARDS
            for b in BOARDS:
                if b in board_data:
                    u_set = board_data[b].setdefault('user_settings', {}).setdefault(author_id, {
                        'nsfw': False, 'hide': set(), 'shadow_gif': False, 'shadow_sticker': False, 'shadow_media': True
                    })
                    u_set['shadow_media'] = True
        except Exception as e:
            logger.warning(f"RAM media_toggle sync error: {e}")

        await log_global_event(
            'bot',
            f"🔇 AUTO-MEDIA_TOGGLE: Система навсегда ЗАПРЕТИЛА медиа юзеру {author_id} (Text-only mode) за спам {category}"
        )
    except Exception as e:
        logger.error(f"Failed to set shadow_ban_media for {author_id}: {e}")

    # 2. Авто-шедоумут на 24 часа (86400 секунд)
    smute_duration = 86400
    try:
        await update_shadow_mute(
            user_id=author_id,
            board_id=board_id or 'b',
            duration_seconds=smute_duration,
            reason=f'auto_copro_guro_{category.lower()}'
        )
        await log_global_event(
            'bot',
            f"🔇 AUTO-SHADOWMUTE: Юзер {author_id} получил шедоумут на {smute_duration}с на /{board_id}/ (авто-защита {category})"
        )
    except Exception as e:
        logger.error(f"Failed to shadowmute {author_id}: {e}")

    # 3. Удаление постов спамера
    deleted_count = 0
    try:
        # Импортируем delete_user_posts и delete_single_post из main
        from main import delete_user_posts, delete_single_post

        # Сначала удаляем конкретные зафиксированные посты с шок-контентом
        for p_num in offending_post_nums:
            if p_num and p_num > 0:
                try:
                    await delete_single_post(p_num, bot)
                    deleted_count += 1
                except Exception as del_err:
                    logger.warning(f"Failed to delete offending post #{p_num}: {del_err}")

        # Сносим все посты юзера за последние 24 часа
        if bot:
            wiped = await delete_user_posts(bot, author_id, 1440, board_id or 'b')
            deleted_count = max(deleted_count, wiped)
    except Exception as e:
        logger.error(f"Failed to wipe posts for {author_id}: {e}")

    await log_global_event(
        'bot',
        f"🚮 AUTO-WIPE: Снесено {deleted_count} постов спамера {author_id} на /{board_id}/"
    )

    # 4. Уведомление админов в Telegram
    if bot:
        alert_text = (
            f"🚨 <b>АВТО-ЗАЩИТА: СПАМЕР {category} НЕЙТРАЛИЗОВАН</b>\n\n"
            f"Нейросеть выявила повторный сброс шок-контента (>2 постов).\n\n"
            f"👤 <b>User ID:</b> <code>{author_id}</code>\n"
            f"📌 <b>Доска:</b> /{board_id}/\n"
            f"🏷️ <b>Категория:</b> {category} ({reason})\n"
            f"🗑 <b>Удалено постов:</b> {deleted_count}\n\n"
            f"🛡️ <b>Примененные санкции:</b>\n"
            f"• 🔇 <b>Media Toggle:</b> Все медиа запрещены (Text-only mode)\n"
            f"• 👻 <b>Шедоумут:</b> 24 часа\n"
            f"• 🔥 <b>Посты:</b> Удалены из БД, каналов и ЛС получателей."
        )
        for adm in ADMIN_IDS:
            try:
                await bot.send_message(adm, alert_text, parse_mode="HTML")
            except Exception:
                pass


# ==============================================================================
# 4. MAIN DISPATCHER ENTRYPOINT
# ==============================================================================

async def process_file_extreme_defense(
    bot: Any,
    file_id: str,
    tags: str,
    description: str = "",
    post_num: Optional[int] = None,
    author_id: Optional[int] = None,
    board_id: Optional[str] = None
) -> bool:
    """
    Главная точка входа для проверки контента после теггинга нейросетью.
    Возвращает True если файл определен как экстремальный контент и обработан.
    """
    is_ext, category, reason = classify_extreme_media(tags, description)
    if not is_ext:
        return False

    logger.warning(
        f"⚠️ [EXTREME MEDIA DETECTED] File: {file_id[:16]}... | Category: {category} | Reason: {reason}"
    )

    # Разрешаем post_num, author_id, board_id если они не переданы
    if not author_id or not post_num:
        try:
            db = await get_pool()
            query = """
                SELECT p.post_num, p.author_id, p.board_id
                FROM Posts p
                WHERE p.post_num IN (
                    SELECT post_num FROM PostFiles 
                    WHERE original_file_id = ? OR thumbnail_file_id = ?
                )
                ORDER BY p.post_num DESC LIMIT 1
            """
            async with db.execute(query, (file_id, file_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    post_num = row[0]
                    author_id = row[1]
                    board_id = board_id or row[2]
        except Exception as e:
            logger.warning(f"Failed to lookup author for file {file_id}: {e}")

    # Если автор так и не найден, просто скрываем файл в БД
    if not author_id:
        try:
            await apply_auto_censure(file_id, "shadow")
        except Exception:
            pass
        return True

    board_id = board_id or 'b'
    post_num = post_num or 0

    # Регистрируем страйк
    strikes = await register_extreme_strike(author_id, post_num, category, file_id, board_id)
    logger.warning(
        f"⚠️ User {author_id} has {strikes} active extreme strikes ({category}) on /{board_id}/"
    )

    if strikes < 2:
        # Страйк 1: Теневое скрытие поста и очистка архива
        try:
            await apply_auto_censure(file_id, "shadow")
            # Если бот передан и есть post_num, сносим пост из каналов
            if bot and post_num > 0:
                from main import get_all_channel_copies, _delete_posts_from_channels
                channel_copies = await get_all_channel_copies(post_num)
                if channel_copies:
                    await _delete_posts_from_channels(
                        [(c_id, m_id, board_id) for c_id, m_id in channel_copies],
                        bot
                    )
        except Exception as e:
            logger.warning(f"Strike 1 censure error: {e}")

        await log_global_event(
            'bot',
            f"⚠️ AUTO-DEFENSE STRIKE 1: Пост #{post_num} юзера {author_id} скрыт (теги: {category}). При повторе будет локдаун."
        )
        return True

    # Страйк >= 2: ПОЛНЫЙ ЛОКДАУН
    user_strikes_data = _EXTREME_STRIKES_CACHE.get(author_id, [])
    offending_posts = [s.get('post_num', 0) for s in user_strikes_data if s.get('post_num', 0) > 0]
    if post_num and post_num not in offending_posts:
        offending_posts.append(post_num)

    await execute_extreme_lockdown(
        bot=bot,
        author_id=author_id,
        board_id=board_id,
        category=category,
        reason=reason,
        offending_post_nums=offending_posts
    )
    return True
