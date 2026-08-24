# -*- coding: utf-8 -*-
"""
Централизованный модуль публикации событий в новостной канал «Тгач Новости» и канал «Лучшее».
Поддерживает:
- «Лучшее» (5+ реакций): богатый постинг с сохранением медиа (фото/видео/гиф/альбомы), ссылок и автора.
- «Тгач Новости»:
    1. Юбилеи и красивые гето-номера постов (квадриплы, квинты, миллионники).
    2. Мега-заносы в казино (джекпоты x50+ или выигрыши > 100,000 ₪).
    3. Апгрейды тира яхты Абу при сборе средств в Фонд Казны.
    4. Крупные рейды ОБЭП и раскулачивания олигархов.
"""

import os
import time
import json
import random
import logging
import asyncio
from typing import Optional, Dict, Any, List

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile, URLInputFile,
    InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument
)
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError
)

from common.config import *
from common.board_config import BOARD_CONFIG
from common.html_utils import escape_html
from common.text_utils import clean_html_tags, sanitize_html
from common.database import (
    get_post_by_num, update_post_content, add_channel_copy, get_pool
)
from common.anon_identity import get_anon_id
import shared_state

logger = logging.getLogger("news_publisher")

def get_target_channels() -> tuple[int, int]:
    """
    Возвращает единый канал (news_channel_id, news_channel_id).
    Канал «Тгач Новости» полностью интегрирует в себя «Лучшее» — весь топовый контент
    (посты 5+ реакций, геты, джекпоты, апгрейды яхты Абу) публикуется в один официальный новостной канал.
    """
    primary_ch = int(os.getenv(
        "NEWS_CHANNEL_ID",
        os.getenv("BEST_CHANNEL_ID", getattr(shared_state, "NEWS_CHANNEL_ID", getattr(shared_state, "BEST_CHANNEL_ID", -1002827087363)))
    ))
    return primary_ch, primary_ch

async def _resolve_channel_media_source(bot: Bot, orig_fid: str, content: dict):
    """
    Разрешает источник медиафайла для отправки в канал.
    """
    if not orig_fid:
        return None
    try:
        from archive_manager import _resolve_media_source
        return await _resolve_media_source(bot, orig_fid, content)
    except Exception as e:
        logger.debug(f"Media source resolution fallback for {orig_fid}: {e}")
        return orig_fid

async def send_channel_content(
    bot: Bot,
    channel_id: int,
    content: dict,
    header_text: str,
    body_text: str = "",
    footer_text: str = ""
) -> Optional[int]:
    """
    Универсальная отправка контента (текст, фото, видео, GIF, аудио, альбомы) в указанный канал.
    Возвращает message_id отправленного сообщения.
    """
    if not channel_id or channel_id == 0:
        return None

    full_text = f"{header_text}\n\n{body_text}".strip()
    if footer_text:
        full_text = f"{full_text}\n\n{footer_text}".strip()

    # Ограничение по длине Telegram
    content_type = content.get("type", "text")
    ct_str = str(content_type).split('.')[-1].lower()

    if ct_str in ('photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note', 'media_group'):
        caption = full_text[:1020] + "..." if len(full_text) > 1024 else full_text
    else:
        caption = full_text[:4090] + "..." if len(full_text) > 4096 else full_text

    common_args = {
        "chat_id": channel_id,
        "caption": caption,
        "parse_mode": "HTML"
    }

    try:
        # 1. Альбомы (Media Group)
        if ct_str == 'media_group':
            media_list = content.get('media', []) or content.get('files', [])
            if media_list and isinstance(media_list, list):
                builder = MediaGroupBuilder(caption=caption)
                for idx, m_item in enumerate(media_list[:10]):
                    fid = m_item.get('file_id') or m_item.get('tg_file_id') if isinstance(m_item, dict) else m_item
                    m_type = m_item.get('type', 'photo') if isinstance(m_item, dict) else 'photo'
                    src = await _resolve_channel_media_source(bot, fid, m_item if isinstance(m_item, dict) else {})
                    if m_type == 'video':
                        builder.add_video(media=src)
                    elif m_type == 'audio':
                        builder.add_audio(media=src)
                    elif m_type == 'document':
                        builder.add_document(media=src)
                    else:
                        builder.add_photo(media=src)
                
                group_items = builder.build()
                if group_items:
                    res = await bot.send_media_group(chat_id=channel_id, media=group_items)
                    return res[0].message_id if res else None

        # 2. Одиночные медиа
        file_id = content.get('file_id')
        if not file_id and content.get('files'):
            files = content.get('files')
            if isinstance(files, list) and files:
                file_id = files[0].get('file_id') or files[0].get('tg_file_id') if isinstance(files[0], dict) else files[0]

        if file_id:
            media_src = await _resolve_channel_media_source(bot, file_id, content)
            if ct_str == 'photo':
                res = await bot.send_photo(photo=media_src, **common_args)
                return res.message_id
            elif ct_str == 'video':
                res = await bot.send_video(video=media_src, **common_args)
                return res.message_id
            elif ct_str == 'animation':
                res = await bot.send_animation(animation=media_src, **common_args)
                return res.message_id
            elif ct_str == 'document':
                res = await bot.send_document(document=media_src, **common_args)
                return res.message_id
            elif ct_str == 'audio':
                res = await bot.send_audio(audio=media_src, **common_args)
                return res.message_id

        # 3. Обычный текст
        res = await bot.send_message(
            chat_id=channel_id,
            text=caption,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
        return res.message_id

    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning(f"Failed to post to channel {channel_id}: {e}")
        # Пробуем без форматирования HTML при ошибке парсера
        if "can't parse entities" in str(e).lower() or "find end tag" in str(e).lower():
            try:
                plain_caption = clean_html_tags(caption)
                if file_id and ct_str == 'photo':
                    res = await bot.send_photo(chat_id=channel_id, photo=file_id, caption=plain_caption)
                else:
                    res = await bot.send_message(chat_id=channel_id, text=plain_caption)
                return res.message_id
            except Exception:
                pass
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
    except Exception as e:
        logger.error(f"Unexpected error posting to channel {channel_id}: {e}", exc_info=True)

    return None

async def publish_to_best_channel(
    bot: Bot,
    board_id: str,
    post_num: int,
    post_data: dict,
    likes_count: int
) -> bool:
    """
    Публикует пост в канал «Лучшее» при наборе 5+ реакций.
    Гарантирует атомарную защиту от повторных пересылок.
    """
    _, best_channel_id = get_target_channels()
    if not best_channel_id or best_channel_id == 0:
        return False

    # 1. Проверяем флаг в памяти
    if post_data.get('forwarded_to_best'):
        return False

    content = post_data.get('content', {})
    if content.get('forwarded_to_best'):
        post_data['forwarded_to_best'] = True
        return False

    # Помечаем пост как отправленный немедленно
    post_data['forwarded_to_best'] = True
    content['forwarded_to_best'] = True

    # 2. Форматируем красивую карточку поста
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', f"/{board_id}/")
    bot_info = await bot.get_me()
    bot_uname = bot_info.username or "tgach_bot"

    author_id = post_data.get('author_id', 0)
    anon_tag = f"<code>[ID:{get_anon_id(author_id)}]</code>" if author_id > 0 else "Аноним"

    header_text = (
        f"🔥 <b>ГОДНОТА С /{board_id}/ — {board_name}</b> (Пост #{post_num})\n"
        f"⭐️ <b>Рейтинг:</b> +{likes_count} реакций"
    )

    raw_text = content.get('text') or content.get('caption') or ''
    sanitized_text = sanitize_html(raw_text) if raw_text else "<i>(Медиа-пост)</i>"

    # Ссылки и подвал
    footer_text = (
        f"👤 <b>Автор:</b> {anon_tag}\n"
        f"👉 <a href=\"https://t.me/{bot_uname}?start=post_{post_num}\">Открыть пост в боте</a>"
    )

    # 3. Отправляем в канал
    msg_id = await send_channel_content(
        bot=bot,
        channel_id=best_channel_id,
        content=content,
        header_text=header_text,
        body_text=sanitized_text,
        footer_text=footer_text
    )

    if msg_id:
        try:
            await add_channel_copy(post_num, best_channel_id, msg_id)
            await update_post_content(post_num, content)
            logger.info(f"✅ Post #{post_num} from /{board_id}/ successfully published to Best Channel ({best_channel_id})")
            return True
        except Exception as e:
            logger.warning(f"Failed to record best channel copy for #{post_num}: {e}")
            return True

    return False

async def publish_post_numeral_milestone(
    bot: Bot,
    board_id: str,
    post_num: int,
    numeral_info: dict,
    content: dict,
    author_id: int
) -> bool:
    """
    Публикует новость о красивом номере поста (квадрипл, квинт, юбилей) в канал «Тгач Новости».
    """
    news_channel_id, _ = get_target_channels()
    if not news_channel_id or news_channel_id == 0:
        return False

    label = numeral_info.get('label', 'Гет').upper()
    emojis = numeral_info.get('emojis', ('🎯', '🚀', '🔥', '🍀'))
    emoji = random.choice(emojis)
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', f"/{board_id}/")

    bot_info = await bot.get_me()
    bot_uname = bot_info.username or "tgach_bot"
    anon_tag = f"<code>[ID:{get_anon_id(author_id)}]</code>" if author_id > 0 else "Аноним"

    header_text = (
        f"🎰 {emoji} <b>{label} ПОЙМАН! Пост #{post_num} на /{board_id}/</b> {emoji}\n"
        f"🏛️ <b>Раздел:</b> {board_name}\n"
        f"👤 <b>Счастливчик:</b> {anon_tag}"
    )

    raw_text = content.get('text') or content.get('caption') or ''
    sanitized_text = sanitize_html(raw_text) if raw_text else "<i>(Без текста)</i>"

    footer_text = f"👉 <a href=\"https://t.me/{bot_uname}?start=post_{post_num}\">Перейти к посту в боте</a>"

    msg_id = await send_channel_content(
        bot=bot,
        channel_id=news_channel_id,
        content=content,
        header_text=header_text,
        body_text=sanitized_text,
        footer_text=footer_text
    )

    return bool(msg_id)

async def publish_casino_jackpot_news(
    bot: Bot,
    user_id: int,
    game_type: str,
    bet_amount: int,
    win_amount: int,
    multiplier: float,
    symbols: str = "",
    board_id: str = "b"
) -> bool:
    """
    Публикует новость о мега-заносе в казино (джекпот x50+ или выигрыш > 100k ₪) в «Тгач Новости».
    """
    news_channel_id, _ = get_target_channels()
    if not news_channel_id or news_channel_id == 0:
        return False

    bot_info = await bot.get_me()
    bot_uname = bot_info.username or "tgach_bot"
    anon_tag = f"<code>[ID:{get_anon_id(user_id)}]</code>"

    header_text = f"🎰🔥 <b>МЕГА-ЗАНОС В КАЗИНО ТГАЧА!</b> 🔥🎰"

    game_names = {
        "slots": "Слоты 777 (Однорукий бандит)",
        "coinflip": "Подбрасывание монетки",
        "blackjack": "Блэкджек (21)",
        "roulette": "Русская рулетка"
    }
    game_label = game_names.get(game_type, game_type.capitalize())

    lines = [
        f"👤 <b>Игрок:</b> {anon_tag}",
        f"🎲 <b>Дисциплина:</b> {game_label}",
        f"💵 <b>Ставка:</b> <code>{bet_amount:,} ₪</code>",
        f"💰 <b>Выплата:</b> <b>+{win_amount:,} ₪</b> (<b>x{multiplier:.1f}</b>)"
    ]
    if symbols:
        lines.append(f"👑 <b>Комбинация:</b> {symbols}")

    lines.append("\n💬 <i>«ОБЭП и налоговая инспекция Абу уже взяли счастливчика на карандаш!»</i>")
    body_text = "\n".join(lines)

    footer_text = f"👉 <a href=\"https://t.me/{bot_uname}?start=casino\">Испытать удачу в казино</a>"

    msg_id = await send_channel_content(
        bot=bot,
        channel_id=news_channel_id,
        content={"type": "text"},
        header_text=header_text,
        body_text=body_text,
        footer_text=footer_text
    )

    return bool(msg_id)

async def publish_abu_fund_tier_upgrade(
    bot: Bot,
    old_tier: int,
    new_tier: int,
    current_fund: int,
    target_fund: int = 1000000000
) -> bool:
    """
    Публикует новость о повышении уровня Фонда Яхты Абу в «Тгач Новости».
    """
    news_channel_id, _ = get_target_channels()
    if not news_channel_id or news_channel_id == 0:
        return False

    try:
        from abu_fund_lore import YACHT_TIERS, GLOBAL_EVENTS
        tier_info = YACHT_TIERS.get(new_tier, {})
        tier_title = tier_info.get("title", f"Тир {new_tier}")
        tier_headline = tier_info.get("headline", "Казна Абу бьет рекорды!")
        perks = tier_info.get("perks", [])
        quote = tier_info.get("quote", "Абу доволен вашими шекелями!")
    except Exception:
        tier_title = f"Уровень Яхты {new_tier}"
        tier_headline = "Офшорный фонд успешно пополнен!"
        perks = ["Золотой унитаз", "Вертолетная площадка"]
        quote = "Слава Падишаху!"

    bot_info = await bot.get_me()
    bot_uname = bot_info.username or "tgach_bot"

    pct = (current_fund / target_fund * 100) if target_fund > 0 else 0
    filled_blocks = int(pct / 10)
    bar = "█" * min(filled_blocks, 10) + "░" * max(0, 10 - filled_blocks)

    header_text = f"🛥️🎉 <b>КАЗНА АБУ ПОВЫСИЛА УРОВЕНЬ! НОВЫЙ РАНГ ЯХТЫ!</b> 🎉🛥️"

    lines = [
        f"🏷️ <b>Ранг судна:</b> <u>{tier_title}</u> (Тир {new_tier})",
        f"📝 <i>«{tier_headline}»</i>\n",
        f"🛠️ <b>Установленное оборудование:</b>"
    ]
    for p in perks[:4]:
        lines.append(f"  • {p}")

    lines.append(f"\n💬 <b>Слово Падишаха:</b>\n<i>«{quote}»</i>\n")
    lines.append(f"📊 <b>Собрано в казну:</b> <code>{current_fund:,} ₪</code> / <code>{target_fund:,} ₪</code> ([{bar}] {pct:.2f}%)")

    body_text = "\n".join(lines)
    footer_text = f"👉 <a href=\"https://t.me/{bot_uname}?start=abu_fund\">Открыть Казну Абу</a>"

    msg_id = await send_channel_content(
        bot=bot,
        channel_id=news_channel_id,
        content={"type": "text"},
        header_text=header_text,
        body_text=body_text,
        footer_text=footer_text
    )

    return bool(msg_id)

async def publish_oligarch_raid_news(
    bot: Bot,
    user_id: int,
    tax_amount: int,
    old_balance: int,
    new_balance: int,
    category: str = "wealth_tax",
    reason: str = "Налог на сверхбогатство"
) -> bool:
    """
    Публикует новость о крупном раскулачивании / рейде ОБЭП в «Тгач Новости».
    """
    news_channel_id, _ = get_target_channels()
    if not news_channel_id or news_channel_id == 0 or tax_amount < 50000:
        return False

    bot_info = await bot.get_me()
    bot_uname = bot_info.username or "tgach_bot"
    anon_tag = f"<code>[ID:{get_anon_id(user_id)}]</code>"

    header_text = f"🚨⚖️ <b>СПЕЦОПЕРАЦИЯ ОБЭП: РАСКУЛАЧИВАНИЕ ОЛИГАРХА!</b> ⚖️🚨"

    lines = [
        f"👤 <b>Фигурант дела:</b> {anon_tag}",
        f"💸 <b>Изъято в казну Абу:</b> <code>-{tax_amount:,} ₪</code>",
        f"💳 <b>Остаток на счетах:</b> <code>{new_balance:,} ₪</code>",
        f"📋 <b>Основание:</b> {reason}\n",
        f"💬 <i>«Средства направлены на полировку вертолетной площадки на яхте Падишаха.»</i>"
    ]
    body_text = "\n".join(lines)
    footer_text = f"👉 <a href=\"https://t.me/{bot_uname}?start=abu_fund\">Казна Абу</a>"

    msg_id = await send_channel_content(
        bot=bot,
        channel_id=news_channel_id,
        content={"type": "text"},
        header_text=header_text,
        body_text=body_text,
        footer_text=footer_text
    )

    return bool(msg_id)
